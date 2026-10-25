SIBIMA — Tahap 1: Fondasi Database
Paket ini berisi:
- sql/schema.sql: struktur 22 tabel dan 7 view dari rancangan database SIBIMA.
- sql/seed.sql: data contoh program dan ruang untuk pengujian (bukan data resmi).
- app/db.py: satu connection pool bersama dan fungsi tes/tutup koneksi.
- buat_admin.py: membuat admin pertama tanpa menampilkan password saat mengetik.
Sebelum mulai
1. Buat salinan cadangan proyek.
2. Salin sql/schema.sql dan sql/seed.sql ke folder sql di proyek.
3. Ganti app/db.py dengan versi dari paket ini.
4. Salin buat_admin.py ke folder utama proyek.
5. Pastikan .env sudah disalin dari .env.example dan DB_NAME, DB_USER, DB_PASSWORD sudah diisi. Jangan membagikan file .env atau password.
Siapkan database PostgreSQL
Jika role dan database bimbel_user / bimbel_db sudah tersedia, lewati langkah pembuatan berikutnya.

Jika belum, masuk menggunakan akun PostgreSQL administrator, misalnya:
CREATE ROLE bimbel_user LOGIN PASSWORD 'GANTI_DENGAN_PASSWORD_DATABASE';
CREATE DATABASE bimbel_db OWNER bimbel_user;
GRANT ALL PRIVILEGES ON DATABASE bimbel_db TO bimbel_user;
Gunakan password database yang sama dengan DB_PASSWORD di .env. Jangan memakai password contoh secara literal.
Jalankan schema
Dari PowerShell pada direktori utama proyek:
psql -U bimbel_user -d bimbel_db -h localhost -v ON_ERROR_STOP=1 -f sql/schema.sql
Schema ini dirancang untuk pemasangan pertama pada database kosong. Jangan menjalankannya ulang pada database yang sudah berisi struktur SIBIMA. File membungkus DDL dalam satu transaksi agar kegagalan tidak meninggalkan setengah schema.

Jika pembuatan ekstensi btree_gist gagal karena izin, jalankan sekali sebagai administrator PostgreSQL:
psql -U postgres -d bimbel_db -h localhost -c "CREATE EXTENSION IF NOT EXISTS btree_gist;"
Setelah itu, jalankan kembali schema.sql hanya jika transaksi pemasangan sebelumnya gagal dan rollback telah selesai.
Isi data contoh
psql -U bimbel_user -d bimbel_db -h localhost -v ON_ERROR_STOP=1 -f sql/seed.sql
Data seed berisi contoh program dan ruang. Silakan ubah harga, nama program, jenjang, kapasitas dan kuota sebelum dipakai sebagai data bisnis sungguhan. Seed tidak membuat akun admin.
Uji koneksi dan buat admin pertama
Aktifkan virtual environment dan pasang dependencies dari proyek terlebih dahulu. Kemudian:
python -m app.db
python buat_admin.py
buat_admin.py hanya mengizinkan inisialisasi jika belum ada admin di database. Password diminta secara tersembunyi.
Cara verifikasi
1. python -m app.db menampilkan koneksi berhasil dan versi PostgreSQL.
2. python buat_admin.py berhasil ketika belum ada admin.
3. Jalankan python buat_admin.py sekali lagi; skrip harus menolak membuat admin kedua.
4. Periksa di PostgreSQL bahwa akun pertama memiliki role='admin', status='aktif', dan email_verified=TRUE.
Catatan: paket ini belum menjalankan SQL terhadap server PostgreSQL aktual karena akses ke database lokal di komputer pengguna tidak tersedia dari sini. Pengujian akhir harus dilakukan pada lingkungan proyek pengguna.