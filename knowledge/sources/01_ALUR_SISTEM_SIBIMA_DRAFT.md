---
document_id: sibima-sistem-flow-draft-v1
judul: Alur Sistem SIBIMA — Registrasi sampai Laporan
versi: '0.1'
status: DRAF_BELUM_DISETUJUI
role_pembaca: [admin]
rag_indexing_allowed: false
---

> **STATUS: DRAF TEKNIS UNTUK REVIEW.** Disusun dari snapshot kode SIBIMA Patch 4E.1 dan `sql/schema.sql`; belum mencerminkan hasil pengecekan PostgreSQL lokal terkini. Belum boleh diindeks untuk jawaban resmi AI sebelum disetujui dan diverifikasi.

# 1. Identitas dan ruang lingkup

SIBIMA adalah **Sistem Informasi Bimbingan Belajar** berbasis CLI Python dengan PostgreSQL, menggunakan Rich dan Questionary untuk antarmuka terminal. Role utama: `admin`, `tutor`, dan `siswa`. Sistem beroperasi dengan program/kelas berkelanjutan, jadwal mingguan, pertemuan tercatat, pembayaran bulanan, notifikasi, dan pelaporan. Gemini/SIBIMA-AI merupakan asisten terpisah yang mengakses data melalui fungsi baca berizin, bukan sebagai pengganti logika transaksi aplikasi.

**Istilah yang tidak boleh dicampur:** akun `users.status`, pendaftaran `enrollments.status`, tagihan `invoices.status`, dan pembayaran `payments.status` adalah empat status berbeda. Jadwal mingguan juga tidak sama dengan bukti pertemuan benar-benar terlaksana.

# 2. Alur dari aplikasi dibuka sampai dashboard

1. `python -m app.main` menjalankan `app/main.py:main()`.
2. `main()` memanggil `app/ui/menu_auth.py:jalankan()` dan menutup connection pool saat berakhir.
3. Jika pengguna login, `menu_login()` memanggil `app/services/auth_service.py:login(username,password)`.
4. Service membaca akun melalui `user_repo.cari_by_username`, memeriksa penguncian akun, password hash, verifikasi email, serta status akun. Terdapat pembatasan percobaan login.
5. Saat sukses, UI memanggil `session.set_user(hasil)`; sesi disimpan di memori proses pada `app/session.py`, tidak otomatis menjadi sesi permanen lintas restart aplikasi.
6. UI mengarahkan ke dashboard Admin, Tutor, atau Siswa sesuai role dari data login.
7. Logout melalui `session.logout()` mengosongkan identitas aktif.

**Kasus khusus:** siswa terverifikasi yang status akunnya masih `menunggu_konfirmasi` dapat masuk ke onboarding terbatas menurut kode `auth_service.login()` dan `menu_siswa`; Tutor yang masih menunggu persetujuan tidak mendapat akses normal. Akses AI database saat ini mensyaratkan status akun aktif.

# 3. Registrasi, OTP, dan persetujuan akun

1. Calon siswa/tutor mengisi nama, username, email, dan password pada menu registrasi.
2. `auth_service.register` memvalidasi input, meng-hash password, lalu `user_repo.buat_user` menambahkan `users` dan profil pada `students` atau `tutors`.
3. `otp_service.kirim_otp` membuat OTP sesuai tujuan (`register`, `reset_password`, `login`) dan mode pengiriman yang dikonfigurasi.
4. `otp_service.verifikasi_otp` memeriksa kode, batas waktu dan percobaan; hasil yang benar memverifikasi akun.
5. Admin memakai `approval_service.setujui_akun` atau `tolak_akun` untuk keputusan akun. Persetujuan siswa menerbitkan NIS; persetujuan tutor menerbitkan kode tutor.
6. **Persetujuan akun tidak identik dengan persetujuan program.** Siswa dengan akun aktif harus mendaftar program secara terpisah.
7. Notifikasi/email berupaya dikirim setelah operasi utama; kegagalan pengiriman tidak seharusnya salah dinyatakan sebagai kegagalan perubahan akun yang sudah commit.

Tabel relevan: `users`, `students`, `tutors`, `otp_codes`, `activity_logs`, `announcements` (notifikasi). Sumber: `app/services/auth_service.py`, `otp_service.py`, `approval_service.py`, `app/repositories/user_repo.py`, `profile_repo.py`.

# 4. Pendaftaran program dan pembentukan invoice

1. Siswa aktif memilih program yang berstatus buka. `enrollment_service.daftar_program` memvalidasi sesi siswa dan ID akun miliknya.
2. `enrollment_repo.buat_enrollment` mengunci baris program menggunakan `SELECT ... FOR UPDATE` agar pemeriksaan kuota dan insert terlindung dari balapan transaksi.
3. Pemeriksaan mencakup ketersediaan program, kuota, dan tidak adanya pendaftaran berjalan yang sama (`menunggu_pembayaran`, `menunggu`, `aktif`).
4. Program berbayar: dibuat `enrollments.status = 'menunggu_pembayaran'`, lalu `billing_repo.buat_invoice_awal` menambahkan invoice awal pada transaksi yang sama. Sistem mencoba mengirim invoice PDF melalui email.
5. Program gratis: dibuat `enrollments.status = 'menunggu'` tanpa invoice awal, dan selanjutnya menunggu keputusan Admin.
6. `enrollment_repo.daftar_menunggu` hanya menampilkan pendaftaran yang memang siap diputuskan, dengan pemeriksaan pembayaran untuk program berbayar.

**Jangan menyimpulkan:** adanya invoice ≠ sudah dibayar; pembayaran lunas ≠ pendaftaran aktif; pendaftaran berstatus menunggu ≠ akun belum aktif.

# 5. Simulasi pembayaran dan pengambilan keputusan Admin

1. Siswa memilih tagihan miliknya pada menu pembayaran.
2. `billing_service.bayar_simulasi` memanggil `billing_repo.proses_simulasi_pembayaran`: ini simulasi, **tidak memproses uang sungguhan**.
3. Repository mengunci invoice dan enrollment untuk memeriksa kepemilikan, status invoice, dan status enrollment yang mengizinkan pembayaran.
4. Jika simulasi sukses, baris `payments` dibuat berstatus `lunas`, `invoices` menjadi `lunas`, dan enrollment `menunggu_pembayaran` beralih menjadi `menunggu`.
5. Jika simulasi gagal, payment menyimpan status gagal; invoice tidak dianggap lunas.
6. `approval_service.setujui_enrollment` memanggil `enrollment_repo.proses_keputusan_admin`: hanya enrollment `menunggu` yang bisa diputuskan. Program berbayar membutuhkan bukti pembayaran lunas.
7. Jika disetujui, enrollment berubah menjadi `aktif`. PDF/email konfirmasi aktivasi dikirim sebagai proses pasca-commit; kegagalan pengiriman tidak membatalkan aktivasi yang sudah berhasil.
8. Jika ditolak, alasan penolakan harus ada; untuk pembayaran simulasi yang sudah lunas, repository membuat `payment_refunds` dan mengubah status pembayaran menjadi `direfund` serta invoice menjadi `batal` pada transaksi yang sama.
9. Alur batal oleh Admin/siswa lain memiliki aturan masing-masing di `admin_enrollment_service` dan `enrollment_repo`.

# 6. Tagihan bulanan dan tunggakan

- Program memiliki `harga_bulanan` dan setiap invoice terikat satu enrollment serta satu periode (periode awal bulan).
- `billing_service.buat_tagihan_bulanan()` digunakan Admin untuk membuat tagihan bulanan; **tidak boleh mengklaim penerbitannya otomatis tanpa interaksi** berdasarkan implementasi snapshot ini.
- Akses akademik siswa dihitung melalui `class_access_sql.AKSES_TERKUNCI_SQL`. Untuk enrollment aktif, adanya invoice positif yang belum dibayar **setelah tiga hari kalender penuh sejak jatuh tempo** mengunci akses mulai H+4; kolom status enrollment tidak harus berubah menjadi `ditangguhkan`.
- `ENROLLMENT_TERAKHIR_TERSEDIA_SQL` memastikan hanya enrollment **terbaru** per siswa/program yang berstatus `aktif` atau `selesai` yang dapat menjadi dasar akses riwayat akademik. Jika pendaftaran terbaru ditolak/batal, akses akademik pada program tersebut tidak boleh disimpulkan tetap ada dari riwayat lama.
- Jawaban AI tentang tagihan harus memisahkan: jumlah tagihan, tanggal jatuh tempo, status invoice, status payment, status enrollment, dan status akses kelas.

# 7. Program, ruangan, jadwal, dan pertemuan

1. Admin mengelola `programs` (nama, jenjang, harga, kuota, bobot nilai, status) lewat `program_service`/`program_repo`.
2. Admin mengelola `rooms` (nama, kapasitas, aktif) dan `schedules` (program, tutor, ruang, hari, jam, aktif) melalui `schedule_service`/`schedule_repo`.
3. Jadwal bersifat **mingguan berulang**, sedangkan pertemuan aktual dicatat di `class_sessions` dengan `schedule_id`, `tanggal`, `pertemuan_ke`, topik, ringkasan, dan status pertemuan.
4. Tutor membuka/menyiapkan pertemuan pada jadwal yang diampu melalui `academic_service.buka_pertemuan` dan `academic_repo.buka_pertemuan`.
5. Status pertemuan di schema: `terlaksana`, `batal`, `perlu_laporan`, `selesai`. Ketika belum dilaporkan, sistem tidak otomatis boleh menganggap siswa alpa atau sesi selesai.
6. Tutor mengelola daftar hadir pada `attendances` berbasis sesi dan enrollment; nilai pada `grades` berbasis enrollment dengan jenis `tugas`, `kuis`, `uts`, `uas` dan rentang nilai 0–100.
7. Siswa hanya melihat data akademik sesuai enrollment yang diizinkan, termasuk pembatasan H+4.
8. Dashboard dan tampilan jadwal/proyeksi belum setara dengan record `class_sessions`: jadwal rutin dan tanggal pertemuan selesai adalah konsep berbeda.

# 8. Pengumuman, notifikasi, laporan, dan audit

- `announcements` adalah tabel pesan/notifikasi; `announcement_targets` mengatur role penerima; `announcement_reads` menyimpan baca/arsip pribadi. Penerima individual dapat ditentukan dengan `penerima_user_id`.
- Admin dapat membuat dan mengarsipkan pengumuman melalui `engagement_service`/`engagement_repo`; Tutor dapat membuat pengumuman terikat kelas yang dia ampu.
- Patch N1/N2 menggunakan trigger dan `notification_sync_repo.sinkronisasi` untuk notifikasi sistem, pengingat jadwal, nilai, dan pertemuan tertunda. Sinkronisasi saat inbox dibuka **bukan background scheduler**.
- `activity_logs` menyimpan aktivitas penting; modul `report_service`/`report_repo` menggunakan query/view untuk laporan, CSV, dan Excel.
- `payment_refunds` mencatat refund simulasi dan tidak boleh dicampur dengan pembayaran bank sungguhan.

# 9. Fitur AI yang berjalan pada snapshot

- `ai_service.AIService` membuat client Gemini dan, jika ada sesi login, memasang `AIToolController`.
- `DatabaseFunctionChat` menangani pertanyaan, stream, pemanggilan fungsi, dan histori percakapan stateless pada aplikasi.
- Controller menyediakan **11** fungsi SQL role-based dan, bila RAG diaktifkan, fungsi `search_knowledge_base`.
- Repository AI menggunakan query SQL tetap dengan parameter, transaksi read-only, batas 20 baris, pemeriksaan role/status di PostgreSQL, dan peran dari sesi.
- RAG menggunakan loader dokumen, chunking, embedding dan ChromaDB. Dokumen draf tidak boleh terindeks sebagai sumber resmi.
- `HybridEvidence` memeriksa pembuktian sumber; respons yang terlalu luas tanpa bukti seharusnya tidak diklaim sebagai fakta.

# 10. Kasus yang perlu dijelaskan jelas oleh AI

- **Akses ditolak:** jelaskan keterbatasan role tanpa mengungkap keberadaan data orang lain.
- **Belum ada data:** bedakan tidak ada hasil dengan query terbatas 20 baris, fungsi tidak tersedia, atau koneksi gagal.
- **Sumber dokumen tidak tersedia:** jawab data operasional yang memang telah diverifikasi, lalu katakan kebijakan/materi belum tersedia; jangan hapus bagian yang terbukti.
- **Tanggal/hari:** gunakan jam lokal aplikasi untuk menjawab 'hari ini', jangan asumsikan jadwal mingguan sebagai bukti pertemuan selesai.
