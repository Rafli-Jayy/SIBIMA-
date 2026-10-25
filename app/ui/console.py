"""Pembantu tampilan dasar berbasis rich."""
from rich.console import Console
from rich.panel import Panel
import os


console = Console()


def judul(teks):
    console.print(Panel(f"[bold]{teks}[/bold]", border_style="cyan"))


def sukses(pesan):
    console.print(f"[bold green]✓[/bold green] {pesan}")


def gagal(pesan):
    console.print(f"[bold red]✗[/bold red] {pesan}")


def info(pesan):
    console.print(f"[bold cyan]i[/bold cyan] {pesan}")



def peringatan(pesan):
    console.print(f"[bold yellow]![/bold yellow] {pesan}")


def bersihkan_layar():
    os.system('cls' if os.name == 'nt' else 'clear')

def jalankan_menu_role(role, judul_halaman, subtitle, fitur):
    """Menampilkan dashboard interaktif sesuai role pengguna."""
    import questionary
    from questionary import Choice, Separator, Style
    from rich.align import Align

    from app import session

    if not session.punya_role(role):
        peringatan("Akses ditolak. Silakan login dengan akun yang sesuai.")
        return

    gaya = Style([
        ("qmark", "fg:#00ffff bold"),
        ("question", "fg:#ffffff bold"),
        ("answer", "fg:#00ffff bold"),
        ("pointer", "fg:#00ffff bold"),
        ("highlighted", "fg:#00ffff bold"),
        ("selected", "fg:#00ffff"),
        ("separator", "fg:#444444"),
        ("instruction", "fg:#888888 italic"),
    ])

    while session.punya_role(role):
        pengguna = session.get_user() or {}
        nama = pengguna.get(
            "nama_lengkap",
            pengguna.get("username", "Pengguna"),
        )

        bersihkan_layar()

        console.print(
            Panel(
                Align.center(
                    f"[bold cyan]{judul_halaman}[/]\n"
                    f"[bold white]{subtitle}[/]"
                ),
                border_style="cyan",
                padding=(1, 4),
                expand=True,
            )
        )

        console.print(
            Panel(
                f"[bold white]Selamat datang, "
                f"[cyan]{nama}[/cyan]![/bold white]\n"
                f"[dim]ROLE: {role.upper()}  •  SESI AKTIF[/dim]\n\n"
                "[white]Pilih modul yang ingin dibuka.[/white]\n"
                "[dim]Modul yang belum selesai dibuat akan "
                "ditandai sebagai pengembangan.[/dim]",
                title="[bold cyan]DASHBOARD[/bold cyan]",
                border_style="bright_blue",
                padding=(1, 2),
                expand=True,
            )
        )

        pilihan_menu = [
            Choice(title=f"  {label}", value=kode)
            for label, kode in fitur
        ]

        pilihan_menu.extend([
            Separator("────────────────────────"),
            Choice("  🚪 Logout", value="logout"),
        ])

        pilihan = questionary.select(
            "Pilih modul:",
            choices=pilihan_menu,
            style=gaya,
            qmark="⚡",
            pointer="▶",
            instruction=" (Gunakan ↑/↓ lalu Enter)",
        ).ask()

        if pilihan is None or pilihan == "logout":
            session.logout()
            sukses("Logout berhasil. Sesi telah ditutup.")
            input("Tekan Enter untuk kembali ke menu utama...")
            return

        label = next(
            (
                teks
                for teks, kode in fitur
                if kode == pilihan
            ),
            pilihan,
        )

        bersihkan_layar()

        console.print(
            Panel(
                f"[bold cyan]{label}[/]\n\n"
                "[white]Navigasi dashboard berhasil.[/]\n\n"
                "[dim]Fitur ini belum dihubungkan ke service "
                "pada tahap ini. Implementasinya akan mengikuti "
                "urutan pengembangan SIBIMA.[/dim]",
                title="[bold yellow]MODUL DALAM PENGEMBANGAN[/bold yellow]",
                border_style="cyan",
                padding=(1, 3),
                expand=True,
            )
        )

        input("Tekan Enter untuk kembali ke dashboard...")
