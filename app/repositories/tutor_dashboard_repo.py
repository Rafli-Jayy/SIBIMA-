"""Data ringkasan Dashboard Tutor: pembacaan SELECT tanpa efek samping.

Status sesi 'Terjadwal' hanya berarti jadwal rutin, bukan bukti telah mengajar.
Tidak mengubah enrollment, absensi, tagihan, atau jadwal.
"""
from psycopg.rows import dict_row
from app.db import pool


_SQL_STAT = """
SELECT
  (SELECT COUNT(DISTINCT s.program_id)::int
     FROM schedules s WHERE s.tutor_id = %s AND s.aktif = TRUE) AS program_diampu,
  (SELECT COUNT(*)::int FROM schedules s
     WHERE s.tutor_id = %s AND s.aktif = TRUE) AS jadwal_aktif,
  (SELECT COUNT(DISTINCT e.student_id)::int
     FROM enrollments e
     JOIN users u ON u.id = e.student_id AND u.status = 'aktif'
     WHERE e.status = 'aktif' AND EXISTS (
       SELECT 1 FROM schedules s
       WHERE s.program_id = e.program_id AND s.tutor_id = %s
         AND s.aktif = TRUE)) AS siswa_aktif,
  (SELECT COUNT(*)::int FROM class_sessions cs
     JOIN schedules s ON s.id = cs.schedule_id
     WHERE s.tutor_id = %s AND cs.status::text = 'perlu_laporan') AS sesi_perlu_laporan
"""

_SQL_JADWAL = """
SELECT s.id AS schedule_id, s.hari::text AS hari,
       s.jam_mulai, s.jam_selesai,
       p.kode AS kode_program, p.nama AS nama_program,
       r.nama AS nama_ruang,
       COALESCE(roster.jumlah_siswa, 0)::int AS jumlah_siswa,
       cs.status::text AS status_sesi_hari_ini,
       (s.hari::text = CASE EXTRACT(ISODOW FROM
           (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Jakarta'))::int
           WHEN 1 THEN 'senin' WHEN 2 THEN 'selasa'
           WHEN 3 THEN 'rabu' WHEN 4 THEN 'kamis'
           WHEN 5 THEN 'jumat' WHEN 6 THEN 'sabtu'
           ELSE 'minggu' END) AS hari_ini
FROM schedules s
JOIN programs p ON p.id = s.program_id
JOIN rooms r ON r.id = s.room_id
LEFT JOIN LATERAL (
    SELECT COUNT(DISTINCT e.student_id)::int AS jumlah_siswa
    FROM enrollments e JOIN users u ON u.id = e.student_id AND u.status = 'aktif'
    WHERE e.program_id = s.program_id AND e.status = 'aktif'
) roster ON TRUE
LEFT JOIN class_sessions cs ON cs.schedule_id = s.id
    AND cs.tanggal = (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Jakarta')::date
WHERE s.tutor_id = %s AND s.aktif = TRUE
ORDER BY CASE s.hari
    WHEN 'senin' THEN 1 WHEN 'selasa' THEN 2 WHEN 'rabu' THEN 3
    WHEN 'kamis' THEN 4 WHEN 'jumat' THEN 5 WHEN 'sabtu' THEN 6 ELSE 7 END,
    s.jam_mulai, p.nama, s.id
"""


def ringkasan_tutor(tutor_id: int) -> dict:
    """Hitung hanya jadwal aktif yang memang milik Tutor yang login."""
    with pool.connection(timeout=5) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_SQL_STAT, (tutor_id, tutor_id, tutor_id, tutor_id))
            return cur.fetchone() or {}


def jadwal_mingguan_tutor(tutor_id: int) -> list[dict]:
    """Daftar jadwal rutin Tutor, beserta status sesi hari ini bila ada."""
    with pool.connection(timeout=5) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_SQL_JADWAL, (tutor_id,))
            return list(cur.fetchall())
