"""Query tabel users.

Fungsi yang direncanakan:
    - buat_user
    - cari_by_username
    - cari_by_id
    - cari_by_email
    - daftar_by_status
    - set_status
    - catat_gagal_login
    - reset_gagal_login
    - set_password
    - set_terverifikasi
    - set_persetujuan
"""

import psycopg
from psycopg.rows import dict_row
from app.db import pool

def buat_user(username: str, email: str, nama_lengkap: str, password_hash: str, role: str = "siswa"):
    """Menyimpan user baru dan tabel relasinya (students/tutors)."""
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                # 1. Insert ke tabel users
                cur.execute("""
                    INSERT INTO users (username, email, nama_lengkap, password_hash, role)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id;
                """, (username, email, nama_lengkap, password_hash, role))
                
                user_id = cur.fetchone()[0]
                
                # 2. Insert ke tabel profil yang sesuai
                if role == 'siswa':
                    cur.execute("INSERT INTO students (user_id, role) VALUES (%s, %s);", (user_id, role))
                elif role == 'tutor':
                    cur.execute("INSERT INTO tutors (user_id, role) VALUES (%s, %s);", (user_id, role))
                
                conn.commit()
                return user_id
    except psycopg.IntegrityError:
        return None

def cari_by_username(username: str):
    """Mencari user berdasarkan username (tidak case-sensitive)."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM users WHERE lower(username) = lower(%s);", (username,))
            return cur.fetchone()

def cari_by_id(user_id: int):
    """Mencari user berdasarkan ID."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s;", (user_id,))
            return cur.fetchone()

def cari_by_email(email: str):
    """Mencari user berdasarkan email."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM users WHERE lower(email) = lower(%s);", (email,))
            return cur.fetchone()

def daftar_by_status(status: str):
    """Mengambil daftar semua user dengan status tertentu (misal: menunggu_konfirmasi)."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM users WHERE status = %s ORDER BY created_at DESC;", (status,))
            return cur.fetchall()

def set_status(user_id: int, status: str):
    """Mengubah status aktif/nonaktif/ditolak pengguna."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET status = %s WHERE id = %s;", (status, user_id))
            conn.commit()

def catat_gagal_login(user_id: int):
    """Menambah angka failed_attempts sebesar +1."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET failed_attempts = failed_attempts + 1 WHERE id = %s;", (user_id,))
            conn.commit()

def reset_gagal_login(user_id: int):
    """Mereset failed_attempts menjadi 0 dan memperbarui waktu last_login saat berhasil masuk."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET failed_attempts = 0, last_login = now() WHERE id = %s;", (user_id,))
            conn.commit()

def set_password(user_id: int, password_hash: str):
    """Memperbarui hash password pengguna."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password_hash = %s, must_change_password = FALSE WHERE id = %s;", 
                        (password_hash, user_id))
            conn.commit()

def set_terverifikasi(user_id: int):
    """Menandai email_verified menjadi TRUE (Biasanya dilakukan setelah OTP)."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET email_verified = TRUE, status = 'menunggu_konfirmasi' WHERE id = %s;", (user_id,))
            conn.commit()

def set_persetujuan(user_id: int, approved_by: int, status: str, reject_reason: str = None):
    """Dieksekusi oleh admin untuk menyetujui atau menolak pendaftaran siswa/tutor."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET status = %s, approved_by = %s, approved_at = now(), reject_reason = %s
                WHERE id = %s;
            """, (status, approved_by, reject_reason, user_id))
            conn.commit()

def catat_gagal_login(
    user_id: int,
    max_attempts: int = 3,
    lock_minutes: int = 5,
):
    """Tambah kegagalan login dan kunci akun jika batas tercapai."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE users
                SET
                    failed_attempts = failed_attempts + 1,
                    locked_until = CASE
                        WHEN failed_attempts + 1 >= %s
                        THEN now() + (%s * INTERVAL '1 minute')
                        ELSE locked_until
                    END
                WHERE id = %s
                RETURNING failed_attempts, locked_until;
                """,
                (max_attempts, lock_minutes, user_id),
            )

            hasil = cur.fetchone()
            conn.commit()
            return hasil


def reset_gagal_login(user_id: int):
    """Reset penghitung kegagalan setelah login berhasil."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET
                    failed_attempts = 0,
                    locked_until = NULL,
                    last_login = now()
                WHERE id = %s;
                """,
                (user_id,),
            )
            conn.commit()


def reset_lock_kedaluwarsa(user_id: int):
    """Buka kembali akun yang masa pengunciannya sudah lewat."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET failed_attempts = 0,
                    locked_until = NULL
                WHERE id = %s
                  AND locked_until IS NOT NULL
                  AND locked_until <= now();
                """,
                (user_id,),
            )
            conn.commit()