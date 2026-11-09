---
document_id: sibima-coding-flow-draft-v1
judul: Alur Kode, Modul dan Fungsi SIBIMA
versi: '0.1'
status: DRAF_BELUM_DISETUJUI
role_pembaca: [admin]
rag_indexing_allowed: false
---

> **STATUS: DRAF TEKNIS UNTUK REVIEW.** Disusun dari snapshot kode SIBIMA Patch 4E.1 dan `sql/schema.sql`; belum mencerminkan hasil pengecekan PostgreSQL lokal terkini. Belum boleh diindeks untuk jawaban resmi AI sebelum disetujui dan diverifikasi.

# 1. Arsitektur dan kontrak pemanggilan

Aplikasi memakai susunan `app/ui` → `app/services` → `app/repositories` → `app/db` → PostgreSQL; pengaturan di `app/config.py`; fungsi validasi di `app/utils`.

```text
PowerShell -> python -m app.main
  -> menu_auth.jalankan()
       -> auth_service.login() -> user_repo.cari_by_username() -> PostgreSQL
       -> session.set_user({id, username, nama_lengkap, role, status, ...})
       -> menu_admin / menu_tutor / menu_siswa
            -> service.<aksi>()
                 -> repo.<query_terparameterisasi>()
                      -> app.db.pool.connection() -> PostgreSQL
```

Kepemilikan data harus ditentukan service/repository dari session yang login, bukan parameter ID bebas dari pengguna atau hasil LLM. UI boleh memvalidasi tampilan, tetapi otorisasi tidak boleh hanya bergantung pada UI.

# 2. Flow kode otentikasi dan sesi

**Rute:** `app/ui/menu_auth.py:menu_login` → `app/services/auth_service.py:login` → `app/repositories/user_repo.py:cari_by_username` → `app/session.py:set_user` → menu role.

Saat login, `auth_service.login` memeriksa username/password, lockout, OTP/email, dan status; setelah keberhasilan UI mengisi session di memori. `app/session.py` menyediakan `set_user`, `get_user`, `logout`, `sudah_login`, `punya_role`. Field sumber `nama_lengkap` sudah ada pada sesi, tetapi jangan mengirim seluruh row `users` ke Gemini sebab row login dapat berisi `password_hash`, informasi penguncian, dan properti internal lain. Untuk identitas AI hanya keluarkan field minimal `nama_lengkap`, `username`, `role`; ID dipakai internal.

# 3. Flow kode akun dan approval

- Registrasi: `menu_auth.menu_register` → `auth_service.register` → `user_repo.buat_user` → `otp_service.kirim_otp` → `otp_repo` dan pengiriman email/simulasi.
- Verifikasi: `menu_auth.menu_verifikasi_registrasi` → `auth_service.verifikasi_otp_registrasi` → `otp_service.verifikasi_otp` → `user_repo.set_terverifikasi`.
- Admin menyetujui/menolak akun: `menu_admin` → `approval_service.setujui_akun/tolak_akun` → `profile_repo.proses_persetujuan_akun` atau `onboarding_repo.tolak_siswa_dan_paket`.
- Persetujuan akun siswa menerbitkan NIS; tutor menerbitkan kode tutor. Setelah itu **pendaftaran program adalah flow terpisah**.

# 4. Flow kode enrollment & pembayaran

```text
menu_siswa (pilih program)
  -> enrollment_service.daftar_program(student_id, program_id)
     -> enrollment_repo.buat_enrollment(...)
        -> kunci_program() FOR UPDATE
        -> hitung_terisi()
        -> INSERT enrollments
        -> billing_repo.buat_invoice_awal (jika berbayar)
     -> invoice_email_service.kirim_email_invoice_pendaftaran

menu_pembayaran (siswa)
  -> billing_service.bayar_simulasi(invoice_id)
     -> billing_repo.proses_simulasi_pembayaran
        -> INSERT payments
        -> UPDATE invoices status=lunas (jika berhasil)
        -> UPDATE enrollments menunggu_pembayaran -> menunggu
     -> billing_receipt_service (PDF/email)

menu_admin (konfirmasi program)
  -> approval_service.setujui_enrollment / tolak_enrollment
     -> enrollment_repo.proses_keputusan_admin
        -> UPDATE enrollments status=aktif / ditolak
        -> refund simulasi dalam transaksi penolakan jika perlu
     -> activation_confirmation_service (PDF/email pasca commit)
```

**Aturan semantik:** `payments.status='lunas'` dan `invoices.status='lunas'` tidak berarti `enrollments.status='aktif'`. Jangan meminta LLM menginterpretasikan ketiadaan jadwal sebagai keputusan admin.

# 5. Flow kode jadwal dan akademik

- Admin program/ruang: `menu_admin.menu_program_ruang` → `program_service` → `program_repo`.
- Admin jadwal: `menu_admin.menu_jadwal` → `schedule_service` → `schedule_repo`; memperhatikan bentrok tutor/ruangan dan jadwal mingguan.
- Tutor: `menu_tutor` → `menu_tutor_academic.jalankan_modul` → `academic_service` → `academic_repo`; pemilihan jadwal/pertemuan harus memeriksa kepemilikan tutor.
- Siswa: `menu_siswa_academic` → `student_service` → `student_repo`, dengan penyaring kelas `class_access_sql`.
- Pertemuan disimpan `class_sessions`; absensi disimpan `attendances` dengan ikatan enrollment; nilai disimpan `grades` dan penginput tutor.
- `class_access_sql.AKSES_TERKUNCI_SQL`: akses kelas aktif terkunci setelah H+3 penuh jika tagihan positif belum lunas; query kelas harus menerapkan logika ini.

# 6. Flow komunikasi dan laporan

- Pengumuman admin/tutor: UI role → `engagement_service` → `engagement_repo`; penyaringan pengumuman berdasarkan role/penerima/kelas.
- Notifikasi sistem: trigger N1/N2 di PostgreSQL serta sinkronisasi di `notification_sync_repo`. Inbox pribadi memakai status baca/arsip di `announcement_reads`.
- Laporan: `menu_admin_laporan` → `report_service` → `report_repo`, query/view read-only, ekspor CSV/Excel dengan validasi.
- Log: `log_service` → `log_repo` → `activity_logs`.

# 7. Flow kode SIBIMA-AI saat ini

```text
buka_ai(role) -> ChatScreen(... responder=AIService(role))
AIService.stream(question, role)
  -> DatabaseFunctionChat.stream(history, query, instructions)
     -> Gemini Interactions API (store=False, streaming)
       -> function_call(name, arguments)
         -> AIToolController.execute()
              -> session.get_user(): validasi id, role, status
              -> jika database: AIReadRepository.execute()
                   -> SELECT users untuk verifikasi sesi
                   -> SQL tetap + parameters (%s) + TRANSACTION READ ONLY
              -> jika RAG: RAGKnowledgeTool.search(query, role)
                   -> embedding query + ChromaDB + validasi sumber & role
       <- function_result, dilanjutkan ke Gemini
  -> HybridEvidence memeriksa dasar jawaban, jika perlu retrieval lanjutan
  -> MockEvent text_chunk/completed/error ke ChatScreen Rich
```

**Pembatasan:** tidak ada SQL bebas, tidak ada pencarian nama semua orang saat ini, tidak ada tool profil akun login saat ini, tidak ada aksi mutasi AI. Tool database punya batas 20 baris. Model/SDK bisa berhenti sebelum event lengkap; adapter memiliki pemulihan terbatas dan boleh menggunakan request API tambahan.

# 8. Kebutuhan patch berikutnya (BELUM DIIMPLEMENTASIKAN)

1. **Identitas diri** `get_my_identity()`: khusus untuk sesi login, mengembalikan nama lengkap, username, role, dan status aman. Identitas tidak boleh berasal dari input model.
2. **Admin menemukan orang** `admin_find_users(name, role?)`: kata pencarian tervalidasi, hasil paginasi/limit dan ringkas; hanya Admin aktif.
3. **Admin melihat detail** `admin_get_user_summary(user_id)`: daftar field aman berdasarkan kebutuhan administratif; tidak boleh password hash, OTP, token, data reset, nilai rahasia keamanan, atau ekspor massal tanpa batas.
4. **Pesan penolakan terarah**: kode kesalahan `ROLE_FORBIDDEN`, `FEATURE_UNAVAILABLE`, `NOT_FOUND_OR_FORBIDDEN`, `SESSION_EXPIRED`, `DATA_UNAVAILABLE`, `SOURCE_UNAVAILABLE`. Beri jawaban yang bisa ditindaklanjuti, tapi jangan mengungkap keberadaan akun/data terlarang.
5. **Dokumentasi RAG code/database**: hanya untuk role Admin; dokumen yang statusnya DRAF belum boleh diindeks; pembaruan kode perlu memicu validasi dan re-index.

# 9. Inventaris kode sumber Python (snapshot)

Daftar berikut dibuat dari analisis AST pada file `.py` yang tersedia. Nama fungsi adalah indeks untuk navigasi **bukan pengganti membaca implementasi lengkap**. Referensi `baris` mengacu ke snapshot ini, bisa berubah setelah patch.

## Folder `app/services`

**`app/services/academic_service.py`**

`_tutor_aktif()` (baris 10); `_id()` (baris 26); `jadwal()` (baris 30); `program_tutor()` (baris 40); `daftar_siswa()` (baris 50); `detail_siswa()` (baris 66); `daftar_pertemuan()` (baris 83); `pertemuan_per_jadwal()` (baris 100); `buka_pertemuan()` (baris 117); `siapkan_pertemuan()` (baris 136); `ringkasan_pertemuan()` (baris 149); `selesaikan_pertemuan()` (baris 164); `batalkan_pertemuan()` (baris 179); `daftar_absensi()` (baris 195); `simpan_absensi()` (baris 208); `rekap_absensi()` (baris 236); `input_nilai()` (baris 252); `nilai_kelas()` (baris 274); `daftar_nilai()` (baris 278); `ubah_nilai()` (baris 296); `simpan_catatan()` (baris 318); `daftar_catatan()` (baris 340)

**`app/services/activation_confirmation_service.py`**

`_teks()` (baris 36); `_tanggal()` (baris 41); `_validasi()` (baris 47); `buat_pdf_konfirmasi_aktivasi()` (baris 66); `kirim_pdf_konfirmasi_aktivasi()` (baris 181)

**`app/services/admin_enrollment_service.py`**

`_admin_aktif()` (baris 9); `daftar_pendaftaran()` (baris 25); `detail_pendaftaran()` (baris 36); `pindahkan_pendaftaran()` (baris 50); `batalkan_pendaftaran()` (baris 72)

**`app/services/admin_management_service.py`**

`_admin_aktif()` (baris 23); `_teks()` (baris 36); `daftar_akun()` (baris 49); `ubah_status_akun()` (baris 59); `buka_kunci_akun()` (baris 86); `reset_password_akun()` (baris 102); `daftar_siswa()` (baris 128); `detail_siswa()` (baris 142); `ubah_siswa()` (baris 150); `daftar_tutor()` (baris 186); `detail_tutor()` (baris 194); `jadwal_tutor()` (baris 202); `ubah_tutor()` (baris 210)

**`app/services/ai_db_chat.py`**

`_safe_diagnostic()` (baris 16); `_document_search_query()` (baris 70); `_retrieval_context()` (baris 77); `_get()` (baris 96); `_as_step()` (baris 102); `_normalize_function_call()` (baris 113); `_terminal_status()` (baris 143); `_unary_recovery()` (baris 148); class `DatabaseFunctionChat` (baris 190): __init__(), stream()

**`app/services/ai_service.py`**

`_current_day_hint()` (baris 64); class `AIService` (baris 80): __init__(), stream(), reset(), close(); `buka_ai()` (baris 140)

**`app/services/ai_tool_controller.py`**

`tool_schema()` (baris 29); `validate_args()` (baris 39); class `AIToolController` (baris 53): __init__(), declarations(), execute()

**`app/services/approval_service.py`**

`_admin_aktif()` (baris 15); `setujui_akun()` (baris 35); `tolak_akun()` (baris 103); `_enrollment_menunggu()` (baris 172); `_format_rupiah()` (baris 182); `setujui_enrollment()` (baris 187); `tolak_enrollment()` (baris 235)

**`app/services/auth_service.py`**

`register()` (baris 15); `kirim_ulang_otp_registrasi()` (baris 66); `verifikasi_otp_registrasi()` (baris 84); `_waktu_sisa_kunci()` (baris 102); `login()` (baris 110); `ganti_password()` (baris 202); `minta_otp_reset_password()` (baris 224); `reset_password()` (baris 251)

**`app/services/billing_receipt_service.py`**

`_plain()` (baris 32); `_rupiah()` (baris 37); `_tanggal()` (baris 45); `_periode()` (baris 53); `buat_pdf_bukti()` (baris 65); `kirim_pdf_via_email()` (baris 240); `kirim_email_simulasi_gagal()` (baris 311); `buat_pdf_bukti_refund()` (baris 357); `kirim_pdf_refund_via_email()` (baris 399)

**`app/services/billing_service.py`**

`_pengguna_aktif()` (baris 9); `buat_tagihan_bulanan()` (baris 22); `daftar_tagihan_admin()` (baris 40); `daftar_tagihan_saya()` (baris 45); `bayar_simulasi()` (baris 50); `riwayat_pembayaran_admin()` (baris 69); `riwayat_pembayaran_saya()` (baris 74); `bukti_pembayaran_admin()` (baris 79); `bukti_pembayaran_saya()` (baris 84); `_detail_bukti_untuk_sesi()` (baris 89); `buat_bukti_pembayaran_pdf()` (baris 108); `kirim_bukti_pembayaran_email()` (baris 116)

**`app/services/email_service.py`**

`kirim_notifikasi_status()` (baris 28); `tampilkan_otp_simulasi()` (baris 246); `_buat_html_email()` (baris 271); `kirim_otp_email()` (baris 475)

**`app/services/engagement_service.py`**

`_pengguna_aktif()` (baris 10); `buat_pengumuman()` (baris 20); `daftar_pengumuman_admin()` (baris 46); `detail_pengumuman_admin()` (baris 53); `arsipkan_pengumuman_admin()` (baris 58); `pengumuman_terbaru_siswa()` (baris 66); `daftar_notifikasi()` (baris 72); `jumlah_notifikasi_belum_dibaca()` (baris 80); `buka_notifikasi()` (baris 86); `sinkronisasi_notifikasi()` (baris 104); `daftar_notifikasi_filter()` (baris 109); `buka_notifikasi_arsip()` (baris 117); `arsipkan_notifikasi_pribadi()` (baris 127); `tandai_semua_dibaca()` (baris 133); `daftar_program_pengumuman_tutor()` (baris 138); `buat_pengumuman_tutor()` (baris 143); `daftar_pengumuman_tutor()` (baris 167); `akhiri_pengumuman_tutor()` (baris 172); `daftar_pertemuan_tertunda_tutor()` (baris 178); `buka_pertemuan_terlewat_tutor()` (baris 183)

**`app/services/enrollment_service.py`**

`daftar_program()` (baris 9); `batalkan()` (baris 104)

**`app/services/gemini_client.py`**

`_opening_state()` (baris 29); class `_ProviderStreamError` (baris 41): __init__(); class `GeminiOptions` (baris 50): ; class `GeminiClient` (baris 59): __init__(), close(), _code(), _retryable(), _friendly_error(), _search_access_error(), _safe_event_label(), _diagnostic(), stream()

**`app/services/hybrid_evidence.py`**

`_label()` (baris 41); `_safe_cell()` (baris 68); `_format_db_row()` (baris 77); class `HybridEvidence` (baris 91): record(), _missing_database(), _documents_sufficient(), refusal(), database_part_when_document_missing(), source_footer()

**`app/services/invoice_email_service.py`**

`_rupiah()` (baris 38); `_tanggal()` (baris 46); `_periode()` (baris 54); `_escape()` (baris 62); `_validasi_invoice()` (baris 66); `buat_pdf_invoice_pendaftaran()` (baris 87); `_html_invoice()` (baris 247); `kirim_email_tagihan_bulanan()` (baris 273); `kirim_email_invoice_pendaftaran()` (baris 337)

**`app/services/log_service.py`**

`_admin_aktif()` (baris 7); `aktivitas_terbaru()` (baris 17); `filter_aktivitas()` (baris 22)

**`app/services/otp_service.py`**

`kirim_otp()` (baris 29); `verifikasi_otp()` (baris 101)

**`app/services/program_service.py`**

`_admin_aktif()` (baris 18); `_teks()` (baris 34); `_bilangan_bulat()` (baris 47); `_uang()` (baris 59); `_bobot()` (baris 73); `buat_program()` (baris 82); `ubah_program()` (baris 119); `buat_ruang()` (baris 167); `ubah_ruang()` (baris 183)

**`app/services/report_service.py`**

`_admin_aktif()` (baris 71); `daftar_jenis_laporan()` (baris 81); `ambil_laporan()` (baris 86); `_siapkan_data_ekspor()` (baris 95); `_direktori_laporan()` (baris 104); `_catat_ekspor()` (baris 110); `ekspor_csv()` (baris 122); `ekspor_excel()` (baris 142)

**`app/services/schedule_service.py`**

`_admin_aktif()` (baris 14); `_id_positif()` (baris 30); `_hari()` (baris 42); `_jam()` (baris 51); `_opsi_ada()` (baris 64); `_cek_referensi_aktif()` (baris 68); `opsi_program()` (baris 88); `opsi_tutor()` (baris 97); `opsi_ruang()` (baris 106); `daftar_jadwal()` (baris 115); `detail_jadwal()` (baris 138); `_validasi_data()` (baris 153); `_pesan_bentrok()` (baris 172); `buat_jadwal()` (baris 182); `ubah_jadwal()` (baris 212); `nonaktifkan_jadwal()` (baris 270)

**`app/services/search_grounding.py`**

`get_field()` (baris 12); `valid_source_url()` (baris 18); `citations_from_step()` (baris 28); `suggestions_from_step()` (baris 44); `deduplicate_citations()` (baris 54)

**`app/services/student_service.py`**

`_siswa_aktif()` (baris 15); `_read()` (baris 25); `kelas_saya()` (baris 35); `program_akademik()` (baris 39); `jadwal_saya()` (baris 43); `pertemuan_saya()` (baris 51); `rekap_absensi()` (baris 58); `riwayat_absensi()` (baris 64); `ringkasan_nilai()` (baris 70); `detail_nilai()` (baris 76); `catatan_materi()` (baris 82); `profil_saya()` (baris 88); `ubah_profil()` (baris 92); `ganti_password()` (baris 108)

**`app/services/tutor_service.py`**

`_tutor_aktif()` (baris 11); `profil()` (baris 27); `ubah_profil()` (baris 40); `ganti_password()` (baris 58)


## Folder `app/repositories`

**`app/repositories/academic_repo.py`**

`daftar_jadwal_tutor()` (baris 8); `daftar_program_tutor()` (baris 38); `daftar_siswa_kelas()` (baris 58); `detail_siswa_kelas()` (baris 100); `daftar_pertemuan()` (baris 145); `daftar_pertemuan_jadwal_tutor()` (baris 175); `buka_pertemuan()` (baris 200); `ringkasan_pertemuan()` (baris 242); `_peserta_sesi()` (baris 263); `selesaikan_pertemuan()` (baris 281); `batalkan_pertemuan()` (baris 321); `daftar_absensi_sesi()` (baris 351); `_enrollment_sah_untuk_absensi()` (baris 401); `simpan_absensi()` (baris 444); `rekap_absensi_tutor()` (baris 519); `tambah_nilai()` (baris 563); `daftar_nilai_tutor()` (baris 596); `ubah_nilai()` (baris 624); `simpan_catatan()` (baris 652); `daftar_catatan_tutor()` (baris 676)

**`app/repositories/admin_dashboard_repo.py`**

`ringkasan_admin()` (baris 45); `jadwal_hari_ini_admin()` (baris 53)

**`app/repositories/admin_management_repo.py`**

`_catat()` (baris 18); `daftar_akun_admin()` (baris 25); `ubah_status_akun_admin()` (baris 52); `buka_kunci_akun_admin()` (baris 79); `reset_password_akun_admin()` (baris 101); `_where_siswa()` (baris 125); `daftar_siswa_admin()` (baris 150); `detail_siswa_admin()` (baris 174); `ubah_siswa_admin()` (baris 197); `daftar_tutor_admin()` (baris 222); `detail_tutor_admin()` (baris 254); `jadwal_tutor_admin()` (baris 259); `ubah_tutor_admin()` (baris 280)

**`app/repositories/ai_read_repo.py`**

`_safe()` (baris 132); class `AIReadRepository` (baris 142): __init__(), execute()

**`app/repositories/billing_repo.py`**

`buat_invoice_awal()` (baris 14); `_catat_log()` (baris 62); `buat_tagihan_bulanan()` (baris 69); `_query_tagihan()` (baris 105); `daftar_tagihan_admin()` (baris 156); `daftar_tagihan_siswa()` (baris 160); `proses_simulasi_pembayaran()` (baris 166); `daftar_riwayat_pembayaran()` (baris 236); `ambil_bukti_pembayaran()` (baris 274)

**`app/repositories/engagement_repo.py`**

`_catat_log()` (baris 11); `buat_pengumuman()` (baris 18); `daftar_pengumuman_admin()` (baris 50); `detail_pengumuman_admin()` (baris 79); `arsipkan_pengumuman()` (baris 102); `pengumuman_terbaru_siswa()` (baris 127); `_valid_pengguna()` (baris 154); `_inbox_scope()` (baris 159); `daftar_notifikasi_penerima()` (baris 170); `jumlah_notifikasi_belum_dibaca()` (baris 219); `detail_notifikasi_penerima()` (baris 230); `tandai_semua_dibaca()` (baris 273); `arsipkan_notifikasi_pribadi()` (baris 288); `_cek_program_tutor()` (baris 311); `daftar_program_pengumuman_tutor()` (baris 324); `terbitkan_pengumuman_tutor()` (baris 333); `daftar_pengumuman_tutor()` (baris 382); `akhiri_pengumuman_tutor()` (baris 401)

**`app/repositories/enrollment_repo.py`**

`kunci_program()` (baris 20); `hitung_terisi()` (baris 34); `buat_enrollment()` (baris 61); `daftar_menunggu()` (baris 141); `set_status()` (baris 189); `enrollment_siswa()` (baris 239); `siswa_aktif_di_program()` (baris 269); `batalkan_milik_siswa()` (baris 297); `proses_keputusan_admin()` (baris 343); `daftar_admin()` (baris 464); `detail_admin()` (baris 516); `pindahkan_admin()` (baris 562); `batalkan_admin()` (baris 758)

**`app/repositories/log_repo.py`**

`catat()` (baris 8); `daftar_terbaru()` (baris 21)

**`app/repositories/notification_sync_repo.py`**

`sinkronisasi()` (baris 11); `daftar_pertemuan_tertunda()` (baris 93); `buka_pertemuan_terlewat()` (baris 122)

**`app/repositories/onboarding_repo.py`**

`tolak_siswa_dan_paket()` (baris 8)

**`app/repositories/otp_repo.py`**

`simpan_otp()` (baris 24); `ambil_otp_aktif()` (baris 62); `tambah_percobaan()` (baris 83); `tandai_terpakai()` (baris 112); `hitung_kirim_terakhir()` (baris 133); `reset_password_dengan_otp()` (baris 159)

**`app/repositories/profile_repo.py`**

`proses_persetujuan_akun()` (baris 22); `detail_pengguna_persetujuan()` (baris 210)

**`app/repositories/program_repo.py`**

`tambah_program()` (baris 21); `ubah_program()` (baris 63); `tutup_program()` (baris 121); `daftar_program()` (baris 142); `daftar_program_buka_dengan_kuota()` (baris 160); `tambah_ruang()` (baris 192); `daftar_ruang()` (baris 211); `daftar_program_dengan_kuota()` (baris 237); `ubah_ruang()` (baris 258)

**`app/repositories/report_repo.py`**

`_limit_valid()` (baris 8); `pemasukan_bulanan()` (baris 14); `siswa_per_program()` (baris 32); `rekap_kehadiran()` (baris 59); `absensi_belum_terhubung()` (baris 83); `rata_nilai_per_program()` (baris 110)

**`app/repositories/schedule_repo.py`**

`daftar_opsi_program()` (baris 15); `daftar_opsi_tutor()` (baris 39); `daftar_opsi_ruang()` (baris 68); `daftar_jadwal()` (baris 92); `ambil_jadwal()` (baris 171); `cek_bentrok()` (baris 177); `buat_jadwal()` (baris 232); `ubah_jadwal()` (baris 267); `ada_riwayat_pertemuan()` (baris 308); `nonaktifkan_jadwal()` (baris 319)

**`app/repositories/student_dashboard_repo.py`**

`_valid_siswa()` (baris 71); `ringkasan_siswa()` (baris 76); `jadwal_mingguan_siswa()` (baris 85)

**`app/repositories/student_repo.py`**

`_valid_id()` (baris 15); `daftar_kelas()` (baris 21); `daftar_program_akademik()` (baris 50); `daftar_jadwal()` (baris 73); `daftar_pertemuan_siswa()` (baris 113); `rekap_absensi()` (baris 152); `daftar_absensi()` (baris 190); `ringkasan_nilai()` (baris 224); `daftar_nilai()` (baris 252); `daftar_catatan_materi()` (baris 282); `profil_siswa()` (baris 317); `ubah_profil_siswa()` (baris 334)

**`app/repositories/tutor_dashboard_repo.py`**

`ringkasan_tutor()` (baris 59); `jadwal_mingguan_tutor()` (baris 67)

**`app/repositories/tutor_repo.py`**

`profil()` (baris 8); `ubah_profil()` (baris 22); `catat_aktivitas()` (baris 46)

**`app/repositories/user_repo.py`**

`buat_user()` (baris 21); `cari_by_username()` (baris 45); `cari_by_id()` (baris 52); `cari_by_email()` (baris 59); `daftar_by_status()` (baris 66); `set_status()` (baris 73); `catat_gagal_login()` (baris 80); `reset_gagal_login()` (baris 87); `set_password()` (baris 94); `set_terverifikasi()` (baris 102); `set_persetujuan()` (baris 109); `catat_gagal_login()` (baris 120); `reset_gagal_login()` (baris 149); `reset_lock_kedaluwarsa()` (baris 167)


## Folder `app/ui`

**`app/ui/admin_dashboard_grid.py`**

`_angka()` (baris 33); `_stat_card()` (baris 40); `_tabel_jadwal()` (baris 50); `render_dashboard_admin()` (baris 67); `tampilkan_dashboard_admin()` (baris 143); `pilih_modul_admin()` (baris 158)

**`app/ui/console.py`**

`judul()` (baris 10); `sukses()` (baris 14); `gagal()` (baris 18); `info()` (baris 23); `peringatan()` (baris 28); `bersihkan_layar()` (baris 32); `jalankan_menu_role()` (baris 35)

**`app/ui/jadwal_context.py`**

`label_hari()` (baris 10); `label_jam()` (baris 14); `jam_jadwal()` (baris 22); `kondisi_jadwal_siswa()` (baris 26); `jadwal_rutin_terdekat()` (baris 44)

**`app/ui/menu_admin.py`**

`_format_waktu()` (baris 56); `_tampilkan_header()` (baris 65); `_paket_menunggu_siswa()` (baris 80); `_tampilkan_detail_akun()` (baris 89); `_daftar_akun_menunggu()` (baris 196); `_tampilkan_daftar_akun()` (baris 205); `_proses_aksi_akun()` (baris 232); `_menu_konfirmasi_akun()` (baris 345); `_format_rupiah()` (baris 433); `_tampilkan_daftar_enrollment()` (baris 440); `_tampilkan_detail_enrollment()` (baris 472); `_proses_aksi_enrollment()` (baris 502); `_menu_konfirmasi_enrollment()` (baris 593); `menu_konfirmasi()` (baris 674); `_tampilkan_modul_belum_tersedia()` (baris 699); `_tekan_enter()` (baris 721); `_pilih_program_admin()` (baris 725); `_tabel_program_admin()` (baris 759); `_program_daftar_admin()` (baris 782); `_program_tambah_admin()` (baris 797); `_program_ubah_admin()` (baris 838); `_program_toggle_admin()` (baris 908); `_ruang_daftar_admin()` (baris 938); `_ruang_tambah_admin()` (baris 963); `_ruang_ubah_admin()` (baris 977); `menu_program_ruang()` (baris 1013); `_tabel_jadwal_admin()` (baris 1065); `_ambil_opsi_jadwal()` (baris 1093); `_pilih_hari_jadwal()` (baris 1127); `_pilih_satu_jadwal()` (baris 1137); `_detail_jadwal_admin()` (baris 1162); `_label_opsi_jadwal()` (baris 1182); `_jadwal_lihat_admin()` (baris 1198); `_jadwal_tambah_admin()` (baris 1247); `_jadwal_ubah_admin()` (baris 1288); `_jadwal_nonaktifkan_admin()` (baris 1336); `menu_jadwal_admin()` (baris 1359); `_tabel_pendaftaran_admin()` (baris 1390); `_detail_pendaftaran_admin()` (baris 1410); `_menu_daftar_pendaftaran_admin()` (baris 1444); `_pilih_pendaftaran_dengan_status()` (baris 1506); `_menu_pindahkan_pendaftaran_admin()` (baris 1534); `_menu_batalkan_pendaftaran_admin()` (baris 1588); `menu_pendaftaran_admin()` (baris 1645); `jalankan()` (baris 1674)

**`app/ui/menu_admin_data.py`**

`_header()` (baris 36); `_pause()` (baris 43); `_admin_aktif()` (baris 50); `_tabel_akun()` (baris 54); `_ambil_filter_akun()` (baris 69); `_pilih_akun()` (baris 87); `menu_manajemen_akun_admin()` (baris 110); `_tabel_siswa()` (baris 195); `_pilih_siswa()` (baris 208); `_detail_siswa()` (baris 226); `_filter_siswa()` (baris 260); `_edit_siswa()` (baris 285); `menu_data_siswa_admin()` (baris 310); `_tabel_tutor()` (baris 370); `_pilih_tutor()` (baris 383); `_detail_tutor()` (baris 399); `_edit_tutor()` (baris 428); `menu_data_tutor_admin()` (baris 450)

**`app/ui/menu_admin_komunikasi.py`**

`_jeda()` (baris 27); `_header()` (baris 34); `_waktu()` (baris 41); `_detail_pengumuman()` (baris 49); `_daftar_pengumuman()` (baris 92); `_buat_pengumuman()` (baris 147); `menu_pengumuman_admin()` (baris 183); `_render_log()` (baris 210); `_filter_log()` (baris 248); `menu_log_aktivitas_admin()` (baris 268)

**`app/ui/menu_admin_laporan.py`**

`_jeda()` (baris 26); `_header()` (baris 33); `_format()` (baris 40); `_tabel_halaman()` (baris 58); `_pesan_hak_akses_laporan()` (baris 77); `_tampilkan_laporan()` (baris 86); `_pilih_jenis_ekspor()` (baris 124); `_ekspor_csv()` (baris 143); `_ekspor_excel()` (baris 168); `menu_laporan_admin()` (baris 191)

**`app/ui/menu_auth.py`**

`tampilkan_header()` (baris 26); `menu_verifikasi_registrasi()` (baris 70); `_proses_password_sementara()` (baris 192); `menu_login()` (baris 230); `menu_register()` (baris 283); `menu_lupa_password()` (baris 334); `jalankan()` (baris 390)

**`app/ui/menu_notifikasi.py`**

`_header()` (baris 18); `_pilih()` (baris 24); `_pause()` (baris 30); `_waktu()` (baris 35); `_sumber()` (baris 39); `_target()` (baris 46); `_detail()` (baris 61); `_daftar()` (baris 106); `jalankan()` (baris 139)

**`app/ui/menu_pembayaran.py`**

`_jeda()` (baris 47); `_waktu()` (baris 54); `_header()` (baris 62); `_tabel_tagihan()` (baris 69); `_tabel_pembayaran()` (baris 98); `_aksi_buat_bukti_pdf()` (baris 124); `_aksi_kirim_bukti_email()` (baris 137); `_pilih_payment()` (baris 176); `_admin_daftar_tagihan()` (baris 195); `_admin_daftar_tunggakan()` (baris 220); `_admin_riwayat()` (baris 233); `_admin_pilih_bukti()` (baris 246); `menu_pembayaran_admin()` (baris 265); `_siswa_tagihan_saya()` (baris 317); `_siswa_bayar_tagihan()` (baris 330); `_siswa_riwayat()` (baris 401); `_siswa_pilih_bukti()` (baris 424); `menu_pembayaran_siswa()` (baris 443)

**`app/ui/menu_siswa.py`**

`_jeda()` (baris 50); `_pengguna_siswa()` (baris 57); `_ambil_pendaftaran()` (baris 68); `_kartu_ringkas()` (baris 73); `_tabel_pendaftaran()` (baris 106); `_dashboard_legacy_007c()` (baris 140); `_dashboard()` (baris 280); `menu_katalog()` (baris 287); `menu_status_pendaftaran()` (baris 388); `_menu_fitur_belum_terhubung()` (baris 409); `_jalankan_onboarding()` (baris 455); `jalankan()` (baris 618)

**`app/ui/menu_siswa_academic.py`**

`_jeda()` (baris 38); `_header()` (baris 45); `_hasil()` (baris 53); `_nilai()` (baris 62); `_tanggal()` (baris 71); `_waktu()` (baris 79); `_tabel_paginasi()` (baris 85); `_pilih_data()` (baris 123); `_program_akademik()` (baris 156); `pilih_data_paginasi()` (baris 197); `tampilkan_katalog_paginasi()` (baris 202); `_panel_info_kelas()` (baris 211); `_label_status_sesi()` (baris 247); `_riwayat_pertemuan_siswa()` (baris 253); `_sesi_per_program_jadwal()` (baris 300); `_panel_rencana_siswa()` (baris 312); `_detail_kelas_siswa()` (baris 344); `menu_kelas_saya()` (baris 372); `_info_jadwal_kosong()` (baris 414); `menu_jadwal_saya()` (baris 435); `menu_absensi_siswa()` (baris 488); `_build_rapor_text()` (baris 527); `menu_nilai_rapor()` (baris 560); `menu_catatan_materi()` (baris 624); `_lihat_profil()` (baris 640); `menu_profil_siswa()` (baris 661); `menu_tanya_ai_info()` (baris 708)

**`app/ui/menu_tutor.py`**

`_dashboard()` (baris 38); `jalankan()` (baris 42)

**`app/ui/menu_tutor_academic.py`**

`_layar()` (baris 38); `_pause()` (baris 54); `_hasil()` (baris 58); `_form_teks()` (baris 63); `_konfirmasi()` (baris 72); `_pilih()` (baris 77); `_teks_nilai()` (baris 122); `_tabel()` (baris 132); `_run_service()` (baris 152); `_programs()` (baris 161); `_pilih_program()` (baris 169); `_jadwal()` (baris 186); `_pilih_jadwal()` (baris 194); `_pilih_siswa()` (baris 212); `_pilih_pertemuan()` (baris 225); `_detail_jadwal_tutor()` (baris 249); `_jelajah_jadwal_tutor()` (baris 330); `_jadwal_hari_ini()` (baris 378); `_jadwal_mingguan()` (baris 387); `_kelas_dan_siswa()` (baris 394); `_buka_pertemuan()` (baris 440); `_label_pertemuan()` (baris 451); `_catatan_pada_pertemuan()` (baris 459); `_kelola_detail_pertemuan()` (baris 477); `_kelola_pertemuan_hari_ini()` (baris 539); `_peserta_absensi_unik()` (baris 550); `_layar_absensi_siswa()` (baris 563); `_isi_absensi()` (baris 589); `_absensi()` (baris 671); `_nilai()` (baris 706); `_materi()` (baris 778); `_profil()` (baris 822); `jalankan_modul()` (baris 867)

**`app/ui/menu_tutor_pengumuman.py`**

`_header()` (baris 16); `_pause()` (baris 22); `_pick()` (baris 27); `_waktu()` (baris 35); `_buat()` (baris 39); `_list()` (baris 78); `jalankan()` (baris 117)

**`app/ui/menu_tutor_tertunda.py`**

`jalankan()` (baris 14)

**`app/ui/proyeksi_pertemuan.py`**

`_tanggal()` (baris 10); `_jam()` (baris 23); `_cari_sesi()` (baris 34); `_ringkas_slot()` (baris 49); `proyeksi_jadwal()` (baris 73)

**`app/ui/student_dashboard_grid.py`**

`_angka()` (baris 30); `_kartu()` (baris 36); `_grid_kartu()` (baris 43); `_jam()` (baris 56); `_panel_kelas()` (baris 64); `_panel_jadwal()` (baris 89); `_weekly_preview()` (baris 113); `_panel_prioritas()` (baris 138); `_quick_access()` (baris 163); `render_dashboard_siswa()` (baris 185); `tampilkan_dashboard_siswa()` (baris 231)

**`app/ui/tabel.py`**

`tampilkan_tabel()` (baris 7)

**`app/ui/tutor_dashboard_grid.py`**

`_n()` (baris 21); `_kartu()` (baris 28); `_jam()` (baris 35); `_status()` (baris 41); `_tabel_hari()` (baris 53); `_jadwal_mingguan()` (baris 76); `render_dashboard_tutor()` (baris 95); `tampilkan_dashboard_tutor()` (baris 174)


## Folder `app/utils`

**`app/utils/academic_validation.py`**

`id_positif()` (baris 11); `jenis_nilai()` (baris 23); `nilai_angka()` (baris 32); `status_absensi()` (baris 47); `teks_catatan()` (baris 56); `tanggal_valid()` (baris 67)

**`app/utils/csv_safety.py`**

`nilai_csv_aman()` (baris 7)

**`app/utils/exceptions.py`**

class `AppError` (baris 4): ; class `DataTidakValid` (baris 8): ; class `DataTidakDitemukan` (baris 12): ; class `DuplikatData` (baris 16): ; class `TidakDiizinkan` (baris 20): ; class `AkunTerkunci` (baris 24): ; class `KuotaPenuh` (baris 28): ; class `JadwalBentrok` (baris 32): 

**`app/utils/formatters.py`**

`rupiah()` (baris 6); `tanggal()` (baris 11); `persen()` (baris 16)

**`app/utils/security.py`**

`hash_password()` (baris 15); `verifikasi_password()` (baris 34); `buat_otp()` (baris 56); `hash_otp()` (baris 72); `verifikasi_otp()` (baris 86)

**`app/utils/student_validation.py`**

`teks_opsional()` (baris 14); `nomor_hp_opsional()` (baris 27); `validasi_profil()` (baris 38)

**`app/utils/validators.py`**

`validasi_username()` (baris 12); `validasi_email()` (baris 27); `validasi_password()` (baris 41); `validasi_no_hp()` (baris 70); `validasi_nominal()` (baris 85); `validasi_nilai()` (baris 100)

# 10. Inventaris modul AI UI, RAG dan entry point (tambahan)

## `app/ui/ai`

**`app/ui/ai/action_preview.py`**: `make_preview` (baris 13); `simulate_action` (baris 25)

**`app/ui/ai/ai_theme.py`**: `fit_width` (baris 19); `workspace_left` (baris 25); `prompt_prefix` (baris 30); `make_console` (baris 35); `question_style` (baris 39)

**`app/ui/ai/chat_screen.py`**: `ChatScreen`: __init__, _question, _choice, _menu, _history, _help, run, _scroll_chat_loop, _chat_loop

**`app/ui/ai/chat_state.py`**: `Message`: __post_init__; `ChatState`: __post_init__, add, recent, clear, page, page_count

**`app/ui/ai/demo.py`**: `main` (baris 9)

**`app/ui/ai/gallery.py`**: `Example`: ; `_message` (baris 49); `render_example` (baris 56); `run_gallery` (baris 107)

**`app/ui/ai/mock_responder.py`**: `MockEvent`: ; `MockResponder`: reply, stream

**`app/ui/ai/response_renderer.py`**: `clean_text` (baris 21); `_within_workspace` (baris 25); `render_header` (baris 34); `render_table` (baris 47); `_message_body` (baris 68); `_user_bubble_width` (baris 85); `render_message` (baris 91); `render_transcript` (baris 105); `render_chat` (baris 125)

**`app/ui/ai/streaming_renderer.py`**: `play_stream` (baris 15)

## `app/services/rag`

**`app/services/rag/chunker.py`**: `TextChunk`: source_label; `_sections_markdown` (baris 34); `_split_long_block` (baris 50); `_split_section` (baris 66); `chunk_document` (baris 102)

**`app/services/rag/document_loader.py`**: `DocumentFormatError`: ; `DocumentAccessError`: ; `Document`: assert_access; `_parse_simple_frontmatter` (baris 53); `_metadata` (baris 83); `_read_pdf` (baris 111); `load_document` (baris 136)

**`app/services/rag/embedding_client.py`**: `EmbeddingError`: ; `normalize` (baris 16); `GeminiEmbedder`: __init__, _embed, embed_documents, embed_query

**`app/services/rag/rag_chat_tool.py`**: `_configured_path` (baris 37); `rag_enabled` (baris 49); `RAGKnowledgeTool`: __init__, from_environment, _get_store, search

**`app/services/rag/vector_store.py`**: `IndexAccessError`: ; `IndexCompatibilityError`: ; `SearchHit`: ; `KnowledgeVectorStore`: __init__, _source_path, _relative, _check_collection, _collection, index_document, search

## `app`

**`app/db.py`**: `konfigurasi_koneksi` (baris 46); `tes_koneksi` (baris 64); `tutup_pool` (baris 101)

**`app/main.py`**: `main` (baris 7)

**`app/session.py`**: `set_user` (baris 6); `get_user` (baris 12); `logout` (baris 16); `sudah_login` (baris 21); `punya_role` (baris 25)

