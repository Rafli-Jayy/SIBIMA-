"""Patch 3 terminal-event compatibility regressions; no live API / PostgreSQL."""
from types import SimpleNamespace as NS

from app.services.ai_db_chat import DatabaseFunctionChat


def event(kind, **kwargs):
    return NS(event_type=kind, **kwargs)


class FakeClient:
    def __init__(self, *streams):
        self.streams = list(streams)
        self.calls = []
        self.interactions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.streams.pop(0))


class FakeGemini:
    def __init__(self, client):
        self._client = client
        self.options = NS(model="gemini-3.5-flash-lite", thinking_level="low")

    def _code(self, exc):
        return None


class FakeController:
    def __init__(self):
        self.called = []

    def declarations(self):
        return [{"type": "function", "name": "get_admin_overview", "parameters": {"type": "object", "properties": {}}}]

    def execute(self, name, args):
        self.called.append((name, args))
        return {"jumlah_siswa": 3}


def tool_first_terminal(kind="interaction.requires_action", status="requires_action"):
    thought = NS(type="thought", signature="sig")
    fc = NS(type="function_call", name="get_admin_overview", id="fc-3", arguments={})
    return [
        event("step.start", index=0, step=thought),
        event("step.stop", index=0, step=thought),
        event("step.start", index=1, step=fc),
        event("step.stop", index=1, step=fc),
        event(kind, interaction=NS(status=status)),
    ]


def answer_terminal(status="completed"):
    content = [{"type": "text", "text": "Ada 3 siswa."}]
    return [
        event("step.start", index=0, step=NS(type="model_output")),
        event("step.delta", index=0, delta=NS(type="text", text="Ada 3 siswa.")),
        event("step.stop", index=0, step=NS(type="model_output", content=content)),
        event("interaction.completed", interaction=NS(status=status)),
    ]


def test_documented_requires_action_executes_one_read():
    ctrl = FakeController()
    client = FakeClient(tool_first_terminal(), answer_terminal())
    output = list(DatabaseFunctionChat(FakeGemini(client), ctrl).stream([], "Jumlah siswa?", "system"))
    assert ctrl.called == [("get_admin_overview", {})]
    assert [x.kind for x in output] == ["db_read_started", "text_chunk", "completed"]
    assert all(c["store"] is False for c in client.calls)


def test_compatible_terminal_snapshot_without_extra_db_access():
    ctrl = FakeController()
    # Anomalous terminal event: completed event with requires_action snapshot.
    client = FakeClient(tool_first_terminal("interaction.completed", "requires_action"), answer_terminal())
    output = list(DatabaseFunctionChat(FakeGemini(client), ctrl).stream([], "Jumlah siswa?", "system"))
    assert ctrl.called == [("get_admin_overview", {})]
    assert output[-1].kind == "completed"


def test_mismatched_status_exposes_only_safe_reason():
    ctrl = FakeController()
    client = FakeClient(answer_terminal(status="in_progress"))
    out = list(DatabaseFunctionChat(FakeGemini(client), ctrl).stream([], "Info saya", "system"))
    assert out[-1].kind == "error"
    assert "status-interaksi=in_progress" in out[-1].payload
    assert "alasan=status-terminal-tidak-dikenal" in out[-1].payload
    assert ctrl.called == []


def test_requires_action_without_function_call_does_not_execute_db():
    ctrl = FakeController()
    client = FakeClient(answer_terminal(status="requires_action"))
    out = list(DatabaseFunctionChat(FakeGemini(client), ctrl).stream([], "Info saya", "system"))
    assert out[-1].kind == "error"
    assert "alasan=requires-action-tanpa-function-call" in out[-1].payload
    assert ctrl.called == []


def test_sdk_enum_like_status_supported():
    class Status:
        value = "completed"
    ctrl = FakeController()
    client = FakeClient(answer_terminal(status=Status()))
    out = list(DatabaseFunctionChat(FakeGemini(client), ctrl).stream([], "Halo", "system"))
    assert out[-1].kind == "completed"
    assert ctrl.called == []
