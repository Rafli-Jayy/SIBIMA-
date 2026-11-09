# Gemini Interactions API — tes cepat dengan batas tunggu

Salin file `diagnose_api.py` ke `tools/llm_test/` di folder utama proyek SIBIMA.

Jalankan dari root SIBIMA dengan virtual environment yang telah aktif:

```powershell
python -u .\tools\llm_test\diagnose_api.py
```

Tester ini langsung menggunakan REST Interactions API dengan model `gemini-3.8-flash` dan `store=false`, tanpa SDK `google-genai`, login SIBIMA, atau PostgreSQL. Tidak ada retry otomatis. Setelah 18 detik tanpa hasil, proses pengujian diakhiri sehingga terminal tidak menggantung tanpa batas. Durasi dan pesan HTTP/error ditampilkan. Kunci API dibaca dari `.env` tanpa dicetak.

Bila HTTP 200 muncul, koneksi REST API bekerja. Jika HTTP 4xx/5xx, baca pesan Google. Jika TIMEOUT, periksa jaringan/latensi sebelum menyentuh UI SIBIMA.
