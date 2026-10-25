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
CREATE TYPE invoice_status    AS ENUM ('belum_dibayar', 'cicilan', 'lunas', 'batal');
CREATE TYPE payment_method    AS ENUM ('va', 'ewallet', 'qris', 'tunai');
CREATE TYPE payment_status    AS ENUM ('menunggu_pembayaran', 'menunggu_konfirmasi',
                                       'lunas', 'ditolak', 'kedaluwarsa', 'dibatalkan');
CREATE TYPE session_status    AS ENUM ('terlaksana', 'batal');
CREATE TYPE attendance_status AS ENUM ('H', 'I', 'S', 'A');   -- Hadir, Izin, Sakit, Alpa
CREATE TYPE grade_type        AS ENUM ('tugas', 'kuis', 'uts', 'uas');
CREATE TYPE request_status    AS ENUM ('menunggu', 'disetujui', 'ditolak');

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
    tarif_per_pertemuan NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (tarif_per_pertemuan >= 0),
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
    jumlah        NUMERIC(12,2)  NOT NULL CHECK (jumlah > 0),
    diskon_persen NUMERIC(5,2)   NOT NULL DEFAULT 0 CHECK (diskon_persen BETWEEN 0 AND 100),
    jatuh_tempo   DATE           NOT NULL,
    status        invoice_status NOT NULL DEFAULT 'belum_dibayar',
    created_at    TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT uq_invoice_periode UNIQUE (enrollment_id, periode)
);
CREATE INDEX idx_invoices_status ON invoices (status, jatuh_tempo);

CREATE TABLE payments (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id   INT            NOT NULL REFERENCES invoices(id),
    metode       payment_method NOT NULL,
    kode_bayar   VARCHAR(30)    NOT NULL UNIQUE,     -- nomor VA / referensi / kode QRIS
    jumlah       NUMERIC(12,2)  NOT NULL CHECK (jumlah > 0),
    status       payment_status NOT NULL DEFAULT 'menunggu_pembayaran',
    expires_at   TIMESTAMPTZ    NOT NULL,
    paid_at      TIMESTAMPTZ,                         -- saat siswa menekan "sudah bayar"
    processed_by INT REFERENCES users(id),            -- admin yang mengonfirmasi
    processed_at TIMESTAMPTZ,
    alasan_tolak TEXT,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT now()
);
CREATE INDEX idx_payments_invoice ON payments (invoice_id);
CREATE INDEX idx_payments_status  ON payments (status, created_at);


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
-- 9. KUIS
-- =====================================================================
CREATE TABLE quizzes (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    program_id INT          NOT NULL REFERENCES programs(id),
    tutor_id   INT          NOT NULL REFERENCES tutors(user_id),
    judul      VARCHAR(150) NOT NULL,
    aktif      BOOLEAN      NOT NULL DEFAULT TRUE,
    dibuat_ai  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE quiz_questions (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quiz_id    INT  NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    pertanyaan TEXT NOT NULL,
    opsi_a     TEXT NOT NULL,
    opsi_b     TEXT NOT NULL,
    opsi_c     TEXT NOT NULL,
    opsi_d     TEXT NOT NULL,
    kunci      CHAR(1) NOT NULL CHECK (kunci IN ('A', 'B', 'C', 'D'))
);

CREATE TABLE quiz_attempts (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quiz_id    INT          NOT NULL REFERENCES quizzes(id),
    student_id INT          NOT NULL REFERENCES students(user_id),
    benar      SMALLINT     NOT NULL CHECK (benar >= 0),
    total      SMALLINT     NOT NULL CHECK (total > 0),
    skor       NUMERIC(5,2) NOT NULL CHECK (skor BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_benar_total CHECK (benar <= total)
);
CREATE INDEX idx_attempts_student ON quiz_attempts (student_id, quiz_id);


-- =====================================================================
-- 10. KOMUNIKASI, UMPAN BALIK, PERMOHONAN, LOG
-- =====================================================================
CREATE TABLE announcements (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    judul      VARCHAR(150) NOT NULL,
    isi        TEXT         NOT NULL,
    dibuat_by  INT          NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Penilaian siswa untuk tutor
CREATE TABLE tutor_reviews (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tutor_id   INT      NOT NULL REFERENCES tutors(user_id),
    student_id INT      NOT NULL REFERENCES students(user_id),
    program_id INT      NOT NULL REFERENCES programs(id),
    rating     SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    masukan    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_review UNIQUE (tutor_id, student_id, program_id)
);

-- Umpan balik tutor untuk siswa
CREATE TABLE student_feedbacks (
    id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tutor_id   INT     NOT NULL REFERENCES tutors(user_id),
    student_id INT     NOT NULL REFERENCES students(user_id),
    program_id INT     NOT NULL REFERENCES programs(id),
    isi        TEXT    NOT NULL,
    dibuat_ai  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pengajuan izin tidak hadir (opsional, bagian Pusat Konfirmasi)
CREATE TABLE leave_requests (
    id           INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id   INT            NOT NULL REFERENCES students(user_id),
    schedule_id  INT            NOT NULL REFERENCES schedules(id),
    tanggal      DATE           NOT NULL,
    alasan       VARCHAR(200)   NOT NULL,
    status       request_status NOT NULL DEFAULT 'menunggu',
    processed_by INT REFERENCES users(id),
    processed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT now()
);

-- Pengajuan perubahan jadwal oleh tutor (opsional, bagian Pusat Konfirmasi)
CREATE TABLE schedule_change_requests (
    id                INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    schedule_id       INT            NOT NULL REFERENCES schedules(id),
    tutor_id          INT            NOT NULL REFERENCES tutors(user_id),
    hari_baru         nama_hari      NOT NULL,
    jam_mulai_baru    TIME           NOT NULL,
    jam_selesai_baru  TIME           NOT NULL,
    alasan            VARCHAR(200)   NOT NULL,
    status            request_status NOT NULL DEFAULT 'menunggu',
    processed_by      INT REFERENCES users(id),
    processed_at      TIMESTAMPTZ,
    created_at        TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT ck_jam_baru CHECK (jam_mulai_baru < jam_selesai_baru)
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
-- 11. VIEW UNTUK LAPORAN DAN DASHBOARD
-- =====================================================================

-- Sisa kuota tiap program (menunggu + aktif dihitung terisi)
CREATE VIEW v_program_kuota AS
SELECT p.id AS program_id, p.kode, p.nama, p.kuota,
       COUNT(e.id) FILTER (WHERE e.status IN ('menunggu', 'aktif'))            AS terisi,
       p.kuota - COUNT(e.id) FILTER (WHERE e.status IN ('menunggu', 'aktif'))  AS sisa
FROM programs p
LEFT JOIN enrollments e ON e.program_id = p.id
GROUP BY p.id;

-- Tagihan beserta total setelah diskon dan jumlah yang sudah lunas
CREATE VIEW v_tagihan_status AS
SELECT i.id AS invoice_id, i.no_invoice, i.enrollment_id, e.student_id,
       i.periode, i.jatuh_tempo, i.status,
       i.jumlah,
       i.diskon_persen,
       ROUND(i.jumlah * (1 - i.diskon_persen / 100), 2)                    AS total_tagihan,
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

-- Honor tutor per bulan = pertemuan terlaksana x tarif saat ini
CREATE VIEW v_honor_tutor AS
SELECT t.user_id AS tutor_id,
       date_trunc('month', cs.tanggal)::date AS bulan,
       COUNT(*)                              AS pertemuan,
       COUNT(*) * t.tarif_per_pertemuan      AS honor
FROM class_sessions cs
JOIN schedules s ON s.id = cs.schedule_id
JOIN tutors t    ON t.user_id = s.tutor_id
WHERE cs.status = 'terlaksana'
GROUP BY t.user_id, date_trunc('month', cs.tanggal), t.tarif_per_pertemuan;

-- Rating rata-rata tutor
CREATE VIEW v_rating_tutor AS
SELECT tutor_id, ROUND(AVG(rating), 1) AS rata_rating, COUNT(*) AS jumlah_ulasan
FROM tutor_reviews
GROUP BY tutor_id;

COMMIT;
