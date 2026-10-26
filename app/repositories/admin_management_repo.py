"""Query admin untuk akun, profil siswa, profil tutor, dan jadwal tutor."""

from psycopg.rows import dict_row

from app.db import pool


_STATUS_USER = {
    "belum_verifikasi",
    "menunggu_konfirmasi",
    "aktif",
    "ditolak",
    "nonaktif",
}
_ROLE_USER = {"admin", "tutor", "siswa"}


def _catat(cur, admin_id: int, aksi: str, detail: str) -> None:
    cur.execute(
        "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, %s, %s);",
        (admin_id, aksi, detail),
    )


def daftar_akun_admin(role: str | None = None, status: str | None = None):
    """Daftar akun dengan profil ID resmi tanpa menampilkan hash password."""
    if role not in (None, *_ROLE_USER):
        raise ValueError("Filter role tidak valid.")
    if status not in (None, *_STATUS_USER):
        raise ValueError("Filter status tidak valid.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT u.id, u.username, u.email, u.nama_lengkap,
                       u.role::text AS role, u.status::text AS status,
                       u.email_verified, u.failed_attempts, u.locked_until,
                       u.must_change_password, u.created_at, u.last_login,
                       s.nis, t.kode_tutor
                FROM users AS u
                LEFT JOIN students AS s ON s.user_id = u.id
                LEFT JOIN tutors AS t ON t.user_id = u.id
                WHERE (%s::text IS NULL OR u.role::text = %s)
                  AND (%s::text IS NULL OR u.status::text = %s)
                ORDER BY u.created_at DESC, u.id DESC;
                """,
                (role, role, status, status),
            )
            return cur.fetchall()


def ubah_status_akun_admin(user_id: int, status_baru: str, admin_id: int) -> bool:
    """Aktifkan/nonaktifkan akun siswa atau tutor dengan log aktivitas."""
    if status_baru not in {"aktif", "nonaktif"}:
        raise ValueError("Status yang diizinkan hanya aktif atau nonaktif.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE users
                SET status = %s::user_status,
                    reject_reason = CASE WHEN %s = 'aktif' THEN NULL ELSE reject_reason END
                WHERE id = %s
                  AND role IN ('siswa', 'tutor')
                  AND status IN ('aktif', 'nonaktif')
                RETURNING id, role::text AS role, status::text AS status;
                """,
                (status_baru, status_baru, user_id),
            )
            hasil = cur.fetchone()
            if hasil is None:
                conn.rollback()
                return False
            _catat(cur, admin_id, "STATUS_AKUN_DIUBAH", f"user_id={user_id}; status={status_baru}")
        conn.commit()
    return True


def buka_kunci_akun_admin(user_id: int, admin_id: int) -> bool:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET failed_attempts = 0, locked_until = NULL
                WHERE id = %s
                  AND (failed_attempts > 0 OR locked_until IS NOT NULL)
                RETURNING id;
                """,
                (user_id,),
            )
            hasil = cur.fetchone()
            if hasil is None:
                conn.rollback()
                return False
            _catat(cur, admin_id, "AKUN_DIBUKA_KUNCI", f"user_id={user_id}")
        conn.commit()
    return True


def reset_password_akun_admin(user_id: int, password_hash: str, admin_id: int) -> bool:
    """Simpan password sementara dan wajibkan pergantian saat login berikutnya."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET password_hash = %s,
                    must_change_password = TRUE,
                    failed_attempts = 0,
                    locked_until = NULL
                WHERE id = %s
                RETURNING id;
                """,
                (password_hash, user_id),
            )
            if cur.fetchone() is None:
                conn.rollback()
                return False
            _catat(cur, admin_id, "PASSWORD_AKUN_DIRESET", f"user_id={user_id}")
        conn.commit()
    return True


def _where_siswa(jenjang=None, program_id=None, status=None, cari=None, user_id=None):
    """Helper parameter filter; caller adds the returned WHERE and params."""
    where = ["u.role = 'siswa'"]
    params = []
    if user_id is not None:
        where.append("u.id = %s")
        params.append(user_id)
    if jenjang:
        where.append("s.jenjang ILIKE %s")
        params.append(f"%{jenjang.strip()}%")
    if status:
        if status not in _STATUS_USER:
            raise ValueError("Filter status siswa tidak valid.")
        where.append("u.status::text = %s")
        params.append(status)
    if program_id is not None:
        where.append("EXISTS (SELECT 1 FROM enrollments ef WHERE ef.student_id = s.user_id AND ef.program_id = %s)")
        params.append(program_id)
    if cari:
        pola = f"%{cari.strip()}%"
        where.append("(u.nama_lengkap ILIKE %s OR u.username ILIKE %s OR u.email ILIKE %s OR COALESCE(s.nis, '') ILIKE %s)")
        params.extend([pola, pola, pola, pola])
    return " AND ".join(where), params


def daftar_siswa_admin(jenjang=None, program_id=None, status=None, cari=None):
    where, params = _where_siswa(jenjang, program_id, status, cari)
    sql = f"""
        SELECT u.id AS user_id, u.username, u.email, u.nama_lengkap,
               u.status::text AS status, u.email_verified, u.created_at,
               s.nis, s.jenjang, s.sekolah, s.no_hp, s.nama_wali,
               COALESCE(string_agg(DISTINCT p.nama, ', ' ORDER BY p.nama)
                   FILTER (WHERE e.id IS NOT NULL), 'Belum ada program') AS program
        FROM users u
        JOIN students s ON s.user_id = u.id
        LEFT JOIN enrollments e ON e.student_id = s.user_id AND e.status IN ('menunggu', 'aktif')
        LEFT JOIN programs p ON p.id = e.program_id
        WHERE {where}
        GROUP BY u.id, u.username, u.email, u.nama_lengkap, u.status,
                 u.email_verified, u.created_at, s.nis, s.jenjang,
                 s.sekolah, s.no_hp, s.nama_wali
        ORDER BY u.nama_lengkap, u.id;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, tuple(params))
            return cur.fetchall()


def detail_siswa_admin(user_id: int):
    where, params = _where_siswa(user_id=user_id)
    sql = f"""
        SELECT u.id AS user_id, u.username, u.email, u.nama_lengkap,
               u.status::text AS status, u.email_verified, u.created_at,
               u.last_login, s.nis, s.jenjang, s.sekolah, s.no_hp, s.nama_wali,
               COALESCE(string_agg(DISTINCT p.nama, ', ' ORDER BY p.nama)
                   FILTER (WHERE e.id IS NOT NULL), 'Belum ada program') AS program
        FROM users u
        JOIN students s ON s.user_id = u.id
        LEFT JOIN enrollments e ON e.student_id = s.user_id AND e.status IN ('menunggu', 'aktif')
        LEFT JOIN programs p ON p.id = e.program_id
        WHERE {where}
        GROUP BY u.id, u.username, u.email, u.nama_lengkap, u.status,
                 u.email_verified, u.created_at, u.last_login, s.nis,
                 s.jenjang, s.sekolah, s.no_hp, s.nama_wali;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, tuple(params))
            return cur.fetchone()


def ubah_siswa_admin(user_id: int, perubahan: dict, admin_id: int) -> bool:
    kolom_user = {"nama_lengkap"}
    kolom_siswa = {"jenjang", "sekolah", "no_hp", "nama_wali"}
    if not perubahan or set(perubahan) - (kolom_user | kolom_siswa):
        raise ValueError("Kolom perubahan profil siswa tidak valid.")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id=%s AND role='siswa' FOR UPDATE;", (user_id,))
            if cur.fetchone() is None:
                conn.rollback()
                return False
            if "nama_lengkap" in perubahan:
                cur.execute("UPDATE users SET nama_lengkap=%s WHERE id=%s;", (perubahan["nama_lengkap"], user_id))
            perubahan_siswa = {k: v for k, v in perubahan.items() if k in kolom_siswa}
            if perubahan_siswa:
                set_clause = ", ".join(f"{kolom} = %s" for kolom in perubahan_siswa)
                cur.execute(
                    f"UPDATE students SET {set_clause} WHERE user_id = %s;",
                    (*perubahan_siswa.values(), user_id),
                )
            _catat(cur, admin_id, "PROFIL_SISWA_DIUBAH", f"user_id={user_id}; kolom={','.join(perubahan)}")
        conn.commit()
    return True


def daftar_tutor_admin(cari=None, user_id=None):
    params = []
    where = ["u.role = 'tutor'"]
    if user_id is not None:
        where.append("u.id = %s")
        params.append(user_id)
    if cari:
        pola = f"%{cari.strip()}%"
        where.append("(u.nama_lengkap ILIKE %s OR u.username ILIKE %s OR u.email ILIKE %s OR COALESCE(t.kode_tutor, '') ILIKE %s)")
        params.extend([pola, pola, pola, pola])
    sql = f"""
        SELECT u.id AS user_id, u.username, u.email, u.nama_lengkap,
               u.status::text AS status, u.email_verified, u.created_at,
               t.kode_tutor, t.keahlian, t.no_hp,
               COUNT(DISTINCT sc.id)::int AS jumlah_jadwal,
               COALESCE(string_agg(DISTINCT p.nama, ', ' ORDER BY p.nama)
                   FILTER (WHERE sc.id IS NOT NULL), 'Belum ada jadwal') AS program
        FROM users u
        JOIN tutors t ON t.user_id = u.id
        LEFT JOIN schedules sc ON sc.tutor_id = t.user_id AND sc.aktif = TRUE
        LEFT JOIN programs p ON p.id = sc.program_id
        WHERE {' AND '.join(where)}
        GROUP BY u.id, u.username, u.email, u.nama_lengkap, u.status,
                 u.email_verified, u.created_at, t.kode_tutor, t.keahlian, t.no_hp
        ORDER BY u.nama_lengkap, u.id;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, tuple(params))
            return cur.fetchall()


def detail_tutor_admin(user_id: int):
    rows = daftar_tutor_admin(user_id=user_id)
    return rows[0] if rows else None


def jadwal_tutor_admin(user_id: int):
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT sc.id, p.kode AS kode_program, p.nama AS nama_program,
                       sc.hari::text AS hari,
                       to_char(sc.jam_mulai, 'HH24:MI') AS jam_mulai,
                       to_char(sc.jam_selesai, 'HH24:MI') AS jam_selesai,
                       r.nama AS ruang, sc.aktif
                FROM schedules sc
                JOIN programs p ON p.id = sc.program_id
                JOIN rooms r ON r.id = sc.room_id
                WHERE sc.tutor_id = %s
                ORDER BY sc.aktif DESC, sc.hari, sc.jam_mulai, sc.id;
                """,
                (user_id,),
            )
            return cur.fetchall()


def ubah_tutor_admin(user_id: int, perubahan: dict, admin_id: int) -> bool:
    kolom_user = {"nama_lengkap"}
    kolom_tutor = {"keahlian", "no_hp"}
    if not perubahan or set(perubahan) - (kolom_user | kolom_tutor):
        raise ValueError("Kolom perubahan profil tutor tidak valid.")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id=%s AND role='tutor' FOR UPDATE;", (user_id,))
            if cur.fetchone() is None:
                conn.rollback()
                return False
            if "nama_lengkap" in perubahan:
                cur.execute("UPDATE users SET nama_lengkap=%s WHERE id=%s;", (perubahan["nama_lengkap"], user_id))
            perubahan_tutor = {k: v for k, v in perubahan.items() if k in kolom_tutor}
            if perubahan_tutor:
                set_clause = ", ".join(f"{kolom} = %s" for kolom in perubahan_tutor)
                cur.execute(
                    f"UPDATE tutors SET {set_clause} WHERE user_id = %s;",
                    (*perubahan_tutor.values(), user_id),
                )
            _catat(cur, admin_id, "PROFIL_TUTOR_DIUBAH", f"user_id={user_id}; kolom={','.join(perubahan)}")
        conn.commit()
    return True
