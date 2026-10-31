"""Submenu komunikasi admin: pengumuman dan log aktivitas."""

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


_LABEL_ROLE = {"siswa": "Siswa", "tutor": "Tutor"}


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


def _detail_pengumuman(item, status):
    while True:
        bersihkan_layar()
        label_status = "PENGUMUMAN AKTIF" if status == "aktif" else "ARSIP PENGUMUMAN"
        _header("Detail Pengumuman", f"{label_status} • ID {item['id']}")
        isi = Text()
        isi.append(str(item.get("judul") or "Tanpa judul"), style="bold cyan")
        isi.append("\n\n")
        isi.append(str(item.get("isi") or ""), style="white")
        isi.append("\n\n")
        target = ", ".join(_LABEL_ROLE.get(role, role) for role in item.get("target_roles", [])) or "Belum ditentukan"
        isi.append(
            f"Penerima: {target}\nDibuat oleh: {item.get('nama_pembuat') or '-'}\nWaktu dibuat: {_waktu(item.get('created_at'))}",
            style="dim",
        )
        if item.get("archived_at"):
            isi.append(f"\nDiarsipkan: {_waktu(item.get('archived_at'))}", style="yellow")
        console.print(Panel(isi, border_style="cyan", padding=(1, 3), expand=True))
        choices = []
        if status == "aktif":
            choices.append(Choice("Arsipkan pengumuman", value="arsip"))
        choices.extend([Separator("────────────────────────"), Choice("Kembali", value="kembali")])
        pilihan = questionary.select("Tindakan:", choices=choices, style=GAYA).ask()
        if pilihan in (None, "kembali"):
            return
        if pilihan == "arsip":
            yakin = questionary.confirm(
                "Arsipkan pengumuman ini? Pengumuman yang diarsipkan tidak dapat dikembalikan.",
                default=False, style=GAYA,
            ).ask()
            if not yakin:
                continue
            try:
                engagement_service.arsipkan_pengumuman_admin(item["id"])
                sukses("Pengumuman berhasil diarsipkan dan tidak lagi tampil di Notifikasi penerima.")
                _jeda()
                return
            except (ValueError, PermissionError) as exc:
                gagal(str(exc)); _jeda(); return
            except psycopg.Error as exc:
                gagal(f"Pengumuman gagal diarsipkan ({type(exc).__name__})."); _jeda(); return


def _daftar_pengumuman(status):
    try:
        data = engagement_service.daftar_pengumuman_admin(status=status, limit=500)
    except (PermissionError, ValueError) as exc:
        gagal(str(exc)); _jeda(); return
    except psycopg.Error as exc:
        gagal(f"Pengumuman gagal dimuat ({type(exc).__name__})."); _jeda(); return

    if not data:
        peringatan("Belum ada pengumuman dalam kategori ini."); _jeda(); return

    halaman = 0
    ukuran = 15
    while True:
        bersihkan_layar()
        judul = "Pengumuman Aktif" if status == "aktif" else "Arsip Pengumuman"
        subjudul = "Pilih satu judul untuk melihat detail" if status == "aktif" else "Arsip bersifat permanen dan tidak dapat dipulihkan"
        _header(judul, subjudul)
        tabel = Table(title=judul, header_style="bold cyan", expand=True)
        tabel.add_column("ID", width=6, justify="right")
        tabel.add_column("Judul", min_width=25, overflow="fold")
        tabel.add_column("Penerima", min_width=15)
        tabel.add_column("Waktu", min_width=17)
        potong = data[halaman * ukuran:(halaman + 1) * ukuran]
        for item in potong:
            target = ", ".join(_LABEL_ROLE.get(role, role) for role in item.get("target_roles", [])) or "-"
            tabel.add_row(str(item["id"]), str(item.get("judul") or ""), target, _waktu(item.get("created_at")))
        console.print(tabel)
        opsi = [Choice(f"{str(item.get('judul') or 'Tanpa judul')[:65]}  •  ID {item['id']}", value=item["id"]) for item in potong]
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
            item = next((row for row in potong if row["id"] == pilihan), None)
            if item:
                _detail_pengumuman(item, status)
                # Muat ulang setelah detail, terutama bila pengumuman baru saja diarsipkan.
                try:
                    data = engagement_service.daftar_pengumuman_admin(status=status, limit=500)
                except (PermissionError, ValueError, psycopg.Error) as exc:
                    gagal(f"Daftar pengumuman gagal dimuat ulang: {exc}"); _jeda(); return
                if not data:
                    return
                halaman = min(halaman, (len(data) - 1) // ukuran)


def _buat_pengumuman():
    bersihkan_layar()
    _header("Buat Pengumuman", "Terbitkan notifikasi untuk role yang dipilih")
    judul = questionary.text("Judul pengumuman (maks. 150 karakter):", style=GAYA).ask()
    if judul is None:
        return
    isi_input = questionary.text("Isi pengumuman (gunakan \\n untuk baris baru):", style=GAYA).ask()
    if isi_input is None:
        return
    isi = isi_input.replace("\\n", "\n").strip()
    penerima = questionary.checkbox(
        "Pilih penerima (minimal satu):",
        choices=[Choice("Siswa", value="siswa"), Choice("Tutor", value="tutor")],
        style=GAYA,
    ).ask()
    if penerima is None:
        return
    if not penerima:
        gagal("Pilih minimal satu penerima pengumuman."); _jeda(); return
    label = " dan ".join(_LABEL_ROLE[role] for role in penerima)
    konfirmasi = questionary.confirm(
        f"Terbitkan pengumuman untuk: {label}? (Notifikasi dalam aplikasi, bukan email)",
        default=False, style=GAYA,
    ).ask()
    if not konfirmasi:
        peringatan("Pembuatan pengumuman dibatalkan."); _jeda(); return
    try:
        item = engagement_service.buat_pengumuman(judul, isi, penerima)
        sukses(f"Pengumuman ID {item['id']} berhasil diterbitkan untuk {label}.")
    except (ValueError, PermissionError) as exc:
        gagal(str(exc))
    except psycopg.Error as exc:
        gagal(f"Pengumuman gagal disimpan ({type(exc).__name__}).")
    _jeda()


def menu_pengumuman_admin():
    if not session.punya_role("admin"):
        peringatan("Akses komunikasi ditolak. Login sebagai admin.")
        return
    while session.punya_role("admin"):
        bersihkan_layar()
        _header("Menu Komunikasi", "Pengelolaan pengumuman dan arsip")
        pilihan = questionary.select(
            "Pilih tindakan:",
            choices=[
                Choice("Buat Pengumuman", value="buat"),
                Choice("Pengumuman Aktif", value="aktif"),
                Choice("Arsip Pengumuman", value="arsip"),
                Separator("────────────────────────"),
                Choice("Kembali", value="kembali"),
            ], style=GAYA, qmark="⚡", pointer="▶",
        ).ask()
        if pilihan in (None, "kembali"):
            return
        if pilihan == "buat":
            _buat_pengumuman()
        elif pilihan == "aktif":
            _daftar_pengumuman("aktif")
        elif pilihan == "arsip":
            _daftar_pengumuman("arsip")


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
