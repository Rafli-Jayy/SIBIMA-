"""Hotfix: animasi spinner aktif saat menunggu token pertama Gemini."""
from io import StringIO
from time import sleep

from rich.console import Console

from app.ui.ai.chat_state import ChatState, Message
from app.ui.ai.mock_responder import MockEvent
from app.ui.ai.streaming_renderer import play_stream


def test_spinner_moves_while_waiting_before_first_chunk():
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=110)

    def delayed_events():
        sleep(0.38)  # Simulasi API memproses prompt sebelum mengirim teks.
        yield MockEvent("text_chunk", "Halo dari Gemini")
        yield MockEvent("completed", {"kind": "markdown", "content": "Halo dari Gemini"})

    result = play_stream(console, delayed_events(), delay=0)

    assert result == {"kind": "markdown", "content": "Halo dari Gemini"}
    assert output.getvalue().count("Sedang berpikir") >= 2
    assert "Halo dari Gemini" in output.getvalue()


def test_spinner_handles_early_error_without_stream_content():
    console = Console(file=StringIO(), force_terminal=False, width=96)
    result = play_stream(console, iter([MockEvent("error", "Kuota API habis")]), delay=0)
    assert result == {"kind": "error", "content": "Kuota API habis"}


def test_spinner_handles_empty_event_stream():
    console = Console(file=StringIO(), force_terminal=False, width=96)
    result = play_stream(console, iter(()), delay=0)
    assert result["kind"] == "error"


def test_spinner_preserves_clean_mode_and_result():
    console = Console(file=StringIO(), force_terminal=False, width=96)
    state = ChatState(role="admin")
    state.add(Message("user", "Halo"))
    result = play_stream(console, iter([
        MockEvent("text_chunk", "Hai, Admin!"),
        MockEvent("completed", {"kind": "markdown", "content": "Hai, Admin!"}),
    ]), delay=0, state=state)
    assert result["content"] == "Hai, Admin!"
    assert state.messages[-1].content == "Halo"  # renderer tidak mengubah state.
