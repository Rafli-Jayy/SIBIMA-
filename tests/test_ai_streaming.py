from io import StringIO
from rich.console import Console
from app.ui.ai.mock_responder import MockResponder
from app.ui.ai.streaming_renderer import play_stream


def test_streaming_without_real_api():
    console = Console(file=StringIO(), force_terminal=False, width=80)
    result = play_stream(console, MockResponder().stream("algoritma", "siswa"), delay=0)
    assert result["kind"] == "markdown"
    assert "algoritma" in result["content"].casefold()
