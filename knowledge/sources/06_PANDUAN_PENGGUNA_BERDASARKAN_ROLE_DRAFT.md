---
document_id: sibima-panduan-role-draft-v1
judul: Panduan Pengguna SIBIMA — Admin Tutor dan Siswa
versi: '0.1'
status: DRAF_BELUM_DISETUJUI
role_pembaca: [admin, tutor, siswa]
rag_indexing_allowed: false
---

> **DRAF — tinjau sebelum disahkan dan diindeks.** Dokumen umum ini tidak menampilkan source code, detail keamanan, ataupun data pribadi. Fitur yang terlihat bisa berbeda menurut status akun, program, dan versi SIBIMA yang terpasang.

# 1. Mengenali akun yang sedang digunakan

Setelah login, menu SIBIMA menampilkan fitur sesuai peran Admin, Tutor, atau Siswa. Informasi nama akun yang sedang login harus diperoleh dari sesi aplikasi sendiri; pengguna lain tidak dapat mengubah peran hanya lewat kalimat kepada AI. Jika sesi berakhir, login ulang dibutuhkan untuk akses data.

# 2. Panduan Siswa

1. Registrasikan akun siswa, lengkapi data, dan verifikasi email melalui OTP sesuai alur aplikasi.
2. Tunggu keputusan Admin atas akun. Setelah akun aktif, siswa dapat memilih program yang masih menerima pendaftaran sesuai kuota.
3. Pada program berbayar, invoice awal dibuat saat pendaftaran. Cek menu tagihan untuk nominal, periode, dan jatuh tempo.
4. Pembayaran versi demo dilakukan melalui simulasi; status pembayaran harus dibedakan dari status pendaftaran program.
5. Setelah pembayaran sukses, pendaftaran dapat berstatus `menunggu` sampai disetujui Admin. Jangan berasumsi pembayaran lunas otomatis mengaktifkan kelas.
6. Cek status pendaftaran di menu yang tersedia; jika sudah aktif, akses jadwal dan riwayat akademik mengikuti aturan program.
7. Jika kelas dibatalkan/ditolak, lihat status pembayaran/refund yang tercatat dan informasi administrasi yang tersedia; tanyakan alasan spesifik kepada Admin jika sistem tidak mencatatnya.
8. Saat ada tagihan bulan berjalan yang terlambat melewati toleransi yang berlaku, akses akademik tertentu dapat terkunci sampai persyaratan pembayaran terpenuhi.
9. Gunakan SIBIMA-AI untuk bertanya tentang **data sendiri**, misalnya nilai, jadwal, pembayaran, dan status pendaftaran; permintaan data pengguna lain tidak dilayani.

# 3. Panduan Tutor

1. Login memakai akun Tutor aktif setelah persetujuan Admin.
2. Buka jadwal dan detail kelas untuk melihat program, hari, jam, dan ruang mengajar.
3. Satu jadwal mingguan dapat memiliki banyak pertemuan pada tanggal berbeda; jadwal rutin tidak berarti pertemuan telah dilaporkan selesai.
4. Gunakan modul Absensi, Nilai, dan Catatan Materi sesuai kelas yang diampu; perubahan akademik harus menggunakan menu resmi, bukan perintah chat AI read-only.
5. Periksa notifikasi dan pertemuan tertunda; belum adanya laporan tidak otomatis berarti siswa alpa.
6. Pengumuman Tutor hanya ditujukan kepada kelas yang dia ampu sesuai aturan akses.
7. SIBIMA-AI dapat membantu jadwal dan data akademik kelas sendiri; pencarian akun lintas pengguna dan pembayaran tidak dibuka untuk role Tutor.

# 4. Panduan Admin

1. Admin mengelola persetujuan akun, program, ruangan, jadwal, pendaftaran, pembayaran, komunikasi, dan laporan melalui menu SIBIMA.
2. Persetujuan akun dan persetujuan pendaftaran program merupakan keputusan terpisah.
3. Jika diperlukan, tagihan bulanan dijalankan dari menu Admin sesuai implementasi aplikasi; jangan menganggap selalu otomatis.
4. Admin dapat menggunakan SIBIMA-AI untuk ringkasan operasional dan tagihan berdasarkan fungsi read-only yang tersedia.
5. **Rencana:** fitur pencarian pengguna menurut nama dan detail ringkas khusus Admin akan ditambahkan setelah pengujian keamanan. Fitur tersebut belum tersedia pada snapshot ini.
6. Permintaan perubahan pembayaran/nilai melalui chatbot tetap tidak dapat dijalankan; gunakan menu administrasi resmi.

# 5. Batas kemampuan dan sumber jawaban AI

- Pertanyaan data aktual dijawab dari fungsi PostgreSQL berizin.
- Pertanyaan kebijakan atau materi dapat menggunakan dokumen knowledge base hanya bila sudah disetujui.
- Dokumen latihan/demo tidak boleh dijadikan rujukan SOP resmi.
- Jika izin akses tidak ada, AI menjelaskan batas role secara ringkas tanpa mengungkap data akun lain.
- Jika data atau dokumen tidak ditemukan, AI harus membedakan keterbatasan sumber, kendala layanan, dan ketiadaan hasil.
