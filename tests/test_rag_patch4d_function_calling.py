"""Patch 4D offline tests: no network, DB access, Chroma installation or API quota."""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from app import session
from app.services.ai_db_chat import DatabaseFunctionChat
from app.services.ai_tool_controller import AIToolController, ROLE_TO_TOOLS
from app.services.ai_service import RAG_INSTRUCTION
from app.services.gemini_client import GeminiClient, GeminiOptions
from app.services.rag.rag_chat_tool import RAGKnowledgeTool, rag_enabled, TOOL_NAME


@pytest.fixture(autouse=True)
def session_isolation(monkeypatch):
    before = session.get_user()
    session.logout()
    monkeypatch.delenv('SIBIMA_RAG_ENABLED', raising=False)
    yield
    session.set_user(before)


def login(role='siswa', user_id=15):
    session.set_user({'id': user_id, 'role': role, 'status': 'aktif'})


class FakeRepo:
    def __init__(self):
        self.calls = []

    def execute(self, user_id, role, name, arguments):
        self.calls.append((user_id, role, name, arguments))
        return {'data': [{'siswa_aktif': 8}], 'jumlah_ditampilkan': 1}


class FakeStore:
    def __init__(self, *, hits=None):
        self.calls = []
        self.hits = ([NS(document_id='demo-python', title='DEMO Python',
                                 section='Variabel', source='DEMO Python — Variabel',
                                 text='Variabel menyimpan nilai.', distance=.2)] if hits is None else hits)

    def search(self, query, *, role, limit):
        self.calls.append((query, role, limit))
        return self.hits


class OfflineAPI:
    def __init__(self, streams):
        self.streams = list(streams)
        self.calls = []
        self.interactions = self

    def create(self, **kwargs):
        assert kwargs['store'] is False
        self.calls.append(kwargs)
        return iter(self.streams.pop(0))


def ev(name, **kwargs):
    return NS(event_type=name, **kwargs)


def request_call(name, call_id, args):
    import json
    step = {'type': 'function_call', 'id': call_id, 'name': name}
    return [ev('step.start', index=0, step={'type': 'thought', 'signature': 'sig'}),
            ev('step.stop', index=0),
            ev('step.start', index=1, step=step),
            ev('step.delta', index=1, delta={'type': 'arguments_delta',
                                             'arguments': json.dumps(args)}),
            ev('step.stop', index=1),
            ev('interaction.completed', interaction=NS(status='requires_action'))]


def answer(text):
    step = {'type': 'model_output', 'content': [{'type': 'text', 'text': text}]}
    return [ev('step.start', index=0, step={'type': 'model_output'}),
            ev('step.delta', index=0, delta={'type': 'text', 'text': text}),
            ev('step.stop', index=0, step=step),
            ev('interaction.completed', interaction=NS(status='completed'))]


def controlled(*, role='siswa', store=None, repo=None):
    login(role)
    store = store or FakeStore()
    repo = repo or FakeRepo()
    rag = RAGKnowledgeTool(store=store)
    return AIToolController(role, repo=repo, rag_tool=rag), store, repo


def test_rag_tool_is_opt_in_and_db_allowlist_unchanged(monkeypatch):
    assert not rag_enabled()
    login('siswa')
    control = AIToolController('siswa', repo=FakeRepo())
    assert TOOL_NAME not in {d['name'] for d in control.declarations()}
    with pytest.raises(PermissionError):
        control.execute(TOOL_NAME, {'query': 'belajar Python'})
    assert sum(len(v) for v in ROLE_TO_TOOLS.values()) == 11
    monkeypatch.setenv('SIBIMA_RAG_ENABLED', 'true')
    assert rag_enabled()
    enabled = AIToolController('siswa', repo=FakeRepo())
    assert TOOL_NAME in {d['name'] for d in enabled.declarations()}
    assert enabled.declarations()[-1]['parameters']['required'] == ['query']


@pytest.mark.parametrize('role', ['admin', 'tutor', 'siswa'])
def test_retrieval_uses_authenticated_role_not_model_arguments(role):
    controller, store, repo = controlled(role=role)
    output = controller.execute(TOOL_NAME, {'query': 'cara memakai variabel Python'})
    assert store.calls == [('cara memakai variabel Python', role, 3)]
    assert output['status'] == 'ok' and output['jumlah'] == 1
    assert output['hasil'][0]['referensi'] == 'DEMO Python — Variabel'
    assert 'DEMO' in output['hasil'][0]['judul']
    assert repo.calls == []
    for args in ({'query': 'cara menyimpan nilai', 'role': 'admin'},
                 {'query': 'cara menyimpan nilai', 'user_id': 1},
                 {'sql': 'SELECT * FROM users'},
                 {'query': ''}, {'query': 'x'*501}):
        with pytest.raises((ValueError, PermissionError)):
            controller.execute(TOOL_NAME, args)
    assert len(store.calls) == 1


def test_logout_or_role_switch_blocks_rag():
    control, store, repo = controlled()
    session.logout()
    with pytest.raises(PermissionError):
        control.execute(TOOL_NAME, {'query': 'materi Python'})
    login('admin', 15)
    with pytest.raises(PermissionError):
        control.execute(TOOL_NAME, {'query': 'materi Python'})
    assert not store.calls


def test_no_matches_and_missing_index_fail_closed():
    control, store, repo = controlled(store=FakeStore(hits=[]))
    result = control.execute(TOOL_NAME, {'query': 'materi tidak ada'})
    assert result['status'] == 'no_matches'
    assert result['hasil'] == []
    class Broken:
        def search(self, *args, **kwargs):
            raise RuntimeError('sensitive api key or data should never be shown')
    rag = RAGKnowledgeTool(store=Broken())
    result = rag.search('materi tidak ada', role='siswa')
    assert result['status'] == 'unavailable'
    assert 'sensitive' not in str(result)


def test_rag_config_cannot_escape_knowledge_root():
    with pytest.raises(ValueError):
        RAGKnowledgeTool(source_root='../../private')
    with pytest.raises(ValueError):
        RAGKnowledgeTool(index_dir='/tmp')


def test_full_stateless_function_call_to_rag_and_back():
    controller, store, repo = controlled()
    sdk = OfflineAPI([request_call(TOOL_NAME, 'rag-1', {'query': 'variabel Python'}),
                      answer('Variabel menyimpan nilai. Sumber: DEMO Python — Variabel.')])
    gemini = GeminiClient(GeminiOptions(api_key='offline'), client=sdk)
    events = list(DatabaseFunctionChat(gemini, controller).stream([], 'Jelaskan variabel', 'RAG test'))
    assert [e.kind for e in events] == ['db_read_started', 'text_chunk', 'completed']
    assert len(sdk.calls) == 2
    assert any(d['name'] == TOOL_NAME for d in sdk.calls[0]['tools'])
    payload = sdk.calls[1]['input'][-1]
    assert payload['type'] == 'function_result'
    assert payload['name'] == TOOL_NAME
    assert payload['call_id'] == 'rag-1'
    assert 'DEMO Python' in payload['result'][0]['text']
    assert events[-1].kind == 'completed'
    assert repo.calls == []


def test_hybrid_two_calls_in_one_turn_stays_role_scoped():
    controller, store, repo = controlled()
    sdk = OfflineAPI([request_call('get_my_invoices', 'db-1', {}),
                      request_call(TOOL_NAME, 'rag-2', {'query': 'prosedur tagihan'}),
                      answer('Tagihan dicek. Sumber aturan: tidak tersedia secara resmi.')])
    gemini = GeminiClient(GeminiOptions(api_key='offline'), client=sdk)
    events = list(DatabaseFunctionChat(gemini, controller).stream([], 'tagihan dan aturan?', 's'))
    assert events[-1].kind == 'completed'
    assert len(repo.calls) == 1
    assert repo.calls[0][0:3] == (15, 'siswa', 'get_my_invoices')
    assert store.calls == [('prosedur tagihan', 'siswa', 3)]
    assert [v['type'] for v in sdk.calls[-1]['input']].count('function_result') == 2


def test_rag_instruction_does_not_treat_demo_as_official_policy():
    assert 'DEMO' in RAG_INSTRUCTION
    assert 'TIDAK DIPERCAYA' in RAG_INSTRUCTION
    assert 'search_knowledge_base' in RAG_INSTRUCTION
