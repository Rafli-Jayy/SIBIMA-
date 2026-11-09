"""Pratinjau tindakan palsu dalam workspace yang sama dengan chat."""
from copy import deepcopy
from rich import box
from rich.align import Align
from rich.panel import Panel
from rich.table import Table
from .response_renderer import clean_text
from .ai_theme import question_style, fit_width, PREVIEW_MAX, prompt_prefix

ALLOWED_ACTIONS = {"buat_pengumuman_demo"}


def make_preview(draft: dict, console_width: int = 100):
    table = Table(show_header=False, box=box.SIMPLE, expand=False, pad_edge=False)
    table.add_column("Parameter", style="dim", width=12, no_wrap=True)
    table.add_column("Isi", overflow="fold")
    table.add_row("Penerima", clean_text(draft.get("target", ""), 120))
    table.add_row("Judul", clean_text(draft.get("title", ""), 180))
    table.add_row("Pesan", clean_text(draft.get("body", ""), 1200))
    return Align.center(Panel(table, title="PRATINJAU PENGUMUMAN", border_style="grey35",
                              width=fit_width(console_width, PREVIEW_MAX), padding=(1, 2),
                              subtitle="Belum diterbitkan"))


def simulate_action(console, draft: dict) -> str:
    """Tidak membuat perubahan data, jaringan, atau berkas."""
    import questionary
    if draft.get("action") not in ALLOWED_ACTIONS:
        return "Tindakan tidak dikenali dan tidak diproses."
    draft = deepcopy(draft)
    while True:
        console.clear()
        console.print(make_preview(draft, console_width=console.width))
        console.print(Align.center(Panel("Pratinjau offline: pengumuman tidak akan dikirim atau disimpan.",
                                   border_style="grey35", width=fit_width(console.width, PREVIEW_MAX))))
        option = questionary.select(
            "Pilih tindakan", choices=["Periksa lagi", "Ubah judul", "Ubah isi", "Simulasikan penerbitan", "Batalkan"],
            default="Periksa lagi", qmark=prompt_prefix(console.width), pointer="›", style=question_style(),
        ).ask()
        if option in (None, "Batalkan"):
            return "Pengumuman dibatalkan. Tidak ada perubahan data."
        if option == "Periksa lagi":
            continue
        if option in ("Ubah judul", "Ubah isi"):
            field = "title" if option == "Ubah judul" else "body"
            value = questionary.text("Judul baru" if field == "title" else "Isi pengumuman",
                                    default=str(draft[field]), qmark=prompt_prefix(console.width),
                                    style=question_style()).ask()
            if value is not None and value.strip():
                draft[field] = value.strip()[:1200]
            continue
        if option == "Simulasikan penerbitan":
            return "Pratinjau penerbitan selesai. Pengumuman tidak disimpan atau dikirim."
