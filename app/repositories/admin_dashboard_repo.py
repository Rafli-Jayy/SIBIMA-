"""Ringkasan operasional Admin. SELECT only, tanpa efek samping."""

from psycopg.rows import dict_row
from app.db import pool


_SQL_RINGKASAN = """
SELECT
    (SELECT COUNT(*) FROM users WHERE role = 'siswa' AND status = 'aktif') AS siswa_aktif,
    (SELECT COUNT(*) FROM users WHERE role = 'tutor' AND status = 'aktif') AS tutor_aktif,
    (SELECT COUNT(*) FROM programs WHERE status = 'buka') AS program_buka,
    (SELECT COUNT(*) FROM enrollments WHERE status = 'aktif') AS enrollment_aktif,
    (SELECT COUNT(*) FROM users WHERE role IN ('siswa', 'tutor')
        AND status = 'menunggu_konfirmasi') AS konfirmasi_akun,
    (SELECT COUNT(*) FROM enrollments WHERE status = 'menunggu') AS konfirmasi_pendaftaran,
    (SELECT COUNT(*) FROM invoices WHERE status = 'belum_dibayar') AS tagihan_belum_lunas,
    (SELECT COUNT(*) FROM invoices WHERE status = 'belum_dibayar'
        AND jatuh_tempo < (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Jakarta')::date) AS tagihan_terlambat,
    (SELECT COUNT(*) FROM schedules WHERE aktif = TRUE) AS jadwal_aktif,
    (SELECT COUNT(*) FROM class_sessions WHERE status::text = 'perlu_laporan') AS sesi_perlu_laporan
"""

_SQL_JADWAL_HARI_INI = """
SELECT p.nama AS program, u.nama_lengkap AS tutor, r.nama AS ruang,
       s.jam_mulai, s.jam_selesai
FROM schedules s
JOIN programs p ON p.id = s.program_id
JOIN users u ON u.id = s.tutor_id
JOIN rooms r ON r.id = s.room_id
WHERE s.aktif = TRUE
  AND s.hari::text = CASE EXTRACT(ISODOW FROM
        (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Jakarta'))::int
        WHEN 1 THEN 'senin'
        WHEN 2 THEN 'selasa'
        WHEN 3 THEN 'rabu'
        WHEN 4 THEN 'kamis'
        WHEN 5 THEN 'jumat'
        WHEN 6 THEN 'sabtu'
        ELSE 'minggu' END
ORDER BY s.jam_mulai, p.nama, s.id
LIMIT 5
"""


def ringkasan_admin() -> dict:
    """Jumlah real dari data transaksi, tidak mengubah status apa pun."""
    with pool.connection(timeout=5) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_SQL_RINGKASAN)
            return cur.fetchone() or {}


def jadwal_hari_ini_admin() -> list[dict]:
    """Jadwal rutin aktif pada hari lokal Asia/Jakarta; bukan sesi terlaksana."""
    with pool.connection(timeout=5) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_SQL_JADWAL_HARI_INI)
            return list(cur.fetchall())
