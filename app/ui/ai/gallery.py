"""Galeri visual 18 skenario UI SIBIMA-AI tanpa database/Gemini.

Cara pakai: python -m app.ui.ai.demo --gallery
Seluruh data administratif pada galeri adalah ILUSTRASI, bukan akun nyata.
"""
from dataclasses import dataclass
from typing import List
from rich.align import Align
from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from .chat_state import ChatState, Message
from .response_renderer import render_chat, render_message, render_header, render_table
from .action_preview import make_preview
from .ai_theme import fit_width, question_style, prompt_prefix


@dataclass(frozen=True)
class Example:
    key: str
    title: str
    category: str
    note: str


EXAMPLES = [
    Example("welcome", "01 · Layar awal", "Percakapan", "Halaman kosong sebelum pesan pertama"),
    Example("single", "02 · Pesan pengguna & AI", "Percakapan", "Bubble pengguna kanan, AI kiri"),
    Example("multiple", "03 · Beberapa putaran chat", "Percakapan", "Transkrip berlanjut tanpa header berulang"),
    Example("long", "04 · Jawaban panjang / ringkasan", "Konten", "Markdown dengan subjudul dan daftar"),
    Example("code", "05 · Kode Python", "Konten", "Syntax highlight dari Markdown"),
    Example("schedule", "06 · Tabel jadwal", "Data", "Contoh jadwal siswa"),
    Example("grades", "07 · Tabel nilai", "Data", "Contoh rapor siswa"),
    Example("billing", "08 · Tabel tagihan", "Data", "Contoh informasi keuangan"),
    Example("empty", "09 · Data kosong", "Status", "Tidak ada jadwal atau tagihan"),
    Example("stream", "10 · Streaming berlangsung", "Status", "Respons parsial saat dibuat"),
    Example("action", "11 · Pratinjau aksi", "Aksi", "Detail tindakan sebelum persetujuan"),
    Example("approval", "12 · Menunggu konfirmasi", "Aksi", "Penjelasan pilihan konfirmasi"),
    Example("success", "13 · Aksi selesai (simulasi)", "Status", "Contoh pemberitahuan sukses"),
    Example("error", "14 · Kegagalan API", "Status", "Gangguan respons"),
    Example("denied", "15 · Akses ditolak", "Keamanan", "Role tidak berwenang"),
    Example("tutor", "16 · Informasi Tutor", "Peran", "Contoh daftar kelas mengajar"),
    Example("admin", "17 · Informasi Admin", "Peran", "Contoh ringkasan aktivitas"),
    Example("narrow", "18 · Tabel terminal sempit", "Responsif", "Detail vertikal menggantikan tabel lebar"),
]


def _message(role: str, user_text: str, answer: str, kind="markdown", data=None, width=100):
    st = ChatState(role=role)
    st.add(Message("user", user_text))
    st.add(Message("assistant", answer, kind=kind, data=data or {}))
    return render_chat(st, console_width=width, show_composer=False)


def render_example(key: str, width: int = 110):
    """Hasil renderable yang dapat diuji tanpa input interaktif."""
    if key == "welcome":
        return render_chat(ChatState(), console_width=width, show_composer=False)
    if key == "single":
        return _message("siswa", "Apa itu algoritma?", "Algoritma adalah langkah-langkah yang logis dan terurut untuk menyelesaikan masalah.", width=width)
    if key == "multiple":
        st = ChatState()
        st.add(Message("user", "Halo"))
        st.add(Message("assistant", "Halo! Mau belajar materi apa hari ini?"))
        st.add(Message("user", "Jelaskan fungsi dalam Python"))
        st.add(Message("assistant", "Fungsi adalah blok kode yang dapat digunakan ulang, misalnya `def hitung(a, b): return a + b`."))
        return render_chat(st, visible_messages=6, console_width=width, show_composer=False)
    if key == "long":
        return _message("siswa", "Ringkas konsep algoritma", "**Algoritma** adalah urutan langkah untuk menyelesaikan persoalan.\n\n### Ciri utama\n\n1. **Jelas:** setiap langkah dipahami.\n2. **Terurut:** memiliki alur yang logis.\n3. **Berakhir:** memiliki kondisi selesai.\n\n### Contoh\n\nMengurutkan angka dari terkecil ke terbesar adalah contoh masalah yang dapat diselesaikan memakai algoritma.", width=width)
    if key == "code":
        return _message("siswa", "Buatkan contoh fungsi Python", "Berikut fungsi sederhana:\n\n```python\ndef hitung_total(a: int, b: int) -> int:\n    return a + b\n\nprint(hitung_total(4, 5))  # 9\n```", width=width)
    if key == "schedule":
        return _message("siswa", "Jadwal saya minggu ini", "**Contoh jadwal kelas**\n\n*Ilustrasi, bukan data akun SIBIMA.*", "table", {"columns": ["Hari", "Program", "Jam"], "rows": [{"Hari": "Senin", "Program": "Matematika", "Jam": "15:30"}, {"Hari": "Rabu", "Program": "Fisika", "Jam": "16:00"}]}, width)
    if key == "grades":
        return _message("siswa", "Tampilkan nilai saya", "**Contoh nilai akademik**\n\n*Nilai berikut hanya ilustrasi.*", "table", {"columns": ["Jenis", "Nilai"], "rows": [{"Jenis": "Tugas", "Nilai": "90"}, {"Jenis": "Kuis", "Nilai": "85"}, {"Jenis": "UTS", "Nilai": "88"}]}, width)
    if key == "billing":
        return _message("siswa", "Status tagihan saya", "**Contoh tagihan bulanan**\n\n*Angka ini bukan tagihan asli.*", "table", {"columns": ["Periode", "Jumlah", "Status"], "rows": [{"Periode": "Oktober", "Jumlah": "Rp 250.000", "Status": "Lunas"}, {"Periode": "November", "Jumlah": "Rp 250.000", "Status": "Belum dibayar"}]}, width)
    if key == "empty":
        return _message("siswa", "Tampilkan jadwal hari ini", "**Belum ada jadwal yang dapat ditampilkan.**\n\nSilakan lihat jadwal mingguan atau katalog program.\n\n*Simulasi tampilan data kosong.*", width=width)
    if key == "stream":
        st = ChatState()
        st.add(Message("user", "Jelaskan variabel Python"))
        return render_chat(st, console_width=width, pending="Variabel dalam Python digunakan untuk menyimpan nilai. Sebagai contoh, kita bisa... ▍", show_composer=False)
    if key == "action":
        draft = {"action": "buat_pengumuman_demo", "target": "Siswa kelas Matematika", "title": "Persiapan Pertemuan", "body": "Harap membawa buku catatan untuk pertemuan berikutnya."}
        return Group(render_header("tutor", width), Text(""), make_preview(draft, width))
    if key == "approval":
        return Group(render_header("tutor", width), Text(""), Align.center(Panel(
            "Sebelum diterbitkan, pengguna harus memilih konfirmasi.\n\n› Konfirmasi tindakan\n  Ubah judul / isi\n  Batalkan\n\n*Tidak ada aksi sungguhan pada Patch 1.*",
            title="KONFIRMASI TINDAKAN · SIMULASI", border_style="yellow", width=fit_width(width, 78), expand=False)))
    if key == "success":
        return _message("tutor", "Terbitkan pengumuman", "**Pratinjau selesai.**\n\nTidak ada pengumuman yang disimpan atau dikirim. Ini contoh tampilan status sukses pada aplikasi nanti.", width=width)
    if key == "error":
        return _message("siswa", "Jelaskan materi", "Maaf, respons tidak dapat ditampilkan. Coba lagi atau kembali ke menu.", "error", width=width)
    if key == "denied":
        return _message("siswa", "Ubah nilai siswa lain", "Akses ditolak. Perubahan nilai hanya dapat dilakukan oleh pengguna yang berwenang melalui fitur yang sesuai.", "error", width=width)
    if key == "tutor":
        return _message("tutor", "Tampilkan kelas yang saya ajar", "**Contoh daftar kelas Tutor**\n\n*Data ilustrasi.*", "table", {"columns": ["Kelas", "Hari", "Siswa"], "rows": [{"Kelas": "Matematika", "Hari": "Senin", "Siswa": "12"}, {"Kelas": "Fisika", "Hari": "Rabu", "Siswa": "8"}]}, width)
    if key == "admin":
        return _message("admin", "Berikan ringkasan SIBIMA", "**Contoh ringkasan administrasi**\n\n- Program aktif: 5\n- Akun menunggu persetujuan: 2\n- Pembayaran belum diproses: 3\n\n*Angka ilustrasi, bukan ringkasan PostgreSQL.*", width=width)
    if key == "narrow":
        return Group(render_header("siswa", width), Text(""), render_message(Message("assistant", "**Contoh data dalam tampilan vertikal**", kind="markdown"), console_width=width), Text(""), render_table({"columns": ["Hari", "Program", "Jam"], "rows": [{"Hari": "Senin", "Program": "Matematika", "Jam": "15:30"}, {"Hari": "Rabu", "Program": "Fisika", "Jam": "16:00"}]}, narrow=True))
    raise ValueError("Skenario galeri tidak dikenal")


def run_gallery(console=None):
    """Menampilkan setiap keadaan UI melalui pilihan Questionary."""
    from .ai_theme import make_console
    console = console or make_console()
    try:
        import questionary
    except ImportError:
        console.print("[red]Questionary belum terpasang.[/red]")
        return
    screen = console.screen(hide_cursor=False) if console.is_terminal else None
    if screen is None:
        from contextlib import nullcontext
        screen = nullcontext()
    with screen:
        while True:
            console.clear()
            console.print(Align.center(Text("GALERI UI SIBIMA-AI — CONTOH OFFLINE", style="bold cyan"), width=fit_width(console.width)))
            console.print(Align.center(Text("Pilih salah satu skenario untuk melihat desainnya.", style="dim"), width=fit_width(console.width)))
            console.print()
            options = [f"{x.title}  [{x.category}]" for x in EXAMPLES] + ["Kembali"]
            selected = questionary.select("Pilih tampilan", choices=options,
                                          qmark=prompt_prefix(console.width),
                                          pointer="›", style=question_style()).ask()
            if selected is None or selected == "Kembali":
                return
            example = next(x for x in EXAMPLES if selected.startswith(x.title))
            console.clear()
            console.print(Align.center(Text(example.title, style="bold cyan"), width=fit_width(console.width)))
            console.print(Align.center(Text(example.note, style="dim"), width=fit_width(console.width)))
            console.print(Align.center(Text("DATA AKUN / TINDAKAN HANYA ILUSTRASI", style="dim"), width=fit_width(console.width)))
            console.print()
            console.print(render_example(example.key, console.width))
            console.print()
            questionary.press_any_key_to_continue(
                "Tekan tombol apa saja untuk kembali ke galeri",
                style=question_style(),
            ).ask()


if __name__ == "__main__":
    run_gallery()
