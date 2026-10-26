"""Query untuk pengumuman global yang dibuat oleh admin."""

from psycopg.rows import dict_row

from app.db import pool


def _catat_log(cur, user_id: int | None, aksi: str, detail: str) -> None:
    cur.execute(
        "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, %s, %s);",
        (user_id, aksi[:60], detail[:4000]),
    )


def buat_pengumuman(judul: str, isi: str, admin_id: int) -> dict:
    """Menyimpan pengumuman dan log pembuat dalam satu transaksi."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO announcements (judul, isi, dibuat_by)
                VALUES (%s, %s, %s)
                RETURNING id, judul, isi, dibuat_by, created_at;
                """,
                (judul, isi, admin_id),
            )
            pengumuman = cur.fetchone()
            _catat_log(
                cur,
                admin_id,
                "PENGUMUMAN_DIBUAT",
                f"Pengumuman ID {pengumuman['id']} dibuat: {judul[:160]}",
            )
        conn.commit()
    return pengumuman


def daftar_pengumuman(limit: int = 100) -> list[dict]:
    """Daftar pengumuman terbaru beserta nama admin pembuat."""
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas pengumuman tidak valid.")
    limit = min(limit, 500)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.id, a.judul, a.isi, a.created_at, a.dibuat_by,
                       COALESCE(u.nama_lengkap, u.username, 'Admin tidak tersedia') AS nama_pembuat
                FROM announcements AS a
                LEFT JOIN users AS u ON u.id = a.dibuat_by
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()


def pengumuman_terbaru(limit: int = 3) -> list[dict]:
    """Mengambil beberapa pengumuman terbaru untuk dashboard siswa."""
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas pengumuman tidak valid.")
    return daftar_pengumuman(min(limit, 10))
