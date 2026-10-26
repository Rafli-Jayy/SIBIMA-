# Daftar Menu Tampilan CLI - BIMBEL CERDAS

Dokumen ini berisi rancangan menu untuk setiap peran. Menu memakai `questionary`:
pilih dengan **panah atas/bawah**, lalu tekan **Enter**. Tampilan tabel dan panel
memakai `rich`.

## Daftar isi

1. [Menu awal (sebelum login)](#1-menu-awal-sebelum-login)
2. [Admin](#2-admin)
3. [Tutor](#3-tutor)
4. [Siswa](#4-siswa)
5. [Aturan tampilan umum](#5-aturan-tampilan-umum)

---

## 1. Menu awal (sebelum login)

```
╭──────────────────────────────────────────────╮
│      BIMBEL CERDAS - SISTEM AKADEMIK         │
╰──────────────────────────────────────────────╯
? Menu utama  (gunakan panah atas/bawah)
 » Login
   Register
   Lupa Password
   Keluar
```

| Menu | Alur |
|---|---|
| Login | username + password -> menu sesuai peran |
| Register | pilih **Siswa** atau **Tutor** -> isi data -> OTP -> menunggu konfirmasi admin |
| Lupa Password | email -> OTP -> password baru |
| Keluar | menutup program |

---

## 2. Admin

### 2.1 Menu utama

```
╭──────────────────────────────────────────────╮
│  DASHBOARD ADMIN                Halo, Rina   │
│  Siswa aktif   : 128    Tutor     : 14       │
│  Program aktif : 5      Pemasukan : Rp 38,5jt│
│  Tunggakan     : 17 tagihan                  │
│  Menunggu konfirmasi : 3 akun, 2 pendaftaran,│
│                        1 pembayaran          │
╰──────────────────────────────────────────────╯
? Menu Admin
 » Pusat Konfirmasi (6)
   Manajemen Akun
   Data Siswa
   Data Tutor
   Program dan Ruang
   Pendaftaran
   Jadwal
   Pembayaran
   Laporan
   Pengumuman
   Log Aktivitas
   Logout
```

Angka di sebelah **Pusat Konfirmasi** adalah jumlah item yang menunggu persetujuan.

### 2.2 Submenu

**Pusat Konfirmasi**

```
 ├─ Pendaftaran akun (siswa/tutor)    [3]  -> detail -> Setujui / Tolak (+alasan)
 ├─ Pendaftaran siswa ke program      [2]  -> detail -> Setujui / Tolak
 ├─ Pembayaran                        [1]  -> detail -> Setujui / Tolak
 └─ Kembali
```

**Manajemen Akun**

```
 ├─ Daftar semua akun (filter role / status)
 ├─ Nonaktifkan / aktifkan akun
 ├─ Buka kunci akun
 ├─ Reset password
 └─ Kembali
```

**Data Siswa**

```
 ├─ Lihat daftar
 ├─ Cari (nama / NIS)
 ├─ Filter (jenjang / program / status)
 ├─ Lihat detail
 ├─ Ubah data
 ├─ Nonaktifkan
 └─ Kembali
```

> Tidak ada menu "Tambah siswa". Akun siswa dan tutor hanya lahir dari **Register**.

**Data Tutor**

```
 ├─ Lihat daftar
 ├─ Lihat detail dan jadwal mengajar
 ├─ Ubah data
 ├─ Nonaktifkan
 └─ Kembali
```

**Program dan Ruang**

```
 ├─ Daftar program (kuota terisi / sisa)
 ├─ Tambah program
 ├─ Ubah program (harga, kuota, bobot nilai)
 ├─ Tutup / buka program
 ├─ Daftar ruang
 ├─ Tambah / ubah ruang
 └─ Kembali
```

**Pendaftaran**

```
 ├─ Daftar pendaftaran (filter status / program)
 ├─ Pindahkan siswa ke program lain
 ├─ Batalkan pendaftaran
 └─ Kembali
```

**Jadwal**

```
 ├─ Lihat jadwal (per program / tutor / ruang / hari)
 ├─ Tambah jadwal   (bentrok tutor atau ruang ditolak otomatis)
 ├─ Ubah jadwal
 ├─ Nonaktifkan jadwal
 └─ Kembali
```

**Pembayaran**

```
 ├─ Buat tagihan bulanan
 ├─ Daftar tagihan (filter status)
 ├─ Daftar tunggakan
 ├─ Riwayat pembayaran
 ├─ Cetak / unduh bukti pembayaran (PDF)
 ├─ Kirim bukti pembayaran ke email siswa
 └─ Kembali
```

**Laporan**

```
 ├─ Pemasukan per bulan
 ├─ Siswa per program
 ├─ Rekap kehadiran
 ├─ Rata-rata nilai per program
 ├─ Ekspor ke CSV
 └─ Kembali
```

**Pengumuman**

```
 ├─ Buat pengumuman
 ├─ Daftar pengumuman
 └─ Kembali
```

**Log Aktivitas**

```
 ├─ Aktivitas terbaru
 ├─ Filter (pengguna / aksi)
 └─ Kembali
```

---

## 3. Tutor

### 3.1 Menu utama

```
╭──────────────────────────────────────────────╮
│  DASHBOARD TUTOR              Halo, Ani Wulan│
│  Kelas diampu : 3        Total siswa : 58    │
│  Jadwal hari ini:                            │
│    15:00-16:30  UTBK Intensif     (R-2)      │
│    18:00-19:30  Matematika SMP    (R-1)      │
╰──────────────────────────────────────────────╯
? Menu Tutor
 » Jadwal Mengajar
   Kelas dan Siswa
   Absensi
   Nilai
   Catatan Materi
   Profil
   Logout
```

### 3.2 Submenu

**Jadwal Mengajar**

```
 ├─ Jadwal hari ini
 ├─ Jadwal mingguan
 └─ Kembali
```

**Kelas dan Siswa**

```
 ├─ Pilih kelas -> daftar siswa (NIS, nama, rata-rata, kehadiran)
 ├─ Detail siswa (hanya siswa di kelasnya)
 └─ Kembali
```

**Absensi**

```
 ├─ Buka pertemuan baru   (nomor pertemuan otomatis)
 ├─ Isi absensi           [H]adir  [I]zin  [S]akit  [A]lpa
 ├─ Ubah absensi pertemuan sebelumnya
 ├─ Rekap absensi per siswa
 └─ Kembali
```

**Nilai**

```
 ├─ Input nilai   (pilih siswa -> jenis: tugas / kuis / UTS / UAS)
 ├─ Ubah nilai
 ├─ Lihat nilai kelas (dengan nilai akhir berbobot)
 └─ Kembali
```

Catatan: jenis nilai `kuis` tetap dapat diinput tutor secara manual; modul kuis mandiri, soal, dan riwayat pengerjaan dihapus.

**Catatan Materi**

```
 ├─ Tulis topik dan ringkasan pertemuan
 ├─ Daftar catatan sebelumnya
 └─ Kembali
```

**Profil**

```
 ├─ Lihat profil
 ├─ Ubah profil (keahlian, nomor HP)
 ├─ Ganti password
 └─ Kembali
```

---

## 4. Siswa

### 4.1 Menu utama

```
╭──────────────────────────────────────────────╮
│  DASHBOARD SISWA          Halo, Budi Santoso │
│  Jadwal hari ini : 15:00 UTBK Intensif (R-2) │
│  Tagihan         : Rp 450.000 jatuh tempo 5/11│
│  Pengumuman terbaru : 3 ditampilkan          │
╰──────────────────────────────────────────────╯
? Menu Siswa
 » Katalog Program
   Kelas Saya
   Jadwal
   Absensi
   Nilai dan Rapor
   Pembayaran
   Catatan Materi
   Tanya AI            (opsional)
   Profil
   Logout
```

### 4.2 Submenu

**Katalog Program**

```
 ├─ Lihat program tersedia (harga, sisa kuota)
 ├─ Detail program
 ├─ Daftar ke program  -> status "menunggu persetujuan admin"
 └─ Kembali
```

**Kelas Saya**

```
 ├─ Program yang diikuti (tutor, status pendaftaran)
 └─ Kembali
```

**Jadwal**

```
 ├─ Jadwal hari ini
 ├─ Jadwal mingguan
 └─ Kembali
```

**Absensi**

```
 ├─ Riwayat kehadiran per program
 ├─ Persentase kehadiran
 └─ Kembali
```

**Nilai dan Rapor**

```
 ├─ Nilai per mata pelajaran
 ├─ Nilai akhir dan tren (naik / turun)
 ├─ Cetak rapor (TXT)
 └─ Kembali
```

**Pembayaran**

```
 ├─ Tagihan saya (status)
 ├─ Bayar tagihan -> nomor Virtual Account -> "Saya sudah membayar"
 ├─ Riwayat pembayaran
 ├─ Unduh bukti pembayaran (PDF)
 ├─ Kirim bukti pembayaran ke email terdaftar
 └─ Kembali
```

**Catatan Materi**

```
 ├─ Pilih program -> daftar catatan pertemuan
 └─ Kembali
```

**Tanya AI** (opsional, Gemini)

```
 ├─ Mulai tanya jawab    (ketik 'keluar' untuk berhenti)
 └─ Kembali
```

**Profil**

```
 ├─ Lihat profil
 ├─ Lengkapi / ubah profil (jenjang, sekolah, nomor HP, nama wali)
 ├─ Ganti password
 └─ Kembali
```

---

## 5. Aturan tampilan umum

| Aturan | Keterangan |
|---|---|
| Navigasi | Setiap layar punya pilihan **Kembali**, menu utama punya **Logout** |
| Tabel panjang | Dibagi per halaman, dengan opsi cari atau filter |
| Aksi berbahaya | Nonaktifkan, tolak, dan batalkan selalu meminta konfirmasi y/n |
| Ikon status | ✓ hijau berhasil, ✗ merah gagal, ! kuning peringatan, i biru info |
| Notifikasi | Angka di menu **Pusat Konfirmasi** menunjukkan item yang menunggu |
| Hak akses | Menu hanya menampilkan fitur sesuai peran; pengecekan peran tetap dilakukan di lapisan `services` |
| Pembatalan | Tombol Ctrl+C atau pembatalan prompt kembali ke menu sebelumnya, bukan menutup program |

## Ringkasan jumlah menu

| Peran | Menu utama | Submenu |
|---|---|---|
| Admin | 11 menu + Logout | 11 kelompok |
| Tutor | 6 menu + Logout | 6 kelompok |
| Siswa | 9 menu + Logout | 9 kelompok |
