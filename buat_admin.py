"""Membuat admin pertama SIBIMA. Jalankan: python buat_admin.py"""

from getpass import getpass

import psycopg

from app.db import pool, tutup_pool
from app.utils.exceptions import DataTidakValid
from app.utils.security import hash_password
from app.utils.validators import validasi_email, validasi_password, validasi_username


BATAS_NAMA = 100


def main() -> int:
    """Membuat satu akun admin awal jika belum ada admin di database."""
    try:
        print("=" * 56)
        print("          SIBIMA KECE - ADMIN PERTAMA")
        print("=" * 56)
        print("Gunakan skrip ini hanya untuk inisialisasi admin pertama.\n")

        username_input = input("Username admin: ").strip()
        email_input = input("Email admin: ").strip()
        nama = input("Nama lengkap: ").strip()
        password = getpass("Password admin (tidak ditampilkan): ")
        konfirmasi = getpass("Ulangi password admin: ")

        try:
            username = validasi_username(username_input)
            email = validasi_email(email_input)
            password = validasi_password(password)
        except DataTidakValid as exc:
            print(f"Input tidak valid: {exc}")
            return 1

        if not nama:
            print("Nama lengkap wajib diisi.")
            return 1
        if len(nama) > BATAS_NAMA:
            print(f"Nama lengkap maksimal {BATAS_NAMA} karakter.")
            return 1
        if password != konfirmasi:
            print("Konfirmasi password tidak cocok.")
            return 1

        try:
            password_hash = hash_password(password)
        except ValueError as exc:
            print(f"Password tidak dapat diproses: {exc}")
            return 1

        with pool.connection(timeout=10) as conn:
            with conn.cursor() as cur:
                # Mencegah dua proses inisialisasi membuat admin pertama
                # secara bersamaan. Lock otomatis lepas saat transaksi selesai.
                cur.execute("SELECT pg_advisory_xact_lock(%s, %s);", (731042, 1))

                cur.execute("SELECT EXISTS (SELECT 1 FROM users WHERE role = 'admin');")
                if cur.fetchone()[0]:
                    print("Admin sudah ada. Skrip ini hanya membuat admin pertama.")
                    return 1

                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM users
                        WHERE lower(username) = lower(%s)
                           OR lower(email) = lower(%s)
                    );
                    """,
                    (username, email),
                )
                if cur.fetchone()[0]:
                    print("Username atau email sudah digunakan akun lain.")
                    return 1

                cur.execute(
                    """
                    INSERT INTO users (
                        username, email, nama_lengkap, password_hash,
                        role, status, email_verified
                    )
                    VALUES (%s, %s, %s, %s, 'admin', 'aktif', TRUE)
                    RETURNING id;
                    """,
                    (username, email, nama, password_hash),
                )
                admin_id = cur.fetchone()[0]

        print("\nAdmin pertama berhasil dibuat.")
        print(f"ID admin : {admin_id}")
        print(f"Username : {username}")
        print("Silakan login melalui aplikasi SIBIMA.")
        return 0

    except psycopg.errors.UniqueViolation:
        print("Gagal: username atau email sudah digunakan.")
        return 1
    except psycopg.Error as exc:
        print(f"Kesalahan database ({type(exc).__name__}).")
        print("Pastikan schema.sql sudah dijalankan dan konfigurasi .env benar.")
        print(f"Detail error: {exc}")
        return 1
    except Exception as exc:
        # Menampilkan jenis error tanpa menyamarkan kegagalan sebagai sukses.
        print(f"Proses pembuatan admin gagal ({type(exc).__name__}).")
        print(f"Detail error: {exc}")
        return 1
    finally:
        tutup_pool()


if __name__ == "__main__":
    raise SystemExit(main())
