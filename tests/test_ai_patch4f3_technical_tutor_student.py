"""Patch 4F.3 offline regressions: no real database or Gemini calls."""
from contextlib import contextmanager
from pathlib import Path
import sys
import types

import pytest

from app import session
from app.repositories.ai_read_repo import (
    AIReadRepository, ADMIN_TUTOR_STUDENTS, ADMIN_TUTOR_STUDENT_COUNT, MAX_ROWS,
)
from app.services.ai_tool_controller import AIToolController, validate_args, tool_schema
from app.services.hybrid_evidence import HybridEvidence
from app.services.rag.relevance import is_relevant
from app.services.ai_service import _trusted_session_hint


@pytest.fixture(autouse=True)
def reset_session():
    before = session.get_user()
    session.logout()
    yield
    session.set_user(before)


def login(role='admin', user_id=7, name='Admin Uji'):
    session.set_user({'id': user_id, 'role': role, 'status': 'aktif',
                      'nama_lengkap': name, 'username': 'admin_uji'})


class FakeRepo:
    def __init__(self, *, search=None):
        self.calls = []
        self.search = search or [{'user_id': 12, 'nama_lengkap': 'Mohammad Zarkasi',
                                  'role': 'tutor', 'status': 'aktif'}]

    def execute(self, uid, role, tool, args):
        self.calls.append((uid, role, tool, dict(args)))
        if tool == 'admin_find_users':
            return {'data': self.search}
        if tool == 'admin_list_students_by_tutor':
            return {'data': [{'program': 'Matematika SMP', 'siswa': 'Siswa Demo',
                              'status_pendaftaran': 'aktif'}],
                    'jumlah_siswa_unik': 1, 'jumlah_pendaftaran_program': 1}
        return {'data': []}


def test_chatscreen_flow_is_technical_knowledge_not_python_demo():
    q='Jelaskan bagaimana ChatScreen mengelola percakapan, streaming, dan reset konteks AI.'
    assert is_relevant(q, 'sibima-code-source-v4f1',
                       'Alur Kode dan Modul SIBIMA', 'ChatScreen',
                       'ChatScreen memanggil reset untuk membersihkan riwayat streaming.')
    assert not is_relevant(q, 'demo-pembelajaran-python-rag-v1',
                           'DEMO RAG — Python Dasar', 'Contoh Variabel Python',
                           'variabel nama = "SIBIMA"')
    assert HybridEvidence().refusal(q) is not None


def test_chatscreen_wrong_section_is_rejected():
    q='Jelaskan fungsi ChatScreen untuk reset konteks AI.'
    assert not is_relevant(q, 'sibima-code-source-v4f1',
                           'Alur Kode dan Modul SIBIMA', 'Invoice',
                           'invoice dibuat pada pendaftaran dan diverifikasi oleh admin.')


def test_chatscreen_document_citation_is_not_borrowed_from_demo():
    q='Jelaskan flow ChatScreen streaming dan reset konteks AI.'
    ledger=HybridEvidence(original_query=q)
    ledger.record('search_knowledge_base', {'status':'ok', 'hasil': [
        {'judul':'DEMO RAG — Python Dasar', 'bagian':'Contoh Variabel Python',
         'document_id':'demo-pembelajaran-python-rag-v1', 'kutipan':'variabel Python'},
        {'judul':'Alur Kode SIBIMA', 'bagian':'ChatScreen',
         'document_id':'sibima-code-source-v4f1', 'kutipan':'ChatScreen reset konteks streaming'}]})
    assert 'ChatScreen' in ledger.source_footer()
    assert 'DEMO' not in ledger.source_footer()


@pytest.mark.parametrize('role', ('tutor', 'siswa'))
def test_student_lookup_not_declared_or_executable_to_non_admin(role):
    login(role)
    repo=FakeRepo()
    controller=AIToolController(role, repo=repo)
    assert 'admin_list_students_by_tutor' not in {t['name'] for t in controller.declarations()}
    with pytest.raises(PermissionError):
        controller.execute('admin_list_students_by_tutor', {'tutor_user_id': 12})
    assert not repo.calls


def test_admin_must_discover_real_tutor_id():
    login()
    repo=FakeRepo()
    controller=AIToolController('admin', repo=repo)
    with pytest.raises(PermissionError):
        controller.execute('admin_list_students_by_tutor', {'tutor_user_id': 12})
    controller.execute('admin_find_users', {'query':'Zarkasi'})
    result=controller.execute('admin_list_students_by_tutor', {'tutor_user_id': 12})
    assert result['data'][0]['siswa'] == 'Siswa Demo'
    assert repo.calls[-1] == (7, 'admin', 'admin_list_students_by_tutor', {'tutor_user_id': 12})
    with pytest.raises(PermissionError):
        controller.execute('admin_list_students_by_tutor', {'tutor_user_id': 99})


def test_non_tutor_candidate_never_authorized():
    login()
    controller=AIToolController('admin', repo=FakeRepo(search=[
        {'user_id': 25, 'nama_lengkap': 'Zarkasi', 'role': 'siswa'}]))
    controller.execute('admin_find_users', {'query': 'Zarkasi'})
    with pytest.raises(PermissionError):
        controller.execute('admin_list_students_by_tutor', {'tutor_user_id': 25})


@pytest.mark.parametrize('value', [True, False, 0, -3, '12', 1.5, None])
def test_tutor_id_must_be_positive_int_not_boolean(value):
    with pytest.raises(ValueError):
        validate_args('admin_list_students_by_tutor', {'tutor_user_id': value})


def test_no_arbitrary_sql_or_identity_override_args():
    for args in ({'tutor_user_id':12,'sql':'DELETE FROM users'},
                 {'tutor_user_id':12,'role':'admin'},
                 {'user_id':7}):
        with pytest.raises(ValueError):
            validate_args('admin_list_students_by_tutor', args)
    declared = tool_schema('admin_list_students_by_tutor')['parameters']
    assert declared['required'] == ['tutor_user_id']
    assert set(declared['properties']) == {'tutor_user_id'}


def test_session_role_change_blocks_cached_tutor():
    login()
    ctrl=AIToolController('admin', repo=FakeRepo())
    ctrl.execute('admin_find_users', {'query': 'Zarkasi'})
    login(role='siswa', user_id=8)
    with pytest.raises(PermissionError):
        ctrl.execute('admin_list_students_by_tutor', {'tutor_user_id':12})


def test_sql_is_select_only_and_requires_active_enrollment_tutor_schedule():
    for sql in [ADMIN_TUTOR_STUDENTS, ADMIN_TUTOR_STUDENT_COUNT]:
        upper=sql.strip().upper()
        assert upper.startswith('SELECT')
        assert 'EXISTS' in upper and "E.STATUS='AKTIF'" in upper
        assert 'S.TUTOR_ID=%S' in upper and 'S.AKTIF=TRUE' in upper
        assert 'PASSWORD' not in upper and 'OTP' not in upper
        assert not any(word in upper for word in ['DELETE FROM', 'UPDATE USERS', 'INSERT INTO'])
    assert f'LIMIT {MAX_ROWS}' in ADMIN_TUTOR_STUDENTS


def test_trusted_session_hint_never_uses_searched_target_or_sensitive_data():
    hint=_trusted_session_hint({'id':7, 'nama_lengkap':'Admin Uji',
                                'username':'admin_uji', 'role':'admin',
                                'password_hash':'super_secret', 'email':'email@demo.test',
                                'searched_person':'Mohammad Zarkasi'})
    assert 'Admin Uji' in hint and 'admin_uji' in hint
    assert 'Mohammad Zarkasi' not in hint and 'super_secret' not in hint
    assert 'email@demo.test' not in hint
    assert 'orang yang sedang dicari' in hint


def test_db_repo_performs_readonly_sql_with_bound_id_and_role_validation(monkeypatch):
    login()
    executed=[]
    class Cursor:
        def __init__(self): self.queue = []
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params=None):
            executed.append((sql, params))
            if 'SELECT role::text AS role FROM users WHERE id=%s' in sql:
                self.queue=[{'role':'tutor'}]
            elif 'COUNT(DISTINCT e.student_id)' in sql:
                self.queue=[{'jumlah_siswa_unik':2, 'jumlah_pendaftaran_program':3}]
            elif 'SELECT DISTINCT p.nama' in sql:
                self.queue=[{'program':'Python','siswa':'Siswa Demo A','status_pendaftaran':'aktif'}]
            else:
                self.queue=[{'role':'admin','status':'aktif'}]
        def fetchone(self): return self.queue.pop(0) if self.queue else None
        def fetchmany(self, size): return self.queue[:size]
    class Conn:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        @contextmanager
        def transaction(self): yield
        def cursor(self, **kwargs): return Cursor()
    class Pool:
        def connection(self, timeout): return Conn()
    monkeypatch.setitem(sys.modules, 'psycopg', types.ModuleType('psycopg'))
    rows = types.ModuleType('psycopg.rows'); rows.dict_row=object()
    monkeypatch.setitem(sys.modules, 'psycopg.rows', rows)
    result=AIReadRepository(Pool()).execute(7, 'admin', 'admin_list_students_by_tutor', {'tutor_user_id':12})
    assert result['jumlah_siswa_unik'] == 2
    assert result['jumlah_pendaftaran_program'] == 3
    assert result['data'][0]['program'] == 'Python'
    assert 'Bukan bukti' in result['basis']
    assert executed[0][0] == 'SET TRANSACTION READ ONLY'
    assert all(sql != 'DROP TABLE' for sql, _ in executed)
    assert all('12' not in sql for sql, _ in executed)
    ids=[params for _, params in executed if params==(12,)]
    assert len(ids) == 3  # role lookup, count, list


def test_knowledge_manifest_includes_relevant_new_source_files():
    from tools.verify_sibima_knowledge import verify
    root=Path(__file__).resolve().parents[1]
    manifest=root/'knowledge/verified/source_manifest.json'
    if not manifest.exists():
        pytest.skip('Verified docs are absent from this installation')
    assert verify()[0]


def test_multiple_tutor_candidates_must_be_disambiguated():
    login()
    repo=FakeRepo(search=[
        {'user_id':12,'role':'tutor','nama_lengkap':'Zarkasi Satu'},
        {'user_id':13,'role':'tutor','nama_lengkap':'Zarkasi Dua'}])
    ctrl=AIToolController('admin', repo=repo)
    ctrl.execute('admin_find_users', {'query':'Zarkasi'})
    with pytest.raises(PermissionError, match='lebih dari satu Tutor'):
        ctrl.execute('admin_list_students_by_tutor', {'tutor_user_id':12})
    assert not any(name == 'admin_list_students_by_tutor' for _, _, name, _ in repo.calls)


def test_new_search_discards_previous_tutor_discovery():
    login()
    repo=FakeRepo()
    ctrl=AIToolController('admin', repo=repo)
    ctrl.execute('admin_find_users', {'query':'Zarkasi'})
    repo.search=[{'user_id':19,'role':'tutor','nama_lengkap':'Tutor Lain'}]
    ctrl.execute('admin_find_users', {'query':'Tutor Lain'})
    with pytest.raises(PermissionError):
        ctrl.execute('admin_list_students_by_tutor', {'tutor_user_id':12})
    assert ctrl.execute('admin_list_students_by_tutor', {'tutor_user_id':19})


def test_evidence_requires_tool_for_typo_in_murid_query():
    ledger=HybridEvidence()
    assert ledger.refusal('siapa ssaja murid yang diajar tutor Zarkasi') is not None
    ledger.record('admin_find_users', {'data': [{'user_id':12,'role':'tutor'}]})
    assert ledger.refusal('siapa ssaja murid yang diajar tutor Zarkasi') is not None
    ledger.record('admin_list_students_by_tutor', {'data': []})
    assert ledger.refusal('siapa ssaja murid yang diajar tutor Zarkasi') is None


def test_failed_research_does_not_leave_stale_tutor_discovery():
    login()
    repo=FakeRepo()
    ctrl=AIToolController('admin', repo=repo)
    ctrl.execute('admin_find_users', {'query':'Zarkasi'})
    def failed_lookup(*args): raise RuntimeError('database unavailable')
    repo.execute=failed_lookup
    with pytest.raises(RuntimeError):
        ctrl.execute('admin_find_users', {'query':'Tutor Lain'})
    # Even when repository is restored, previously discovered tutor ID is stale.
    repo.execute=FakeRepo().execute
    with pytest.raises(PermissionError):
        ctrl.execute('admin_list_students_by_tutor', {'tutor_user_id':12})
