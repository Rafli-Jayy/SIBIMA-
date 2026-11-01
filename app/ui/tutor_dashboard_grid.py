"""PATCH-007B: Dashboard Tutor Rich berbentuk grid, kompatibel Questionary.

UI ini bersifat read-only; menu utama Tutor yang lama tetap menjadi navigasi.
"""
from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align

from app.ui.console import console


HARI_NAMA = {
    'senin': 'Senin', 'selasa': 'Selasa', 'rabu': 'Rabu',
    'kamis': 'Kamis', 'jumat': 'Jumat', 'sabtu': 'Sabtu', 'minggu': 'Minggu',
}


def _n(data, key):
    """Angka 0 tetap 0; error/None menjadi em dash agar tidak menyesatkan."""
    if data is None or data.get(key) is None:
        return '—'
    return str(data[key])


def _kartu(label, value, detail):
    return Panel(Group(
        Align.center(Text(value, style='bold cyan')),
        Align.center(Text(detail, style='dim', overflow='ellipsis')),
    ), title=label, title_align='left', border_style='blue', padding=(0, 1), expand=True)


def _jam(v):
    if v is None:
        return '--:--'
    return v.strftime('%H:%M') if hasattr(v, 'strftime') else str(v)[:5]


def _status(row):
    """Sesi tanpa record masih TERJADWAL, bukan selesai/terlaksana."""
    value = row.get('status_sesi_hari_ini')
    return {
        None: 'Terjadwal',
        'perlu_laporan': 'Perlu laporan',
        'selesai': 'Selesai',
        'batal': 'Batal',
        'terlaksana': 'Sesi historis',
    }.get(value, str(value))


def _tabel_hari(rows, width):
    table = Table(box=None, expand=True, show_header=True, header_style='bold cyan', padding=(0, 1))
    table.add_column('Jam', no_wrap=True, width=11)
    table.add_column('Program', overflow='fold')
    if width >= 90:
        table.add_column('Ruang / Peserta', overflow='fold')
        table.add_column('Status sesi', overflow='fold')
    elif width >= 68:
        table.add_column('Status', overflow='fold')
    for row in rows[:5]:
        name = str(row.get('nama_program') or '-')
        time = f"{_jam(row.get('jam_mulai'))}–{_jam(row.get('jam_selesai'))}"
        place = str(row.get('nama_ruang') or '-')
        pupils = str(row.get('jumlah_siswa') if row.get('jumlah_siswa') is not None else '?')
        if width >= 90:
            table.add_row(Text(time), Text(name), Text(f'{place} • {pupils} siswa'), Text(_status(row)))
        elif width >= 68:
            table.add_row(Text(time), Text(name + ' / ' + place), Text(_status(row)))
        else:
            table.add_row(Text(time), Text(name + ' / ' + place + ' / ' + _status(row)))
    return table


def _jadwal_mingguan(rows, width):
    table = Table(box=None, expand=True, show_header=True, header_style='bold cyan', padding=(0, 1))
    table.add_column('Hari', no_wrap=True, width=7)
    table.add_column('Jam', no_wrap=True, width=11)
    table.add_column('Program / Ruang', overflow='fold')
    if width >= 90:
        table.add_column('Peserta', justify='right')
    for row in rows[:6]:
        name = str(row.get('nama_program') or '-')
        place = str(row.get('nama_ruang') or '-')
        data = [Text(HARI_NAMA.get(row.get('hari'), str(row.get('hari') or '-'))),
                Text(f"{_jam(row.get('jam_mulai'))}–{_jam(row.get('jam_selesai'))}"),
                Text(f'{name} / {place}')]
        if width >= 90:
            data.append(Text(str(row.get('jumlah_siswa') if row.get('jumlah_siswa') is not None else '?')))
        table.add_row(*data)
    return table


def render_dashboard_tutor(pengguna: dict, ringkasan: dict | None,
                           jadwal: list[dict] | None, *, width: int = 110):
    """Buat Rich renderable murni, agar dapat diuji tanpa database."""
    nama = str(pengguna.get('nama_lengkap') or pengguna.get('username') or 'Tutor')
    username = str(pengguna.get('username') or '-')
    header = Text()
    header.append('S I B I M A  /  TUTOR', style='bold cyan')
    header.append('\nPusat Aktivitas Pengajar', style='bold white')
    header.append('\nSelamat datang, ', style='dim')
    header.append(nama, style='cyan')
    header.append('  •  @' + username, style='dim')
    header_panel = Panel(header, border_style='cyan', padding=(0, 2))

    card_rows = []
    cards = (
        _kartu('Program Diampu', _n(ringkasan, 'program_diampu'), 'Program berjadwal aktif'),
        _kartu('Jadwal Aktif', _n(ringkasan, 'jadwal_aktif'), 'Jadwal rutin mingguan'),
        _kartu('Siswa Aktif', _n(ringkasan, 'siswa_aktif'), 'Siswa unik di program'),
        _kartu('Perlu Laporan', _n(ringkasan, 'sesi_perlu_laporan'), 'Sesi tersimpan belum selesai'),
    )
    cols = 4 if width >= 112 else (2 if width >= 68 else 1)
    for i in range(0, len(cards), cols):
        row = Table.grid(expand=True, padding=(0, 1))
        for _ in cards[i:i+cols]:
            row.add_column(ratio=1)
        row.add_row(*cards[i:i+cols])
        card_rows.append(row)

    if jadwal is None:
        today_content = Text('Jadwal tidak dapat dimuat.', style='yellow')
        weekly_content = Text('Jadwal mingguan tidak dapat dimuat.', style='yellow')
    elif not jadwal:
        today_content = Text('Tidak ada jadwal mengajar aktif hari ini.', style='dim')
        weekly_content = Text('Belum ada jadwal aktif untuk akun Tutor ini.', style='dim')
    else:
        today = [r for r in jadwal if r.get('hari_ini') is True]
        today_content = (_tabel_hari(today, width) if today else
                         Text('Tidak ada jadwal mengajar aktif hari ini.', style='dim'))
        weekly_content = _jadwal_mingguan(jadwal, width)

    today_panel = Panel(today_content, title='JADWAL HARI INI',
                        title_align='left', border_style='blue', padding=(1, 1))
    weekly_panel = Panel(weekly_content, title='JADWAL MINGGUAN (RUTIN)',
                         title_align='left', border_style='bright_black', padding=(1, 1))
    # 2 kolom cukup lebar untuk tabel; jangan paksa pada PowerShell kecil.
    if width >= 110:
        panels = Table.grid(expand=True, padding=(0, 1))
        panels.add_column(ratio=1)
        panels.add_column(ratio=1)
        panels.add_row(today_panel, weekly_panel)
    else:
        panels = Group(today_panel, weekly_panel)

    quick = Table.grid(expand=True, padding=(0, 1))
    if width >= 73:
        quick.add_column(ratio=1)
        quick.add_column(ratio=1)
        quick.add_row('[cyan]01[/] Jadwal Mengajar', '[cyan]02[/] Kelas dan Siswa')
        quick.add_row('[cyan]03[/] Absensi', '[cyan]04[/] Nilai')
        quick.add_row('[cyan]05[/] Catatan Materi', '[cyan]06[/] Profil Saya')
        quick.add_row('[cyan]🔔[/] Notifikasi', '[dim]00[/] Logout')
    else:
        quick.add_column()
        for label in ('01 Jadwal Mengajar', '02 Kelas dan Siswa', '03 Absensi',
                      '04 Nilai', '05 Catatan Materi', '06 Profil Saya',
                      '🔔 Notifikasi', '00 Logout'):
            quick.add_row(Text(label))
    quick_panel = Panel(quick, title='AKSES CEPAT', title_align='left',
                        border_style='bright_black', padding=(0, 1))

    footer = Text('Pilih modul menggunakan ↑/↓ dan Enter. Data disegarkan saat kembali.', style='dim')
    footer.append('\nTerjadwal ≠ sudah mengajar; hanya sesi selesai masuk rekap final.', style='dim')
    if ringkasan is None:
        footer.append('\nStatistik tidak tersedia; periksa koneksi database.', style='yellow')
    if jadwal is not None and len(jadwal) > 6:
        footer.append('\nJadwal mingguan menampilkan 6 jadwal pertama.', style='dim')
    return Group(header_panel, *card_rows, panels, quick_panel, footer)


def tampilkan_dashboard_tutor(pengguna: dict):
    """Statistik gagal dibaca tidak boleh memutus login Tutor."""
    from app.repositories import tutor_dashboard_repo
    tutor_id = pengguna.get('id')
    try:
        stats = tutor_dashboard_repo.ringkasan_tutor(tutor_id)
    except Exception:
        stats = None
    try:
        rows = tutor_dashboard_repo.jadwal_mingguan_tutor(tutor_id)
    except Exception:
        rows = None
    console.print(render_dashboard_tutor(pengguna, stats, rows,
                                         width=console.size.width))
