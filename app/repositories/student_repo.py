"""Query akademik dan profil yang dibatasi pada satu akun siswa."""

from psycopg.rows import dict_row

from app.db import pool


_HARI_ORDER_SQL = """CASE sc.hari::text
    WHEN 'senin' THEN 1 WHEN 'selasa' THEN 2 WHEN 'rabu' THEN 3
    WHEN 'kamis' THEN 4 WHEN 'jumat' THEN 5 WHEN 'sabtu' THEN 6
    WHEN 'minggu' THEN 7 ELSE 8 END"""


def _valid_id(value: int, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{label} tidak valid.")
    return value


def daftar_kelas(student_id: int) -> list[dict]:
    """Daftar enrollment siswa, termasuk status dan tutor yang dijadwalkan."""
    _valid_id(student_id, "ID siswa")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT e.id AS enrollment_id, e.program_id, e.status,
                       e.created_at, e.processed_at, e.alasan_tolak,
                       p.kode, p.nama AS nama_program, p.jenjang,
                       p.harga_bulanan, p.deskripsi,
                       COALESCE((
                           SELECT string_agg(DISTINCT tu.nama_lengkap, ', ' ORDER BY tu.nama_lengkap)
                           FROM schedules sc
                           JOIN tutors t ON t.user_id = sc.tutor_id
                           JOIN users tu ON tu.id = t.user_id AND tu.status = 'aktif'
                           WHERE sc.program_id = p.id AND sc.aktif = TRUE
                       ), 'Belum ditentukan') AS tutor
                FROM enrollments e
                JOIN programs p ON p.id = e.program_id
                WHERE e.student_id = %s
                ORDER BY e.created_at DESC, e.id DESC;
                """,
                (student_id,),
            )
            return cur.fetchall()


def daftar_program_akademik(student_id: int) -> list[dict]:
    """Program yang sedang diikuti atau sudah selesai, untuk akses arsip akademik."""
    _valid_id(student_id, "ID siswa")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT e.id AS enrollment_id, e.program_id, e.status AS status_enrollment,
                       p.kode, p.nama AS nama_program, p.jenjang
                FROM enrollments e
                JOIN programs p ON p.id = e.program_id
                WHERE e.student_id = %s
                  AND (
                      e.status IN ('aktif', 'selesai')
                      OR EXISTS (SELECT 1 FROM grades g WHERE g.enrollment_id = e.id)
                      OR EXISTS (
                          SELECT 1
                          FROM attendances a
                          JOIN class_sessions cs ON cs.id = a.session_id
                          JOIN schedules sc ON sc.id = cs.schedule_id
                          WHERE a.student_id = e.student_id AND sc.program_id = e.program_id
                      )
                      OR EXISTS (
                          SELECT 1
                          FROM class_sessions cs
                          JOIN schedules sc ON sc.id = cs.schedule_id
                          WHERE sc.program_id = e.program_id
                            AND (NULLIF(BTRIM(cs.topik), '') IS NOT NULL
                                 OR NULLIF(BTRIM(cs.ringkasan), '') IS NOT NULL)
                      )
                  )
                ORDER BY CASE e.status WHEN 'aktif' THEN 0 WHEN 'selesai' THEN 1 ELSE 2 END,
                         p.nama, e.id DESC;
                """,
                (student_id,),
            )
            return cur.fetchall()


def daftar_jadwal(student_id: int, hari: str | None = None, program_id: int | None = None) -> list[dict]:
    """Jadwal aktif hanya dari program yang enrollment-nya aktif milik siswa."""
    _valid_id(student_id, "ID siswa")
    if hari is not None and hari not in {"senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"}:
        raise ValueError("Nama hari tidak valid.")
    if program_id is not None:
        _valid_id(program_id, "ID program")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT sc.id AS schedule_id, sc.hari::text AS hari,
                       sc.jam_mulai, sc.jam_selesai, sc.program_id,
                       p.kode, p.nama AS nama_program, p.jenjang,
                       r.nama AS nama_ruang, tu.nama_lengkap AS nama_tutor
                FROM schedules sc
                JOIN programs p ON p.id = sc.program_id
                JOIN rooms r ON r.id = sc.room_id
                JOIN tutors t ON t.user_id = sc.tutor_id
                JOIN users tu ON tu.id = t.user_id AND tu.status = 'aktif'
                WHERE sc.aktif = TRUE
                  AND EXISTS (
                      SELECT 1
                      FROM enrollments e
                      WHERE e.student_id = %s
                        AND e.program_id = sc.program_id
                        AND e.status = 'aktif'
                  )
                  AND (%s::nama_hari IS NULL OR sc.hari = %s::nama_hari)
                  AND (%s::integer IS NULL OR p.id = %s::integer)
                ORDER BY {_HARI_ORDER_SQL}, sc.jam_mulai, p.nama, sc.id;
                """,
                (student_id, hari, hari, program_id, program_id),
            )
            return cur.fetchall()


def rekap_absensi(student_id: int, program_id: int | None = None) -> list[dict]:
    """Ringkasan presensi per program dari view laporan."""
    _valid_id(student_id, "ID siswa")
    if program_id is not None:
        _valid_id(program_id, "ID program")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT p.id AS program_id, p.nama AS nama_program,
                       r.total_pertemuan, r.hadir, r.izin, r.sakit, r.alpa,
                       r.persen_hadir
                FROM v_rekap_kehadiran r
                JOIN programs p ON p.id = r.program_id
                JOIN enrollments e ON e.student_id = r.student_id AND e.program_id = p.id
                WHERE r.student_id = %s
                  AND (%s::integer IS NULL OR p.id = %s::integer)
                ORDER BY p.nama;
                """,
                (student_id, program_id, program_id),
            )
            return cur.fetchall()


def daftar_absensi(student_id: int, program_id: int | None = None, limit: int = 300) -> list[dict]:
    """Riwayat presensi terperinci milik siswa yang sedang login."""
    _valid_id(student_id, "ID siswa")
    if program_id is not None:
        _valid_id(program_id, "ID program")
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas riwayat absensi tidak valid.")
    limit = min(limit, 1000)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT cs.tanggal, cs.pertemuan_ke, cs.topik,
                       p.id AS program_id, p.nama AS nama_program,
                       a.status::text AS status_absensi, a.keterangan
                FROM attendances a
                JOIN class_sessions cs ON cs.id = a.session_id
                JOIN schedules sc ON sc.id = cs.schedule_id
                JOIN programs p ON p.id = sc.program_id
                JOIN enrollments e ON e.student_id = a.student_id AND e.program_id = p.id
                WHERE a.student_id = %s
                  AND (%s::integer IS NULL OR p.id = %s::integer)
                ORDER BY cs.tanggal DESC, cs.pertemuan_ke DESC
                LIMIT %s;
                """,
                (student_id, program_id, program_id, limit),
            )
            return cur.fetchall()


def ringkasan_nilai(student_id: int, program_id: int | None = None) -> list[dict]:
    """Nilai komponen dan nilai akhir berbobot dari view v_nilai_akhir."""
    _valid_id(student_id, "ID siswa")
    if program_id is not None:
        _valid_id(program_id, "ID program")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT e.id AS enrollment_id, p.id AS program_id,
                       p.kode, p.nama AS nama_program, p.jenjang,
                       p.bobot_tugas, p.bobot_kuis, p.bobot_uts, p.bobot_uas,
                       v.tugas, v.kuis, v.uts, v.uas, v.nilai_akhir,
                       e.status AS status_enrollment
                FROM enrollments e
                JOIN programs p ON p.id = e.program_id
                LEFT JOIN v_nilai_akhir v ON v.enrollment_id = e.id
                WHERE e.student_id = %s
                  AND (%s::integer IS NULL OR p.id = %s::integer)
                ORDER BY p.nama;
                """,
                (student_id, program_id, program_id),
            )
            return cur.fetchall()


def daftar_nilai(student_id: int, program_id: int, limit: int = 500) -> list[dict]:
    """Nilai komponen siswa per program; query tidak menerima student_id dari UI lain."""
    _valid_id(student_id, "ID siswa")
    _valid_id(program_id, "ID program")
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas daftar nilai tidak valid.")
    limit = min(limit, 1000)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT g.id AS grade_id, g.jenis::text AS jenis, g.judul,
                       g.nilai, g.tanggal, p.nama AS nama_program,
                       COALESCE(tu.nama_lengkap, tu.username, '-') AS nama_tutor
                FROM grades g
                JOIN enrollments e ON e.id = g.enrollment_id
                JOIN programs p ON p.id = e.program_id
                LEFT JOIN users tu ON tu.id = g.input_by
                WHERE e.student_id = %s
                  AND e.program_id = %s
                ORDER BY g.jenis, g.tanggal DESC, g.id DESC
                LIMIT %s;
                """,
                (student_id, program_id, limit),
            )
            return cur.fetchall()


def daftar_catatan_materi(student_id: int, program_id: int, limit: int = 300) -> list[dict]:
    """Catatan sesi hanya untuk program siswa sendiri yang aktif/selesai."""
    _valid_id(student_id, "ID siswa")
    _valid_id(program_id, "ID program")
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas catatan materi tidak valid.")
    limit = min(limit, 1000)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT cs.id AS session_id, cs.tanggal, cs.pertemuan_ke,
                       cs.topik, cs.ringkasan, p.nama AS nama_program,
                       COALESCE(tu.nama_lengkap, '-') AS nama_tutor
                FROM class_sessions cs
                JOIN schedules sc ON sc.id = cs.schedule_id
                JOIN programs p ON p.id = sc.program_id
                JOIN enrollments e ON e.student_id = %s AND e.program_id = p.id
                JOIN tutors t ON t.user_id = sc.tutor_id
                JOIN users tu ON tu.id = t.user_id
                WHERE p.id = %s
                  AND cs.status = 'terlaksana'
                  AND (NULLIF(BTRIM(cs.topik), '') IS NOT NULL
                       OR NULLIF(BTRIM(cs.ringkasan), '') IS NOT NULL)
                ORDER BY cs.tanggal DESC, cs.pertemuan_ke DESC
                LIMIT %s;
                """,
                (student_id, program_id, limit),
            )
            return cur.fetchall()


def profil_siswa(student_id: int) -> dict | None:
    _valid_id(student_id, "ID siswa")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT u.id, u.username, u.email, u.nama_lengkap, u.status,
                       s.nis, s.jenjang, s.sekolah, s.no_hp, s.nama_wali
                FROM users u
                JOIN students s ON s.user_id = u.id
                WHERE u.id = %s AND u.role = 'siswa';
                """,
                (student_id,),
            )
            return cur.fetchone()


def ubah_profil_siswa(student_id: int, data: dict) -> bool:
    """Mengubah field profil yang memang tersedia di menu siswa."""
    _valid_id(student_id, "ID siswa")
    allowed = {"jenjang", "sekolah", "no_hp", "nama_wali"}
    if not isinstance(data, dict) or set(data) != allowed:
        raise ValueError("Data profil tidak lengkap atau memiliki field yang tidak diizinkan.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE students
                SET jenjang = %s, sekolah = %s, no_hp = %s, nama_wali = %s
                WHERE user_id = %s
                RETURNING user_id;
                """,
                (data["jenjang"], data["sekolah"], data["no_hp"], data["nama_wali"], student_id),
            )
            if cur.fetchone() is None:
                return False
            cur.execute(
                "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, %s, %s);",
                (student_id, "PROFIL_SISWA_DIUBAH", "Siswa memperbarui informasi profil."),
            )
        conn.commit()
    return True
