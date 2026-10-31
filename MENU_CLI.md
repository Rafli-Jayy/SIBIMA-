# Referensi Menu CLI SIBIMA

Dokumen ini merangkum menu yang terhubung pada implementasi di `app/ui/`. Ini adalah referensi perilaku aplikasi saat ini, bukan daftar rencana fitur.

Navigasi utama memakai `questionary`: gunakan tombol **↑/↓** lalu tekan **Enter**. Tampilan panel dan tabel memakai `rich`. Beberapa daftar panjang menggunakan halaman berikutnya/sebelumnya.

## Daftar isi

1. [Menu awal dan autentikasi](#1-menu-awal-dan-autentikasi)
2. [Menu Admin](#2-menu-admin)
3. [Menu Tutor](#3-menu-tutor)
4. [Menu Siswa](#4-menu-siswa)
5. [Alur pembayaran](#5-alur-pembayaran)
6. [Pengumuman dan notifikasi](#6-pengumuman-dan-notifikasi)
7. [Aturan navigasi dan hak akses](#7-aturan-navigasi-dan-hak-akses)

---

## 1. Menu awal dan autentikasi

```text
S I B I M A
Menu awal
 ├─ Login
 ├─ Register
 │   ├─ Siswa
 │   └─ Tutor
 ├─ Lupa Kata Sandi
 └─ Keluar dari Aplikasi
```

### Login
- Masukkan username dan password.
- Sistem memeriksa status akun dan password.
- Jika berhasil, pengguna diarahkan ke menu berdasarkan role: Admin, Tutor, atau Siswa.

### Register
- Pilih role Siswa atau Tutor.
- Isi data akun yang diminta.
- Verifikasi OTP.
- Setelah OTP benar, akun menunggu konfirmasi Admin.

### Lupa kata sandi
- Masukkan email dan ikuti verifikasi OTP.
- Buat password baru setelah verifikasi berhasil.

---

## 2. Menu Admin

Dashboard Admin menampilkan identitas pengguna dan modul administrasi.

```text
MENU ADMIN
 ├─ Pusat Konfirmasi
 ├─ Manajemen Akun
 ├─ Data Siswa
 ├─ Data Tutor
 ├─ Program dan Ruang
 ├─ Pendaftaran
 ├─ Jadwal
 ├─ Pembayaran
 ├─ Laporan
 ├─ Komunikasi
 ├─ Log Aktivitas
 └─ Logout
```

### 2.1 Pusat Konfirmasi

```text
PUSAT KONFIRMASI
 ├─ Akun siswa/tutor
 │   ├─ Lihat daftar pendaftar
 │   ├─ Buka detail akun
 │   ├─ Setujui akun
 │   └─ Tolak akun (dengan alasan)
 ├─ Pendaftaran program bimbel
 │   ├─ Lihat pendaftaran yang menunggu
 │   ├─ Buka detail pendaftaran
 │   ├─ Terima pendaftaran
 │   └─ Tolak pendaftaran (dengan alasan)
 └─ Kembali
```

Catatan:
- Persetujuan akun berbeda dari persetujuan pendaftaran program.
- Pendaftaran program berbayar masuk antrean setelah pembayaran simulasi berhasil.
- Program gratis langsung masuk antrean Admin tanpa invoice.
- Admin memutuskan menerima/menolak pendaftaran; Admin tidak mengonfirmasi pembayaran simulasi.

### 2.2 Manajemen Akun

```text
MANAJEMEN AKUN
 ├─ Daftar semua akun (filter role/status)
 ├─ Nonaktifkan / aktifkan akun
 ├─ Buka kunci akun
 ├─ Reset password akun
 └─ Kembali
```

### 2.3 Data Siswa

```text
DATA SISWA
 ├─ Lihat daftar siswa
 ├─ Cari siswa (nama / NIS)
 ├─ Filter (jenjang / program / status)
 ├─ Lihat detail siswa dan riwayat program
 ├─ Ubah data siswa
 ├─ Nonaktifkan akun siswa
 └─ Kembali
```

Akun Siswa dibuat melalui Register, bukan melalui menu tambah siswa manual.

### 2.4 Data Tutor

```text
DATA TUTOR
 ├─ Lihat daftar tutor
 ├─ Lihat detail dan jadwal mengajar
 ├─ Ubah data tutor
 ├─ Nonaktifkan akun tutor
 └─ Kembali
```

### 2.5 Program dan Ruang

```text
PROGRAM DAN RUANG
 ├─ Daftar program (terisi / sisa kuota)
 ├─ Tambah program
 ├─ Ubah program (kode, nama, jenjang, deskripsi,
 │                harga bulanan, kuota, bobot nilai)
 ├─ Tutup / buka program
 ├─ Daftar ruang
 ├─ Tambah ruang
 ├─ Ubah ruang
 └─ Kembali
```

Bobot nilai terdiri dari tugas, kuis, UTS, dan UAS; total bobot harus 100%.

### 2.6 Pendaftaran

```text
PENDAFTARAN
 ├─ Daftar pendaftaran (filter status / program)
 ├─ Pindahkan siswa ke program lain
 ├─ Batalkan pendaftaran
 └─ Kembali
```

Status pendaftaran yang ditampilkan mencakup menunggu, aktif, ditolak, dibatalkan, dan selesai. Pembatalan mengubah status; riwayat tidak dihapus.

### 2.7 Jadwal

```text
JADWAL
 ├─ Lihat jadwal (semua / per program / tutor / ruang / hari)
 ├─ Tambah jadwal
 ├─ Ubah jadwal
 ├─ Nonaktifkan jadwal
 └─ Kembali
```

Database mencegah bentrok waktu tutor dan ruang melalui exclusion constraint.

### 2.8 Pembayaran Admin

```text
PEMBAYARAN ADMIN
 ├─ Buat tagihan bulanan
 ├─ Daftar tagihan (filter status)
 ├─ Daftar tunggakan
 ├─ Riwayat pembayaran
 ├─ Unduh bukti pembayaran (PDF)
 ├─ Kirim bukti pembayaran via email
 └─ Kembali
```

Admin memantau tagihan dan riwayat. Pembayaran bulanan diproses melalui simulasi otomatis dari sisi siswa, bukan melalui persetujuan pembayaran manual oleh Admin.

### 2.9 Laporan

```text
LAPORAN
 ├─ Pemasukan per bulan
 ├─ Siswa per program
 ├─ Rekap kehadiran
 ├─ Rata-rata nilai per program
 ├─ Ekspor laporan ke CSV
 ├─ Ekspor laporan ke Excel (.xlsx)
 └─ Kembali
```

### 2.10 Komunikasi

```text
KOMUNIKASI
 ├─ Buat Pengumuman
 ├─ Pengumuman Aktif
 ├─ Arsip Pengumuman
 └─ Kembali
```

Saat membuat pengumuman, Admin memilih minimal satu penerima: Siswa, Tutor, atau keduanya. Pengumuman aktif dapat dibuka detailnya dan diarsipkan. Pengumuman yang telah diarsipkan tidak ditampilkan sebagai notifikasi aktif.

### 2.11 Log Aktivitas

```text
LOG AKTIVITAS
 ├─ Aktivitas terbaru
 ├─ Filter berdasarkan pengguna / aksi
 └─ Kembali
```

---

## 3. Menu Tutor

```text
MENU TUTOR
 ├─ Jadwal Mengajar
 ├─ Kelas dan Siswa
 ├─ Absensi
 ├─ Nilai
 ├─ Catatan Materi
 ├─ Notifikasi
 ├─ Profil Saya
 └─ Logout
```

### 3.1 Jadwal Mengajar
- Lihat jadwal hari ini.
- Lihat jadwal mingguan.

### 3.2 Kelas dan Siswa
- Pilih kelas yang diampu.
- Lihat daftar siswa pada kelas tersebut.
- Buka detail siswa dalam kelas yang menjadi tanggung jawab Tutor.

### 3.3 Absensi
- Buka pertemuan baru (nomor pertemuan otomatis).
- Isi atau ubah absensi pertemuan.
- Lihat rekap absensi per siswa.
- Kode absensi: `H` (Hadir), `I` (Izin), `S` (Sakit), `A` (Alpa).

### 3.4 Nilai
- Input nilai siswa.
- Ubah nilai yang pernah diinput.
- Lihat nilai kelas dan nilai akhir berbobot.
- Jenis nilai: tugas, kuis (input manual), UTS, dan UAS.
- Nilai berada pada rentang 0–100.

### 3.5 Catatan Materi
- Tulis atau ubah topik dan ringkasan pertemuan.
- Lihat daftar catatan sebelumnya.

### 3.6 Notifikasi
- Lihat pengumuman aktif yang ditujukan kepada Tutor.
- Notifikasi yang belum dibaca ditandai `BARU`.
- Membuka detail mencatat status baca untuk akun Tutor tersebut.

### 3.7 Profil Saya
- Lihat profil.
- Ubah keahlian dan nomor HP.
- Ganti password.

Tutor hanya boleh mengakses kelas dan siswa yang menjadi tanggung jawabnya. Pemeriksaan hak akses dilakukan di service, bukan hanya dengan menyembunyikan pilihan menu.

---

## 4. Menu Siswa

```text
MENU SISWA
 ├─ Katalog Program
 ├─ Kelas Saya
 ├─ Jadwal Saya
 ├─ Absensi
 ├─ Nilai dan Rapor
 ├─ Tagihan dan Pembayaran
 ├─ Catatan Materi
 ├─ Notifikasi
 ├─ Tanya AI (informasi fitur; belum diaktifkan)
 ├─ Profil Saya
 └─ Logout
```

### 4.1 Katalog Program
- Lihat program yang tersedia.
- Lihat detail program.
- Daftar ke program.
- Sistem memeriksa status program, kuota, dan apakah siswa sudah terdaftar.

### 4.2 Kelas Saya
- Lihat program/pendaftaran milik sendiri.
- Lihat status pendaftaran dan informasi kelas yang tersedia.

### 4.3 Jadwal Saya
- Lihat jadwal hari ini.
- Lihat jadwal mingguan.
- Filter jadwal berdasarkan program.

### 4.4 Absensi
- Lihat riwayat kehadiran per program.
- Lihat persentase kehadiran.

### 4.5 Nilai dan Rapor
- Lihat nilai.
- Lihat rincian nilai.
- Cetak rapor ke file TXT.

### 4.6 Tagihan dan Pembayaran
- Lihat tagihan dan statusnya.
- Checkout simulasi melalui `Bayar Sekarang`.
- Lihat riwayat pembayaran.
- Unduh bukti pembayaran PDF.
- Kirim bukti pembayaran ke email terdaftar.

### 4.7 Catatan Materi
- Pilih program.
- Lihat catatan/topik dan ringkasan pertemuan yang tersedia.

### 4.8 Notifikasi
- Lihat pengumuman aktif yang ditujukan kepada Siswa.
- Jumlah notifikasi belum dibaca muncul pada label menu jika lebih dari nol.
- Notifikasi belum dibaca ditandai `BARU`.
- Membuka detail mencatat status baca untuk akun Siswa tersebut.

### 4.9 Tanya AI
- Fitur opsional.
- Saat ini hanya menampilkan informasi bahwa integrasi Gemini belum diaktifkan.
- Mengisi `GEMINI_API_KEY` saja belum membuat fitur Tanya AI berfungsi.

### 4.10 Profil Saya
- Lihat profil.
- Lengkapi atau ubah jenjang, sekolah, nomor HP, dan nama wali.
- Ganti password.

Siswa hanya boleh melihat data miliknya sendiri. Pemeriksaan kepemilikan data dilakukan di service.

---

## 5. Alur pembayaran

### 5.1 Pendaftaran program berbayar

```text
Siswa pilih program
      ↓
Konfirmasi pendaftaran
      ↓
Enrollment + invoice pertama dibuat
      ↓
Bayar Sekarang
      ↓
Simulasi internal otomatis
   ┌──┴──┐
   ↓     ↓
Lunas  Gagal
   ↓     ↓
Masuk  Invoice tetap
antrean belum dibayar
Admin  dan bisa dicoba lagi
   ↓
Admin terima / tolak
```

- Pendaftaran berbayar membuat invoice sebelum keputusan Admin.
- Pembayaran berhasil mengubah invoice/payment menjadi `lunas` dan enrollment menjadi `menunggu`.
- Pembayaran gagal tidak membuat invoice menjadi lunas.
- Jika Admin menerima, enrollment menjadi `aktif`.
- Jika Admin menolak setelah pembayaran lunas, refund dicatat sebagai simulasi terpisah.

### 5.2 Program gratis
Program dengan harga nol tidak membuat invoice/payment. Enrollment langsung masuk antrean keputusan Admin.

### 5.3 Pembayaran bulanan
Admin membuat tagihan untuk enrollment aktif. Siswa melakukan checkout simulasi. Tidak ada tahap konfirmasi pembayaran bulanan oleh Admin.

### 5.4 Status yang penting

| Objek | Status | Makna |
|---|---|---|
| Enrollment | `menunggu_pembayaran` | Menunggu pembayaran awal |
| Enrollment | `menunggu` | Menunggu keputusan Admin |
| Enrollment | `aktif` | Pendaftaran diterima |
| Enrollment | `ditolak` | Pendaftaran ditolak |
| Invoice | `belum_dibayar` | Tagihan belum lunas |
| Invoice | `lunas` | Tagihan lunas menurut simulasi |
| Invoice | `batal` | Tagihan dibatalkan |
| Payment | `lunas` | Simulasi pembayaran berhasil |
| Payment | `gagal` | Simulasi pembayaran gagal |
| Payment | `direfund` | Pembayaran direfund secara simulasi |
| Refund | `berhasil` / `gagal` | Hasil proses refund simulasi |

> Tidak ada uang sungguhan yang berpindah. Status `lunas` dan `direfund` merupakan hasil simulasi internal.

---

## 6. Pengumuman dan notifikasi

- Admin membuat pengumuman dari menu Komunikasi.
- Penerima dapat dipilih sebagai Siswa, Tutor, atau keduanya.
- Pengumuman ditampilkan pada menu Notifikasi masing-masing role.
- Status baca disimpan per user.
- Label `BARU` dan jumlah belum dibaca hanya berlaku untuk akun yang sedang login.
- Admin dapat mengarsipkan pengumuman aktif.
- Arsip tidak ditampilkan pada daftar notifikasi Siswa/Tutor dan tidak memiliki menu pemulihan.

---

## 7. Aturan navigasi dan hak akses

| Aturan | Perilaku |
|---|---|
| Navigasi | Gunakan ↑/↓ dan Enter pada pilihan Questionary |
| Kembali | Submenu menyediakan pilihan kembali ke menu sebelumnya |
| Logout | Menutup sesi pengguna dan kembali ke alur awal |
| Daftar panjang | Beberapa daftar/tabel menggunakan pagination |
| Hak akses | Menu disesuaikan dengan role; service tetap memeriksa hak akses |
| Data siswa | Siswa hanya dapat melihat data miliknya |
| Data tutor | Tutor hanya dapat mengakses kelas dan siswa yang ditugaskan |
| Pengumuman | Siswa/Tutor hanya melihat pengumuman aktif yang ditargetkan ke rolenya |
| Pembayaran | Checkout adalah simulasi internal, bukan pembayaran nyata |

### Fitur yang tidak termasuk pada versi menu ini

Dokumen ini tidak mencantumkan fitur yang sudah tidak tersedia pada implementasi saat ini, antara lain:
- Kuis mandiri, bank soal, dan riwayat pengerjaan kuis.
- Rating tutor dan feedback siswa.
- Permohonan izin dan pengajuan perubahan jadwal.
- Penggajian/honor tutor.

Jenis nilai `kuis` masih tersedia sebagai input nilai manual oleh Tutor. Hal tersebut tidak berarti modul kuis mandiri tersedia.

---

Dokumen ini diselaraskan dengan menu pada `app/ui/menu_auth.py`, `menu_admin.py`, `menu_admin_data.py`, `menu_admin_komunikasi.py`, `menu_admin_laporan.py`, `menu_pembayaran.py`, `menu_tutor.py`, `menu_tutor_academic.py`, `menu_siswa.py`, `menu_siswa_academic.py`, dan `menu_notifikasi.py` pada arsip proyek yang diaudit.
