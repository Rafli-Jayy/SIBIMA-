-- =====================================================================
-- SIBIMA KECE - schema.sql
-- PostgreSQL 13 ke atas
-- Jalankan sebagai bimbel_user pada database bimbel_db:
--   psql -U bimbel_user -d bimbel_db -h localhost -v ON_ERROR_STOP=1 -f sql/schema.sql
-- Simpan file sebagai UTF-8. Komentar sengaja memakai ASCII saja.
-- =====================================================================

-- RESET (hapus semua objek). Buka komentar HANYA jika ingin mengulang dari nol.
-- DROP SCHEMA public CASCADE;
-- CREATE SCHEMA public;

-- Dibutuhkan untuk mencegah jadwal bentrok (exclusion constraint).
-- Jika gagal karena hak akses, jalankan sekali sebagai superuser postgres:
--   \c bimbel_db
--   CREATE EXTENSION btree_gist;
CREATE EXTENSION IF NOT EXISTS btree_gist;


BEGIN;

-- =====================================================================
-- 1. TIPE ENUM
-- =====================================================================
CREATE TYPE user_role         AS ENUM ('admin', 'tutor', 'siswa');
CREATE TYPE user_status       AS ENUM ('belum_verifikasi', 'menunggu_konfirmasi',
                                       'aktif', 'ditolak', 'nonaktif');
CREATE TYPE otp_purpose       AS ENUM ('register', 'reset_password', 'login');
CREATE TYPE program_status    AS ENUM ('buka', 'tutup');
CREATE TYPE nama_hari         AS ENUM ('senin', 'selasa', 'rabu', 'kamis',
                                       'jumat', 'sabtu', 'minggu');
CREATE TYPE enrollment_status AS ENUM ('menunggu', 'aktif', 'ditolak', 'batal', 'selesai');
CREATE TYPE invoice_status    AS ENUM ('belum_dibayar', 'lunas', 'batal');
CREATE TYPE payment_status    AS ENUM ('menunggu_pembayaran', 'menunggu_konfirmasi',
                                       'lunas', 'ditolak');
CREATE TYPE session_status    AS ENUM ('terlaksana', 'batal');
CREATE TYPE attendance_status AS ENUM ('H', 'I', 'S', 'A');   -- Hadir, Izin, Sakit, Alpa
CREATE TYPE grade_type        AS ENUM ('tugas', 'kuis', 'uts', 'uas');

-- Tipe range waktu (untuk deteksi jadwal bentrok)
CREATE TYPE timerange AS RANGE (subtype = time);


-- =====================================================================
-- 2. SEQUENCE DAN FUNGSI PENOMORAN OTOMATIS
-- =====================================================================
CREATE SEQUENCE nis_seq        START 1;
CREATE SEQUENCE kode_tutor_seq START 1;
CREATE SEQUENCE invoice_seq    START 1;

-- NIS: S-0001, S-0002, ...
CREATE FUNCTION fn_next_nis() RETURNS TEXT AS $$
    SELECT 'S-' || lpad(nextval('nis_seq')::text, 4, '0');
$$ LANGUAGE sql;

-- Kode tutor: T-001, T-002, ...
CREATE FUNCTION fn_next_kode_tutor() RETURNS TEXT AS $$
    SELECT 'T-' || lpad(nextval('kode_tutor_seq')::text, 3, '0');
$$ LANGUAGE sql;

-- No. invoice: INV-20261021-0001
CREATE FUNCTION fn_next_invoice() RETURNS TEXT AS $$
    SELECT 'INV-' || to_char(now(), 'YYYYMMDD') || '-' ||
           lpad(nextval('invoice_seq')::text, 4, '0');
$$ LANGUAGE sql;


-- =====================================================================
-- 3. AKUN DAN KEAMANAN
-- =====================================================================
CREATE TABLE users (
    id                   INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username             VARCHAR(30)  NOT NULL,
    email                VARCHAR(120) NOT NULL,
    nama_lengkap         VARCHAR(100) NOT NULL,
    password_hash        TEXT         NOT NULL,
    role                 user_role    NOT NULL,
    status               user_status  NOT NULL DEFAULT 'belum_verifikasi',
    email_verified       BOOLEAN      NOT NULL DEFAULT FALSE,
    failed_attempts      SMALLINT     NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    locked_until         TIMESTAMPTZ,
    must_change_password BOOLEAN      NOT NULL DEFAULT FALSE,
    approved_by          INT REFERENCES users(id),
    approved_at          TIMESTAMPTZ,
    reject_reason        TEXT,
    last_login           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_id_role   UNIQUE (id, role),
    CONSTRAINT ck_username_format CHECK (username ~ '^[a-zA-Z0-9_]{4,30}$'),
    CONSTRAINT ck_email_format    CHECK (email ~* '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$')
);
-- Username dan email unik tanpa membedakan huruf besar/kecil
CREATE UNIQUE INDEX uq_users_username ON users (lower(username));
CREATE UNIQUE INDEX uq_users_email    ON users (lower(email));
CREATE INDEX idx_users_status ON users (status, role);

CREATE TABLE otp_codes (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    INT         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash  TEXT        NOT NULL,                 -- simpan hash, bukan OTP asli
    purpose    otp_purpose NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts   SMALLINT    NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_otp_user ON otp_codes (user_id, purpose, created_at DESC);


-- =====================================================================
-- 4. PROFIL SISWA DAN TUTOR
-- Kolom role + foreign key gabungan memastikan baris students hanya
-- bisa menunjuk ke user ber-role 'siswa' (begitu juga tutors).
-- Admin tidak punya tabel profil.
-- =====================================================================
CREATE TABLE students (
    user_id   INT PRIMARY KEY,
    role      user_role NOT NULL DEFAULT 'siswa' CHECK (role = 'siswa'),
    nis       VARCHAR(10) UNIQUE,                    -- diisi saat admin menyetujui akun
    jenjang   VARCHAR(20),
    sekolah   VARCHAR(100),
    no_hp     VARCHAR(20),
    nama_wali VARCHAR(100),
    FOREIGN KEY (user_id, role) REFERENCES users (id, role) ON DELETE CASCADE
);

CREATE TABLE tutors (
    user_id             INT PRIMARY KEY,
    role                user_role NOT NULL DEFAULT 'tutor' CHECK (role = 'tutor'),
    kode_tutor          VARCHAR(10) UNIQUE,          -- diisi saat admin menyetujui akun
    keahlian            VARCHAR(150),
    no_hp               VARCHAR(20),
    FOREIGN KEY (user_id, role) REFERENCES users (id, role) ON DELETE CASCADE
);


-- =====================================================================
-- 5. DATA MASTER: PROGRAM, RUANG, JADWAL
-- =====================================================================
CREATE TABLE programs (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kode          VARCHAR(10)    NOT NULL UNIQUE,
    nama          VARCHAR(100)   NOT NULL,
    jenjang       VARCHAR(20)    NOT NULL,
    deskripsi     TEXT,
    harga_bulanan NUMERIC(12,2)  NOT NULL CHECK (harga_bulanan >= 0),
    kuota         SMALLINT       NOT NULL CHECK (kuota > 0),
    status        program_status NOT NULL DEFAULT 'buka',
    -- Bobot nilai (persen). Total harus 100.
    bobot_tugas   SMALLINT NOT NULL DEFAULT 30 CHECK (bobot_tugas BETWEEN 0 AND 100),
    bobot_kuis    SMALLINT NOT NULL DEFAULT 20 CHECK (bobot_kuis  BETWEEN 0 AND 100),
    bobot_uts     SMALLINT NOT NULL DEFAULT 20 CHECK (bobot_uts   BETWEEN 0 AND 100),
    bobot_uas     SMALLINT NOT NULL DEFAULT 30 CHECK (bobot_uas   BETWEEN 0 AND 100),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_bobot_total CHECK (bobot_tugas + bobot_kuis + bobot_uts + bobot_uas = 100)
);

CREATE TABLE rooms (
    id        INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nama      VARCHAR(30) NOT NULL UNIQUE,
    kapasitas SMALLINT    NOT NULL CHECK (kapasitas > 0),
    aktif     BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE TABLE schedules (
    id          INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    program_id  INT       NOT NULL REFERENCES programs(id),
    tutor_id    INT       NOT NULL REFERENCES tutors(user_id),
    room_id     INT       NOT NULL REFERENCES rooms(id),
    hari        nama_hari NOT NULL,
    jam_mulai   TIME      NOT NULL,
    jam_selesai TIME      NOT NULL,
    aktif       BOOLEAN   NOT NULL DEFAULT TRUE,
    CONSTRAINT ck_jam_valid CHECK (jam_mulai < jam_selesai),
    -- Tutor tidak boleh mengajar dua kelas pada hari dan jam yang beririsan
    CONSTRAINT ex_bentrok_tutor EXCLUDE USING gist (
        tutor_id WITH =, hari WITH =, timerange(jam_mulai, jam_selesai) WITH &&
    ) WHERE (aktif),
    -- Ruang tidak boleh dipakai dua kelas pada hari dan jam yang beririsan
    CONSTRAINT ex_bentrok_ruang EXCLUDE USING gist (
        room_id WITH =, hari WITH =, timerange(jam_mulai, jam_selesai) WITH &&
    ) WHERE (aktif)
);
CREATE INDEX idx_schedules_program ON schedules (program_id);
CREATE INDEX idx_schedules_tutor   ON schedules (tutor_id, hari);


-- =====================================================================
-- 6. PENDAFTARAN PROGRAM (ENROLLMENT)
-- Batal/ditolak cukup mengubah status, jangan hapus baris.
-- =====================================================================
CREATE TABLE enrollments (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id    INT NOT NULL REFERENCES students(user_id),
    program_id    INT NOT NULL REFERENCES programs(id),
    status        enrollment_status NOT NULL DEFAULT 'menunggu',
    alasan_tolak  TEXT,
    processed_by  INT REFERENCES users(id),
    processed_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_enrollment UNIQUE (student_id, program_id)
);
CREATE INDEX idx_enroll_program ON enrollments (program_id, status);


-- =====================================================================
-- 7. TAGIHAN DAN PEMBAYARAN
-- =====================================================================
CREATE TABLE invoices (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    no_invoice    VARCHAR(30)    NOT NULL UNIQUE DEFAULT fn_next_invoice(),
    enrollment_id INT            NOT NULL REFERENCES enrollments(id),
    periode       DATE           NOT NULL CHECK (EXTRACT(DAY FROM periode) = 1),  -- tanggal 1 tiap bulan
    jumlah        NUMERIC(12,2)  NOT NULL CHECK (jumlah >= 0), -- total akhir yang harus dibayar
    jatuh_tempo   DATE           NOT NULL,
    status        invoice_status NOT NULL DEFAULT 'belum_dibayar',
    created_at    TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT uq_invoice_periode UNIQUE (enrollment_id, periode)
);
CREATE INDEX idx_invoices_status ON invoices (status, jatuh_tempo);

CREATE TABLE payments (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id   INT            NOT NULL REFERENCES invoices(id),
    kode_bayar   VARCHAR(30)    NOT NULL UNIQUE,     -- nomor Virtual Account
    jumlah       NUMERIC(12,2)  NOT NULL CHECK (jumlah > 0),
    status       payment_status NOT NULL DEFAULT 'menunggu_pembayaran',
    paid_at      TIMESTAMPTZ,                         -- saat siswa menekan "sudah bayar"
    processed_by INT REFERENCES users(id),            -- admin yang mengonfirmasi
    processed_at TIMESTAMPTZ,
    alasan_tolak TEXT,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT now()
);
CREATE INDEX idx_payments_invoice ON payments (invoice_id);
CREATE INDEX idx_payments_status  ON payments (status, created_at);

-- Setiap percobaan pembayaran harus sebesar total tagihan penuh.
CREATE FUNCTION fn_validate_full_payment() RETURNS TRIGGER AS $$
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
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validate_full_payment
BEFORE INSERT OR UPDATE OF invoice_id, jumlah ON payments
FOR EACH ROW EXECUTE FUNCTION fn_validate_full_payment();


-- =====================================================================
-- 8. PERTEMUAN, ABSENSI, NILAI
-- =====================================================================
CREATE TABLE class_sessions (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    schedule_id  INT            NOT NULL REFERENCES schedules(id),
    tanggal      DATE           NOT NULL,
    pertemuan_ke SMALLINT       NOT NULL CHECK (pertemuan_ke > 0),
    topik        VARCHAR(150),
    ringkasan    TEXT,                                -- catatan materi untuk siswa
    status       session_status NOT NULL DEFAULT 'terlaksana',
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT uq_session_tanggal UNIQUE (schedule_id, tanggal),
    CONSTRAINT uq_session_ke      UNIQUE (schedule_id, pertemuan_ke)
);

CREATE TABLE attendances (
    session_id INT               NOT NULL REFERENCES class_sessions(id) ON DELETE CASCADE,
    student_id INT               NOT NULL REFERENCES students(user_id),
    status     attendance_status NOT NULL,
    keterangan VARCHAR(200),
    dicatat_at TIMESTAMPTZ       NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, student_id)
);
CREATE INDEX idx_attend_student ON attendances (student_id);

CREATE TABLE grades (
    id            INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    enrollment_id INT           NOT NULL REFERENCES enrollments(id),
    jenis         grade_type    NOT NULL,
    judul         VARCHAR(100),
    nilai         NUMERIC(5,2)  NOT NULL CHECK (nilai BETWEEN 0 AND 100),
    tanggal       DATE          NOT NULL DEFAULT CURRENT_DATE,
    input_by      INT           REFERENCES tutors(user_id),
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX idx_grades_enroll ON grades (enrollment_id, jenis);



-- =====================================================================
-- 9. KOMUNIKASI DAN LOG
-- =====================================================================
CREATE TABLE announcements (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    judul      VARCHAR(150) NOT NULL,
    isi        TEXT         NOT NULL,
    dibuat_by  INT          NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);


CREATE TABLE activity_logs (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id    INT REFERENCES users(id),
    aksi       VARCHAR(60) NOT NULL,                 -- contoh: LOGIN, SETUJUI_AKUN
    detail     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_logs_waktu ON activity_logs (created_at DESC);


-- =====================================================================
-- 10. VIEW UNTUK LAPORAN DAN DASHBOARD
-- =====================================================================

-- Sisa kuota tiap program (menunggu + aktif dihitung terisi)
CREATE VIEW v_program_kuota AS
SELECT p.id AS program_id, p.kode, p.nama, p.kuota,
       COUNT(e.id) FILTER (WHERE e.status IN ('menunggu', 'aktif'))            AS terisi,
       p.kuota - COUNT(e.id) FILTER (WHERE e.status IN ('menunggu', 'aktif'))  AS sisa
FROM programs p
LEFT JOIN enrollments e ON e.program_id = p.id
GROUP BY p.id;

-- Tagihan dan jumlah yang sudah lunas (jumlah adalah total akhir tagihan)
CREATE VIEW v_tagihan_status AS
SELECT i.id AS invoice_id, i.no_invoice, i.enrollment_id, e.student_id,
       i.periode, i.jatuh_tempo, i.status,
       i.jumlah,
       i.jumlah AS total_tagihan,
       COALESCE(SUM(p.jumlah) FILTER (WHERE p.status = 'lunas'), 0)        AS terbayar
FROM invoices i
JOIN enrollments e ON e.id = i.enrollment_id
LEFT JOIN payments p ON p.invoice_id = i.id
GROUP BY i.id, e.student_id;

-- Pemasukan per bulan (hanya pembayaran yang sudah dikonfirmasi)
CREATE VIEW v_pemasukan_bulanan AS
SELECT date_trunc('month', processed_at)::date AS bulan,
       COUNT(*)    AS jumlah_transaksi,
       SUM(jumlah) AS total_pemasukan
FROM payments
WHERE status = 'lunas'
GROUP BY 1;

-- Rekap kehadiran siswa per program
CREATE VIEW v_rekap_kehadiran AS
SELECT a.student_id, s.program_id,
       COUNT(*)                                       AS total_pertemuan,
       COUNT(*) FILTER (WHERE a.status = 'H')         AS hadir,
       COUNT(*) FILTER (WHERE a.status = 'I')         AS izin,
       COUNT(*) FILTER (WHERE a.status = 'S')         AS sakit,
       COUNT(*) FILTER (WHERE a.status = 'A')         AS alpa,
       ROUND(100.0 * COUNT(*) FILTER (WHERE a.status = 'H') / COUNT(*), 1) AS persen_hadir
FROM attendances a
JOIN class_sessions cs ON cs.id = a.session_id
JOIN schedules s       ON s.id = cs.schedule_id
GROUP BY a.student_id, s.program_id;

-- Nilai akhir berbobot. Komponen yang belum ada nilainya tidak dihitung
-- (hasilnya menjadi "nilai sementara" sampai UTS/UAS terisi).
CREATE VIEW v_nilai_akhir AS
WITH rata AS (
    SELECT enrollment_id, jenis, AVG(nilai) AS rata
    FROM grades
    GROUP BY enrollment_id, jenis
),
pivot AS (
    SELECT enrollment_id,
           MAX(rata) FILTER (WHERE jenis = 'tugas') AS tugas,
           MAX(rata) FILTER (WHERE jenis = 'kuis')  AS kuis,
           MAX(rata) FILTER (WHERE jenis = 'uts')   AS uts,
           MAX(rata) FILTER (WHERE jenis = 'uas')   AS uas
    FROM rata
    GROUP BY enrollment_id
)
SELECT e.id AS enrollment_id, e.student_id, e.program_id,
       ROUND(pv.tugas, 2) AS tugas,
       ROUND(pv.kuis, 2)  AS kuis,
       ROUND(pv.uts, 2)   AS uts,
       ROUND(pv.uas, 2)   AS uas,
       ROUND(
           ( COALESCE(pv.tugas * p.bobot_tugas, 0)
           + COALESCE(pv.kuis  * p.bobot_kuis,  0)
           + COALESCE(pv.uts   * p.bobot_uts,   0)
           + COALESCE(pv.uas   * p.bobot_uas,   0) )
           / NULLIF(
               CASE WHEN pv.tugas IS NOT NULL THEN p.bobot_tugas ELSE 0 END
             + CASE WHEN pv.kuis  IS NOT NULL THEN p.bobot_kuis  ELSE 0 END
             + CASE WHEN pv.uts   IS NOT NULL THEN p.bobot_uts   ELSE 0 END
             + CASE WHEN pv.uas   IS NOT NULL THEN p.bobot_uas   ELSE 0 END
           , 0)
       , 2) AS nilai_akhir
FROM enrollments e
JOIN programs p ON p.id = e.program_id
LEFT JOIN pivot pv ON pv.enrollment_id = e.id;


COMMIT;
