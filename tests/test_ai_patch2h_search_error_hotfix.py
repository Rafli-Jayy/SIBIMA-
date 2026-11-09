"""Patch 2H Hotfix: search access errors remain isolated from normal Gemini chat.

Pure offline tests: never connect to Gemini, PostgreSQL, or paid features.
"""
from types import SimpleNamespace as NS

import pytest

from app.services.ai_service import AIService
from app.services.gemini_client import GeminiClient, GeminiOptions


class APIError(Exception):
    def __init__(self, status, message):
        self.code = status
        super().__init__(message)


class FakeInteractions:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        current = self.results.pop(0)
        if isinstance(current, Exception):
            raise current
        return iter(current)


class FakeSDK:
    def __init__(self, results):
        self.interactions = FakeInteractions(results)


def final_stream(text="Halo"):
    return [
        NS(event_type="step.start", index=0, step=NS(type="model_output")),
        NS(event_type="step.delta", index=0, delta=NS(type="text", text=text)),
        NS(event_type="step.stop", index=0, step=None),
        NS(event_type="interaction.completed", interaction=NS(status="completed")),
    ]


def create_service(results, *, search=True, attempts=3):
    fake = FakeSDK(results)
    adapter = GeminiClient(
        GeminiOptions(api_key="fake-secret", model="gemini-3.5-flash-lite",
                      thinking_level="low", google_search_enabled=search,
                      max_attempts=attempts),
        client=fake, sleep_fn=lambda _: (_ for _ in ()).throw(AssertionError("retry sleep")),
    )
    return AIService("admin", client=adapter), adapter, fake


def test_search_429_pauses_search_for_session_and_allows_next_normal_chat():
    secret = "UNIQUE_KEY_SHOULD_NEVER_APPEAR"
    error = APIError(429, f"429 RESOURCE_EXHAUSTED: details hidden {secret}")
    service, adapter, fake = create_service([error, final_stream("Chat normal")])
    first = list(service.stream("Cari info terbaru", "admin"))
    assert len(fake.interactions.calls) == 1  # no automatic 429 retry
    assert first[-1].kind == "error"
    assert "HTTP 429" in first[-1].payload
    assert "Google Search" in first[-1].payload
    assert "status tier belum dapat dipastikan" in first[-1].payload
    assert "dinonaktifkan" in first[-1].payload
    assert secret not in first[-1].payload
    assert adapter._search_suspended is True
    assert service.history == []

    second = list(service.stream("Jelaskan TypeScript", "admin"))
    assert second[-1].kind == "completed"
    assert second[-1].payload["content"] == "Chat normal"
    assert "tools" in fake.interactions.calls[0]
    assert "tools" not in fake.interactions.calls[1]
    assert len(service.history) == 2


def test_search_free_tier_message_is_specific_only_when_provider_says_so():
    service, adapter, fake = create_service([
        APIError(429, "Grounding with Google Search is not available on Free Tier")
    ])
    output = list(service.stream("Cari", "admin"))[-1].payload
    assert "tier API proyek ini" in output
    assert "status tier belum dapat dipastikan" not in output
    assert adapter._search_suspended is True
    assert len(fake.interactions.calls) == 1


@pytest.mark.parametrize("code,expected", [(403, "HTTP 403"), (400, "HTTP 400")])
def test_denied_search_access_is_suspended(code, expected):
    service, adapter, fake = create_service([
        APIError(code, "grounding access denied")
    ])
    result = list(service.stream("Cari", "admin"))[-1]
    assert result.kind == "error"
    assert expected in result.payload
    assert adapter._search_suspended
    assert len(fake.interactions.calls) == 1


def test_ambiguous_400_does_not_change_session_search_mode():
    service, adapter, fake = create_service([APIError(400, "Invalid parameter unrelated to search")])
    out = list(service.stream("Cari", "admin"))
    assert out[-1].kind == "error"
    assert adapter._search_suspended is False
    assert len(fake.interactions.calls) == 1


def test_search_503_is_not_retried_and_not_considered_tier_failure():
    service, adapter, fake = create_service([APIError(503, "High demand")])
    out = list(service.stream("Cari", "admin"))
    assert out[-1].kind == "error"
    assert "Koneksi atau layanan" in out[-1].payload
    assert not adapter._search_suspended
    assert len(fake.interactions.calls) == 1


def test_no_search_429_keeps_original_error_handling():
    service, adapter, fake = create_service([APIError(429, "Daily quota exceeded")], search=False)
    out = list(service.stream("Halo", "admin"))
    assert "Batas penggunaan Gemini" in out[-1].payload
    assert "Google Search" not in out[-1].payload
    assert len(fake.interactions.calls) == 1
    assert not adapter._search_suspended


def test_normal_retry_kept_for_non_search_temporary_503():
    service, adapter, fake = create_service([APIError(503, "Busy"), final_stream()], search=False)
    # This test intentionally provides a benign sleep_fn, unlike create_service.
    adapter._sleep = lambda _: None
    out = list(service.stream("Halo", "admin"))
    assert out[-1].kind == "completed"
    assert len(fake.interactions.calls) == 2


def test_suspended_search_persists_through_new_chat_but_not_other_sessions():
    service, adapter, fake = create_service([APIError(429, "Quota exceeded"), final_stream()])
    list(service.stream("Cari", "admin"))
    service.reset()
    assert not service.history
    assert adapter._search_suspended
    list(service.stream("Halo", "admin"))
    assert "tools" not in fake.interactions.calls[1]

    other_service, other_adapter, other_fake = create_service([final_stream()], search=True)
    list(other_service.stream("Halo", "admin"))
    assert "tools" in other_fake.interactions.calls[0]
    assert not other_adapter._search_suspended

@pytest.mark.parametrize("status", [429, "429", "RESOURCE_EXHAUSTED"])
def test_search_sse_event_quota_errors_are_handled_without_leaking_data(status):
    private = "PRIVATE_SERVER_MESSAGE_SHOULD_NOT_APPEAR"
    stream = [
        NS(event_type="interaction.created"),
        NS(event_type="error", error=NS(code=status, message=private)),
    ]
    service, adapter, fake = create_service([stream, final_stream()])
    output = list(service.stream("Cari", "admin"))[-1]
    assert output.kind == "error"
    assert "HTTP 429" in output.payload
    assert private not in output.payload
    assert adapter._search_suspended
    assert len(fake.interactions.calls) == 1
    assert service.history == []
    follow_up = list(service.stream("Halo", "admin"))[-1]
    assert follow_up.kind == "completed"
    assert "tools" not in fake.interactions.calls[1]
