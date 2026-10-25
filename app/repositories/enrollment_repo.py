"""Repository untuk pendaftaran program bimbel."""

from psycopg.rows import dict_row

from app.db import pool


STATUS_ENROLLMENT_VALID = {
    "menunggu",
    "aktif",
    "ditolak",
    "batal",
    "selesai",
}


def kunci_program(cur, program_id: int):
    """Kunci baris program selama transaksi pendaftaran berlangsung."""
    cur.execute(
        """
        SELECT id, kode, nama, status, kuota
        FROM programs
        WHERE id = %s
        FOR UPDATE;
        """,
        (program_id,),
    )
    return cur.fetchone()


def hitung_terisi(program_id: int, cur=None) -> int:
    """Hitung kuota terpakai dari enrollment menunggu/aktif.

    Cursor opsional menjaga hitung kuota berjalan pada transaksi yang sama
    dengan penguncian program. Mendukung dict_row dan cursor tuple biasa.
    """
    query = """
        SELECT COUNT(*) AS jumlah
        FROM enrollments
        WHERE program_id = %s
          AND status IN ('menunggu', 'aktif');
    """

    if cur is not None:
        cur.execute(query, (program_id,))
        hasil = cur.fetchone()
        if isinstance(hasil, dict):
            return hasil["jumlah"]
        return hasil[0]

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, (program_id,))
            hasil = cursor.fetchone()
            return hasil["jumlah"]


def buat_enrollment(student_id: int, program_id: int):
    """Buat pendaftaran dengan kunci baris untuk melindungi kuota."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT user_id FROM students WHERE user_id = %s;",
                (student_id,),
            )
            if cur.fetchone() is None:
                return {"berhasil": False, "alasan": "siswa_tidak_ditemukan"}

            program = kunci_program(cur, program_id)
            if program is None:
                return {"berhasil": False, "alasan": "program_tidak_ditemukan"}

            cur.execute(
                """
                SELECT id, status
                FROM enrollments
                WHERE student_id = %s AND program_id = %s;
                """,
                (student_id, program_id),
            )
            existing = cur.fetchone()
            if existing is not None:
                return {
                    "berhasil": False,
                    "alasan": "sudah_terdaftar",
                    "enrollment_id": existing["id"],
                    "status": existing["status"],
                }

            if program["status"] != "buka":
                return {"berhasil": False, "alasan": "program_tutup"}

            terisi = hitung_terisi(program_id, cur)
            if terisi >= program["kuota"]:
                return {"berhasil": False, "alasan": "kuota_penuh"}

            cur.execute(
                """
                INSERT INTO enrollments (student_id, program_id, status)
                VALUES (%s, %s, 'menunggu')
                RETURNING id, status;
                """,
                (student_id, program_id),
            )
            hasil = cur.fetchone()

        conn.commit()

    return {
        "berhasil": True,
        "enrollment_id": hasil["id"],
        "status": hasil["status"],
    }


def daftar_menunggu():
    """Ambil antrean enrollment yang menunggu keputusan admin."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    e.id AS enrollment_id,
                    e.student_id,
                    u.nama_lengkap AS nama_siswa,
                    u.username,
                    u.email,
                    s.nis,
                    e.program_id,
                    p.kode AS kode_program,
                    p.nama AS nama_program,
                    p.harga_bulanan,
                    e.status,
                    e.created_at
                FROM enrollments AS e
                JOIN students AS s ON s.user_id = e.student_id
                JOIN users AS u ON u.id = s.user_id
                JOIN programs AS p ON p.id = e.program_id
                WHERE e.status = 'menunggu'
                ORDER BY e.created_at ASC, e.id ASC;
                """
            )
            return cur.fetchall()


def set_status(
    enrollment_id: int,
    status: str,
    processed_by: int | None = None,
    alasan_tolak: str | None = None,
) -> bool:
    """Memperbarui status enrollment; transisi bersyarat tersedia terpisah."""
    if status not in STATUS_ENROLLMENT_VALID:
        raise ValueError("Status enrollment tidak valid.")

    if status == "ditolak" and not (
        isinstance(alasan_tolak, str) and alasan_tolak.strip()
    ):
        raise ValueError("Alasan penolakan wajib diisi.")

    alasan = (
        alasan_tolak.strip()
        if status == "ditolak" and alasan_tolak
        else None
    )

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE enrollments
                SET status = %s,
                    processed_by = %s,
                    processed_at = CASE
                        WHEN %s THEN now()
                        ELSE NULL
                    END,
                    alasan_tolak = %s
                WHERE id = %s
                RETURNING id;
                """,
                (
                    status,
                    processed_by,
                    processed_by is not None,
                    alasan,
                    enrollment_id,
                ),
            )
            ditemukan = cur.fetchone() is not None
        conn.commit()

    return ditemukan


def enrollment_siswa(student_id: int):
    """Ambil riwayat pendaftaran siswa berdasarkan user ID siswa."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    e.id AS enrollment_id,
                    e.student_id,
                    e.program_id,
                    p.kode AS kode_program,
                    p.nama AS nama_program,
                    p.jenjang,
                    p.deskripsi,
                    p.harga_bulanan,
                    e.status,
                    e.alasan_tolak,
                    e.created_at,
                    e.processed_at
                FROM enrollments AS e
                JOIN programs AS p ON p.id = e.program_id
                WHERE e.student_id = %s
                ORDER BY e.created_at DESC, e.id DESC;
                """,
                (student_id,),
            )
            return cur.fetchall()


def siswa_aktif_di_program(program_id: int):
    """Ambil daftar siswa dengan enrollment aktif di suatu program."""
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    e.id AS enrollment_id,
                    s.user_id AS student_id,
                    s.nis,
                    u.username,
                    u.nama_lengkap,
                    u.email,
                    s.jenjang,
                    s.sekolah,
                    e.created_at
                FROM enrollments AS e
                JOIN students AS s ON s.user_id = e.student_id
                JOIN users AS u ON u.id = s.user_id
                WHERE e.program_id = %s
                  AND e.status = 'aktif'
                ORDER BY u.nama_lengkap, s.user_id;
                """,
                (program_id,),
            )
            return cur.fetchall()


def batalkan_milik_siswa(enrollment_id: int, student_id: int) -> bool:
    """Batalkan enrollment hanya jika pemilik cocok dan status masih menunggu."""
    if type(enrollment_id) is not int or enrollment_id <= 0:
        return False
    if type(student_id) is not int or student_id <= 0:
        return False

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE enrollments
                SET status = 'batal'
                WHERE id = %s
                  AND student_id = %s
                  AND status = 'menunggu'
                RETURNING id;
                """,
                (enrollment_id, student_id),
            )
            berhasil = cur.fetchone() is not None
        conn.commit()

    return berhasil



def proses_keputusan_admin(
    enrollment_id: int,
    processed_by: int,
    keputusan: str,
    alasan_tolak: str | None = None,
) -> dict:
    """Setujui/tolak enrollment; persetujuan membuat tagihan pertama atomik.

    Periode invoice adalah bulan kalender saat admin menyetujui. Jatuh tempo
    default adalah 7 hari kalender dari tanggal persetujuan. Enrollment gratis
    diaktifkan tanpa invoice karena constraint schema menolak invoice jumlah 0.
    """
    if type(enrollment_id) is not int or enrollment_id <= 0:
        raise ValueError("ID pendaftaran tidak valid.")
    if type(processed_by) is not int or processed_by <= 0:
        raise ValueError("ID administrator tidak valid.")
    if keputusan not in {"disetujui", "ditolak"}:
        raise ValueError("Keputusan harus 'disetujui' atau 'ditolak'.")

    alasan = alasan_tolak.strip() if isinstance(alasan_tolak, str) else ""
    if keputusan == "ditolak" and not alasan:
        raise ValueError("Alasan penolakan wajib diisi.")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Kunci enrollment dan program; proses ganda akan menunggu dan
            # kemudian melihat status terbaru setelah transaksi pertama selesai.
            cur.execute(
                """
                SELECT
                    e.id AS enrollment_id,
                    e.student_id,
                    e.program_id,
                    e.status,
                    p.nama AS nama_program,
                    p.harga_bulanan
                FROM enrollments AS e
                JOIN programs AS p ON p.id = e.program_id
                WHERE e.id = %s
                FOR UPDATE OF e, p;
                """,
                (enrollment_id,),
            )
            enrollment = cur.fetchone()
            if enrollment is None:
                return {"berhasil": False, "pesan": "Pendaftaran tidak ditemukan."}
            if enrollment["status"] != "menunggu":
                return {
                    "berhasil": False,
                    "pesan": "Pendaftaran sudah diproses atau tidak lagi menunggu.",
                }

            if keputusan == "ditolak":
                cur.execute(
                    """
                    UPDATE enrollments
                    SET status = 'ditolak',
                        processed_by = %s,
                        processed_at = now(),
                        alasan_tolak = %s
                    WHERE id = %s
                      AND status = 'menunggu'
                    RETURNING id;
                    """,
                    (processed_by, alasan, enrollment_id),
                )
                if cur.fetchone() is None:
                    return {
                        "berhasil": False,
                        "pesan": "Pendaftaran sudah diproses oleh admin lain.",
                    }
                hasil = {
                    "berhasil": True,
                    "keputusan": "ditolak",
                    "enrollment_id": enrollment_id,
                    "student_id": enrollment["student_id"],
                    "program_id": enrollment["program_id"],
                    "nama_program": enrollment["nama_program"],
                    "harga_bulanan": enrollment["harga_bulanan"],
                    "alasan_tolak": alasan,
                    "invoice": None,
                }
            else:
                cur.execute(
                    """
                    UPDATE enrollments
                    SET status = 'aktif',
                        processed_by = %s,
                        processed_at = now(),
                        alasan_tolak = NULL
                    WHERE id = %s
                      AND status = 'menunggu'
                    RETURNING id;
                    """,
                    (processed_by, enrollment_id),
                )
                if cur.fetchone() is None:
                    return {
                        "berhasil": False,
                        "pesan": "Pendaftaran sudah diproses oleh admin lain.",
                    }

                invoice = None
                jumlah = enrollment["harga_bulanan"]
                if jumlah > 0:
                    # Unik enrollment + periode mencegah invoice pertama ganda.
                    cur.execute(
                        """
                        INSERT INTO invoices (
                            enrollment_id, periode, jumlah,
                            diskon_persen, jatuh_tempo, status
                        )
                        VALUES (
                            %s,
                            date_trunc('month', CURRENT_DATE)::date,
                            %s,
                            0,
                            CURRENT_DATE + 7,
                            'belum_dibayar'
                        )
                        ON CONFLICT (enrollment_id, periode) DO NOTHING
                        RETURNING id, no_invoice, periode, jumlah,
                                  diskon_persen, jatuh_tempo, status;
                        """,
                        (enrollment_id, jumlah),
                    )
                    invoice = cur.fetchone()
                    if invoice is None:
                        cur.execute(
                            """
                            SELECT id, no_invoice, periode, jumlah,
                                   diskon_persen, jatuh_tempo, status
                            FROM invoices
                            WHERE enrollment_id = %s
                              AND periode = date_trunc('month', CURRENT_DATE)::date;
                            """,
                            (enrollment_id,),
                        )
                        invoice = cur.fetchone()
                    if invoice is None:
                        # Exception membatalkan update enrollment di transaksi ini.
                        raise RuntimeError(
                            "Invoice pertama tidak dapat dibuat atau ditemukan."
                        )

                hasil = {
                    "berhasil": True,
                    "keputusan": "disetujui",
                    "enrollment_id": enrollment_id,
                    "student_id": enrollment["student_id"],
                    "program_id": enrollment["program_id"],
                    "nama_program": enrollment["nama_program"],
                    "harga_bulanan": jumlah,
                    "invoice": invoice,
                }
        conn.commit()

    return hasil
