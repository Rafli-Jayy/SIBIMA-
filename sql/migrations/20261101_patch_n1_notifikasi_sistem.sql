-- PATCH-N1: Notifikasi sistem pribadi. PostgreSQL 13+; khusus bimbel_db.
-- Jalankan dengan psql -X -v ON_ERROR_STOP=1 -U postgres -d bimbel_db -f ...
-- Tidak menghapus atau mengubah isi notifikasi lama; hanya schema tambahan dan triggers.
BEGIN;
DO $$
BEGIN
  IF current_database() <> 'bimbel_db' THEN
    RAISE EXCEPTION 'PATCH-N1 hanya boleh dipasang pada bimbel_db';
  END IF;
  IF to_regclass('public.users') IS NULL OR to_regclass('public.announcements') IS NULL
    OR to_regclass('public.announcement_targets') IS NULL
    OR to_regclass('public.announcement_reads') IS NULL
    OR to_regclass('public.enrollments') IS NULL OR to_regclass('public.programs') IS NULL
    OR to_regclass('public.invoices') IS NULL OR to_regclass('public.payments') IS NULL THEN
    RAISE EXCEPTION 'Struktur tabel SIBIMA belum sesuai PATCH-N1';
  END IF;
END $$;

ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS penerima_user_id integer;
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS sumber varchar(20) NOT NULL DEFAULT 'admin';
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS kategori varchar(30) NOT NULL DEFAULT 'umum';
ALTER TABLE public.announcements ADD COLUMN IF NOT EXISTS event_key text;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint c JOIN pg_attribute a
    ON a.attrelid = c.conrelid AND a.attname = 'penerima_user_id'
    WHERE c.conrelid = 'public.announcements'::regclass AND c.contype = 'f'
      AND a.attnum = ANY(c.conkey) AND c.confrelid = 'public.users'::regclass
  ) THEN
    ALTER TABLE public.announcements ADD CONSTRAINT sibima_n1_recipient_fk
      FOREIGN KEY (penerima_user_id) REFERENCES public.users(id) ON DELETE CASCADE;
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS sibima_n1_event_key_uniq
  ON public.announcements(event_key) WHERE event_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS sibima_n1_private_inbox_idx
  ON public.announcements(penerima_user_id, created_at DESC)
  WHERE archived_at IS NULL AND penerima_user_id IS NOT NULL;

-- Internal-only writer: trigger runs as table owner's trusted role, not from chat/UI.
CREATE OR REPLACE FUNCTION public.sibima_n1_emit(
  target_id integer, category_name text, unique_event_key text,
  notification_title text, notification_body text, actor_id integer DEFAULT NULL
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE author_id integer;
BEGIN
  IF target_id IS NULL OR unique_event_key IS NULL THEN RETURN; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = target_id) THEN RETURN; END IF;
  author_id := COALESCE(actor_id, target_id);
  IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = author_id) THEN author_id := target_id; END IF;
  INSERT INTO public.announcements
    (judul, isi, dibuat_by, penerima_user_id, sumber, kategori, event_key)
  VALUES
    (left(notification_title, 150), left(notification_body, 4000), author_id,
     target_id, 'sistem', category_name, unique_event_key)
  ON CONFLICT DO NOTHING;
END $$;
REVOKE ALL ON FUNCTION public.sibima_n1_emit(integer,text,text,text,text,integer) FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.sibima_n1_users_trigger()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
DROP TRIGGER IF EXISTS sibima_n1_users_after_update ON public.users;
CREATE TRIGGER sibima_n1_users_after_update AFTER UPDATE OF status ON public.users
FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION public.sibima_n1_users_trigger();

CREATE OR REPLACE FUNCTION public.sibima_n1_enrollment_trigger()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
DROP TRIGGER IF EXISTS sibima_n1_enroll_insert ON public.enrollments;
DROP TRIGGER IF EXISTS sibima_n1_enroll_update ON public.enrollments;
CREATE TRIGGER sibima_n1_enroll_insert AFTER INSERT ON public.enrollments
FOR EACH ROW EXECUTE FUNCTION public.sibima_n1_enrollment_trigger();
CREATE TRIGGER sibima_n1_enroll_update AFTER UPDATE OF status ON public.enrollments
FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION public.sibima_n1_enrollment_trigger();

CREATE OR REPLACE FUNCTION public.sibima_n1_invoices_trigger()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
DROP TRIGGER IF EXISTS sibima_n1_invoice_insert ON public.invoices;
CREATE TRIGGER sibima_n1_invoice_insert AFTER INSERT ON public.invoices
FOR EACH ROW EXECUTE FUNCTION public.sibima_n1_invoices_trigger();

CREATE OR REPLACE FUNCTION public.sibima_n1_payments_trigger()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
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
DROP TRIGGER IF EXISTS sibima_n1_payment_insert ON public.payments;
DROP TRIGGER IF EXISTS sibima_n1_payment_update ON public.payments;
CREATE TRIGGER sibima_n1_payment_insert AFTER INSERT ON public.payments
FOR EACH ROW EXECUTE FUNCTION public.sibima_n1_payments_trigger();
CREATE TRIGGER sibima_n1_payment_update AFTER UPDATE OF status ON public.payments
FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION public.sibima_n1_payments_trigger();
-- Penggunaan trigger hanya oleh PostgreSQL, bukan panggilan langsung dari akun aplikasi.
REVOKE ALL ON FUNCTION public.sibima_n1_users_trigger() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.sibima_n1_enrollment_trigger() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.sibima_n1_invoices_trigger() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.sibima_n1_payments_trigger() FROM PUBLIC;
COMMIT;
