"""Query untuk pencatatan dan pembacaan activity_logs."""

from psycopg.rows import dict_row

from app.db import pool


def catat(user_id: int | None, aksi: str, detail: str | None = None) -> None:
    """Mencatat aktivitas sederhana di transaksi tersendiri."""
    if not isinstance(aksi, str) or not aksi.strip():
        raise ValueError("Kode aksi log wajib diisi.")
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, %s, %s);",
                (user_id, aksi.strip()[:60], (detail or "")[:4000] or None),
            )
        conn.commit()


def daftar_terbaru(limit: int = 100, pengguna: str | None = None,
                   aksi: str | None = None) -> list[dict]:
    """Membaca log terbaru; filter pengguna menerima ID, username, atau nama."""
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas log tidak valid.")
    limit = min(limit, 500)
    pengguna = pengguna.strip() if isinstance(pengguna, str) else None
    aksi = aksi.strip() if isinstance(aksi, str) else None
    if pengguna and len(pengguna) > 120:
        raise ValueError("Filter pengguna maksimal 120 karakter.")
    if aksi and len(aksi) > 60:
        raise ValueError("Filter aksi maksimal 60 karakter.")

    kondisi = []
    params: list[object] = []
    if pengguna:
        kondisi.append(
            "(CAST(l.user_id AS TEXT) = %s OR u.username ILIKE %s OR u.nama_lengkap ILIKE %s)"
        )
        like = f"%{pengguna}%"
        params.extend([pengguna, like, like])
    if aksi:
        kondisi.append("l.aksi ILIKE %s")
        params.append(f"%{aksi}%")
    where_sql = "WHERE " + " AND ".join(kondisi) if kondisi else ""
    params.append(limit)

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT l.id, l.user_id,
                       COALESCE(u.nama_lengkap, u.username,
                                CASE WHEN l.user_id IS NULL THEN 'Sistem' ELSE 'Akun tidak tersedia' END) AS pengguna,
                       u.username, l.aksi, l.detail, l.created_at
                FROM activity_logs AS l
                LEFT JOIN users AS u ON u.id = l.user_id
                {where_sql}
                ORDER BY l.created_at DESC, l.id DESC
                LIMIT %s;
                """,
                params,
            )
            return cur.fetchall()
