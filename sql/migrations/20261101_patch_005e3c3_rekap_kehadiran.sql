-- PATCH-005E3-C3 — CREATE OR REPLACE menjaga kolom asli dan privilege view.
-- Disarankan via tools/apply_migration_005e3c3.py agar mendapat preflight.
CREATE OR REPLACE VIEW v_rekap_kehadiran AS
SELECT e.student_id, e.program_id,
       r.total_pertemuan, r.hadir, r.izin, r.sakit, r.alpa, r.persen_hadir,
       e.id AS enrollment_id,
       e.status::text AS status_enrollment,
       e.created_at::date AS tanggal_pendaftaran
FROM enrollments e
CROSS JOIN LATERAL (
    SELECT COUNT(*) AS total_pertemuan,
           COUNT(*) FILTER (WHERE a.status = 'H') AS hadir,
           COUNT(*) FILTER (WHERE a.status = 'I') AS izin,
           COUNT(*) FILTER (WHERE a.status = 'S') AS sakit,
           COUNT(*) FILTER (WHERE a.status = 'A') AS alpa,
           ROUND(100.0 * COUNT(*) FILTER (WHERE a.status = 'H')
                 / NULLIF(COUNT(*), 0), 1) AS persen_hadir
    FROM attendances a
    JOIN class_sessions cs ON cs.id = a.session_id AND cs.status = 'selesai'
    JOIN schedules s ON s.id = cs.schedule_id AND s.program_id = e.program_id
    WHERE a.enrollment_id = e.id AND a.student_id = e.student_id
) r
WHERE e.status IN ('aktif', 'selesai', 'batal');
