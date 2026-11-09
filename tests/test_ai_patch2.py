"""Patch 2 tests use fake SSE events: no key, DB or network required."""
from io import StringIO
from types import SimpleNamespace as NS

from rich.console import Console

from app.services.ai_service import AIService
from app.services.gemini_client import GeminiClient, GeminiOptions
from app.ui.ai.chat_screen import ChatScreen


def event(name, **kw):
    return NS(event_type=name, **kw)


def success_events(text="Halo!"):
    return [
        event("step.start", index=0, step=NS(type="thought")),
        event("step.delta", index=0, delta=NS(type="thought_signature", signature="encrypted-signature")),
        event("step.stop", index=0),
        event("step.start", index=1, step=NS(type="model_output")),
        event("step.delta", index=1, delta=NS(type="text", text=text)),
        event("step.stop", index=1),
        event("interaction.completed", interaction=NS(status="completed")),
    ]


class FakeAPI:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return iter(outcome)


class FakeClient:
    def __init__(self, outcomes):
        self.interactions = FakeAPI(outcomes)


def make_service(role, outcomes):
    fake = FakeClient(outcomes)
    adapter = GeminiClient(GeminiOptions(api_key="unused", max_attempts=3), client=fake, sleep_fn=lambda _: None)
    return AIService(role, client=adapter), fake


def test_stateless_history_signatures_and_role():
    svc, fake = make_service("tutor", [success_events("Jawaban pertama."), success_events("Lanjutan.")])
    a = list(svc.stream("Halo", "tutor"))
    b = list(svc.stream("Lanjut", "tutor"))
    assert a[-1].kind == "completed" and b[-1].kind == "completed"
    assert fake.interactions.calls[0]["store"] is False
    assert fake.interactions.calls[0]["model"] == "gemini-3.8-flash"
    assert "Tutor" in fake.interactions.calls[0]["system_instruction"]
    hist = fake.interactions.calls[1]["input"]
    assert len(hist) == 4
    assert hist[1] == {"type": "thought", "signature": "encrypted-signature"}
    assert hist[2]["content"][0]["text"] == "Jawaban pertama."
    assert hist[3]["content"][0]["text"] == "Lanjut"
    svc.reset()
    assert svc.history == []


def test_retry_before_first_delta_only():
    error = ConnectionError("temporary")
    svc, fake = make_service("siswa", [error, success_events()])
    assert list(svc.stream("Halo", "siswa"))[-1].kind == "completed"
    assert len(fake.interactions.calls) == 2


def test_partial_stream_never_retries_or_commits():
    class Broken:
        def __iter__(self):
            yield event("step.start", index=0, step=NS(type="model_output"))
            yield event("step.delta", index=0, delta=NS(type="text", text="Awal"))
            raise ConnectionError("offline")
    svc, fake = make_service("admin", [Broken()])
    outputs = list(svc.stream("Halo", "admin"))
    assert [v.kind for v in outputs] == ["text_chunk", "error"]
    assert len(fake.interactions.calls) == 1
    assert svc.history == []


def test_no_retry_for_auth_errors():
    class BadKey(Exception):
        code = 403
    svc, fake = make_service("admin", [BadKey("secret detail")])
    outputs = list(svc.stream("Hi", "admin"))
    assert outputs[-1].kind == "error"
    assert "secret detail" not in outputs[-1].payload
    assert len(fake.interactions.calls) == 1


def test_screen_reset_and_close_session_without_ui_rewrite(monkeypatch):
    svc, fake = make_service("siswa", [success_events()])
    c = Console(file=StringIO(), force_terminal=False, width=120)
    screen = ChatScreen(role="siswa", console=c, responder=svc, stream_delay=0, view_mode="scroll", online=True)
    messages = iter(["Halo", "/baru", "/kembali"])
    monkeypatch.setattr(screen, "_question", lambda: next(messages))
    screen.run()
    assert svc.history == []
    assert screen.state.messages == []
    assert "Gemini · Online" in c.file.getvalue()


def test_mismatch_role_rejected():
    import pytest
    svc, _ = make_service("admin", [])
    with pytest.raises(ValueError):
        list(svc.stream("Hai", "siswa"))


def test_partial_reply_visible_after_stream_error():
    from app.ui.ai.mock_responder import MockEvent
    from app.ui.ai.streaming_renderer import play_stream
    c = Console(file=StringIO(), width=100, force_terminal=False)
    outcome = play_stream(c, iter([
        MockEvent("text_chunk", "Sebagian jawaban"),
        MockEvent("error", "Koneksi terputus"),
    ]), delay=0)
    assert outcome["kind"] == "error"
    assert "Sebagian jawaban" in outcome["content"]
    assert "Koneksi terputus" in outcome["content"]
