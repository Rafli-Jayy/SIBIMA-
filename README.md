# SIBIMA — Sistem Informasi Bimbingan Belajar

SIBIMA adalah aplikasi **CLI berbasis Python dan PostgreSQL** untuk membantu operasional bimbingan belajar. Aplikasi menyediakan akses terpisah untuk Admin, Tutor, dan Siswa. Navigasi interaktif menggunakan `questionary`, sedangkan panel dan tabel terminal menggunakan `rich`.

> **Catatan keamanan:** jangan menaruh password database, password email, API key, atau kredensial lain di README maupun repository. Simpan nilai rahasia hanya di file `.env` lokal dan jangan commit file tersebut.

## Daftar isi

1. [Fitur yang tersedia](#1-fitur-yang-tersedia)
2. [Teknologi dan dependensi](#2-teknologi-dan-dependensi)
3. [Struktur proyek](#3-struktur-proyek)
4. [Persiapan instalasi baru](#4-persiapan-instalasi-baru)
5. [Konfigurasi .env](#5-konfigurasi-env)
6. [Menjalankan aplikasi](#6-menjalankan-aplikasi)
7. [Alur akun dan OTP](#7-alur-akun-dan-otp)
8. [Alur pendaftaran dan pembayaran](#8-alur-pendaftaran-dan-pembayaran)
9. [Pengumuman dan notifikasi](#9-pengumuman-dan-notifikasi)
10. [Database dan migrasi](#10-database-dan-migrasi)
11. [Pengujian](#11-pengujian)
12. [Pemecahan masalah](#12-pemecahan-masalah)
13. [Batasan implementasi saat ini](#13-batasan-implementasi-saat-ini)

---

## 1. Fitur yang tersedia

### Admin
- Pusat Konfirmasi untuk pendaftaran akun Siswa/Tutor dan pendaftaran program.
- Manajemen akun: melihat akun, mengaktifkan/menonaktifkan, membuka kunci, dan reset password.
- Data Siswa: daftar, pencarian, filter, detail, ubah data, dan nonaktifkan akun.
- Data Tutor: daftar, detail dan jadwal mengajar, ubah data, dan nonaktifkan akun.
- Program dan Ruang: mengelola program, harga, kuota, bobot nilai, serta ruang belajar.
- Pendaftaran: melihat pendaftaran, memindahkan siswa ke program lain, dan membatalkan pendaftaran.
- Jadwal: melihat, menambah, mengubah, dan menonaktifkan jadwal. Bentrok tutor/ruang dicegah oleh constraint database.
- Pembayaran: membuat tagihan bulanan, melihat tagihan/tunggakan/riwayat, serta membuat atau mengirim bukti PDF.
- Laporan: pemasukan bulanan, siswa per program, rekap kehadiran, rata-rata nilai, ekspor CSV, dan ekspor Excel.
- Komunikasi: membuat pengumuman, melihat pengumuman aktif, dan mengarsipkan pengumuman.
- Log Aktivitas: melihat aktivitas terbaru dan memfilter berdasarkan pengguna/aksi.

### Tutor
- Melihat jadwal mengajar hari ini atau mingguan.
- Melihat kelas yang diampu dan daftar siswa pada kelas tersebut.
- Membuka pertemuan, mengisi/mengubah absensi, dan melihat rekap absensi.
- Menginput/mengubah nilai tugas, kuis (nilai manual), UTS, dan UAS.
- Menulis/mengubah topik dan ringkasan materi pertemuan.
- Melihat dan mengubah profil serta mengganti password.
- Membaca pengumuman melalui menu Notifikasi.

### Siswa
- Melihat katalog program dan mendaftar program.
- Melihat kelas/pendaftaran yang dimiliki.
- Melihat jadwal, absensi, nilai, dan rapor TXT.
- Melihat tagihan, menjalankan checkout simulasi, melihat riwayat pembayaran, dan mengunduh/mengirim bukti pembayaran.
- Membaca catatan materi pertemuan.
- Melihat menu informasi Tanya AI (fitur belum diaktifkan pada implementasi ini).
- Melihat dan mengubah profil serta mengganti password.
- Membaca pengumuman melalui menu Notifikasi.

### Pembayaran simulasi
SIBIMA **tidak terhubung ke bank atau payment gateway dan tidak memindahkan uang sungguhan**. Tombol `Bayar Sekarang` menjalankan simulasi internal. Persentase keberhasilan simulasi diatur melalui `PAYMENT_SIMULATION_SUCCESS_RATE`.

---

## 2. Teknologi dan dependensi

| Teknologi | Kegunaan |
|---|---|
| Python | Aplikasi CLI |
| PostgreSQL | Penyimpanan data |
| `psycopg` dan `psycopg_pool` | Koneksi dan connection pool PostgreSQL |
| `python-dotenv` | Membaca konfigurasi `.env` |
| `bcrypt` | Hash password |
| `questionary` | Menu interaktif terminal |
| `rich` | Panel, tabel, dan tampilan terminal |
| `email-validator` | Validasi alamat email |
| `reportlab` | Pembuatan PDF |
| `openpyxl` | Ekspor Excel |
| `google-genai` | Dependensi Gemini yang tercantum; fitur Tanya AI belum diaktifkan |
| `pytest` | Pengujian otomatis |

Daftar paket dan versinya dikelola melalui `requirements.txt`.

---

## 3. Struktur proyek

Struktur utama pada arsip proyek:

```text
SIBIMA/
├── app/
│   ├── repositories/       # Query dan akses data PostgreSQL
│   ├── services/           # Aturan bisnis dan pemeriksaan hak akses
│   ├── ui/                 # Menu CLI Admin, Tutor, Siswa, dan autentikasi
│   ├── utils/              # Validasi, keamanan, format, dan exception
│   ├── config.py           # Membaca konfigurasi .env
│   ├── db.py               # Connection pool PostgreSQL
│   ├── main.py             # Titik masuk aplikasi
│   └── session.py          # Sesi pengguna aktif
├── sql/
│   ├── schema.sql          # Skema database terkini untuk instalasi baru
│   ├── seed.sql            # Data contoh program dan ruang
│   ├── migrations/         # Migrasi untuk database versi sebelumnya
│   └── permissions/        # Skrip hak akses database
├── tests/                  # Pengujian otomatis
├── bukti/                  # Keluaran bukti/dokumen lokal
├── buat_admin.py           # Membuat akun admin pertama
├── buat_struktur.py        # Utilitas struktur proyek
├── .env.example            # Template konfigurasi
├── .gitignore
├── MENU_CLI.md             # Referensi menu CLI
├── README.md
└── requirements.txt
```

Alur arsitektur aplikasi:

```text
UI (app/ui)
    ↓
Services (app/services)
    ↓
Repositories (app/repositories)
    ↓
PostgreSQL (app/db.py)
```

UI menangani interaksi pengguna. Aturan bisnis dan pemeriksaan hak akses ditempatkan di service. Repository menangani query database.

---

## 4. Persiapan instalasi baru

### Prasyarat
- Python yang mendukung sintaks proyek dan pip.
- PostgreSQL aktif.
- Terminal PowerShell (Windows) atau terminal shell (Linux/macOS).

### Langkah 1 — Buka folder proyek

Buka PowerShell di folder root SIBIMA, yaitu folder yang berisi `app`, `sql`, dan `requirements.txt`.

### Langkah 2 — Buat virtual environment

```powershell
python -m venv .venv
```

Aktifkan di Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Jika PowerShell menolak menjalankan skrip aktivasi, gunakan Command Prompt:

```bat
.venv\Scripts\activate.bat
```

### Langkah 3 — Pasang dependensi

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Langkah 4 — Siapkan PostgreSQL

Buat database dan role PostgreSQL sesuai konfigurasi yang akan digunakan. Contoh berikut menggunakan nama `bimbel_db` dan `bimbel_user`; sesuaikan password dan hak akses dengan lingkungan sendiri.

```sql
CREATE ROLE bimbel_user WITH LOGIN PASSWORD 'GANTI_DENGAN_PASSWORD_LOKAL';
CREATE DATABASE bimbel_db OWNER bimbel_user;
```

Jalankan SQL tersebut melalui `psql` sebagai administrator PostgreSQL. Jika role/database sudah tersedia, jangan membuatnya kembali.

### Langkah 5 — Buat file `.env`

Salin template:

```powershell
Copy-Item .env.example .env
```

Edit `.env`, lalu isi konfigurasi database dan layanan yang akan digunakan. Lihat bagian [Konfigurasi .env](#5-konfigurasi-env).

### Langkah 6 — Buat skema dan data contoh

Untuk **database baru yang masih kosong**, jalankan skema terkini satu kali:

```powershell
psql -U bimbel_user -d bimbel_db -h localhost -v ON_ERROR_STOP=1 -f sql/schema.sql
```

Kemudian masukkan data contoh:

```powershell
psql -U bimbel_user -d bimbel_db -h localhost -v ON_ERROR_STOP=1 -f sql/seed.sql
```

`seed.sql` menambahkan contoh ruang dan program. Skrip ini tidak membuat akun admin.

### Langkah 7 — Buat admin pertama

```powershell
python buat_admin.py
```

Masukkan username, email, nama lengkap, dan password admin ketika diminta. Password diketik tanpa ditampilkan di terminal.

### Langkah 8 — Jalankan aplikasi

```powershell
python -m app.main
```

> Jangan menjalankan `schema.sql` berulang kali pada database yang sudah berisi skema. File tersebut merupakan skema lengkap untuk instalasi baru, bukan skrip pembaruan database.

---

## 5. Konfigurasi `.env`

Gunakan `.env.example` sebagai template. Variabel yang dibaca aplikasi:

| Variabel | Fungsi | Nilai contoh/default |
|---|---|---|
| `DB_HOST` | Host PostgreSQL | `localhost` |
| `DB_PORT` | Port PostgreSQL | `5432` |
| `DB_NAME` | Nama database | `bimbel_db` |
| `DB_USER` | Role database | `bimbel_user` |
| `DB_PASSWORD` | Password role database | Isi sendiri |
| `OTP_MODE` | Mode OTP: `simulasi` atau `email` | `simulasi` |
| `OTP_EXPIRE_MINUTES` | Masa berlaku OTP | `5` |
| `OTP_MAX_ATTEMPTS` | Maksimal percobaan OTP | `3` |
| `MAX_LOGIN_ATTEMPTS` | Batas percobaan login gagal | `3` |
| `LOCK_MINUTES` | Lama penguncian setelah gagal login | `5` |
| `SMTP_HOST` | Host SMTP | `smtp.gmail.com` |
| `SMTP_PORT` | Port SMTP | `587` |
| `SMTP_USER` | Akun pengirim email | Kosong sampai dikonfigurasi |
| `SMTP_PASSWORD` | Kredensial SMTP/app password | Kosong sampai dikonfigurasi |
| `GEMINI_API_KEY` | API key Gemini untuk Tanya AI | Kosong jika tidak digunakan |
| `PAYMENT_SIMULATION_SUCCESS_RATE` | Persentase simulasi pembayaran berhasil | `90` |

Contoh:

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=bimbel_db
DB_USER=bimbel_user
DB_PASSWORD=password_lokal_yang_kuat

OTP_MODE=simulasi
OTP_EXPIRE_MINUTES=5
OTP_MAX_ATTEMPTS=3

MAX_LOGIN_ATTEMPTS=3
LOCK_MINUTES=5

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=

GEMINI_API_KEY=
PAYMENT_SIMULATION_SUCCESS_RATE=90
```

Ketentuan:
- `OTP_MODE=simulasi`: OTP ditampilkan melalui alur simulasi di terminal.
- `OTP_MODE=email`: SMTP harus dikonfigurasi agar OTP dapat dikirim.
- `PAYMENT_SIMULATION_SUCCESS_RATE` menerima angka `0` sampai `100`. Nilai `0` membuat simulasi selalu gagal; nilai `100` membuat simulasi selalu berhasil.
- Jangan menggunakan password contoh di atas untuk server atau akun sungguhan.
- Jangan membagikan file `.env`. File tersebut sudah dicantumkan dalam `.gitignore`.

---

## 6. Menjalankan aplikasi

Pastikan virtual environment aktif, `.env` sudah diisi, dan PostgreSQL berjalan.

```powershell
python -m app.main
```

Menu awal menyediakan:
- Login.
- Register sebagai Siswa atau Tutor.
- Lupa Password.
- Keluar.

Setelah login, aplikasi menampilkan menu sesuai role akun. Detail menu dan submenu tersedia pada [MENU_CLI.md](MENU_CLI.md).

---

## 7. Alur akun dan OTP

1. Calon Siswa atau Tutor memilih Register.
2. Pendaftar mengisi data akun.
3. Sistem memvalidasi data dan mengirim/memperlihatkan OTP sesuai `OTP_MODE`.
4. OTP memiliki masa berlaku dan batas percobaan sesuai konfigurasi.
5. Setelah OTP benar, akun berstatus `menunggu_konfirmasi`.
6. Admin memeriksa pendaftaran akun melalui Pusat Konfirmasi.
7. Jika disetujui, akun menjadi `aktif`. NIS siswa atau kode tutor diterbitkan.
8. Jika ditolak, alasan penolakan disimpan.
9. Akun aktif dapat login ke menu sesuai role.

Password disimpan menggunakan hash bcrypt. OTP disimpan dalam bentuk hash, bukan kode OTP asli.

---

## 8. Alur pendaftaran dan pembayaran

### Pendaftaran program berbayar

1. Siswa memilih program yang tersedia dan mengonfirmasi pendaftaran.
2. Sistem membuat enrollment berstatus `menunggu_pembayaran` dan invoice pertama.
3. Sistem membuat dokumen invoice dan mengirim email jika konfigurasi email tersedia.
4. Siswa memilih `Bayar Sekarang`.
5. Mesin simulasi internal menentukan hasil berdasarkan konfigurasi keberhasilan:
   - **Berhasil:** pembayaran dan invoice menjadi `lunas`; enrollment masuk antrean konfirmasi admin dengan status `menunggu`.
   - **Gagal:** invoice tetap `belum_dibayar`; siswa dapat mencoba lagi.
6. Admin menerima atau menolak pendaftaran, bukan mengonfirmasi transaksi pembayaran.
7. Jika admin menerima, enrollment menjadi `aktif`.
8. Jika admin menolak pendaftaran yang sudah dibayar, sistem mencatat refund simulasi secara terpisah dan memperbarui status terkait.

### Program gratis

Program dengan harga nol tidak memerlukan invoice atau pembayaran. Pendaftaran langsung masuk antrean keputusan admin.

### Pembayaran bulanan

Admin membuat tagihan bulanan untuk enrollment aktif. Siswa melakukan checkout simulasi. Hasil berhasil memperbarui invoice/payment secara otomatis; hasil gagal membiarkan invoice belum dibayar agar dapat dicoba kembali.

### Penting

Pembayaran dan refund di SIBIMA adalah **simulasi internal**. Tidak ada uang sungguhan yang ditransfer, tidak ada koneksi bank, dan tidak ada payment gateway.

---

## 9. Pengumuman dan notifikasi

- Admin membuat pengumuman melalui menu **Komunikasi**.
- Setiap pengumuman dapat ditujukan kepada Siswa, Tutor, atau keduanya.
- Siswa dan Tutor membaca pengumuman dari menu **Notifikasi**, bukan dari dashboard.
- Status baca dicatat per pengguna. Status baca satu pengguna tidak mengubah status baca pengguna lain.
- Notifikasi yang belum dibaca ditandai `BARU`; menu menampilkan jumlah belum dibaca jika jumlahnya lebih dari nol.
- Admin dapat melihat pengumuman aktif dan arsip.
- Pengumuman yang diarsipkan tidak ditampilkan lagi kepada Siswa/Tutor. Arsip tidak memiliki fitur pemulihan melalui menu.

---

## 10. Database dan migrasi

### Objek pada `sql/schema.sql`

Skema terkini dalam arsip ini mendefinisikan:

**18 tabel**
- `users`
- `otp_codes`
- `students`
- `tutors`
- `programs`
- `rooms`
- `schedules`
- `enrollments`
- `invoices`
- `payments`
- `payment_refunds`
- `class_sessions`
- `attendances`
- `grades`
- `announcements`
- `announcement_targets`
- `announcement_reads`
- `activity_logs`

**5 view**
- `v_program_kuota`
- `v_tagihan_status`
- `v_pemasukan_bulanan`
- `v_rekap_kehadiran`
- `v_nilai_akhir`

**12 tipe**
- 11 ENUM dan satu range type `timerange`.

### Instalasi baru vs database yang sudah berjalan

- **Database baru/kosong:** gunakan `sql/schema.sql`, lalu `sql/seed.sql`.
- **Database lama yang sudah berisi data:** backup terlebih dahulu dan tentukan versi skema asal. Jangan menjalankan `schema.sql` penuh di atas database yang sudah ada.
- File dalam `sql/migrations/` adalah migrasi historis untuk jalur pembaruan dari versi sebelumnya. Migrasi harus dipilih dan dijalankan sesuai kondisi database asal, bukan dijalankan secara acak atau diulang tanpa pemeriksaan.
- `sql/permissions/20261026_laporan_select.sql` memberikan hak `SELECT` untuk objek laporan. Jalankan hanya jika diperlukan, sebagai pemilik objek atau administrator PostgreSQL. Jika role database bukan `bimbel_user`, sesuaikan nama role dalam skrip sebelum digunakan.

### Backup

Contoh membuat backup:

```powershell
pg_dump -U bimbel_user -h localhost -d bimbel_db -F c -f backup_sibima.dump
```

Contoh pemulihan ke database tujuan yang sudah disiapkan:

```powershell
pg_restore -U bimbel_user -h localhost -d bimbel_db --clean --if-exists backup_sibima.dump
```

Perintah pemulihan dapat mengganti objek database tujuan. Pastikan target benar dan backup tersedia sebelum menjalankannya.

---

## 11. Pengujian

Jalankan dari root proyek dengan virtual environment aktif:

```powershell
python -m pytest
```

Untuk melihat detail setiap test:

```powershell
python -m pytest -v
```

Jika test gagal dikoleksi karena dependensi belum tersedia, pasang ulang dependensi:

```powershell
python -m pip install -r requirements.txt
```

Pengujian otomatis tidak menggantikan pengujian integrasi PostgreSQL, SMTP, atau pemeriksaan alur UI secara manual. Catat hasil pengujian aktual; jangan menyimpulkan seluruh sistem lulus hanya dari sebagian test.

---

## 12. Pemecahan masalah

### `ModuleNotFoundError`
Pastikan virtual environment aktif dan pasang dependensi:

```powershell
python -m pip install -r requirements.txt
```

### Konfigurasi database belum lengkap
Pastikan file `.env` ada di root proyek dan nilai `DB_NAME`, `DB_USER`, serta `DB_PASSWORD` sudah diisi.

### Koneksi PostgreSQL gagal
Periksa:
- Service PostgreSQL sedang berjalan.
- Database dan role sudah dibuat.
- Host dan port benar.
- Password pada `.env` cocok.
- Role memiliki hak akses ke database dan objek yang digunakan.

### Laporan gagal karena `InsufficientPrivilege`
Periksa instruksi yang ditampilkan aplikasi. Skrip hak akses laporan berada di `sql/permissions/20261026_laporan_select.sql`. Jalankan dengan akun pemilik objek/administrator setelah memeriksa dan menyesuaikan nama role bila diperlukan.

### Email tidak terkirim
Pastikan `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, dan `SMTP_PASSWORD` benar. Untuk penyedia email yang memerlukan app password, gunakan kredensial aplikasi sesuai kebijakan penyedia email.

### Tanya AI tidak tersedia
Fitur ini memerlukan `GEMINI_API_KEY` yang valid. Fitur AI bersifat opsional.

---

## 13. Batasan implementasi saat ini

Dokumentasi ini mengikuti menu dan modul yang ada pada arsip kode yang disinkronkan. Beberapa batasan penting:

- Pembayaran/refund hanya simulasi internal, bukan transaksi finansial nyata.
- Tidak ada integrasi payment gateway.
- Modul kuis mandiri, bank soal, riwayat pengerjaan kuis, rating tutor, feedback siswa, permohonan izin, dan penggajian tutor tidak termasuk dalam menu/skema versi ini.
- Nilai dengan jenis `kuis` tetap dapat dicatat secara manual oleh Tutor; ini bukan modul kuis mandiri.
- Pengumuman dikirim sebagai notifikasi dalam aplikasi, bukan email massal.
- Menu Tanya AI saat ini hanya menampilkan informasi bahwa fitur belum diaktifkan. Mengisi `GEMINI_API_KEY` saja belum membuat fitur tersebut berfungsi.
- PDF konfirmasi pendaftaran tidak didokumentasikan sebagai fitur yang tersedia pada versi ini. Bukti invoice/pembayaran/refund merupakan dokumen yang berbeda.

---

Dokumentasi ini menjelaskan struktur dan perilaku yang ditemukan pada versi kode SIBIMA yang disinkronkan. Jika implementasi berubah, perbarui README dan MENU_CLI bersamaan dengan perubahan kode.
