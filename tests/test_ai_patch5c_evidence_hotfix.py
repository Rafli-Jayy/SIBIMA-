"""Regression: Patch 5C analytics must count as verified DB evidence.

No database, network or Gemini API calls.
"""
from types import SimpleNamespace as NS
import json

from app.services.hybrid_evidence import HybridEvidence
from app.services.ai_db_chat import DatabaseFunctionChat
from app.services.gemini_client import GeminiClient, GeminiOptions

QUESTION = "Berapa jumlah akun siswa aktif dibandingkan pendaftaran aktif?"


def _event(name, **kwargs):
    return NS(event_type=name, **kwargs)


def _tool_stream():
    return [
        _event("step.start", index=0, step={"type": "function_call", "id": "call1", "name": "admin_enrollment_overview", "arguments": {}}),
        _event("step.stop", index=0),
        _event("interaction.completed", interaction=NS(status="requires_action")),
    ]


def _answer_stream():
    answer = "Ada 4 akun siswa aktif dan 8 pendaftaran aktif."
    return [
        _event("step.start", index=0, step={"type": "model_output"}),
        _event("step.delta", index=0, delta={"type": "text", "text": answer}),
        _event("step.stop", index=0, step={"type": "model_output", "content": [{"type": "text", "text": answer}]}),
        _event("interaction.completed", interaction=NS(status="completed")),
    ]


class _API:
    def __init__(self, streams):
        self.interactions = self
        self.streams = list(streams)
    def create(self, **kwargs):
        return iter(self.streams.pop(0))


class _Controller:
    def __init__(self):
        self.calls = []
    def declarations(self):
        return [{"type": "function", "name": "admin_enrollment_overview", "parameters": {"type": "object", "properties": {}}}]
    def execute(self, name, args):
        self.calls.append((name, args))
        return {"data": {"akun_siswa_aktif_global": 4, "jumlah_enrollment": 8}, "total_hasil": 8}


def test_new_admin_summary_is_accepted_by_evidence_guard():
    evidence = HybridEvidence(original_query=QUESTION)
    evidence.record("admin_enrollment_overview", {"data": {"akun_siswa_aktif_global": 4, "jumlah_enrollment": 8}})
    assert evidence.refusal(QUESTION) is None


def test_without_db_tool_still_rejects_guessed_count():
    assert HybridEvidence(original_query=QUESTION).refusal(QUESTION) is not None
    evidence = HybridEvidence(original_query=QUESTION)
    evidence.record("get_my_schedule", {"data": []})
    assert evidence.refusal(QUESTION) is not None


def test_actual_chat_flow_with_new_summary_tool_keeps_verified_answer():
    api = _API([_tool_stream(), _answer_stream()])
    gemini = GeminiClient(GeminiOptions(api_key="offline"), client=api)
    controller = _Controller()
    events = list(DatabaseFunctionChat(gemini, controller).stream([], QUESTION, "test"))
    assert len(controller.calls) == 1
    assert controller.calls[0][0] == "admin_enrollment_overview"
    assert events[-1].kind == "completed"
    assert "4 akun siswa aktif" in events[-1].payload["content"]
    assert "Saya belum berhasil memeriksa" not in events[-1].payload["content"]
