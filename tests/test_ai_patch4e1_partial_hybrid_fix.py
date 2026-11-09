"""Patch 4E.1: prevent losing verified DB facts when optional RAG evidence is missing.

Offline only; does not contact Google, read PostgreSQL, or index a document.
"""
from types import SimpleNamespace as NS
import json

from app.services.ai_db_chat import DatabaseFunctionChat, _document_search_query
from app.services.gemini_client import GeminiClient, GeminiOptions
from app.services.hybrid_evidence import HybridEvidence


QUESTION = ('Tampilkan jadwal mengajar saya, lalu jelaskan materi variabel Python '
            'berdasarkan modul yang tersedia.')
SCHEDULE = {
    'data': [
        {'program': 'Python', 'hari': 'Jumat', 'jam_mulai': '18:00',
         'jam_selesai': '20:00', 'ruang': 'Ruang Raja Ampat A1'},
        {'program': 'Bahasa Javascript', 'hari': 'Selasa', 'jam_mulai': '18:00',
         'jam_selesai': '20:00', 'ruang': 'Ruang Raja Ampat A2'},
    ],
    'jumlah_ditampilkan': 2,
}
HITS = {'status': 'ok', 'hasil': [
    {'judul': 'DEMO Python Dasar', 'bagian': 'Contoh Variabel Python',
     'document_id': 'demo-python',
     'kutipan': 'Variabel Python menyimpan nilai. Contoh: nama = "SIBIMA".'}
]}


def ev(kind, **data):
    return NS(event_type=kind, **data)


def call(name, identity):
    return [
        ev('step.start', index=0, step={'type': 'function_call', 'id': identity,
                                       'name': name, 'arguments': {}}),
        ev('step.stop', index=0),
        ev('interaction.completed', interaction=NS(status='requires_action')),
    ]


def answer(text):
    return [
        ev('step.start', index=0, step={'type': 'model_output'}),
        ev('step.delta', index=0, delta={'type': 'text', 'text': text}),
        ev('step.stop', index=0, step={'type': 'model_output',
                                     'content': [{'type': 'text', 'text': text}]}),
        ev('interaction.completed', interaction=NS(status='completed')),
    ]


class FakeAPI:
    def __init__(self, streams):
        self.interactions = self
        self.streams = list(streams)
        self.calls = []

    def create(self, **kwargs):
        assert kwargs['store'] is False
        self.calls.append(kwargs)
        return iter(self.streams.pop(0))


class FakeController:
    def __init__(self, rag_result=HITS, enabled=True):
        self.rag_result = rag_result
        self.enabled = enabled
        self.calls = []

    def declarations(self):
        names = ['get_my_teaching_schedule']
        if self.enabled:
            names.append('search_knowledge_base')
        return [{'name': name} for name in names]

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        if name == 'get_my_teaching_schedule':
            assert arguments == {}
            return SCHEDULE
        if name == 'search_knowledge_base' and self.enabled:
            assert len(arguments['query']) <= 500
            return self.rag_result
        raise PermissionError('Tool is unavailable')


def run(streams, rag_result=HITS, enabled=True):
    sdk = FakeAPI(streams)
    ctrl = FakeController(rag_result, enabled)
    model = GeminiClient(GeminiOptions(api_key='test'), client=sdk)
    events = list(DatabaseFunctionChat(model, ctrl).stream([], QUESTION, 'test'))
    return events, ctrl, sdk


def test_tutor_rag_skipped_once_recovers_and_preserves_db_evidence():
    events, ctrl, sdk = run([
        call('get_my_teaching_schedule', 'db1'),
        answer('Jadwal Jumat Python dan materi variabel berasal dari Gemini (belum dicek).'),
        answer('Jadwal Python Jumat 18:00–20:00. Variabel Python menyimpan nilai.'),
    ])
    assert [e.kind for e in events] == [
        'db_read_started', 'text_chunk', 'text_reset', 'text_chunk', 'completed'
    ]
    final = events[-1].payload['content']
    assert 'Jadwal Python Jumat' in final
    assert 'DEMO Python Dasar' in final
    assert 'belum dicek' not in final
    assert [name for name, _ in ctrl.calls] == [
        'get_my_teaching_schedule', 'search_knowledge_base'
    ]
    assert len(sdk.calls) == 3
    # Direct retrieval context is transient, not saved as a user prompt in memory.
    history_steps = events[-1].payload['data']['steps']
    assert not any('Dokumen yang baru ditemukan' in json.dumps(x, ensure_ascii=False)
                   for x in history_steps)
    assert sdk.calls[-1]['input'][-1]['type'] == 'user_input'
    assert 'DEMO Python Dasar' in json.dumps(sdk.calls[-1]['input'][-1], ensure_ascii=False)


def test_no_matching_document_keeps_actual_tutor_schedule_instead_of_erasing():
    events, ctrl, sdk = run([
        call('get_my_teaching_schedule', 'db1'),
        answer('Jawaban parsial yang belum diverifikasi.'),
    ], rag_result={'status': 'no_matches', 'hasil': []})
    assert [e.kind for e in events] == [
        'db_read_started', 'text_chunk', 'text_reset', 'text_chunk', 'completed'
    ]
    final = events[-1].payload['content']
    assert 'Python' in final and 'Jumat' in final and '18:00' in final
    assert 'Bahasa Javascript' in final and 'Selasa' in final
    assert 'materi/dokumen belum' in final
    assert 'Jawaban parsial' not in final
    assert len(sdk.calls) == 2
    assert events[-1].payload['data']['steps'] == []


def test_rag_disabled_still_preserves_verified_schedule_without_extra_call():
    events, ctrl, sdk = run([
        call('get_my_teaching_schedule', 'db1'),
        answer('Materi variabel tersedia, katanya.'),
    ], enabled=False)
    assert len(sdk.calls) == 2
    assert [n for n, _ in ctrl.calls] == ['get_my_teaching_schedule']
    final = events[-1].payload['content']
    assert 'Jumat' in final
    assert 'Materi variabel tersedia' not in final


def test_unsafe_text_from_database_is_not_markdown_control_or_unbounded():
    evidence = HybridEvidence()
    evidence.record('get_my_teaching_schedule', {
        'data': [{'program': '**<script>malicious</script>**' + 'A'*200,
                  'hari': 'Jumat', 'jam_mulai': '18:00', 'jam_selesai': '20:00',
                  'ruang': '`[fake]`'}]
    })
    output = evidence.database_part_when_document_missing(QUESTION)
    assert output is not None and '<script>' not in output and '**' not in output
    assert '`' not in output and len(output) < 500


def test_model_question_document_query_uses_modul_clause():
    result = _document_search_query(QUESTION)
    assert result.startswith('jelaskan materi variabel Python')
    assert 'Tampilkan jadwal' not in result


def test_recovery_context_remains_in_sdk_input_if_model_calls_another_tool():
    events, ctrl, sdk = run([
        call('get_my_teaching_schedule', 'db1'),
        answer('Belum mengambil dokumen.'),
        call('get_my_teaching_schedule', 'db2'),
        answer('Jadwal Tutor dan variabel Python sudah dirangkum dari sumber.'),
    ])
    assert events[-1].kind == 'completed'
    assert len(sdk.calls) == 4
    all_input = sdk.calls[-1]['input']
    assert any(x.get('type') == 'user_input' and
               'Dokumen yang baru ditemukan' in json.dumps(x, ensure_ascii=False)
               for x in all_input)
    assert sum(x.get('type') == 'function_result' for x in all_input) == 2
    # Ephemeral data is intentionally absent from persistent chat steps.
    assert not any('Dokumen yang baru ditemukan' in json.dumps(x, ensure_ascii=False)
                   for x in events[-1].payload['data']['steps'])
