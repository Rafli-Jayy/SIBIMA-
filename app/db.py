
"""Koneksi PostgreSQL SIBIMA menggunakan satu connection pool bersama."""

from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

from app.ui.console import gagal, info, sukses
from app.config import DB_CONFIG, DB_TARGET


# Nama variabel .env berdasarkan database yang dipilih.
_PREFIX = "SUPABASE_DB" if DB_TARGET == "supabase" else "DB"

_NAMA_ENV = {
    "host": f"{_PREFIX}_HOST",
    "port": f"{_PREFIX}_PORT",
    "dbname": f"{_PREFIX}_NAME",
    "user": f"{_PREFIX}_USER",
    "password": f"{_PREFIX}_PASSWORD",
}

_kurang = [
    env_name
    for key, env_name in _NAMA_ENV.items()
    if not DB_CONFIG.get(key)
]

if _kurang:
    raise RuntimeError(
        f"Konfigurasi database '{DB_TARGET}' belum lengkap: "
        + ", ".join(_kurang)
        + ". Periksa file .env."
    )


# make_conninfo menangani karakter khusus di username/password.
conninfo = make_conninfo(
    **{
        key: value
        for key, value in DB_CONFIG.items()
        if value is not None and value != ""
    }
)


def konfigurasi_koneksi(conn) -> None:
    """Mengatur timezone untuk setiap koneksi baru dalam pool."""
    conn.execute("SET TIME ZONE 'Asia/Jakarta'")
    conn.commit()


# Satu pool bersama untuk seluruh repository SIBIMA.
pool = ConnectionPool(
    conninfo=conninfo,
    configure=konfigurasi_koneksi,
    min_size=1,
    max_size=5,
    open=True,
)

_pool_ditutup = False


def tes_koneksi() -> bool:
    """Menguji koneksi PostgreSQL aktif."""

    try:
        info(f"Database aktif: {DB_TARGET.upper()}")
        info("Mencoba menghubungi PostgreSQL...")

        with pool.connection(timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        current_database(),
                        current_setting('server_version'),
                        current_setting('TimeZone')
                    """
                )
                nama_db, versi, timezone = cur.fetchone()

        sukses("Koneksi database berhasil.")
        info(f"Target  : {DB_TARGET.upper()}")
        info(f"Database: {nama_db}")
        info(f"Server  : PostgreSQL {versi}")
        info(f"Timezone: {timezone}")

        return True

    except Exception as exc:
        gagal(f"Koneksi database gagal ({type(exc).__name__}).")
        info(
            f"Periksa konfigurasi database '{DB_TARGET}' "
            "di file .env dan koneksi jaringan."
        )
        info(f"Detail error: {exc}")
        return False


def tutup_pool() -> None:
    """Menutup connection pool ketika program selesai."""
    global _pool_ditutup

    if not _pool_ditutup:
        pool.close()
        _pool_ditutup = True


if __name__ == "__main__":
    try:
        tes_koneksi()
    finally:
        tutup_pool()
