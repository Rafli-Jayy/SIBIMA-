"""Fixed, parameterized, read-only queries for SIBIMA-AI (Patch 3).

Never accept SQL, user_id, or arbitrary columns from the model. This module
uses the application's existing connection pool; it does not modify schema.
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from app.repositories.class_access_sql import AKSES_TERKUNCI_SQL, ENROLLMENT_TERAKHIR_TERSEDIA_SQL

MAX_ROWS = 20
AUTHORIZED = {
    "admin": {"get_admin_overview", "list_unpaid_invoices"},
    "tutor": {"get_my_teaching_schedule", "list_my_class_students", "get_my_class_attendance"},
    "siswa": {"get_my_schedule", "get_my_grades", "get_my_attendance", "get_my_invoices", "get_my_payments", "get_my_enrollments"},
}

# Each query is static. %s are psycopg placeholders, never concatenated model text.
QUERIES = {
    "get_admin_overview": """
        SELECT (SELECT COUNT(*) FROM users WHERE role='siswa' AND status='aktif')::int AS siswa_aktif,
               (SELECT COUNT(*) FROM users WHERE role='tutor' AND status='aktif')::int AS tutor_aktif,
               (SELECT COUNT(*) FROM programs WHERE status='buka')::int AS program_buka,
               (SELECT COUNT(*) FROM enrollments WHERE status='aktif')::int AS pendaftaran_aktif,
               (SELECT COUNT(*) FROM invoices WHERE status='belum_dibayar')::int AS tagihan_belum_lunas
    """,
    "list_unpaid_invoices": """
        SELECT i.no_invoice, i.periode, i.jumlah, i.jatuh_tempo,
               p.nama AS program, u.nama_lengkap AS siswa
        FROM invoices i JOIN enrollments e ON e.id=i.enrollment_id
        JOIN programs p ON p.id=e.program_id JOIN users u ON u.id=e.student_id
        WHERE i.status='belum_dibayar'
          AND (%s::boolean=FALSE OR i.jatuh_tempo < CURRENT_DATE)
        ORDER BY i.jatuh_tempo, i.id LIMIT 20
    """,
    "get_my_teaching_schedule": """
        SELECT p.nama AS program, s.hari::text AS hari, s.jam_mulai, s.jam_selesai,
               r.nama AS ruang FROM schedules s
        JOIN programs p ON p.id=s.program_id JOIN rooms r ON r.id=s.room_id
        WHERE s.tutor_id=%s AND s.aktif=TRUE
        ORDER BY s.hari, s.jam_mulai LIMIT 20
    """,
    "list_my_class_students": """
        SELECT p.nama AS program, u.nama_lengkap AS siswa, e.status::text AS status
        FROM enrollments e JOIN programs p ON p.id=e.program_id
        JOIN users u ON u.id=e.student_id AND u.status='aktif'
        WHERE e.status='aktif' AND (%s::int IS NULL OR e.program_id=%s::int)
        AND EXISTS (SELECT 1 FROM schedules s WHERE s.program_id=e.program_id
                    AND s.tutor_id=%s AND s.aktif=TRUE)
        ORDER BY p.nama, u.nama_lengkap LIMIT 20
    """,
    "get_my_class_attendance": """
        SELECT p.nama AS program, u.nama_lengkap AS siswa,
               COUNT(a.session_id)::int AS tercatat,
               COUNT(*) FILTER (WHERE a.status='H')::int AS hadir,
               COUNT(*) FILTER (WHERE a.status='I')::int AS izin,
               COUNT(*) FILTER (WHERE a.status='S')::int AS sakit,
               COUNT(*) FILTER (WHERE a.status='A')::int AS alpa
        FROM attendances a JOIN class_sessions cs ON cs.id=a.session_id AND cs.status='selesai'
        JOIN schedules s ON s.id=cs.schedule_id AND s.tutor_id=%s AND s.aktif=TRUE
        JOIN enrollments e ON e.id=a.enrollment_id AND e.student_id=a.student_id
             AND e.program_id=s.program_id AND e.status='aktif'
        JOIN users u ON u.id=e.student_id AND u.status='aktif'
        JOIN programs p ON p.id=e.program_id
        WHERE (%s::int IS NULL OR e.program_id=%s::int)
        GROUP BY p.nama, u.nama_lengkap ORDER BY p.nama,u.nama_lengkap LIMIT 20
    """,
    "get_my_schedule": f"""
        SELECT p.nama AS program, s.hari::text AS hari, s.jam_mulai, s.jam_selesai,
               r.nama AS ruang, tu.nama_lengkap AS tutor
        FROM enrollments e JOIN schedules s ON s.program_id=e.program_id AND s.aktif=TRUE
        JOIN programs p ON p.id=e.program_id JOIN rooms r ON r.id=s.room_id
        JOIN users tu ON tu.id=s.tutor_id
        WHERE e.student_id=%s AND e.status='aktif'
          AND {ENROLLMENT_TERAKHIR_TERSEDIA_SQL} AND NOT {AKSES_TERKUNCI_SQL}
        ORDER BY s.hari, s.jam_mulai LIMIT 20
    """,
    "get_my_grades": f"""
        SELECT p.nama AS program, g.jenis::text AS jenis, g.judul, g.nilai, g.tanggal
        FROM grades g JOIN enrollments e ON e.id=g.enrollment_id
        JOIN programs p ON p.id=e.program_id
        WHERE e.student_id=%s AND {ENROLLMENT_TERAKHIR_TERSEDIA_SQL}
          AND NOT {AKSES_TERKUNCI_SQL}
          AND (%s::int IS NULL OR e.program_id=%s::int)
        ORDER BY g.tanggal DESC,g.id DESC LIMIT 20
    """,
    "get_my_attendance": f"""
        SELECT p.nama AS program, cs.tanggal, cs.pertemuan_ke,
               a.status::text AS kehadiran, cs.status::text AS status_pertemuan
        FROM attendances a JOIN enrollments e ON e.id=a.enrollment_id AND e.student_id=a.student_id
        JOIN class_sessions cs ON cs.id=a.session_id AND cs.status<>'batal'
        JOIN schedules s ON s.id=cs.schedule_id AND s.program_id=e.program_id
        JOIN programs p ON p.id=e.program_id
        WHERE e.student_id=%s AND {ENROLLMENT_TERAKHIR_TERSEDIA_SQL}
          AND NOT {AKSES_TERKUNCI_SQL} AND cs.tanggal>=e.created_at::date
          AND (%s::int IS NULL OR e.program_id=%s::int)
        ORDER BY cs.tanggal DESC,cs.id DESC LIMIT 20
    """,
    "get_my_enrollments": """
        SELECT p.nama AS program, e.status::text AS status_pendaftaran,
               e.created_at AS tanggal_pendaftaran, e.processed_at AS tanggal_pemrosesan,
               (SELECT i.status::text FROM invoices i WHERE i.enrollment_id=e.id
                ORDER BY i.id DESC LIMIT 1) AS status_tagihan_terakhir,
               (SELECT pay.status::text FROM payments pay
                JOIN invoices i ON i.id=pay.invoice_id WHERE i.enrollment_id=e.id
                ORDER BY pay.created_at DESC,pay.id DESC LIMIT 1) AS status_pembayaran_terakhir
        FROM enrollments e JOIN programs p ON p.id=e.program_id
        WHERE e.student_id=%s ORDER BY e.created_at DESC,e.id DESC LIMIT 20
    """,
    "get_my_invoices": """
        SELECT p.nama AS program, i.no_invoice, i.periode, i.jumlah,
               i.jatuh_tempo, i.status::text AS status,
               e.status::text AS status_pendaftaran
        FROM invoices i JOIN enrollments e ON e.id=i.enrollment_id
        JOIN programs p ON p.id=e.program_id
        WHERE e.student_id=%s ORDER BY i.jatuh_tempo DESC,i.id DESC LIMIT 20
    """,
    "get_my_payments": """
        SELECT p.nama AS program, pay.kode_bayar, pay.jumlah,
               pay.status::text AS status, pay.paid_at,
               e.status::text AS status_pendaftaran
        FROM payments pay JOIN invoices i ON i.id=pay.invoice_id
        JOIN enrollments e ON e.id=i.enrollment_id
        JOIN programs p ON p.id=e.program_id
        WHERE e.student_id=%s ORDER BY pay.created_at DESC,pay.id DESC LIMIT 20
    """,
}



# Patch 4F.1: separate, explicitly approved read-only capabilities.
# Keep the 11 legacy QUERIES unchanged; no schema migrations or arbitrary SQL.
EXTRA_AUTHORIZED = {
    "admin": {"get_my_identity", "admin_find_users", "admin_get_user_summary", "admin_list_students_by_tutor"},
    "tutor": {"get_my_identity"},
    "siswa": {"get_my_identity"},
}
EXTRA_QUERIES = {
    "get_my_identity": """
        SELECT id AS user_id, username, nama_lengkap,
               role::text AS role, status::text AS status
        FROM users WHERE id=%s LIMIT 1
    """,
    "admin_find_users": """
        SELECT u.id AS user_id, u.username, u.nama_lengkap,
               u.role::text AS role, u.status::text AS status,
               (SELECT COUNT(*) FROM schedules s
                WHERE s.tutor_id=u.id AND s.aktif=TRUE)::int AS jadwal_mengajar_aktif,
               (SELECT COUNT(DISTINCT s.program_id) FROM schedules s
                WHERE s.tutor_id=u.id AND s.aktif=TRUE)::int AS program_diajar_aktif,
               (SELECT COUNT(*) FROM enrollments e
                WHERE e.student_id=u.id AND e.status='aktif')::int AS pendaftaran_aktif
        FROM users u
        WHERE strpos(lower(u.nama_lengkap), lower(%s)) > 0
           OR strpos(lower(u.username), lower(%s)) > 0
        ORDER BY CASE WHEN lower(u.nama_lengkap)=lower(%s)
                       OR lower(u.username)=lower(%s) THEN 0 ELSE 1 END,
                 u.nama_lengkap, u.id
        LIMIT 10
    """,
    "admin_get_user_summary": """
        SELECT u.id AS user_id, u.username, u.nama_lengkap,
               u.role::text AS role, u.status::text AS status,
               u.created_at AS terdaftar_pada,
               (SELECT COUNT(*) FROM schedules s
                WHERE s.tutor_id=u.id AND s.aktif=TRUE)::int AS jadwal_mengajar_aktif,
               (SELECT COUNT(DISTINCT s.program_id) FROM schedules s
                WHERE s.tutor_id=u.id AND s.aktif=TRUE)::int AS program_diajar_aktif,
               (SELECT COUNT(*) FROM enrollments e
                WHERE e.student_id=u.id AND e.status='aktif')::int AS pendaftaran_aktif
        FROM users u WHERE u.id=%s LIMIT 1
    """,
}
# A student's active enrollment in a program taught by the tutor is NOT
# evidence that this tutor taught every session or that the student attended.
ADMIN_TUTOR_STUDENTS = """
    SELECT DISTINCT p.nama AS program, u.nama_lengkap AS siswa,
           e.status::text AS status_pendaftaran
    FROM enrollments e
    JOIN users u ON u.id=e.student_id AND u.role='siswa' AND u.status='aktif'
    JOIN programs p ON p.id=e.program_id
    WHERE e.status='aktif'
      AND EXISTS (SELECT 1 FROM schedules s
                  WHERE s.program_id=e.program_id
                    AND s.tutor_id=%s AND s.aktif=TRUE)
    ORDER BY p.nama, u.nama_lengkap LIMIT 20
"""
ADMIN_TUTOR_STUDENT_COUNT = """
    SELECT COUNT(DISTINCT e.student_id)::int AS jumlah_siswa_unik,
           COUNT(*)::int AS jumlah_pendaftaran_program
    FROM enrollments e
    JOIN users u ON u.id=e.student_id AND u.role='siswa' AND u.status='aktif'
    WHERE e.status='aktif'
      AND EXISTS (SELECT 1 FROM schedules s
                  WHERE s.program_id=e.program_id
                    AND s.tutor_id=%s AND s.aktif=TRUE)
"""
ADMIN_TUTOR_SCHEDULE = """
    SELECT p.nama AS program, s.hari::text AS hari, s.jam_mulai, s.jam_selesai,
           r.nama AS ruang
    FROM schedules s JOIN programs p ON p.id=s.program_id
    JOIN rooms r ON r.id=s.room_id
    WHERE s.tutor_id=%s AND s.aktif=TRUE
    ORDER BY p.nama, s.hari, s.jam_mulai LIMIT 20
"""
ADMIN_STUDENT_ENROLLMENTS = """
    SELECT p.nama AS program, e.status::text AS status_pendaftaran,
           e.created_at AS tanggal_pendaftaran
    FROM enrollments e JOIN programs p ON p.id=e.program_id
    WHERE e.student_id=%s ORDER BY e.created_at DESC,e.id DESC LIMIT 20
"""

def _safe(value):
    if isinstance(value, (date, datetime, time, Decimal)):
        return str(value)
    if isinstance(value, dict):
        return {k: _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return value


class AIReadRepository:
    """Enforces ACTIVE role from DB within a read-only transaction on every call."""

    def __init__(self, pool=None):
        self._pool = pool

    def execute(self, user_id: int, role: str, name: str, args: dict) -> dict:
        if name not in (set(QUERIES) | set(EXTRA_QUERIES) | {"admin_list_students_by_tutor"}) or name not in (AUTHORIZED.get(role, set()) | EXTRA_AUTHORIZED.get(role, set())):
            raise PermissionError("Fungsi tidak diizinkan.")
        if type(user_id) is not int or user_id <= 0:
            raise PermissionError("Sesi tidak valid.")
        if self._pool is None:
            # Lazy import: offline UI tests and chat demo never connect to PostgreSQL.
            from app.db import pool
            self._pool = pool
        from psycopg.rows import dict_row
        with self._pool.connection(timeout=5) as conn:
            with conn.transaction():
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("SET TRANSACTION READ ONLY")
                    cur.execute("SET LOCAL statement_timeout = '5000ms'")
                    cur.execute("SELECT role::text AS role, status::text AS status FROM users WHERE id=%s", (user_id,))
                    current = cur.fetchone()
                    if not current or current["role"] != role or current["status"] != "aktif":
                        raise PermissionError("Sesi pengguna tidak lagi aktif atau berubah.")
                    if name == "get_admin_overview":
                        params = ()
                    elif name == "get_my_identity":
                        params = (user_id,)
                    elif name == "admin_find_users":
                        query = args["query"]
                        params = (query, query, query, query)
                    elif name == "admin_get_user_summary":
                        params = (args["user_id"],)
                    elif name == "admin_list_students_by_tutor":
                        params = (args["tutor_user_id"],)
                    elif name == "list_unpaid_invoices":
                        params = (args.get("overdue_only", False),)
                    elif name in {"get_my_teaching_schedule", "get_my_schedule", "get_my_invoices", "get_my_payments", "get_my_enrollments"}:
                        params = (user_id,)
                    elif name == "list_my_class_students":
                        p = args.get("program_id")
                        params = (p, p, user_id)
                    elif name == "get_my_class_attendance":
                        p = args.get("program_id")
                        params = (user_id, p, p)
                    else:
                        p = args.get("program_id")
                        params = (user_id, p, p)
                    if name == "admin_list_students_by_tutor":
                        # Revalidate the target role from PostgreSQL, not only
                        # the model's arguments or cached discovery results.
                        cur.execute("SELECT role::text AS role FROM users WHERE id=%s",
                                    (args["tutor_user_id"],))
                        target = cur.fetchone()
                        if not target or target["role"] != "tutor":
                            raise PermissionError("Akun yang dipilih bukan Tutor.")
                        cur.execute(ADMIN_TUTOR_STUDENT_COUNT, params)
                        totals = cur.fetchone() or {}
                        cur.execute(ADMIN_TUTOR_STUDENTS, params)
                        rows = cur.fetchmany(MAX_ROWS)
                        return {
                            "data": _safe(rows),
                            "jumlah_ditampilkan": len(rows),
                            "maksimum_baris": MAX_ROWS,
                            "jumlah_siswa_unik": int(totals.get("jumlah_siswa_unik") or 0),
                            "jumlah_pendaftaran_program": int(totals.get("jumlah_pendaftaran_program") or 0),
                            "basis": "Enrollment aktif pada program dengan jadwal aktif Tutor. "
                                     "Bukan bukti siswa hadir atau diajar langsung pada sesi tertentu.",
                            "catatan": "Daftar maksimal 20 baris; jumlah agregat dihitung untuk semua data yang memenuhi syarat.",
                        }
                    cur.execute((QUERIES | EXTRA_QUERIES)[name], params)
                    rows = cur.fetchmany(MAX_ROWS)
                    result = {"data": _safe(rows), "jumlah_ditampilkan": len(rows),
                              "maksimum_baris": (10 if name == "admin_find_users" else MAX_ROWS),
                              "catatan": "Hasil pencarian dibatasi; beberapa nama mungkin cocok."
                                         if name == "admin_find_users" else
                                         "Hasil dibatasi. Tidak ada hasil bukan berarti seluruh data tidak ada."}
                    if name == "admin_get_user_summary" and rows:
                        target = rows[0]
                        # Only fetch context appropriate to the matched user's role.
                        if target["role"] == "tutor":
                            cur.execute(ADMIN_TUTOR_SCHEDULE, (args["user_id"],))
                            result["detail_program"] = _safe(cur.fetchmany(MAX_ROWS))
                        elif target["role"] == "siswa":
                            cur.execute(ADMIN_STUDENT_ENROLLMENTS, (args["user_id"],))
                            result["detail_program"] = _safe(cur.fetchmany(MAX_ROWS))
                    return result
