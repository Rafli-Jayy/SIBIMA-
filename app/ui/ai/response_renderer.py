"""ChatGPT-inspired terminal layout: pesan pengguna di kanan, AI di kiri.

Tidak menggunakan Panel untuk setiap jawaban AI; data tetap dirender oleh Rich.
Semua output LLM adalah konten tak tepercaya, tidak pernah dieksekusi sebagai markup ANSI.
"""
import re
from typing import Any, Dict
from rich import box
from rich.align import Align
from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from .ai_theme import ERROR, fit_width, USER_BUBBLE_MAX, WORKSPACE_MAX
from .chat_state import ChatState, Message

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def clean_text(value: Any, limit: int = 12000) -> str:
    return CONTROL_CHARS.sub("", str(value))[:limit]


def _within_workspace(renderable, console_width: int):
    """Kunci posisi kiri konten lalu pusatkan satu workspace pada layar."""
    width = fit_width(console_width)
    grid = Table.grid(padding=0, expand=False)
    grid.add_column(width=width, no_wrap=False)
    grid.add_row(renderable)
    return Align.center(grid)


def render_header(role: str, console_width: int = 100, online: bool = False):
    role_text = {"siswa": "Siswa", "tutor": "Tutor", "admin": "Admin"}.get(role, "Pengguna")
    width = fit_width(console_width)
    header = Table.grid(expand=False, padding=0)
    header.add_column(width=max(12, width // 2), overflow="ellipsis")
    header.add_column(width=max(1, width - max(12, width // 2)), justify="right", overflow="ellipsis")
    a = Text("◈  SIBIMA AI", style="bold white")
    status = ("Gemini · Online" if online else ("Pratinjau UI (offline)" if width >= 80 else "Offline"))
    b = Text(f"{role_text}  ·  {status}", style="dim")
    header.add_row(a, b)
    return _within_workspace(header, console_width)


def render_table(data: Dict[str, Any], narrow: bool = False):
    columns = data.get("columns", [])
    rows = data.get("rows", [])
    if not isinstance(columns, list) or not isinstance(rows, list) or not columns:
        return Text("Informasi tidak dapat ditampilkan dalam tabel.")
    if narrow:
        blocks = []
        for i, row in enumerate(rows[:25], start=1):
            if isinstance(row, dict):
                lines = "\n".join(f"{clean_text(col, 40)}: {clean_text(row.get(col, ''), 100)}" for col in columns[:8])
                blocks.append(Text(f"{i:02d}  {lines.replace(chr(10), '  ·  ')}"))
        return Group(*blocks) if blocks else Text("Tidak ada informasi tersedia.")
    table = Table(box=box.SIMPLE, header_style="bold cyan", expand=False, show_edge=False, pad_edge=False)
    for col in columns[:8]:
        table.add_column(clean_text(col, 48), overflow="fold")
    for row in rows[:25]:
        if isinstance(row, dict):
            table.add_row(*(clean_text(row.get(col, ""), 160) for col in columns[:8]))
    return table


def _message_body(message: Message, compact: bool, console_width: int, streaming: bool):
    if compact:
        content = clean_text(message.content, 380)
        if len(message.content) > 380:
            content += "… (lihat /riwayat untuk membaca lengkap)"
        return Text(content, overflow="fold")
    if streaming:
        return Text(clean_text(message.content), overflow="fold")
    if message.kind == "table" and message.sender == "assistant":
        return Group(Markdown(clean_text(message.content)), Text(""), render_table(message.data, narrow=fit_width(console_width) < 72))
    if message.kind == "error":
        return Text(clean_text(message.content), style=ERROR, overflow="fold")
    if message.sender == "user":
        return Text(clean_text(message.content), overflow="fold")
    return Markdown(clean_text(message.content))


def _user_bubble_width(content: str, workspace_width: int) -> int:
    """Pesan singkat mengikuti isi; pesan panjang dibungkus ke batas bubble."""
    longest = max((len(line) for line in str(content).splitlines()), default=0)
    return min(max(18, longest + 6), USER_BUBBLE_MAX, max(14, workspace_width - 2))


def render_message(message: Message, compact: bool = False, console_width: int = 100, streaming: bool = False):
    width = fit_width(console_width)
    body = _message_body(message, compact, console_width, streaming)
    if message.sender == "user":
        bubble = Panel(body, box=box.ROUNDED, width=_user_bubble_width(message.content, width),
                       expand=False, border_style="grey35", padding=(0, 2))
        return _within_workspace(Align.right(bubble, width=width), console_width)

    # Respons AI seperti ChatGPT: identitas di kiri, teks tanpa panel kotak.
    heading = Text("✦  SIBIMA AI", style="bold cyan")
    content = Group(heading, Text(""), body)
    return _within_workspace(Align.left(content, width=width), console_width)


def render_transcript(state: ChatState, visible_messages: int = 4,
                      console_width: int = 100, pending: str = None):
    """Hanya bubble pengguna dan jawaban AI, TANPA header/footer/prompt.

    Komponen ini dapat dirender ulang selama streaming tanpa mencetak
    instruksi input di antara balasan atau menyimpan chrome sebagai pesan.
    """
    items = []
    for msg in state.recent(visible_messages):
        items.append(render_message(msg, compact=len(msg.content) > 950,
                                    console_width=console_width))
        items.append(Text(""))
    if pending is not None:
        pending_msg = Message("assistant", pending or "Menyiapkan jawaban…")
        items.append(render_message(pending_msg, console_width=console_width,
                                    streaming=True))
        items.append(Text(""))
    return Group(*items)


def render_chat(state: ChatState, visible_messages: int = 4, console_width: int = 100,
                pending: str = None, show_composer: bool = True, online: bool = False):
    """Satu halaman: header sekali, transcript bersih, composer sekali."""
    items = [render_header(state.role, console_width, online=online), Text("")]
    if not state.messages and pending is None:
        greeting = Group(
            Text("Apa yang ingin kamu pelajari hari ini?", style="bold white", justify="center"),
            Text("Tanya materi, contoh Python, atau lihat informasi SIBIMA.", style="dim", justify="center"),
        )
        items.append(_within_workspace(greeting, console_width))
        items.append(Text(""))
    items.append(render_transcript(state, visible_messages, console_width, pending))
    if show_composer:
        line = Text("─" * fit_width(console_width), style="grey35")
        footer = ("Enter kirim   ·   /menu   ·   /riwayat   ·   /baru   ·   /kembali"
                  if fit_width(console_width) >= 68 else
                  "Enter kirim   ·   /menu   ·   /kembali")
        items.append(_within_workspace(line, console_width))
        items.append(_within_workspace(Text(footer, style="dim"), console_width))
    return Group(*items)
