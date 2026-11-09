"""Patch 1E: terminal scrollback, no duplicated composer, 18 UI showcase samples."""
from io import StringIO
import pytest
from rich.console import Console
from app.ui.ai.chat_screen import ChatScreen
from app.ui.ai.gallery import EXAMPLES, render_example
from app.ui.ai.chat_state import ChatState, Message


def capture(element, width=100):
    f = StringIO()
    Console(file=f, width=width, force_terminal=False, color_system=None).print(element)
    return f.getvalue()


def test_gallery_has_all_18_unique_ui_states():
    assert len(EXAMPLES) == 18
    assert len({example.key for example in EXAMPLES}) == 18
    for example in EXAMPLES:
        content = capture(render_example(example.key, width=100))
        assert content.strip(), example.key


def test_gallery_contains_true_code_table_and_action_preview():
    assert "hitung_total" in capture(render_example("code"))
    assert "Matematika" in capture(render_example("schedule"))
    assert "PRATINJAU" in capture(render_example("action"))
    assert "Akses ditolak" in capture(render_example("denied"))


def test_narrow_gallery_is_readable():
    for width in [62, 88, 140]:
        for key in ("single", "code", "schedule", "action", "narrow", "error"):
            text = capture(render_example(key, width=width), width=width)
            assert max(map(len, text.splitlines())) <= width, (key, width)


def test_scroll_mode_appends_messages_once_and_does_not_clear(monkeypatch):
    c = Console(file=StringIO(), width=120, force_terminal=False, color_system=None)
    screen = ChatScreen(role="siswa", console=c, stream_delay=0, view_mode="scroll")
    asked = iter(["halo", "jelaskan algoritma", "/kembali"])
    monkeypatch.setattr(screen, "_question", lambda: next(asked))
    clear_called = []
    monkeypatch.setattr(c, "clear", lambda: clear_called.append(True))
    monkeypatch.setattr(c, "screen", lambda **kw: (_ for _ in ()).throw(AssertionError("no alt screen")))
    screen.run()
    text = c.file.getvalue()
    assert not clear_called
    assert text.count("◈  SIBIMA AI") == 1
    assert text.count("› Tulis pesan") == 0
    assert "jelaskan algoritma" in text
    assert "algoritma adalah" in text.lower()
    assert text.count("halo") == 1  # user bubble only, AI does not repeat raw user text


def test_scroll_mode_leaves_all_long_messages_readable(monkeypatch):
    c = Console(file=StringIO(), width=110, force_terminal=False, color_system=None)
    screen = ChatScreen(role="siswa", console=c, stream_delay=0, view_mode="scroll")
    msg = "B" * 700
    screen.responder.reply = lambda *_: {"kind": "markdown", "content": msg}
    # MockResponder.stream internally calls .reply, and data is emitted in chunks.
    asked = iter(["haloo", "/kembali"])
    monkeypatch.setattr(screen, "_question", lambda: next(asked))
    screen.run()
    assert "BBBBBBBB" in c.file.getvalue()


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        ChatScreen(view_mode="invalid")
