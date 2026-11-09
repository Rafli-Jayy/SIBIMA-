---
document_id: sibima-schema-18-tables-draft-v1
judul: Database SIBIMA — Kamus Tabel Relasi dan Status
versi: '0.1'
status: DRAF_BELUM_DISETUJUI
role_pembaca: [admin]
rag_indexing_allowed: false
---

> **STATUS: DRAF TEKNIS UNTUK REVIEW.** Disusun dari snapshot kode SIBIMA Patch 4E.1 dan `sql/schema.sql`; belum mencerminkan hasil pengecekan PostgreSQL lokal terkini. Belum boleh diindeks untuk jawaban resmi AI sebelum disetujui dan diverifikasi.

# 1. Asal data dan batasan

Dokumen ini diturunkan **langsung dari dump `sql/schema.sql` di snapshot**. Ini menjelaskan skema database, bukan menjamin bahwa DB lokal pengguna memiliki isi data, privilege, migration, atau struktur yang sama pada saat dijalankan. Dilarang menaruh hasil `SELECT` berisi data pribadi atau dump seed ke indeks RAG.

Struktur utama terdiri dari **18 tabel**. Ada view untuk analisis dan trigger untuk notifikasi/validasi pembayaran. Semua identifier dalam dokumentasi sesuai bentuk bahasa Inggris pada schema fisik.

# 2. Cara menelusuri relasi inti

```text
users(id)
  |-- students(user_id) -> enrollments(student_id) -> programs(id)
  |                            |-> invoices(enrollment_id) -> payments(invoice_id)
  |                            |                             -> payment_refunds(payment_id)
  |                            |-> grades(enrollment_id)
  |                            `-> attendances(enrollment_id)
  `-- tutors(user_id) -> schedules(tutor_id)
                       |-> programs(program_id)
                       |-> rooms(room_id)
                       `-> class_sessions(schedule_id) -> attendances(session_id)

announcements -> announcement_targets / announcement_reads
activity_logs -> users
otp_codes -> users
```

**Perhatian:** tabel `students`/`tutors` merupakan profil role yang mengacu ke `users`. Jadwal tutor memiliki relasi ke `tutors.user_id`, bukan `users.id` langsung dalam deklarasi FK. Notifikasi sistem dan email merupakan jalur berbeda. Status bayar, tagihan, dan enrollment tetap tiga konsep terpisah.

# 3. Status ENUM yang dipakai

- `attendance_status`: `H`, `I`, `S`, `A`
- `enrollment_status`: `menunggu`, `aktif`, `ditolak`, `batal`, `selesai`, `menunggu_pembayaran`
- `grade_type`: `tugas`, `kuis`, `uts`, `uas`
- `invoice_status`: `belum_dibayar`, `lunas`, `batal`
- `nama_hari`: `senin`, `selasa`, `rabu`, `kamis`, `jumat`, `sabtu`, `minggu`
- `otp_purpose`: `register`, `reset_password`, `login`
- `payment_status`: `menunggu_pembayaran`, `menunggu_konfirmasi`, `lunas`, `ditolak`, `gagal`, `direfund`
- `program_status`: `buka`, `tutup`
- `session_status`: `terlaksana`, `batal`, `perlu_laporan`, `selesai`
- `user_role`: `admin`, `tutor`, `siswa`
- `user_status`: `belum_verifikasi`, `menunggu_konfirmasi`, `aktif`, `ditolak`, `nonaktif`

# 4. Kamus lengkap tabel dan kolom

## Tabel `activity_logs`

**Primary key:** id.  
**Relasi keluar:** `user_id` → `users.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `bigint NOT NULL` |
| `user_id` | `integer` |
| `aksi` | `character varying(60) NOT NULL` |
| `detail` | `text` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |

## Tabel `announcement_reads`

**Primary key:** announcement_id, user_id.  
**Relasi keluar:** `announcement_id` → `announcements.id`; `user_id` → `users.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `announcement_id` | `integer NOT NULL` |
| `user_id` | `integer NOT NULL` |
| `read_at` | `timestamp with time zone DEFAULT now() NOT NULL` |
| `archived_at` | `timestamp with time zone` |

## Tabel `announcement_targets`

**Primary key:** announcement_id, target_role.  
**Relasi keluar:** `announcement_id` → `announcements.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `announcement_id` | `integer NOT NULL` |
| `target_role` | `public.user_role NOT NULL` |

## Tabel `announcements`

**Primary key:** id.  
**Relasi keluar:** `actor_user_id` → `users.id`; `dibuat_by` → `users.id`; `program_id` → `programs.id`; `penerima_user_id` → `users.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `judul` | `character varying(150) NOT NULL` |
| `isi` | `text NOT NULL` |
| `dibuat_by` | `integer NOT NULL` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |
| `archived_at` | `timestamp with time zone` |
| `penerima_user_id` | `integer` |
| `sumber` | `character varying(20) DEFAULT 'admin'::character varying NOT NULL` |
| `kategori` | `character varying(30) DEFAULT 'umum'::character varying NOT NULL` |
| `event_key` | `text` |
| `expires_at` | `timestamp with time zone` |
| `program_id` | `integer` |
| `batch_key` | `text` |
| `actor_user_id` | `integer` |
| `related_type` | `character varying(30)` |
| `related_id` | `integer` |

## Tabel `attendances`

**Primary key:** session_id, student_id.  
**Relasi keluar:** `session_id` → `class_sessions.id`; `student_id` → `students.user_id`; `enrollment_id` → `enrollments.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `session_id` | `integer NOT NULL` |
| `student_id` | `integer NOT NULL` |
| `status` | `public.attendance_status NOT NULL` |
| `keterangan` | `character varying(200)` |
| `dicatat_at` | `timestamp with time zone DEFAULT now() NOT NULL` |
| `enrollment_id` | `integer` |

## Tabel `class_sessions`

**Primary key:** id.  
**Relasi keluar:** `schedule_id` → `schedules.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `schedule_id` | `integer NOT NULL` |
| `tanggal` | `date NOT NULL` |
| `pertemuan_ke` | `smallint NOT NULL` |
| `topik` | `character varying(150)` |
| `ringkasan` | `text` |
| `status` | `public.session_status DEFAULT 'perlu_laporan'::public.session_status NOT NULL` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |
| `alasan_batal` | `character varying(500)` |
| `selesai_at` | `timestamp with time zone` |

## Tabel `enrollments`

**Primary key:** id.  
**Relasi keluar:** `processed_by` → `users.id`; `program_id` → `programs.id`; `student_id` → `students.user_id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `student_id` | `integer NOT NULL` |
| `program_id` | `integer NOT NULL` |
| `status` | `public.enrollment_status DEFAULT 'menunggu'::public.enrollment_status NOT NULL` |
| `alasan_tolak` | `text` |
| `processed_by` | `integer` |
| `processed_at` | `timestamp with time zone` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |

## Tabel `grades`

**Primary key:** id.  
**Relasi keluar:** `enrollment_id` → `enrollments.id`; `input_by` → `tutors.user_id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `enrollment_id` | `integer NOT NULL` |
| `jenis` | `public.grade_type NOT NULL` |
| `judul` | `character varying(100)` |
| `nilai` | `numeric(5,2) NOT NULL` |
| `tanggal` | `date DEFAULT CURRENT_DATE NOT NULL` |
| `input_by` | `integer` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |

## Tabel `invoices`

**Primary key:** id.  
**Relasi keluar:** `enrollment_id` → `enrollments.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `no_invoice` | `character varying(30) DEFAULT public.fn_next_invoice() NOT NULL` |
| `enrollment_id` | `integer NOT NULL` |
| `periode` | `date NOT NULL` |
| `jumlah` | `numeric(12,2) NOT NULL` |
| `jatuh_tempo` | `date NOT NULL` |
| `status` | `public.invoice_status DEFAULT 'belum_dibayar'::public.invoice_status NOT NULL` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |

## Tabel `otp_codes`

**Primary key:** id.  
**Relasi keluar:** `user_id` → `users.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `user_id` | `integer NOT NULL` |
| `code_hash` | `text NOT NULL` |
| `purpose` | `public.otp_purpose NOT NULL` |
| `expires_at` | `timestamp with time zone NOT NULL` |
| `attempts` | `smallint DEFAULT 0 NOT NULL` |
| `used_at` | `timestamp with time zone` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |

## Tabel `payment_refunds`

**Primary key:** id.  
**Relasi keluar:** `payment_id` → `payments.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `payment_id` | `integer NOT NULL` |
| `kode_refund` | `character varying(40) NOT NULL` |
| `jumlah` | `numeric(12,2) NOT NULL` |
| `alasan` | `text NOT NULL` |
| `status` | `character varying(20) DEFAULT 'berhasil'::character varying NOT NULL` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |
| `processed_at` | `timestamp with time zone DEFAULT now() NOT NULL` |

## Tabel `payments`

**Primary key:** id.  
**Relasi keluar:** `invoice_id` → `invoices.id`; `processed_by` → `users.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `invoice_id` | `integer NOT NULL` |
| `kode_bayar` | `character varying(30) NOT NULL` |
| `jumlah` | `numeric(12,2) NOT NULL` |
| `status` | `public.payment_status DEFAULT 'menunggu_pembayaran'::public.payment_status NOT NULL` |
| `paid_at` | `timestamp with time zone` |
| `processed_by` | `integer` |
| `processed_at` | `timestamp with time zone` |
| `alasan_tolak` | `text` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |

## Tabel `programs`

**Primary key:** id.  
**Relasi keluar:** Tidak ada foreign key keluar.

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `kode` | `character varying(10) NOT NULL` |
| `nama` | `character varying(100) NOT NULL` |
| `jenjang` | `character varying(20) NOT NULL` |
| `deskripsi` | `text` |
| `harga_bulanan` | `numeric(12,2) NOT NULL` |
| `kuota` | `smallint NOT NULL` |
| `status` | `public.program_status DEFAULT 'buka'::public.program_status NOT NULL` |
| `bobot_tugas` | `smallint DEFAULT 30 NOT NULL` |
| `bobot_kuis` | `smallint DEFAULT 20 NOT NULL` |
| `bobot_uts` | `smallint DEFAULT 20 NOT NULL` |
| `bobot_uas` | `smallint DEFAULT 30 NOT NULL` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |

## Tabel `rooms`

**Primary key:** id.  
**Relasi keluar:** Tidak ada foreign key keluar.

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `nama` | `character varying(30) NOT NULL` |
| `kapasitas` | `smallint NOT NULL` |
| `aktif` | `boolean DEFAULT true NOT NULL` |

## Tabel `schedules`

**Primary key:** id.  
**Relasi keluar:** `program_id` → `programs.id`; `room_id` → `rooms.id`; `tutor_id` → `tutors.user_id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `program_id` | `integer NOT NULL` |
| `tutor_id` | `integer NOT NULL` |
| `room_id` | `integer NOT NULL` |
| `hari` | `public.nama_hari NOT NULL` |
| `jam_mulai` | `time without time zone NOT NULL` |
| `jam_selesai` | `time without time zone NOT NULL` |
| `aktif` | `boolean DEFAULT true NOT NULL` |
| `notif_monitor_from` | `timestamp with time zone DEFAULT now() NOT NULL` |

## Tabel `students`

**Primary key:** user_id.  
**Relasi keluar:** `user_id, role` → `users.id, role`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `user_id` | `integer NOT NULL` |
| `role` | `public.user_role DEFAULT 'siswa'::public.user_role NOT NULL` |
| `nis` | `character varying(10)` |
| `jenjang` | `character varying(20)` |
| `sekolah` | `character varying(100)` |
| `no_hp` | `character varying(20)` |
| `nama_wali` | `character varying(100)` |

## Tabel `tutors`

**Primary key:** user_id.  
**Relasi keluar:** `user_id, role` → `users.id, role`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `user_id` | `integer NOT NULL` |
| `role` | `public.user_role DEFAULT 'tutor'::public.user_role NOT NULL` |
| `kode_tutor` | `character varying(10)` |
| `keahlian` | `character varying(150)` |
| `no_hp` | `character varying(20)` |

## Tabel `users`

**Primary key:** id.  
**Relasi keluar:** `approved_by` → `users.id`

| Kolom | Definisi PostgreSQL pada dump |
|---|---|
| `id` | `integer NOT NULL` |
| `username` | `character varying(30) NOT NULL` |
| `email` | `character varying(120) NOT NULL` |
| `nama_lengkap` | `character varying(100) NOT NULL` |
| `password_hash` | `text NOT NULL` |
| `role` | `public.user_role NOT NULL` |
| `status` | `public.user_status DEFAULT 'belum_verifikasi'::public.user_status NOT NULL` |
| `email_verified` | `boolean DEFAULT false NOT NULL` |
| `failed_attempts` | `smallint DEFAULT 0 NOT NULL` |
| `locked_until` | `timestamp with time zone` |
| `must_change_password` | `boolean DEFAULT false NOT NULL` |
| `approved_by` | `integer` |
| `approved_at` | `timestamp with time zone` |
| `reject_reason` | `text` |
| `last_login` | `timestamp with time zone` |
| `created_at` | `timestamp with time zone DEFAULT now() NOT NULL` |


# 5. Relasi foreign key (langsung dari deklarasi schema)

| Entitas asal / FK | Referensi | Aturan penghapusan |
|---|---|---|
| `activity_logs(user_id)` | `users(id)` | `DEFAULT / NO ACTION` |
| `announcement_reads(announcement_id)` | `announcements(id)` | `CASCADE` |
| `announcement_reads(user_id)` | `users(id)` | `CASCADE` |
| `announcement_targets(announcement_id)` | `announcements(id)` | `CASCADE` |
| `announcements(actor_user_id)` | `users(id)` | `DEFAULT / NO ACTION` |
| `announcements(dibuat_by)` | `users(id)` | `DEFAULT / NO ACTION` |
| `announcements(program_id)` | `programs(id)` | `DEFAULT / NO ACTION` |
| `attendances(session_id)` | `class_sessions(id)` | `CASCADE` |
| `attendances(student_id)` | `students(user_id)` | `DEFAULT / NO ACTION` |
| `class_sessions(schedule_id)` | `schedules(id)` | `DEFAULT / NO ACTION` |
| `enrollments(processed_by)` | `users(id)` | `DEFAULT / NO ACTION` |
| `enrollments(program_id)` | `programs(id)` | `DEFAULT / NO ACTION` |
| `enrollments(student_id)` | `students(user_id)` | `DEFAULT / NO ACTION` |
| `attendances(enrollment_id)` | `enrollments(id)` | `DEFAULT / NO ACTION` |
| `grades(enrollment_id)` | `enrollments(id)` | `DEFAULT / NO ACTION` |
| `grades(input_by)` | `tutors(user_id)` | `DEFAULT / NO ACTION` |
| `invoices(enrollment_id)` | `enrollments(id)` | `DEFAULT / NO ACTION` |
| `otp_codes(user_id)` | `users(id)` | `CASCADE` |
| `payment_refunds(payment_id)` | `payments(id)` | `DEFAULT / NO ACTION` |
| `payments(invoice_id)` | `invoices(id)` | `DEFAULT / NO ACTION` |
| `payments(processed_by)` | `users(id)` | `DEFAULT / NO ACTION` |
| `schedules(program_id)` | `programs(id)` | `DEFAULT / NO ACTION` |
| `schedules(room_id)` | `rooms(id)` | `DEFAULT / NO ACTION` |
| `schedules(tutor_id)` | `tutors(user_id)` | `DEFAULT / NO ACTION` |
| `announcements(penerima_user_id)` | `users(id)` | `CASCADE` |
| `students(user_id, role)` | `users(id, role)` | `CASCADE` |
| `tutors(user_id, role)` | `users(id, role)` | `CASCADE` |
| `users(approved_by)` | `users(id)` | `DEFAULT / NO ACTION` |

# 6. View dan trigger

**View:** `v_nilai_akhir`, `v_pemasukan_bulanan`, `v_program_kuota`, `v_rekap_kehadiran`, `v_tagihan_status`.

**Trigger dalam schema:** `sibima_n1_enroll_insert`, `sibima_n1_enroll_update`, `sibima_n1_invoice_insert`, `sibima_n1_payment_insert`, `sibima_n1_payment_update`, `sibima_n1_users_after_update`, `sibima_n2_attendance_updated`, `sibima_n2_grade_insert`, `sibima_n2_grade_update`, `sibima_n2_schedule_changed`, `sibima_n2_session_finished`, `trg_validate_full_payment`.

View bersifat turunan SQL dan hasilnya harus ditafsirkan sesuai predicate view. Trigger sistem notification N1/N2 terjadi pada insert/update data tertentu; tidak sama dengan worker asynchronous.

# 7. Query konsep aman untuk AI dan analisis lintas tabel

- **Daftar enrollment siswa:** `users` → `students` → `enrollments` → `programs`, filter `student_id` dari sesi. Status yang ditampilkan harus `enrollments.status`.
- **Tagihan:** `enrollments` → `invoices`, filter enrollment milik siswa. `invoices.status` tidak setara dengan `payments.status`.
- **Pembayaran:** `invoices` → `payments` → `payment_refunds`. Untuk alasan refund, baca sumber keputusan yang sah; jangan menebak alasan.
- **Jadwal tutor:** `schedules` → `programs`/`rooms`, filter `schedules.tutor_id` dari akun Tutor.
- **Pertemuan:** `schedules` → `class_sessions`; satu jadwal dapat memiliki banyak pertemuan bertanggal.
- **Absensi:** `class_sessions` → `attendances`, ikatan ke siswa/enrollment harus konsisten.
- **Nilai:** `enrollments` → `grades`, filter enrollment siswa atau program yang memang diajarkan Tutor.
- **Pencarian pengguna oleh Admin (RENCANA):** pencarian nama/username pada `users`, paginasi terbatas dan filter role; detail hanya field yang diizinkan; tidak membuka `otp_codes`, password hash, lockout, atau token.
- **Laporan jumlah keseluruhan:** COUNT pada server database, **bukan** menghitung 20 record yang terpotong oleh limit repository AI.

# 8. Kontrak integritas yang penting

- `users.role` diikat ke profil `students.role`/`tutors.role` melalui FK komposit.
- Indeks parsial `uq_enrollment_berjalan` mencegah dua pendaftaran berjalan untuk siswa dan program yang sama.
- `invoices` unik per kombinasi `(enrollment_id, periode)`.
- `class_sessions` unik per `(schedule_id, tanggal)` serta `(schedule_id, pertemuan_ke)`.
- `grades.nilai` 0 sampai 100; bobot nilai di `programs` wajib berjumlah 100.
- Jadwal `jam_mulai < jam_selesai`; cek bentrok tambahan di repository/schema.
- Transaksi baca AI wajib `SET TRANSACTION READ ONLY`, SQL tetap berparameter, dan hasil dibatasi. Bentuk SQL hasil Gemini tidak boleh dieksekusi secara bebas.

# 9. Makna kelima view pada snapshot

| View | Logika menurut definisi `schema.sql` | Catatan |
|---|---|---|
| `v_nilai_akhir` | Menghitung rerata nilai per jenis tugas/kuis/UTS/UAS, lalu rata-rata berbobot menurut pengaturan program; komponen tanpa nilai tidak digunakan dalam pembagi | Jangan menganggap nilai akhir sudah final jika komponen belum ada |
| `v_pemasukan_bulanan` | Mengelompokkan pembayaran berstatus `lunas` menurut bulan `paid_at`; menghitung banyak transaksi dan jumlah nominal | Pembayaran yang sudah direfund bukan `lunas` aktif pada status sekarang |
| `v_program_kuota` | Menghitung enrollment `menunggu_pembayaran`, `menunggu`, `aktif` sebagai `terisi`, lalu menghitung `sisa` | Dump menampilkan definisi `CREATE VIEW` awal yang placeholder, **kemudian** `CREATE OR REPLACE VIEW` yang merupakan definisi efektif |
| `v_rekap_kehadiran` | Menghitung status H/I/S/A dari absensi pada pertemuan selesai, per enrollment siswa-program | Bukan hitungan jadwal mingguan dan tidak boleh otomatis menandai Alpa |
| `v_tagihan_status` | Menampilkan nominal invoice dan total terbayar dari pembayaran berstatus lunas | Seperti `v_program_kuota`, dump memiliki placeholder awal lalu definisi efektif `CREATE OR REPLACE VIEW` |

# 10. Trigger, fungsi dan batas cakupan dokumentasi

- Trigger N1 pada `users`, `enrollments`, `invoices`, `payments` membuat notifikasi berbasis perubahan data yang sesuai.
- Trigger N2 pada `attendances`, `grades`, `schedules`, `class_sessions` mendukung notifikasi aktivitas akademik terkait.
- `trg_validate_full_payment` mengacu pada `fn_validate_full_payment`; jangan berasumsi semua pembayaran parsial dibolehkan.
- Fungsi sequence `fn_next_invoice`, `fn_next_nis`, dan `fn_next_kode_tutor` menangani nomor/identitas yang dihasilkan.
- Jika butuh auditing setiap cabang implementasi trigger atau privilege, baca definisi SQL fungsi secara langsung sebelum mengesahkan dokumen ini. Ini adalah **peta mendalam dari schema**, bukan salinan lengkap seluruh source SQL.
