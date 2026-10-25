"""Query tabel otp_codes.

Fungsi yang direncanakan:
    - simpan_otp
    - ambil_otp_aktif
    - tambah_percobaan
    - tandai_terpakai
    - hitung_kirim_terakhir
"""


"""Repository untuk mengelola OTP pada tabel otp_codes."""



from psycopg.rows import dict_row

from app.db import pool


def simpan_otp(
    user_id: int,
    code_hash: str,
    tujuan: str,
    expires_at,
) -> int:
    """Simpan OTP baru dan nonaktifkan OTP lama yang belum digunakan."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE otp_codes
                SET used_at = now()
                WHERE user_id = %s
                  AND purpose = %s
                  AND used_at IS NULL;
                """,
                (user_id, tujuan),
            )

            cur.execute(
                """
                INSERT INTO otp_codes (
                    user_id, code_hash, purpose, expires_at
                )
                VALUES (%s, %s, %s, %s)
                RETURNING id;
                """,
                (user_id, code_hash, tujuan, expires_at),
            )

            otp_id = cur.fetchone()[0]

        conn.commit()

    return otp_id


def ambil_otp_aktif(user_id: int, tujuan: str):
    """Ambil OTP terbaru yang belum digunakan."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, user_id, code_hash, purpose,
                       expires_at, attempts, used_at, created_at
                FROM otp_codes
                WHERE user_id = %s
                  AND purpose = %s
                  AND used_at IS NULL
                ORDER BY created_at DESC, id DESC
                LIMIT 1;
                """,
                (user_id, tujuan),
            )

            return cur.fetchone()


def tambah_percobaan(otp_id: int, batas: int):
    """Tambah percobaan dan nonaktifkan OTP saat batas tercapai."""
    if batas < 1:
        raise ValueError("Batas percobaan harus minimal 1.")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE otp_codes
                SET attempts = attempts + 1,
                    used_at = CASE
                        WHEN attempts + 1 >= %s THEN now()
                        ELSE used_at
                    END
                WHERE id = %s
                  AND used_at IS NULL
                RETURNING attempts, used_at;
                """,
                (batas, otp_id),
            )

            hasil = cur.fetchone()

        conn.commit()

    return hasil


def tandai_terpakai(otp_id: int) -> bool:
    """Tandai OTP sebagai terpakai agar tidak dapat digunakan ulang."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE otp_codes
                SET used_at = now()
                WHERE id = %s
                  AND used_at IS NULL;
                """,
                (otp_id,),
            )

            berhasil = cur.rowcount == 1

        conn.commit()

    return berhasil


def hitung_kirim_terakhir(
    user_id: int,
    tujuan: str,
    detik: int = 60,
) -> int:
    """Hitung jumlah OTP yang dibuat dalam rentang waktu tertentu."""
    if detik < 1:
        raise ValueError("Rentang waktu harus minimal 1 detik.")

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM otp_codes
                WHERE user_id = %s
                  AND purpose = %s
                  AND created_at >=
                      now() - (%s * INTERVAL '1 second');
                """,
                (user_id, tujuan, detik),
            )

            return cur.fetchone()[0]
