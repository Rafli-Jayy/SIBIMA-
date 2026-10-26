"""Submenu pengumuman admin dan log aktivitas."""

from datetime import datetime

import psycopg
import questionary
from questionary import Choice, Separator, Style
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app import session
from app.services import engagement_service, log_service
from app.ui.console import bersihkan_layar, console, gagal, peringatan, sukses

GAYA = Style([
    ("qmark", "fg:#00ffff bold"), ("question", "fg:#ffffff bold"),
    ("answer", "fg:#00ffff bold"), ("pointer", "fg:#00ffff bold"),
    ("highlighted", "fg:#00ffff bold"), ("selected", "fg:#00ffff"),
    ("separator", "fg:#444444"), ("instruction", "fg:#888888 italic"),
])


def _jeda():
    try:
        input("\nTekan Enter untuk kembali...")
    except (EOFError, KeyboardInterrupt):
        pass


def _header(judul, subjudul):
    console.print(Panel(
        f"[bold cyan]S I B I M A[/bold cyan]\n[bold white]{judul.upper()}[/bold white]\n[dim]{subjudul}[/dim]",
        border_style="cyan", padding=(1, 3), expand=True,
    ))


def _waktu(nilai):
    if nilai is None:
        return "-"
    if isinstance(nilai, datetime):
        return nilai.strftime("%d-%m-%Y %H:%M")
    return str(nilai)


def _detail_pengumuman(item):
    bersihkan_layar()
    _header("Detail Pengumuman", f"Pengumuman ID {item['id']}")
    isi = Text()
    isi.append(str(item.get("judul") or "Tanpa judul"), style="bold cyan")
    isi.append("\n\n")
    isi.append(str(item.get("isi") or ""), style="white")
    isi.append("\n\n")
    isi.append(f"Dibuat oleh: {item.get('nama_pembuat') or '-'}\nWaktu: {_waktu(item.get('created_at'))}", style="dim")
    console.print(Panel(isi, border_style="cyan", padding=(1, 3), expand=True))
    _jeda()


def _daftar_pengumuman():
    try:
        data = engagement_service.daftar_pengumuman_admin(limit=200)
    except PermissionError as exc:
        gagal(str(exc)); _jeda(); return
    except psycopg.Error as exc:
        gagal(f"Pengumuman gagal dimuat ({type(exc).__name__})."); _jeda(); return

    if not data:
        peringatan("Belum ada pengumuman."); _jeda(); return

    # Halaman singkat untuk memilih detail tanpa memenuhi terminal dengan semua isi.
    halaman = 0
    ukuran = 20
    while True:
        bersihkan_layar()
        _header("Daftar Pengumuman", "Pengumuman global yang dapat dilihat siswa")
        tabel = Table(title="Pengumuman terbaru", header_style="bold cyan", expand=True)
        tabel.add_column("ID", width=6, justify="right")
        tabel.add_column("Judul", min_width=25, overflow="fold")
        tabel.add_column("Dibuat oleh", min_width=18, overflow="fold")
        tabel.add_column("Waktu", min_width=17)
        potong = data[halaman * ukuran:(halaman + 1) * ukuran]
        for item in potong:
            tabel.add_row(Text(str(item["id"])), Text(str(item.get("judul") or "")),
                          Text(str(item.get("nama_pembuat") or "-")), Text(_waktu(item.get("created_at"))))
        console.print(tabel)
        opsi = [Choice(f"Buka detail ID {item['id']} — {str(item.get('judul') or '')[:55]}", value=item["id"]) for item in potong]
        if halaman > 0:
            opsi.append(Choice("Halaman sebelumnya", value="prev"))
        if (halaman + 1) * ukuran < len(data):
            opsi.append(Choice("Halaman berikutnya", value="next"))
        opsi.extend([Separator("────────────────────────"), Choice("Kembali", value="kembali")])
        pilihan = questionary.select("Pilih pengumuman:", choices=opsi, style=GAYA).ask()
        if pilihan in (None, "kembali"):
            return
        if pilihan == "prev":
            halaman = max(0, halaman - 1)
        elif pilihan == "next":
            halaman = min((len(data) - 1) // ukuran, halaman + 1)
        else:
            item = next((row for row in data if row["id"] == pilihan), None)
            if item:
                _detail_pengumuman(item)


def _buat_pengumuman():
    bersihkan_layar()
    _header("Buat Pengumuman", "Pengumuman ini akan terlihat pada dashboard siswa")
    judul = questionary.text("Judul pengumuman (maks. 150 karakter):", style=GAYA).ask()
    if judul is None:
        return
    isi_input = questionary.text(
        "Isi pengumuman (gunakan \\n untuk baris baru):", style=GAYA,
    ).ask()
    if isi_input is None:
        return
    isi = isi_input.replace("\\n", "\n").strip()
    konfirmasi = questionary.confirm(
        "Terbitkan pengumuman untuk semua siswa?", default=False, style=GAYA,
    ).ask()
    if not konfirmasi:
        peringatan("Pembuatan pengumuman dibatalkan."); _jeda(); return
    try:
        item = engagement_service.buat_pengumuman(judul, isi)
        sukses(f"Pengumuman ID {item['id']} berhasil diterbitkan.")
    except (ValueError, PermissionError) as exc:
        gagal(str(exc))
    except psycopg.Error as exc:
        gagal(f"Pengumuman gagal disimpan ({type(exc).__name__}).")
    _jeda()


def menu_pengumuman_admin():
    if not session.punya_role("admin"):
        peringatan("Akses pengumuman ditolak. Login sebagai admin.")
        return
    while session.punya_role("admin"):
        bersihkan_layar()
        _header("Pengumuman", "Komunikasi resmi admin kepada siswa")
        pilihan = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Buat pengumuman", value="buat"),
                Choice("Daftar pengumuman", value="daftar"),
                Separator("────────────────────────"),
                Choice("Kembali ke dashboard", value="kembali"),
            ], style=GAYA, qmark="⚡", pointer="▶",
        ).ask()
        if pilihan in (None, "kembali"):
            return
        if pilihan == "buat":
            _buat_pengumuman()
        elif pilihan == "daftar":
            _daftar_pengumuman()


def _render_log(data, judul):
    ukuran = 20
    halaman = 0
    while True:
        bersihkan_layar()
        _header("Log Aktivitas", judul)
        tabel = Table(title="Aktivitas terbaru", header_style="bold cyan", expand=True)
        tabel.add_column("ID", width=7, justify="right")
        tabel.add_column("Waktu", min_width=17)
        tabel.add_column("Pengguna", min_width=18, overflow="fold")
        tabel.add_column("Aksi", min_width=22, overflow="fold")
        tabel.add_column("Detail", min_width=30, overflow="fold")
        potong = data[halaman * ukuran:(halaman + 1) * ukuran]
        for item in potong:
            detail = str(item.get("detail") or "-").replace("\n", " ")
            if len(detail) > 180:
                detail = detail[:177] + "..."
            tabel.add_row(Text(str(item.get("id", "-"))), Text(_waktu(item.get("created_at"))),
                          Text(str(item.get("pengguna") or "Sistem")), Text(str(item.get("aksi") or "-")), Text(detail))
        if not data:
            tabel.add_row("-", "-", "-", "-", "Tidak ada aktivitas yang cocok")
        console.print(tabel)
        console.print(f"[dim]Menampilkan {halaman * ukuran + 1 if data else 0}-{halaman * ukuran + len(potong)} dari {len(data)} entri[/dim]")
        opsi = []
        if halaman > 0:
            opsi.append(Choice("Halaman sebelumnya", value="prev"))
        if (halaman + 1) * ukuran < len(data):
            opsi.append(Choice("Halaman berikutnya", value="next"))
        opsi.extend([Separator("────────────────────────"), Choice("Kembali", value="kembali")])
        pilihan = questionary.select("Navigasi:", choices=opsi, style=GAYA).ask()
        if pilihan in (None, "kembali"):
            return
        if pilihan == "prev":
            halaman = max(0, halaman - 1)
        elif pilihan == "next":
            halaman = min((len(data) - 1) // ukuran, halaman + 1)


def _filter_log():
    pengguna = questionary.text(
        "Filter pengguna (ID, username, atau nama; kosong = semua):", style=GAYA,
    ).ask()
    if pengguna is None:
        return
    aksi = questionary.text(
        "Filter aksi (contoh LOGIN; kosong = semua):", style=GAYA,
    ).ask()
    if aksi is None:
        return
    try:
        data = log_service.filter_aktivitas(pengguna=pengguna, aksi=aksi, limit=200)
        _render_log(data, f"Filter pengguna={pengguna or 'semua'}, aksi={aksi or 'semua'}")
    except (ValueError, PermissionError) as exc:
        gagal(str(exc)); _jeda()
    except psycopg.Error as exc:
        gagal(f"Log gagal difilter ({type(exc).__name__})."); _jeda()


def menu_log_aktivitas_admin():
    if not session.punya_role("admin"):
        peringatan("Akses log aktivitas ditolak. Login sebagai admin.")
        return
    while session.punya_role("admin"):
        bersihkan_layar()
        _header("Log Aktivitas", "Jejak aktivitas yang tercatat di database")
        pilihan = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Aktivitas terbaru", value="terbaru"),
                Choice("Filter berdasarkan pengguna / aksi", value="filter"),
                Separator("────────────────────────"),
                Choice("Kembali ke dashboard", value="kembali"),
            ], style=GAYA, qmark="⚡", pointer="▶",
        ).ask()
        if pilihan in (None, "kembali"):
            return
        if pilihan == "terbaru":
            try:
                data = log_service.aktivitas_terbaru(limit=200)
                _render_log(data, "Aktivitas terbaru")
            except PermissionError as exc:
                gagal(str(exc)); _jeda()
            except psycopg.Error as exc:
                gagal(f"Log gagal dimuat ({type(exc).__name__})."); _jeda()
        elif pilihan == "filter":
            _filter_log()
