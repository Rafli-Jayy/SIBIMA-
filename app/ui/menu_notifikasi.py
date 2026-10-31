"""Pusat Notifikasi bersama untuk siswa dan tutor."""

import psycopg
import questionary
from questionary import Choice, Separator, Style
from rich.panel import Panel
from rich.table import Table

from app.services import engagement_service
from app.ui.console import console, bersihkan_layar, gagal, info, peringatan

_GAYA = Style([
    ("qmark", "fg:#00ffff bold"), ("question", "fg:#ffffff bold"),
    ("answer", "fg:#00ffff bold"), ("pointer", "fg:#00ffff bold"),
    ("highlighted", "fg:#00ffff bold"), ("selected", "fg:#00ffff"),
    ("separator", "fg:#526477"), ("instruction", "fg:#91a4b7 italic"),
])

def jalankan(role: str) -> None:
    if role not in {"siswa", "tutor"}:
        gagal("Peran notifikasi tidak valid.")
        return
    label = "SISWA" if role == "siswa" else "TUTOR"
    while True:
        bersihkan_layar()
        console.print(Panel(
            f"[bold cyan]NOTIFIKASI {label}[/bold cyan]\n[dim]Pengumuman aktif yang ditujukan untuk akunmu[/dim]",
            border_style="cyan", padding=(1, 2), expand=True,
        ))
        try:
            daftar = engagement_service.daftar_notifikasi(role)
        except (psycopg.Error, PermissionError, ValueError) as exc:
            gagal(f"Notifikasi gagal dimuat ({type(exc).__name__}).")
            input("\nTekan Enter untuk kembali...")
            return

        tabel = Table(show_header=True, header_style="bold cyan", expand=True)
        tabel.add_column("Status", width=14)
        tabel.add_column("Pengumuman", ratio=1)
        tabel.add_column("Tanggal", width=18)
        choices = []
        for item in daftar:
            status = "DIBACA" if item.get("sudah_dibaca") else "BARU"
            created = item.get("created_at")
            tanggal = created.strftime("%d %b %Y %H:%M") if hasattr(created, "strftime") else str(created or "—")
            judul = str(item.get("judul") or "Tanpa judul")
            tabel.add_row("[dim]DIBACA[/dim]" if status == "DIBACA" else "[bold yellow]BARU[/bold yellow]", judul, tanggal)
            choices.append(Choice(f"{'✓' if status == 'DIBACA' else '●'}  {judul}", value=item["id"]))
        if not daftar:
            tabel.add_row("—", "Belum ada notifikasi aktif", "—")
        console.print(tabel)
        choices.extend([Separator("────────────────────────"), Choice("Kembali", value="kembali")])
        pilihan = questionary.select(
            "Pilih notifikasi untuk membaca detail:", choices=choices, style=_GAYA,
            qmark="⚡", pointer="▶", instruction=" (↑/↓ lalu Enter)",
        ).ask()
        if pilihan is None or pilihan == "kembali":
            return
        try:
            item = engagement_service.buka_notifikasi(role, pilihan)
        except (psycopg.Error, PermissionError, ValueError) as exc:
            gagal(f"Notifikasi tidak dapat dibuka ({type(exc).__name__}).")
            input("\nTekan Enter untuk kembali...")
            continue
        bersihkan_layar()
        console.print(Panel(
            f"[bold cyan]{item.get('judul') or 'Tanpa judul'}[/bold cyan]\n\n{item.get('isi') or '(Tidak ada isi)'}",
            title=f"NOTIFIKASI {label}", border_style="cyan", padding=(1, 2), expand=True,
        ))
        created = item.get("created_at")
        if created:
            console.print(f"[dim]Diterbitkan: {created.strftime('%d %b %Y %H:%M') if hasattr(created, 'strftime') else created}[/dim]")
        input("\nTekan Enter untuk kembali ke daftar...")
