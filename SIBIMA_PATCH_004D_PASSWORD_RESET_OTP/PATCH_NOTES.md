# PATCH-004D — Catatan Instalasi dan Pengujian

## Instalasi yang konsisten dengan patch sebelumnya

1. Ekstrak ZIP sehingga folder `SIBIMA_PATCH_004D_PASSWORD_RESET_OTP` berada di `C:\Users\rapli\OneDrive\Desktop\SIBIMA`.
2. Buka PowerShell di **folder utama SIBIMA** (bukan `bimbel`).
3. Jika virtual environment belum aktif, jalankan `.\venv\Scripts\Activate.ps1` sesuai nama folder environment milikmu.
4. Jalankan:

```powershell
.\SIBIMA_PATCH_004D_PASSWORD_RESET_OTP\APPLY_PATCH.ps1
python -m pytest tests/test_password_reset_otp.py -q
python -m pytest tests -q
```

Tidak perlu membuat database baru atau menjalankan migrasi SQL.

## Cakupan dan batasan

- OTP dikirim dengan sistem existing: `OTP_MODE=simulasi` menampilkan kode di terminal **hanya untuk pengembangan**; `OTP_MODE=email` mengirim melalui SMTP ke email pengguna.
- Pada mode email, pastikan SMTP sudah dikonfigurasi di `.env`. Jangan membagikan kode OTP.
- Email belum diverifikasi / nonaktif / ditolak tidak menerima reset. Pesan permintaan reset tetap generik untuk mencegah identifikasi akun.
- Kode OTP berlaku sesuai `OTP_EXPIRE_MINUTES` (default 5 menit), batas salah sesuai `OTP_MAX_ATTEMPTS` (default 3), dan permintaan OTP dibatasi 3 kali per 60 detik per akun.
- OTP yang digunakan/expired tidak bisa digunakan lagi.
- Reset password dan penggunaan kode OTP terjadi dalam satu transaksi PostgreSQL dengan penguncian baris; kegagalan SQL harus rollback.
- Akun dengan `must_change_password` yang direset melalui OTP boleh login dengan password baru tanpa wajib mengganti ulang.
- Saat reset berhasil, penghitung gagal login dan penguncian login direset.
- Tidak ada perubahan pada alur pembayaran, enrollment, atau migrasi database.

## Hasil audit yang bisa diklaim

- **33 test khusus PATCH-004D lulus** pada environment audit menggunakan stub untuk dependensi yang tidak tersedia; test repositori memakai database tiruan, tanpa koneksi PostgreSQL atau SMTP asli.
- **Pengujian penuh SIBIMA dan integrasi email/PostgreSQL belum dijalankan di lingkungan pengguna** untuk patch ini. Jalankan perintah di atas lalu periksa output.

## Jika installer menolak

Jangan menimpa file manual. Pesan hash mismatch berarti kode proyek sudah berbeda; minta audit ulang versi file tersebut terlebih dahulu.

## Cara mencoba via CLI (opsional)

Jalankan `python -m app.main` -> pilih `Lupa Kata Sandi` -> masukkan email akun terverifikasi yang memang milikmu -> kode OTP -> password baru. Ini **akan benar-benar mengubah password akun yang digunakan**. Kalau hanya ingin tes non-destruktif, cukup gunakan pytest terlebih dahulu.
