"""PATCH-005E3-C1: pemeriksaan absensi dan enrollment, baca-saja.

Jalankan dari folder utama SIBIMA:
    python tools/audit_attendance_005e3c1.py --check

Tidak mengubah database, tidak menampilkan identitas siswa, dan tidak
menghubungkan absensi lama ke enrollment secara otomatis.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_COLUMNS = {
    'attendances': {'session_id', 'student_id', 'status'},
    'class_sessions': {'id', 'schedule_id', 'tanggal', 'status'},
    'schedules': {'id', 'program_id'},
    'enrollments': {'id', 'student_id', 'program_id', 'created_at', 'status'},
}

QUERY_COUNTS = """
WITH rekaman AS (
    SELECT a.session_id, a.student_id, cs.status::text AS status_sesi,
           COALESCE(c.jumlah_semua, 0) AS jumlah_semua,
           COALESCE(c.jumlah_sebelum_sesi, 0) AS jumlah_sebelum_sesi
    FROM attendances a
    JOIN class_sessions cs ON cs.id = a.session_id
    JOIN schedules s ON s.id = cs.schedule_id
    LEFT JOIN LATERAL (
        SELECT COUNT(*) AS jumlah_semua,
               COUNT(*) FILTER (WHERE e.created_at::date <= cs.tanggal)
                   AS jumlah_sebelum_sesi
        FROM enrollments e
        WHERE e.student_id = a.student_id AND e.program_id = s.program_id
    ) c ON TRUE
)
SELECT COUNT(*)::int AS total_absensi,
       COUNT(*) FILTER (WHERE jumlah_semua = 0)::int AS tanpa_enrollment_program,
       COUNT(*) FILTER (WHERE jumlah_semua > 0 AND jumlah_sebelum_sesi = 0)::int
           AS sebelum_pendaftaran_tercatat,
       COUNT(*) FILTER (WHERE jumlah_semua = 1 AND jumlah_sebelum_sesi = 1)::int
           AS calon_tunggal_tanggal,
       COUNT(*) FILTER (WHERE jumlah_semua > 1 AND jumlah_sebelum_sesi > 0)::int
           AS riwayat_enrollment_berganda,
       COUNT(*) FILTER (WHERE status_sesi = 'batal')::int AS absensi_sesi_batal,
       COUNT(*) FILTER (WHERE status_sesi = 'perlu_laporan')::int AS absensi_sesi_perlu_laporan
FROM rekaman
"""

QUERY_MULTIPLE_ENROLLMENTS = """
SELECT COUNT(*)::int AS pasangan_berganda
FROM (
    SELECT student_id, program_id
    FROM enrollments
    GROUP BY student_id, program_id
    HAVING COUNT(*) > 1
) pasangan
"""

QUERY_SESSION_STATUSES = """
SELECT status::text AS status, COUNT(*)::int AS jumlah
FROM class_sessions
GROUP BY status::text
ORDER BY status::text
"""

QUERY_BOUND_COLUMN = """
SELECT COUNT(*) FILTER (WHERE enrollment_id IS NULL)::int AS belum_terhubung,
       COUNT(*) FILTER (WHERE enrollment_id IS NOT NULL)::int AS sudah_terhubung
FROM attendances
"""


def make_report(cursor):
    """Return only aggregate counts; cursor must be inside READ ONLY transaction."""
    cursor.execute("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name IN ('attendances', 'class_sessions', 'schedules', 'enrollments')
    """)
    found = {}
    for row in cursor.fetchall():
        found.setdefault(row['table_name'], set()).add(row['column_name'])
    missing = {table: sorted(columns - found.get(table, set()))
               for table, columns in REQUIRED_COLUMNS.items()
               if columns - found.get(table, set())}
    if missing:
        raise ValueError('Skema tabel berbeda dari SIBIMA yang diaudit: ' + str(missing))

    cursor.execute(QUERY_COUNTS)
    counts = dict(cursor.fetchone())
    cursor.execute(QUERY_MULTIPLE_ENROLLMENTS)
    duplicate_pairs = int(cursor.fetchone()['pasangan_berganda'])
    cursor.execute(QUERY_SESSION_STATUSES)
    statuses = {row['status']: int(row['jumlah']) for row in cursor.fetchall()}
    bound = None
    if 'enrollment_id' in found['attendances']:
        cursor.execute(QUERY_BOUND_COLUMN)
        bound = dict(cursor.fetchone())
    return {'counts': counts, 'duplicate_pairs': duplicate_pairs,
            'statuses': statuses, 'bound': bound}


def format_report(db_name, report):
    c = report['counts']
    lines = [
        '=== SIBIMA PATCH-005E3-C1 | AUDIT READ-ONLY ===',
        f'Database: {db_name}',
        f"Total catatan absensi: {c['total_absensi']}",
        f"Pasangan siswa-program dengan lebih dari 1 enrollment: {report['duplicate_pairs']}",
        '',
        'Klasifikasi sementara (BUKAN pemetaan otomatis):',
        f"- Calon tunggal berdasar program dan tanggal: {c['calon_tunggal_tanggal']}",
        f"- Riwayat enrollment berganda, perlu tinjauan: {c['riwayat_enrollment_berganda']}",
        f"- Tidak ada enrollment pada program: {c['tanpa_enrollment_program']}",
        f"- Tanggal sesi sebelum tanggal enrollment: {c['sebelum_pendaftaran_tercatat']}",
        f"- Absensi pada sesi batal (indikator silang): {c['absensi_sesi_batal']}",
        f"- Absensi pada sesi perlu_laporan (indikator silang): {c['absensi_sesi_perlu_laporan']}",
        '',
        'Jumlah sesi menurut status:',
    ]
    for name, total in sorted(report['statuses'].items()):
        lines.append(f'- {name}: {total}')
    if report['bound'] is None:
        lines.append('Kolom attendances.enrollment_id: BELUM ADA (sesuai pra-migrasi)')
    else:
        lines.append('Kolom attendances.enrollment_id: SUDAH ADA')
        lines.append(f"- Belum ditautkan: {report['bound']['belum_terhubung']}")
        lines.append(f"- Sudah ditautkan: {report['bound']['sudah_terhubung']}")
    lines.extend([
        '',
        'PENTING: Calon tunggal bukan bukti final kepemilikan enrollment.',
        'Riwayat pembatalan dan daftar ulang dapat membuat tanggal saja tidak cukup.',
        'Tidak ada data yang diubah. Tidak ada ID atau nama siswa yang ditampilkan.',
    ])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Audit absensi SIBIMA read-only, tanpa perubahan database.')
    parser.add_argument('--check', action='store_true', required=True,
                        help='Jalankan pemeriksaan agregat saja; tidak mengubah data.')
    parser.parse_args(argv)
    try:
        import psycopg
        from psycopg.rows import dict_row
        from app.config import DB_CONFIG
    except ImportError:
        print('Dependensi belum tersedia. Aktifkan venv dan instal requirements.txt.')
        return 1
    expected = DB_CONFIG.get('dbname')
    if not expected:
        print('DB_NAME pada .env belum lengkap.')
        return 1
    try:
        with psycopg.connect(**DB_CONFIG, autocommit=True, connect_timeout=10) as conn:
            with conn.transaction():
                with conn.cursor(row_factory=dict_row) as cursor:
                    # Ditentukan pada awal transaksi agar query setelahnya tidak dapat menulis.
                    cursor.execute('SET TRANSACTION READ ONLY')
                    cursor.execute("SET LOCAL statement_timeout = '30000ms'")
                    cursor.execute("SET LOCAL TIME ZONE 'Asia/Jakarta'")
                    cursor.execute('SELECT current_database() AS nama')
                    actual = cursor.fetchone()['nama']
                    if actual != expected:
                        print('Database terkoneksi berbeda dari DB_NAME. Pemeriksaan dihentikan.')
                        return 1
                    report = make_report(cursor)
                    print(format_report(actual, report))
        return 0
    except (ValueError, Exception) as exc:
        # Hindari mencetak exception koneksi yang mungkin memuat host atau akun.
        if isinstance(exc, ValueError):
            print(f'Audit dihentikan: {exc}')
        else:
            print(f'Audit gagal ({type(exc).__name__}). Periksa hak SELECT, koneksi, dan skema.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
