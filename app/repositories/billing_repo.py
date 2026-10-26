"""Repository tagihan dan pembayaran Virtual Account penuh SIBIMA."""

from secrets import token_hex

from psycopg.rows import dict_row

from app.db import pool

STATUS_TAGIHAN = {"belum_dibayar", "lunas", "batal"}
STATUS_PEMBAYARAN = {
    "menunggu_pembayaran",
    "menunggu_konfirmasi",
    "lunas",
    "ditolak",
}


def buat_invoice_awal(cur, enrollment_id: int, jumlah):
    """Buat/ambil tagihan pertama dalam transaksi pemanggil.

    Cursor harus berada dalam transaksi aktif dan menggunakan dict_row.
    Tagihan dengan nominal nol tidak dibuat.
    """
    if type(enrollment_id) is not int or enrollment_id <= 0:
        raise ValueError("ID enrollment tidak valid untuk pembuatan invoice.")
    if jumlah is None or jumlah < 0:
        raise ValueError("Nominal invoice tidak valid.")
    if jumlah == 0:
        return None

    cur.execute(
        """
        INSERT INTO invoices (enrollment_id, periode, jumlah, jatuh_tempo, status)
        VALUES (%s, date_trunc('month', CURRENT_DATE)::date, %s,
                CURRENT_DATE + 7, 'belum_dibayar')
        ON CONFLICT (enrollment_id, periode) DO NOTHING
        RETURNING id, no_invoice, periode, jumlah, jatuh_tempo, status;
        """,
        (enrollment_id, jumlah),
    )
    invoice = cur.fetchone()
    if invoice is not None:
        return invoice

    cur.execute(
        """
        SELECT id, no_invoice, periode, jumlah, jatuh_tempo, status
        FROM invoices
        WHERE enrollment_id = %s
          AND periode = date_trunc('month', CURRENT_DATE)::date
        FOR UPDATE;
        """,
        (enrollment_id,),
    )
    invoice = cur.fetchone()
    if invoice is None:
        raise RuntimeError("Invoice pertama tidak dapat dibuat atau ditemukan.")
    if invoice["jumlah"] != jumlah:
        raise ValueError(
            "Invoice untuk periode ini sudah ada dengan nominal berbeda. "
            "Periksa data tagihan sebelum menyetujui pendaftaran."
        )
    return invoice


def _catat_log(cur, user_id: int | None, aksi: str, detail: str):
    cur.execute(
        "INSERT INTO activity_logs (user_id, aksi, detail) VALUES (%s, %s, %s);",
        (user_id, aksi[:60], detail),
    )


def buat_tagihan_bulanan(admin_id: int) -> int:
    """Buat tagihan bulan berjalan untuk enrollment aktif tanpa invoice bulan ini."""
    if type(admin_id) is not int or admin_id <= 0:
        raise ValueError("ID admin tidak valid.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO invoices (enrollment_id, periode, jumlah, jatuh_tempo, status)
                SELECT e.id,
                       date_trunc('month', CURRENT_DATE)::date,
                       p.harga_bulanan,
                       CURRENT_DATE + 7,
                       'belum_dibayar'
                FROM enrollments AS e
                JOIN programs AS p ON p.id = e.program_id
                WHERE e.status = 'aktif'
                  AND p.harga_bulanan > 0
                ON CONFLICT (enrollment_id, periode) DO NOTHING
                RETURNING id;
                """
            )
            dibuat = len(cur.fetchall())
            _catat_log(
                cur,
                admin_id,
                "BILLING_TAGIHAN_BULANAN",
                f"Admin membuat {dibuat} tagihan untuk periode bulan berjalan.",
            )
        conn.commit()
    return dibuat


def _query_tagihan(status=None, tunggakan=False, student_id=None, limit=300):
    if status is not None and status not in STATUS_TAGIHAN:
        raise ValueError("Filter status tagihan tidak valid.")
    limit = max(1, min(int(limit), 1000))

    conditions = []
    params = []
    if student_id is not None:
        conditions.append("e.student_id = %s")
        params.append(student_id)
    if status is not None:
        conditions.append("i.status = %s")
        params.append(status)
    if tunggakan:
        conditions.append("i.status = 'belum_dibayar' AND i.jatuh_tempo < CURRENT_DATE")

    where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)

    query = f"""
        SELECT i.id AS invoice_id, i.no_invoice, i.periode, i.jumlah,
               i.jatuh_tempo, i.status AS invoice_status, i.created_at AS invoice_created_at,
               e.id AS enrollment_id, e.student_id, e.status AS enrollment_status,
               p.id AS program_id, p.kode AS kode_program, p.nama AS nama_program,
               u.nama_lengkap AS nama_siswa, u.username, u.email, s.nis,
               lp.payment_id, lp.kode_bayar, lp.payment_status,
               lp.payment_jumlah, lp.paid_at
        FROM invoices AS i
        JOIN enrollments AS e ON e.id = i.enrollment_id
        JOIN programs AS p ON p.id = e.program_id
        JOIN students AS s ON s.user_id = e.student_id
        JOIN users AS u ON u.id = e.student_id
        LEFT JOIN LATERAL (
            SELECT pay.id AS payment_id, pay.kode_bayar,
                   pay.status AS payment_status, pay.jumlah AS payment_jumlah,
                   pay.paid_at
            FROM payments AS pay
            WHERE pay.invoice_id = i.id
            ORDER BY pay.created_at DESC, pay.id DESC
            LIMIT 1
        ) AS lp ON TRUE
        {where_sql}
        ORDER BY i.jatuh_tempo ASC, i.created_at DESC, i.id DESC
        LIMIT %s;
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def daftar_tagihan_admin(status=None, tunggakan=False, limit=300):
    return _query_tagihan(status=status, tunggakan=tunggakan, limit=limit)


def daftar_tagihan_siswa(student_id: int, status=None, limit=300):
    if type(student_id) is not int or student_id <= 0:
        raise ValueError("ID siswa tidak valid.")
    return _query_tagihan(status=status, student_id=student_id, limit=limit)


def mulai_pembayaran_va(student_id: int, invoice_id: int) -> dict:
    """Buat VA referensi internal untuk pembayaran penuh satu tagihan."""
    if type(student_id) is not int or student_id <= 0:
        raise ValueError("ID siswa tidak valid.")
    if type(invoice_id) is not int or invoice_id <= 0:
        raise ValueError("ID tagihan tidak valid.")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT i.id AS invoice_id, i.no_invoice, i.jumlah,
                       i.status AS invoice_status, e.student_id
                FROM invoices AS i
                JOIN enrollments AS e ON e.id = i.enrollment_id
                WHERE i.id = %s AND e.student_id = %s
                FOR UPDATE OF i;
                """,
                (invoice_id, student_id),
            )
            invoice = cur.fetchone()
            if invoice is None:
                raise LookupError("Tagihan tidak ditemukan untuk akun siswa ini.")
            if invoice["invoice_status"] == "lunas":
                raise ValueError("Tagihan ini sudah lunas.")
            if invoice["invoice_status"] == "batal":
                raise ValueError("Tagihan ini sudah dibatalkan.")
            if invoice["jumlah"] <= 0:
                raise ValueError("Tagihan bernilai nol tidak memerlukan pembayaran.")

            cur.execute(
                """
                SELECT id AS payment_id, kode_bayar, jumlah, status AS payment_status,
                       paid_at, created_at
                FROM payments
                WHERE invoice_id = %s
                  AND status IN ('menunggu_pembayaran', 'menunggu_konfirmasi', 'lunas')
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE;
                """,
                (invoice_id,),
            )
            sebelumnya = cur.fetchone()
            if sebelumnya is not None:
                if sebelumnya["payment_status"] == "lunas":
                    raise ValueError(
                        "Sudah ada pembayaran lunas untuk tagihan ini. "
                        "Hubungi admin jika status tagihan belum diperbarui."
                    )
                return sebelumnya

            # Nomor ini adalah referensi VA internal/simulasi, bukan koneksi ke bank.
            kode_bayar = f"VA{invoice_id:08d}{token_hex(4).upper()}"
            cur.execute(
                """
                INSERT INTO payments (invoice_id, kode_bayar, jumlah, status)
                VALUES (%s, %s, %s, 'menunggu_pembayaran')
                RETURNING id AS payment_id, kode_bayar, jumlah,
                          status AS payment_status, paid_at, created_at;
                """,
                (invoice_id, kode_bayar, invoice["jumlah"]),
            )
            pembayaran = cur.fetchone()
            _catat_log(
                cur,
                student_id,
                "BILLING_VA_DIBUAT",
                f"VA dibuat untuk invoice {invoice['no_invoice']} (payment ID {pembayaran['payment_id']}).",
            )
        conn.commit()
    return pembayaran


def siswa_konfirmasi_sudah_bayar(student_id: int, payment_id: int) -> dict:
    if type(student_id) is not int or student_id <= 0:
        raise ValueError("ID siswa tidak valid.")
    if type(payment_id) is not int or payment_id <= 0:
        raise ValueError("ID pembayaran tidak valid.")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT pay.id AS payment_id, pay.kode_bayar, pay.status AS payment_status,
                       i.id AS invoice_id, i.no_invoice, i.status AS invoice_status,
                       e.student_id
                FROM payments AS pay
                JOIN invoices AS i ON i.id = pay.invoice_id
                JOIN enrollments AS e ON e.id = i.enrollment_id
                WHERE pay.id = %s AND e.student_id = %s
                FOR UPDATE OF pay, i;
                """,
                (payment_id, student_id),
            )
            pembayaran = cur.fetchone()
            if pembayaran is None:
                raise LookupError("Pembayaran tidak ditemukan untuk akun siswa ini.")
            if pembayaran["payment_status"] == "menunggu_konfirmasi":
                return pembayaran
            if pembayaran["payment_status"] != "menunggu_pembayaran":
                raise ValueError("Pembayaran ini tidak lagi menunggu konfirmasi dari siswa.")
            if pembayaran["invoice_status"] != "belum_dibayar":
                raise ValueError("Status tagihan tidak mengizinkan pengajuan pembayaran.")

            cur.execute(
                """
                UPDATE payments
                SET status = 'menunggu_konfirmasi', paid_at = now(), alasan_tolak = NULL
                WHERE id = %s
                RETURNING id AS payment_id, kode_bayar, status AS payment_status, paid_at;
                """,
                (payment_id,),
            )
            hasil = cur.fetchone()
            _catat_log(
                cur,
                student_id,
                "BILLING_SISWA_KONFIRMASI",
                f"Siswa menyatakan membayar invoice {pembayaran['no_invoice']} (payment ID {payment_id}).",
            )
        conn.commit()
    return hasil


def daftar_konfirmasi_pembayaran(limit=300):
    limit = max(1, min(int(limit), 1000))
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT pay.id AS payment_id, pay.kode_bayar, pay.jumlah AS payment_jumlah,
                       pay.status AS payment_status, pay.paid_at, pay.created_at AS payment_created_at,
                       i.id AS invoice_id, i.no_invoice, i.periode, i.jumlah AS invoice_jumlah,
                       i.status AS invoice_status, i.jatuh_tempo,
                       e.student_id, s.nis, u.nama_lengkap AS nama_siswa, u.username,
                       p.nama AS nama_program, p.kode AS kode_program
                FROM payments AS pay
                JOIN invoices AS i ON i.id = pay.invoice_id
                JOIN enrollments AS e ON e.id = i.enrollment_id
                JOIN students AS s ON s.user_id = e.student_id
                JOIN users AS u ON u.id = e.student_id
                JOIN programs AS p ON p.id = e.program_id
                WHERE pay.status = 'menunggu_konfirmasi'
                ORDER BY pay.paid_at ASC NULLS LAST, pay.id ASC
                LIMIT %s;
                """,
                (limit,),
            )
            return cur.fetchall()


def proses_pembayaran_admin(payment_id: int, admin_id: int, keputusan: str, alasan: str | None = None):
    """Setujui/tolak pengajuan dan sinkronkan status invoice dalam satu transaksi."""
    if type(payment_id) is not int or payment_id <= 0:
        raise ValueError("ID pembayaran tidak valid.")
    if type(admin_id) is not int or admin_id <= 0:
        raise ValueError("ID admin tidak valid.")
    if keputusan not in {"lunas", "ditolak"}:
        raise ValueError("Keputusan pembayaran tidak valid.")
    alasan_bersih = (alasan or "").strip()
    if keputusan == "ditolak" and not alasan_bersih:
        raise ValueError("Alasan penolakan wajib diisi.")

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT pay.id AS payment_id, pay.invoice_id, pay.kode_bayar,
                       pay.jumlah AS payment_jumlah, pay.status AS payment_status,
                       i.no_invoice, i.jumlah AS invoice_jumlah, i.status AS invoice_status,
                       e.student_id, u.nama_lengkap AS nama_siswa
                FROM payments AS pay
                JOIN invoices AS i ON i.id = pay.invoice_id
                JOIN enrollments AS e ON e.id = i.enrollment_id
                JOIN users AS u ON u.id = e.student_id
                WHERE pay.id = %s
                FOR UPDATE OF pay, i;
                """,
                (payment_id,),
            )
            pembayaran = cur.fetchone()
            if pembayaran is None:
                raise LookupError("Data pembayaran tidak ditemukan.")
            if pembayaran["payment_status"] != "menunggu_konfirmasi":
                raise ValueError("Pembayaran sudah diproses atau belum diajukan siswa.")
            if pembayaran["invoice_status"] != "belum_dibayar":
                raise ValueError("Tagihan tidak lagi berstatus belum dibayar; pembayaran ini tidak dapat diproses.")

            if keputusan == "lunas":
                if pembayaran["payment_jumlah"] != pembayaran["invoice_jumlah"]:
                    raise ValueError("Nominal pembayaran tidak sama dengan tagihan penuh.")
                cur.execute(
                    "UPDATE invoices SET status = 'lunas' WHERE id = %s AND status = 'belum_dibayar' RETURNING id;",
                    (pembayaran["invoice_id"],),
                )
                if cur.fetchone() is None:
                    raise ValueError("Tagihan bukan lagi berstatus belum dibayar.")
                cur.execute(
                    """
                    UPDATE payments
                    SET status = 'lunas', processed_by = %s, processed_at = now(), alasan_tolak = NULL
                    WHERE id = %s
                    RETURNING id;
                    """,
                    (admin_id, payment_id),
                )
                aksi = "BILLING_ADMIN_LUNAS"
                detail = (
                    f"Admin menyetujui pembayaran {pembayaran['kode_bayar']} "
                    f"untuk invoice {pembayaran['no_invoice']} sebesar {pembayaran['payment_jumlah']}."
                )
            else:
                cur.execute(
                    """
                    UPDATE payments
                    SET status = 'ditolak', processed_by = %s, processed_at = now(), alasan_tolak = %s
                    WHERE id = %s
                    RETURNING id;
                    """,
                    (admin_id, alasan_bersih, payment_id),
                )
                aksi = "BILLING_ADMIN_TOLAK"
                detail = (
                    f"Admin menolak pembayaran {pembayaran['kode_bayar']} "
                    f"untuk invoice {pembayaran['no_invoice']}. Alasan: {alasan_bersih}"
                )
            _catat_log(cur, admin_id, aksi, detail)
        conn.commit()
    return pembayaran


def daftar_riwayat_pembayaran(student_id: int | None = None, limit=300):
    limit = max(1, min(int(limit), 1000))
    params = []
    where = ""
    if student_id is not None:
        if type(student_id) is not int or student_id <= 0:
            raise ValueError("ID siswa tidak valid.")
        where = "WHERE e.student_id = %s"
        params.append(student_id)
    params.append(limit)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT pay.id AS payment_id, pay.kode_bayar, pay.jumlah AS payment_jumlah,
                       pay.status AS payment_status, pay.paid_at, pay.processed_at,
                       pay.alasan_tolak, pay.created_at AS payment_created_at,
                       i.id AS invoice_id, i.no_invoice, i.periode, i.jumlah AS invoice_jumlah,
                       i.jatuh_tempo, i.status AS invoice_status,
                       e.student_id, s.nis, u.nama_lengkap AS nama_siswa,
                       p.nama AS nama_program, p.kode AS kode_program
                FROM payments AS pay
                JOIN invoices AS i ON i.id = pay.invoice_id
                JOIN enrollments AS e ON e.id = i.enrollment_id
                JOIN students AS s ON s.user_id = e.student_id
                JOIN users AS u ON u.id = e.student_id
                JOIN programs AS p ON p.id = e.program_id
                {where}
                ORDER BY pay.created_at DESC, pay.id DESC
                LIMIT %s;
                """,
                params,
            )
            return cur.fetchall()


def ambil_bukti_pembayaran(payment_id: int, student_id: int | None = None):
    if type(payment_id) is not int or payment_id <= 0:
        raise ValueError("ID pembayaran tidak valid.")
    params = [payment_id]
    where_owner = ""
    if student_id is not None:
        if type(student_id) is not int or student_id <= 0:
            raise ValueError("ID siswa tidak valid.")
        where_owner = "AND e.student_id = %s"
        params.append(student_id)
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT pay.id AS payment_id, pay.kode_bayar, pay.jumlah AS payment_jumlah,
                       pay.status AS payment_status, pay.paid_at, pay.processed_at,
                       i.id AS invoice_id, i.no_invoice, i.periode,
                       i.jumlah AS invoice_jumlah, i.jatuh_tempo,
                       e.student_id, s.nis, u.nama_lengkap AS nama_siswa,
                       u.email AS email_siswa, u.username,
                       p.nama AS nama_program, p.kode AS kode_program
                FROM payments AS pay
                JOIN invoices AS i ON i.id = pay.invoice_id
                JOIN enrollments AS e ON e.id = i.enrollment_id
                JOIN students AS s ON s.user_id = e.student_id
                JOIN users AS u ON u.id = e.student_id
                JOIN programs AS p ON p.id = e.program_id
                WHERE pay.id = %s AND pay.status = 'lunas' {where_owner}
                LIMIT 1;
                """,
                params,
            )
            return cur.fetchone()
