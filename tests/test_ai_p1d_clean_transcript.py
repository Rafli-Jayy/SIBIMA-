"""Patch 1D regression: chat history must contain only user/assistant messages."""
from contextlib import contextmanager
from io import StringIO
from rich.console import Console
from app.ui.ai.chat_state import ChatState, Message
from app.ui.ai.chat_screen import ChatScreen
from app.ui.ai.response_renderer import render_chat, render_transcript


def capture(renderable, width=140):
    s = StringIO()
    Console(file=s, width=width, color_system=None, force_terminal=False).print(renderable)
    return s.getvalue()


def test_transcript_has_only_messages_no_controls_or_role():
    state = ChatState(role="admin")
    state.add(Message("user", "Mantap bet nih AI"))
    state.add(Message("assistant", "Terima kasih!"))
    state.add(Message("user", "jelaskan algoritma"))
    state.add(Message("assistant", "Algoritma adalah langkah terurut."))
    content = capture(render_transcript(state, console_width=140))
    assert "Mantap bet nih AI" in content
    assert "Terima kasih!" in content
    assert "jelaskan algoritma" in content
    assert "Algoritma adalah langkah terurut." in content
    for forbidden in ["Enter kirim", "/menu", "/riwayat", "Tulis pesan", "Pratinjau UI", "Admin"]:
        assert forbidden not in content
    assert content.count("✦  SIBIMA AI") == 2  # one sender label per AI reply, not header


def test_active_page_has_one_header_and_one_footer():
    state = ChatState(role="admin")
    for i in range(3):
        state.add(Message("user", f"Pesan {i}"))
        state.add(Message("assistant", f"Balasan {i}"))
    content = capture(render_chat(state, visible_messages=6, console_width=140))
    assert content.count("◈  SIBIMA AI") == 1
    assert content.count("Enter kirim") == 1
    assert content.count("/menu") == 1
    assert "Tulis pesan" not in content  # questionary only renders active prompt


def test_stream_frame_never_renders_composer():
    state = ChatState()
    state.add(Message("user", "algoritma"))
    page = capture(render_chat(state, console_width=140, pending="Menyiapkan jawaban…", show_composer=False))
    assert "algoritma" in page and "Menyiapkan jawaban" in page
    assert "Enter kirim" not in page
    assert "Tulis pesan" not in page


def test_terminal_screen_wraps_entire_chat_session(monkeypatch):
    console = Console(file=StringIO(), width=100, force_terminal=True)
    calls = []

    @contextmanager
    def fake_screen(*, hide_cursor=True):
        calls.append(("enter", hide_cursor))
        yield
        calls.append(("exit",))

    monkeypatch.setattr(console, "screen", fake_screen)
    screen = ChatScreen(console=console, stream_delay=0)
    monkeypatch.setattr(screen, "_question", lambda: "/kembali")
    screen.run()
    assert calls == [("enter", False), ("exit",)]


def test_noninteractive_console_does_not_enter_alternate_screen(monkeypatch):
    console = Console(file=StringIO(), width=100, force_terminal=False)
    screen = ChatScreen(console=console, stream_delay=0)
    monkeypatch.setattr(screen, "_question", lambda: "/kembali")
    monkeypatch.setattr(console, "screen", lambda **kw: (_ for _ in ()).throw(AssertionError("screen should not run")))
    screen.run()
