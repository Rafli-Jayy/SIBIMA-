"""Pusat Notifikasi SIBIMA PATCH-N2: Rich + Questionary, daftar satu kali tanpa tabel ganda."""
import psycopg
import questionary
from questionary import Choice, Separator, Style
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from app.services import engagement_service
from app.ui.console import console, bersihkan_layar, gagal, sukses, peringatan

_STYLE=Style([('qmark','fg:#00ffff bold'),('question','fg:#ffffff bold'),
  ('answer','fg:#00ffff bold'),('pointer','fg:#00ffff bold'),
  ('highlighted','fg:#00ffff bold'),('selected','fg:#00ffff'),
  ('separator','fg:#526477'),('instruction','fg:#91a4b7 italic')])
_PAGE=7


def _header(role, sub):
    bersihkan_layar()
    console.print(Panel(f'[bold cyan]S I B I M A / NOTIFIKASI {role.upper()}[/]\n[dim]{sub}[/]',
                        border_style='cyan',padding=(1,2),expand=True))


def _pilih(label,items,back=True):
    choices=[Choice(k,value=v) for k,v in items]
    if back: choices += [Separator('──────────────────'),Choice('Kembali',value='__back__')]
    return questionary.select(label,choices=choices,style=_STYLE,qmark='⚡',pointer='▶').ask()


def _pause():
    try: input('\nTekan Enter untuk melanjutkan...')
    except (EOFError,KeyboardInterrupt): pass


def _waktu(value):
    return value.strftime('%d-%m-%Y %H:%M WIB') if hasattr(value,'strftime') else str(value or '-')


def _sumber(row):
    src=row.get('sumber')
    if src=='tutor': return 'Tutor: '+str(row.get('nama_pembuat') or 'Tidak tersedia')
    if src=='admin': return 'Admin: '+str(row.get('nama_pembuat') or 'Tidak tersedia')
    return 'Sistem SIBIMA'


def _target(row,role):
    kind=row.get('related_type')
    if role=='tutor':
        if kind=='schedule_pending': return 'tertunda'
        if kind=='session': return 'absensi'
        if kind=='schedule': return 'jadwal'
        return None
    if kind=='grade': return 'nilai'
    if kind=='session': return 'absensi'
    if kind=='schedule': return 'jadwal'
    if row.get('kategori')=='tagihan': return 'pembayaran'
    if row.get('kategori')=='pendaftaran': return 'pendaftaran'
    return None


def _detail(role,row,arsip=False):
    try:
        item=(engagement_service.buka_notifikasi_arsip(role,row['id']) if arsip
              else engagement_service.buka_notifikasi(role,row['id']))
    except (psycopg.Error,PermissionError,ValueError) as exc:
        gagal(f'Gagal membuka notifikasi ({type(exc).__name__}).');_pause();return None
    while True:
        _header(role,'Detail pesan dan identitas sumber informasi')
        pesan=Text()
        pesan.append(str(item.get('judul') or 'Tanpa judul')+'\n\n',style='bold cyan')
        pesan.append(str(item.get('isi') or '(Tidak ada isi)'),style='white')
        console.print(Panel(pesan,border_style='cyan',padding=(1,2)))
        info=Table.grid(padding=(0,1)); info.add_column(style='dim',width=18);info.add_column()
        info.add_row('Sumber',_sumber(item))
        if item.get('sumber')=='sistem' and item.get('nama_pelaku'):
            info.add_row('Tindakan oleh',str(item['nama_pelaku']))
        if item.get('nama_program'): info.add_row('Kelas',str(item['nama_program']))
        info.add_row('Kategori',str(item.get('kategori') or 'umum').capitalize())
        info.add_row('Diterbitkan',_waktu(item.get('created_at')))
        if item.get('expires_at'): info.add_row('Berlaku sampai',_waktu(item['expires_at']))
        console.print(info)
        # Arsip pribadi hanya memengaruhi kotak masuk pengguna ini,
        # termasuk notifikasi pengumuman Admin/Tutor yang diterimanya.
        # Berbeda dari arsip pengumuman milik Tutor sebagai pembuat.
        pengumuman = item.get('sumber') in ('admin', 'tutor') or item.get('kategori') == 'pengumuman'
        opts=[]
        tujuan=None if pengumuman else _target(item,role)
        if tujuan and not arsip: opts.append(('Buka menu terkait', 'open'))
        if not arsip:
            opts.append(('Arsipkan Notifikasi','archive'))
        opts.append(('Kembali ke daftar','back'))
        choice=_pilih('Tindakan:',opts,back=False)
        if choice in ('back',None): return None
        if choice=='open': return tujuan
        if choice=='archive':
            yakin=questionary.confirm('Arsipkan pesan ini hanya untuk akunmu?',default=False,style=_STYLE).ask()
            if yakin:
                try:
                    engagement_service.arsipkan_notifikasi_pribadi(role,item['id'])
                    sukses('Notifikasi telah dipindahkan ke Arsip Saya.')
                except (psycopg.Error,PermissionError,ValueError) as exc:
                    gagal(f'Gagal mengarsipkan ({type(exc).__name__}).')
                _pause();return None


def _daftar(role, *, arsip=False):
    page=0
    while True:
        try:
            # Endpoint internal mendukung parameter lama demi kompatibilitas N2;
            # antarmuka pengguna tidak lagi menampilkan filter.
            rows=engagement_service.daftar_notifikasi_filter(role,arsip=arsip,limit=500)
        except (psycopg.Error,PermissionError,ValueError) as exc:
            gagal(f'Daftar pesan tidak tersedia ({type(exc).__name__}).');_pause();return None
        page=min(page,max(0,(len(rows)-1)//_PAGE))
        portion=rows[page*_PAGE:(page+1)*_PAGE]
        _header(role, ('ARSIP SAYA' if arsip else 'KOTAK MASUK')+
                f' • {len(rows)} pesan • halaman {page+1}/{max(1,(len(rows)+_PAGE-1)//_PAGE)}')
        options=[]
        for row in portion:
            mark='●' if not row.get('sudah_dibaca') and not arsip else '✓'
            title=str(row.get('judul') or 'Tanpa judul').replace('\n',' ')[:48]
            by=_sumber(row)
            options.append((f'{mark} {title} • {by[:26]}',row['id']))
        if not options: console.print('[dim]Belum ada pesan.[/]')
        if page>0:options.append(('← Halaman sebelumnya','__prev__'))
        if (page+1)*_PAGE<len(rows):options.append(('Halaman berikutnya →','__next__'))
        options.append(('Kembali','__back__'))
        chosen=_pilih('Pilih pesan:',options,back=False)
        if chosen in (None,'__back__'):return None
        if chosen=='__prev__':page-=1;continue
        if chosen=='__next__':page+=1;continue
        row=next((r for r in portion if r['id']==chosen),None)
        if row:
            next_action=_detail(role,row,arsip=arsip)
            if next_action:return next_action


def jalankan(role: str):
    """Mengembalikan kode menu tujuan bila dipilih aksi cepat; caller menavigasi."""
    if role not in ('siswa','tutor'):
        gagal('Peran tidak valid.');return None
    try:
        engagement_service.sinkronisasi_notifikasi(role)
    except (psycopg.Error,PermissionError,ValueError) as exc:
        # Pembaca notifikasi tetap dapat dibuka meskipun sinkronisasi pengingat gagal.
        peringatan(f'Pengingat jadwal belum dapat diperbarui ({type(exc).__name__}).')
    while True:
        try: unread=engagement_service.jumlah_notifikasi_belum_dibaca(role)
        except (psycopg.Error,PermissionError,ValueError) as exc:
            gagal(f'Notifikasi gagal dimuat ({type(exc).__name__}).');_pause();return None
        _header(role,f'{unread} belum dibaca • navigasi ↑/↓ dan Enter')
        chosen=_pilih('Menu Notifikasi:',[
            ('Kotak Masuk','inbox'),
            ('Tandai Semua Dibaca','allread'),('Arsip Saya','archive'),('Kembali','back')],back=False)
        if chosen in (None,'back'):return None
        if chosen=='inbox':
            target=_daftar(role)
            if target:return target
        elif chosen=='archive':
            target=_daftar(role,arsip=True)
            if target:return target
        elif chosen=='allread':
            if questionary.confirm('Tandai seluruh pesan aktif sebagai dibaca?',default=False,style=_STYLE).ask():
                try:
                    count=engagement_service.tandai_semua_dibaca(role)
                    sukses(f'{count} pesan ditandai sudah dibaca.')
                except (psycopg.Error,PermissionError,ValueError) as exc:
                    gagal(f'Tindakan gagal ({type(exc).__name__}).')
                _pause()
