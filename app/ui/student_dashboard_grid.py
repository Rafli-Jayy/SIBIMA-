"""PATCH-007C: dashboard Siswa dengan grid Rich yang hanya membaca data.

Pilihan menu tetap berada di menu_siswa.py (Questionary); tidak ada navigasi
bayangan atau penulisan database di komponen dashboard.
"""
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align

from app.ui.console import console
from app.utils.formatters import rupiah


_STATUS = {
    'menunggu_pembayaran': 'Menunggu pembayaran',
    'menunggu': 'Menunggu Admin',
    'aktif': 'Aktif',
    'ditolak': 'Ditolak',
    'batal': 'Dibatalkan',
    'selesai': 'Selesai',
}
_HARI = {
    'senin': 'Senin', 'selasa': 'Selasa', 'rabu': 'Rabu',
    'kamis': 'Kamis', 'jumat': 'Jumat', 'sabtu': 'Sabtu', 'minggu': 'Minggu',
}


def _angka(stats, key):
    if stats is None or stats.get(key) is None:
        return '—'
    return str(stats[key])


def _kartu(judul, nilai, detail):
    return Panel(Group(
        Align.center(Text(str(nilai), style='bold cyan')),
        Align.center(Text(detail, style='dim', overflow='ellipsis')),
    ), title=judul, title_align='left', border_style='blue', padding=(0, 1), expand=True)


def _grid_kartu(kartu, width):
    ncol = 4 if width >= 112 else (2 if width >= 68 else 1)
    hasil = []
    for start in range(0, len(kartu), ncol):
        batch = kartu[start:start+ncol]
        grid = Table.grid(expand=True, padding=(0, 1))
        for _ in batch:
            grid.add_column(ratio=1)
        grid.add_row(*batch)
        hasil.append(grid)
    return hasil


def _jam(value):
    if value is None:
        return '--:--'
    if hasattr(value, 'strftime'):
        return value.strftime('%H:%M')
    return str(value)[:5]


def _panel_kelas(enrollments, width):
    if not enrollments:
        body = Text('Belum ada pendaftaran. Mulai dari Katalog Program.', style='dim')
    else:
        table = Table(box=None, expand=True, show_header=True,
                      header_style='bold cyan', padding=(0, 1))
        table.add_column('Program', overflow='fold')
        table.add_column('Status', overflow='fold')
        if width >= 82:
            table.add_column('Jenjang', overflow='fold')
        for item in enrollments[:5]:
            nama = str(item.get('nama_program') or 'Program tidak diketahui')
            status = str(item.get('status') or '-')
            style = 'green' if status == 'aktif' else (
                'yellow' if status in ('menunggu_pembayaran', 'menunggu') else 'dim')
            cells = [Text(nama), Text(_STATUS.get(status, status), style=style)]
            if width >= 82:
                cells.append(Text(str(item.get('jenjang') or '-')))
            table.add_row(*cells)
        body = table
    panel = Panel(body, title='KELAS & PENDAFTARAN', title_align='left',
                  border_style='blue', padding=(1, 1))
    return panel


def _panel_jadwal(jadwal, width):
    if jadwal is None:
        body = Text('Jadwal tidak dapat dimuat.', style='yellow')
    elif not jadwal:
        body = Text('Belum ada jadwal aktif pada kelasmu.', style='dim')
    else:
        today = [row for row in jadwal if row.get('hari_ini') is True]
        if not today:
            body = Text('Tidak ada jadwal kelas hari ini.', style='dim')
        else:
            table = Table(box=None, expand=True, show_header=True,
                          header_style='bold cyan', padding=(0, 1))
            table.add_column('Jam', width=11, no_wrap=True)
            table.add_column('Program / Ruang', overflow='fold')
            for item in today[:4]:
                jam = f"{_jam(item.get('jam_mulai'))}–{_jam(item.get('jam_selesai'))}"
                program = str(item.get('nama_program') or '-')
                ruang = str(item.get('nama_ruang') or '-')
                table.add_row(Text(jam), Text(f'{program} / {ruang}'))
            body = table
    return Panel(body, title='JADWAL HARI INI', title_align='left',
                 border_style='bright_blue', padding=(1, 1))


def _weekly_preview(jadwal, width):
    if jadwal is None:
        body = Text('Jadwal mingguan tidak dapat dimuat.', style='yellow')
    elif not jadwal:
        body = Text('Belum ada jadwal mingguan. Periksa Kelas Saya atau hubungi Admin.', style='dim')
    else:
        table = Table(box=None, expand=True, show_header=True,
                      header_style='bold cyan', padding=(0, 1))
        table.add_column('Hari', no_wrap=True, width=7)
        table.add_column('Waktu', no_wrap=True, width=11)
        table.add_column('Program', overflow='fold')
        if width >= 90:
            table.add_column('Tutor / Ruang', overflow='fold')
        for item in jadwal[:5]:
            hari = _HARI.get(item.get('hari'), str(item.get('hari') or '-'))
            waktu = f"{_jam(item.get('jam_mulai'))}–{_jam(item.get('jam_selesai'))}"
            cells = [Text(hari), Text(waktu), Text(str(item.get('nama_program') or '-'))]
            if width >= 90:
                cells.append(Text(f"{item.get('nama_tutor') or '-'} / {item.get('nama_ruang') or '-'}"))
            table.add_row(*cells)
        body = table
    return Panel(body, title='JADWAL MINGGUAN (RUTIN)', title_align='left',
                 border_style='bright_black', padding=(1, 1))


def _panel_prioritas(enrollments, stats):
    menunggu_bayar = sum(item.get('status') == 'menunggu_pembayaran' for item in enrollments)
    menunggu_admin = sum(item.get('status') == 'menunggu' for item in enrollments)
    messages = []
    if menunggu_bayar:
        messages.append(Text(f'{menunggu_bayar} pendaftaran menunggu pembayaran pertama.', style='yellow'))
    if menunggu_admin:
        messages.append(Text(f'{menunggu_admin} pendaftaran menunggu keputusan Admin.', style='yellow'))
    if stats is None:
        messages.append(Text('Status tagihan belum dapat diperiksa.', style='yellow'))
    else:
        unpaid = stats.get('tagihan_belum_lunas')
        if unpaid:
            nominal = stats.get('jumlah_tagihan')
            jumlah = rupiah(nominal) if nominal is not None else 'nominal belum tersedia'
            messages.append(Text(f'{unpaid} invoice belum lunas, total {jumlah}.', style='yellow'))
        if stats.get('tagihan_terlambat'):
            messages.append(Text('Ada tagihan melewati jatuh tempo. Periksa menu Pembayaran.', style='yellow'))
    if not messages:
        messages.append(Text('Tidak ada antrean atau tagihan yang perlu perhatian.', style='green'))
    return Panel(Group(*messages), title='PERLU PERHATIAN', title_align='left',
                 border_style='yellow' if len(messages)>0 and messages[0].style=='yellow' else 'bright_black',
                 padding=(0, 1))


def _quick_access(width):
    pairs = (
        ('01', 'Katalog Program', '02', 'Kelas Saya'),
        ('03', 'Jadwal Saya', '04', 'Absensi'),
        ('05', 'Nilai & Rapor', '06', 'Tagihan'),
        ('07', 'Catatan Materi', '08', 'Notifikasi / Profil'),
    )
    grid = Table.grid(expand=True, padding=(0, 1))
    if width >= 72:
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        for a, b, c, d in pairs:
            grid.add_row(Text(f'{a}  {b}'), Text(f'{c}  {d}'))
    else:
        grid.add_column()
        for a, b, c, d in pairs:
            grid.add_row(Text(f'{a}  {b}'))
            grid.add_row(Text(f'{c}  {d}'))
    return Panel(grid, title='AKSES CEPAT', title_align='left',
                 border_style='bright_black', padding=(0, 1))


def render_dashboard_siswa(pengguna: dict, enrollments: list[dict],
                          stats: dict | None, jadwal: list[dict] | None,
                          *, width: int = 110):
    """Renderable murni untuk tes UI tanpa perlu koneksi database."""
    nama = str(pengguna.get('nama_lengkap') or pengguna.get('username') or 'Siswa')
    akun = str(pengguna.get('username') or '-')
    header = Text('S I B I M A  /  SISWA', style='bold cyan')
    header.append('\nPusat Aktivitas Belajar', style='bold white')
    header.append('\nSelamat datang, ', style='dim')
    header.append(nama, style='cyan')
    header.append('  •  @' + akun, style='dim')
    header_panel = Panel(header, border_style='cyan', padding=(0, 2))

    average = '—'
    if stats is not None:
        value = stats.get('rata_nilai_tercatat')
        average = f'{value:.2f}' if value is not None else 'Belum ada'
    cards = (
        _kartu('Kelas Aktif', _angka(stats, 'kelas_aktif'), 'Enrollment berstatus aktif'),
        _kartu('Hadir', _angka(stats, 'pertemuan_hadir'), 'Sesi selesai, hadir tercatat'),
        _kartu('Rata-rata Nilai', average, 'Nilai tercatat, bukan nilai akhir'),
        _kartu('Tagihan', _angka(stats, 'tagihan_belum_lunas'), 'Invoice belum lunas'),
    )
    sections = [header_panel, *_grid_kartu(cards, width)]
    first = _panel_kelas(enrollments, width)
    second = _panel_jadwal(jadwal, width)
    if width >= 110:
        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_row(first, second)
        sections.append(grid)
    else:
        sections.extend((first, second))
    sections.extend((_weekly_preview(jadwal, width), _panel_prioritas(enrollments, stats),
                     _quick_access(width)))
    if stats is None:
        sections.append(Text('Statistik tidak tersedia; coba cek koneksi database.', style='yellow'))
    if len(enrollments) > 5:
        sections.append(Text('Kelas & Pendaftaran: tampil 5 data pertama; buka Kelas Saya untuk lainnya.', style='dim'))
    if jadwal is not None and len(jadwal) > 5:
        sections.append(Text('Jadwal mingguan: tampil 5 jadwal pertama; buka Jadwal Saya untuk lainnya.', style='dim'))
    sections.append(Text('Gunakan ↑/↓ dan Enter pada pilihan menu di bawah. Data diperbarui saat kembali.', style='dim'))
    return Group(*sections)


def tampilkan_dashboard_siswa(pengguna: dict, enrollments: list[dict]):
    """Gagal mengambil statistik tidak boleh memutus siswa dari menu."""
    from app.repositories import student_dashboard_repo
    student_id = pengguna.get('id')
    try:
        stats = student_dashboard_repo.ringkasan_siswa(student_id)
    except Exception:
        stats = None
    try:
        jadwal = student_dashboard_repo.jadwal_mingguan_siswa(student_id)
    except Exception:
        jadwal = None
    console.print(render_dashboard_siswa(pengguna, enrollments, stats, jadwal,
                                         width=console.size.width))
