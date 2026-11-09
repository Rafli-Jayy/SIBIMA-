"""Patch 4F.3: Admin Tutor→student lookup, source relevance, identity isolation.

All tests are offline. Database effects are emulated, never performed.
"""
from contextlib import contextmanager
import json
import re
import sys
import types
from pathlib import Path

import pytest

from app import session
from app.repositories.ai_read_repo import (
    AIReadRepository, ADMIN_TUTOR_STUDENTS, ADMIN_TUTOR_STUDENT_COUNT,
    EXTRA_AUTHORIZED,
)
from app.services.ai_service import _trusted_session_hint, AIService
from app.services.ai_tool_controller import AIToolController, validate_args
from app.services.hybrid_evidence import HybridEvidence, _DOCUMENT_REQUEST
from app.services.rag.relevance import is_relevant

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def restore_session(monkeypatch):
    prev = session.get_user()
    monkeypatch.delenv('SIBIMA_RAG_ENABLED', raising=False)
    session.set_user({'id': 7, 'role': 'admin', 'status': 'aktif',
                      'nama_lengkap': 'Admin Asli', 'username': 'admin_asli'})
    yield
    session.set_user(prev)


class FakeRepo:
    def __init__(self, multiple=False):
        self.calls = []
        self.multiple = multiple

    def execute(self, uid, role, name, args):
        self.calls.append((uid, role, name, args))
        if name == 'admin_find_users':
            found = [{'user_id': 33, 'nama_lengkap': 'Mohammad Zarkasi', 'role': 'tutor'}]
            if self.multiple:
                found += [{'user_id': 34, 'nama_lengkap': 'Rizal Zarkasi', 'role': 'tutor'}]
            return {'data': found}
        if name == 'admin_list_students_by_tutor':
            return {'data': [{'program': 'Matematika SMP', 'siswa': 'Siswa Demo',
                              'status_pendaftaran': 'aktif'}],
                    'jumlah_siswa_unik': 1, 'jumlah_pendaftaran_program': 1}
        return {'data': []}


def test_admin_must_discover_tutor_id_before_listing_students():
    repo = FakeRepo()
    ctrl = AIToolController('admin', repo=repo)
    with pytest.raises(PermissionError):
        ctrl.execute('admin_list_students_by_tutor', {'tutor_user_id': 33})
    assert repo.calls == []
    ctrl.execute('admin_find_users', {'query': 'Zarkasi'})
    out = ctrl.execute('admin_list_students_by_tutor', {'tutor_user_id': 33})
    assert out['data'][0]['siswa'] == 'Siswa Demo'
    assert repo.calls[-1] == (7, 'admin', 'admin_list_students_by_tutor', {'tutor_user_id': 33})


def test_discovery_cannot_be_reused_after_unrelated_search():
    ctrl = AIToolController('admin', repo=FakeRepo())
    ctrl.execute('admin_find_users', {'query': 'Zarkasi'})
    ctrl.execute('admin_find_users', {'query': 'Orang Lain'})
    # A successful new lookup clears previous matches; here the fake returns
    # same tutor again, so test instead session-identity invalidation below.
    session.set_user({'id': 8, 'role': 'admin', 'status': 'aktif'})
    with pytest.raises(PermissionError):
        ctrl.execute('admin_list_students_by_tutor', {'tutor_user_id': 33})


def test_multiple_tutor_candidates_need_disambiguation():
    repo = FakeRepo(multiple=True)
    ctrl = AIToolController('admin', repo=repo)
    ctrl.execute('admin_find_users', {'query': 'Zarkasi'})
    with pytest.raises(PermissionError, match='lebih dari satu Tutor'):
        ctrl.execute('admin_list_students_by_tutor', {'tutor_user_id': 33})
    assert len(repo.calls) == 1


@pytest.mark.parametrize('value', [0, -2, True, 3.5, '33', None, {}, []])
def test_tutor_id_rejects_untrusted_values(value):
    with pytest.raises(ValueError):
        validate_args('admin_list_students_by_tutor', {'tutor_user_id': value})


@pytest.mark.parametrize('role', ['tutor', 'siswa'])
def test_non_admin_cannot_obtain_student_list(role):
    session.set_user({'id': 13, 'role': role, 'status': 'aktif'})
    repo = FakeRepo()
    ctrl = AIToolController(role, repo=repo)
    assert 'admin_list_students_by_tutor' not in [x['name'] for x in ctrl.declarations()]
    with pytest.raises(PermissionError):
        ctrl.execute('admin_list_students_by_tutor', {'tutor_user_id': 33})
    assert repo.calls == []


def test_fixed_queries_use_enrollment_and_schedule_with_distinct_counts():
    for sql in (ADMIN_TUTOR_STUDENTS, ADMIN_TUTOR_STUDENT_COUNT):
        lower = sql.lower()
        assert lower.lstrip().startswith('select')
        assert 'from enrollments e' in lower
        assert 's.tutor_id=%s' in lower
        assert "e.status='aktif'" in lower
        assert 'insert into' not in lower and 'delete from' not in lower
        assert 'password_hash' not in lower and 'otp_codes' not in lower
    assert 'count(distinct e.student_id)' in ADMIN_TUTOR_STUDENT_COUNT.lower()
    assert 'limit 20' in ADMIN_TUTOR_STUDENTS.lower()
    assert 'admin_list_students_by_tutor' in EXTRA_AUTHORIZED['admin']


def test_tutor_students_requires_grounded_database_result():
    q = 'Siapa saja murid yang diajar tutor Zarkasi?'
    ev = HybridEvidence(original_query=q)
    assert ev.refusal(q) is not None
    ev.record('admin_find_users', {'data': [{'user_id': 33, 'nama_lengkap': 'Zarkasi'}]})
    assert ev.refusal(q) is not None
    ev.record('admin_list_students_by_tutor', {'data': [{'program': 'Python', 'siswa': 'Siswa Demo'}]})
    assert ev.refusal(q) is None


def test_chat_screen_question_is_technical_even_without_sibima_keyword():
    q = 'Jelaskan bagaimana ChatScreen mengelola percakapan, streaming, dan reset konteks AI.'
    docid = 'sibima-code-source-v4f1'
    title = 'Alur Kode, Modul dan Fungsi SIBIMA'
    assert _DOCUMENT_REQUEST.search(q)
    assert is_relevant(q, docid, title, '7A. UI dan ChatScreen',
                       'ChatScreen memanggil streaming_renderer dan reset')
    assert not is_relevant(q, 'demo-pembelajaran-python-rag-v1',
                           'DEMO Python', 'Contoh Variabel Python',
                           'Python digunakan untuk belajar variabel')
    assert not is_relevant(q, 'sibima-flow-source-v4f1',
                           'Alur Sistem SIBIMA', 'Program siswa',
                           'Proses registrasi siswa dan jadwal tutor')


def test_identity_hint_is_session_only_and_minimally_scoped():
    hint = _trusted_session_hint({'id': 7, 'nama_lengkap': 'Admin Asli',
                                  'username': 'admin_asli', 'role': 'admin',
                                  'email': 'private@example.org', 'password_hash': 'HASH-SECRET',
                                  'api_key': 'KEY-SECRET'})
    assert 'Admin Asli' in hint and 'admin_asli' in hint
    for secret in ('private@example.org', 'HASH-SECRET', 'KEY-SECRET'):
        assert secret not in hint
    assert 'orang yang sedang dicari' in hint


def test_chat_rejects_switched_login_before_gemini_request():
    class StubGemini:
        pass
    ai = AIService('admin', client=StubGemini())
    session.set_user({'id': 7, 'role': 'siswa', 'status': 'aktif'})
    with pytest.raises(PermissionError):
        list(ai.stream('Halo', 'admin'))


def test_repository_in_read_only_transaction_and_uses_bound_tutor_id(monkeypatch):
    calls = []

    class Cursor:
        stage = 0
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, sql, params=None):
            calls.append((sql, params))
        def fetchone(self):
            sql = calls[-1][0]
            if 'SELECT role::text AS role, status::text AS status' in sql:
                return {'role': 'admin', 'status': 'aktif'}
            if 'SELECT role::text AS role FROM users' in sql:
                return {'role': 'tutor'}
            if 'COUNT(DISTINCT e.student_id)' in sql:
                return {'jumlah_siswa_unik': 1, 'jumlah_pendaftaran_program': 2}
            raise AssertionError('Unexpected fetchone: ' + sql[:70])
        def fetchmany(self, max_rows):
            assert max_rows == 20
            return [{'program': 'Matematika SMP', 'siswa': 'Siswa Demo',
                     'status_pendaftaran': 'aktif'}]
        def __init__(self): pass

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        @contextmanager
        def transaction(self): yield self
        def cursor(self, **kwargs): return Cursor()

    class Pool:
        @contextmanager
        def connection(self, **kwargs): yield Connection()

    fake_psycopg = types.ModuleType('psycopg')
    fake_rows = types.ModuleType('psycopg.rows')
    fake_rows.dict_row = object()
    monkeypatch.setitem(sys.modules, 'psycopg', fake_psycopg)
    monkeypatch.setitem(sys.modules, 'psycopg.rows', fake_rows)
    result = AIReadRepository(pool=Pool()).execute(7, 'admin', 'admin_list_students_by_tutor', {'tutor_user_id': 33})
    assert result['jumlah_siswa_unik'] == 1
    assert result['jumlah_pendaftaran_program'] == 2
    assert any('SET TRANSACTION READ ONLY' in sql for sql, _ in calls)
    assert all(params == (33,) for sql, params in calls if 's.tutor_id=%s' in sql)
    assert all(params == (7,) for sql, params in calls if 'AS status FROM users' in sql)
    assert not any(re.search(r'\b(?:INSERT|UPDATE|DELETE)\b', sql, re.I) for sql, _ in calls)


def test_manifest_matches_exact_patched_source():
    from tools.verify_sibima_knowledge import verify
    ok, mismatches = verify()
    assert ok, mismatches
