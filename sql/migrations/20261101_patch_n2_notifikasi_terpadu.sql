-- SIBIMA PATCH-N2: perluasan N1, tanpa tabel baru; hanya bimbel_db.
-- Dijalankan satu kali setelah --check dan sebelum --apply; aman diulang.
BEGIN;
DO $$
BEGIN
  IF current_database() <> 'bimbel_db' THEN RAISE EXCEPTION 'N2 hanya untuk bimbel_db'; END IF;
  IF to_regclass('public.announcements') IS NULL OR to_regclass('public.announcement_reads') IS NULL
    OR to_regclass('public.class_sessions') IS NULL OR to_regclass('public.attendances') IS NULL
    OR to_regclass('public.grades') IS NULL OR to_regclass('public.schedules') IS NULL
    OR to_regprocedure('public.sibima_n1_emit(integer,text,text,text,text,integer)') IS NULL
  THEN RAISE EXCEPTION 'N1 / tabel akademik belum lengkap. Hentikan N2.'; END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public'
     AND table_name='class_sessions' AND column_name='status') THEN
    RAISE EXCEPTION 'Status pertemuan 005E3B belum tersedia.';
  END IF;
END $$;
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS expires_at timestamptz;
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS program_id integer REFERENCES public.programs(id);
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS batch_key text;
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS actor_user_id integer REFERENCES public.users(id);
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS related_type varchar(30);
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS related_id integer;
ALTER TABLE public.announcement_reads ADD COLUMN IF NOT EXISTS archived_at timestamptz;
-- Untuk memulai pemantauan setelah instalasi: jangan menganggap jadwal lama
-- otomatis belum dilaporkan sebelum PATCH-N2 terpasang.
ALTER TABLE public.schedules ADD COLUMN IF NOT EXISTS notif_monitor_from timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS sibima_n2_tutor_batch_idx ON public.announcements(dibuat_by,batch_key)
 WHERE sumber='tutor' AND batch_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS sibima_n2_related_idx ON public.announcements(related_type,related_id)
 WHERE related_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS sibima_n2_read_arch_idx ON public.announcement_reads(user_id,archived_at);

-- N1 emitter sekarang juga mengisi aktor yang TERVERIFIKASI; bila actor = target
-- (fallback lama) jangan keliru menampilkan siswa sebagai pembuat peristiwa sistem.
CREATE OR REPLACE FUNCTION public.sibima_n1_emit(
  target_id integer, category_name text, unique_event_key text,
  notification_title text, notification_body text, actor_id integer DEFAULT NULL
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE author_id integer; real_actor integer;
BEGIN
  IF target_id IS NULL OR unique_event_key IS NULL THEN RETURN; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.users WHERE id=target_id) THEN RETURN; END IF;
  real_actor := NULL;
  IF actor_id IS NOT NULL AND actor_id <> target_id
    AND EXISTS (SELECT 1 FROM public.users WHERE id=actor_id)
  THEN real_actor := actor_id; END IF;
  author_id := COALESCE(real_actor,target_id);
  INSERT INTO public.announcements
    (judul,isi,dibuat_by,penerima_user_id,sumber,kategori,event_key,actor_user_id)
  VALUES (left(notification_title,150),left(notification_body,4000),author_id,
          target_id,'sistem',category_name,unique_event_key,real_actor)
  ON CONFLICT DO NOTHING;
END $$;
REVOKE ALL ON FUNCTION public.sibima_n1_emit(integer,text,text,text,text,integer) FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.sibima_n2_emit(
  target_id integer, category_name text, unique_event_key text,
  notification_title text, notification_body text, actor_id integer DEFAULT NULL,
  program_ref integer DEFAULT NULL, ref_type text DEFAULT NULL, ref_id integer DEFAULT NULL
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE author_id integer; valid_actor integer;
BEGIN
 IF target_id IS NULL OR unique_event_key IS NULL OR notification_title IS NULL THEN RETURN; END IF;
 IF NOT EXISTS (SELECT 1 FROM public.users WHERE id=target_id) THEN RETURN; END IF;
 valid_actor := NULL;
 IF actor_id IS NOT NULL AND EXISTS (SELECT 1 FROM public.users WHERE id=actor_id) THEN
   valid_actor := actor_id;
 END IF;
 author_id := COALESCE(valid_actor,target_id);
 INSERT INTO public.announcements
   (judul,isi,dibuat_by,penerima_user_id,sumber,kategori,event_key,
    actor_user_id,program_id,related_type,related_id)
 VALUES (left(notification_title,150),left(notification_body,4000),author_id,
         target_id,'sistem',left(category_name,30),unique_event_key,
         valid_actor,program_ref,left(ref_type,30),ref_id)
 ON CONFLICT DO NOTHING;
END $$;
REVOKE ALL ON FUNCTION public.sibima_n2_emit(integer,text,text,text,text,integer,integer,text,integer) FROM PUBLIC;

-- Nilai: kirim setelah INSERT/UPDATE berhasil. Tidak mengirim bila nilai identik.
CREATE OR REPLACE FUNCTION public.sibima_n2_grade_trigger()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE sid integer; pid integer; pname text; title_text text; body_text text; key_text text;
BEGIN
 IF TG_OP='UPDATE' THEN
   IF (OLD.nilai,OLD.jenis,OLD.judul,OLD.tanggal)
       IS NOT DISTINCT FROM (NEW.nilai,NEW.jenis,NEW.judul,NEW.tanggal) THEN RETURN NEW; END IF;
 END IF;
 SELECT e.student_id,e.program_id,p.nama INTO sid,pid,pname
 FROM public.enrollments e JOIN public.programs p ON p.id=e.program_id WHERE e.id=NEW.enrollment_id;
 IF sid IS NULL THEN RETURN NEW; END IF;
 title_text := CASE WHEN TG_OP='INSERT' THEN 'Nilai Baru Diterbitkan' ELSE 'Nilai Diperbarui' END;
 body_text := 'Nilai ' || upper(NEW.jenis::text) || ' - ' || coalesce(nullif(btrim(NEW.judul),''),'Penilaian') ||
   ' untuk ' || coalesce(pname,'kelas') || ': ' || NEW.nilai::text || '/100.';
 IF TG_OP='UPDATE' THEN body_text := body_text || ' Nilai sebelumnya: ' || OLD.nilai::text || '/100.'; END IF;
 key_text := CASE WHEN TG_OP='INSERT' THEN 'n2:grade:new:' || NEW.id
                  ELSE 'n2:grade:edit:' || NEW.id || ':' || txid_current()::text END;
 PERFORM public.sibima_n2_emit(sid,'nilai',key_text,title_text,body_text,
   NEW.input_by,pid,'grade',NEW.id);
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS sibima_n2_grade_insert ON public.grades;
DROP TRIGGER IF EXISTS sibima_n2_grade_update ON public.grades;
CREATE TRIGGER sibima_n2_grade_insert AFTER INSERT ON public.grades
 FOR EACH ROW EXECUTE FUNCTION public.sibima_n2_grade_trigger();
CREATE TRIGGER sibima_n2_grade_update AFTER UPDATE ON public.grades
 FOR EACH ROW EXECUTE FUNCTION public.sibima_n2_grade_trigger();

CREATE OR REPLACE FUNCTION public.sibima_n2_session_trigger()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE schedule_row record; a record; student_row record;
DECLARE nama_status text; body_text text;
BEGIN
 IF OLD.status IS NOT DISTINCT FROM NEW.status OR NEW.status::text NOT IN ('selesai','batal') THEN RETURN NEW; END IF;
 SELECT s.id AS schedule_id,s.program_id,s.tutor_id,p.nama AS nama_program
 INTO schedule_row FROM public.schedules s JOIN public.programs p ON p.id=s.program_id
 WHERE s.id=NEW.schedule_id;
 IF schedule_row IS NULL THEN RETURN NEW; END IF;
 -- Pengingat jadwal hari itu tidak boleh tampak aktif setelah sesi final/batal.
 UPDATE public.announcements SET expires_at=now()
  WHERE sumber='sistem' AND kategori='jadwal'
   AND related_type='schedule' AND related_id=NEW.schedule_id
   AND event_key LIKE ('n2:jadwal:'||NEW.schedule_id||':'||NEW.tanggal::text||':%')
   AND (expires_at IS NULL OR expires_at > now());
 IF NEW.status::text='batal' THEN
  FOR student_row IN SELECT DISTINCT e.student_id FROM public.enrollments e
      WHERE e.program_id=schedule_row.program_id
        AND e.status::text='aktif'
        AND COALESCE(e.processed_at::date,e.created_at::date)<=NEW.tanggal
  LOOP
   PERFORM public.sibima_n2_emit(student_row.student_id,'jadwal',
    'n2:session:cancel:'||NEW.id||':'||student_row.student_id,
    'Pertemuan Dibatalkan',
    'Pertemuan '||schedule_row.nama_program||' tanggal '||NEW.tanggal::text||
      ' dibatalkan. Alasan: '||coalesce(nullif(NEW.alasan_batal,''),'Tidak dicantumkan.'),
    schedule_row.tutor_id,schedule_row.program_id,'session',NEW.id);
  END LOOP;
 ELSE
  FOR a IN SELECT student_id,status::text AS status_absen FROM public.attendances
    WHERE session_id=NEW.id
  LOOP
   nama_status := CASE a.status_absen WHEN 'H' THEN 'Hadir' WHEN 'I' THEN 'Izin'
                  WHEN 'S' THEN 'Sakit' WHEN 'A' THEN 'Alpa' ELSE a.status_absen END;
   body_text := 'Absensi '||schedule_row.nama_program||' pertemuan ke-'||NEW.pertemuan_ke::text||
      ' ('||NEW.tanggal::text||') telah difinalisasi. Status kamu: '||nama_status||'.';
   PERFORM public.sibima_n2_emit(a.student_id,'absensi',
     'n2:attendance:final:'||NEW.id||':'||a.student_id,
     'Hasil Absensi: '||nama_status,body_text,
     schedule_row.tutor_id,schedule_row.program_id,'session',NEW.id);
  END LOOP;
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS sibima_n2_session_finished ON public.class_sessions;
CREATE TRIGGER sibima_n2_session_finished AFTER UPDATE OF status ON public.class_sessions
 FOR EACH ROW EXECUTE FUNCTION public.sibima_n2_session_trigger();

-- Koreksi absensi yang sah setelah final menghasilkan notifikasi koreksi.
CREATE OR REPLACE FUNCTION public.sibima_n2_attendance_trigger()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE st record; nama_status text;
BEGIN
 IF OLD.status IS NOT DISTINCT FROM NEW.status THEN RETURN NEW; END IF;
 SELECT cs.id AS sid,cs.pertemuan_ke,cs.tanggal,s.program_id,s.tutor_id,p.nama AS nama_program
 INTO st FROM public.class_sessions cs JOIN public.schedules s ON s.id=cs.schedule_id
 JOIN public.programs p ON p.id=s.program_id
 WHERE cs.id=NEW.session_id AND cs.status::text='selesai';
 IF st IS NULL THEN RETURN NEW; END IF;
 nama_status := CASE NEW.status::text WHEN 'H' THEN 'Hadir' WHEN 'I' THEN 'Izin'
                  WHEN 'S' THEN 'Sakit' WHEN 'A' THEN 'Alpa' ELSE NEW.status::text END;
 PERFORM public.sibima_n2_emit(NEW.student_id,'absensi',
   'n2:attendance:correction:'||NEW.session_id||':'||NEW.student_id||':'||txid_current()::text,
   'Koreksi Absensi: '||nama_status,
   'Absensi '||st.nama_program||' tanggal '||st.tanggal::text||
   ' diperbarui menjadi '||nama_status||'.',st.tutor_id,st.program_id,'session',NEW.session_id);
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS sibima_n2_attendance_updated ON public.attendances;
CREATE TRIGGER sibima_n2_attendance_updated AFTER UPDATE ON public.attendances
 FOR EACH ROW EXECUTE FUNCTION public.sibima_n2_attendance_trigger();

-- Revisi jadwal: pesan baru untuk peserta aktif dan Tutor lama/baru.
CREATE OR REPLACE FUNCTION public.sibima_n2_schedule_trigger()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
DECLARE target_row record; pname text; notes text;
BEGIN
 IF (OLD.program_id,OLD.tutor_id,OLD.hari,OLD.jam_mulai,OLD.jam_selesai,OLD.room_id,OLD.aktif)
   IS NOT DISTINCT FROM
    (NEW.program_id,NEW.tutor_id,NEW.hari,NEW.jam_mulai,NEW.jam_selesai,NEW.room_id,NEW.aktif)
 THEN RETURN NEW; END IF;
 SELECT nama INTO pname FROM public.programs WHERE id=NEW.program_id;
 notes := 'Jadwal '||coalesce(pname,'kelas')||' diperbarui. Hari: '||NEW.hari::text||
   ', jam: '||NEW.jam_mulai::text||'–'||NEW.jam_selesai::text||
   '. Status: '||CASE WHEN NEW.aktif THEN 'aktif' ELSE 'nonaktif' END||
   '. Periksa menu Jadwal untuk detail terkini.';
 UPDATE public.announcements SET expires_at=now()
 WHERE related_type='schedule' AND related_id=NEW.id AND kategori='jadwal'
   AND event_key LIKE ('n2:jadwal:'||NEW.id||':%')
   AND (expires_at IS NULL OR expires_at > now());
 FOR target_row IN
    SELECT DISTINCT student_id AS uid FROM public.enrollments
    WHERE program_id IN (OLD.program_id,NEW.program_id) AND status::text='aktif'
    UNION SELECT OLD.tutor_id AS uid UNION SELECT NEW.tutor_id AS uid
 LOOP
  PERFORM public.sibima_n2_emit(target_row.uid,'jadwal',
    'n2:schedule:changed:'||NEW.id||':'||txid_current()::text||':'||target_row.uid,
    'Perubahan Jadwal Kelas',notes,NULL,NEW.program_id,'schedule',NEW.id);
 END LOOP;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS sibima_n2_schedule_changed ON public.schedules;
CREATE TRIGGER sibima_n2_schedule_changed
 AFTER UPDATE OF program_id,tutor_id,hari,jam_mulai,jam_selesai,room_id,aktif ON public.schedules
 FOR EACH ROW EXECUTE FUNCTION public.sibima_n2_schedule_trigger();

REVOKE ALL ON FUNCTION public.sibima_n2_grade_trigger() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.sibima_n2_session_trigger() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.sibima_n2_attendance_trigger() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.sibima_n2_schedule_trigger() FROM PUBLIC;

-- Untuk akun aplikasi yang sebelumnya belum mendapat izin UPDATE kolom baru.
DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='bimbel_user') THEN
 GRANT SELECT,INSERT,UPDATE ON public.announcements TO bimbel_user;
 GRANT SELECT,INSERT,UPDATE ON public.announcement_reads TO bimbel_user;
 GRANT USAGE,SELECT ON SEQUENCE public.announcements_id_seq TO bimbel_user;
 END IF; END $$;
COMMIT;
