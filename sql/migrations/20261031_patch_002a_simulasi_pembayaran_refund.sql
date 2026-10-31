-- PATCH-002A: pendaftaran + invoice langsung, simulasi pembayaran otomatis, refund simulasi.
-- Jalankan sekali pada database bimbel_db sebagai pemilik schema / role dengan hak ALTER.
-- Migration ini tidak memindahkan uang dan tidak memanggil payment gateway.

-- Tahap 1: tambahkan nilai ENUM lalu COMMIT sebelum nilai baru dipakai di query.
BEGIN;
ALTER TYPE enrollment_status ADD VALUE IF NOT EXISTS 'menunggu_pembayaran';
ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'gagal';
ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'direfund';
COMMIT;

-- Tahap 2: tabel refund, penyesuaian data lama, dan view laporan.
BEGIN;
CREATE TABLE IF NOT EXISTS payment_refunds (
    id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payment_id INT NOT NULL UNIQUE REFERENCES payments(id),
    kode_refund VARCHAR(40) NOT NULL UNIQUE,
    jumlah NUMERIC(12,2) NOT NULL CHECK (jumlah > 0),
    alasan TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'berhasil' CHECK (status IN ('berhasil', 'gagal')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payment_refunds_status ON payment_refunds (status, created_at);
GRANT SELECT, INSERT, UPDATE ON TABLE payment_refunds TO bimbel_user;
GRANT USAGE, SELECT ON SEQUENCE payment_refunds_id_seq TO bimbel_user;

-- Pendaftaran berbayar lama yang masih menunggu admin sekarang menunggu pembayaran.
UPDATE enrollments e
SET status = 'menunggu_pembayaran'
FROM programs p
WHERE p.id = e.program_id
  AND e.status = 'menunggu'
  AND p.harga_bulanan > 0
  AND NOT EXISTS (
      SELECT 1 FROM invoices i
      WHERE i.enrollment_id = e.id AND i.status = 'lunas'
  );

-- Terbitkan invoice pertama bagi pendaftaran lama yang belum memilikinya.
INSERT INTO invoices (enrollment_id, periode, jumlah, jatuh_tempo, status)
SELECT e.id, date_trunc('month', CURRENT_DATE)::date, p.harga_bulanan,
       CURRENT_DATE + 7, 'belum_dibayar'
FROM enrollments e
JOIN programs p ON p.id = e.program_id
WHERE e.status = 'menunggu_pembayaran'
  AND p.harga_bulanan > 0
  AND NOT EXISTS (
      SELECT 1 FROM invoices i
      WHERE i.enrollment_id = e.id
        AND i.periode = date_trunc('month', CURRENT_DATE)::date
  )
ON CONFLICT (enrollment_id, periode) DO NOTHING;

-- Tutup referensi pembayaran manual lama yang belum lunas; siswa dapat checkout ulang.
UPDATE payments
SET status = 'gagal',
    alasan_tolak = COALESCE(alasan_tolak, 'Percobaan pembayaran manual lama ditutup saat migrasi ke simulasi otomatis.')
WHERE status IN ('menunggu_pembayaran', 'menunggu_konfirmasi');

CREATE OR REPLACE VIEW v_program_kuota AS
SELECT p.id AS program_id, p.kode, p.nama, p.kuota,
       COUNT(e.id) FILTER (WHERE e.status IN ('menunggu_pembayaran', 'menunggu', 'aktif')) AS terisi,
       p.kuota - COUNT(e.id) FILTER (WHERE e.status IN ('menunggu_pembayaran', 'menunggu', 'aktif')) AS sisa
FROM programs p LEFT JOIN enrollments e ON e.program_id = p.id GROUP BY p.id;

CREATE OR REPLACE VIEW v_pemasukan_bulanan AS
SELECT date_trunc('month', paid_at)::date AS bulan,
       COUNT(*) AS jumlah_transaksi, SUM(jumlah) AS total_pemasukan
FROM payments WHERE status = 'lunas' GROUP BY 1;
COMMIT;
