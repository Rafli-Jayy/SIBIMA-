"""Ringkasan dashboard Siswa SIBIMA, SELECT saja dan terbatas ke student_id login.

Tidak mengubah status enrollment, invoice, sesi, atau nilai.
"""
from psycopg.rows import dict_row

from app.db import pool


_SQL_RINGKAS = """
SELECT
    (SELECT COUNT(*)::int
     FROM enrollments e
     WHERE e.student_id = %s AND e.status = 'aktif') AS kelas_aktif,
    (SELECT COUNT(DISTINCT a.session_id)::int
     FROM attendances a
     JOIN enrollments e ON e.id = a.enrollment_id
     JOIN class_sessions cs ON cs.id = a.session_id
     JOIN schedules sc ON sc.id = cs.schedule_id
     WHERE e.student_id = %s AND a.student_id = e.student_id
       AND e.status = 'aktif'
       AND sc.program_id = e.program_id
       AND cs.tanggal >= e.created_at::date
       AND cs.status::text = 'selesai' AND a.status::text = 'H') AS pertemuan_hadir,
    (SELECT ROUND(AVG(g.nilai), 2)
     FROM grades g JOIN enrollments e ON e.id = g.enrollment_id
     WHERE e.student_id = %s AND e.status = 'aktif') AS rata_nilai_tercatat,
    (SELECT COUNT(*)::int
     FROM invoices i JOIN enrollments e ON e.id = i.enrollment_id
     WHERE e.student_id = %s AND i.status = 'belum_dibayar'
       AND e.status IN ('aktif', 'menunggu_pembayaran', 'menunggu')) AS tagihan_belum_lunas,
    (SELECT COALESCE(SUM(i.jumlah), 0)
     FROM invoices i JOIN enrollments e ON e.id = i.enrollment_id
     WHERE e.student_id = %s AND i.status = 'belum_dibayar'
       AND e.status IN ('aktif', 'menunggu_pembayaran', 'menunggu')) AS jumlah_tagihan,
    (SELECT COUNT(*)::int
     FROM invoices i JOIN enrollments e ON e.id = i.enrollment_id
     WHERE e.student_id = %s AND i.status = 'belum_dibayar'
       AND e.status = 'aktif' AND i.jatuh_tempo < CURRENT_DATE) AS tagihan_terlambat
"""

_SQL_JADWAL = """
SELECT s.id AS schedule_id, s.hari::text AS hari,
       s.jam_mulai, s.jam_selesai,
       p.nama AS nama_program, r.nama AS nama_ruang,
       tu.nama_lengkap AS nama_tutor,
       (s.hari::text = CASE EXTRACT(ISODOW FROM
           (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Jakarta'))::int
           WHEN 1 THEN 'senin' WHEN 2 THEN 'selasa'
           WHEN 3 THEN 'rabu' WHEN 4 THEN 'kamis'
           WHEN 5 THEN 'jumat' WHEN 6 THEN 'sabtu'
           ELSE 'minggu' END) AS hari_ini
FROM schedules s
JOIN programs p ON p.id = s.program_id
JOIN rooms r ON r.id = s.room_id
JOIN tutors t ON t.user_id = s.tutor_id
JOIN users tu ON tu.id = t.user_id AND tu.status = 'aktif'
WHERE s.aktif = TRUE
  AND EXISTS (
      SELECT 1 FROM enrollments e
      WHERE e.student_id = %s AND e.program_id = s.program_id
        AND e.status = 'aktif'
  )
ORDER BY CASE s.hari::text
    WHEN 'senin' THEN 1 WHEN 'selasa' THEN 2 WHEN 'rabu' THEN 3
    WHEN 'kamis' THEN 4 WHEN 'jumat' THEN 5 WHEN 'sabtu' THEN 6 ELSE 7 END,
    s.jam_mulai, p.nama, s.id
"""


def _valid_siswa(student_id):
    if type(student_id) is not int or student_id <= 0:
        raise ValueError('ID siswa tidak valid.')


def ringkasan_siswa(student_id: int) -> dict:
    """Statistik tanpa menganggap nilai NULL sebagai nol."""
    _valid_siswa(student_id)
    with pool.connection(timeout=5) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_SQL_RINGKAS, (student_id,) * 6)
            return cur.fetchone() or {}


def jadwal_mingguan_siswa(student_id: int) -> list[dict]:
    """Semua jadwal rutin aktif milik program yang enrollment-nya aktif."""
    _valid_siswa(student_id)
    with pool.connection(timeout=5) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_SQL_JADWAL, (student_id,))
            return list(cur.fetchall())
