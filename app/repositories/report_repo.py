"""Query read-only untuk laporan admin SIBIMA."""

from psycopg.rows import dict_row

from app.db import pool


def _limit_valid(limit: int, batas: int = 5000) -> int:
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas data harus berupa bilangan bulat positif.")
    return min(limit, batas)


def pemasukan_bulanan(limit: int = 24) -> list[dict]:
    """Pemasukan berdasarkan waktu admin mengonfirmasi pembayaran lunas."""
    limit = _limit_valid(limit, 120)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT bulan, jumlah_transaksi, total_pemasukan
                FROM v_pemasukan_bulanan
                WHERE bulan IS NOT NULL
                ORDER BY bulan DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()


def siswa_per_program() -> list[dict]:
    """Ringkasan siswa aktif, antrean pendaftaran, dan sisa kuota per program."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT p.id AS program_id, p.kode AS kode_program,
                       p.nama AS nama_program, p.jenjang, p.status AS status_program,
                       p.kuota,
                       COUNT(DISTINCT e.student_id)
                           FILTER (WHERE e.status = 'aktif') AS siswa_aktif,
                       COUNT(DISTINCT e.student_id)
                           FILTER (WHERE e.status = 'menunggu') AS menunggu,
                       GREATEST(
                           p.kuota - COUNT(DISTINCT e.student_id)
                               FILTER (WHERE e.status IN ('aktif', 'menunggu')),
                           0
                       ) AS kuota_tersisa
                FROM programs AS p
                LEFT JOIN enrollments AS e ON e.program_id = p.id
                GROUP BY p.id
                ORDER BY p.jenjang, p.nama;
                """
            )
            return cur.fetchall()


def rekap_kehadiran(limit: int = 5000) -> list[dict]:
    """Rekap absensi per siswa dan program berdasarkan view v_rekap_kehadiran."""
    limit = _limit_valid(limit)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT p.kode AS kode_program, p.nama AS nama_program,
                       st.nis, u.nama_lengkap AS nama_siswa,
                       r.total_pertemuan, r.hadir, r.izin, r.sakit, r.alpa,
                       r.persen_hadir
                FROM v_rekap_kehadiran AS r
                JOIN programs AS p ON p.id = r.program_id
                JOIN students AS st ON st.user_id = r.student_id
                JOIN users AS u ON u.id = st.user_id
                ORDER BY p.nama, u.nama_lengkap
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()


def rata_nilai_per_program() -> list[dict]:
    """Rata-rata nilai akhir berbobot per program; enrollment batal/ditolak dikecualikan."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT p.kode AS kode_program, p.nama AS nama_program, p.jenjang,
                       COUNT(DISTINCT e.student_id)
                           FILTER (WHERE v.nilai_akhir IS NOT NULL) AS siswa_dinilai,
                       ROUND(AVG(v.nilai_akhir), 2) AS rata_nilai_akhir
                FROM programs AS p
                LEFT JOIN enrollments AS e
                  ON e.program_id = p.id AND e.status IN ('aktif', 'selesai')
                LEFT JOIN v_nilai_akhir AS v ON v.enrollment_id = e.id
                GROUP BY p.id
                ORDER BY p.jenjang, p.nama;
                """
            )
            return cur.fetchall()
