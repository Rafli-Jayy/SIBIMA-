"""Release gate for SIBIMA-AI Hybrid RAG 4F.3.

Offline tests only. No Gemini API calls or actual PostgreSQL queries.
"""
import pytest

from app import session
from app.services.ai_tool_controller import (
    AIToolController, ROLE_TO_TOOLS, EXTRA_ROLE_TO_TOOLS,
)
from app.services.ai_access_messages import role_access_clarification
from app.services.hybrid_evidence import HybridEvidence
from app.services.rag.relevance import is_relevant
from app.services.rag.document_loader import load_document, DocumentAccessError
from app.services.ai_service import _trusted_session_hint
from tools.verify_sibima_knowledge import verify
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MemoryRepo:
    def __init__(self):
        self.calls = []

    def execute(self, uid, role, name, args):
        self.calls.append((uid, role, name, args))
        if name == "admin_find_users":
            return {"data": [{"user_id": 9, "nama_lengkap": "Tutor Contoh", "role": "tutor"}]}
        return {"data": []}


@pytest.fixture(autouse=True)
def isolate_session(monkeypatch):
    before = session.get_user()
    monkeypatch.setenv("SIBIMA_RAG_ENABLED", "false")
    yield
    session.set_user(before)


def principal(role):
    return {"id": 77, "role": role, "status": "aktif", "username": "tester", "nama_lengkap": "Admin Tester"}


@pytest.mark.parametrize("role", ("admin", "tutor", "siswa"))
def test_no_hidden_tools_when_rag_disabled(role):
    session.set_user(principal(role))
    controller = AIToolController(role, repo=MemoryRepo())
    expected = set(ROLE_TO_TOOLS[role]) | set(EXTRA_ROLE_TO_TOOLS[role])
    assert {tool["name"] for tool in controller.declarations()} == expected


@pytest.mark.parametrize("role", ("tutor", "siswa"))
def test_non_admin_cannot_use_admin_lookup_tools(role):
    session.set_user(principal(role))
    repo = MemoryRepo()
    controller = AIToolController(role, repo=repo)
    for name, args in (
        ("admin_find_users", {"query": "Zarkasi"}),
        ("admin_get_user_summary", {"user_id": 9}),
        ("admin_list_students_by_tutor", {"tutor_user_id": 9}),
    ):
        with pytest.raises(PermissionError):
            controller.execute(name, args)
    assert not repo.calls


def test_admin_tutor_id_must_be_discovered():
    session.set_user(principal("admin"))
    repo = MemoryRepo()
    controller = AIToolController("admin", repo=repo)
    with pytest.raises(PermissionError):
        controller.execute("admin_list_students_by_tutor", {"tutor_user_id": 9})
    assert not repo.calls
    controller.execute("admin_find_users", {"query": "Zarkasi"})
    controller.execute("admin_list_students_by_tutor", {"tutor_user_id": 9})
    assert len(repo.calls) == 2


def test_login_switch_blocks_old_controller():
    session.set_user(principal("admin"))
    repo = MemoryRepo()
    controller = AIToolController("admin", repo=repo)
    session.set_user({"id": 78, "role": "admin", "status": "aktif"})
    with pytest.raises(PermissionError):
        controller.execute("get_admin_overview", {})
    assert not repo.calls


def test_admin_schedule_access_message_is_specific():
    message = role_access_clarification("admin", "Tampilkan jadwal mengajar saya.")
    assert message is not None and "Admin" in message and "Tutor" in message


def test_identity_hint_excludes_sensitive_fields():
    hint = _trusted_session_hint({**principal("admin"), "email": "PRIVATE-EMAIL",
                                  "password_hash": "PRIVATE-HASH", "otp": "PRIVATE-OTP"})
    assert "Admin Tester" in hint
    assert all(v not in hint for v in ("PRIVATE-EMAIL", "PRIVATE-HASH", "PRIVATE-OTP"))


def test_demo_document_not_used_for_sibima_source_flow():
    assert not is_relevant(
        "Jelaskan flow kode pembayaran SIBIMA dan 18 tabelnya",
        "demo-pembelajaran-python-rag-v1", "DEMO RAG — Python Dasar",
        "Contoh Variabel Python", "variabel untuk menyimpan nilai")


def test_technical_document_not_official_policy():
    assert not is_relevant(
        "Menurut SOP resmi SIBIMA apa denda pembayaran?",
        "sibima-flow-source-v4f1", "Alur Sistem SIBIMA",
        "Pembayaran", "periode invoice bulanan")


def test_chatscreen_technical_question_is_supported():
    q = "Jelaskan bagaimana ChatScreen melakukan streaming dan reset konteks"
    assert is_relevant(q, "sibima-code-source-v4f1",
                       "Alur Kode dan Modul SIBIMA", "UI ChatScreen",
                       "ChatScreen melakukan streaming dan reset dengan /baru")


@pytest.mark.parametrize("role", ("tutor", "siswa"))
def test_technical_knowledge_denied_to_non_admin(role):
    path = ROOT / "knowledge/verified/02_ALUR_KODE_DAN_MODUL.md"
    with pytest.raises(DocumentAccessError):
        load_document(path, role=role)


def test_technical_knowledge_approved_for_admin():
    doc = load_document(ROOT / "knowledge/verified/02_ALUR_KODE_DAN_MODUL.md", role="admin")
    assert doc.status == "DISETUJUI"
    assert doc.indexing_allowed
    assert doc.allowed_roles == frozenset({"admin"})


def test_manifest_matches_project_source():
    ok, mismatches = verify()
    assert ok, mismatches


def test_document_attribution_not_from_demo_for_system_flow():
    q = "Jelaskan flow sistem pendaftaran dan pembayaran SIBIMA"
    ev = HybridEvidence(original_query=q)
    ev.record("search_knowledge_base", {"status": "ok", "hasil": [
        {"judul": "DEMO RAG Python Dasar", "document_id": "demo-pembelajaran-python-rag-v1",
         "bagian": "Perulangan Python", "kutipan": "contoh for x in ..."}
    ]})
    assert not ev.documents
    assert not ev.source_footer()
