"""Patch 2I offline regression tests: no API key, network, or PostgreSQL."""
from types import SimpleNamespace as NS

from app.services.ai_service import AIService, BASE_INSTRUCTION
from app.services.gemini_client import GeminiClient, GeminiOptions


def ev(kind, **data):
    return NS(event_type=kind, **data)


def start(index, kind, **extra):
    return ev("step.start", index=index, step=NS(type=kind, **extra))


def delta(index, kind, **extra):
    return ev("step.delta", index=index, delta=NS(type=kind, **extra))


class FakeAPI:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.outcomes.pop(0))


class FakeClient:
    def __init__(self, outcomes):
        self.interactions = FakeAPI(outcomes)


def make(outcomes):
    fake = FakeClient(outcomes)
    adapter = GeminiClient(GeminiOptions(api_key="unused", max_attempts=1), client=fake)
    return adapter, fake


def test_missing_completed_with_open_step_has_safe_event_trace():
    adapter, fake = make([[
        ev("interaction.created", interaction=NS(id="SECRET_IDENTIFIER")),
        start(0, "model_output"),
        delta(0, "text", text="TEKS_PRIBADI"),
    ]])
    result = list(adapter.stream([], "PROMPT_PRIVATE", "SECRET_INSTRUCTIONS"))
    assert [x.kind for x in result] == ["text_chunk", "error"]
    error = result[-1].payload
    assert "alasan=event-completed-tidak-ada" in error
    assert "step-terbuka=1" in error
    assert "jumlah-event=3" in error
    assert "alur=interaction.created>start:model_output>delta:text" in error
    for secret in ("PROMPT_PRIVATE", "TEKS_PRIBADI", "SECRET_IDENTIFIER", "SECRET_INSTRUCTIONS"):
        assert secret not in error
    assert len(fake.interactions.calls) == 1


def test_missing_completed_after_stop_still_fails_not_false_success():
    adapter, _ = make([[
        start(0, "model_output"), delta(0, "text", text="jawaban"), ev("step.stop", index=0)
    ]])
    result = list(adapter.stream([], "x", "y"))
    assert result[-1].kind == "error"
    assert "alasan=event-completed-tidak-ada" in result[-1].payload
    assert "step-terbuka=0" in result[-1].payload


def test_completed_without_step_stop_is_rejected():
    adapter, _ = make([[
        start(0, "model_output"), delta(0, "text", text="isi"),
        ev("interaction.completed", interaction=NS(status="completed")),
    ]])
    result = list(adapter.stream([], "x", "y"))
    assert result[-1].kind == "error"
    assert "alasan=step-stop-tidak-ada" in result[-1].payload


def test_thought_summary_and_text_in_thought_step_not_user_visible():
    adapter, _ = make([[
        start(0, "thought", signature="SIG1"),
        delta(0, "thought_summary", content=NS(type="text", text="PRIVATE_ANALYSIS")),
        delta(0, "text", text="PRIVATE_THOUGHT"),
        ev("step.stop", index=0),
        start(1, "model_output"), delta(1, "text", text="Jawaban akhir."),
        ev("step.stop", index=1), ev("interaction.completed"),
    ]])
    result = list(adapter.stream([], "Halo", "SIBIMA"))
    assert [x.kind for x in result] == ["text_chunk", "completed"]
    assert "PRIVATE_ANALYSIS" not in str(result)
    assert "PRIVATE_THOUGHT" not in str(result)
    assert result[-1].payload["data"]["steps"][1] == {"type": "thought", "signature": "SIG1"}


def test_detects_split_thinking_intro_before_emitting_chunks():
    adapter, fake = make([[
        start(0, "model_output"),
        delta(0, "text", text="Here is a "),
        delta(0, "text", text="thinking pro"),
        delta(0, "text", text="cess that leads to private steps: SECRET"),
        ev("step.stop", index=0), ev("interaction.completed"),
    ]])
    svc = AIService("admin", client=adapter)
    result = list(svc.stream("Kode TypeScript", "admin"))
    assert [e.kind for e in result] == ["error"]
    assert "alasan=output-analisis-terdeteksi" in result[-1].payload
    assert "SECRET" not in result[-1].payload
    assert svc.history == []
    assert len(fake.interactions.calls) == 1


def test_normal_english_opening_here_is_does_not_get_blocked():
    adapter, _ = make([[
        start(0, "model_output"),
        delta(0, "text", text="Here is "),
        delta(0, "text", text="a TypeScript example:"),
        ev("step.stop", index=0), ev("interaction.completed"),
    ]])
    result = list(adapter.stream([], "Kode", "SIBIMA"))
    assert [x.kind for x in result] == ["text_chunk", "completed"]
    assert result[-1].payload["content"] == "Here is a TypeScript example:"


def test_short_valid_answer_can_be_held_until_completion():
    adapter, _ = make([[
        start(0, "model_output"), delta(0, "text", text="Here"),
        ev("step.stop", index=0), ev("interaction.completed"),
    ]])
    result = list(adapter.stream([], "Kode", "SIBIMA"))
    assert [x.kind for x in result] == ["text_chunk", "completed"]
    assert result[-1].payload["content"] == "Here"


def test_success_diagnostic_absent_and_history_commits():
    adapter, _ = make([[
        start(0, "thought"), delta(0, "thought_signature", signature="SIG"),
        ev("step.stop", index=0),
        start(1, "model_output"), delta(1, "text", text="OK"), ev("step.stop", index=1),
        ev("interaction.completed", interaction=NS(status="completed")),
    ]])
    svc = AIService("tutor", client=adapter)
    result = list(svc.stream("Halo", "tutor"))
    assert result[-1].kind == "completed"
    assert len(svc.history) == 3
    assert "Diagnostik" not in str(result[-1].payload)


def test_system_prompt_requests_only_final_answer():
    assert "Jangan menampilkan proses berpikir internal" in BASE_INSTRUCTION
