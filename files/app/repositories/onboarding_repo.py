"""Operasi onboarding siswa yang perlu dilakukan secara atomik."""

from psycopg.rows import dict_row

from app.db import pool


def tolak_siswa_dan_paket(
    user_id: int,
    approved_by: int,
    alasan: str,
) -> dict:
    """Tolak akun siswa dan semua pilihan paket yang masih menunggu atomik."""
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("ID pengguna tidak valid.")
    if type(approved_by) is not int or approved_by <= 0:
        raise ValueError("ID administrator tidak valid.")
    if not isinstance(alasan, str) or not alasan.strip():
        raise ValueError("Alasan penolakan wajib diisi.")
    alasan = alasan.strip()

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, username, email, nama_lengkap, role, status,
                       email_verified
                FROM users
                WHERE id = %s
                FOR UPDATE;
                """,
                (user_id,),
            )
            user = cur.fetchone()
            if user is None:
                raise ValueError("Pengguna tidak ditemukan.")
            if user["role"] != "siswa":
                raise ValueError("Operasi penolakan paket ini hanya untuk siswa.")
            if not user["email_verified"]:
                raise ValueError("Email siswa belum diverifikasi.")
            if user["status"] != "menunggu_konfirmasi":
                raise ValueError("Akun siswa tidak lagi menunggu persetujuan.")

            cur.execute(
                """
                UPDATE enrollments
                SET status = 'ditolak',
                    processed_by = %s,
                    processed_at = now(),
                    alasan_tolak = %s
                WHERE student_id = %s AND status = 'menunggu'
                RETURNING id;
                """,
                (approved_by, alasan, user_id),
            )
            enrollment_ids = [row["id"] for row in cur.fetchall()]

            cur.execute(
                """
                UPDATE users
                SET status = 'ditolak',
                    approved_by = %s,
                    approved_at = now(),
                    reject_reason = %s
                WHERE id = %s
                  AND role = 'siswa'
                  AND status = 'menunggu_konfirmasi'
                  AND email_verified = TRUE
                RETURNING id;
                """,
                (approved_by, alasan, user_id),
            )
            if cur.fetchone() is None:
                raise ValueError(
                    "Status akun berubah. Muat ulang antrean konfirmasi."
                )

        conn.commit()

    return {
        "user_id": user_id,
        "username": user["username"],
        "email": user["email"],
        "nama_lengkap": user["nama_lengkap"],
        "enrollment_ids": enrollment_ids,
        "alasan": alasan,
    }
