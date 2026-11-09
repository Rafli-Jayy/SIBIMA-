# Tester LLM Gemini untuk SIBIMA (terpisah)

Folder ini merupakan **alat diagnosis mandiri**, tidak memanggil `app/`, database, atau UI Patch 1.

## Pasang

1. Salin folder `tools/llm_test/` ini ke dalam **root folder SIBIMA** yang berisi `.env` dan folder `app`.
2. Buka terminal VS Code di root folder SIBIMA dan aktifkan `.venv` seperti biasa.
3. Instal dependensi:

   ```powershell
   python -m pip install "google-genai>=2.3.0" python-dotenv
   ```

4. Pastikan `.env` root berisi `GEMINI_API_KEY=...` (jangan bagikan key), dan bila diinginkan `GEMINI_MODEL=gemini-3.8-flash`, `GEMINI_THINKING_LEVEL=low`.
5. Tes lokal tanpa internet: `python tools/llm_test/test_chat.py --self-test`
6. Jalankan percakapan langsung:

   ```powershell
   python tools/llm_test/test_chat.py
   ```

## Perintah

- `Halo`: kirim pertanyaan dan terima streaming.
- `/baru`: hapus histori lokal.
- `/keluar`: tutup tester.
- `python tools/llm_test/test_chat.py --thinking low`: coba respons lebih cepat.
- `python tools/llm_test/test_chat.py --once "Halo"`: uji satu pertanyaan.

## Diagnostik

- **Teks pertama** = waktu sejak sebelum pemanggilan API sampai karakter pertama.
- **Total respons** = waktu hingga streaming selesai.
- **Retry dimatikan** sehingga tidak ada tambahan waktu akibat percobaan ulang.
- Menggunakan `client.interactions.create(..., stream=True, store=False)`.
- Histori percakapan hanya di memori dalam bentuk transkrip teks sederhana, **bukan** native steps/thought signatures seperti integrasi Patch 2. Ini sengaja untuk memisahkan masalah jaringan/model/streaming dari komponen SIBIMA.
- Tidak ada penyimpanan file percakapan dan tidak mengirim data pribadi SIBIMA secara otomatis.
- **Penting:** setiap pemanggilan API dapat menggunakan kuota dan mungkin berbiaya sesuai akun Gemini API kamu.

Jika tester ini cepat tetapi chat SIBIMA lambat, penyebab kemungkinan berada pada integrasi SIBIMA, bukan model atau koneksi dasar. Bila keduanya lambat, periksa model, akses API, dan jaringan.
