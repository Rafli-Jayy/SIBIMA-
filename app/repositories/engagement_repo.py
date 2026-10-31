"""Query pengumuman admin dan pembacaan ringkasan pengumuman siswa."""

from psycopg.rows import dict_row

from app.db import pool


_ROLE_LABEL = {"siswa": "Siswa", "tutor": "Tutor"}


def _catat_log(cur, user_id: int | None, aksi: str, detail: str) -> None:
    cur.execute(
        "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, %s, %s);",
        (user_id, aksi[:60], detail[:4000]),
    )


def buat_pengumuman(judul: str, isi: str, admin_id: int, target_roles: list[str]) -> dict:
    """Simpan pengumuman dan target penerimanya dalam satu transaksi."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO announcements (judul, isi, dibuat_by)
                VALUES (%s, %s, %s)
                RETURNING id, judul, isi, dibuat_by, created_at, archived_at;
                """,
                (judul, isi, admin_id),
            )
            pengumuman = cur.fetchone()
            for role in target_roles:
                cur.execute(
                    """
                    INSERT INTO announcement_targets (announcement_id, target_role)
                    VALUES (%s, %s);
                    """,
                    (pengumuman["id"], role),
                )
            _catat_log(
                cur,
                admin_id,
                "PENGUMUMAN_DIBUAT",
                f"Pengumuman ID {pengumuman['id']} dibuat untuk {', '.join(_ROLE_LABEL[r] for r in target_roles)}: {judul[:160]}",
            )
        conn.commit()
    pengumuman["target_roles"] = list(target_roles)
    return pengumuman


def daftar_pengumuman_admin(status: str = "aktif", limit: int = 100) -> list[dict]:
    """Ambil pengumuman aktif atau arsip beserta target dan nama pembuat."""
    if status not in {"aktif", "arsip"}:
        raise ValueError("Status daftar pengumuman tidak valid.")
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas pengumuman tidak valid.")
    limit = min(limit, 500)
    kondisi_arsip = "a.archived_at IS NULL" if status == "aktif" else "a.archived_at IS NOT NULL"
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT a.id, a.judul, a.isi, a.created_at, a.archived_at, a.dibuat_by,
                       COALESCE(u.nama_lengkap, u.username, 'Admin tidak tersedia') AS nama_pembuat,
                       COALESCE(array_agg(at.target_role::text ORDER BY at.target_role)
                           FILTER (WHERE at.target_role IS NOT NULL), ARRAY[]::text[]) AS target_roles
                FROM announcements AS a
                LEFT JOIN users AS u ON u.id = a.dibuat_by
                LEFT JOIN announcement_targets AS at ON at.announcement_id = a.id
                WHERE {kondisi_arsip}
                GROUP BY a.id, u.nama_lengkap, u.username
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()


def detail_pengumuman_admin(announcement_id: int) -> dict | None:
    """Ambil detail satu pengumuman untuk Admin."""
    if type(announcement_id) is not int or announcement_id < 1:
        raise ValueError("ID pengumuman tidak valid.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.id, a.judul, a.isi, a.created_at, a.archived_at, a.dibuat_by,
                       COALESCE(u.nama_lengkap, u.username, 'Admin tidak tersedia') AS nama_pembuat,
                       COALESCE(array_agg(at.target_role::text ORDER BY at.target_role)
                           FILTER (WHERE at.target_role IS NOT NULL), ARRAY[]::text[]) AS target_roles
                FROM announcements AS a
                LEFT JOIN users AS u ON u.id = a.dibuat_by
                LEFT JOIN announcement_targets AS at ON at.announcement_id = a.id
                WHERE a.id = %s
                GROUP BY a.id, u.nama_lengkap, u.username;
                """,
                (announcement_id,),
            )
            return cur.fetchone()


def arsipkan_pengumuman(announcement_id: int, admin_id: int) -> bool:
    """Arsipkan pengumuman aktif. Arsip bersifat satu arah/permanen."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE announcements
                SET archived_at = now()
                WHERE id = %s AND archived_at IS NULL
                RETURNING id, judul;
                """,
                (announcement_id,),
            )
            item = cur.fetchone()
            if item:
                _catat_log(
                    cur,
                    admin_id,
                    "PENGUMUMAN_DIARSIPKAN",
                    f"Pengumuman ID {item['id']} diarsipkan: {item['judul'][:160]}",
                )
        conn.commit()
    return item is not None


def pengumuman_terbaru_siswa(limit: int = 3) -> list[dict]:
    """Kompatibilitas sementara dashboard lama: hanya pengumuman aktif target siswa."""
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas pengumuman tidak valid.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.id, a.judul, a.isi, a.created_at
                FROM announcements AS a
                JOIN announcement_targets AS at ON at.announcement_id = a.id
                WHERE a.archived_at IS NULL AND at.target_role = 'siswa'
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT %s;
                """,
                (min(limit, 10),),
            )
            return cur.fetchall()


def daftar_notifikasi_penerima(user_id: int, role: str, limit: int = 200) -> list[dict]:
    """Ambil pengumuman aktif yang ditujukan ke peran pengguna, dengan status baca pribadi."""
    if role not in {"siswa", "tutor"}:
        raise ValueError("Peran penerima tidak valid.")
    if type(limit) is not int or limit < 1:
        raise ValueError("Batas notifikasi tidak valid.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.id, a.judul, a.isi, a.created_at,
                       r.read_at,
                       (r.announcement_id IS NOT NULL) AS sudah_dibaca
                FROM announcements AS a
                JOIN announcement_targets AS t ON t.announcement_id = a.id
                LEFT JOIN announcement_reads AS r
                  ON r.announcement_id = a.id AND r.user_id = %s
                WHERE a.archived_at IS NULL AND t.target_role = %s
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT %s;
                """,
                (user_id, role, min(limit, 500)),
            )
            return cur.fetchall()


def detail_notifikasi_penerima(user_id: int, role: str, announcement_id: int) -> dict | None:
    """Buka detail notifikasi yang aktif dan sesuai peran; catat baca per pengguna."""
    if role not in {"siswa", "tutor"}:
        raise ValueError("Peran penerima tidak valid.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT a.id, a.judul, a.isi, a.created_at
                FROM announcements AS a
                JOIN announcement_targets AS t ON t.announcement_id = a.id
                WHERE a.id = %s AND a.archived_at IS NULL AND t.target_role = %s;
                """,
                (announcement_id, role),
            )
            item = cur.fetchone()
            if item is None:
                return None
            cur.execute(
                """
                INSERT INTO announcement_reads (announcement_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT (announcement_id, user_id) DO NOTHING;
                """,
                (announcement_id, user_id),
            )
        conn.commit()
    return item
