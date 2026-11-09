"""Offline tests for Gemini diagnostics. No API key, network or PostgreSQL."""
from types import SimpleNamespace as NS

from app.services.gemini_client import GeminiClient, GeminiOptions


def event(kind, **data):
    return NS(event_type=kind, **data)


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.interactions = self

    def create(self, **kwargs):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return iter(self.result)


def run(result, *, attempts=1):
    client = FakeClient(result)
    gemini = GeminiClient(
        GeminiOptions(api_key="unused", max_attempts=attempts),
        client=client,
        sleep_fn=lambda _: None,
    )
    return list(gemini.stream([], "PROMPT_RAHASIA", "Instruksi internal")), client


def test_partial_stream_network_failure_has_safe_metadata():
    class ServerOverloaded(Exception):
        code = 503

    def stream():
        yield event("step.start", index=0, step=NS(type="model_output"))
        yield event("step.delta", index=0, delta=NS(type="text", text="TEKS_RAHASIA"))
        raise ServerOverloaded("internal: API_KEY_RAHASIA / private request")

    results, client = run(stream())
    assert [e.kind for e in results] == ["text_chunk", "error"]
    error = results[-1].payload
    assert "HTTP 503" in error
    assert "jenis=ServerOverloaded" in error
    assert "fase=menerima-teks" in error
    assert "event=step.delta" in error
    assert "teks-terkirim=12karakter" in error
    assert "percobaan=1/1" in error
    assert "Respons sebagian" in error
    for secret in ("PROMPT_RAHASIA", "API_KEY_RAHASIA", "TEKS_RAHASIA", "private request"):
        assert secret not in error
    assert client.calls == 1


def test_http_auth_error_show_code_without_private_message():
    class Rejected(Exception):
        status_code = 403

    results, _ = run(Rejected("secret token exposed by SDK"))
    error = results[-1].payload
    assert "HTTP 403" in error
    assert "jenis=Rejected" in error
    assert "fase=membuka-stream" in error
    assert "secret token" not in error


def test_stream_error_event_diagnostic_uses_code_not_server_message():
    results, _ = run([
        event("interaction.created"),
        event("error", error=NS(code="gateway_timeout", message="SECRET_INTERNAL_MESSAGE")),
    ])
    error = results[-1].payload
    assert "event=error" in error
    assert "kode-event=gateway_timeout" in error
    assert "alasan=event-gagal" in error
    assert "SECRET_INTERNAL_MESSAGE" not in error


def test_missing_completed_after_partial_text_has_explicit_reason():
    results, _ = run([
        event("step.start", index=0, step=NS(type="model_output")),
        event("step.delta", index=0, delta=NS(type="text", text="Satu")),
        event("step.stop", index=0),
    ])
    assert results[-1].kind == "error"
    assert "alasan=event-completed-tidak-ada" in results[-1].payload
    assert "fase=memvalidasi-hasil" in results[-1].payload


def test_unexpected_delta_does_not_leak_server_payload():
    results, _ = run([
        event("step.start", index=0, step=NS(type="model_output")),
        event("step.delta", index=0, delta=NS(type="UNEXPECTED_KIND", text="secret body")),
    ])
    err = results[-1].payload
    assert "alasan=jenis-delta-tidak-didukung" in err
    assert "secret body" not in err


def test_successful_stream_still_completed_without_diagnostic():
    results, _ = run([
        event("step.start", index=0, step=NS(type="model_output")),
        event("step.delta", index=0, delta=NS(type="text", text="Halo")),
        event("step.stop", index=0),
        event("interaction.completed", interaction=NS(status="completed")),
    ])
    assert [x.kind for x in results] == ["text_chunk", "completed"]
    assert "Diagnostik" not in str(results[-1].payload)
