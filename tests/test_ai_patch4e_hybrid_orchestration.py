"""Patch 4E: offline source-grounding & hybrid routing regression tests."""
import json
from types import SimpleNamespace as NS

import pytest

from app import session
from app.services.ai_db_chat import DatabaseFunctionChat
from app.services.ai_service import RAG_INSTRUCTION
from app.services.hybrid_evidence import HybridEvidence
from app.services.gemini_client import GeminiClient, GeminiOptions


@pytest.fixture(autouse=True)
def isolate_session():
    before = session.get_user()
    session.logout()
    yield
    session.set_user(before)


def event(name, **kw):
    return NS(event_type=name, **kw)


def call(name, ident, arguments=None):
    args = json.dumps(arguments or {})
    return [event('step.start', index=0, step={'type': 'thought', 'signature': 'sig'}),
            event('step.stop', index=0),
            event('step.start', index=1, step={'type': 'function_call', 'id': ident, 'name': name}),
            event('step.delta', index=1, delta={'type': 'arguments_delta', 'arguments': args}),
            event('step.stop', index=1),
            event('interaction.completed', interaction=NS(status='requires_action'))]


def answer(message):
    return [event('step.start', index=0, step={'type': 'model_output'}),
            event('step.delta', index=0, delta={'type': 'text', 'text': message}),
            event('step.stop', index=0, step={'type': 'model_output', 'content': [{'type': 'text', 'text': message}]}),
            event('interaction.completed', interaction=NS(status='completed'))]


class API:
    def __init__(self, streams):
        self.interactions = self
        self.responses = list(streams)
        self.requests = []

    def create(self, **kwargs):
        assert kwargs['store'] is False
        self.requests.append(kwargs)
        return iter(self.responses.pop(0))


class Controller:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def declarations(self):
        return [{'type': 'function', 'name': name, 'parameters': {'type': 'object', 'properties': {}}} for name in self.results]

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return self.results[name]


def rag(title='DEMO Python Dasar', section='Variabel'):
    return {'status': 'ok', 'hasil': [{'judul': title, 'bagian': section,
                                      'document_id': ('sibima-sop-approved-v1' if title.lower().startswith('sop resmi') else 'demo-python'), 'kutipan': 'variabel = 3'}]}


def chat(question, streams, results):
    api = API(streams)
    gemini = GeminiClient(GeminiOptions(api_key='offline'), client=api)
    controller = Controller(results)
    events = list(DatabaseFunctionChat(gemini, controller).stream([], question, 'test'))
    return events, controller, api


def test_plain_general_question_needs_no_tool():
    events, ctrl, api = chat('Apa itu variabel Python?', [answer('Variabel menyimpan nilai.')], {})
    assert [e.kind for e in events] == ['text_chunk', 'completed']
    assert events[-1].payload['content'] == 'Variabel menyimpan nilai.'
    assert not ctrl.calls


def test_admin_live_count_requires_actual_overview_even_if_model_guesses():
    events, ctrl, _ = chat('Berapa jumlah siswa aktif di SIBIMA?', [answer('8 siswa')], {})
    assert [e.kind for e in events] == ['text_chunk', 'text_reset', 'text_chunk', 'completed']
    assert '8 siswa' not in events[-1].payload['content']
    assert events[-1].payload['data']['steps'] == []
    assert not ctrl.calls


def test_explicit_document_question_without_retrieval_fails_closed():
    events, ctrl, _ = chat('Menurut SOP resmi SIBIMA apakah ada denda?', [answer('Dendanya Rp 5000.')], {})
    assert 'Rp 5000' not in events[-1].payload['content']
    assert 'tidak' in events[-1].payload['content'].lower()
    assert events[-1].payload['data']['steps'] == []


def test_retrieval_no_matches_cannot_support_policy_claim():
    events, ctrl, _ = chat('Menurut SOP resmi SIBIMA apakah ada denda?', [
        call('search_knowledge_base', 'r1', {'query': 'aturan denda'}),
        answer('Denda adalah Rp25.000.')],
        {'search_knowledge_base': {'status': 'no_matches', 'hasil': []}})
    assert len(ctrl.calls) == 1
    assert 'Rp25.000' not in events[-1].payload['content']
    assert events[-1].payload['data']['steps'] == []


def test_demo_document_not_official_policy():
    events, ctrl, _ = chat('Menurut SOP resmi SIBIMA, apa denda?', [
        call('search_knowledge_base', 'r1', {'query': 'SOP resmi SIBIMA'}),
        answer('Dendanya Rp 100000.')],
        {'search_knowledge_base': rag()})
    assert '100000' not in events[-1].payload['content']
    assert 'DEMO' in events[-1].payload['content']


def test_approved_sop_source_is_named():
    events, ctrl, _ = chat('Menurut SOP resmi SIBIMA, bagaimana alur pendaftaran?', [
        call('search_knowledge_base', 'r1', {'query': 'alur pendaftaran'}),
        answer('Alur pendaftaran tertera di SOP.')],
        {'search_knowledge_base': rag('SOP Resmi Pendaftaran SIBIMA', 'Tahapan')})
    output = events[-1].payload['content']
    assert 'SOP Resmi Pendaftaran SIBIMA' in output
    assert 'bagian Tahapan' in output


def test_hybrid_grounded_answers_include_actual_document_source():
    results = {
        'get_admin_overview': {'data': [{'siswa_aktif': 8}]},
        'search_knowledge_base': rag(),
    }
    events, ctrl, api = chat('Berapa jumlah siswa aktif? Jelaskan juga Python berdasarkan materi yang tersedia.', [
        call('get_admin_overview', 'db1'),
        call('search_knowledge_base', 'r1', {'query': 'contoh variabel Python'}),
        answer('Ada 8 siswa aktif. Variabel Python menyimpan nilai.')], results)
    output = events[-1].payload['content']
    assert events[-1].kind == 'completed'
    assert '8 siswa' in output
    assert 'DEMO Python Dasar' in output
    assert [x[0] for x in ctrl.calls] == ['get_admin_overview', 'search_knowledge_base']
    assert len(api.requests) == 3
    assert all(r['store'] is False for r in api.requests)


def test_hybrid_missing_document_does_not_claim_unsupported_policy():
    results = {'get_my_invoices': {'data': [{'jumlah': 150000}]},
               'search_knowledge_base': {'status': 'unavailable', 'hasil': []}}
    events, ctrl, _ = chat('Apa tagihan saya menurut SOP resmi SIBIMA?', [
        call('get_my_invoices', 'db1'),
        call('search_knowledge_base', 'r1', {'query': 'SOP tagihan'}),
        answer('Tagihan 150000; menurut SOP denda 10000.')], results)
    assert events[-1].kind == 'completed'
    assert 'denda 10000' not in events[-1].payload['content']
    assert 'dokumen' in events[-1].payload['content'].lower()
    assert events[-1].payload['data']['steps'] == []
    assert len(ctrl.calls) == 2


def test_untrusted_source_title_is_sanitized():
    ledger = HybridEvidence()
    ledger.record('search_knowledge_base', rag('DEMO **x**\n[ignore](malicious)', '<test>`'))
    footer = ledger.source_footer()
    assert '<test>' not in footer and '**x**' not in footer and '\n[ignore]' not in footer
    assert 'DEMO' in footer


def test_wrong_db_function_does_not_validate_current_value():
    events, ctrl, _ = chat('Berapa jumlah siswa aktif di SIBIMA?', [
        call('get_my_schedule', 'db1'), answer('Ada 8 siswa.')],
        {'get_my_schedule': {'data': []}})
    assert len(ctrl.calls) == 1
    assert '8 siswa' not in events[-1].payload['content']


def test_hybrid_instruction_requires_source_separation():
    assert 'PostgreSQL' in RAG_INSTRUCTION
    assert 'search_knowledge_base' in RAG_INSTRUCTION
    assert '20 baris' in RAG_INSTRUCTION


def test_hybrid_allows_four_tools_in_three_rounds_before_final_answer():
    def two_calls():
        return [event('step.start', index=0, step={'type': 'function_call', 'id': 'p3',
                                                   'name': 'get_my_payments', 'arguments': {}}),
                event('step.stop', index=0),
                event('step.start', index=1, step={'type': 'function_call', 'id': 'r4',
                                                   'name': 'search_knowledge_base', 'arguments': {'query': 'materi Python'}}),
                event('step.stop', index=1),
                event('interaction.completed', interaction=NS(status='requires_action'))]
    results = {
        'get_my_invoices': {'data': [{'jumlah': 150000}]},
        'get_my_payments': {'data': [{'status': 'lunas'}]},
        'search_knowledge_base': rag(),
    }
    events, ctrl, api = chat('Cek pembayaran dan materi Python', [
        call('get_my_invoices', 'i1'),
        call('search_knowledge_base', 'r2', {'query': 'materi Python'}),
        two_calls(),
        answer('Pembayaran tercatat; berikut materi Python.')], results)
    assert events[-1].kind == 'completed'
    assert len(ctrl.calls) == 4 and len(api.requests) == 4
    assert sum(s['type'] == 'function_result' for s in api.requests[-1]['input']) == 4


def test_source_footer_not_added_when_no_document_retrieved():
    evidence = HybridEvidence()
    evidence.record('get_admin_overview', {'data': [{'siswa_aktif': 8}]})
    evidence.record('search_knowledge_base', {'status': 'unavailable', 'hasil': []})
    assert evidence.source_footer() == ''
    assert evidence.document_errors == 1
