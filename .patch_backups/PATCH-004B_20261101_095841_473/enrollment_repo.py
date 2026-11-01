"""Repository untuk pendaftaran program bimbel."""

from psycopg.rows import dict_row

from app.db import pool
from app.repositories.billing_repo import buat_invoice_awal


STATUS_ENROLLMENT_VALID = {
    "menunggu_pembayaran",
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
        SELECT id, kode, nama, status, kuota, harga_bulanan
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
          AND status IN ('menunggu_pembayaran', 'menunggu', 'aktif');
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
                """
                SELECT s.user_id, u.nama_lengkap, u.email, s.nis
                FROM students s JOIN users u ON u.id = s.user_id
                WHERE s.user_id = %s;
                """,
                (student_id,),
            )
            siswa = cur.fetchone()
            if siswa is None:
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

            status_awal = "menunggu_pembayaran" if program.get("harga_bulanan", 0) > 0 else "menunggu"
            cur.execute(
                """
                INSERT INTO enrollments (student_id, program_id, status)
                VALUES (%s, %s, %s)
                RETURNING id, status;
                """,
                (student_id, program_id, status_awal),
            )
            hasil = cur.fetchone()
            invoice = None
            if program.get("harga_bulanan", 0) > 0:
                invoice = buat_invoice_awal(
                    cur=cur,
                    enrollment_id=hasil["id"],
                    jumlah=program["harga_bulanan"],
                )

        conn.commit()

    return {
        "berhasil": True,
        "enrollment_id": hasil["id"],
        "status": hasil["status"],
        "invoice": invoice,
        "student_name": siswa["nama_lengkap"],
        "student_email": siswa["email"],
        "student_nis": siswa["nis"],
        "program_name": program["nama"],
        "program_code": program["kode"],
        "program_fee": program.get("harga_bulanan", 0),
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
                    e.created_at,
                    inv.no_invoice,
                    inv.jumlah AS invoice_jumlah,
                    inv.status AS invoice_status,
                    lp.payment_status,
                    lp.paid_at
                FROM enrollments AS e
                JOIN students AS s ON s.user_id = e.student_id
                JOIN users AS u ON u.id = s.user_id
                JOIN programs AS p ON p.id = e.program_id
                LEFT JOIN LATERAL (
                    SELECT i.no_invoice, i.jumlah, i.status
                    FROM invoices i WHERE i.enrollment_id = e.id
                    ORDER BY i.created_at DESC, i.id DESC LIMIT 1
                ) inv ON TRUE
                LEFT JOIN LATERAL (
                    SELECT pay.status AS payment_status, pay.paid_at
                    FROM payments pay JOIN invoices i ON i.id = pay.invoice_id
                    WHERE i.enrollment_id = e.id
                    ORDER BY pay.created_at DESC, pay.id DESC LIMIT 1
                ) lp ON TRUE
                WHERE e.status = 'menunggu'
                  AND u.status = 'aktif'
                  AND (p.harga_bulanan = 0 OR inv.status = 'lunas')
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
                  AND status IN ('menunggu_pembayaran', 'menunggu')
                  AND NOT EXISTS (
                      SELECT 1 FROM invoices i
                      WHERE i.enrollment_id = enrollments.id AND i.status = 'lunas'
                  )
                RETURNING id;
                """,
                (enrollment_id, student_id),
            )
            berhasil = cur.fetchone() is not None
            if berhasil:
                cur.execute(
                    """
                    UPDATE payments pay SET status = 'gagal'
                    FROM invoices i
                    WHERE pay.invoice_id = i.id
                      AND i.enrollment_id = %s
                      AND pay.status IN ('menunggu_pembayaran', 'menunggu_konfirmasi');
                    """,
                    (enrollment_id,),
                )
                cur.execute(
                    "UPDATE invoices SET status = 'batal' WHERE enrollment_id = %s AND status = 'belum_dibayar';",
                    (enrollment_id,),
                )
        conn.commit()

    return berhasil



def proses_keputusan_admin(
    enrollment_id: int,
    processed_by: int,
    keputusan: str,
    alasan_tolak: str | None = None,
) -> dict:
    """Putuskan pendaftaran; refund simulasi dibuat atomik saat penolakan."""
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
            cur.execute(
                """
                SELECT e.id, e.student_id, e.program_id, e.status,
                       p.nama AS nama_program, p.harga_bulanan
                FROM enrollments e JOIN programs p ON p.id = e.program_id
                WHERE e.id = %s FOR UPDATE OF e;
                """,
                (enrollment_id,),
            )
            enrollment = cur.fetchone()
            if enrollment is None:
                return {"berhasil": False, "pesan": "Pendaftaran tidak ditemukan."}
            if enrollment["status"] != "menunggu":
                return {"berhasil": False, "pesan": "Pendaftaran belum siap diputuskan atau sudah diproses."}

            cur.execute(
                """
                SELECT i.id AS invoice_id, i.no_invoice, i.jumlah, i.status AS invoice_status,
                       pay.id AS payment_id, pay.kode_bayar, pay.jumlah AS payment_jumlah,
                       pay.status AS payment_status
                FROM invoices i
                LEFT JOIN LATERAL (
                    SELECT p.id, p.kode_bayar, p.jumlah, p.status
                    FROM payments p WHERE p.invoice_id = i.id
                    ORDER BY p.created_at DESC, p.id DESC LIMIT 1
                ) pay ON TRUE
                WHERE i.enrollment_id = %s
                ORDER BY i.created_at ASC, i.id ASC
                FOR UPDATE OF i;
                """,
                (enrollment_id,),
            )
            invoices = cur.fetchall()
            paid = [x for x in invoices if x["invoice_status"] == "lunas" and x["payment_status"] == "lunas"]
            if keputusan == "disetujui" and enrollment["harga_bulanan"] > 0 and not paid:
                return {"berhasil": False, "pesan": "Pembayaran belum lunas. Pendaftaran belum dapat disetujui."}
            if keputusan == "ditolak":
                refund_rows = []
                for invoice in paid:
                    if invoice["payment_id"] is None:
                        continue
                    kode_refund = f"RF-{invoice['no_invoice']}"
                    cur.execute(
                        """
                        INSERT INTO payment_refunds (payment_id, kode_refund, jumlah, alasan, status)
                        VALUES (%s, %s, %s, %s, 'berhasil')
                        ON CONFLICT (payment_id) DO NOTHING
                        RETURNING id, kode_refund, jumlah, status, created_at, processed_at;
                        """,
                        (invoice["payment_id"], kode_refund, invoice["payment_jumlah"], alasan),
                    )
                    refund = cur.fetchone()
                    if refund is None:
                        cur.execute(
                            "SELECT id, kode_refund, jumlah, status, created_at, processed_at FROM payment_refunds WHERE payment_id = %s;",
                            (invoice["payment_id"],),
                        )
                        refund = cur.fetchone()
                    cur.execute("UPDATE payments SET status = 'direfund' WHERE id = %s;", (invoice["payment_id"],))
                    cur.execute("UPDATE invoices SET status = 'batal' WHERE id = %s;", (invoice["invoice_id"],))
                    refund_rows.append({**refund, "no_invoice": invoice["no_invoice"]})
                cur.execute(
                    """UPDATE enrollments SET status = 'ditolak', processed_by = %s,
                       processed_at = now(), alasan_tolak = %s WHERE id = %s AND status = 'menunggu'
                       RETURNING id;""",
                    (processed_by, alasan, enrollment_id),
                )
                if cur.fetchone() is None:
                    raise RuntimeError("Pendaftaran berubah saat keputusan diproses.")
                cur.execute(
                    "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, %s, %s);",
                    (processed_by, "ENROLLMENT_TOLAK", f"Admin menolak pendaftaran {enrollment_id} ({enrollment['nama_program']}). Refund simulasi: {len(refund_rows)}."),
                )
                hasil = {
                    "berhasil": True, "keputusan": "ditolak", "enrollment_id": enrollment_id,
                    "student_id": enrollment["student_id"], "program_id": enrollment["program_id"],
                    "nama_program": enrollment["nama_program"], "harga_bulanan": enrollment["harga_bulanan"],
                    "alasan_tolak": alasan, "refunds": refund_rows,
                }
            else:
                cur.execute(
                    """UPDATE enrollments SET status = 'aktif', processed_by = %s,
                       processed_at = now(), alasan_tolak = NULL WHERE id = %s AND status = 'menunggu'
                       RETURNING id;""",
                    (processed_by, enrollment_id),
                )
                if cur.fetchone() is None:
                    raise RuntimeError("Pendaftaran berubah saat keputusan diproses.")
                cur.execute(
                    "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, %s, %s);",
                    (processed_by, "ENROLLMENT_SETUJU", f"Admin menyetujui pendaftaran {enrollment_id} ({enrollment['nama_program']})."),
                )
                hasil = {
                    "berhasil": True, "keputusan": "disetujui", "enrollment_id": enrollment_id,
                    "student_id": enrollment["student_id"], "program_id": enrollment["program_id"],
                    "nama_program": enrollment["nama_program"], "harga_bulanan": enrollment["harga_bulanan"],
                    "invoice": paid[0] if paid else None, "refunds": [],
                }
        conn.commit()
    return hasil


def daftar_admin(status: str | None = None, program_id: int | None = None):
    """Daftar pendaftaran untuk admin dengan filter status/program opsional."""
    if status is not None and status not in STATUS_ENROLLMENT_VALID:
        raise ValueError("Filter status pendaftaran tidak valid.")
    if program_id is not None and (type(program_id) is not int or program_id <= 0):
        raise ValueError("Filter program tidak valid.")

    where = []
    params = []
    if status is not None:
        where.append("e.status = %s::enrollment_status")
        params.append(status)
    if program_id is not None:
        where.append("e.program_id = %s")
        params.append(program_id)
    klausa = "WHERE " + " AND ".join(where) if where else ""

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT
                    e.id AS enrollment_id,
                    e.student_id,
                    s.nis,
                    u.nama_lengkap AS nama_siswa,
                    u.username,
                    u.email,
                    e.program_id,
                    p.kode AS kode_program,
                    p.nama AS nama_program,
                    p.jenjang,
                    p.harga_bulanan,
                    e.status,
                    e.alasan_tolak,
                    e.processed_by,
                    e.processed_at,
                    e.created_at,
                    (SELECT COUNT(*) FROM invoices i
                     WHERE i.enrollment_id = e.id) AS jumlah_tagihan
                FROM enrollments AS e
                JOIN students AS s ON s.user_id = e.student_id
                JOIN users AS u ON u.id = s.user_id
                JOIN programs AS p ON p.id = e.program_id
                {klausa}
                ORDER BY e.created_at DESC, e.id DESC;
                """,
                params,
            )
            return cur.fetchall()


def detail_admin(enrollment_id: int):
    """Ambil detail pendaftaran berikut ringkasan tagihan tanpa menggandakan SUM."""
    if type(enrollment_id) is not int or enrollment_id <= 0:
        return None
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    e.id AS enrollment_id,
                    e.student_id,
                    s.nis,
                    u.nama_lengkap AS nama_siswa,
                    u.username,
                    u.email,
                    u.status AS status_akun,
                    e.program_id,
                    p.kode AS kode_program,
                    p.nama AS nama_program,
                    p.jenjang,
                    p.harga_bulanan,
                    e.status,
                    e.alasan_tolak,
                    e.processed_by,
                    admin.nama_lengkap AS diproses_oleh,
                    e.processed_at,
                    e.created_at,
                    (SELECT COUNT(*) FROM invoices i
                     WHERE i.enrollment_id = e.id) AS jumlah_tagihan,
                    (SELECT COALESCE(SUM(i.jumlah), 0) FROM invoices i
                     WHERE i.enrollment_id = e.id AND i.status <> 'batal') AS total_tagihan,
                    (SELECT COALESCE(SUM(pmt.jumlah), 0)
                     FROM payments pmt JOIN invoices i ON i.id = pmt.invoice_id
                     WHERE i.enrollment_id = e.id AND pmt.status = 'lunas') AS total_terbayar
                FROM enrollments AS e
                JOIN students AS s ON s.user_id = e.student_id
                JOIN users AS u ON u.id = s.user_id
                JOIN programs AS p ON p.id = e.program_id
                LEFT JOIN users AS admin ON admin.id = e.processed_by
                WHERE e.id = %s;
                """,
                (enrollment_id,),
            )
            return cur.fetchone()


def pindahkan_admin(
    enrollment_id: int,
    program_tujuan_id: int,
    processed_by: int,
) -> dict:
    """Pindahkan enrollment aktif tanpa memindahkan riwayat invoice ke program baru.

    Enrollment lama dipertahankan sebagai selesai. Enrollment baru menjadi aktif.
    Tagihan periode berjalan yang belum lunas dibatalkan dan dibuat ulang untuk
    program tujuan. Jika periode berjalan sudah lunas, tagihan lama dipertahankan
    dan tidak dibuat tagihan kedua pada bulan yang sama.
    """
    if type(enrollment_id) is not int or enrollment_id <= 0:
        raise ValueError("ID pendaftaran tidak valid.")
    if type(program_tujuan_id) is not int or program_tujuan_id <= 0:
        raise ValueError("Program tujuan tidak valid.")
    if type(processed_by) is not int or processed_by <= 0:
        raise ValueError("ID administrator tidak valid.")

    from app.repositories.billing_repo import buat_invoice_awal

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT e.id, e.student_id, e.program_id, e.status,
                       p.nama AS nama_program_asal
                FROM enrollments e
                JOIN programs p ON p.id = e.program_id
                WHERE e.id = %s
                FOR UPDATE OF e;
                """,
                (enrollment_id,),
            )
            asal = cur.fetchone()
            if asal is None:
                return {"berhasil": False, "pesan": "Pendaftaran asal tidak ditemukan."}
            if asal["status"] != "aktif":
                return {
                    "berhasil": False,
                    "pesan": "Hanya pendaftaran berstatus aktif yang dapat dipindahkan.",
                }
            if asal["program_id"] == program_tujuan_id:
                return {"berhasil": False, "pesan": "Siswa sudah berada di program tersebut."}

            cur.execute(
                """
                SELECT id, kode, nama, status, kuota, harga_bulanan
                FROM programs WHERE id = %s FOR UPDATE;
                """,
                (program_tujuan_id,),
            )
            tujuan = cur.fetchone()
            if tujuan is None:
                return {"berhasil": False, "pesan": "Program tujuan tidak ditemukan."}
            if tujuan["status"] != "buka":
                return {"berhasil": False, "pesan": "Program tujuan sedang ditutup."}

            cur.execute(
                """
                SELECT COUNT(*) AS jumlah FROM enrollments
                WHERE program_id = %s AND status IN ('menunggu_pembayaran', 'menunggu', 'aktif');
                """,
                (program_tujuan_id,),
            )
            terisi = cur.fetchone()["jumlah"]
            if terisi >= tujuan["kuota"]:
                return {"berhasil": False, "pesan": "Kuota program tujuan sudah penuh."}

            cur.execute(
                """
                SELECT id, status FROM enrollments
                WHERE student_id = %s AND program_id = %s;
                """,
                (asal["student_id"], program_tujuan_id),
            )
            if cur.fetchone() is not None:
                return {
                    "berhasil": False,
                    "pesan": (
                        "Siswa sudah memiliki riwayat pendaftaran pada program tujuan. "
                        "Pemindahan dibatalkan agar riwayat tidak tertimpa."
                    ),
                }

            cur.execute(
                """
                SELECT id, status FROM invoices
                WHERE enrollment_id = %s
                  AND periode = date_trunc('month', CURRENT_DATE)::date
                FOR UPDATE;
                """,
                (enrollment_id,),
            )
            invoice_berjalan = cur.fetchone()
            periode_sudah_lunas = bool(
                invoice_berjalan and invoice_berjalan["status"] == "lunas"
            )
            if invoice_berjalan is not None and not periode_sudah_lunas:
                cur.execute(
                    """
                    UPDATE payments
                    SET status = 'ditolak',
                        processed_by = %s,
                        processed_at = now(),
                        alasan_tolak = %s
                    WHERE invoice_id = %s
                      AND status IN ('menunggu_pembayaran', 'menunggu_konfirmasi');
                    """,
                    (
                        processed_by,
                        "Tagihan diganti karena pendaftaran dipindahkan oleh admin.",
                        invoice_berjalan["id"],
                    ),
                )
                cur.execute(
                    "UPDATE invoices SET status = 'batal' WHERE id = %s AND status <> 'lunas';",
                    (invoice_berjalan["id"],),
                )

            # Buat enrollment baru agar invoice masa lalu tetap melekat pada program asal.
            cur.execute(
                """
                INSERT INTO enrollments (
                    student_id, program_id, status, processed_by, processed_at
                ) VALUES (%s, %s, 'aktif', %s, now())
                RETURNING id;
                """,
                (asal["student_id"], program_tujuan_id, processed_by),
            )
            enrollment_baru_id = cur.fetchone()["id"]

            cur.execute(
                """
                UPDATE enrollments
                SET status = 'selesai', processed_by = %s, processed_at = now()
                WHERE id = %s AND status = 'aktif';
                """,
                (processed_by, enrollment_id),
            )

            invoice_baru = None
            if not periode_sudah_lunas:
                invoice_baru = buat_invoice_awal(
                    cur, enrollment_baru_id, tujuan["harga_bulanan"]
                )

            cur.execute(
                """
                INSERT INTO activity_logs (user_id, aksi, detail)
                VALUES (%s, 'ENROLLMENT_DIPINDAHKAN', %s);
                """,
                (
                    processed_by,
                    f"Enrollment {enrollment_id} dari program {asal['program_id']} "
                    f"dipindahkan ke enrollment {enrollment_baru_id} "
                    f"pada program {program_tujuan_id}.",
                ),
            )
        conn.commit()

    if periode_sudah_lunas:
        catatan_tagihan = "Tagihan periode berjalan yang sudah lunas dipertahankan; tidak dibuat tagihan kedua bulan ini."
    elif invoice_baru:
        catatan_tagihan = f"Tagihan baru {invoice_baru['no_invoice']} sebesar Rp {invoice_baru['jumlah']:,.0f} dibuat untuk program tujuan."
    else:
        catatan_tagihan = "Program tujuan gratis, jadi tidak dibuat tagihan baru."
    return {
        "berhasil": True,
        "pesan": (
            f"Siswa berhasil dipindahkan dari {asal['nama_program_asal']} ke "
            f"{tujuan['nama']}. Riwayat tagihan lama tetap tersimpan. {catatan_tagihan}"
        ),
        "enrollment_lama_id": enrollment_id,
        "enrollment_baru_id": enrollment_baru_id,
        "invoice": invoice_baru,
    }


def batalkan_admin(enrollment_id: int, processed_by: int, alasan: str | None = None) -> dict:
    """Batalkan pendaftaran menunggu/aktif tanpa menghapus riwayat tagihan."""
    if type(enrollment_id) is not int or enrollment_id <= 0:
        raise ValueError("ID pendaftaran tidak valid.")
    if type(processed_by) is not int or processed_by <= 0:
        raise ValueError("ID administrator tidak valid.")
    alasan = alasan.strip() if isinstance(alasan, str) else ""

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT e.id, e.student_id, e.program_id, e.status,
                       p.nama AS nama_program
                FROM enrollments e JOIN programs p ON p.id = e.program_id
                WHERE e.id = %s FOR UPDATE OF e;
                """,
                (enrollment_id,),
            )
            enrollment = cur.fetchone()
            if enrollment is None:
                return {"berhasil": False, "pesan": "Pendaftaran tidak ditemukan."}
            if enrollment["status"] not in {"menunggu", "aktif"}:
                return {
                    "berhasil": False,
                    "pesan": "Hanya pendaftaran menunggu atau aktif yang dapat dibatalkan.",
                }

            cur.execute(
                """
                UPDATE enrollments
                SET status = 'batal', processed_by = %s, processed_at = now()
                WHERE id = %s AND status IN ('menunggu_pembayaran', 'menunggu', 'aktif')
                RETURNING id;
                """,
                (processed_by, enrollment_id),
            )
            if cur.fetchone() is None:
                return {"berhasil": False, "pesan": "Pendaftaran sudah berubah; muat ulang daftar."}

            detail = (
                f"Pendaftaran {enrollment_id} pada program {enrollment['program_id']} "
                f"dibatalkan oleh admin. Alasan: {alasan or 'tidak dicantumkan'}. "
                "Riwayat tagihan tidak dihapus."
            )
            cur.execute(
                "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, 'ENROLLMENT_DIBATALKAN', %s);",
                (processed_by, detail),
            )
        conn.commit()

    return {
        "berhasil": True,
        "pesan": (
            f"Pendaftaran {enrollment['nama_program']} dibatalkan. "
            "Riwayat tagihan tetap dipertahankan untuk audit dan penagihan."
        ),
    }
