---
document_id: sibima-ai-access-blueprint-v1
judul: Blueprint AI Session Identity dan Admin User Search
versi: '0.1'
status: DRAF_BELUM_DISETUJUI
role_pembaca: [admin]
rag_indexing_allowed: false
---

> **STATUS: DRAF TEKNIS UNTUK REVIEW.** Disusun dari snapshot kode SIBIMA Patch 4E.1 dan `sql/schema.sql`; belum mencerminkan hasil pengecekan PostgreSQL lokal terkini. Belum boleh diindeks untuk jawaban resmi AI sebelum disetujui dan diverifikasi.

# 1. Tujuan revisi Patch 4F — belum diimplementasikan

Kebutuhan baru: (a) respons penolakan akses yang jelas dan tepat, (b) Admin dapat menemukan akun menurut nama dan membaca data yang diizinkan, (c) AI mengenali nama akun yang sedang login, dan (d) RAG menjelaskan alur SIBIMA dari sumber kode/sistem/database yang telah ditinjau.

# 2. Kondisi sekarang vs rancangan

| Kebutuhan | Kondisi kode snapshot | Rancangan | 
|---|---|---|
| Identitas login | `session.get_user()` mempunyai ID, username, nama lengkap, role, status; AI belum menyediakan tool identitas terstruktur | `get_my_identity` dengan proyeksi field minimal | 
| Admin cari orang | `admin_management_repo` sudah punya daftar/detail akun untuk UI; tool AI baru ada `get_admin_overview`, `list_unpaid_invoices` | Tool pencarian + detail admin baru, dengan filter dan batas | 
| Pesan akses | Model/HybridEvidence kadang memberi penolakan generik | kode alasan terstandar + pesan user-facing berdasarkan kode | 
| Knowledge RAG | Demo materi Python sudah terindeks; SOP masih draf | dokumentasi sistem/kode/database disusun & diverifikasi sebelum indexing | 

# 3. Matrik izin tool (usulan yang perlu disetujui)

| Fungsi | Admin | Tutor | Siswa | Data yang boleh ditampilkan |
|---|---|---|---|---|
| `get_my_identity()` | Ya | Ya | Ya | Nama lengkap, username, role, status akun milik sendiri |
| `admin_find_users(query, role?)` | Ya | Tidak | Tidak | Daftar ringkas nama, username, role, status, ID untuk memilih satu akun; maksimal mis. 10 hasil |
| `admin_get_user_summary(user_id)` | Ya | Tidak | Tidak | Ringkasan akun/program/status pendaftaran yang relevan; tidak mencakup rahasia autentikasi |
| Fungsi admin lama | Ya | Tidak | Tidak | Sesuai fungsi yang sudah tersedia |
| Fungsi Tutor lama | Tidak | Ya | Tidak | Hanya kelas yang diampu |
| Fungsi Siswa lama | Tidak | Tidak | Ya | Hanya akun dan enrollment yang boleh diakses |
| `search_knowledge_base(query)` | Sesuai metadata | Sesuai metadata | Sesuai metadata | Hanya dokumen DISETUJUI dan boleh diindeks, difilter sebelum isi dikirim ke Gemini |

**Catatan:** tidak menambahkan fitur pencarian nama orang untuk siswa atau tutor secara umum. Jika diminta oleh role lain, tolak tanpa menyebutkan apakah nama tersebut ada di sistem. Admin juga tidak boleh mendapat dump massal seluruh database via AI.

# 4. Contoh penolakan akses yang jelas (target UX)

**Admin bertanya:** "Tampilkan jadwal mengajar saya."  
**Jawaban:** "Anda masuk sebagai Admin. Fungsi *jadwal mengajar pribadi* hanya tersedia untuk akun Tutor. Saya tidak bisa menganggap Admin sebagai Tutor. Anda bisa menggunakan menu Jadwal Admin untuk melihat jadwal yang menjadi kewenangan Admin."  
**Kategori:** `ROLE_FORBIDDEN` / `UNSUPPORTED_FOR_ROLE`. Jangan memanggil RAG sebagai pengganti data operasional.

**Tutor bertanya:** "Cari profil Ahmad, termasuk tagihannya."  
**Jawaban:** "Pencarian akun dan tagihan lintas pengguna hanya tersedia untuk Admin. Sebagai Tutor, saya hanya dapat membantu informasi akademik pada kelas yang Anda ampu."  
**Kategori:** `ROLE_FORBIDDEN`.

**Siswa bertanya:** "Tampilkan tagihan teman saya."  
**Jawaban:** "Saya hanya dapat menampilkan tagihan milik akun yang sedang login. Data siswa lain tidak bisa diakses melalui akun Siswa."  
**Kategori:** `NOT_FOUND_OR_FORBIDDEN`; jangan memastikan apakah target ada.

**Pengguna bertanya:** "Siapa nama akun saya?"  
**Jawaban target:** "Nama akun yang sedang login adalah [nama_lengkap], username [username], role [role]." Nama dan username berasal dari sesi server yang diverifikasi; jangan dipercaya dari kalimat pengguna.

**Tidak ada data:** "Saya tidak menemukan data yang tersedia untuk permintaan ini dalam ruang lingkup akses Anda. Hasil juga bisa terbatas oleh filter atau jumlah maksimum baris."  
**Tidak ada dokumen resmi:** "Saya bisa menjelaskan data SIBIMA yang sudah terverifikasi. Namun, dokumen SOP resmi terkait pertanyaan ini belum tersedia/diizinkan di knowledge base, jadi saya tidak akan menyimpulkan aturannya."  
**Koneksi gagal:** "Data belum bisa dimuat karena layanan sedang mengalami kendala. Saya tidak akan menebak nilai atau statusnya."  
**Sesi berakhir:** "Sesi login sudah berubah atau berakhir. Silakan login ulang sebelum mengakses data." 

# 5. Kontrak API yang direkomendasikan (RANCANGAN)

```python
# deklarasi API untuk blueprint saja — BELUM DIIMPLEMENTASIKAN
get_my_identity() -> {"nama_lengkap": str, "username": str, "role": str, "status": str}
admin_find_users(query: str, role: str | None = None) -> {"matches": list, "has_more": bool}
admin_get_user_summary(user_id: int) -> {"account": dict, "enrollments": list}
```

1. Setiap panggilan memeriksa `session.get_user()` + role/status aktif **lagi** di DB sebelum query.
2. `query` harus teks berukuran terbatas, bukan SQL; gunakan placeholder `%s`, escapekan wildcard jika pencarian literal, dan batasi hasil.
3. Beberapa nama mirip → kembalikan kandidat ringkas, minta Admin memilih, jangan menebak identitas.
4. Daftar hasil ringkas default: `id`, `nama_lengkap`, `username`, `role`, `status`. Detail opsional `enrollments/programs` hanya setelah pemilihan akun.
5. Jangan mengembalikan `password_hash`, `otp_codes`, token/API key, OTP reset, faktor autentikasi, atau rincian proteksi akun. Jangan tampilkan seluruh row DB kepada Gemini.
6. Pencarian harus punya limit dan pagination serta audit event sesuai kebutuhan privacy, tetapi **AI read-only tidak boleh langsung membuat log ke tabel aplikasi** jika tidak disepakati. Logging aman bisa dilakukan di lapisan terpisah jika disetujui.
7. Error dari repository dibedakan menjadi kode alasan internal yang aman; model tidak boleh mengarang penolakan berdasarkan prompt saja.

# 6. Hal yang tidak bisa diselesaikan RAG saja

RAG pada dokumentasi sistem **bukan** cara membaca `users.nama_lengkap` aktual, menghitung jumlah invoice, atau menampilkan profil orang. Itu adalah data operasional dan harus lewat repository read-only yang memeriksa role. Dokumentasi kode/database tidak boleh berisi rekaman personal dari tabel produksi.

# 7. Syarat persetujuan knowledge source

- Dokumen disusun dari implementasi kode snapshot dan schema, bukan menebak aturan bisnis.
- Reviewer memverifikasi kesesuaian terhadap kode lokal/migrasi, terutama jika ada patch setelah snapshot.
- Semua berkas bertanda `DRAF_BELUM_DISETUJUI`, `rag_indexing_allowed: false` sampai disetujui satu per satu.
- **Dokumentasi kode dan skema diberi `role_pembaca: [admin]`.** Dokumen flow pengguna boleh tersedia untuk role lain setelah ditinjau kontennya.
- Jika code berubah, versi dokumen, index embedding, dan referensi sumber perlu diperbarui. Tidak perlu mengubah 18 tabel PostgreSQL untuk menyimpan dokumentasi RAG.
- Prompt injection dalam dokumen tidak boleh dijalankan sebagai instruksi oleh Gemini.
