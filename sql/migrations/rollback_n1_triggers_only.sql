-- Rollback konservatif: NONAKTIFKAN pemicu PATCH-N1, TANPA menghapus notifikasi atau data.
-- Perubahan kolom announcements tetap dipertahankan demi keamanan data historis.
BEGIN;
DO $$ BEGIN
 IF current_database() <> 'bimbel_db' THEN
  RAISE EXCEPTION 'Rollback N1 hanya untuk bimbel_db';
 END IF;
END $$;
DROP TRIGGER IF EXISTS sibima_n1_users_after_update ON public.users;
DROP TRIGGER IF EXISTS sibima_n1_enroll_insert ON public.enrollments;
DROP TRIGGER IF EXISTS sibima_n1_enroll_update ON public.enrollments;
DROP TRIGGER IF EXISTS sibima_n1_invoice_insert ON public.invoices;
DROP TRIGGER IF EXISTS sibima_n1_payment_insert ON public.payments;
DROP TRIGGER IF EXISTS sibima_n1_payment_update ON public.payments;
COMMIT;
