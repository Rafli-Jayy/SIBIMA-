"""Patch 5C read-only SQL analytics for SIBIMA-AI.

Invoked INSIDE AIReadRepository's pre-existing read-only transaction after
rechecking the logged-in user's role/status from PostgreSQL. All inputs are
validated by ai_query_planner. No arbitrary SQL and no database writes.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from app.repositories.class_access_sql import AKSES_TERKUNCI_SQL, ENROLLMENT_TERAKHIR_TERSEDIA_SQL
from app.services.ai_query_planner import TOOL_ROLE, validate_plan, plan_metadata

PAGE_SIZE = 20
TZ = "Asia/Jakarta"  # SQL timezone is a literal under application control.

_ENROLLMENT_FILTER = """
WITH f AS (SELECT %s::int AS pid, %s::text AS state, %s::date AS start_date, %s::date AS end_date),
selected AS (
    SELECT e.* FROM enrollments e CROSS JOIN f
    WHERE (f.pid IS NULL OR e.program_id=f.pid)
      AND (f.state IS NULL OR e.status::text=f.state)
      AND (f.start_date IS NULL OR (e.created_at AT TIME ZONE 'Asia/Jakarta')::date>=f.start_date)
      AND (f.end_date IS NULL OR (e.created_at AT TIME ZONE 'Asia/Jakarta')::date<=f.end_date)
)
"""
_ENROLLMENT_COUNT = _ENROLLMENT_FILTER + """
SELECT (SELECT COUNT(*) FROM users WHERE role='siswa' AND status='aktif')::int AS akun_siswa_aktif_global,
       COUNT(*)::int AS jumlah_enrollment,
       COUNT(DISTINCT student_id)::int AS siswa_unik,
       COUNT(DISTINCT program_id)::int AS jumlah_program,
       COUNT(*) FILTER (WHERE status='menunggu')::int AS menunggu,
       COUNT(*) FILTER (WHERE status='menunggu_pembayaran')::int AS menunggu_pembayaran,
       COUNT(*) FILTER (WHERE status='aktif')::int AS aktif,
       COUNT(*) FILTER (WHERE status='ditolak')::int AS ditolak,
       COUNT(*) FILTER (WHERE status='batal')::int AS batal,
       COUNT(*) FILTER (WHERE status='selesai')::int AS selesai
FROM selected
"""
_ENROLLMENT_BY_PROGRAM = _ENROLLMENT_FILTER + """
SELECT p.id AS program_id, p.nama AS program,
       COUNT(*)::int AS jumlah_enrollment,
       COUNT(DISTINCT se.student_id)::int AS siswa_unik
FROM selected se JOIN programs p ON p.id=se.program_id
GROUP BY p.id, p.nama
ORDER BY jumlah_enrollment DESC, p.id
LIMIT 20
"""

_INVOICE_FILTER = """
WITH f AS (SELECT %s::int AS pid, %s::date AS start_period,
                  %s::date AS end_period, %s::text AS lateness),
selected AS (
    SELECT i.id, i.jumlah, i.periode, i.jatuh_tempo, e.program_id
    FROM invoices i JOIN enrollments e ON e.id=i.enrollment_id
    CROSS JOIN f
    WHERE i.status='belum_dibayar'
      AND (f.pid IS NULL OR e.program_id=f.pid)
      AND (f.start_period IS NULL OR i.periode >= f.start_period)
      AND (f.end_period IS NULL OR i.periode <= f.end_period)
      AND (f.lateness='semua' OR
           (f.lateness='overdue' AND i.jatuh_tempo < (now() AT TIME ZONE 'Asia/Jakarta')::date) OR
           (f.lateness='lewat_h3' AND i.jatuh_tempo < (now() AT TIME ZONE 'Asia/Jakarta')::date - 3))
)
"""
_INVOICE_TOTAL = _INVOICE_FILTER + """
SELECT COUNT(*)::int AS jumlah_invoice,
       COALESCE(SUM(jumlah), 0)::numeric(18,2) AS nominal_bruto_belum_lunas
FROM selected
"""
_INVOICE_GROUP_COUNT = {
    "program": _INVOICE_FILTER + "SELECT COUNT(DISTINCT program_id)::int AS kelompok_total FROM selected",
    "periode": _INVOICE_FILTER + "SELECT COUNT(DISTINCT periode)::int AS kelompok_total FROM selected",
}
_INVOICE_GROUP_LIST = {
    "program": _INVOICE_FILTER + """
        SELECT p.id AS program_id, p.nama AS program,
               COUNT(*)::int AS jumlah_invoice,
               SUM(se.jumlah)::numeric(18,2) AS nominal_bruto_belum_lunas
        FROM selected se JOIN programs p ON p.id=se.program_id
        GROUP BY p.id,p.nama ORDER BY nominal_bruto_belum_lunas DESC,p.id LIMIT 20
    """,
    "periode": _INVOICE_FILTER + """
        SELECT se.periode, COUNT(*)::int AS jumlah_invoice,
               SUM(se.jumlah)::numeric(18,2) AS nominal_bruto_belum_lunas
        FROM selected se GROUP BY se.periode ORDER BY se.periode DESC LIMIT 20
    """,
}

_PROGRAM_CTE = """
WITH f AS (SELECT %s::int AS pid, %s::text AS enrollment_status),
selected AS (
    SELECT e.* FROM enrollments e CROSS JOIN f
    WHERE (f.enrollment_status IS NULL OR e.status::text=f.enrollment_status)
),
enroll_stats AS (
    SELECT program_id, COUNT(*)::int AS jumlah_enrollment,
           COUNT(DISTINCT student_id)::int AS siswa_unik
    FROM selected GROUP BY program_id
),
active_stats AS (
    SELECT program_id, COUNT(*)::int AS pendaftaran_aktif,
           COUNT(DISTINCT student_id)::int AS siswa_aktif_unik
    FROM enrollments WHERE status='aktif' GROUP BY program_id
),
schedule_stats AS (
    SELECT program_id, COUNT(*)::int AS jadwal_aktif,
           COUNT(DISTINCT tutor_id)::int AS tutor_unik
    FROM schedules WHERE aktif=TRUE GROUP BY program_id
)
"""
_PROGRAM_COUNT = _PROGRAM_CTE + """
SELECT COUNT(*)::int AS jumlah_program FROM programs p CROSS JOIN f
WHERE (f.pid IS NULL OR p.id=f.pid)
"""
_PROGRAM_LIST = _PROGRAM_CTE + """
SELECT p.id AS program_id,p.nama AS program, p.status::text AS status_program, p.kuota,
       COALESCE(en.jumlah_enrollment,0) AS jumlah_enrollment,
       COALESCE(en.siswa_unik,0) AS siswa_unik,
       COALESCE(ac.pendaftaran_aktif,0) AS pendaftaran_aktif,
       COALESCE(ac.siswa_aktif_unik,0) AS siswa_aktif_unik,
       COALESCE(sc.jadwal_aktif,0) AS jadwal_aktif,
       COALESCE(sc.tutor_unik,0) AS tutor_unik
FROM programs p CROSS JOIN f
LEFT JOIN enroll_stats en ON en.program_id=p.id
LEFT JOIN active_stats ac ON ac.program_id=p.id
LEFT JOIN schedule_stats sc ON sc.program_id=p.id
WHERE (f.pid IS NULL OR p.id=f.pid)
ORDER BY p.nama, p.id LIMIT 20
"""

_ATTENDANCE_CTE = """
WITH f AS (SELECT %s::int AS pid, %s::date AS start_date, %s::date AS end_date),
sessions AS (
    SELECT cs.id AS session_id, s.program_id FROM class_sessions cs
    JOIN schedules s ON s.id=cs.schedule_id CROSS JOIN f
    WHERE cs.status='selesai'
      AND (f.pid IS NULL OR s.program_id=f.pid)
      AND (f.start_date IS NULL OR cs.tanggal >= f.start_date)
      AND (f.end_date IS NULL OR cs.tanggal <= f.end_date)
),
records AS (
    SELECT a.status FROM attendances a
    JOIN sessions ss ON ss.session_id=a.session_id
    JOIN enrollments e ON e.id=a.enrollment_id AND e.student_id=a.student_id
                      AND e.program_id=ss.program_id
)
"""
_TUTOR_ATTENDANCE_CTE = """
WITH f AS (SELECT %s::int AS pid, %s::date AS start_date, %s::date AS end_date, %s::int AS tutor_id),
sessions AS (
    SELECT cs.id AS session_id, s.program_id FROM class_sessions cs
    JOIN schedules s ON s.id=cs.schedule_id CROSS JOIN f
    WHERE cs.status='selesai' AND s.aktif=TRUE AND s.tutor_id=f.tutor_id
      AND (f.pid IS NULL OR s.program_id=f.pid)
      AND (f.start_date IS NULL OR cs.tanggal >= f.start_date)
      AND (f.end_date IS NULL OR cs.tanggal <= f.end_date)
),
records AS (
    SELECT a.status FROM attendances a
    JOIN sessions ss ON ss.session_id=a.session_id
    JOIN enrollments e ON e.id=a.enrollment_id AND e.student_id=a.student_id
                      AND e.program_id=ss.program_id AND e.status='aktif'
)
"""
_ATTENDANCE_TOTAL = """
SELECT (SELECT COUNT(*) FROM sessions)::int AS jumlah_sesi_selesai,
       COUNT(*)::int AS jumlah_catatan,
       COUNT(*) FILTER (WHERE status='H')::int AS hadir,
       COUNT(*) FILTER (WHERE status='I')::int AS izin,
       COUNT(*) FILTER (WHERE status='S')::int AS sakit,
       COUNT(*) FILTER (WHERE status='A')::int AS alpa,
       ROUND(100.0 * COUNT(*) FILTER (WHERE status='H') / NULLIF(COUNT(*),0),2)
           AS persentase_hadir_tercatat
FROM records
"""

_TUTOR_PROGRAM_CTE = """
WITH f AS (SELECT %s::int AS tutor_id, %s::int AS pid),
taught AS (
    SELECT s.program_id,COUNT(*)::int AS jadwal_aktif
    FROM schedules s CROSS JOIN f
    WHERE s.tutor_id=f.tutor_id AND s.aktif=TRUE
      AND (f.pid IS NULL OR s.program_id=f.pid)
    GROUP BY s.program_id
),
students AS (
    SELECT e.program_id, COUNT(DISTINCT e.student_id)::int AS siswa_aktif_unik,
           COUNT(*)::int AS pendaftaran_aktif
    FROM enrollments e JOIN taught t ON t.program_id=e.program_id
    JOIN users u ON u.id=e.student_id AND u.role='siswa' AND u.status='aktif'
    WHERE e.status='aktif' GROUP BY e.program_id
)
"""
_TUTOR_PROGRAM_COUNT = _TUTOR_PROGRAM_CTE + "SELECT COUNT(*)::int AS jumlah_program FROM taught"
_TUTOR_PROGRAM_LIST = _TUTOR_PROGRAM_CTE + """
SELECT p.id AS program_id, p.nama AS program, t.jadwal_aktif,
       COALESCE(st.siswa_aktif_unik,0) AS siswa_aktif_unik,
       COALESCE(st.pendaftaran_aktif,0) AS pendaftaran_aktif
FROM taught t JOIN programs p ON p.id=t.program_id
LEFT JOIN students st ON st.program_id=t.program_id
ORDER BY p.nama, p.id LIMIT 20
"""

_STUDENT_ELIGIBLE = f"""
WITH f AS (SELECT %s::int AS user_id, %s::int AS pid),
eligible AS (
    SELECT e.id AS enrollment_id, e.program_id, e.created_at
    FROM enrollments e CROSS JOIN f
    WHERE e.student_id=f.user_id
      AND (f.pid IS NULL OR e.program_id=f.pid)
      AND {ENROLLMENT_TERAKHIR_TERSEDIA_SQL}
      AND NOT {AKSES_TERKUNCI_SQL}
),
grade_stats AS (
    SELECT e.program_id, COUNT(*)::int AS jumlah_nilai,
           ROUND(AVG(g.nilai),2) AS rata_rata_nilai_aritmetika
    FROM eligible e JOIN grades g ON g.enrollment_id=e.enrollment_id
    GROUP BY e.program_id
),
attendance_stats AS (
    SELECT e.program_id,COUNT(*)::int AS catatan_kehadiran,
           COUNT(*) FILTER (WHERE a.status='H')::int AS hadir,
           COUNT(*) FILTER (WHERE a.status='I')::int AS izin,
           COUNT(*) FILTER (WHERE a.status='S')::int AS sakit,
           COUNT(*) FILTER (WHERE a.status='A')::int AS alpa
    FROM eligible e
    JOIN attendances a ON a.enrollment_id=e.enrollment_id
    JOIN class_sessions cs ON cs.id=a.session_id AND cs.status='selesai'
    JOIN schedules s ON s.id=cs.schedule_id AND s.program_id=e.program_id
    WHERE a.student_id=(SELECT user_id FROM f)
      AND cs.tanggal >= (e.created_at AT TIME ZONE 'Asia/Jakarta')::date
    GROUP BY e.program_id
)
"""
_STUDENT_COUNT = _STUDENT_ELIGIBLE + "SELECT COUNT(*)::int AS jumlah_program FROM eligible"
_STUDENT_LIST = _STUDENT_ELIGIBLE + """
SELECT p.id AS program_id,p.nama AS program,
       COALESCE(g.jumlah_nilai,0) AS jumlah_nilai,
       g.rata_rata_nilai_aritmetika,
       COALESCE(a.catatan_kehadiran,0) AS catatan_kehadiran,
       COALESCE(a.hadir,0) AS hadir, COALESCE(a.izin,0) AS izin,
       COALESCE(a.sakit,0) AS sakit, COALESCE(a.alpa,0) AS alpa
FROM eligible e JOIN programs p ON p.id=e.program_id
LEFT JOIN grade_stats g ON g.program_id=e.program_id
LEFT JOIN attendance_stats a ON a.program_id=e.program_id
ORDER BY p.nama,p.id LIMIT 20
"""


def _safe(value):
    if isinstance(value, (date, datetime, time, Decimal)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _safe(v) for k, v in value.items()}
    return value


def _one(cur, sql, params):
    cur.execute(sql, params)
    return cur.fetchone() or {}


def _page(cur, sql, params):
    cur.execute(sql, params)
    return cur.fetchmany(PAGE_SIZE)


def execute_analytics(cur, user_id: int, role: str, name: str, args: dict) -> dict:
    """Called only after AIReadRepository verified the database principal.

    Repeat validation here to defend against direct repository calls that
    bypass the controller. `user_id` is never read from LLM arguments.
    """
    if type(user_id) is not int or user_id <= 0:
        raise PermissionError("Sesi tidak valid.")
    validated = validate_plan(name, args, role)
    meta = plan_metadata(name, role)
    pid = validated.get("program_id")
    period = {k: validated.get(k) for k in ("tanggal_dari", "tanggal_sampai", "periode_dari", "periode_sampai")}
    rows = []
    if name == "admin_enrollment_overview":
        params = (pid, validated.get("status"), validated.get("tanggal_dari"), validated.get("tanggal_sampai"))
        data = _one(cur, _ENROLLMENT_COUNT, params)
        rows = _page(cur, _ENROLLMENT_BY_PROGRAM, params)
        group_total = int(data.get("jumlah_program") or 0)
        total = int(data.get("jumlah_enrollment") or 0)
        data = {**data, "per_program": rows}
        definition = "Akun siswa aktif global terpisah dari baris enrollment dan student_id unik. Filter hanya berlaku pada enrollment."
    elif name == "admin_receivables_summary":
        params = (pid, validated.get("periode_dari"), validated.get("periode_sampai"), validated["keterlambatan"])
        data = _one(cur, _INVOICE_TOTAL, params)
        by = validated["kelompok"]
        total = int(data.get("jumlah_invoice") or 0)
        group_total = 1
        if by != "total":
            group_total = int(_one(cur, _INVOICE_GROUP_COUNT[by], params).get("kelompok_total") or 0)
            rows = _page(cur, _INVOICE_GROUP_LIST[by], params)
        data = {**data, "kelompok": by, "rincian": rows}
        definition = "Jumlah nominal bruto SELURUH invoice status belum_dibayar, bukan saldo bersih pembayaran; periode adalah invoices.periode (awal bulan)."
    elif name == "admin_program_activity":
        params = (pid, validated.get("status_enrollment"))
        total = int(_one(cur, _PROGRAM_COUNT, params).get("jumlah_program") or 0)
        group_total = total
        rows = _page(cur, _PROGRAM_LIST, params)
        data = {"per_program": rows, "jumlah_program": total}
        definition = "Pendaftaran/siswa unik sesuai filter status; pendaftaran_aktif dihitung tanpa filter status; jadwal aktif dan Tutor unik dihitung terpisah."
    elif name in {"admin_attendance_summary", "tutor_attendance_statistics"}:
        params = (pid, validated.get("tanggal_dari"), validated.get("tanggal_sampai"))
        if name == "admin_attendance_summary":
            sql = _ATTENDANCE_CTE + _ATTENDANCE_TOTAL
        else:
            sql = _TUTOR_ATTENDANCE_CTE + _ATTENDANCE_TOTAL
            params += (user_id,)
        data = _one(cur, sql, params)
        total = int(data.get("jumlah_catatan") or 0)
        group_total = 1
        definition = ("Hanya sesi selesai; persentase = hadir / seluruh catatan H/I/S/A. "
                      "Tidak ada absensi tercatat berarti persentase tidak tersedia (NULL), bukan nol persen. "
                      "Sesi belum dilaporkan tidak dihitung.")
    elif name == "tutor_program_summary":
        params = (user_id, pid)
        total = int(_one(cur, _TUTOR_PROGRAM_COUNT, params).get("jumlah_program") or 0)
        group_total = total
        rows = _page(cur, _TUTOR_PROGRAM_LIST, params)
        data = {"jumlah_program": total, "per_program": rows}
        definition = "Jadwal aktif Tutor login; siswa aktif hanya siswa dengan enrollment aktif di program itu, bukan bukti kehadiran di sesi Tutor."
    elif name == "student_progress_summary":
        params = (user_id, pid)
        total = int(_one(cur, _STUDENT_COUNT, params).get("jumlah_program") or 0)
        group_total = total
        rows = _page(cur, _STUDENT_LIST, params)
        data = {"jumlah_program": total, "per_program": rows}
        definition = "Hanya enrollment terakhir yang boleh diakses; rata-rata nilai aritmetika (bukan nilai akhir berbobot). Absensi tercatat di sesi selesai sejak enrollment."
    else:
        raise PermissionError("Fungsi analitik tidak dikenal.")

    returned = len(rows) if name not in {"admin_attendance_summary", "tutor_attendance_statistics"} else 1
    if name == "admin_receivables_summary" and validated["kelompok"] == "total":
        returned = 1
    return {
        "data": _safe(data), "definisi": definition,
        "filter_digunakan": {k: v for k, v in validated.items()},
        "periode": {k: v for k, v in period.items() if v is not None},
        "timezone": TZ, "sumber": "PostgreSQL SIBIMA (agregasi read-only)",
        "rencana": meta, "total_hasil": total,
        "total_kelompok": group_total, "jumlah_ditampilkan": returned,
        "terpotong": group_total > returned,
        "catatan": "Angka agregat dihitung atas seluruh baris yang memenuhi syarat, bukan 20 baris daftar."
    }
