"""Pengumuman kelas oleh Tutor: penerima hanya enrollment aktif pada program yang diampu."""
import psycopg
import questionary
from questionary import Choice,Style,Separator
from rich.panel import Panel
from rich.markup import escape
from rich.table import Table
from app.services import engagement_service
from app.ui.console import console,bersihkan_layar,gagal,sukses,peringatan

STYLE=Style([('qmark','fg:#00ffff bold'),('question','fg:#ffffff bold'),
 ('pointer','fg:#00ffff bold'),('highlighted','fg:#00ffff bold'),
 ('selected','fg:#00ffff'),('separator','fg:#526477')])


def _header(sub):
    bersihkan_layar()
    console.print(Panel('[bold cyan]S I B I M A / PENGUMUMAN KELAS[/]\n[dim]'+sub+'[/]',
                        padding=(1,2),border_style='cyan'))


def _pause():
    try: input('\nTekan Enter untuk melanjutkan...')
    except (EOFError,KeyboardInterrupt): pass


def _pick(label,choices):
    choices=[Choice(name,value=v) for name,v in choices]
    choices.extend([Separator('──────────────────'),Choice('Kembali',value='__back__')])
    selected = questionary.select(label,choices=choices,style=STYLE,qmark='⚡',pointer='▶').ask()
    # Questionary mengembalikan title ketika Choice.value=None; normalisasikan sentinel.
    return None if selected == '__back__' else selected


def _waktu(v):
    return v.strftime('%d-%m-%Y %H:%M') if hasattr(v,'strftime') else str(v or '—')


def _buat():
    try: programs=engagement_service.daftar_program_pengumuman_tutor()
    except (psycopg.Error,PermissionError,ValueError) as exc:
        gagal(f'Kelas tidak tersedia ({type(exc).__name__}).');_pause();return
    if not programs:
        _header('Buat Pengumuman')
        peringatan('Tidak ada kelas dengan jadwal aktif yang kamu ampu.');_pause();return
    _header('Langkah 1/4 • Pilih program')
    program_id=_pick('Kelas tujuan:',[(f"{p['nama']} • {p['jumlah_siswa']} siswa aktif",p['id']) for p in programs])
    if program_id is None:return
    _header('Langkah 2/4 • Tulis pengumuman')
    judul=questionary.text('Judul (maksimal 150 karakter):',style=STYLE).ask()
    if judul is None:return
    isi=questionary.text('Isi (ketik \\n untuk baris baru):',style=STYLE).ask()
    if isi is None:return
    isi=isi.replace('\\n','\n')
    _header('Langkah 3/4 • Masa berlaku')
    durasi=_pick('Berakhir otomatis:', [('7 hari (disarankan)','7_hari'),
              ('Setelah pertemuan berikutnya','pertemuan_berikut'),
              ('Tanggal dan jam khusus (WIB)','tanggal')])
    if durasi is None:return
    tanggal=None
    if durasi=='tanggal':
        tanggal=questionary.text('Berakhir pada (YYYY-MM-DD HH:MM):',style=STYLE).ask()
        if tanggal is None:return
    _header('Langkah 4/4 • Pratinjau dan konfirmasi')
    program=next(p for p in programs if p['id']==program_id)
    console.print(Panel(f'[bold]{escape(judul.strip())}[/]\n\n{escape(isi.strip())}\n\n'
                        f"[dim]Kelas: {escape(str(program['nama']))} • Penerima saat ini: {program['jumlah_siswa']} siswa aktif[/]\n"
                        f'[dim]Masa berlaku: {durasi}[/]',border_style='cyan'))
    if not questionary.confirm('Terbitkan pengumuman ini?',default=False,style=STYLE).ask():return
    try:
        result=engagement_service.buat_pengumuman_tutor(program_id,judul,isi,durasi,tanggal)
        sukses(f"Pengumuman diterbitkan ke {result['jumlah_penerima']} siswa. Berakhir: {_waktu(result['expires_at'])}.")
    except (psycopg.Error,PermissionError,ValueError) as exc:
        gagal(f'Gagal menerbitkan: {exc if isinstance(exc,(PermissionError,ValueError)) else type(exc).__name__}')
    _pause()


def _list(status):
    while True:
        try: rows=engagement_service.daftar_pengumuman_tutor(status)
        except (psycopg.Error,PermissionError,ValueError) as exc:
            gagal(f'Pengumuman gagal dimuat ({type(exc).__name__}).');_pause();return
        _header('Pengumuman aktif' if status=='aktif' else 'Arsip dan pengumuman kedaluwarsa')
        if not rows:
            peringatan('Belum ada pengumuman di bagian ini.');_pause();return
        # Satu judul hanya satu pilihan, tanpa duplikasi tabel + daftar.
        page=0
        while True:
            view=rows[page*7:(page+1)*7]
            opts=[(f"{row['judul'][:48]} • {row['nama_program']} ({row['jumlah_penerima']} siswa)",row['batch_key']) for row in view]
            if page>0: opts.append(('← Sebelumnya','__prev__'))
            if (page+1)*7<len(rows): opts.append(('Berikutnya →','__next__'))
            chosen=_pick('Pilih pengumuman:',opts)
            if chosen is None:return
            if chosen=='__prev__':page-=1;_header('Daftar pengumuman');continue
            if chosen=='__next__':page+=1;_header('Daftar pengumuman');continue
            item=next((row for row in rows if row['batch_key']==chosen),None)
            if not item:break
            _header('Detail pengumuman')
            console.print(Panel(f"[bold cyan]{escape(str(item['judul']))}[/]\n\n{escape(str(item['isi']))}\n\n"
              f"[dim]Kelas: {escape(str(item['nama_program']))} • {item['jumlah_penerima']} penerima\n"
              f"Diterbitkan: {_waktu(item['created_at'])} • Berakhir: {_waktu(item['expires_at'])}[/]",
              border_style='cyan'))
            if status=='aktif':
                if _pick('Tindakan:', [('Arsipkan Pengumuman','end')])=='end':
                    if questionary.confirm('Arsipkan pengumuman ini untuk semua penerima? Arsip tidak dapat dikembalikan.',default=False,style=STYLE).ask():
                        try:
                            engagement_service.akhiri_pengumuman_tutor(item['batch_key'])
                            sukses('Pengumuman berhasil diarsipkan dan tidak tampil lagi di kotak masuk aktif siswa.')
                        except (psycopg.Error,PermissionError,ValueError) as exc:
                            gagal(f'Tindakan gagal ({type(exc).__name__}).')
                        _pause()
            else:_pause()
            break


def jalankan():
    while True:
        _header('Kelola pengumuman kelas sendiri, tanpa email broadcast')
        op=_pick('Pilih menu:', [('Buat Pengumuman Baru','buat'),
            ('Pengumuman Aktif','aktif'),('Arsip & Pengumuman Berakhir','arsip')])
        if op is None:return
        if op=='buat':_buat()
        else:_list(op)
