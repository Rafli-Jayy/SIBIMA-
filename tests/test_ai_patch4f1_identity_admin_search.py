"""Patch 4F.1 security and role semantics. Offline; no Gemini API or PostgreSQL."""
from contextlib import contextmanager
from types import SimpleNamespace as NS
import sys
import types

import pytest

from app import session
from app.repositories.ai_read_repo import (AIReadRepository, QUERIES, EXTRA_QUERIES,
    EXTRA_AUTHORIZED, ADMIN_STUDENT_ENROLLMENTS, ADMIN_TUTOR_SCHEDULE)
from app.services.ai_tool_controller import (AIToolController, ROLE_TO_TOOLS,
    EXTRA_ROLE_TO_TOOLS, validate_args)
from app.services.ai_access_messages import role_access_clarification
from app.services.hybrid_evidence import HybridEvidence
from app.services.gemini_client import GeminiClient, GeminiOptions
from app.services.ai_db_chat import DatabaseFunctionChat


@pytest.fixture(autouse=True)
def isolate():
    previous = session.get_user()
    session.logout()
    yield
    session.set_user(previous)


def login(role="admin", user_id=11, name="Admin Demo"):
    session.set_user({"id": user_id, "role": role, "status": "aktif",
                      "username": "demo_test", "nama_lengkap": name})


class Repo:
    def __init__(self):
        self.calls = []

    def execute(self, uid, role, name, args):
        self.calls.append((uid, role, name, args))
        if name == 'admin_find_users':
            return {'data': [{'user_id': 43, 'nama_lengkap': 'Mohammad Zarkasi',
                              'role': 'tutor', 'jadwal_mengajar_aktif': 6,
                              'program_diajar_aktif': 4}]}
        if name == 'get_my_identity':
            return {'data': [{'user_id': uid, 'nama_lengkap': 'Admin Demo',
                              'username': 'demo_test', 'role': role, 'status': 'aktif'}]}
        if name == 'admin_get_user_summary':
            return {'data': [{'user_id': args['user_id'], 'role': 'tutor'}],
                    'detail_program': [{'program': 'Python', 'hari': 'Senin'}]}
        return {'data': []}


def test_eleven_legacy_tools_unchanged_and_three_new_role_scoped():
    assert len(QUERIES) == 11
    assert sum(map(len, ROLE_TO_TOOLS.values())) == 11
    assert set(EXTRA_ROLE_TO_TOOLS['siswa']) == {'get_my_identity'}
    assert set(EXTRA_ROLE_TO_TOOLS['tutor']) == {'get_my_identity'}
    assert set(EXTRA_ROLE_TO_TOOLS['admin']) == {'get_my_identity', 'admin_find_users', 'admin_get_user_summary', 'admin_list_students_by_tutor'}
    for role in ROLE_TO_TOOLS:
        login(role)
        c = AIToolController(role, repo=Repo())
        names = {x['name'] for x in c.declarations()}
        assert set(EXTRA_ROLE_TO_TOOLS[role]) <= names
        assert set(ROLE_TO_TOOLS[role]) <= names
        if role != 'admin':
            assert 'admin_find_users' not in names
            assert 'admin_get_user_summary' not in names
            assert 'admin_list_students_by_tutor' not in names


def test_identity_read_uses_authenticated_user_not_model_id():
    login('siswa', 71)
    repo = Repo()
    c = AIToolController('siswa', repo=repo)
    result = c.execute('get_my_identity', {})
    assert result['data'][0]['user_id'] == 71
    assert repo.calls == [(71, 'siswa', 'get_my_identity', {})]
    with pytest.raises(ValueError):
        c.execute('get_my_identity', {'user_id': 43})


@pytest.mark.parametrize('role', ['tutor', 'siswa'])
def test_non_admin_name_search_blocked_even_when_directly_called(role):
    login(role)
    repo = Repo()
    c = AIToolController(role, repo=repo)
    for name, args in [('admin_find_users', {'query': 'Zarkasi'}),
                       ('admin_get_user_summary', {'user_id': 43})]:
        with pytest.raises(PermissionError):
            c.execute(name, args)
    assert not repo.calls


def test_admin_name_partial_search_and_count_differentiation():
    login()
    repo = Repo()
    c = AIToolController('admin', repo=repo)
    matches = c.execute('admin_find_users', {'query': '  ZarKaSi  '})['data']
    assert matches[0]['jadwal_mengajar_aktif'] == 6
    assert matches[0]['program_diajar_aktif'] == 4
    assert repo.calls[0] == (11, 'admin', 'admin_find_users', {'query': 'ZarKaSi'})
    assert c.execute('admin_get_user_summary', {'user_id': 43})['detail_program'][0]['program'] == 'Python'


def test_admin_detail_requires_prior_discovery_and_cannot_guess_id():
    login()
    repo = Repo()
    c = AIToolController('admin', repo=repo)
    with pytest.raises(PermissionError):
        c.execute('admin_get_user_summary', {'user_id': 43})
    c.execute('admin_find_users', {'query': 'zarkasi'})
    with pytest.raises(PermissionError):
        c.execute('admin_get_user_summary', {'user_id': 999})
    assert all(name != 'admin_get_user_summary' for _,_,name,_ in repo.calls)


@pytest.mark.parametrize('query', ['', ' ', 'x', 'a'*81, 'ab\x00cd', 123, None])
def test_reject_bad_search_query(query):
    with pytest.raises(ValueError):
        validate_args('admin_find_users', {'query': query})


def test_unknown_args_or_boolean_user_ids_rejected():
    for name, args in [('admin_find_users', {'query': 'Zarkasi', 'role': 'admin'}),
                       ('admin_get_user_summary', {'user_id': True}),
                       ('admin_get_user_summary', {'user_id': 0}),
                       ('get_my_identity', {'sql': 'SELECT * FROM users'})]:
        with pytest.raises(ValueError):
            validate_args(name, args)


def test_session_logout_or_role_switch_invalidates_discovery():
    login()
    c = AIToolController('admin', repo=Repo())
    c.execute('admin_find_users', {'query': 'Zarkasi'})
    session.set_user({'id': 71, 'role': 'siswa', 'status': 'aktif'})
    with pytest.raises(PermissionError):
        c.execute('admin_get_user_summary', {'user_id': 43})
    session.logout()
    with pytest.raises(PermissionError):
        c.execute('get_my_identity', {})


def test_exact_role_access_message_without_db_or_model():
    assert 'Admin' in role_access_clarification('admin', 'Tampilkan jadwal mengajar saya, lalu jelaskan Python.')
    assert 'siswa lain' in role_access_clarification('siswa', 'Tampilkan nilai siswa lain.')
    assert 'Tutor' in role_access_clarification('tutor', 'Tampilkan seluruh nilai semua siswa.')
    assert role_access_clarification('admin', 'Tampilkan jadwal mengajar Zarkasi') is None
    assert role_access_clarification('tutor', 'Jadwal mengajar saya') is None


def test_grounding_for_name_and_named_tutor_requires_real_tool_result():
    ev = HybridEvidence()
    assert 'database' in ev.refusal('Zarkasi itu punya kelas berapa totalnya?')
    ev.record('admin_find_users', {'data': [{'nama_lengkap': 'Mohammad Zarkasi'}]})
    assert ev.refusal('Zarkasi itu punya kelas berapa totalnya?') is None
    assert HybridEvidence().refusal('Siapa nama saya?') is not None
    ev.record('get_my_identity', {'data': [{'nama_lengkap': 'Siswa A'}]})
    assert ev.refusal('Siapa nama saya?') is None


def test_repository_queries_are_fixed_select_and_no_credentials():
    assert set(EXTRA_QUERIES) == {'get_my_identity', 'admin_find_users', 'admin_get_user_summary'}
    assert all(q.lstrip().upper().startswith('SELECT') for q in EXTRA_QUERIES.values())
    assert 'strpos(' in EXTRA_QUERIES['admin_find_users']
    assert 'LIMIT 10' in EXTRA_QUERIES['admin_find_users']
    for query in [*EXTRA_QUERIES.values(), ADMIN_STUDENT_ENROLLMENTS, ADMIN_TUTOR_SCHEDULE]:
        q = query.lower()
        assert all(secret not in q for secret in ('password_hash', 'otp_codes', 'locked_until', 'email ', 'no_hp'))
        assert all(keyword not in q for keyword in ('delete from', 'update users', 'insert into', 'drop table'))
    assert EXTRA_AUTHORIZED['siswa'] == {'get_my_identity'}


def test_actual_repo_uses_read_only_and_search_binds_literal_query(monkeypatch):
    login('admin')
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self, sql, params=None): calls.append((sql, params))
        def fetchone(self): return {'role': 'admin', 'status': 'aktif'}
        def fetchmany(self, size): return [{'user_id': 43, 'nama_lengkap': 'Zarkasi', 'role': 'tutor'}]
    class Conn:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        @contextmanager
        def transaction(self): yield
        def cursor(self, **kwargs): return Cursor()
    class Pool:
        def connection(self, timeout): return Conn()
    monkeypatch.setitem(sys.modules, 'psycopg', types.ModuleType('psycopg'))
    rows = types.ModuleType('psycopg.rows')
    rows.dict_row = object()
    monkeypatch.setitem(sys.modules, 'psycopg.rows', rows)
    payload = "' OR 1=1 --"
    result = AIReadRepository(Pool()).execute(11, 'admin', 'admin_find_users', {'query': payload})
    assert result['data'][0]['user_id'] == 43
    assert calls[0][0] == 'SET TRANSACTION READ ONLY'
    assert calls[1][0].startswith('SET LOCAL statement_timeout')
    assert calls[2][1] == (11,)
    assert calls[3][1] == (payload, payload, payload, payload)
    assert payload not in calls[3][0]


def test_named_role_rejection_is_completed_without_gemini_call():
    class SDK:
        def __init__(self): self.interactions=self; self.calls=0
        def create(self, **kwargs): self.calls += 1; raise AssertionError('must not call model')
    login('admin')
    sdk=SDK()
    gemini=GeminiClient(GeminiOptions(api_key='offline'), client=sdk)
    c=AIToolController('admin', repo=Repo())
    result=list(DatabaseFunctionChat(gemini,c).stream([], 'Tampilkan jadwal mengajar saya', 'Instruksi'))
    assert [r.kind for r in result] == ['text_chunk','completed']
    assert result[-1].payload['data']['steps']==[]
    assert 'Admin' in result[-1].payload['content']
    assert sdk.calls==0


def test_tutor_combined_finance_and_grades_cross_students_is_denied():
    msg = role_access_clarification('tutor', 'Tampilkan seluruh tagihan dan nilai semua siswa di SIBIMA.')
    assert msg is not None and 'Tutor' in msg


def test_gemini_function_call_search_name_is_stateless_and_grounded():
    import json
    def event(kind, **data):
        return NS(event_type=kind, **data)
    def tool(name, args):
        return [event('step.start', index=0,
                      step={'type': 'function_call', 'id': 'fc1', 'name': name}),
                event('step.delta', index=0,
                      delta={'type': 'arguments_delta', 'arguments': json.dumps(args)}),
                event('step.stop', index=0),
                event('interaction.completed', interaction=NS(status='requires_action'))]
    def answer(txt):
        return [event('step.start', index=0, step={'type':'model_output'}),
                event('step.delta', index=0, delta={'type':'text', 'text':txt}),
                event('step.stop', index=0, step={'type':'model_output',
                    'content':[{'type':'text', 'text':txt}]}),
                event('interaction.completed', interaction=NS(status='completed'))]
    class SDK:
        def __init__(self):
            self.interactions = self
            self.streams = [tool('admin_find_users', {'query':'Zarkasi'}),
                            answer('Mohammad Zarkasi: 6 jadwal, 4 program berbeda.')]
            self.calls = []
        def create(self, **args):
            self.calls.append(args)
            return iter(self.streams.pop(0))
    login()
    sdk = SDK()
    ctrl = AIToolController('admin', repo=Repo())
    gemini=GeminiClient(GeminiOptions(api_key='offline'), client=sdk)
    events = list(DatabaseFunctionChat(gemini, ctrl).stream([], 'Zarkasi punya kelas berapa totalnya?', 'instruksi'))
    assert events[-1].kind == 'completed'
    assert '6 jadwal' in events[-1].payload['content']
    assert len(sdk.calls) == 2
    assert all(x['store'] is False for x in sdk.calls)
    assert any(x['type']=='function_result' for x in sdk.calls[-1]['input'])


def test_gemini_identity_uses_session_and_no_user_id_parameter():
    import json
    def ev(kind, **kwargs): return NS(event_type=kind, **kwargs)
    class SDK:
        def __init__(self):
            self.interactions = self
            self.streams = [
                [ev('step.start',index=0,step={'type':'function_call','id':'identity1', 'name':'get_my_identity'}),
                 ev('step.delta',index=0,delta={'type':'arguments_delta','arguments':'{}'}),
                 ev('step.stop',index=0),ev('interaction.completed', interaction=NS(status='requires_action'))],
                [ev('step.start',index=0,step={'type':'model_output'}),
                 ev('step.delta',index=0,delta={'type':'text','text':'Akun login Anda adalah Siswa A.'}),
                 ev('step.stop',index=0,step={'type':'model_output','content':[{'type':'text','text':'Akun login Anda adalah Siswa A.'}]}),
                 ev('interaction.completed',interaction=NS(status='completed'))]
            ]
            self.requests=[]
        def create(self,**kw): self.requests.append(kw); return iter(self.streams.pop(0))
    class IdentityRepo(Repo):
        def execute(self, uid,role,name,args):
            self.calls.append((uid,role,name,args))
            return {'data':[{'user_id':uid,'nama_lengkap':'Siswa A','username':'siswa_demo','role':role,'status':'aktif'}]}
    login('siswa', 72, 'Siswa A')
    repo=IdentityRepo()
    sdk=SDK()
    ctrl=AIToolController('siswa',repo=repo)
    events=list(DatabaseFunctionChat(GeminiClient(GeminiOptions(api_key='offline'),client=sdk),ctrl).stream([], 'Nama saya siapa?', 'instruksi'))
    assert events[-1].kind=='completed'
    assert repo.calls == [(72,'siswa','get_my_identity',{})]
    assert 'Siswa A' in events[-1].payload['content']
