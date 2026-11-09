"""All tests offline, no network, no connection to PostgreSQL."""
from app.services.ai_dynamic_plan import NAME as DYNAMIC_NAME
from types import SimpleNamespace as NS
from contextlib import contextmanager
import sys
import types

import pytest
from app import session
from app.services.ai_tool_controller import AIToolController, ROLE_TO_TOOLS, EXTRA_ROLE_TO_TOOLS, PATCH5C_ROLE_TO_TOOLS
from app.services.ai_dynamic_plan import ROLE_DYNAMIC_NAMES
from app.services.ai_history_plan import HISTORY_TOOLS
from app.services.ai_db_chat import DatabaseFunctionChat
from app.services.ai_service import AIService
from app.services.gemini_client import GeminiClient, GeminiOptions
from app.repositories.ai_read_repo import AIReadRepository, QUERIES


@pytest.fixture(autouse=True)
def clear_session():
    old = session.get_user()
    session.logout()
    yield
    session.set_user(old)


class FakeRepo:
    def __init__(self):
        self.calls = []

    def execute(self, user_id, role, name, args):
        self.calls.append((user_id, role, name, args))
        return {"data": [{"status": "lunas"}], "jumlah_ditampilkan": 1}


def login(role="siswa", user_id=71):
    session.set_user({"id": user_id, "role": role, "status": "aktif"})


def event(t, **kwargs):
    return NS(event_type=t, **kwargs)


def tool_stream(name="get_my_invoices", arguments=None):
    call = NS(type="function_call", id="fc-123", name=name, arguments=arguments or {})
    thought = NS(type="thought", signature="opaque-thinking")
    return [event("step.start", index=0, step=thought),
            event("step.stop", index=0, step=thought),
            event("step.start", index=1, step=NS(type="function_call", id="fc-123", name=name)),
            event("step.delta", index=1, delta=NS(type="arguments", partial_arguments="{}")),
            event("step.stop", index=1),
            event("interaction.requires_action", interaction=NS(status="requires_action"))]


def answer_stream():
    output = NS(type="model_output", content=[{"type": "text", "text": "Tagihan sudah lunas."}])
    return [event("step.start", index=0, step=NS(type="model_output")),
            event("step.delta", index=0, delta=NS(type="text", text="Tagihan sudah lunas.")),
            event("step.stop", index=0, step=output),
            event("interaction.completed", interaction=NS(status="completed"))]


class FakeClient:
    def __init__(self, *results):
        self.responses = list(results)
        self.calls = []
        self.interactions = self
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return iter(self.responses.pop(0))


def test_tool_allowlist_including_enrollment_status():
    assert sum(len(v) for v in ROLE_TO_TOOLS.values()) == 11
    for role, allowed in ROLE_TO_TOOLS.items():
        login(role)
        control = AIToolController(role, repo=FakeRepo())
        declared = {item["name"] for item in control.declarations()}
        expected = set(allowed) | set(EXTRA_ROLE_TO_TOOLS[role]) | set(PATCH5C_ROLE_TO_TOOLS[role]) | (set(HISTORY_TOOLS) if role == "admin" else set()) | {ROLE_DYNAMIC_NAMES[role]}
        if control.rag_tool is not None:
            expected.add("search_knowledge_base")
        assert declared == expected
        assert all(item["type"] == "function" for item in control.declarations())


def test_spoofing_id_and_cross_role_blocked():
    login("siswa", 71)
    repo = FakeRepo()
    ctrl = AIToolController("siswa", repo=repo)
    for name, args in (("get_admin_overview", {}), ("get_my_grades", {"student_id": 99}),
                       ("get_my_grades", {"program_id": "1 OR 1=1"})):
        with pytest.raises((PermissionError, ValueError)):
            ctrl.execute(name, args)
    assert repo.calls == []
    with pytest.raises(PermissionError):
        AIToolController("admin", repo=repo)
    assert ctrl.execute("get_my_grades", {}) == {"data": [{"status": "lunas"}], "jumlah_ditampilkan": 1}
    assert repo.calls[-1] == (71, "siswa", "get_my_grades", {})
    session.logout()
    with pytest.raises(PermissionError):
        ctrl.execute("get_my_grades", {})


def test_database_calls_stateless_and_history_protected():
    login()
    repo = FakeRepo()
    controller = AIToolController("siswa", repo=repo)
    fake = FakeClient(tool_stream(), answer_stream())
    gemini = GeminiClient(GeminiOptions(api_key="fake"), client=fake)
    result = list(DatabaseFunctionChat(gemini, controller).stream([], "Tagihan saya?", "instruksi"))
    assert [x.kind for x in result] == ["db_read_started", "text_chunk", "completed"]
    assert "Tagihan sudah" in result[-1].payload["content"]
    assert repo.calls == [(71, "siswa", "get_my_invoices", {})]
    assert all(c["store"] is False for c in fake.calls)
    assert fake.calls[0]["tools"][0]["name"] == "get_my_schedule"
    history = fake.calls[1]["input"]
    assert [s["type"] for s in history] == ["user_input", "thought", "function_call", "function_result"]
    assert history[1]["signature"] == "opaque-thinking"
    assert history[3]["call_id"] == "fc-123"
    assert '"lunas"' in history[3]["result"][0]["text"]
    assert [s["type"] for s in result[-1].payload["data"]["steps"]] == [
        "user_input", "thought", "function_call", "function_result", "model_output"]


def test_malicious_model_call_never_reads_db():
    login()
    repo = FakeRepo()
    controller = AIToolController("siswa", repo=repo)
    fake = FakeClient(tool_stream("get_admin_overview"))
    gemini = GeminiClient(GeminiOptions(api_key="fake"), client=fake)
    result = list(DatabaseFunctionChat(gemini, controller).stream([], "hack", "safe"))
    assert result[-1].kind == "error" and repo.calls == []
    assert "completed" not in [r.kind for r in result]


def test_session_change_before_call_is_rejected():
    login()
    controller = AIToolController("siswa", repo=FakeRepo())
    session.set_user({"id": 999, "role": "siswa", "status": "aktif"})
    with pytest.raises(PermissionError):
        controller.execute("get_my_invoices", {})


def test_incomplete_stream_does_not_execute_or_commit():
    login()
    ctrl = AIToolController("siswa", repo=FakeRepo())
    fake = FakeClient(tool_stream()[:-1])
    gemini = GeminiClient(GeminiOptions(api_key="fake"), client=fake)
    result = list(DatabaseFunctionChat(gemini, ctrl).stream([], "get data", "safe"))
    assert result[-1].kind == "error"
    assert "completed" not in [v.kind for v in result]


def test_queries_are_static_selects_and_restricted():
    assert len(QUERIES) == 11
    for query in QUERIES.values():
        assert query.lstrip().upper().startswith("SELECT")
        assert all(term not in query.upper() for term in ("DELETE FROM", "UPDATE USERS", "DROP TABLE", "INSERT INTO"))
        assert "LIMIT 20" in query or "COUNT(*)" in query


def test_repo_sets_readonly_and_checks_db_user(monkeypatch):
    login()
    records = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self, query, params=None): records.append((query, params))
        def fetchone(self): return {"role": "siswa", "status": "aktif"}
        def fetchmany(self, n): return [{"program": "Aljabar"}]
    class Conn:
        def __enter__(self): return self
        def __exit__(self,*a): pass
        @contextmanager
        def transaction(self): yield
        def cursor(self, **kwargs): return Cursor()
    class Pool:
        def connection(self, timeout): return Conn()
    monkeypatch.setitem(sys.modules, "psycopg", types.ModuleType("psycopg"))
    mod = types.ModuleType("psycopg.rows")
    mod.dict_row = object()
    monkeypatch.setitem(sys.modules, "psycopg.rows", mod)
    result = AIReadRepository(Pool()).execute(71, "siswa", "get_my_invoices", {})
    assert result["data"][0]["program"] == "Aljabar"
    assert records[0][0] == "SET TRANSACTION READ ONLY"
    assert records[1][0].startswith("SET LOCAL statement_timeout")
    assert records[2][1] == (71,)
    assert records[3][1] == (71,)


def test_ai_service_uses_db_only_with_login(monkeypatch):
    login()
    repo = FakeRepo()
    # Supply a stubbed AIToolController to avoid real DB; no DB IO occurs.
    import app.services.ai_tool_controller as mod
    original = mod.AIToolController
    class StubController(original):
        def __init__(self, role): super().__init__(role, repo=repo)
    monkeypatch.setattr(mod, "AIToolController", StubController)
    fake = FakeClient(tool_stream(), answer_stream())
    adapter = GeminiClient(GeminiOptions(api_key="test"), client=fake)
    service = AIService("siswa", client=adapter)
    events = list(service.stream("Tagihan saya?", "siswa"))
    assert events[-1].kind == "completed"
    assert events[-1].payload["data"] == {} # never reveal tool raw steps to UI
    assert len(service.history) == 5
    service.reset()
    assert not service.history
