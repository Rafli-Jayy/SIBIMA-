"""Dynamic Chat streaming: menggambar pesan AI pada kolom chat yang sama."""
from typing import Iterable, Dict, Any, Optional
from time import sleep, monotonic
from rich.console import Console, Group
from rich.align import Align
from rich.spinner import Spinner
from rich.text import Text
from rich.live import Live
from .mock_responder import MockEvent
from .response_renderer import clean_text, render_chat, render_message, _within_workspace
from .ai_theme import fit_width
from .chat_state import ChatState, Message


def play_stream(console: Console, events: Iterable[MockEvent], delay: float = 0.035,
                state: Optional[ChatState] = None) -> Dict[str, Any]:
    """Render event stream tanpa menjalankan prompt bersamaan dengan Rich Live."""
    buffer = ""
    result = None
    last_refresh = 0.0

    def thinking_frame(status: str = "Sedang berpikir…"):
        # Rich merender Spinner pada refresh thread selama API menunggu token pertama.
        # Tetap berada di workspace AI yang sama tanpa mencetak baris baru.
        indicator = Group(
            Text("✦  SIBIMA AI", style="bold cyan"),
            Text(""),
            Spinner("dots", text=Text(" " + status, style="dim"), style="cyan"),
        )
        indicator = _within_workspace(
            Align.left(indicator, width=fit_width(console.width)), console.width
        )
        if state is not None:
            return Group(
                render_chat(state, console_width=console.width, show_composer=False),
                Text(""), indicator
            )
        return indicator

    def frame(text: str):
        # Hanya tail respons untuk membatasi tinggi layar; riwayat ada di state.
        preview = clean_text(text[-1000:])
        if len(text) > 1000:
            preview = "…\n" + preview
        if state is not None:
            return render_chat(state, console_width=console.width, pending=preview, show_composer=False)
        return render_message(Message("assistant", preview or "Menyiapkan jawaban…"),
                              console_width=console.width, streaming=True)

    # One Rich Live session so thinking/search spinner moves while SSE is blocked.
    # Grounded content is never printed here; a browser companion shows the
    # complete answer with the required Google Search Suggestions.
    with Live(thinking_frame(), console=console, auto_refresh=console.is_terminal,
              refresh_per_second=10, transient=True, vertical_overflow="ellipsis") as live:
        for event in events:
            if event.kind == "text_reset":
                # Only after a full safe fallback is ready; never retain truncated text.
                buffer = ""
                live.update(thinking_frame("Menyiapkan ulang jawaban…"), refresh=True)
            elif event.kind == "db_read_started":
                live.update(thinking_frame("Mengambil informasi SIBIMA…"), refresh=True)
            elif event.kind == "search_started":
                live.update(thinking_frame("Mencari melalui Google…"), refresh=True)
            elif event.kind == "search_finished":
                live.update(thinking_frame("Menyiapkan hasil pencarian…"), refresh=True)
            elif event.kind == "text_chunk":
                buffer = (buffer + str(event.payload))[:12000]
                now = monotonic()
                if now - last_refresh >= 0.10:
                    live.update(frame(buffer + " ▍"), refresh=True)
                    last_refresh = now
                if delay > 0:
                    sleep(delay)
            elif event.kind == "completed":
                result = event.payload
            elif event.kind == "error":
                result = {"kind": "error", "content": (buffer + "\n\n⚠ " if buffer else "") + clean_text(event.payload)}
        if buffer:
            live.update(frame(buffer), refresh=True)
    return result if result is not None else {"kind": "error", "content": "Jawaban terhenti sebelum selesai."}
