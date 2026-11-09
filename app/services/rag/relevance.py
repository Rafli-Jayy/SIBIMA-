"""Deterministic relevance gate for RAG source attribution.

This is a *conservative* supplement to vector similarity and source ACLs:
- Chroma nearest-neighbor alone cannot prove topical relevance;
- DEMO learning sources must not substantiate SIBIMA workflows;
- source code documentation must not masquerade as an official SOP;
- source filtering never grants role access or overrides the original document loader.
"""
from __future__ import annotations
import re

_LEARNING = re.compile(
    r"\b(?:variabel|variable|perulangan|looping|latihan\s+python|"
    r"belajar\s+python|materi\s+python|modul\s+python|"
    r"contoh\s+(?:fungsi|kode)\s+python|fungsi\s+python|"
    r"pemrograman\s+(?:dasar|python)|list\s+python|cara\s+menyimpan\s+nilai|"
    r"python.{0,50}\bmateri\b|materi.{0,50}\bpython\b)\b", re.I)
_SYSTEM = re.compile(
    r"\b(?:sibima|bimbel|pendaftaran|enrollment|invoice|tagihan|"
    r"pembayaran|absensi|kehadiran|tutor|kelas|admin|otp|"
    r"postgre(?:sql)?|database|skema|tabel|relasi|"
    r"source\s+code|alur\s+kode|flow\s+coding)\b", re.I)
# Verified technical questions can mention concrete Python symbols without
# saying "SIBIMA" or "coding". Keep these signals narrowly scoped to code docs.
_CODE_SYMBOL = re.compile(
    r"\b(?:chatscreen|chat_screen|streaming_renderer|response_renderer|"
    r"databasefunctionchat|aiservice|aitoolcontroller|hybridevidence|"
    r"ai_read_repo|ai_service|ai_db_chat|geminiclient|source_manifest|"
    r"function.calling|text_reset|reset\s*\(\s*\)|"
    r"reset\s+(?:konteks|percakapan|chat)|\/baru|"
    r"streaming|event\s+(?:step|gemini)|session\.get_user)\b", re.I)
_SYMBOL_TO_ANCHOR = {
    "chatscreen": ("chatscreen", "chat_screen"),
    "chat_screen": ("chatscreen", "chat_screen"),
    "databasefunctionchat": ("databasefunctionchat", "ai_db_chat"),
    "ai_read_repo": ("ai_read_repo",),
    "response_renderer": ("response_renderer",),
    "streaming_renderer": ("streaming_renderer",),
    "aitoolcontroller": ("aitoolcontroller", "ai_tool_controller"),
    "hybridevidence": ("hybridevidence", "hybrid_evidence"),
}

_OFFICIAL = re.compile(r"\b(?:sop\s+resmi|kebijakan\s+resmi|aturan\s+resmi|denda\s+resmi|sop\s+sibima)\b", re.I)
_LIVE_METRIC = re.compile(r"\b(?:berapa|jumlah|total|siapa|daftar|tampilkan)\b.{0,65}\b(?:siswa\s+aktif|tutor|tagihan\s+saya|nilai\s+saya|jadwal\s+saya|pendaftaran\s+saya)\b", re.I)
_OPERATIONS = re.compile(r"\b(?:flow|alur|cara\s+kerja|mekanisme|proses|"
    r"logika|aturan|ketentuan|tahapan|struktur|arsitektur|cara\s+dibuat|"
    r"perbulan|bulanan|jatuh\s+tempo|database|skema|tabel|relasi|modul|coding|kode|source)\b", re.I)
_STOP = frozenset('apa apakah bagaimana jelaskan tampilkan lihat dari dalam untuk dengan yang pada atas dan atau siapa saya kami kamu itu ini bisa ada sebagai secara semua berdasarkan sumber dokumen tersedia di ke menurut sebuah sistem sibima informasi milik sekarang saat data tentang karena mana jadi bro dong lalu tolong'.split())


def _tokens(s: str) -> set[str]:
    """Small lexical safety fallback; not a semantic relevance guarantee."""
    return {v for v in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", s.casefold())
            if v not in _STOP}


def is_relevant(query: str, document_id: str, title: str,
                section: str = "", excerpt: str = "") -> bool:
    """False means source MUST NOT be passed to Gemini or cited as evidence.

    The known SIBIMA source categories are deliberately explicit. Unknown docs
    require meaningful lexical overlap; vector distance alone is insufficient.
    """
    if not isinstance(query, str) or not query.strip():
        return False
    q = query.casefold()
    name = f"{document_id} {title}".casefold()
    is_demo = ('demo' in name or document_id.startswith('demo-'))
    is_technical = document_id.startswith(('sibima-flow-', 'sibima-code-', 'sibima-schema-'))

    if _OFFICIAL.search(q):
        # Technical snapshots and tutorials are not official SOP/policy.
        return not (is_demo or is_technical) and bool(re.search(r"\b(?:sop|kebijakan|peraturan)\b", name))

    if is_demo:
        # The word 'Python' alone is insufficient: SIBIMA itself is written in Python.
        learning_signal = bool(_LEARNING.search(q)) or q.strip(' ?.!,' ).casefold() == 'python'
        return learning_signal and not (
            _OPERATIONS.search(q) and _SYSTEM.search(q) and not re.search(r"\b(?:materi|modul|belajar|latihan)\b", q))

    if is_technical:
        code_symbols = _CODE_SYMBOL.search(q)
        if _LIVE_METRIC.search(q) and not _OPERATIONS.search(q) and not code_symbols:
            return False
        # A technical symbol question needs a code-level source, not merely a
        # general SIBIMA flow paragraph with overlapping terms.
        if code_symbols and document_id.startswith('sibima-code-'):
            context = f"{section} {excerpt}".casefold()
            for symbol, aliases in _SYMBOL_TO_ANCHOR.items():
                if re.search(r"\b" + re.escape(symbol) + r"\b", q):
                    if not any(alias in context for alias in aliases):
                        return False
            return True
        if code_symbols and not _OPERATIONS.search(q):
            return False
        # Questions about an operational system/code/schema go to verified
        # technical docs, not general Python learning examples.
        if _LEARNING.search(q) and not _SYSTEM.search(q):
            return False
        if not _OPERATIONS.search(q) or not (_SYSTEM.search(q) or 'sibima' in name):
            return False
        if document_id.startswith('sibima-schema-'):
            return bool(re.search(r"\b(?:database|postgre(?:sql)?|skema|tabel|relasi|erd|foreign key|primary key|kolom|trigger|view|enum)\b",q))
        if document_id.startswith('sibima-code-'):
            return bool(re.search(r"\b(?:coding|kode|source|repository|service|fungsi|function|modul|query|python|implementasi)\b",q))
        return True

    # For future documents (new topics/IDs), require topical overlap. More
    # permissive similarity-only citation is intentionally not supported.
    query_terms = _tokens(query)
    source_terms = _tokens(f"{title} {section} {excerpt[:800]}")
    overlap = query_terms & source_terms
    return bool(overlap) and (len(overlap) >= 2 or len(query_terms) <= 3)
