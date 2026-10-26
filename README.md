# BIMBEL CERDAS (CLI)
GANTI_DENGAN_PASSWORD_KUAT

Program CLI Python untuk manajemen bimbingan belajar: admin, tutor, dan siswa.

## Menjalankan

1. Buat dan aktifkan virtual environment, lalu `python -m pip install -r requirements.txt`
2. Salin `.env.example` menjadi `.env` dan isi nilainya
3. Buat database, lalu jalankan `sql/schema.sql` dan `sql/seed.sql`
4. `python buat_admin.py` (sekali saja)
5. Jalankan program dari folder proyek: `python -m app.main`

## Struktur

- `app/repositories/` : semua query SQL
- `app/services/`     : aturan bisnis
- `app/ui/`           : menu dan tampilan CLI
- `app/utils/`        : validasi, keamanan, format
- `sql/`              : schema dan seed
- `tests/`            : pengujian

# BIMBEL CERDAS - Sistem Manajemen Bimbingan Belajar (CLI)

Program CLI berbasis Python dan PostgreSQL untuk mengelola bimbingan belajar.
Ada tiga peran pengguna: **Admin**, **Tutor**, dan **Siswa**. Setiap peran punya
menu dan hak akses sendiri.

| Teknologi | Fungsi |
|---|---|
| Python 3 | Bahasa pemrograman |
| PostgreSQL + `psycopg` | Basis data dan koneksi (connection pool) |
| `bcrypt` | Hash password |
| `rich` dan `questionary` | Tampilan tabel dan menu interaktif di terminal |
| `python-dotenv` | Konfigurasi rahasia di file `.env` |
| `google-genai` (opsional) | Integrasi Gemini |

Fitur bertanda **(opsional)** adalah tambahan yang dikerjakan jika waktu cukup.

---

## Daftar isi

1. [Alur umum akun](#1-alur-umum-akun-semua-peran)
2. [Alur Admin](#2-alur-admin)
3. [Alur Tutor](#3-alur-tutor)
4. [Alur Siswa](#4-alur-siswa)
5. [Alur pembayaran](#5-alur-pembayaran-simulasi)
6. [Siklus lengkap lintas peran](#6-siklus-lengkap-lintas-peran)
7. [Hak akses](#7-hak-akses)
8. [Struktur proyek dan cara menjalankan](#8-struktur-proyek-dan-cara-menjalankan)

---

## 1. Alur umum akun (semua peran)

Siswa dan tutor mendaftar sendiri. Akun baru harus melewati **dua lapis
verifikasi**: OTP (membuktikan email valid) lalu **konfirmasi admin**
(membuktikan pendaftar boleh masuk). Satu-satunya akun yang dibuat tanpa
register adalah **admin pertama**, lewat `python buat_admin.py`.

### 1.1 Register, OTP, konfirmasi, login

```
 Pendaftar                    Sistem                         Admin
 ---------                    ------                         -----
 Register (pilih Siswa/Tutor)
   isi nama, username, email,
   password
        |
        v
                 validasi input, cek username/email unik,
                 simpan akun (status: belum_verifikasi)
                 buat OTP 6 digit (berlaku 5 menit)
        |
        v
 Masukkan OTP  -------> OTP benar? --tidak--> sisa percobaan -1 (maks 3)
                             |ya                (habis -> minta OTP baru)
                             v
                 status: menunggu_konfirmasi
        |
        v
 "Menunggu konfirmasi admin"            ------>   Pusat Konfirmasi
                                                  lihat daftar pendaftar
                                                       |
                                  +--------------------+--------------------+
                                  v                                         v
                               SETUJUI                                    TOLAK
                       status: aktif                              status: ditolak
                       siswa -> NIS terbit                        alasan disimpan
                       tutor -> kode tutor terbit
        |
        v
 Login --> menu sesuai peran
```

### 1.2 Status akun

| Status | Arti | Bisa login? |
|---|---|---|
| `belum_verifikasi` | OTP belum dimasukkan | Tidak (diarahkan ke OTP) |
| `menunggu_konfirmasi` | OTP benar, menunggu admin | Tidak |
| `aktif` | Disetujui admin | Ya |
| `ditolak` | Ditolak admin (alasan ditampilkan) | Tidak |
| `nonaktif` | Dinonaktifkan admin | Tidak |

### 1.3 Login

```
 Input username + password
        |
        v
 Akun ada? --tidak--> "Username atau password salah"
        |ya
        v
 Sedang terkunci? --ya--> "Akun terkunci, coba lagi nanti"
        |tidak
        v
 Password cocok (bcrypt)? --tidak--> gagal +1
        |ya                          gagal >= 3 -> kunci 5 menit
        v
 Status akun aktif? --tidak--> tampilkan pesan sesuai status
        |ya
        v
 reset hitungan gagal, catat last_login
        |
        v
 Menu sesuai peran (Admin / Tutor / Siswa)
```

### 1.4 Lupa password dan ganti password

- **Lupa password:** masukkan email -> OTP dikirim -> masukkan OTP -> password baru.
- **Ganti password:** wajib memasukkan password lama lebih dulu.

### 1.5 OTP

- Dibuat dengan `secrets`, disimpan sebagai **hash** (bukan kode asli).
- Berlaku 5 menit, sekali pakai, maksimal 3 kali percobaan.
- Dua mode, diatur lewat `OTP_MODE` di `.env`:
  `simulasi` (kode tampil di terminal) atau `email` (dikirim lewat SMTP).

---

## 2. Alur Admin

Admin mengelola data master, menyetujui pendaftaran, mengonfirmasi pembayaran,
dan memantau laporan.

### 2.1 Menu

```
DASHBOARD ADMIN  (ringkasan: siswa aktif, tutor, program, pemasukan bulan ini,
                  tunggakan, jumlah item menunggu konfirmasi)
 |
 +-- [1]  Pusat Konfirmasi
 |         +-- Pendaftaran akun (siswa/tutor)
 |         +-- Pendaftaran siswa ke program
 |         +-- Pembayaran
 +-- [2]  Manajemen Akun      (nonaktifkan, buka kunci, reset password)
 +-- [3]  Data Siswa          (lihat, cari, filter, ubah, nonaktifkan)
 +-- [4]  Data Tutor          (lihat, ubah, nonaktifkan)
 +-- [5]  Program dan Ruang   (tambah, ubah, tutup program; kelola ruang)
 +-- [6]  Pendaftaran         (pindah atau batalkan siswa dari program)
 +-- [7]  Jadwal              (tambah, ubah, nonaktifkan; cek bentrok)
 +-- [8]  Pembayaran          (tagihan, tunggakan, Virtual Account, bukti pembayaran)
 +-- [9]  Laporan             (pemasukan, siswa per program, kehadiran; ekspor CSV)
 +-- [10] Pengumuman
 +-- [11] Log Aktivitas
 +-- [0]  Logout
```

Admin **tidak** menambah siswa atau tutor secara langsung. Akun hanya lahir dari
alur register.

### 2.2 Urutan kerja admin (dari awal sampai berjalan)

```
 1. Buat akun admin pertama (buat_admin.py), login
 2. Isi data master:
      Ruang  ->  Program (harga, kuota, bobot nilai)
 3. Setujui pendaftaran TUTOR di Pusat Konfirmasi
 4. Buat JADWAL: pilih program, tutor, ruang, hari, jam
      (sistem menolak jika tutor atau ruang bentrok)
 5. Setujui pendaftaran SISWA di Pusat Konfirmasi (NIS terbit)
 6. Setujui pendaftaran siswa ke PROGRAM
      (kuota dicek, tagihan pertama dibuat)
 7. Buat tagihan bulanan untuk semua pendaftaran aktif
 8. Konfirmasi PEMBAYARAN yang masuk (setujui atau tolak)
 9. Pantau Dashboard dan Laporan, buat Pengumuman
10. Pantau laporan dan ekspor data sesuai kebutuhan
```

### 2.3 Alur tiap modul admin

**Pusat Konfirmasi**

```
 Pilih jenis antrean -> daftar item "menunggu"
        |
        v
 Pilih satu item -> lihat detail
        |
        +-- [Setujui] -> status berubah, dicatat siapa dan kapan,
        |                akibat otomatis (lihat tabel di bawah)
        +-- [Tolak]   -> wajib isi alasan, status ditolak
```

| Item yang disetujui | Akibat otomatis |
|---|---|
| Akun siswa | Status `aktif`, NIS dibuat |
| Akun tutor | Status `aktif`, kode tutor dibuat |
| Pendaftaran program | Enrollment `aktif`, tagihan pertama dibuat |
| Pembayaran | Pembayaran `lunas`, status tagihan diperbarui, bukti dibuat |

**Program dan jadwal**

```
 Program : isi kode, nama, jenjang, harga/bulan, kuota, bobot nilai (total 100)
 Jadwal  : pilih program -> tutor -> ruang -> hari -> jam mulai/selesai
           bentrok dengan jadwal tutor/ruang lain? -> ditolak, pilih ulang
```

**Pendaftaran (koreksi)**

```
 Pilih siswa -> pindah program atau batalkan
 Pendaftaran dibatalkan dengan mengubah status (riwayat tidak dihapus)
```

**Laporan**

```
 Pilih laporan -> tabel di layar -> [Ekspor CSV] (opsional)
 Sumber: pemasukan bulanan, siswa per program, rekap kehadiran,
         rata-rata nilai dan tunggakan
```

---

## 3. Alur Tutor

Tutor mengajar kelas yang ditugaskan admin, mencatat kehadiran dan nilai, dan
hanya bisa mengakses **kelas dan siswa miliknya sendiri**.

### 3.1 Menu

```
DASHBOARD TUTOR  (jadwal hari ini, jumlah kelas dan siswa)
 |
 +-- [1] Jadwal Mengajar      (harian/mingguan)
 +-- [2] Kelas dan Siswa      (daftar siswa per kelas yang diampu)
 +-- [3] Absensi              (isi, ubah, rekap)
 +-- [4] Nilai                (tugas, kuis, UTS, UAS)
 +-- [5] Catatan Materi       (topik dan ringkasan per pertemuan)
 +-- [6] Profil
 +-- [0] Logout
```

### 3.2 Urutan kerja tutor

```
 1. Register -> OTP -> tunggu konfirmasi admin -> login
 2. Lengkapi profil (keahlian, nomor HP)
 3. Lihat jadwal mengajar yang dibuat admin
 4. Tiap kelas berlangsung:
      a. Buka pertemuan baru (nomor pertemuan otomatis)
      b. Isi topik dan ringkasan materi
      c. Isi absensi siswa (H / I / S / A)
 5. Berikan nilai: tugas, kuis, UTS, UAS
 6. Perbarui profil jika diperlukan
```

### 3.3 Alur tiap modul tutor

**Absensi**

```
 Pilih kelas -> pilih tanggal/pertemuan
        |
        v
 Daftar siswa AKTIF di program itu
        |
        v
 Isi status tiap siswa: [H]adir [I]zin [S]akit [A]lpa
        |
        v
 Simpan (boleh disimpan ulang untuk mengoreksi)
 -> ringkasan: Hadir 2, Izin 0, Sakit 1, Alpa 0
```

**Nilai**

```
 Pilih kelas -> pilih siswa -> pilih jenis (tugas/kuis/UTS/UAS)
 -> isi judul dan nilai (0-100) -> simpan
 -> sistem menghitung nilai akhir berbobot (bobot diatur per program)
    Selama UTS/UAS belum ada, hasilnya "nilai sementara".
```


---

## 4. Alur Siswa

Siswa mendaftar, mengikuti program, membayar, dan memantau perkembangannya.
Siswa hanya bisa melihat **data miliknya sendiri**.

### 4.1 Menu

```
DASHBOARD SISWA  (jadwal hari ini, tagihan jatuh tempo, pengumuman terbaru)
 |
 +-- [1]  Katalog Program     (lihat, daftar mandiri)
 +-- [2]  Kelas Saya          (program diikuti, tutor, status)
 +-- [3]  Jadwal              (harian/mingguan, pengingat jadwal terdekat)
 +-- [4]  Absensi             (riwayat dan persentase)
 +-- [5]  Nilai dan Rapor     (nilai per mapel, rata-rata, cetak rapor TXT)
 +-- [6]  Pembayaran          (tagihan, bayar, riwayat, bukti)
 +-- [7]  Catatan Materi      (ringkasan per pertemuan)
 +-- [8]  Tanya AI            (opsional, Gemini)
 +-- [9]  Profil
 +-- [0]  Logout
```

### 4.2 Urutan kerja siswa

```
 1. Register -> OTP -> tunggu konfirmasi admin -> login
 2. Lengkapi profil (jenjang, sekolah, nomor HP, nama wali)
 3. Buka Katalog Program -> pilih program -> Daftar
      status: "menunggu persetujuan admin"
 4. Setelah disetujui: program muncul di Kelas Saya,
    tagihan pertama terbit
 5. Bayar tagihan (lihat bagian 5)
 6. Ikuti kelas sesuai jadwal
 7. Pantau absensi, nilai, dan rapor

```

### 4.3 Alur tiap modul siswa

**Daftar program**

```
 Katalog (hanya program berstatus "buka", tampil sisa kuota)
        |
        v
 Pilih program -> konfirmasi daftar
        |
        v
 Kuota masih ada? --tidak--> "Kuota penuh"
        |ya
        v
 Sudah terdaftar di program ini? --ya--> ditolak
        |tidak
        v
 Pendaftaran tersimpan (status: menunggu) -> menunggu admin
```


**Rapor**

```
 Nilai per mapel: tugas, kuis, UTS, UAS, nilai akhir, tren naik/turun
 -> [Cetak rapor ke TXT]
```

---

## 5. Alur pembayaran (simulasi Virtual Account)

Pembayaran menggunakan satu metode, yaitu **Virtual Account (VA)**, dan harus
membayar **seluruh nominal tagihan** dalam satu transaksi. Tidak ada cicilan,
diskon, pilihan E-Wallet/QRIS/tunai, atau kedaluwarsa pembayaran. Program tetap
mensimulasikan proses pembayaran; bukan integrasi payment gateway sungguhan.

```
 SISWA                                SISTEM                       ADMIN
 -----                                ------                       -----
 Pilih tagihan
        |
        v
                         buat satu kode Virtual Account
                         jumlah yang harus dibayar = total tagihan
                         status: menunggu_pembayaran
        |
        v
 Tampilkan kode VA dan nominal penuh
        |
        v
 Klik "Saya sudah membayar"
        |
        v
                         status: menunggu_konfirmasi  ---------->  Pusat Konfirmasi
                                                                    cek pembayaran
                                                                        |
                                                       +----------------+----------------+
                                                       v                                 v
                                                    SETUJUI                            TOLAK
                                              pembayaran: lunas                  pembayaran: ditolak
                                              tagihan: lunas                     alasan penolakan dicatat
                                              bukti pembayaran dibuat            siswa dapat mengulang
        |
        v
 Lihat status dan bukti pada riwayat pembayaran
```

| Status pembayaran | Arti |
|---|---|
| `menunggu_pembayaran` | Kode Virtual Account dibuat, belum dikonfirmasi siswa |
| `menunggu_konfirmasi` | Siswa melaporkan sudah membayar dan menunggu admin |
| `lunas` | Pembayaran penuh telah dikonfirmasi admin |
| `ditolak` | Konfirmasi ditolak admin; alasan dicatat |

Status tagihan: `belum_dibayar` -> `lunas` (atau `batal`). Pembayaran dihitung
sebagai pemasukan hanya setelah status pembayaran menjadi `lunas`.

Skema baru memiliki trigger yang menolak nominal pembayaran baru jika tidak sama dengan total invoice. Catatan implementasi: alur pembuatan kode VA, pengiriman konfirmasi siswa, dan keputusan admin pada service checkout/pembayaran masih berupa kerangka.

---

## 6. Siklus lengkap lintas peran

Gambaran satu siklus dari pendaftaran sampai laporan, siapa melakukan apa, dan
tabel mana yang berubah.

| No | Pelaku | Aksi | Tabel utama |
|---|---|---|---|
| 1 | Admin | Membuat ruang, program, dan akun admin pertama | `rooms`, `programs`, `users` |
| 2 | Tutor | Register, OTP | `users`, `tutors`, `otp_codes` |
| 3 | Admin | Menyetujui tutor, membuat jadwal | `users`, `tutors`, `schedules` |
| 4 | Siswa | Register, OTP | `users`, `students`, `otp_codes` |
| 5 | Admin | Menyetujui siswa (NIS terbit) | `users`, `students` |
| 6 | Siswa | Mendaftar ke program | `enrollments` |
| 7 | Admin | Menyetujui pendaftaran, tagihan pertama terbit | `enrollments`, `invoices` |
| 8 | Siswa | Membayar (simulasi) | `payments` |
| 9 | Admin | Mengonfirmasi pembayaran | `payments`, `invoices` |
| 10 | Tutor | Membuka pertemuan dan mengisi absensi | `class_sessions`, `attendances` |
| 11 | Tutor | Mengisi nilai akademik | `grades` |
| 12 | Siswa | Melihat jadwal, absensi, nilai, dan catatan materi | `schedules`, `attendances`, `grades`, `class_sessions` |
| 13 | Admin | Melihat laporan akademik dan pemasukan | view `v_*` |

Setiap aksi penting (login, persetujuan, pembayaran) dicatat di `activity_logs`.

---

## 7. Hak akses

| Fitur | Admin | Tutor | Siswa |
|---|---|---|---|
| Register | - | Ya (perlu konfirmasi admin) | Ya (perlu konfirmasi admin) |
| Pusat Konfirmasi | Penuh | - | - |
| Kelola akun, program, ruang | Penuh | - | - |
| Jadwal | Kelola | Lihat milik sendiri | Lihat milik sendiri |
| Daftar siswa | Semua | Hanya kelas yang diampu | - |
| Absensi | Lihat semua | Isi untuk kelasnya | Lihat milik sendiri |
| Nilai | Lihat semua | Isi untuk kelasnya | Lihat milik sendiri |
| Pembayaran | Kelola dan konfirmasi | - | Bayar dan lihat milik sendiri |
| Pengumuman | Buat | Lihat | Lihat |
| Laporan | Penuh | - | - |
| Log aktivitas | Lihat | - | - |

Aturan penerapan: setiap fungsi memfilter data dengan id pengguna yang sedang
login (siswa lewat `student_id`, tutor lewat `schedules.tutor_id`). Pengecekan
peran dilakukan di lapisan `services`, bukan hanya di menu.

---

## 8. Struktur proyek dan cara menjalankan

```
bimbel/
+-- app/
|   +-- main.py, config.py, db.py, session.py
|   +-- repositories/   query SQL per kelompok tabel
|   +-- services/       aturan bisnis dan pengecekan hak akses
|   +-- ui/             menu dan tampilan CLI (rich, questionary)
|   +-- utils/          validasi, keamanan, format, exception
+-- sql/                schema.sql, seed.sql
+-- tests/              pengujian (pytest)
+-- bukti/              bukti pembayaran dan rapor (TXT)
+-- buat_admin.py       membuat admin pertama
+-- .env.example, requirements.txt
```

Alur kode: `ui -> services -> repositories -> db`.

### Menjalankan

```bash
# 1. Virtual environment dan library
python -m venv .venv
.venv\Scripts\activate            # Windows
source .venv/bin/activate         # Linux / Mac
python -m pip install -r requirements.txt

# 2. Konfigurasi: salin .env.example menjadi .env lalu isi nilainya

# 3. Database (PostgreSQL)
psql -U bimbel_user -d bimbel_db -h localhost -1 -v ON_ERROR_STOP=1 -f sql/schema.sql
psql -U bimbel_user -d bimbel_db -h localhost -f sql/seed.sql

# 4. Admin pertama (sekali saja)
python buat_admin.py

# 5. Jalankan program dari folder proyek
python -m app.main

# 6. Pengujian
python -m pytest
```

### Ringkasan database

15 tabel dan 5 view setelah fitur kuis mandiri, izin/perubahan jadwal, honor tutor, rating tutor, dan umpan balik dihapus. Konfirmasi admin memakai kolom `status`, `processed_by`,
dan `alasan_tolak` pada tabel terkait. Riwayat pembayaran lama tetap disimpan oleh migrasi; status pembayaran historis yang sudah tidak digunakan dinormalisasi dan dicatat pada alasan penolakan. Data fitur yang dicabut dihapus sesuai daftar migrasi.
Jadwal bentrok (tutor dan ruang) ditolak langsung oleh PostgreSQL.
Cadangan data: `pg_dump -U bimbel_user -d bimbel_db > cadangan.sql`.

Dibuat    : 50 file
Dilewati  : 0 file (sudah ada, tidak ditimpa)

SIBIMA/
├── .vscode/
│   └── settings.json
├── app/
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── academic_repo.py
│   │   ├── billing_repo.py
│   │   ├── engagement_repo.py
│   │   ├── enrollment_repo.py
│   │   ├── log_repo.py
│   │   ├── otp_repo.py
│   │   ├── profile_repo.py
│   │   ├── program_repo.py
│   │   ├── report_repo.py
│   │   ├── schedule_repo.py
│   │   └── user_repo.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── academic_service.py
│   │   ├── ai_service.py
│   │   ├── approval_service.py
│   │   ├── auth_service.py
│   │   ├── billing_service.py
│   │   ├── email_service.py
│   │   ├── enrollment_service.py
│   │   ├── otp_service.py
│   │   └── report_service.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── console.py
│   │   ├── menu_admin.py
│   │   ├── menu_auth.py
│   │   ├── menu_siswa.py
│   │   ├── menu_tutor.py
│   │   └── tabel.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── exceptions.py
│   │   ├── formatters.py
│   │   ├── security.py
│   │   └── validators.py
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── main.py
│   └── session.py
├── bukti/
│   └── .gitkeep
├── sql/
├── tests/
│   ├── __init__.py
│   ├── test_formatters.py
│   ├── test_security.py
│   └── test_validators.py
├── .env.example
├── .gitignore
├── README.md
├── buat_struktur.py
└── requirements.txt

Langkah berikut: salin .env.example menjadi .env lalu isi nilainya.