-- Pemulihan terbatas N2: matikan pembuat notifikasi otomatis N2.
-- TIDAK menghapus kolom, pesan historis, N1, ataupun pengumuman Tutor yang sudah terbit.
BEGIN;
DO $$ BEGIN IF current_database()<>'bimbel_db' THEN RAISE EXCEPTION 'Bukan bimbel_db'; END IF; END $$;
DROP TRIGGER IF EXISTS sibima_n2_grade_insert ON public.grades;
DROP TRIGGER IF EXISTS sibima_n2_grade_update ON public.grades;
DROP TRIGGER IF EXISTS sibima_n2_session_finished ON public.class_sessions;
DROP TRIGGER IF EXISTS sibima_n2_attendance_updated ON public.attendances;
DROP TRIGGER IF EXISTS sibima_n2_schedule_changed ON public.schedules;
COMMIT;
