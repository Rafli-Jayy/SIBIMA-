from io import StringIO
from rich.console import Console
from app.ui.ai.ai_theme import fit_width, workspace_left, prompt_prefix
from app.ui.ai.chat_state import ChatState, Message
from app.ui.ai.response_renderer import render_chat, render_header, render_message
from app.ui.ai.streaming_renderer import play_stream
from app.ui.ai.mock_responder import MockResponder
from app.ui.ai.chat_screen import ChatScreen


def capture(renderable, width=140, legacy_windows=None):
    stream = StringIO()
    Console(file=stream, width=width, color_system=None, force_terminal=False, legacy_windows=legacy_windows).print(renderable)
    return stream.getvalue()


def test_chatgpt_alignment_user_right_ai_left():
    state = ChatState()
    state.add(Message("user", "Apa itu algoritma?"))
    state.add(Message("assistant", "Algoritma merupakan urutan langkah."))
    # Rich may substitute ROUNDED (╭) with SQUARE (┌) on Windows.
    # Verify both rendering modes without changing the actual chat UI.
    for legacy_windows in (False, True):
        content = capture(render_chat(state, console_width=140), legacy_windows=legacy_windows)
        user_line = next(line for line in content.splitlines() if "Apa itu algoritma?" in line)
        ai_line = next(line for line in content.splitlines() if "Algoritma merupakan" in line)
        assert user_line.index("Apa itu") > ai_line.index("Algoritma") + 20
        assert content.count("╭") + content.count("┌") == 1, "Hanya pesan pengguna yang punya bubble"
        assert "✦  SIBIMA AI" in content


def test_prompt_aligned_with_workspace_left():
    for width in [58, 80, 140, 200]:
        assert len(prompt_prefix(width)) - 1 == workspace_left(width)
        assert fit_width(width) + 2 * workspace_left(width) <= width


def test_prompt_questionary_uses_same_gutter(monkeypatch):
    import types
    import sys
    called = {}
    class Stub:
        def ask(self):
            return "tes"
    def fake_text(message, **kwargs):
        called["message"] = message
        called.update(kwargs)
        return Stub()
    stub_questionary = types.ModuleType("questionary")
    stub_questionary.text = fake_text
    stub_questionary.Style = lambda rules: rules
    monkeypatch.setitem(sys.modules, "questionary", stub_questionary)
    console = Console(file=StringIO(), width=140)
    assert ChatScreen(console=console)._question() == "tes"
    assert called["qmark"] == prompt_prefix(140)
    assert called["message"] == "Tulis pesan"


def test_narrow_terminal_header_and_footer_short():
    for width in [48, 62, 80, 140]:
        state = ChatState(role="tutor")
        state.add(Message("user", "Ceritakan cara kerja fungsi.", kind="markdown"))
        state.add(Message("assistant", "Penjelasan fungsi.\n\n- Satu\n- Dua"))
        output = capture(render_chat(state, console_width=width), width=width)
        assert "SIBIMA AI" in output
        assert "Penjelasan fungsi" in output
        assert "Tulis pesan" not in output  # prompt asli datang dari Questionary, bukan kotak palsu
        assert "Enter kirim" in output
        assert max(map(len, output.splitlines())) <= width


def test_streaming_uses_same_conversation_layout():
    state = ChatState()
    state.add(Message("user", "algoritma"))
    pending = capture(render_chat(state, console_width=140, pending="Langkah pertama...", show_composer=False))
    assert "Langkah pertama" in pending and "algoritma" in pending
    assert pending.index("algoritma") < pending.index("Langkah pertama")
    result = play_stream(Console(file=StringIO(), width=100, force_terminal=False),
                         MockResponder().stream("algoritma", "siswa"), delay=0, state=state)
    assert result["kind"] == "markdown"
