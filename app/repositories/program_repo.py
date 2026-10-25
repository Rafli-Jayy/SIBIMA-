"""Query tabel programs dan rooms.

Fungsi yang direncanakan:
    - tambah_program
    - ubah_program
    - tutup_program
    - daftar_program
    - daftar_program_buka_dengan_kuota
    - tambah_ruang
    - daftar_ruang
"""


"""Repository untuk program bimbel dan ruang belajar."""

from psycopg.rows import dict_row

from app.db import pool


def tambah_program(
    kode: str,
    nama: str,
    jenjang: str,
    deskripsi: str | None,
    harga_bulanan,
    kuota: int,
    status: str = "buka",
    bobot_tugas: int = 30,
    bobot_kuis: int = 20,
    bobot_uts: int = 20,
    bobot_uas: int = 30,
) -> int:
    """Membuat program baru dan mengembalikan ID-nya."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO programs (
                    kode, nama, jenjang, deskripsi,
                    harga_bulanan, kuota, status,
                    bobot_tugas, bobot_kuis, bobot_uts, bobot_uas
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                RETURNING id;
                """,
                (
                    kode, nama, jenjang, deskripsi,
                    harga_bulanan, kuota, status,
                    bobot_tugas, bobot_kuis, bobot_uts, bobot_uas,
                ),
            )
            program_id = cur.fetchone()[0]

        conn.commit()

    return program_id


def ubah_program(program_id: int, **perubahan) -> bool:
    """Mengubah kolom program yang diberikan melalui keyword argument.

    Contoh:
        ubah_program(1, nama="Matematika Intensif")
        ubah_program(1, harga_bulanan=350000, kuota=25)
        ubah_program(1, status="buka")
        ubah_program(1, deskripsi=None)
    """
    kolom_diizinkan = {
        "kode",
        "nama",
        "jenjang",
        "deskripsi",
        "harga_bulanan",
        "kuota",
        "status",
        "bobot_tugas",
        "bobot_kuis",
        "bobot_uts",
        "bobot_uas",
    }

    if not perubahan:
        raise ValueError("Tidak ada perubahan program yang diberikan.")

    kolom_tidak_valid = set(perubahan) - kolom_diizinkan
    if kolom_tidak_valid:
        raise ValueError(
            "Kolom program tidak diizinkan: "
            + ", ".join(sorted(kolom_tidak_valid))
        )

    # Nama kolom berasal dari whitelist, bukan input SQL bebas.
    set_clause = ", ".join(
        f"{kolom} = %s" for kolom in perubahan
    )
    nilai = list(perubahan.values())

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE programs
                SET {set_clause}
                WHERE id = %s
                RETURNING id;
                """,
                (*nilai, program_id),
            )

            ditemukan = cur.fetchone() is not None

        conn.commit()

    return ditemukan


def tutup_program(program_id: int) -> bool:
    """Menutup program agar tidak menerima pendaftaran baru."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE programs
                SET status = 'tutup'
                WHERE id = %s
                RETURNING id;
                """,
                (program_id,),
            )

            ditemukan = cur.fetchone() is not None

        conn.commit()

    return ditemukan


def daftar_program():
    """Mengambil seluruh program, baik yang buka maupun tutup."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    id, kode, nama, jenjang, deskripsi,
                    harga_bulanan, kuota, status,
                    bobot_tugas, bobot_kuis, bobot_uts, bobot_uas,
                    created_at
                FROM programs
                ORDER BY created_at DESC, id DESC;
                """
            )
            return cur.fetchall()


def daftar_program_buka_dengan_kuota():
    """Mengambil program yang dibuka dan masih mempunyai kuota."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    p.id,
                    p.kode,
                    p.nama,
                    p.jenjang,
                    p.deskripsi,
                    p.harga_bulanan,
                    p.kuota,
                    p.status,
                    p.bobot_tugas,
                    p.bobot_kuis,
                    p.bobot_uts,
                    p.bobot_uas,
                    q.terisi,
                    q.sisa
                FROM programs AS p
                JOIN v_program_kuota AS q
                    ON q.program_id = p.id
                WHERE p.status = 'buka'
                  AND q.sisa > 0
                ORDER BY p.nama, p.id;
                """
            )
            return cur.fetchall()


def tambah_ruang(nama: str, kapasitas: int, aktif: bool = True) -> int:
    """Menambahkan ruang belajar dan mengembalikan ID-nya."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rooms (nama, kapasitas, aktif)
                VALUES (%s, %s, %s)
                RETURNING id;
                """,
                (nama, kapasitas, aktif),
            )
            ruang_id = cur.fetchone()[0]

        conn.commit()

    return ruang_id


def daftar_ruang(hanya_aktif: bool = False):
    """Mengambil daftar ruang, opsional hanya ruang yang aktif."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if hanya_aktif:
                cur.execute(
                    """
                    SELECT id, nama, kapasitas, aktif
                    FROM rooms
                    WHERE aktif = TRUE
                    ORDER BY nama, id;
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT id, nama, kapasitas, aktif
                    FROM rooms
                    ORDER BY nama, id;
                    """
                )

            return cur.fetchall()

