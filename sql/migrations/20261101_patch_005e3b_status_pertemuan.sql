-- PATCH-005E3-B: Jalankan menggunakan tools/apply_migration_005e3b.py.
-- Enum ditambahkan dan COMMIT terlebih dahulu sebelum kolom/default diubah.
-- SQL ini referensi; jangan jalankan ulang schema.sql pada database aktif.
-- Tahap 1 (commit terpisah):
ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'perlu_laporan';
ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'selesai';
-- Tahap 2 (transaksi baru):
ALTER TABLE class_sessions ADD COLUMN IF NOT EXISTS alasan_batal VARCHAR(500);
ALTER TABLE class_sessions ADD COLUMN IF NOT EXISTS selesai_at TIMESTAMPTZ;
ALTER TABLE class_sessions ALTER COLUMN status SET DEFAULT 'perlu_laporan'::session_status;
-- Data lama 'terlaksana' tetap; tidak diubah massal.
