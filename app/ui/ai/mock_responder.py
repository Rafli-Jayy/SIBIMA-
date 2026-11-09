"""Respons prototipe yang wajar, tanpa menyamar sebagai Gemini atau database.

P1B memakai contoh terbatas dan deterministik. Informasi akademik umum adalah
konten nyata; informasi akun adalah ilustrasi yang diberi penanda jelas.
"""
from dataclasses import dataclass
from typing import Any, Dict, Iterator
import re


@dataclass(frozen=True)
class MockEvent:
    kind: str
    payload: Any


SAMPLE_ROWS = [
    {"Hari": "Senin", "Program": "Matematika", "Jam": "15.30–17.00"},
    {"Hari": "Rabu", "Program": "Bahasa Inggris", "Jam": "16.00–17.30"},
    {"Hari": "Jumat", "Program": "Fisika", "Jam": "16.30–18.00"},
]


class MockResponder:
    def reply(self, query: str, role: str) -> Dict[str, Any]:
        q = query.casefold().strip()
        if not q:
            return {"kind": "error", "content": "Tuliskan pertanyaan terlebih dahulu."}
        if any(x in q for x in ("simulasi gagal", "uji error", "test error")):
            return {"kind": "error", "content": "Maaf, respons tidak dapat ditampilkan. Silakan coba kembali."}
        if any(x in q for x in ("pengumuman", "buat aksi", "aksi demo")):
            if role == "siswa":
                return {"kind": "markdown", "content": "Pengumuman kelas dibuat oleh Tutor atau Admin. Sebagai Siswa, kamu dapat melihat pengumuman yang ditujukan kepadamu."}
            target = "Siswa di kelas yang diampu" if role == "tutor" else "Siswa dan Tutor"
            return {
                "kind": "action",
                "content": "Saya sudah menyiapkan draf pengumuman. Periksa penerima dan isinya sebelum melanjutkan.",
                "data": {
                    "action": "buat_pengumuman_demo",
                    "target": target,
                    "title": "Persiapan Pertemuan Berikutnya",
                    "body": "Pada pertemuan berikutnya kita akan membahas materi lanjutan. Silakan meninjau catatan pertemuan sebelumnya dan membawa perlengkapan belajar.",
                },
            }
        if any(x in q for x in ("jadwal", "nilai saya", "tabel", "tagihan")):
            if "nilai" in q:
                return {"kind": "table", "content": "**Contoh tampilan nilai akademik**\n\n*Angka di bawah hanya ilustrasi, bukan nilai akunmu.*", "data": {"columns": ["Penilaian", "Nilai"], "rows": [{"Penilaian": "Tugas 1", "Nilai": "90"}, {"Penilaian": "Kuis", "Nilai": "85"}, {"Penilaian": "UTS", "Nilai": "88"}]}}
            if "tagihan" in q:
                return {"kind": "table", "content": "**Contoh informasi tagihan**\n\n*Nominal dan status berikut hanya ilustrasi, bukan data pembayaranmu.*", "data": {"columns": ["Periode", "Jumlah", "Status"], "rows": [{"Periode": "Oktober 2026", "Jumlah": "Rp 250.000", "Status": "Lunas"}, {"Periode": "November 2026", "Jumlah": "Rp 250.000", "Status": "Belum dibayar"}]}}
            if role == "tutor":
                return {"kind": "table", "content": "**Contoh jadwal mengajar**\n\n*Ini data ilustrasi, belum mengambil jadwal Tutor dari SIBIMA.*", "data": {"columns": ["Hari", "Program", "Jam"], "rows": SAMPLE_ROWS}}
            return {"kind": "table", "content": "**Contoh jadwal kelas mingguan**\n\n*Ini data ilustrasi, belum mengambil jadwal dari akun SIBIMA.*", "data": {"columns": ["Hari", "Program", "Jam"], "rows": SAMPLE_ROWS}}
        if any(x in q for x in ("python", "kode", "pemrograman")):
            return {"kind": "markdown", "content": "**Contoh fungsi sederhana dalam Python**\n\n```python\ndef hitung_total(a, b):\n    return a + b\n\nprint(hitung_total(2, 3))  # 5\n```\n\nFungsi `hitung_total()` menerima dua angka dan mengembalikan hasil penjumlahannya."}
        if any(x in q for x in ("algoritma", "materi", "belajar")):
            return {"kind": "markdown", "content": "**Apa itu algoritma?**\n\nAlgoritma adalah urutan langkah yang jelas dan logis untuk menyelesaikan suatu masalah.\n\n**Contoh: menghitung luas persegi panjang**\n\n1. Masukkan panjang dan lebar.\n2. Kalikan panjang dengan lebar.\n3. Tampilkan hasilnya.\n\nJika panjang 5 cm dan lebar 3 cm, luasnya adalah **15 cm²**."}
        if "ringkas" in q:
            return {"kind": "markdown", "content": "Aku bisa membantu membuat ringkasan. Kirimkan teks atau topik yang ingin diringkas.\n\nUntuk pratinjau tampilan saat ini, coba ketik `algoritma` atau `contoh Python`."}
        if any(x in q for x in ("halo", "hai", "selamat pagi", "selamat malam")):
            return {"kind": "markdown", "content": "Halo! Apa yang ingin kamu bahas hari ini?\n\nKita bisa mulai dari materi pelajaran, contoh kode Python, atau informasi fitur SIBIMA."}
        return {"kind": "markdown", "content": "Aku bisa membantu membahas materi dan menunjukkan contoh tampilan fitur SIBIMA.\n\nSaat ini percakapan masih berada dalam **pratinjau antarmuka**, sehingga pertanyaan di luar contoh yang tersedia belum dapat dijawab secara bebas. Coba `jelaskan algoritma`, `contoh Python`, atau `jadwal saya`."}

    def stream(self, query: str, role: str) -> Iterator[MockEvent]:
        result = self.reply(query, role)
        for chunk in re.findall(r"\S+\s*|\n+", result["content"]):
            yield MockEvent("text_chunk", chunk)
        yield MockEvent("completed", result)
