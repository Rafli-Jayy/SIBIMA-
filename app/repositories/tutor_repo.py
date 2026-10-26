"""Repository data profil tutor SIBIMA."""

from psycopg.rows import dict_row

from app.db import pool


def profil(tutor_id: int):
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT u.id, u.username, u.email, u.nama_lengkap, u.status::text AS status_akun,
                   t.kode_tutor, t.keahlian, t.no_hp
            FROM users u JOIN tutors t ON t.user_id = u.id
            WHERE u.id = %s AND u.role = 'tutor';
            """,
            (tutor_id,),
        )
        return cur.fetchone()


def ubah_profil(tutor_id: int, *, keahlian: str | None, no_hp: str | None) -> bool:
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE tutors t SET keahlian = %s, no_hp = %s
            FROM users u
            WHERE t.user_id = %s AND u.id = t.user_id
              AND u.role = 'tutor' AND u.status = 'aktif'
            RETURNING t.user_id;
            """,
            (keahlian, no_hp, tutor_id),
        )
        result = cur.fetchone()
        if result is None:
            conn.rollback()
            return False
        cur.execute(
            "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, 'PROFIL_TUTOR_DIUBAH', %s);",
            (tutor_id, "fields=keahlian,no_hp"),
        )
        conn.commit()
        return True


def catat_aktivitas(tutor_id: int, aksi: str, detail: str | None = None) -> None:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, %s, %s);",
            (tutor_id, aksi, detail),
        )
        conn.commit()
