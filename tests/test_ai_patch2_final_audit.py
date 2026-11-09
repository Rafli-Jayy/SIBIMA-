"""Additional offline release-gate tests for SIBIMA-AI Patch 2.

No database, credentials, network calls or changes to application code.
"""

from io import StringIO
from types import SimpleNamespace as NS
from pathlib import Path
import ast

import pytest
from rich.console import Console

from app.services.ai_service import AIService
from app.services.gemini_client import GeminiClient, GeminiOptions
from app.ui.ai.chat_screen import ChatScreen
from app.ui.ai.mock_responder import MockEvent
from app.ui.ai.streaming_renderer import play_stream


def e(kind, **kwargs):
    return NS(event_type=kind, **kwargs)


def chunks_result(texts=("Halo",)):
    return [
        e("step.start", index=0, step=NS(type="model_output")),
        *[e("step.delta", index=0, delta=NS(type="text", text=t)) for t in texts],
        e("step.stop", index=0),
        e("interaction.completed"),
    ]


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class API:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return iter(outcome)


class Client:
    def __init__(self, outcomes):
        self.interactions = API(outcomes)


def adapter(outcomes, max_attempts=3):
    client = Client(outcomes)
    pauses = []
    ai = GeminiClient(GeminiOptions(
        api_key="dummy", model="gemini-3.5-flash-lite",
        thinking_level="low", max_attempts=max_attempts,
    ), client=client, sleep_fn=pauses.append)
    return ai, client.interactions, pauses


def test_daily_quota_429_no_retry_and_no_secret_error():
    ai, api, pauses = adapter([Failure(429, "Rate limit exceeded: limit 20 requests per day on Free Tier")])
    result = list(ai.stream([], "Halo", "SIBIMA"))
    assert [r.kind for r in result] == ["error"]
    assert len(api.calls) == 1 and pauses == []
    assert "20 requests" not in result[0].payload


def test_temporary_429_retries_once():
    ai, api, pauses = adapter([Failure(429, "Rate limit exceeded temporarily"), chunks_result()])
    result = list(ai.stream([], "Halo", "SIBIMA"))
    assert result[-1].kind == "completed"
    assert len(api.calls) == 2 and pauses == [1]


def test_503_high_demand_can_retry_but_has_bounded_budget():
    ai, api, pauses = adapter([Failure(503, "high demand"), Failure(503, "high demand"), chunks_result()])
    result = list(ai.stream([], "Halo", "SIBIMA"))
    assert result[-1].kind == "completed"
    assert len(api.calls) == 3 and pauses == [1, 2]


def test_repeated_503_terminates_without_infinite_loading():
    ai, api, pauses = adapter([Failure(503, "high demand") for _ in range(3)])
    result = list(ai.stream([], "Halo", "SIBIMA"))
    assert result[-1].kind == "error"
    assert len(api.calls) == 3 and pauses == [1, 2]


@pytest.mark.parametrize('code', [401, 403, 404])
def test_model_or_auth_errors_do_not_retry(code):
    ai, api, pauses = adapter([Failure(code, "a sensitive backend message")])
    result = list(ai.stream([], "Halo", "SIBIMA"))
    assert result[-1].kind == "error"
    assert "sensitive backend message" not in result[-1].payload
    assert len(api.calls) == 1 and pauses == []


def test_model_used_is_configured_not_hardcoded():
    ai, api, _ = adapter([chunks_result()])
    list(ai.stream([], "Halo", "Admin"))
    assert api.calls[0]['model'] == 'gemini-3.5-flash-lite'
    assert api.calls[0]['generation_config']['thinking_level'] == 'low'
    assert api.calls[0]['store'] is False
    assert api.calls[0]['stream'] is True


def test_long_response_keeps_full_completed_text():
    text = 'ab ' * 10000
    ai, _, _ = adapter([chunks_result([text[:10000], text[10000:]])])
    result = list(ai.stream([], "Jelaskan", "SIBIMA"))
    assert result[-1].kind == 'completed'
    assert result[-1].payload['content'] == text


def test_reset_removes_context_before_next_request():
    ai, api, _ = adapter([chunks_result(["MANGGA"]), chunks_result(["Lupa"] )])
    service = AIService('admin', client=ai)
    assert list(service.stream('ingat MANGGA', 'admin'))[-1].kind == 'completed'
    assert service.history
    service.reset()
    assert service.history == []
    assert list(service.stream('apa tadi', 'admin'))[-1].kind == 'completed'
    request = api.calls[-1]['input']
    assert len(request) == 1
    assert 'MANGGA' not in str(request)


def test_online_chat_never_runs_demo_action(monkeypatch):
    class Responder:
        def stream(self, _query, _role):
            yield MockEvent('completed', {
                'kind': 'action', 'content': 'aksi percobaan',
                'data': {'action': 'do_something'},
            })
        def close(self): pass
    console = Console(file=StringIO(), width=108, force_terminal=False)
    screen = ChatScreen(role='admin', console=console, responder=Responder(),
                        view_mode='scroll', online=True)
    prompts = iter(['Jalankan aksi', '/kembali'])
    monkeypatch.setattr(screen, '_question', lambda: next(prompts))
    monkeypatch.setattr('app.ui.ai.chat_screen.simulate_action',
                        lambda *_: pytest.fail('Online action was executed'))
    screen.run()
    assert len(screen.state.messages) == 0  # logout clears state


def test_stream_spinner_error_no_extra_message_printed():
    console = Console(file=StringIO(), width=120, force_terminal=False)
    result = play_stream(console, [MockEvent('error', 'Kuota harian habis')], delay=0)
    assert result['kind'] == 'error'
    assert result['content'] == 'Kuota harian habis'


@pytest.mark.parametrize('file, role', [
    ('app/ui/menu_admin.py', 'admin'),
    ('app/ui/menu_tutor.py', 'tutor'),
    ('app/ui/menu_siswa.py', 'siswa'),
])
def test_all_role_menus_have_ai_entry(file, role):
    tree = ast.parse(Path(file).read_text('utf-8'))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and
             isinstance(n.func, ast.Name) and n.func.id == 'buka_ai']
    assert any(c.args and isinstance(c.args[0], ast.Constant) and
               c.args[0].value == role for c in calls)
