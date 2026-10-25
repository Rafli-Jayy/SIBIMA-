"""Koneksi PostgreSQL SIBIMA menggunakan satu connection pool bersama."""

from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

from app.config import DB_CONFIG


# Konfigurasi ini wajib tersedia di file .env.
_NAMA_ENV = {
    "dbname": "DB_NAME",
    "user": "DB_USER",
    "password": "DB_PASSWORD",
}
_kurang = [
    env_name
    for key, env_name in _NAMA_ENV.items()
    if not DB_CONFIG.get(key)
]
if _kurang:
    raise RuntimeError(
        "Konfigurasi database belum lengkap: "
        + ", ".join(_kurang)
        + ". Salin .env.example menjadi .env dan isi nilainya."
    )

# make_conninfo menangani karakter khusus pada nama pengguna/password.
# Host dan port tetap menggunakan default dari app.config jika tidak diubah.
conninfo = make_conninfo(
    **{
        key: value
        for key, value in DB_CONFIG.items()
        if value is not None and value != ""
    }
)

# Pool hanya dibuat satu kali. Repository yang mengimpor `pool` memakai
# objek yang sama selama aplikasi berjalan.
pool = ConnectionPool(
    conninfo=conninfo,
    kwargs={"options": "-c timezone=Asia/Jakarta"},
    min_size=1,
    max_size=5,
    open=True,
)
_pool_ditutup = False


def tes_koneksi() -> bool:
    """Menguji koneksi PostgreSQL dan menampilkan hasilnya di terminal."""
    from app.ui.console import gagal, info, sukses

    try:
        info("Mencoba menghubungi PostgreSQL...")
        with pool.connection(timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                versi = cur.fetchone()[0]

        sukses("Koneksi database berhasil.")
        info(f"Server: {versi}")
        return True
    except Exception as exc:
        gagal(f"Koneksi database gagal ({type(exc).__name__}).")
        info(
            "Periksa apakah PostgreSQL aktif, database dan pengguna sudah "
            "dibuat, serta nilai DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD "
            "di .env sudah benar."
        )
        info(f"Detail error: {exc}")
        return False


def tutup_pool() -> None:
    """Menutup connection pool ketika program benar-benar selesai."""
    global _pool_ditutup

    if not _pool_ditutup:
        pool.close()
        _pool_ditutup = True


if __name__ == "__main__":
    try:
        tes_koneksi()
    finally:
        tutup_pool()
