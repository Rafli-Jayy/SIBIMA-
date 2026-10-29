"""Query tabel students dan tutors.

Fungsi yang direncanakan:
    - buat_profil_siswa
    - buat_profil_tutor
    - ubah_profil_siswa
    - ubah_profil_tutor
    - terbitkan_nis
    - terbitkan_kode_tutor
    - daftar_siswa
    - daftar_tutor
    - cari_siswa
"""

"""Repository profil siswa/tutor dan persetujuan akun."""

from psycopg.rows import dict_row

from app.db import pool


def proses_persetujuan_akun(
    user_id: int,
    approved_by: int,
    status: str,
    reject_reason: str | None = None,
) -> dict:
    """Memproses persetujuan/penolakan akun secara transaksional.

    Persetujuan:
    - Memastikan akun menunggu dan email terverifikasi.
    - Menerbitkan NIS atau kode tutor jika belum tersedia.
    - Mengaktifkan akun dalam transaksi yang sama.

    Penolakan:
    - Memastikan akun menunggu dan email terverifikasi.
    - Menyimpan status, alasan, admin pemroses, dan waktunya.
    """
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("ID pengguna tidak valid.")

    if type(approved_by) is not int or approved_by <= 0:
        raise ValueError("ID administrator tidak valid.")

    if status not in {"aktif", "ditolak"}:
        raise ValueError("Status persetujuan tidak valid.")

    alasan = (
        reject_reason.strip()
        if isinstance(reject_reason, str)
        else ""
    )

    if status == "ditolak" and not alasan:
        raise ValueError("Alasan penolakan wajib diisi.")

    identitas = None
    jenis_identitas = None

    # Jika terjadi exception, transaksi dibatalkan oleh context manager.
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Kunci akun agar dua admin tidak memprosesnya bersamaan.
            cur.execute(
                """
                SELECT id, role, status, email_verified
                FROM users
                WHERE id = %s
                FOR UPDATE;
                """,
                (user_id,),
            )
            user = cur.fetchone()

            if user is None:
                raise ValueError("Pengguna tidak ditemukan.")

            if user["role"] not in {"siswa", "tutor"}:
                raise ValueError(
                    "Hanya akun siswa dan tutor yang dapat diproses."
                )

            if not user["email_verified"]:
                raise ValueError(
                    "Email pengguna belum diverifikasi."
                )

            if user["status"] != "menunggu_konfirmasi":
                raise ValueError(
                    "Akun tidak lagi menunggu persetujuan."
                )

            # Pastikan profil ada dan kunci barisnya.
            if user["role"] == "siswa":
                cur.execute(
                    """
                    SELECT user_id, nis
                    FROM students
                    WHERE user_id = %s
                    FOR UPDATE;
                    """,
                    (user_id,),
                )
                profil = cur.fetchone()

                if profil is None:
                    raise ValueError(
                        "Profil siswa tidak ditemukan."
                    )

                jenis_identitas = "NIS"
                identitas = profil["nis"]

                if status == "aktif" and not identitas:
                    cur.execute(
                        """
                        UPDATE students
                        SET nis = fn_next_nis()
                        WHERE user_id = %s
                          AND nis IS NULL
                        RETURNING nis;
                        """,
                        (user_id,),
                    )
                    hasil_identitas = cur.fetchone()

                    if hasil_identitas is None:
                        raise ValueError(
                            "NIS gagal diterbitkan."
                        )

                    identitas = hasil_identitas["nis"]

            else:
                cur.execute(
                    """
                    SELECT user_id, kode_tutor
                    FROM tutors
                    WHERE user_id = %s
                    FOR UPDATE;
                    """,
                    (user_id,),
                )
                profil = cur.fetchone()

                if profil is None:
                    raise ValueError(
                        "Profil tutor tidak ditemukan."
                    )

                jenis_identitas = "Kode tutor"
                identitas = profil["kode_tutor"]

                if status == "aktif" and not identitas:
                    cur.execute(
                        """
                        UPDATE tutors
                        SET kode_tutor = fn_next_kode_tutor()
                        WHERE user_id = %s
                          AND kode_tutor IS NULL
                        RETURNING kode_tutor;
                        """,
                        (user_id,),
                    )
                    hasil_identitas = cur.fetchone()

                    if hasil_identitas is None:
                        raise ValueError(
                            "Kode tutor gagal diterbitkan."
                        )

                    identitas = hasil_identitas["kode_tutor"]

            # Status hanya boleh berubah jika masih menunggu.
            cur.execute(
                """
                UPDATE users
                SET status = %s,
                    approved_by = %s,
                    approved_at = now(),
                    reject_reason = %s
                WHERE id = %s
                  AND status = 'menunggu_konfirmasi'
                  AND email_verified = TRUE
                RETURNING id;
                """,
                (
                    status,
                    approved_by,
                    alasan if status == "ditolak" else None,
                    user_id,
                ),
            )

            if cur.fetchone() is None:
                raise ValueError(
                    "Status akun berubah. Muat ulang daftar konfirmasi."
                )

        conn.commit()

    return {
        "user_id": user_id,
        "role": user["role"],
        "status": status,
        "jenis_identitas": jenis_identitas,
        "identitas": identitas,
    }

def detail_pengguna_persetujuan(user_id: int) -> dict | None:
    """Ambil detail akun dan profil yang diperlukan sebelum keputusan admin.

    Password hash tidak pernah dipilih atau ditampilkan di UI.
    """
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("ID pengguna tidak valid.")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    u.id, u.username, u.email, u.nama_lengkap, u.role, u.status,
                    u.email_verified, u.created_at, u.last_login,
                    u.failed_attempts, u.locked_until, u.must_change_password,
                    u.approved_at, u.reject_reason,
                    s.nis, s.jenjang, s.sekolah, s.no_hp AS student_no_hp,
                    s.nama_wali,
                    t.kode_tutor, t.keahlian, t.no_hp AS tutor_no_hp
                FROM users AS u
                LEFT JOIN students AS s ON s.user_id = u.id
                LEFT JOIN tutors AS t ON t.user_id = u.id
                WHERE u.id = %s;
                """,
                (user_id,),
            )
            return cur.fetchone()
