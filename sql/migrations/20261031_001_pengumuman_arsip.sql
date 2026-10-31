-- SIBIMA PATCH-001A: dukungan arsip pengumuman.
-- Jalankan satu kali pada database yang sudah memakai schema SIBIMA terbaru.
-- Backup database sebelum menjalankan migration.

BEGIN;

ALTER TABLE announcements
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_announcements_aktif
    ON announcements (created_at DESC, id DESC)
    WHERE archived_at IS NULL;

COMMIT;
