-- PATCH-001A: target role, read tracking, and permanent announcement archive.
-- Safe to rerun: existing columns/tables/targets are preserved.
BEGIN;

ALTER TABLE announcements
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS announcement_targets (
    announcement_id INT NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
    target_role     user_role NOT NULL CHECK (target_role IN ('siswa', 'tutor')),
    PRIMARY KEY (announcement_id, target_role)
);
CREATE INDEX IF NOT EXISTS idx_announcement_targets_role
    ON announcement_targets (target_role, announcement_id);

CREATE TABLE IF NOT EXISTS announcement_reads (
    announcement_id INT NOT NULL REFERENCES announcements(id) ON DELETE CASCADE,
    user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    read_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (announcement_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_announcement_reads_user
    ON announcement_reads (user_id, announcement_id);

-- Backfill seluruh pengumuman lama, termasuk yang sudah diarsipkan.
-- Arsip lama tetap arsip; backfill hanya memastikan target historis tersedia.
INSERT INTO announcement_targets (announcement_id, target_role)
SELECT id, 'siswa'::user_role FROM announcements
ON CONFLICT (announcement_id, target_role) DO NOTHING;

INSERT INTO announcement_targets (announcement_id, target_role)
SELECT id, 'tutor'::user_role FROM announcements
ON CONFLICT (announcement_id, target_role) DO NOTHING;

COMMIT;
