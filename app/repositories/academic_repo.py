"""Repository pertemuan, absensi, nilai, dan catatan materi tutor SIBIMA."""

from psycopg.rows import dict_row

from app.db import pool


def daftar_jadwal_tutor(tutor_id: int, *, aktif: bool | None = True):
    """Daftar jadwal milik tutor; aktif=None berarti semua status."""
    where = ["s.tutor_id = %s"]
    params = [tutor_id]
    if aktif is not None:
        where.append("s.aktif = %s")
        params.append(aktif)
    query = f"""
        SELECT s.id, s.program_id, p.kode AS kode_program, p.nama AS nama_program,
               p.jenjang, s.room_id, r.nama AS nama_ruang, r.kapasitas AS kapasitas_ruang,
               s.hari::text AS hari, s.jam_mulai, s.jam_selesai, s.aktif,
               COALESCE(roster.jumlah_siswa, 0)::int AS jumlah_siswa
        FROM schedules s
        JOIN programs p ON p.id = s.program_id
        JOIN rooms r ON r.id = s.room_id
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::int AS jumlah_siswa
            FROM enrollments e
            WHERE e.program_id = s.program_id AND e.status = 'aktif'
        ) roster ON TRUE
        WHERE {' AND '.join(where)}
        ORDER BY CASE s.hari WHEN 'senin' THEN 1 WHEN 'selasa' THEN 2
            WHEN 'rabu' THEN 3 WHEN 'kamis' THEN 4 WHEN 'jumat' THEN 5
            WHEN 'sabtu' THEN 6 ELSE 7 END, s.jam_mulai, p.nama, s.id;
    """
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def daftar_program_tutor(tutor_id: int):
    """Daftar program yang pernah atau sedang diampu oleh tutor."""
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT p.id, p.kode, p.nama, p.jenjang,
                   COUNT(DISTINCT e.student_id) FILTER (WHERE e.status = 'aktif')::int AS siswa_aktif,
                   COUNT(DISTINCT s.id) FILTER (WHERE s.aktif)::int AS jadwal_aktif
            FROM schedules s
            JOIN programs p ON p.id = s.program_id
            LEFT JOIN enrollments e ON e.program_id = p.id
            WHERE s.tutor_id = %s
            GROUP BY p.id
            ORDER BY p.jenjang, p.nama;
            """,
            (tutor_id,),
        )
        return cur.fetchall()


def daftar_siswa_kelas(tutor_id: int, program_id: int):
    """Roster aktif untuk program yang memang pernah ditugaskan kepada tutor."""
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT e.id AS enrollment_id, st.user_id AS student_id, st.nis,
                   u.nama_lengkap, st.jenjang, st.sekolah,
                   ROUND(v.tugas, 2) AS tugas, ROUND(v.kuis, 2) AS kuis,
                   ROUND(v.uts, 2) AS uts, ROUND(v.uas, 2) AS uas,
                   ROUND(v.nilai_akhir, 2) AS nilai_akhir,
                   COALESCE(a.total_tercatat, 0)::int AS total_absensi,
                   COALESCE(a.hadir, 0)::int AS hadir,
                   COALESCE(a.izin, 0)::int AS izin,
                   COALESCE(a.sakit, 0)::int AS sakit,
                   COALESCE(a.alpa, 0)::int AS alpa,
                   a.persen_hadir
            FROM enrollments e
            JOIN students st ON st.user_id = e.student_id
            JOIN users u ON u.id = st.user_id AND u.status = 'aktif'
            LEFT JOIN v_nilai_akhir v ON v.enrollment_id = e.id
            LEFT JOIN LATERAL (
                SELECT COUNT(DISTINCT a.session_id) FILTER (WHERE a.status IS NOT NULL)::int AS total_tercatat,
                       COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'H')::int AS hadir,
                       COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'I')::int AS izin,
                       COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'S')::int AS sakit,
                       COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'A')::int AS alpa,
                       ROUND(100.0 * COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'H')
                         / NULLIF(COUNT(DISTINCT a.session_id) FILTER (WHERE a.status IS NOT NULL), 0), 1) AS persen_hadir
                FROM schedules sch
                JOIN class_sessions cs ON cs.schedule_id = sch.id
                JOIN attendances a ON a.session_id = cs.id AND a.student_id = e.student_id
                WHERE sch.tutor_id = %s AND sch.program_id = e.program_id
            ) a ON TRUE
            WHERE e.program_id = %s AND e.status = 'aktif'
              AND EXISTS (SELECT 1 FROM schedules sx WHERE sx.tutor_id = %s AND sx.program_id = e.program_id)
            ORDER BY u.nama_lengkap, st.user_id;
            """,
            (tutor_id, program_id, tutor_id),
        )
        return cur.fetchall()


def detail_siswa_kelas(tutor_id: int, program_id: int, student_id: int):
    """Detail siswa; query mensyaratkan enrollment aktif dalam kelas tutor."""
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT e.id AS enrollment_id, e.status::text AS status_pendaftaran,
                   p.kode AS kode_program, p.nama AS nama_program,
                   st.user_id AS student_id, st.nis, st.jenjang, st.sekolah,
                   st.no_hp, st.nama_wali, u.username, u.email, u.nama_lengkap,
                   ROUND(v.tugas, 2) AS tugas, ROUND(v.kuis, 2) AS kuis,
                   ROUND(v.uts, 2) AS uts, ROUND(v.uas, 2) AS uas,
                   ROUND(v.nilai_akhir, 2) AS nilai_akhir,
                   COALESCE(a.total_tercatat, 0)::int AS total_absensi,
                   COALESCE(a.hadir, 0)::int AS hadir,
                   COALESCE(a.izin, 0)::int AS izin,
                   COALESCE(a.sakit, 0)::int AS sakit,
                   COALESCE(a.alpa, 0)::int AS alpa,
                   a.persen_hadir
            FROM enrollments e
            JOIN programs p ON p.id = e.program_id
            JOIN students st ON st.user_id = e.student_id
            JOIN users u ON u.id = st.user_id AND u.status = 'aktif'
            LEFT JOIN v_nilai_akhir v ON v.enrollment_id = e.id
            LEFT JOIN LATERAL (
                SELECT COUNT(DISTINCT a.session_id) FILTER (WHERE a.status IS NOT NULL)::int AS total_tercatat,
                       COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'H')::int AS hadir,
                       COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'I')::int AS izin,
                       COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'S')::int AS sakit,
                       COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'A')::int AS alpa,
                       ROUND(100.0 * COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'H')
                         / NULLIF(COUNT(DISTINCT a.session_id) FILTER (WHERE a.status IS NOT NULL), 0), 1) AS persen_hadir
                FROM schedules sch
                JOIN class_sessions cs ON cs.schedule_id = sch.id
                JOIN attendances a ON a.session_id = cs.id AND a.student_id = e.student_id
                WHERE sch.tutor_id = %s AND sch.program_id = e.program_id
            ) a ON TRUE
            WHERE e.student_id = %s AND e.program_id = %s AND e.status = 'aktif'
              AND EXISTS (SELECT 1 FROM schedules sx WHERE sx.tutor_id = %s AND sx.program_id = e.program_id)
            LIMIT 1;
            """,
            (tutor_id, student_id, program_id, tutor_id),
        )
        return cur.fetchone()


def daftar_pertemuan(tutor_id: int, *, program_id: int | None = None, limit: int = 100):
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas pertemuan tidak valid.")
    limit = min(limit, 500)
    filter_program = "AND s.program_id = %s" if program_id is not None else ""
    params = (tutor_id, program_id, limit) if program_id is not None else (tutor_id, limit)
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT cs.id AS session_id, cs.schedule_id, cs.tanggal, cs.pertemuan_ke,
                   cs.topik, cs.ringkasan, cs.status::text AS status_pertemuan,
                   s.program_id, p.kode AS kode_program, p.nama AS nama_program,
                   s.hari::text AS hari, s.jam_mulai, s.jam_selesai,
                   r.nama AS nama_ruang, COALESCE(a.jumlah, 0)::int AS jumlah_absen
            FROM class_sessions cs
            JOIN schedules s ON s.id = cs.schedule_id
            JOIN programs p ON p.id = s.program_id
            JOIN rooms r ON r.id = s.room_id
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS jumlah FROM attendances WHERE session_id = cs.id
            ) a ON TRUE
            WHERE s.tutor_id = %s {filter_program}
            ORDER BY cs.tanggal DESC, cs.pertemuan_ke DESC, cs.id DESC
            LIMIT %s;
            """,
            params,
        )
        return cur.fetchall()


def buka_pertemuan(tutor_id: int, schedule_id: int) -> dict:
    """Buat sesi hari ini secara atomik; jika sudah ada, gunakan sesi yang sama."""
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id FROM schedules WHERE id = %s AND tutor_id = %s AND aktif = TRUE FOR UPDATE;",
            (schedule_id, tutor_id),
        )
        if cur.fetchone() is None:
            raise ValueError("Jadwal tidak ditemukan, bukan milikmu, atau sudah nonaktif.")
        cur.execute("SELECT CURRENT_DATE AS tanggal;")
        tanggal = cur.fetchone()["tanggal"]
        cur.execute(
            "SELECT id, pertemuan_ke FROM class_sessions WHERE schedule_id = %s AND tanggal = %s;",
            (schedule_id, tanggal),
        )
        existing = cur.fetchone()
        if existing:
            conn.commit()
            return {"session_id": existing["id"], "pertemuan_ke": existing["pertemuan_ke"], "tanggal": tanggal, "dibuat": False}
        cur.execute(
            "SELECT COALESCE(MAX(pertemuan_ke), 0) + 1 AS berikutnya FROM class_sessions WHERE schedule_id = %s;",
            (schedule_id,),
        )
        nomor = cur.fetchone()["berikutnya"]
        cur.execute(
            "INSERT INTO class_sessions (schedule_id, tanggal, pertemuan_ke) VALUES (%s, %s, %s) RETURNING id;",
            (schedule_id, tanggal, nomor),
        )
        session_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, 'PERTEMUAN_DIBUKA', %s);",
            (tutor_id, f"session_id={session_id}; schedule_id={schedule_id}; pertemuan_ke={nomor}"),
        )
        conn.commit()
        return {"session_id": session_id, "pertemuan_ke": nomor, "tanggal": tanggal, "dibuat": True}


def daftar_absensi_sesi(tutor_id: int, session_id: int):
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT cs.id, cs.status::text AS status_pertemuan, s.program_id
            FROM class_sessions cs JOIN schedules s ON s.id = cs.schedule_id
            WHERE cs.id = %s AND s.tutor_id = %s;
            """,
            (session_id, tutor_id),
        )
        sesi = cur.fetchone()
        if not sesi:
            raise ValueError("Pertemuan tidak ditemukan atau bukan milikmu.")
        cur.execute(
            """
            SELECT st.user_id AS student_id, st.nis, u.nama_lengkap,
                   a.status::text AS status_absensi, a.keterangan
            FROM enrollments e
            JOIN students st ON st.user_id = e.student_id
            JOIN users u ON u.id = st.user_id
            LEFT JOIN attendances a ON a.student_id = e.student_id AND a.session_id = %s
            WHERE e.program_id = %s
              AND (e.status = 'aktif' OR a.session_id IS NOT NULL)
            ORDER BY u.nama_lengkap, st.user_id;
            """,
            (session_id, sesi["program_id"]),
        )
        return cur.fetchall()


def simpan_absensi(tutor_id: int, session_id: int, records: list[dict]) -> int:
    if not isinstance(records, list) or not records:
        raise ValueError("Tidak ada data absensi untuk disimpan.")
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT cs.id, cs.status::text AS status_pertemuan, s.program_id
            FROM class_sessions cs JOIN schedules s ON s.id = cs.schedule_id
            WHERE cs.id = %s AND s.tutor_id = %s FOR UPDATE OF cs;
            """,
            (session_id, tutor_id),
        )
        sesi = cur.fetchone()
        if not sesi:
            raise ValueError("Pertemuan tidak ditemukan atau bukan milikmu.")
        if sesi["status_pertemuan"] == "batal":
            raise ValueError("Absensi tidak dapat diubah untuk pertemuan yang dibatalkan.")
        seen = set()
        for record in records:
            student_id = record["student_id"]
            status = record["status"]
            if student_id in seen:
                raise ValueError("Siswa yang sama tercantum lebih dari sekali.")
            seen.add(student_id)
            cur.execute(
                """
                SELECT 1 FROM enrollments e
                WHERE e.student_id = %s AND e.program_id = %s
                  AND (e.status = 'aktif' OR EXISTS (
                      SELECT 1 FROM attendances a WHERE a.session_id = %s AND a.student_id = e.student_id
                  ))
                FOR UPDATE;
                """,
                (student_id, sesi["program_id"], session_id),
            )
            if cur.fetchone() is None:
                raise ValueError(f"Siswa ID {student_id} bukan peserta sah program ini.")
            cur.execute(
                """
                INSERT INTO attendances (session_id, student_id, status, keterangan, dicatat_at)
                VALUES (%s, %s, %s::attendance_status, %s, now())
                ON CONFLICT (session_id, student_id) DO UPDATE
                SET status = EXCLUDED.status, keterangan = EXCLUDED.keterangan, dicatat_at = now();
                """,
                (session_id, student_id, status, record.get("keterangan")),
            )
        cur.execute(
            "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, 'ABSENSI_DISIMPAN', %s);",
            (tutor_id, f"session_id={session_id}; jumlah_siswa={len(records)}"),
        )
        conn.commit()
    return len(records)


def rekap_absensi_tutor(tutor_id: int, program_id: int):
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT st.user_id AS student_id, st.nis, u.nama_lengkap,
                   COUNT(DISTINCT cs.id)::int AS total_pertemuan,
                   COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'H')::int AS hadir,
                   COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'I')::int AS izin,
                   COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'S')::int AS sakit,
                   COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'A')::int AS alpa,
                   ROUND(100.0 * COUNT(DISTINCT a.session_id) FILTER (WHERE a.status = 'H')
                     / NULLIF(COUNT(DISTINCT a.session_id) FILTER (WHERE a.status IS NOT NULL), 0), 1) AS persen_hadir
            FROM enrollments e
            JOIN students st ON st.user_id = e.student_id
            JOIN users u ON u.id = st.user_id AND u.status = 'aktif'
            JOIN schedules s ON s.program_id = e.program_id AND s.tutor_id = %s
            JOIN class_sessions cs ON cs.schedule_id = s.id
            LEFT JOIN attendances a ON a.session_id = cs.id AND a.student_id = e.student_id
            WHERE e.program_id = %s AND e.status = 'aktif'
            GROUP BY st.user_id, st.nis, u.nama_lengkap
            ORDER BY u.nama_lengkap;
            """,
            (tutor_id, program_id),
        )
        return cur.fetchall()


def tambah_nilai(tutor_id: int, program_id: int, student_id: int, *, jenis: str, judul: str | None, nilai, tanggal=None) -> int:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT e.id FROM enrollments e
            JOIN students st ON st.user_id = e.student_id
            JOIN users u ON u.id = st.user_id AND u.status = 'aktif'
            WHERE e.student_id = %s AND e.program_id = %s AND e.status = 'aktif'
              AND EXISTS (SELECT 1 FROM schedules s WHERE s.program_id = e.program_id AND s.tutor_id = %s)
            FOR UPDATE OF e;
            """,
            (student_id, program_id, tutor_id),
        )
        enrollment = cur.fetchone()
        if enrollment is None:
            raise ValueError("Siswa tidak aktif pada program yang kamu ampu.")
        cur.execute(
            """
            INSERT INTO grades (enrollment_id, jenis, judul, nilai, tanggal, input_by)
            VALUES (%s, %s::grade_type, %s, %s, COALESCE(%s::date, CURRENT_DATE), %s)
            RETURNING id;
            """,
            (enrollment["id"], jenis, judul, nilai, tanggal, tutor_id),
        )
        grade_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, 'NILAI_DITAMBAHKAN', %s);",
            (tutor_id, f"grade_id={grade_id}; enrollment_id={enrollment['id']}; jenis={jenis}"),
        )
        conn.commit()
        return grade_id


def daftar_nilai_tutor(tutor_id: int, program_id: int, *, hanya_milik_tutor: bool = False, limit: int = 200):
    limit = max(1, min(int(limit), 500))
    filter_milik = "AND g.input_by = %s" if hanya_milik_tutor else ""
    params = [program_id, tutor_id]
    if hanya_milik_tutor:
        params.append(tutor_id)
    params.append(limit)
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT g.id AS grade_id, g.enrollment_id, e.student_id, st.nis,
                   u.nama_lengkap, g.jenis::text AS jenis, g.judul, g.nilai,
                   g.tanggal, g.created_at
            FROM grades g
            JOIN enrollments e ON e.id = g.enrollment_id
            JOIN students st ON st.user_id = e.student_id
            JOIN users u ON u.id = st.user_id
            WHERE e.program_id = %s
              AND EXISTS (SELECT 1 FROM schedules s WHERE s.program_id = e.program_id AND s.tutor_id = %s)
              {filter_milik}
            ORDER BY g.tanggal DESC, g.id DESC
            LIMIT %s;
            """,
            tuple(params),
        )
        return cur.fetchall()


def ubah_nilai(tutor_id: int, grade_id: int, *, jenis: str, judul: str | None, nilai, tanggal=None) -> bool:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE grades g
            SET jenis = %s::grade_type, judul = %s, nilai = %s,
                tanggal = COALESCE(%s::date, CURRENT_DATE)
            WHERE g.id = %s AND g.input_by = %s
              AND EXISTS (
                  SELECT 1 FROM enrollments e JOIN schedules s ON s.program_id = e.program_id
                  WHERE e.id = g.enrollment_id AND s.tutor_id = %s
              )
            RETURNING g.id;
            """,
            (jenis, judul, nilai, tanggal, grade_id, tutor_id, tutor_id),
        )
        hasil = cur.fetchone()
        if not hasil:
            conn.rollback()
            return False
        cur.execute(
            "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, 'NILAI_DIUBAH', %s);",
            (tutor_id, f"grade_id={grade_id}; jenis={jenis}"),
        )
        conn.commit()
    return True


def simpan_catatan(tutor_id: int, session_id: int, *, topik: str | None, ringkasan: str | None) -> bool:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE class_sessions cs SET topik = %s, ringkasan = %s
            FROM schedules s
            WHERE cs.schedule_id = s.id AND cs.id = %s AND s.tutor_id = %s
              AND cs.status <> 'batal'
            RETURNING cs.id;
            """,
            (topik, ringkasan, session_id, tutor_id),
        )
        hasil = cur.fetchone()
        if not hasil:
            conn.rollback()
            return False
        cur.execute(
            "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, 'CATATAN_MATERI_DISIMPAN', %s);",
            (tutor_id, f"session_id={session_id}"),
        )
        conn.commit()
    return True


def daftar_catatan_tutor(tutor_id: int, *, program_id: int | None = None, limit: int = 100):
    limit = max(1, min(int(limit), 500))
    filter_program = "AND s.program_id = %s" if program_id is not None else ""
    params = (tutor_id, program_id, limit) if program_id is not None else (tutor_id, limit)
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT cs.id AS session_id, cs.tanggal, cs.pertemuan_ke, cs.topik, cs.ringkasan,
                   p.kode AS kode_program, p.nama AS nama_program,
                   s.hari::text AS hari, s.jam_mulai
            FROM class_sessions cs
            JOIN schedules s ON s.id = cs.schedule_id
            JOIN programs p ON p.id = s.program_id
            WHERE s.tutor_id = %s {filter_program}
              AND (NULLIF(BTRIM(cs.topik), '') IS NOT NULL OR NULLIF(BTRIM(cs.ringkasan), '') IS NOT NULL)
            ORDER BY cs.tanggal DESC, cs.pertemuan_ke DESC
            LIMIT %s;
            """,
            params,
        )
        return cur.fetchall()
