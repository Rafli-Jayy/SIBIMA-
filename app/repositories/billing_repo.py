"""Repository tagihan dan pembayaran Virtual Account penuh SIBIMA."""

from psycopg.rows import dict_row

from app.db import pool
from app.config import PAYMENT_SIMULATION_SUCCESS_RATE

STATUS_TAGIHAN = {"belum_dibayar", "lunas", "batal"}
STATUS_PEMBAYARAN = {
    "menunggu_pembayaran", "menunggu_konfirmasi", "lunas", "ditolak", "gagal", "direfund",
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


def buat_tagihan_bulanan(admin_id: int) -> list[dict]:
    """Buat tagihan bulan berjalan dan kembalikan detail invoice yang baru dibuat."""
    if type(admin_id) is not int or admin_id <= 0:
        raise ValueError("ID admin tidak valid.")
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                WITH inserted AS (
                    INSERT INTO invoices (enrollment_id, periode, jumlah, jatuh_tempo, status)
                    SELECT e.id, date_trunc('month', CURRENT_DATE)::date,
                           p.harga_bulanan, CURRENT_DATE + 7, 'belum_dibayar'
                    FROM enrollments e JOIN programs p ON p.id = e.program_id
                    WHERE e.status = 'aktif' AND p.harga_bulanan > 0
                    ON CONFLICT (enrollment_id, periode) DO NOTHING
                    RETURNING id
                )
                SELECT i.id AS invoice_id, i.no_invoice, i.periode, i.jumlah,
                       i.jatuh_tempo, i.status, u.email AS email_siswa,
                       u.nama_lengkap AS nama_siswa, p.nama AS nama_program
                FROM inserted x JOIN invoices i ON i.id = x.id
                JOIN enrollments e ON e.id = i.enrollment_id
                JOIN users u ON u.id = e.student_id
                JOIN programs p ON p.id = e.program_id
                ORDER BY i.id;
                """
            )
            dibuat = cur.fetchall()
            _catat_log(
                cur, admin_id, "BILLING_TAGIHAN_BULANAN",
                f"Admin membuat {len(dibuat)} tagihan untuk periode bulan berjalan.",
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


def proses_simulasi_pembayaran(student_id: int, invoice_id: int, *, hasil_override=None) -> dict:
    """Jalankan simulasi checkout otomatis; tidak memproses uang sungguhan.

    hasil_override hanya untuk pengujian internal ("lunas" atau "gagal"); UI
    siswa tidak menerima parameter untuk menentukan hasil transaksi.
    """
    import secrets

    if type(student_id) is not int or student_id <= 0:
        raise ValueError("ID siswa tidak valid.")
    if type(invoice_id) is not int or invoice_id <= 0:
        raise ValueError("ID tagihan tidak valid.")
    if hasil_override not in (None, "lunas", "gagal"):
        raise ValueError("Hasil simulasi internal tidak valid.")
    hasil = hasil_override or (
        "lunas" if secrets.randbelow(100) < PAYMENT_SIMULATION_SUCCESS_RATE else "gagal"
    )

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT i.id AS invoice_id, i.no_invoice, i.jumlah,
                          i.status AS invoice_status, i.periode, e.id AS enrollment_id,
                          e.status AS enrollment_status, e.student_id, p.nama AS nama_program,
                          u.nama_lengkap AS nama_siswa, u.email AS email_siswa
                   FROM invoices i JOIN enrollments e ON e.id = i.enrollment_id
                   JOIN programs p ON p.id = e.program_id
                   JOIN users u ON u.id = e.student_id
                   WHERE i.id = %s AND e.student_id = %s FOR UPDATE OF i, e;""",
                (invoice_id, student_id),
            )
            invoice = cur.fetchone()
            if invoice is None:
                raise LookupError("Tagihan tidak ditemukan untuk akun siswa ini.")
            if invoice["invoice_status"] == "lunas":
                raise ValueError("Tagihan ini sudah lunas.")
            if invoice["invoice_status"] != "belum_dibayar":
                raise ValueError("Tagihan ini tidak dapat dibayar.")
            if invoice["jumlah"] <= 0:
                raise ValueError("Tagihan bernilai nol tidak memerlukan pembayaran.")
            if invoice["enrollment_status"] not in {"menunggu_pembayaran", "menunggu", "aktif"}:
                raise ValueError("Status pendaftaran tidak mengizinkan pembayaran.")

            kode_bayar = f"SIM-{invoice_id:08d}-{secrets.token_hex(3).upper()}"
            cur.execute(
                """INSERT INTO payments (invoice_id, kode_bayar, jumlah, status, paid_at)
                   VALUES (%s, %s, %s, %s, CASE WHEN %s = 'lunas' THEN now() ELSE NULL END)
                   RETURNING id AS payment_id, kode_bayar, jumlah AS payment_jumlah, status AS payment_status, paid_at;""",
                (invoice_id, kode_bayar, invoice["jumlah"], hasil, hasil),
            )
            payment = cur.fetchone()
            if hasil == "lunas":
                cur.execute("UPDATE invoices SET status = 'lunas' WHERE id = %s AND status = 'belum_dibayar';", (invoice_id,))
                if invoice["enrollment_status"] == "menunggu_pembayaran":
                    cur.execute("UPDATE enrollments SET status = 'menunggu' WHERE id = %s AND status = 'menunggu_pembayaran';", (invoice["enrollment_id"],))
                aksi = "BILLING_SIMULASI_BERHASIL"
                detail = f"Simulasi pembayaran {kode_bayar} untuk invoice {invoice['no_invoice']} berhasil sebesar {invoice['jumlah']}."
            else:
                aksi = "BILLING_SIMULASI_GAGAL"
                detail = f"Simulasi pembayaran {kode_bayar} untuk invoice {invoice['no_invoice']} gagal."
            _catat_log(cur, student_id, aksi, detail)
        conn.commit()
    return {
        **payment, "invoice_id": invoice_id, "no_invoice": invoice["no_invoice"],
        "invoice_jumlah": invoice["jumlah"], "nama_program": invoice["nama_program"],
        "simulation_result": hasil,
        "nama_siswa": invoice["nama_siswa"], "email_siswa": invoice["email_siswa"],
    }


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
                       p.nama AS nama_program, p.kode AS kode_program,
                       rf.kode_refund, rf.status AS refund_status, rf.created_at AS refund_created_at
                FROM payments AS pay
                JOIN invoices AS i ON i.id = pay.invoice_id
                JOIN enrollments AS e ON e.id = i.enrollment_id
                JOIN students AS s ON s.user_id = e.student_id
                JOIN users AS u ON u.id = e.student_id
                JOIN programs AS p ON p.id = e.program_id
                LEFT JOIN payment_refunds rf ON rf.payment_id = pay.id
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
