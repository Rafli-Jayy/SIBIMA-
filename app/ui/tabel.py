"""Pembantu menampilkan tabel dengan rich."""
from rich.table import Table

from app.ui.console import console


def tampilkan_tabel(judul, kolom, baris):
    """kolom: list nama kolom. baris: list of list/tuple nilai."""
    tabel = Table(title=judul, header_style="bold cyan")
    for nama in kolom:
        tabel.add_column(str(nama))
    for b in baris:
        tabel.add_row(*[str(x) for x in b])
    console.print(tabel)
