-- Perbaiki hak baca untuk laporan SIBIMA.
-- Jalankan sebagai postgres atau akun pemilik objek database.
-- Perintah ini hanya memberikan hak SELECT; tidak mengubah isi atau skema data.

BEGIN;
GRANT USAGE ON SCHEMA public TO bimbel_user;

-- View yang dipakai report_repo.py.
GRANT SELECT ON TABLE
    public.v_pemasukan_bulanan,
    public.v_rekap_kehadiran,
    public.v_nilai_akhir
TO bimbel_user;

-- Tabel dasar yang dibaca langsung oleh query laporan dan yang digunakan
-- apabila pemilik view adalah bimbel_user.
GRANT SELECT ON TABLE
    public.programs,
    public.enrollments,
    public.students,
    public.users,
    public.payments,
    public.attendances,
    public.class_sessions,
    public.schedules,
    public.grades
TO bimbel_user;

COMMIT;

-- Verifikasi hak akses view yang langsung dibaca oleh laporan.
SELECT
    has_table_privilege('bimbel_user', 'public.v_pemasukan_bulanan', 'SELECT') AS pemasukan_bulanan,
    has_table_privilege('bimbel_user', 'public.v_rekap_kehadiran', 'SELECT') AS rekap_kehadiran,
    has_table_privilege('bimbel_user', 'public.v_nilai_akhir', 'SELECT') AS nilai_akhir;
