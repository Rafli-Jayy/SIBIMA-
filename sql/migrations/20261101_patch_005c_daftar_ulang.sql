-- PATCH-005C: Boleh daftar ulang setelah batal/ditolak/selesai.
-- Transaksi: jalankan via tools/apply_migration_005c.py (atau psql -1).
-- Buat unique index BARU sebelum melepas constraint lama.
-- Tidak menghapus enrollment, invoice, payment, refund atau nilai.
CREATE UNIQUE INDEX IF NOT EXISTS uq_enrollment_berjalan
    ON enrollments (student_id, program_id)
    WHERE status IN ('menunggu_pembayaran', 'menunggu', 'aktif');

ALTER TABLE enrollments DROP CONSTRAINT IF EXISTS uq_enrollment;
