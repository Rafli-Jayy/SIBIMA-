-- PATCH-005E3-C2 — Referensi enrollment pada catatan absensi.
-- Dipakai oleh tools/apply_migration_005e3c2.py setelah --check dan konfirmasi.
-- TIDAK melakukan backfill atau UPDATE attendances historis.
ALTER TABLE attendances ADD COLUMN IF NOT EXISTS enrollment_id INTEGER;
ALTER TABLE attendances ADD CONSTRAINT fk_attendances_enrollment
    FOREIGN KEY (enrollment_id) REFERENCES enrollments(id);
CREATE INDEX IF NOT EXISTS idx_attend_enrollment
    ON attendances (enrollment_id) WHERE enrollment_id IS NOT NULL;
