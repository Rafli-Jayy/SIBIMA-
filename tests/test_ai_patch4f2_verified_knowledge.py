"""Regression for source-mismatch bug and verified technical knowledge only.

No DB/network/embedding invocation. Uses actual doc loader + fake retrieval.
"""
import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from app.services.rag.relevance import is_relevant
from app.services.rag.document_loader import load_document, DocumentAccessError
from app.services.rag.rag_chat_tool import RAGKnowledgeTool
from app.services.hybrid_evidence import HybridEvidence, _DOCUMENT_REQUEST

ROOT=Path(__file__).resolve().parents[1]

DEMO = NS(document_id='demo-pembelajaran-python-rag-v1',
          title='DEMO RAG — Python Dasar (Bukan SOP Bimbel)',
          section='Contoh Variabel Python', source='demo variabel',
          text='Dalam Python variabel menyimpan nilai.',distance=0.05)
REAL = NS(document_id='sibima-flow-source-v4f1',
          title='Alur Sistem SIBIMA — Registrasi sampai Laporan',
          section='Tagihan bulanan dan tunggakan', source='flow dokumen',
          text='Tagihan bulanan dibuat melalui aksi Admin, periode awal bulan.',distance=0.22)

class Store:
    def __init__(self, hits):self.hits=hits
    def search(self,query,*,role,limit):return self.hits


def test_similarity_alone_cannot_cite_demo_for_sibima_flow():
    assert not is_relevant('Jelaskan flow SIBIMA secara lengkap', DEMO.document_id,DEMO.title,DEMO.section,DEMO.text)
    result=RAGKnowledgeTool(store=Store([DEMO])).search('Jelaskan flow SIBIMA secara lengkap',role='admin')
    assert result['status']=='no_matches' and result['hasil']==[]
    ledger=HybridEvidence(original_query='Jelaskan flow SIBIMA secara lengkap')
    ledger.record('search_knowledge_base', {'status':'ok','hasil':[{'judul':DEMO.title,'bagian':DEMO.section,'document_id':DEMO.document_id,'kutipan':DEMO.text}]})
    assert ledger.source_footer()==''
    assert ledger.refusal('Jelaskan flow SIBIMA secara lengkap') is not None
    assert _DOCUMENT_REQUEST.search('Jelaskan flow SIBIMA secara lengkap')


def test_real_flow_is_acceptable_for_system_flow():
    result=RAGKnowledgeTool(store=Store([DEMO,REAL])).search('Jelaskan flow SIBIMA secara lengkap',role='admin')
    assert result['status']=='ok' and result['jumlah']==1 and result['hasil'][0]['document_id']==REAL.document_id
    ledger=HybridEvidence(original_query='Jelaskan flow SIBIMA secara lengkap')
    ledger.record('search_knowledge_base',result)
    assert 'Alur Sistem SIBIMA' in ledger.source_footer() and 'DEMO' not in ledger.source_footer()


def test_demo_python_remains_usable_for_learning_question():
    result=RAGKnowledgeTool(store=Store([DEMO,REAL])).search('Apa itu variabel Python menurut modul?',role='siswa')
    assert result['status']=='ok' and [x['document_id'] for x in result['hasil']]==[DEMO.document_id]


def test_official_sop_is_not_substituted_by_verified_code():
    query='Menurut SOP resmi SIBIMA apakah ada denda keterlambatan?'
    result=RAGKnowledgeTool(store=Store([REAL,DEMO])).search(query,role='admin')
    assert result['status']=='no_matches'
    assert not is_relevant(query,REAL.document_id,REAL.title,REAL.section,REAL.text)


def test_live_counts_do_not_use_static_docs_as_actual_db():
    assert not is_relevant('Berapa jumlah siswa aktif di SIBIMA?',REAL.document_id,REAL.title,REAL.section,REAL.text)


def test_three_actual_approved_documents_are_admin_only():
    for name in ('01_ALUR_SISTEM_SIBIMA.md','02_ALUR_KODE_DAN_MODUL.md','03_STRUKTUR_DATABASE_18_TABEL.md'):
        source=ROOT/'knowledge/verified'/name
        if not source.is_file():
            pytest.skip('Verified knowledge deployment package not installed')
        doc=load_document(source,role='admin')
        assert doc.status=='DISETUJUI' and doc.indexing_allowed and doc.allowed_roles==frozenset({'admin'})
        with pytest.raises(DocumentAccessError):load_document(source,role='siswa')
        with pytest.raises(DocumentAccessError):load_document(source,role='tutor')


def test_explicitly_unapproved_sop_stays_blocked():
    path=ROOT/'knowledge/sources/SOP_Pendaftaran_Pembayaran_SIBIMA_DRAFT.md'
    if not path.is_file():pytest.skip('SOP draft not available')
    with pytest.raises(DocumentAccessError):load_document(path)


def test_manifest_matches_deployment_and_rejects_tampering(tmp_path):
    from tools.verify_sibima_knowledge import verify
    path=ROOT/'knowledge/verified/source_manifest.json'
    if not path.is_file():pytest.skip('manifest not installed')
    assert verify()[0]
    data=json.loads(path.read_text(encoding='utf-8'))
    data['source_sha256']['sql/schema.sql']='0'*64
    edited=tmp_path/'bad_manifest.json'
    edited.write_text(json.dumps(data),encoding='utf-8')
    ok,wrong=verify(project_root=ROOT,manifest_path=edited)
    assert not ok and 'sql/schema.sql' in wrong


def test_live_person_search_is_not_replaced_with_static_kb():
    assert not is_relevant('Zarkasi mengajar berapa kelas?',REAL.document_id,REAL.title,REAL.section,REAL.text)


def test_verified_retrieval_context_does_not_require_demo_python():
    assert is_relevant('Jelaskan alur pembayaran bulanan di SIBIMA',REAL.document_id,REAL.title,REAL.section,REAL.text)
    assert is_relevant('Jelaskan struktur database SIBIMA','sibima-schema-source-v4f1',
                       'Database SIBIMA — Kamus Tabel Relasi dan Status','Struktur database')
