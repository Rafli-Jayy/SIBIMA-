"""Offline tests for Patch 4B; no PostgreSQL / Gemini / vector store involved."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.services.rag import (
    DocumentAccessError, DocumentFormatError, chunk_document, load_document,
)

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "knowledge/sources/SOP_Pendaftaran_Pembayaran_SIBIMA_DRAFT.md"


def _meta(**overrides):
    meta = dict(
        document_id="demo-sop-v1",
        judul="SOP Demo",
        versi="1.0",
        status="DISETUJUI",
        role_pembaca=["admin", "siswa"],
        rag_indexing_allowed=True,
    )
    meta.update(overrides)
    return meta


def _write_txt(tmp_path, body="Aturan pendaftaran dan tagihan SIBIMA.", **overrides):
    file = tmp_path / "aturan.txt"
    file.write_text(body, encoding="utf-8")
    (tmp_path / "aturan.txt.meta.json").write_text(json.dumps(_meta(**overrides)), encoding="utf-8")
    return file


def test_draft_explicitly_blocked_for_normal_retrieval():
    with pytest.raises(DocumentAccessError, match="belum disetujui"):
        load_document(DRAFT, role="siswa")


def test_draft_only_preview_and_chunk_is_also_guarded():
    doc = load_document(DRAFT, preview=True, role="siswa")
    assert doc.status == "DRAF_BELUM_DISETUJUI"
    assert doc.indexing_allowed is False
    with pytest.raises(DocumentAccessError):
        chunk_document(doc, role="siswa")
    pieces = chunk_document(doc, preview=True, role="siswa", max_chars=650)
    assert len(pieces) >= 10
    assert all(len(p.text) <= 650 for p in pieces)
    assert all(p.document_id == doc.document_id for p in pieces)
    assert all(p.allowed_roles == frozenset({"admin", "tutor", "siswa"}) for p in pieces)
    assert all(not p.text.lstrip().startswith("---") for p in pieces)
    assert any("Arti status pendaftaran" in p.section for p in pieces)
    assert any("Tagihan bulanan" in p.section for p in pieces)


def test_stable_chunk_ids_and_source_labels():
    doc = load_document(DRAFT, preview=True)
    first = chunk_document(doc, preview=True)
    second = chunk_document(doc, preview=True)
    assert [p.chunk_id for p in first] == [p.chunk_id for p in second]
    assert len({p.chunk_id for p in first}) == len(first)
    assert all(doc.title in p.source_label for p in first)


def test_approved_txt_with_sidecar_allowed_only_by_role(tmp_path):
    file = _write_txt(tmp_path)
    doc = load_document(file, role="admin")
    chunks = chunk_document(doc, role="siswa", max_chars=400)
    assert chunks and "pendaftaran" in chunks[0].text
    with pytest.raises(DocumentAccessError, match="Role"):
        load_document(file, role="tutor")
    with pytest.raises(DocumentAccessError, match="Role"):
        chunk_document(doc, role="tutor")


def test_reject_unapproved_txt_and_inconsistent_metadata(tmp_path):
    file = _write_txt(tmp_path, status="DRAF_BELUM_DISETUJUI", rag_indexing_allowed=False)
    with pytest.raises(DocumentAccessError):
        load_document(file)
    doc = load_document(file, preview=True)
    with pytest.raises(DocumentAccessError):
        chunk_document(doc)
    _write_txt(tmp_path, status="DRAF_BELUM_DISETUJUI", rag_indexing_allowed=True)
    with pytest.raises(DocumentFormatError):
        load_document(file, preview=True)


def test_reject_missing_sidecar(tmp_path):
    f = tmp_path / "no_sidecar.txt"
    f.write_text("Important", encoding="utf-8")
    with pytest.raises(DocumentFormatError, match="sidecar"):
        load_document(f)


def test_reject_unknown_roles_and_missing_required_metadata(tmp_path):
    file = _write_txt(tmp_path, role_pembaca=["unknown"])
    with pytest.raises(DocumentFormatError, match="Role tidak dikenal"):
        load_document(file)
    f = tmp_path / "aturan.txt.meta.json"
    f.write_text(json.dumps({"document_id": "demo-sop-v1"}), encoding="utf-8")
    with pytest.raises(DocumentFormatError, match="tidak lengkap"):
        load_document(file)


def test_reject_unsupported_extension_and_symlink(tmp_path):
    p = tmp_path / "bad.docx"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(DocumentFormatError, match="Hanya"):
        load_document(p)
    target = _write_txt(tmp_path)
    symlink = tmp_path / "alias.txt"
    try:
        symlink.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink permissions unavailable on Windows")
    with pytest.raises(DocumentFormatError):
        load_document(symlink)


def test_section_chunks_keep_all_unique_words(tmp_path):
    words = [f"kata{i:04d}" for i in range(150)]
    body = " ".join(words)
    file = _write_txt(tmp_path, body=body)
    doc = load_document(file)
    chunks = chunk_document(doc, max_chars=320, overlap_chars=40)
    assert len(chunks) > 2
    assert all(len(p.text) <= 320 for p in chunks)
    joined = " ".join(c.text for c in chunks)
    for word in words:
        assert word in joined


def test_preview_cli_can_read_draft_but_normal_refuses():
    script = ROOT / "tools/rag_inspect.py"
    refused = subprocess.run([sys.executable, str(script), str(DRAFT)], text=True, capture_output=True)
    assert refused.returncode == 2
    assert "DITOLAK" in refused.stderr
    preview = subprocess.run([sys.executable, str(script), str(DRAFT), "--preview"], text=True, capture_output=True)
    assert preview.returncode == 0, preview.stderr
    assert "Indexing : TIDAK BOLEH" in preview.stdout
    assert "MODE PREVIEW" in preview.stdout


def test_pdf_with_sidecar_and_page_provenance(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    filepath = tmp_path / "materi.pdf"
    with pymupdf.open() as pdf:
        p1 = pdf.new_page()
        p1.insert_text((72, 72), "Kebijakan pendaftaran dan pembayaran")
        p2 = pdf.new_page()
        p2.insert_text((72, 72), "Penjelasan absensi")
        pdf.save(filepath)
    (tmp_path / "materi.pdf.meta.json").write_text(json.dumps(_meta()), encoding="utf-8")
    doc = load_document(filepath, role="siswa")
    chunks = chunk_document(doc, role="siswa")
    assert [c.page for c in chunks] == [1, 2]
    assert "halaman 2" in chunks[1].source_label


def test_pdf_without_text_rejected(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    filepath = tmp_path / "kosong.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(filepath)
    (tmp_path / "kosong.pdf.meta.json").write_text(json.dumps(_meta()), encoding="utf-8")
    with pytest.raises(DocumentFormatError, match="tidak memiliki teks"):
        load_document(filepath)
