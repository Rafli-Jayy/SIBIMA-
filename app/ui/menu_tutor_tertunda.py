"""Tindak lanjut jadwal Tutor yang terlewat, termasuk sesi yang belum pernah dibuka."""
import psycopg
import questionary
from questionary import Choice,Separator,Style
from rich.panel import Panel
from app.services import engagement_service
from app.ui.console import console,bersihkan_layar,gagal,sukses,peringatan
from app.ui import menu_tutor_academic

GAYA=Style([('qmark','fg:#00ffff bold'),('question','fg:#ffffff bold'),
            ('pointer','fg:#00ffff bold'),('highlighted','fg:#00ffff bold')])


def jalankan():
    page=0
    while True:
        bersihkan_layar()
        console.print(Panel('[bold cyan]S I B I M A / PERTEMUAN TERTUNDA[/]\n'
           '[dim]Jadwal yang lewat belum berarti kelas berlangsung. Tutor harus memverifikasi laporan.[/]',
           border_style='cyan',padding=(1,2)))
        try: rows=engagement_service.daftar_pertemuan_tertunda_tutor(200)
        except (psycopg.Error,PermissionError,ValueError) as exc:
            gagal(f'Gagal memuat jadwal tertunda ({type(exc).__name__}).');return
        if not rows:
            sukses('Tidak ada pertemuan yang perlu dilaporkan.');
            input('\nTekan Enter untuk kembali...');return
        page=min(page,(len(rows)-1)//7)
        subset=rows[page*7:(page+1)*7]
        choices=[Choice(f"{r['tanggal']} • {r['nama_program']} • "
                  f"{'Sesi ada, belum selesai' if r['session_id'] else 'Belum ada catatan sesi'}",
                 value=page*7+i) for i,r in enumerate(subset)]
        if page>0:choices.append(Choice('← Halaman sebelumnya',value='__prev__'))
        if (page+1)*7<len(rows):choices.append(Choice('Halaman berikutnya →',value='__next__'))
        choices.extend([Separator('──────────────────'),Choice('Kembali',value='__back__')])
        index=questionary.select('Pilih jadwal tertunda:',choices=choices,style=GAYA,qmark='⚡',pointer='▶').ask()
        if index in (None,'__back__'):return
        if index=='__prev__':page-=1;continue
        if index=='__next__':page+=1;continue
        row=rows[index]
        if row['session_id']:
            menu_tutor_academic._kelola_detail_pertemuan(row['session_id'])
            continue
        if not questionary.confirm(
            f"Buat laporan TERLAMBAT untuk {row['nama_program']} tanggal {row['tanggal']}? "
            'Jadwal terlewat bukan bukti kelas sudah dilaksanakan.',
            default=False,style=GAYA).ask():
            continue
        try:
            session_id=engagement_service.buka_pertemuan_terlewat_tutor(
                row['schedule_id'],row['tanggal'])
        except (psycopg.Error,ValueError,PermissionError) as exc:
            gagal(f"Tidak bisa membuka laporan: {exc if isinstance(exc,(PermissionError,ValueError)) else type(exc).__name__}")
            input('\nTekan Enter...');continue
        menu_tutor_academic._kelola_detail_pertemuan(session_id)
