# Patch Dashboard Siswa SIBIMA

## Isi patch
1. `app/ui/menu_siswa.py` — dashboard siswa menyesuaikan status enrollment, katalog program nyata, dan riwayat pendaftaran.
2. `app/services/enrollment_service.py` — mewajibkan pendaftar cocok dengan sesi siswa aktif dan mempertahankan fungsi `batalkan()`.
3. `app/repositories/enrollment_repo.py` — menambahkan `batalkan_milik_siswa()` dengan pemeriksaan pemilik dan status dalam satu UPDATE bersyarat.

## Cara memasang
1. Cadangkan tiga file yang sekarang ada.
2. Salin tiga file dari patch ke folder proyek SIBIMA yang sama, dengan struktur direktori yang dipertahankan.
3. Pastikan `menu_auth.py` menyimpan sesi melalui `session.set_user(hasil)` ketika login berhasil, dan memanggil `menu_siswa.jalankan()` untuk role `siswa`.
4. Jalankan dari folder utama:
   ```powershell
   python -m py_compile app/ui/menu_siswa.py app/services/enrollment_service.py app/repositories/enrollment_repo.py
   python -m app.main
   ```
5. Login dengan akun siswa yang statusnya aktif. Pilih `Katalog Program`, pilih program yang tersedia, periksa detail, lalu konfirmasi pendaftaran.

## Perilaku UI
- Tidak memiliki enrollment: dashboard menyorot Katalog Program sebagai langkah awal.
- Enrollment menunggu: dashboard menampilkan jumlah/daftar pendaftaran yang menunggu keputusan admin.
- Enrollment aktif: dashboard menampilkan kelas aktif.
- Status ditolak, batal, dan selesai ditampilkan di riwayat.
- Jadwal, absensi, nilai/rapor, pembayaran, kuis, ulasan tutor dan profil yang belum diimplementasikan ditampilkan sebagai placeholder; menu tersebut tidak mengubah data.

## Batasan database saat ini
Constraint `UNIQUE(student_id, program_id)` membatasi satu pendaftaran per pasangan siswa-program, jadi pendaftaran ulang program yang pernah ditolak/dibatalkan belum didukung. Katalog ini mengecualikan program yang pernah didaftarkan agar siswa tidak mencoba operasi yang akan ditolak database.

## Pengujian
Pemeriksaan sintaks Python berhasil pada tiga file. Alur UI dan koneksi database masih perlu dites pada komputer pengguna.
