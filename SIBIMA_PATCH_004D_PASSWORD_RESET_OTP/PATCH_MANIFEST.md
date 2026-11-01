# PATCH-004D — Lupa Password Aman dengan OTP

## Tujuan
Menambahkan alur `Lupa Kata Sandi` di CLI dan memastikan perubahan password hanya terjadi setelah verifikasi OTP `reset_password` secara atomik di PostgreSQL.

## File diperbarui
- `app/services/auth_service.py`
- `app/services/otp_service.py`
- `app/repositories/otp_repo.py`
- `app/services/email_service.py`
- `app/ui/menu_auth.py`

## File ditambahkan
- `tests/test_password_reset_otp.py`

## Keamanan installer
- Preflight hash SHA256 seluruh file dan verifikasi versi source audit.
- Backup file lama ke `.patch_backups/PATCH-004D_OTP_*` sebelum ditimpa.
- Berhenti tanpa menimpa jika versi tidak sesuai atau ada konflik.
- Coba rollback file salinan jika proses penyalinan gagal.
- Tidak mengubah `.env`, database, schema, atau data pengguna.

## Alur
Menu Utama -> Lupa Kata Sandi -> email -> OTP -> password baru dan konfirmasi -> login kembali.
