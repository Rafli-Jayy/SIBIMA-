"""Offline regression: truncated SSE recovery and real enrollment status.
No database connection, no Gemini API, no credentials.
"""
from types import SimpleNamespace as NS

from app.repositories.ai_read_repo import QUERIES, AUTHORIZED, AIReadRepository
from app.services.ai_tool_controller import AIToolController
from app.services.ai_db_chat import DatabaseFunctionChat
from app.services.ai_service import _current_day_hint, DATABASE_INSTRUCTION


def ev(t, **kwargs):
    return NS(event_type=t, **kwargs)


class SDK:
    def __init__(self, streams, unary=None):
        self.streams = list(streams)
        self.unary = unary
        self.calls = []
        self.interactions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        for item in kwargs['input']:
            if item['type'] == 'function_call':
                assert isinstance(item.get('arguments'), dict)
        if kwargs['stream']:
            return iter(self.streams.pop(0))
        return self.unary


class Gemini:
    def __init__(self, sdk):
        self._client = sdk
        self.options = NS(model='gemini-3.5-flash-lite', thinking_level='low')

    def _code(self, exc):
        return None


class Controller:
    def __init__(self):
        self.calls = []

    def declarations(self):
        return [{'type': 'function', 'name': 'get_admin_overview',
                 'parameters': {'type': 'object', 'properties': {}}}]

    def execute(self, name, args):
        self.calls.append((name, args))
        return {'data': [{'siswa_aktif': 8}]}


def request_tool():
    return [ev('step.start', index=0, step={'type': 'thought', 'signature': 'opaque'}),
            ev('step.stop', index=0),
            ev('step.start', index=1, step={'type': 'function_call', 'id': 'c1',
                                          'name': 'get_admin_overview', 'arguments': {}}),
            ev('step.delta', index=1, delta={'type': 'arguments_delta', 'arguments': '{}'}),
            ev('step.stop', index=1),
            ev('interaction.completed', interaction=NS(status='requires_action'))]


def partial_text():
    return [ev('step.start', index=0, step={'type': 'model_output'}),
            ev('step.delta', index=0, delta={'type': 'text', 'text': 'Daftar terpo-'})]


def completed_unary(text='Jawaban lengkap.'):
    return NS(status='completed', steps=[NS(type='thought', signature='opaque2'),
              NS(type='model_output', content=[{'type': 'text', 'text': text}])])


def test_truncated_after_function_result_recovers_without_db_repeat():
    sdk = SDK([request_tool(), partial_text()], completed_unary())
    ctrl = Controller()
    events = list(DatabaseFunctionChat(Gemini(sdk), ctrl).stream([], 'Ringkasan siswa?', 's'))
    assert ctrl.calls == [('get_admin_overview', {})]
    assert [x.kind for x in events] == ['db_read_started', 'text_chunk', 'text_reset', 'text_chunk', 'completed']
    assert events[-2].payload == 'Jawaban lengkap.'
    assert events[-1].payload['content'] == 'Jawaban lengkap.'
    text = str(events[-1].payload['data']['steps'])
    assert 'Daftar terpo-' not in text
    assert all(c['store'] is False for c in sdk.calls)
    assert sdk.calls[-1]['stream'] is False


def test_truncated_plain_refusal_recovers_and_clears_partial():
    sdk = SDK([partial_text()], completed_unary('Tidak diizinkan membuka data pengguna lain.'))
    ctrl = Controller()
    events = list(DatabaseFunctionChat(Gemini(sdk), ctrl).stream([], 'data orang lain?', 's'))
    assert ctrl.calls == []
    assert [x.kind for x in events] == ['text_chunk', 'text_reset', 'text_chunk', 'completed']
    assert 'Tidak diizinkan' in events[-1].payload['content']


def test_bad_nonstream_recovery_still_denied():
    sdk = SDK([partial_text()], NS(status='failed', steps=[]))
    ctrl = Controller()
    events = list(DatabaseFunctionChat(Gemini(sdk), ctrl).stream([], 'test', 's'))
    assert ctrl.calls == []
    assert events[-1].kind == 'error'
    assert 'pemulihan' in str(events[-1].payload)
    assert not any(e.kind == 'completed' for e in events)


def test_enrollment_tool_is_scoped_to_student_only():
    assert 'get_my_enrollments' in AUTHORIZED['siswa']
    assert 'get_my_enrollments' not in AUTHORIZED['admin']
    assert 'get_my_enrollments' not in AUTHORIZED['tutor']
    assert 'e.student_id=%s' in QUERIES['get_my_enrollments']
    assert 'status_pendaftaran' in QUERIES['get_my_enrollments']
    assert 'status_pembayaran_terakhir' in QUERIES['get_my_enrollments']
    assert 'e.status::text AS status_pendaftaran' in QUERIES['get_my_invoices']
    assert 'e.status::text AS status_pendaftaran' in QUERIES['get_my_payments']
    assert 'get_my_enrollments' in DATABASE_INSTRUCTION


def test_today_context_uses_local_calendar():
    ctx = _current_day_hint()
    assert 'Tanggal lokal aplikasi:' in ctx
    assert 'hari ' in ctx
    assert 'Untuk pertanyaan' in ctx


def test_missing_function_stop_uses_unary_call_then_authorized_db():
    # First SSE ends while assembling the tool call. Complete unary response
    # produces a proper function_call, which still goes through our controller.
    partial = [ev('step.start', index=0, step={'type': 'thought', 'signature': 'opaque'}),
               ev('step.stop', index=0),
               ev('step.start', index=1, step={'type': 'function_call', 'id': 'c1',
                                             'name': 'get_admin_overview', 'arguments': {}}),
               ev('step.delta', index=1, delta={'type': 'arguments_delta', 'arguments': '{}'})]
    full_call = NS(status='requires_action', steps=[
        NS(type='thought', signature='opaque'),
        NS(type='function_call', id='c1', name='get_admin_overview', arguments={}),
    ])
    final = [ev('step.start', index=0, step={'type': 'model_output'}),
             ev('step.delta', index=0, delta={'type': 'text', 'text': 'Ada delapan siswa.'}),
             ev('step.stop', index=0, step={'type': 'model_output',
                                           'content': [{'type': 'text', 'text': 'Ada delapan siswa.'}]}),
             ev('interaction.completed', interaction=NS(status='completed'))]
    sdk = SDK([partial, final], full_call)
    ctrl = Controller()
    events = list(DatabaseFunctionChat(Gemini(sdk), ctrl).stream([], 'Jumlah siswa?', 's'))
    assert ctrl.calls == [('get_admin_overview', {})]
    assert events[-1].kind == 'completed'
    assert 'Ada delapan' in events[-1].payload['content']
    assert len(sdk.calls) == 3
