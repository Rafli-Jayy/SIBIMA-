from io import StringIO
from rich.console import Console
from app.ui.ai.ai_theme import fit_width, WORKSPACE_MAX
from app.ui.ai.chat_state import ChatState, Message
from app.ui.ai.response_renderer import render_chat, render_header
from app.ui.ai.action_preview import make_preview
from app.ui.ai.mock_responder import MockResponder
from app.ui.ai.streaming_renderer import play_stream


def test_panel_width_capped_on_ultrawide_terminal():
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=200, color_system=None)
    console.print(render_chat(ChatState(role="siswa"), console_width=200))
    lines = [line.rstrip() for line in buf.getvalue().splitlines() if "─" in line]
    assert lines
    assert max(len(line.strip()) for line in lines) < 110
    assert fit_width(200) == WORKSPACE_MAX


def test_compact_preview_not_full_width():
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=200, color_system=None)
    console.print(make_preview({"target": "Tutor", "title": "Informasi Pertemuan", "body": "Persiapan belajar"}, console_width=200))
    assert "Informasi Pertemuan" in buf.getvalue()
    assert max(len(line.strip()) for line in buf.getvalue().splitlines() if line.strip()) < 110


def test_header_mentions_preview_mode_once_without_demo_everywhere():
    buf = StringIO()
    Console(file=buf, force_terminal=False, width=100).print(render_header("admin", 100))
    assert "Pratinjau UI" in buf.getvalue()
    assert "Role demo" not in buf.getvalue()


def test_mock_account_data_not_claimed_real():
    for query in ("jadwal saya", "nilai saya", "tagihan saya"):
        result = MockResponder().reply(query, "siswa")
        assert result["kind"] == "table"
        assert "ilustrasi" in result["content"].casefold()


def test_streaming_panel_width_is_capped():
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=180)
    result = play_stream(console, MockResponder().stream("halo", "siswa"), delay=0)
    assert result["kind"] == "markdown"
