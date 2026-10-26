-- SIBIMA: hapus fitur kuis mandiri, permohonan, honor, rating/feedback;
-- sederhanakan pembayaran menjadi Virtual Account dan bayar penuh.
-- Jalankan setelah BACKUP, sebagai pemilik objek/tabel yang terdampak.
-- Perubahan berjalan atomik: bila gagal, seluruh migrasi dibatalkan.

BEGIN;

-- Hapus view yang memakai kolom/status lama terlebih dahulu.
DROP VIEW IF EXISTS v_honor_tutor;
DROP VIEW IF EXISTS v_rating_tutor;
DROP VIEW IF EXISTS v_tagihan_status;
DROP VIEW IF EXISTS v_pemasukan_bulanan;

-- Pertahankan nominal akhir tagihan lama: jumlah baru menjadi nominal setelah diskon.
-- Izinkan invoice bernilai nol untuk kasus diskon historis 100%.
ALTER TABLE invoices DROP CONSTRAINT IF EXISTS invoices_jumlah_check;
UPDATE invoices
SET jumlah = ROUND(jumlah * (1 - diskon_persen / 100), 2)
WHERE diskon_persen <> 0;
ALTER TABLE invoices
    ADD CONSTRAINT invoices_jumlah_nonnegative_check CHECK (jumlah >= 0);
ALTER TABLE invoices DROP COLUMN IF EXISTS diskon_persen;

-- Cicilan tidak lagi menjadi status invoice. Tagihan yang dahulu berstatus
-- cicilan dipindahkan menjadi belum_dibayar; riwayat payment tidak dihapus.
UPDATE invoices SET status = 'belum_dibayar' WHERE status::text = 'cicilan';
ALTER TABLE invoices ALTER COLUMN status DROP DEFAULT;
CREATE TYPE invoice_status_simplified AS ENUM ('belum_dibayar', 'lunas', 'batal');
ALTER TABLE invoices
    ALTER COLUMN status TYPE invoice_status_simplified
    USING status::text::invoice_status_simplified;
DROP TYPE invoice_status;
ALTER TYPE invoice_status_simplified RENAME TO invoice_status;
ALTER TABLE invoices ALTER COLUMN status SET DEFAULT 'belum_dibayar';

-- Status kedaluwarsa/dibatalkan tidak lagi digunakan untuk payment.
-- Simpan informasi status historis pada alasan_tolak sebelum menormalkannya.
UPDATE payments
SET alasan_tolak = concat_ws(
        E'\n',
        NULLIF(alasan_tolak, ''),
        'Status lama sebelum penyederhanaan: ' || status::text
    ),
    status = 'ditolak'
WHERE status::text IN ('kedaluwarsa', 'dibatalkan');

ALTER TABLE payments ALTER COLUMN status DROP DEFAULT;
ALTER TABLE payments DROP COLUMN IF EXISTS metode;
ALTER TABLE payments DROP COLUMN IF EXISTS expires_at;
DROP TYPE IF EXISTS payment_method;

CREATE TYPE payment_status_simplified AS ENUM (
    'menunggu_pembayaran', 'menunggu_konfirmasi', 'lunas', 'ditolak'
);
ALTER TABLE payments
    ALTER COLUMN status TYPE payment_status_simplified
    USING status::text::payment_status_simplified;
DROP TYPE payment_status;
ALTER TYPE payment_status_simplified RENAME TO payment_status;
ALTER TABLE payments ALTER COLUMN status SET DEFAULT 'menunggu_pembayaran';

-- Hapus tabel fitur yang dicabut. Tabel akademik grades tetap dipertahankan;
-- nilai manual dengan jenis 'kuis' tetap sah meski modul kuis mandiri dihapus.
DROP TABLE IF EXISTS quiz_attempts;
DROP TABLE IF EXISTS quiz_questions;
DROP TABLE IF EXISTS quizzes;
DROP TABLE IF EXISTS tutor_reviews;
DROP TABLE IF EXISTS student_feedbacks;
DROP TABLE IF EXISTS leave_requests;
DROP TABLE IF EXISTS schedule_change_requests;

ALTER TABLE tutors DROP COLUMN IF EXISTS tarif_per_pertemuan;
DROP TYPE IF EXISTS request_status;

-- Bangun ulang view pembayaran tanpa diskon dan tanpa view honor/rating.
CREATE VIEW v_tagihan_status AS
SELECT i.id AS invoice_id,
       i.no_invoice,
       i.enrollment_id,
       e.student_id,
       i.periode,
       i.jatuh_tempo,
       i.status,
       i.jumlah,
       i.jumlah AS total_tagihan,
       COALESCE(SUM(p.jumlah) FILTER (WHERE p.status = 'lunas'), 0) AS terbayar
FROM invoices i
JOIN enrollments e ON e.id = i.enrollment_id
LEFT JOIN payments p ON p.invoice_id = i.id
GROUP BY i.id, e.student_id;

CREATE VIEW v_pemasukan_bulanan AS
SELECT date_trunc('month', processed_at)::date AS bulan,
       COUNT(*) AS jumlah_transaksi,
       SUM(jumlah) AS total_pemasukan
FROM payments
WHERE status = 'lunas'
GROUP BY 1;

-- Cegah pembayaran baru/yang diedit memiliki nominal parsial.
-- Baris pembayaran historis tetap dipertahankan dan tidak divalidasi ulang.
CREATE OR REPLACE FUNCTION fn_validate_full_payment() RETURNS TRIGGER AS $$
DECLARE
    nominal_tagihan NUMERIC(12,2);
BEGIN
    SELECT jumlah INTO nominal_tagihan
    FROM invoices
    WHERE id = NEW.invoice_id;

    IF nominal_tagihan IS NULL THEN
        RAISE EXCEPTION 'Tagihan % tidak ditemukan.', NEW.invoice_id;
    END IF;
    IF NEW.jumlah <> nominal_tagihan THEN
        RAISE EXCEPTION 'Pembayaran harus penuh sebesar %.', nominal_tagihan;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validate_full_payment ON payments;
CREATE TRIGGER trg_validate_full_payment
BEFORE INSERT OR UPDATE OF invoice_id, jumlah ON payments
FOR EACH ROW EXECUTE FUNCTION fn_validate_full_payment();

COMMIT;
