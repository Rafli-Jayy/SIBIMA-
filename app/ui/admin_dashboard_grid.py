"""PATCH-007A: tampilan dashboard Admin berbasis grid Rich.

Tidak mengubah database, hak akses, maupun tujuan menu yang ada.
"""

from rich.align import Align
from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from app.ui.console import console


# Seluruh kode modul Admin lama wajib tetap dapat diakses.
KELOMPOK_MENU = (
    ("Prioritas", (("Pusat Konfirmasi", "konfirmasi"),
                   ("Pendaftaran", "pendaftaran"),
                   ("Pembayaran", "pembayaran"))),
    ("Data Pengguna", (("Manajemen Akun", "akun"),
                       ("Data Siswa", "siswa"),
                       ("Data Tutor", "tutor"))),
    ("Akademik", (("Program dan Ruang", "program"),
                  ("Jadwal", "jadwal"))),
    ("Laporan & Komunikasi", (("Laporan", "laporan"),
                             ("Komunikasi", "pengumuman"),
                             ("Log Aktivitas", "log"),
                             ("SIBIMA-AI", "ai"))),
)


def _angka(data, key):
    """None berarti tidak tersedia, berbeda dari nol."""
    if data is None or data.get(key) is None:
        return "—"
    return str(data[key])


def _stat_card(data, key, label, subjudul, warna="cyan"):
    angka = _angka(data, key)
    isi = Group(
        Align.center(Text(angka, style=f"bold {warna}")),
        Align.center(Text(subjudul, style="dim", overflow="ellipsis")),
    )
    return Panel(isi, title=label, title_align="left", border_style="blue",
                 padding=(0, 1), expand=True)


def _tabel_jadwal(rows):
    t = Table(box=None, expand=True, show_header=True, header_style="bold cyan",
              padding=(0, 1))
    t.add_column("Jam", no_wrap=True, width=13)
    t.add_column("Program", overflow="ellipsis")
    t.add_column("Tutor / Ruang", overflow="ellipsis")
    for item in rows:
        start, end = item.get("jam_mulai"), item.get("jam_selesai")
        def jam(v):
            if v is None:
                return "?"
            return v.strftime("%H:%M") if hasattr(v, "strftime") else str(v)[:5]
        t.add_row(f"{jam(start)}–{jam(end)}", str(item.get("program") or "-"),
                  f"{item.get('tutor') or '-'} / {item.get('ruang') or '-'}")
    return t


def render_dashboard_admin(nama: str, ringkasan: dict | None,
                           jadwal: list[dict] | None, *, width: int = 120):
    """Pure Rich renderable: mudah diuji dengan data tiruan."""
    identitas = Text()
    identitas.append("S I B I M A  /  ADMIN", style="bold cyan")
    identitas.append("\nPusat Kendali Bimbel", style="bold white")
    identitas.append("\nSelamat datang, ", style="dim")
    identitas.append(str(nama), style="cyan")  # bukan Rich markup dari input pengguna
    header = Panel(identitas, border_style="cyan", padding=(0, 2))

    kartu = [
        _stat_card(ringkasan, "siswa_aktif", "Siswa Aktif", "Akun terverifikasi"),
        _stat_card(ringkasan, "tutor_aktif", "Tutor Aktif", "Siap mengajar"),
        _stat_card(ringkasan, "program_buka", "Program Buka", "Menerima siswa"),
        _stat_card(ringkasan, "enrollment_aktif", "Pendaftaran Aktif", "Enrollment aktif"),
    ]
    jumlah_kolom = 4 if width >= 112 else (2 if width >= 66 else 1)
    baris_kartu = []
    for i in range(0, len(kartu), jumlah_kolom):
        baris = Table.grid(expand=True, padding=(0, 1))
        for _ in range(len(kartu[i:i+jumlah_kolom])):
            baris.add_column(ratio=1)
        baris.add_row(*kartu[i:i+jumlah_kolom])
        baris_kartu.append(baris)

    perhatian = Table.grid(expand=True, padding=(0, 1))
    perhatian.add_column(ratio=3)
    perhatian.add_column(justify="right", ratio=1)
    for key, label in (
        ("konfirmasi_akun", "Konfirmasi akun"),
        ("konfirmasi_pendaftaran", "Konfirmasi pendaftaran"),
        ("tagihan_belum_lunas", "Invoice belum lunas"),
        ("tagihan_terlambat", "Invoice lewat jatuh tempo"),
        ("sesi_perlu_laporan", "Sesi perlu laporan"),
    ):
        perhatian.add_row(label, _angka(ringkasan, key))
    panel_perhatian = Panel(perhatian, title="PERLU PERHATIAN",
                            title_align="left", border_style="yellow", padding=(1, 1))

    if jadwal is None:
        isi_jadwal = Text("Jadwal tidak dapat dimuat.", style="yellow")
    elif not jadwal:
        isi_jadwal = Text("Tidak ada jadwal rutin aktif hari ini.", style="dim")
    else:
        isi_jadwal = _tabel_jadwal(jadwal)
    panel_jadwal = Panel(isi_jadwal, title="JADWAL HARI INI (RUTIN)",
                         title_align="left", border_style="blue", padding=(1, 1))

    if width >= 105:
        ringkasan_bawah = Table.grid(expand=True, padding=(0, 1))
        ringkasan_bawah.add_column(ratio=1)
        ringkasan_bawah.add_column(ratio=1)
        ringkasan_bawah.add_row(panel_perhatian, panel_jadwal)
    else:
        ringkasan_bawah = Group(panel_perhatian, panel_jadwal)

    quick = Table.grid(expand=True, padding=(0, 1))
    if width >= 73:
        quick.add_column(ratio=1)
        quick.add_column(ratio=1)
        quick.add_row("[cyan]01[/] Konfirmasi & Tagihan", "[cyan]02[/] Akun & Pengguna")
        quick.add_row("[cyan]03[/] Program & Jadwal", "[cyan]04[/] Laporan & Komunikasi")
    else:
        quick.add_column()
        for item in ("01 Konfirmasi & Tagihan", "02 Akun & Pengguna",
                     "03 Program & Jadwal", "04 Laporan & Komunikasi"):
            quick.add_row(item)
    quick_panel = Panel(quick, title="AKSES CEPAT", title_align="left",
                        border_style="bright_black", padding=(0, 1))
    footer = Text("Pilih kelompok menu dengan ↑/↓ dan Enter. Data diperbarui saat kembali.",
                  style="dim")
    if ringkasan is None:
        footer.append("\nStatistik tidak tersedia; periksa koneksi database.", style="yellow")
    return Group(header, *baris_kartu, ringkasan_bawah, quick_panel, footer)


def tampilkan_dashboard_admin(nama: str):
    """Gagal baca data tidak boleh membuat admin logout atau menampilkan angka palsu."""
    from app.repositories import admin_dashboard_repo
    try:
        ringkasan = admin_dashboard_repo.ringkasan_admin()
    except Exception:
        ringkasan = None
    try:
        jadwal = admin_dashboard_repo.jadwal_hari_ini_admin()
    except Exception:
        jadwal = None
    console.print(render_dashboard_admin(nama, ringkasan, jadwal,
                                         width=console.size.width))


def pilih_modul_admin(style):
    """Navigasi ringkas. 'dashboard' meminta redraw agar Questionary tak menumpuk."""
    import questionary
    from questionary import Choice, Separator

    choices = [Choice(f"{i}. {label}", value=i-1)
               for i, (label, _) in enumerate(KELOMPOK_MENU, start=1)]
    choices += [Separator("────────────────────"),
                Choice("Logout", value="logout")]
    selected = questionary.select(
        "Pilih area kerja:", choices=choices, style=style,
        qmark="⚡", pointer="▶", instruction=" (↑/↓ lalu Enter)",
    ).ask()
    if selected is None or selected == "logout":
        return "logout"
    if not isinstance(selected, int) or not 0 <= selected < len(KELOMPOK_MENU):
        return "dashboard"
    title, items = KELOMPOK_MENU[selected]
    sub = [Choice(label, value=kode) for label, kode in items]
    sub += [Separator("────────────────────"),
            Choice("Kembali ke dashboard", value="kembali")]
    choice = questionary.select(
        f"{title}:", choices=sub, style=style,
        qmark="⚡", pointer="▶", instruction=" (↑/↓ lalu Enter)",
    ).ask()
    if choice is None or choice == "kembali":
        return "dashboard"
    return choice
