"""Repository tagihan dan pembayaran SIBIMA.

Repository tagihan untuk skema pembayaran sederhana.

Saat ini modul yang diimplementasikan baru helper transaksi untuk membuat invoice
pertama. Alur pembayaran Virtual Account penuh masih menjadi pengembangan lanjutan.
"""


def buat_invoice_awal(cur, enrollment_id: int, jumlah):
    """Buat atau ambil invoice awal menggunakan cursor transaksi pemanggil.

    Cursor harus berada di transaksi aktif dan menggunakan row_factory=dict_row.
    Periode invoice adalah bulan berjalan; jatuh tempo tujuh hari kalender
    setelah tanggal database saat proses dijalankan. Program gratis tidak dibuatkan invoice.
    """
    if type(enrollment_id) is not int or enrollment_id <= 0:
        raise ValueError("ID enrollment tidak valid untuk pembuatan invoice.")
    if jumlah is None or jumlah < 0:
        raise ValueError("Nominal invoice tidak valid.")
    if jumlah == 0:
        return None

    cur.execute(
        """
        INSERT INTO invoices (
            enrollment_id, periode, jumlah, jatuh_tempo, status
        )
        VALUES (
            %s,
            date_trunc('month', CURRENT_DATE)::date,
            %s,
            CURRENT_DATE + 7,
            'belum_dibayar'
        )
        ON CONFLICT (enrollment_id, periode) DO NOTHING
        RETURNING id, no_invoice, periode, jumlah,
                  jatuh_tempo, status;
        """,
        (enrollment_id, jumlah),
    )
    invoice = cur.fetchone()
    if invoice is not None:
        return invoice

    # Kalau invoice periode ini sudah ada, gunakan yang lama hanya jika nominal
    # cocok. Konflik nominal harus membatalkan approval agar data tidak diam-diam
    # menerima tagihan yang berbeda dari harga program.
    cur.execute(
        """
        SELECT id, no_invoice, periode, jumlah,
               jatuh_tempo, status
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
