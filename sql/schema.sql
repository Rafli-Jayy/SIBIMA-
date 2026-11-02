--
-- PostgreSQL database dump
--

\restrict C2W58oX5fQsoUQ5wDv7ez6cXaHpnxleZZncEWIXhIkg0JEaVIZzubNYYg3gMsA1

-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;


--
-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';


--
-- Name: attendance_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.attendance_status AS ENUM (
    'H',
    'I',
    'S',
    'A'
);


--
-- Name: enrollment_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.enrollment_status AS ENUM (
    'menunggu',
    'aktif',
    'ditolak',
    'batal',
    'selesai',
    'menunggu_pembayaran'
);


--
-- Name: grade_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.grade_type AS ENUM (
    'tugas',
    'kuis',
    'uts',
    'uas'
);


--
-- Name: invoice_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.invoice_status AS ENUM (
    'belum_dibayar',
    'lunas',
    'batal'
);


--
-- Name: nama_hari; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.nama_hari AS ENUM (
    'senin',
    'selasa',
    'rabu',
    'kamis',
    'jumat',
    'sabtu',
    'minggu'
);


--
-- Name: otp_purpose; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.otp_purpose AS ENUM (
    'register',
    'reset_password',
    'login'
);


--
-- Name: payment_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.payment_status AS ENUM (
    'menunggu_pembayaran',
    'menunggu_konfirmasi',
    'lunas',
    'ditolak',
    'gagal',
    'direfund'
);


--
-- Name: program_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.program_status AS ENUM (
    'buka',
    'tutup'
);


--
-- Name: session_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.session_status AS ENUM (
    'terlaksana',
    'batal',
    'perlu_laporan',
    'selesai'
);


--
-- Name: timerange; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.timerange AS RANGE (
    subtype = time without time zone,
    multirange_type_name = public.timemultirange
);


--
-- Name: user_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_role AS ENUM (
    'admin',
    'tutor',
    'siswa'
);


--
-- Name: user_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_status AS ENUM (
    'belum_verifikasi',
    'menunggu_konfirmasi',
    'aktif',
    'ditolak',
    'nonaktif'
);


--
-- Name: fn_next_invoice(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_next_invoice() RETURNS text
    LANGUAGE sql
    AS $$
    SELECT 'INV-' || to_char(now(), 'YYYYMMDD') || '-' ||
           lpad(nextval('invoice_seq')::text, 4, '0');
$$;


--
-- Name: fn_next_kode_tutor(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_next_kode_tutor() RETURNS text
    LANGUAGE sql
    AS $$
    SELECT 'T-' || lpad(nextval('kode_tutor_seq')::text, 3, '0');
$$;


--
-- Name: fn_next_nis(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_next_nis() RETURNS text
    LANGUAGE sql
    AS $$
    SELECT 'S-' || lpad(nextval('nis_seq')::text, 4, '0');
$$;


--
-- Name: fn_validate_full_payment(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_validate_full_payment() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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
$$;


--
-- Name: sibima_n1_emit(integer, text, text, text, text, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sibima_n1_emit(target_id integer, category_name text, unique_event_key text, notification_title text, notification_body text, actor_id integer DEFAULT NULL::integer) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
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


--
-- Name: sibima_n1_enrollment_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sibima_n1_enrollment_trigger() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
DECLARE program_name text;
BEGIN
  SELECT p.nama INTO program_name FROM public.programs p WHERE p.id = NEW.program_id;
  program_name := coalesce(program_name, 'program bimbel');
  IF TG_OP = 'INSERT' THEN
    IF NEW.status::text IN ('menunggu_pembayaran', 'menunggu') THEN
      PERFORM public.sibima_n1_emit(NEW.student_id, 'pendaftaran', 'n1:enrollment:dibuat:' || NEW.id,
        'Pendaftaran Kelas Tercatat',
        'Pendaftaran ' || program_name || ' tercatat. Status: ' ||
        CASE WHEN NEW.status::text = 'menunggu_pembayaran' THEN 'menunggu pembayaran pertama.'
             ELSE 'menunggu persetujuan Admin.' END,
        NEW.student_id);
    END IF;
  ELSIF OLD.status IS DISTINCT FROM NEW.status THEN
    IF NEW.status::text = 'aktif' AND OLD.status::text = 'menunggu' THEN
      PERFORM public.sibima_n1_emit(NEW.student_id, 'pendaftaran', 'n1:enrollment:aktif:' || NEW.id,
        'Kelas Disetujui dan Aktif',
        'Pendaftaran ' || program_name || ' telah disetujui Admin. Kelas sekarang aktif.',
        NEW.processed_by);
    ELSIF NEW.status::text = 'ditolak' THEN
      PERFORM public.sibima_n1_emit(NEW.student_id, 'pendaftaran', 'n1:enrollment:ditolak:' || NEW.id,
        'Pendaftaran Kelas Ditolak',
        'Pendaftaran ' || program_name || ' ditolak. ' ||
          CASE WHEN NEW.alasan_tolak IS NOT NULL AND btrim(NEW.alasan_tolak) <> ''
               THEN 'Alasan: ' || left(NEW.alasan_tolak, 1000)
               ELSE 'Silakan hubungi Admin untuk informasi.' END,
        NEW.processed_by);
    END IF;
  END IF;
  RETURN NEW;
END $$;


--
-- Name: sibima_n1_invoices_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sibima_n1_invoices_trigger() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
DECLARE student_id integer; program_name text;
BEGIN
  SELECT e.student_id, p.nama INTO student_id, program_name
  FROM public.enrollments e JOIN public.programs p ON p.id = e.program_id
  WHERE e.id = NEW.enrollment_id;
  PERFORM public.sibima_n1_emit(student_id, 'tagihan', 'n1:invoice:dibuat:' || NEW.id,
    'Tagihan Baru Diterbitkan',
    'Invoice ' || NEW.no_invoice || ' untuk ' || coalesce(program_name, 'program bimbel') ||
    ' tersedia. Periksa nominal dan tanggal jatuh tempo melalui menu Tagihan dan Pembayaran.',
    student_id);
  RETURN NEW;
END $$;


--
-- Name: sibima_n1_payments_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sibima_n1_payments_trigger() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
DECLARE student_id integer; invoice_code text; title_text text; body_text text;
BEGIN
  IF TG_OP = 'UPDATE' AND OLD.status IS NOT DISTINCT FROM NEW.status THEN RETURN NEW; END IF;
  IF NEW.status::text NOT IN ('lunas', 'gagal', 'ditolak') THEN RETURN NEW; END IF;
  SELECT e.student_id, i.no_invoice INTO student_id, invoice_code
  FROM public.invoices i JOIN public.enrollments e ON e.id = i.enrollment_id
  WHERE i.id = NEW.invoice_id;
  IF NEW.status::text = 'lunas' THEN
    title_text := 'Pembayaran Simulasi Berhasil';
    body_text := 'Pembayaran simulasi untuk invoice ' || invoice_code ||
      ' berhasil tercatat. Jika pendaftaran masih menunggu Admin, akses kelas belum aktif.';
  ELSE
    title_text := 'Pembayaran Tidak Berhasil';
    body_text := 'Pembayaran simulasi untuk invoice ' || invoice_code ||
      ' tidak berhasil. Periksa menu Tagihan dan Pembayaran untuk melanjutkan.';
  END IF;
  PERFORM public.sibima_n1_emit(student_id, 'tagihan',
     'n1:payment:' || NEW.status::text || ':' || NEW.id,
     title_text, body_text, student_id);
  RETURN NEW;
END $$;


--
-- Name: sibima_n1_users_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sibima_n1_users_trigger() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
BEGIN
  IF NEW.status::text = 'aktif' AND OLD.status::text = 'menunggu_konfirmasi'
     AND NEW.role::text IN ('siswa', 'tutor') THEN
    PERFORM public.sibima_n1_emit(NEW.id, 'akun', 'n1:akun:aktif:' || NEW.id,
      'Akun SIBIMA Disetujui',
      'Akun kamu telah disetujui Admin dan sudah aktif. Silakan masuk ke SIBIMA untuk melihat layanan yang tersedia.',
      NEW.approved_by);
  END IF;
  RETURN NEW;
END $$;


--
-- Name: sibima_n2_attendance_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sibima_n2_attendance_trigger() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
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


--
-- Name: sibima_n2_emit(integer, text, text, text, text, integer, integer, text, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sibima_n2_emit(target_id integer, category_name text, unique_event_key text, notification_title text, notification_body text, actor_id integer DEFAULT NULL::integer, program_ref integer DEFAULT NULL::integer, ref_type text DEFAULT NULL::text, ref_id integer DEFAULT NULL::integer) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
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


--
-- Name: sibima_n2_grade_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sibima_n2_grade_trigger() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
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


--
-- Name: sibima_n2_schedule_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sibima_n2_schedule_trigger() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
DECLARE target_row record; pname text; notes text;
BEGIN
 IF (OLD.program_id,OLD.tutor_id,OLD.hari,OLD.jam_mulai,OLD.jam_selesai,OLD.room_id,OLD.aktif)
   IS NOT DISTINCT FROM
    (NEW.program_id,NEW.tutor_id,NEW.hari,NEW.jam_mulai,NEW.jam_selesai,NEW.room_id,NEW.aktif)
 THEN RETURN NEW; END IF;
 SELECT nama INTO pname FROM public.programs WHERE id=NEW.program_id;
 notes := 'Jadwal '||coalesce(pname,'kelas')||' diperbarui. Hari: '||NEW.hari::text||
   ', jam: '||NEW.jam_mulai::text||'â€“'||NEW.jam_selesai::text||
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


--
-- Name: sibima_n2_session_trigger(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sibima_n2_session_trigger() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
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


SET default_table_access_method = heap;

--
-- Name: activity_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.activity_logs (
    id bigint NOT NULL,
    user_id integer,
    aksi character varying(60) NOT NULL,
    detail text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: activity_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.activity_logs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.activity_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: announcement_reads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.announcement_reads (
    announcement_id integer NOT NULL,
    user_id integer NOT NULL,
    read_at timestamp with time zone DEFAULT now() NOT NULL,
    archived_at timestamp with time zone
);


--
-- Name: announcement_targets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.announcement_targets (
    announcement_id integer NOT NULL,
    target_role public.user_role NOT NULL,
    CONSTRAINT announcement_targets_target_role_check CHECK ((target_role = ANY (ARRAY['siswa'::public.user_role, 'tutor'::public.user_role])))
);


--
-- Name: announcements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.announcements (
    id integer NOT NULL,
    judul character varying(150) NOT NULL,
    isi text NOT NULL,
    dibuat_by integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    archived_at timestamp with time zone,
    penerima_user_id integer,
    sumber character varying(20) DEFAULT 'admin'::character varying NOT NULL,
    kategori character varying(30) DEFAULT 'umum'::character varying NOT NULL,
    event_key text,
    expires_at timestamp with time zone,
    program_id integer,
    batch_key text,
    actor_user_id integer,
    related_type character varying(30),
    related_id integer
);


--
-- Name: announcements_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.announcements ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.announcements_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: attendances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attendances (
    session_id integer NOT NULL,
    student_id integer NOT NULL,
    status public.attendance_status NOT NULL,
    keterangan character varying(200),
    dicatat_at timestamp with time zone DEFAULT now() NOT NULL,
    enrollment_id integer
);


--
-- Name: class_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.class_sessions (
    id integer NOT NULL,
    schedule_id integer NOT NULL,
    tanggal date NOT NULL,
    pertemuan_ke smallint NOT NULL,
    topik character varying(150),
    ringkasan text,
    status public.session_status DEFAULT 'perlu_laporan'::public.session_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    alasan_batal character varying(500),
    selesai_at timestamp with time zone,
    CONSTRAINT class_sessions_pertemuan_ke_check CHECK ((pertemuan_ke > 0))
);


--
-- Name: class_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.class_sessions ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.class_sessions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: enrollments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.enrollments (
    id integer NOT NULL,
    student_id integer NOT NULL,
    program_id integer NOT NULL,
    status public.enrollment_status DEFAULT 'menunggu'::public.enrollment_status NOT NULL,
    alasan_tolak text,
    processed_by integer,
    processed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: enrollments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.enrollments ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.enrollments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: grades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grades (
    id integer NOT NULL,
    enrollment_id integer NOT NULL,
    jenis public.grade_type NOT NULL,
    judul character varying(100),
    nilai numeric(5,2) NOT NULL,
    tanggal date DEFAULT CURRENT_DATE NOT NULL,
    input_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT grades_nilai_check CHECK (((nilai >= (0)::numeric) AND (nilai <= (100)::numeric)))
);


--
-- Name: grades_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.grades ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.grades_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: invoice_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.invoice_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: invoices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.invoices (
    id integer NOT NULL,
    no_invoice character varying(30) DEFAULT public.fn_next_invoice() NOT NULL,
    enrollment_id integer NOT NULL,
    periode date NOT NULL,
    jumlah numeric(12,2) NOT NULL,
    jatuh_tempo date NOT NULL,
    status public.invoice_status DEFAULT 'belum_dibayar'::public.invoice_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT invoices_jumlah_check CHECK ((jumlah >= (0)::numeric)),
    CONSTRAINT invoices_periode_check CHECK ((EXTRACT(day FROM periode) = (1)::numeric))
);


--
-- Name: invoices_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.invoices ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.invoices_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: kode_tutor_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.kode_tutor_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nis_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nis_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: otp_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.otp_codes (
    id integer NOT NULL,
    user_id integer NOT NULL,
    code_hash text NOT NULL,
    purpose public.otp_purpose NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    attempts smallint DEFAULT 0 NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT otp_codes_attempts_check CHECK ((attempts >= 0))
);


--
-- Name: otp_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.otp_codes ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.otp_codes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: payment_refunds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payment_refunds (
    id integer NOT NULL,
    payment_id integer NOT NULL,
    kode_refund character varying(40) NOT NULL,
    jumlah numeric(12,2) NOT NULL,
    alasan text NOT NULL,
    status character varying(20) DEFAULT 'berhasil'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    processed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT payment_refunds_jumlah_check CHECK ((jumlah > (0)::numeric)),
    CONSTRAINT payment_refunds_status_check CHECK (((status)::text = ANY ((ARRAY['berhasil'::character varying, 'gagal'::character varying])::text[])))
);


--
-- Name: payment_refunds_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.payment_refunds ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.payment_refunds_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payments (
    id integer NOT NULL,
    invoice_id integer NOT NULL,
    kode_bayar character varying(30) NOT NULL,
    jumlah numeric(12,2) NOT NULL,
    status public.payment_status DEFAULT 'menunggu_pembayaran'::public.payment_status NOT NULL,
    paid_at timestamp with time zone,
    processed_by integer,
    processed_at timestamp with time zone,
    alasan_tolak text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT payments_jumlah_check CHECK ((jumlah > (0)::numeric))
);


--
-- Name: payments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.payments ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.payments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: programs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.programs (
    id integer NOT NULL,
    kode character varying(10) NOT NULL,
    nama character varying(100) NOT NULL,
    jenjang character varying(20) NOT NULL,
    deskripsi text,
    harga_bulanan numeric(12,2) NOT NULL,
    kuota smallint NOT NULL,
    status public.program_status DEFAULT 'buka'::public.program_status NOT NULL,
    bobot_tugas smallint DEFAULT 30 NOT NULL,
    bobot_kuis smallint DEFAULT 20 NOT NULL,
    bobot_uts smallint DEFAULT 20 NOT NULL,
    bobot_uas smallint DEFAULT 30 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_bobot_total CHECK (((((bobot_tugas + bobot_kuis) + bobot_uts) + bobot_uas) = 100)),
    CONSTRAINT programs_bobot_kuis_check CHECK (((bobot_kuis >= 0) AND (bobot_kuis <= 100))),
    CONSTRAINT programs_bobot_tugas_check CHECK (((bobot_tugas >= 0) AND (bobot_tugas <= 100))),
    CONSTRAINT programs_bobot_uas_check CHECK (((bobot_uas >= 0) AND (bobot_uas <= 100))),
    CONSTRAINT programs_bobot_uts_check CHECK (((bobot_uts >= 0) AND (bobot_uts <= 100))),
    CONSTRAINT programs_harga_bulanan_check CHECK ((harga_bulanan >= (0)::numeric)),
    CONSTRAINT programs_kuota_check CHECK ((kuota > 0))
);


--
-- Name: programs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.programs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.programs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: rooms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rooms (
    id integer NOT NULL,
    nama character varying(30) NOT NULL,
    kapasitas smallint NOT NULL,
    aktif boolean DEFAULT true NOT NULL,
    CONSTRAINT rooms_kapasitas_check CHECK ((kapasitas > 0))
);


--
-- Name: rooms_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.rooms ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.rooms_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schedules (
    id integer NOT NULL,
    program_id integer NOT NULL,
    tutor_id integer NOT NULL,
    room_id integer NOT NULL,
    hari public.nama_hari NOT NULL,
    jam_mulai time without time zone NOT NULL,
    jam_selesai time without time zone NOT NULL,
    aktif boolean DEFAULT true NOT NULL,
    notif_monitor_from timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_jam_valid CHECK ((jam_mulai < jam_selesai))
);


--
-- Name: schedules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.schedules ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.schedules_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: students; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.students (
    user_id integer NOT NULL,
    role public.user_role DEFAULT 'siswa'::public.user_role NOT NULL,
    nis character varying(10),
    jenjang character varying(20),
    sekolah character varying(100),
    no_hp character varying(20),
    nama_wali character varying(100),
    CONSTRAINT students_role_check CHECK ((role = 'siswa'::public.user_role))
);


--
-- Name: tutors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tutors (
    user_id integer NOT NULL,
    role public.user_role DEFAULT 'tutor'::public.user_role NOT NULL,
    kode_tutor character varying(10),
    keahlian character varying(150),
    no_hp character varying(20),
    CONSTRAINT tutors_role_check CHECK ((role = 'tutor'::public.user_role))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(30) NOT NULL,
    email character varying(120) NOT NULL,
    nama_lengkap character varying(100) NOT NULL,
    password_hash text NOT NULL,
    role public.user_role NOT NULL,
    status public.user_status DEFAULT 'belum_verifikasi'::public.user_status NOT NULL,
    email_verified boolean DEFAULT false NOT NULL,
    failed_attempts smallint DEFAULT 0 NOT NULL,
    locked_until timestamp with time zone,
    must_change_password boolean DEFAULT false NOT NULL,
    approved_by integer,
    approved_at timestamp with time zone,
    reject_reason text,
    last_login timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_email_format CHECK (((email)::text ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'::text)),
    CONSTRAINT ck_username_format CHECK (((username)::text ~ '^[a-zA-Z0-9_]{4,30}$'::text)),
    CONSTRAINT users_failed_attempts_check CHECK ((failed_attempts >= 0))
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.users ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: v_nilai_akhir; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_nilai_akhir AS
 WITH rata AS (
         SELECT grades.enrollment_id,
            grades.jenis,
            avg(grades.nilai) AS rata
           FROM public.grades
          GROUP BY grades.enrollment_id, grades.jenis
        ), pivot AS (
         SELECT rata.enrollment_id,
            max(rata.rata) FILTER (WHERE (rata.jenis = 'tugas'::public.grade_type)) AS tugas,
            max(rata.rata) FILTER (WHERE (rata.jenis = 'kuis'::public.grade_type)) AS kuis,
            max(rata.rata) FILTER (WHERE (rata.jenis = 'uts'::public.grade_type)) AS uts,
            max(rata.rata) FILTER (WHERE (rata.jenis = 'uas'::public.grade_type)) AS uas
           FROM rata
          GROUP BY rata.enrollment_id
        )
 SELECT e.id AS enrollment_id,
    e.student_id,
    e.program_id,
    round(pv.tugas, 2) AS tugas,
    round(pv.kuis, 2) AS kuis,
    round(pv.uts, 2) AS uts,
    round(pv.uas, 2) AS uas,
    round(((((COALESCE((pv.tugas * (p.bobot_tugas)::numeric), (0)::numeric) + COALESCE((pv.kuis * (p.bobot_kuis)::numeric), (0)::numeric)) + COALESCE((pv.uts * (p.bobot_uts)::numeric), (0)::numeric)) + COALESCE((pv.uas * (p.bobot_uas)::numeric), (0)::numeric)) / (NULLIF((((
        CASE
            WHEN (pv.tugas IS NOT NULL) THEN (p.bobot_tugas)::integer
            ELSE 0
        END +
        CASE
            WHEN (pv.kuis IS NOT NULL) THEN (p.bobot_kuis)::integer
            ELSE 0
        END) +
        CASE
            WHEN (pv.uts IS NOT NULL) THEN (p.bobot_uts)::integer
            ELSE 0
        END) +
        CASE
            WHEN (pv.uas IS NOT NULL) THEN (p.bobot_uas)::integer
            ELSE 0
        END), 0))::numeric), 2) AS nilai_akhir
   FROM ((public.enrollments e
     JOIN public.programs p ON ((p.id = e.program_id)))
     LEFT JOIN pivot pv ON ((pv.enrollment_id = e.id)));


--
-- Name: v_pemasukan_bulanan; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_pemasukan_bulanan AS
 SELECT (date_trunc('month'::text, paid_at))::date AS bulan,
    count(*) AS jumlah_transaksi,
    sum(jumlah) AS total_pemasukan
   FROM public.payments
  WHERE (status = 'lunas'::public.payment_status)
  GROUP BY ((date_trunc('month'::text, paid_at))::date);


--
-- Name: v_program_kuota; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_program_kuota AS
SELECT
    NULL::integer AS program_id,
    NULL::character varying(10) AS kode,
    NULL::character varying(100) AS nama,
    NULL::smallint AS kuota,
    NULL::bigint AS terisi,
    NULL::bigint AS sisa;


--
-- Name: v_rekap_kehadiran; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_rekap_kehadiran AS
 SELECT e.student_id,
    e.program_id,
    r.total_pertemuan,
    r.hadir,
    r.izin,
    r.sakit,
    r.alpa,
    r.persen_hadir,
    e.id AS enrollment_id,
    (e.status)::text AS status_enrollment,
    (e.created_at)::date AS tanggal_pendaftaran
   FROM (public.enrollments e
     CROSS JOIN LATERAL ( SELECT count(*) AS total_pertemuan,
            count(*) FILTER (WHERE (a.status = 'H'::public.attendance_status)) AS hadir,
            count(*) FILTER (WHERE (a.status = 'I'::public.attendance_status)) AS izin,
            count(*) FILTER (WHERE (a.status = 'S'::public.attendance_status)) AS sakit,
            count(*) FILTER (WHERE (a.status = 'A'::public.attendance_status)) AS alpa,
            round(((100.0 * (count(*) FILTER (WHERE (a.status = 'H'::public.attendance_status)))::numeric) / (NULLIF(count(*), 0))::numeric), 1) AS persen_hadir
           FROM ((public.attendances a
             JOIN public.class_sessions cs ON (((cs.id = a.session_id) AND (cs.status = 'selesai'::public.session_status))))
             JOIN public.schedules s ON (((s.id = cs.schedule_id) AND (s.program_id = e.program_id))))
          WHERE ((a.enrollment_id = e.id) AND (a.student_id = e.student_id))) r)
  WHERE (e.status = ANY (ARRAY['aktif'::public.enrollment_status, 'selesai'::public.enrollment_status, 'batal'::public.enrollment_status]));


--
-- Name: v_tagihan_status; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_tagihan_status AS
SELECT
    NULL::integer AS invoice_id,
    NULL::character varying(30) AS no_invoice,
    NULL::integer AS enrollment_id,
    NULL::integer AS student_id,
    NULL::date AS periode,
    NULL::date AS jatuh_tempo,
    NULL::public.invoice_status AS status,
    NULL::numeric(12,2) AS jumlah,
    NULL::numeric(12,2) AS total_tagihan,
    NULL::numeric AS terbayar;


--
-- Name: activity_logs activity_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_pkey PRIMARY KEY (id);


--
-- Name: announcement_reads announcement_reads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcement_reads
    ADD CONSTRAINT announcement_reads_pkey PRIMARY KEY (announcement_id, user_id);


--
-- Name: announcement_targets announcement_targets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcement_targets
    ADD CONSTRAINT announcement_targets_pkey PRIMARY KEY (announcement_id, target_role);


--
-- Name: announcements announcements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT announcements_pkey PRIMARY KEY (id);


--
-- Name: attendances attendances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendances
    ADD CONSTRAINT attendances_pkey PRIMARY KEY (session_id, student_id);


--
-- Name: class_sessions class_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_sessions
    ADD CONSTRAINT class_sessions_pkey PRIMARY KEY (id);


--
-- Name: enrollments enrollments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_pkey PRIMARY KEY (id);


--
-- Name: schedules ex_bentrok_ruang; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT ex_bentrok_ruang EXCLUDE USING gist (room_id WITH =, hari WITH =, public.timerange(jam_mulai, jam_selesai) WITH &&) WHERE (aktif);


--
-- Name: schedules ex_bentrok_tutor; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT ex_bentrok_tutor EXCLUDE USING gist (tutor_id WITH =, hari WITH =, public.timerange(jam_mulai, jam_selesai) WITH &&) WHERE (aktif);


--
-- Name: grades grades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_pkey PRIMARY KEY (id);


--
-- Name: invoices invoices_no_invoice_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_no_invoice_key UNIQUE (no_invoice);


--
-- Name: invoices invoices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_pkey PRIMARY KEY (id);


--
-- Name: otp_codes otp_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.otp_codes
    ADD CONSTRAINT otp_codes_pkey PRIMARY KEY (id);


--
-- Name: payment_refunds payment_refunds_kode_refund_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_refunds
    ADD CONSTRAINT payment_refunds_kode_refund_key UNIQUE (kode_refund);


--
-- Name: payment_refunds payment_refunds_payment_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_refunds
    ADD CONSTRAINT payment_refunds_payment_id_key UNIQUE (payment_id);


--
-- Name: payment_refunds payment_refunds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_refunds
    ADD CONSTRAINT payment_refunds_pkey PRIMARY KEY (id);


--
-- Name: payments payments_kode_bayar_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_kode_bayar_key UNIQUE (kode_bayar);


--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- Name: programs programs_kode_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.programs
    ADD CONSTRAINT programs_kode_key UNIQUE (kode);


--
-- Name: programs programs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.programs
    ADD CONSTRAINT programs_pkey PRIMARY KEY (id);


--
-- Name: rooms rooms_nama_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_nama_key UNIQUE (nama);


--
-- Name: rooms rooms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_pkey PRIMARY KEY (id);


--
-- Name: schedules schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT schedules_pkey PRIMARY KEY (id);


--
-- Name: students students_nis_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_nis_key UNIQUE (nis);


--
-- Name: students students_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_pkey PRIMARY KEY (user_id);


--
-- Name: tutors tutors_kode_tutor_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tutors
    ADD CONSTRAINT tutors_kode_tutor_key UNIQUE (kode_tutor);


--
-- Name: tutors tutors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tutors
    ADD CONSTRAINT tutors_pkey PRIMARY KEY (user_id);


--
-- Name: invoices uq_invoice_periode; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT uq_invoice_periode UNIQUE (enrollment_id, periode);


--
-- Name: class_sessions uq_session_ke; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_sessions
    ADD CONSTRAINT uq_session_ke UNIQUE (schedule_id, pertemuan_ke);


--
-- Name: class_sessions uq_session_tanggal; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_sessions
    ADD CONSTRAINT uq_session_tanggal UNIQUE (schedule_id, tanggal);


--
-- Name: users uq_users_id_role; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_id_role UNIQUE (id, role);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_announcement_reads_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_announcement_reads_user ON public.announcement_reads USING btree (user_id, announcement_id);


--
-- Name: idx_announcement_targets_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_announcement_targets_role ON public.announcement_targets USING btree (target_role, announcement_id);


--
-- Name: idx_announcements_aktif; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_announcements_aktif ON public.announcements USING btree (created_at DESC, id DESC) WHERE (archived_at IS NULL);


--
-- Name: idx_attend_enrollment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_attend_enrollment ON public.attendances USING btree (enrollment_id) WHERE (enrollment_id IS NOT NULL);


--
-- Name: idx_attend_student; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_attend_student ON public.attendances USING btree (student_id);


--
-- Name: idx_enroll_program; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_enroll_program ON public.enrollments USING btree (program_id, status);


--
-- Name: idx_grades_enroll; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_grades_enroll ON public.grades USING btree (enrollment_id, jenis);


--
-- Name: idx_invoices_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_invoices_status ON public.invoices USING btree (status, jatuh_tempo);


--
-- Name: idx_logs_waktu; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_logs_waktu ON public.activity_logs USING btree (created_at DESC);


--
-- Name: idx_otp_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_otp_user ON public.otp_codes USING btree (user_id, purpose, created_at DESC);


--
-- Name: idx_payment_refunds_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_payment_refunds_status ON public.payment_refunds USING btree (status, created_at);


--
-- Name: idx_payments_invoice; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_payments_invoice ON public.payments USING btree (invoice_id);


--
-- Name: idx_payments_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_payments_status ON public.payments USING btree (status, created_at);


--
-- Name: idx_schedules_program; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_schedules_program ON public.schedules USING btree (program_id);


--
-- Name: idx_schedules_tutor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_schedules_tutor ON public.schedules USING btree (tutor_id, hari);


--
-- Name: idx_users_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_status ON public.users USING btree (status, role);


--
-- Name: sibima_n1_event_key_uniq; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX sibima_n1_event_key_uniq ON public.announcements USING btree (event_key) WHERE (event_key IS NOT NULL);


--
-- Name: sibima_n1_private_inbox_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sibima_n1_private_inbox_idx ON public.announcements USING btree (penerima_user_id, created_at DESC) WHERE ((archived_at IS NULL) AND (penerima_user_id IS NOT NULL));


--
-- Name: sibima_n2_read_arch_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sibima_n2_read_arch_idx ON public.announcement_reads USING btree (user_id, archived_at);


--
-- Name: sibima_n2_related_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sibima_n2_related_idx ON public.announcements USING btree (related_type, related_id) WHERE (related_type IS NOT NULL);


--
-- Name: sibima_n2_tutor_batch_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX sibima_n2_tutor_batch_idx ON public.announcements USING btree (dibuat_by, batch_key) WHERE (((sumber)::text = 'tutor'::text) AND (batch_key IS NOT NULL));


--
-- Name: uq_enrollment_berjalan; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_enrollment_berjalan ON public.enrollments USING btree (student_id, program_id) WHERE (status = ANY (ARRAY['menunggu_pembayaran'::public.enrollment_status, 'menunggu'::public.enrollment_status, 'aktif'::public.enrollment_status]));


--
-- Name: uq_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_users_email ON public.users USING btree (lower((email)::text));


--
-- Name: uq_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_users_username ON public.users USING btree (lower((username)::text));


--
-- Name: v_program_kuota _RETURN; Type: RULE; Schema: public; Owner: -
--

CREATE OR REPLACE VIEW public.v_program_kuota AS
 SELECT p.id AS program_id,
    p.kode,
    p.nama,
    p.kuota,
    count(e.id) FILTER (WHERE (e.status = ANY (ARRAY['menunggu_pembayaran'::public.enrollment_status, 'menunggu'::public.enrollment_status, 'aktif'::public.enrollment_status]))) AS terisi,
    (p.kuota - count(e.id) FILTER (WHERE (e.status = ANY (ARRAY['menunggu_pembayaran'::public.enrollment_status, 'menunggu'::public.enrollment_status, 'aktif'::public.enrollment_status])))) AS sisa
   FROM (public.programs p
     LEFT JOIN public.enrollments e ON ((e.program_id = p.id)))
  GROUP BY p.id;


--
-- Name: v_tagihan_status _RETURN; Type: RULE; Schema: public; Owner: -
--

CREATE OR REPLACE VIEW public.v_tagihan_status AS
 SELECT i.id AS invoice_id,
    i.no_invoice,
    i.enrollment_id,
    e.student_id,
    i.periode,
    i.jatuh_tempo,
    i.status,
    i.jumlah,
    i.jumlah AS total_tagihan,
    COALESCE(sum(p.jumlah) FILTER (WHERE (p.status = 'lunas'::public.payment_status)), (0)::numeric) AS terbayar
   FROM ((public.invoices i
     JOIN public.enrollments e ON ((e.id = i.enrollment_id)))
     LEFT JOIN public.payments p ON ((p.invoice_id = i.id)))
  GROUP BY i.id, e.student_id;


--
-- Name: enrollments sibima_n1_enroll_insert; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n1_enroll_insert AFTER INSERT ON public.enrollments FOR EACH ROW EXECUTE FUNCTION public.sibima_n1_enrollment_trigger();


--
-- Name: enrollments sibima_n1_enroll_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n1_enroll_update AFTER UPDATE OF status ON public.enrollments FOR EACH ROW WHEN ((old.status IS DISTINCT FROM new.status)) EXECUTE FUNCTION public.sibima_n1_enrollment_trigger();


--
-- Name: invoices sibima_n1_invoice_insert; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n1_invoice_insert AFTER INSERT ON public.invoices FOR EACH ROW EXECUTE FUNCTION public.sibima_n1_invoices_trigger();


--
-- Name: payments sibima_n1_payment_insert; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n1_payment_insert AFTER INSERT ON public.payments FOR EACH ROW EXECUTE FUNCTION public.sibima_n1_payments_trigger();


--
-- Name: payments sibima_n1_payment_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n1_payment_update AFTER UPDATE OF status ON public.payments FOR EACH ROW WHEN ((old.status IS DISTINCT FROM new.status)) EXECUTE FUNCTION public.sibima_n1_payments_trigger();


--
-- Name: users sibima_n1_users_after_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n1_users_after_update AFTER UPDATE OF status ON public.users FOR EACH ROW WHEN ((old.status IS DISTINCT FROM new.status)) EXECUTE FUNCTION public.sibima_n1_users_trigger();


--
-- Name: attendances sibima_n2_attendance_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n2_attendance_updated AFTER UPDATE ON public.attendances FOR EACH ROW EXECUTE FUNCTION public.sibima_n2_attendance_trigger();


--
-- Name: grades sibima_n2_grade_insert; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n2_grade_insert AFTER INSERT ON public.grades FOR EACH ROW EXECUTE FUNCTION public.sibima_n2_grade_trigger();


--
-- Name: grades sibima_n2_grade_update; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n2_grade_update AFTER UPDATE ON public.grades FOR EACH ROW EXECUTE FUNCTION public.sibima_n2_grade_trigger();


--
-- Name: schedules sibima_n2_schedule_changed; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n2_schedule_changed AFTER UPDATE OF program_id, tutor_id, hari, jam_mulai, jam_selesai, room_id, aktif ON public.schedules FOR EACH ROW EXECUTE FUNCTION public.sibima_n2_schedule_trigger();


--
-- Name: class_sessions sibima_n2_session_finished; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER sibima_n2_session_finished AFTER UPDATE OF status ON public.class_sessions FOR EACH ROW EXECUTE FUNCTION public.sibima_n2_session_trigger();


--
-- Name: payments trg_validate_full_payment; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_validate_full_payment BEFORE INSERT OR UPDATE OF invoice_id, jumlah ON public.payments FOR EACH ROW EXECUTE FUNCTION public.fn_validate_full_payment();


--
-- Name: activity_logs activity_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.activity_logs
    ADD CONSTRAINT activity_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: announcement_reads announcement_reads_announcement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcement_reads
    ADD CONSTRAINT announcement_reads_announcement_id_fkey FOREIGN KEY (announcement_id) REFERENCES public.announcements(id) ON DELETE CASCADE;


--
-- Name: announcement_reads announcement_reads_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcement_reads
    ADD CONSTRAINT announcement_reads_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: announcement_targets announcement_targets_announcement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcement_targets
    ADD CONSTRAINT announcement_targets_announcement_id_fkey FOREIGN KEY (announcement_id) REFERENCES public.announcements(id) ON DELETE CASCADE;


--
-- Name: announcements announcements_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT announcements_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id);


--
-- Name: announcements announcements_dibuat_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT announcements_dibuat_by_fkey FOREIGN KEY (dibuat_by) REFERENCES public.users(id);


--
-- Name: announcements announcements_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT announcements_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: attendances attendances_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendances
    ADD CONSTRAINT attendances_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.class_sessions(id) ON DELETE CASCADE;


--
-- Name: attendances attendances_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendances
    ADD CONSTRAINT attendances_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.students(user_id);


--
-- Name: class_sessions class_sessions_schedule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_sessions
    ADD CONSTRAINT class_sessions_schedule_id_fkey FOREIGN KEY (schedule_id) REFERENCES public.schedules(id);


--
-- Name: enrollments enrollments_processed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_processed_by_fkey FOREIGN KEY (processed_by) REFERENCES public.users(id);


--
-- Name: enrollments enrollments_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: enrollments enrollments_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.students(user_id);


--
-- Name: attendances fk_attendances_enrollment; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendances
    ADD CONSTRAINT fk_attendances_enrollment FOREIGN KEY (enrollment_id) REFERENCES public.enrollments(id);


--
-- Name: grades grades_enrollment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_enrollment_id_fkey FOREIGN KEY (enrollment_id) REFERENCES public.enrollments(id);


--
-- Name: grades grades_input_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.grades
    ADD CONSTRAINT grades_input_by_fkey FOREIGN KEY (input_by) REFERENCES public.tutors(user_id);


--
-- Name: invoices invoices_enrollment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_enrollment_id_fkey FOREIGN KEY (enrollment_id) REFERENCES public.enrollments(id);


--
-- Name: otp_codes otp_codes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.otp_codes
    ADD CONSTRAINT otp_codes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: payment_refunds payment_refunds_payment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_refunds
    ADD CONSTRAINT payment_refunds_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES public.payments(id);


--
-- Name: payments payments_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id);


--
-- Name: payments payments_processed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_processed_by_fkey FOREIGN KEY (processed_by) REFERENCES public.users(id);


--
-- Name: schedules schedules_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT schedules_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.programs(id);


--
-- Name: schedules schedules_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT schedules_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(id);


--
-- Name: schedules schedules_tutor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schedules
    ADD CONSTRAINT schedules_tutor_id_fkey FOREIGN KEY (tutor_id) REFERENCES public.tutors(user_id);


--
-- Name: announcements sibima_n1_recipient_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT sibima_n1_recipient_fk FOREIGN KEY (penerima_user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: students students_user_id_role_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_user_id_role_fkey FOREIGN KEY (user_id, role) REFERENCES public.users(id, role) ON DELETE CASCADE;


--
-- Name: tutors tutors_user_id_role_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tutors
    ADD CONSTRAINT tutors_user_id_role_fkey FOREIGN KEY (user_id, role) REFERENCES public.users(id, role) ON DELETE CASCADE;


--
-- Name: users users_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id);


--
-- PostgreSQL database dump complete
--

\unrestrict C2W58oX5fQsoUQ5wDv7ez6cXaHpnxleZZncEWIXhIkg0JEaVIZzubNYYg3gMsA1

