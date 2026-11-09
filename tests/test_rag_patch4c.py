"""Patch4C offline tests: no Google, PostgreSQL or Chroma install necessary."""
from __future__ import annotations
import json
from math import sqrt
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.rag.document_loader import DocumentAccessError
from app.services.rag.embedding_client import EmbeddingError, normalize
from app.services.rag.vector_store import KnowledgeVectorStore, IndexCompatibilityError, IndexAccessError


class FakeEmbedder:
    dimension = 4
    identity = "test-embeddings-4"
    doc_calls = 0
    query_calls = 0

    def _embed(self, text):
        low = text.lower()
        v = [0.1, 0.1, 0.1, 0.1]
        for keyword, i in [("python", 0), ("tagihan", 1), ("jadwal", 2), ("absensi", 3)]:
            v[i] += low.count(keyword) * 4
        return normalize(v, self.dimension)

    def embed_documents(self, texts):
        self.doc_calls += 1
        return [self._embed(t) for t in texts]

    def embed_query(self, text):
        self.query_calls += 1
        return self._embed(text)


class FakeCollection:
    def __init__(self, name, metadata):
        self.name = name
        self.metadata = metadata
        self.rows = {}

    def get(self, *, where=None, include=None):
        rows = [(i, r) for i, r in self.rows.items() if not where or all(r[2].get(k)==v for k,v in where.items())]
        return {"ids": [i for i,_ in rows], "metadatas": [r[2] for _,r in rows]}

    def upsert(self, *, ids, documents, embeddings, metadatas):
        for i, d, e, m in zip(ids, documents, embeddings, metadatas):
            self.rows[i] = (d, e, m)

    def delete(self, *, ids):
        for i in ids:
            self.rows.pop(i, None)

    def count(self):
        return len(self.rows)

    def query(self, *, query_embeddings, n_results, where, include):
        q = query_embeddings[0]
        rows = []
        for i, (doc, emb, meta) in self.rows.items():
            if not all(meta.get(k) == v for k,v in where.items()):
                continue
            # Cosine distance for normalized vectors
            dot = sum(x*y for x,y in zip(q,emb))
            rows.append((1-dot, i, doc, meta))
        rows.sort(key=lambda x:x[0])
        rows = rows[:n_results]
        return {"ids": [[r[1] for r in rows]], "documents": [[r[2] for r in rows]],
                "metadatas": [[r[3] for r in rows]], "distances": [[r[0] for r in rows]]}


class FakeClient:
    def __init__(self):
        self.collection = None

    def get_or_create_collection(self, *, name, metadata, configuration, embedding_function):
        assert configuration["hnsw"]["space"] == "cosine"
        assert embedding_function is None
        if self.collection is None:
            self.collection = FakeCollection(name, metadata)
        return self.collection

    def get_collection(self, *, name, embedding_function):
        if self.collection is None:
            raise ValueError("collection missing")
        return self.collection


def make_doc(root: Path, *, status="DISETUJUI", allowed=("siswa", "admin"), doc_id="demo-kb-1"):
    file = root / "approved.txt"
    file.write_text("Materi Python: variabel dan fungsi.\n\nMateri jadwal kelas Python tersedia di aplikasi.", encoding="utf-8")
    meta = {"document_id": doc_id, "judul": "Demo KB", "versi":"1.0",
            "status":status, "role_pembaca":list(allowed),
            "rag_indexing_allowed":status=="DISETUJUI"}
    (root / "approved.txt.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return file


def build_store(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    f = make_doc(root)
    embed = FakeEmbedder()
    fake = FakeClient()
    store = KnowledgeVectorStore(source_root=root, index_dir=tmp_path/"index", embedder=embed, client=fake)
    return store, f, embed, fake


def test_approved_document_can_be_indexed_and_searched(tmp_path):
    store, f, embed, fake = build_store(tmp_path)
    assert store.index_document(f) >= 1
    assert embed.doc_calls == 1
    hits = store.search("Python", role="siswa", limit=2, max_distance=2)
    assert hits and hits[0].document_id == "demo-kb-1"
    assert hits[0].title == "Demo KB" and hits[0].source
    assert embed.query_calls == 1


def test_draft_cannot_index_not_even_create_collection_or_embed(tmp_path):
    store, f, embed, client = build_store(tmp_path)
    meta = json.loads((f.parent/"approved.txt.meta.json").read_text())
    meta.update(status="DRAF_BELUM_DISETUJUI", rag_indexing_allowed=False)
    (f.parent/"approved.txt.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(DocumentAccessError):
        store.index_document(f)
    assert embed.doc_calls == 0 and client.collection is None


def test_tutor_no_permission_to_read(tmp_path):
    store, f, embed, client = build_store(tmp_path)
    store.index_document(f)
    assert store.search("Python", role="tutor", max_distance=2) == []
    with pytest.raises(IndexAccessError):
        store.search("Python", role="guest")


def test_authorization_revocation_immediately_blocks_stale_index(tmp_path):
    store, f, _, _ = build_store(tmp_path)
    store.index_document(f)
    meta_file = f.parent/"approved.txt.meta.json"
    meta = json.loads(meta_file.read_text())
    meta["role_pembaca"] = ["admin"]
    meta_file.write_text(json.dumps(meta), encoding="utf-8")
    assert store.search("Python", role="siswa", max_distance=2) == []


def test_document_revocation_immediately_blocks_stale_index(tmp_path):
    store, f, _, _ = build_store(tmp_path)
    store.index_document(f)
    mf = f.parent/"approved.txt.meta.json"
    meta = json.loads(mf.read_text())
    meta.update(status="DRAF_BELUM_DISETUJUI", rag_indexing_allowed=False)
    mf.write_text(json.dumps(meta), encoding="utf-8")
    assert store.search("Python", role="admin", max_distance=2) == []


def test_source_changed_without_reindex_not_returned(tmp_path):
    store, f, _, _ = build_store(tmp_path)
    store.index_document(f)
    f.write_text("Materi Python berubah setelah index, tidak boleh sajikan konten lama.", encoding="utf-8")
    assert store.search("Python", role="siswa", max_distance=2) == []


def test_repeated_index_no_embed_recall(tmp_path):
    store, f, embed, _ = build_store(tmp_path)
    n = store.index_document(f)
    assert store.index_document(f) == n
    assert embed.doc_calls == 1


def test_model_dimension_identity_mismatch_rejected(tmp_path):
    store, f, embed, _ = build_store(tmp_path)
    store.index_document(f)
    embed.identity = "other-model-4"
    with pytest.raises(IndexCompatibilityError):
        store.search("Python", role="siswa")


def test_no_outside_source_or_symlink(tmp_path):
    store, f, embed, _ = build_store(tmp_path)
    outside = tmp_path/"external.md"
    outside.write_text("x")
    with pytest.raises(IndexAccessError):
        store.index_document(outside)
    sym = f.parent/"sym.txt"
    try:
        sym.symlink_to(f)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink privileges unavailable")
    with pytest.raises(IndexAccessError):
        store.index_document(sym)


def test_invalid_queries_and_vectors_rejected(tmp_path):
    store, f, _, _ = build_store(tmp_path)
    store.index_document(f)
    for query in ("", "  ", "x"*1501):
        with pytest.raises(ValueError):
            store.search(query, role="siswa")
    with pytest.raises(ValueError):
        store.search("Python", role="siswa", limit=11)
    with pytest.raises(EmbeddingError):
        normalize([1, 2], 4)
    with pytest.raises(EmbeddingError):
        normalize([0, 0], 2)


def test_no_index_created_by_query(tmp_path):
    store, f, embed, client = build_store(tmp_path)
    with pytest.raises(ValueError):
        store.search("Python", role="admin")
    assert client.collection is None


def test_different_document_id_collision_rejected(tmp_path):
    store, f, embed, client = build_store(tmp_path)
    store.index_document(f)
    other = f.parent / "other.txt"
    other.write_text(f.read_text(), encoding="utf-8")
    (f.parent / "other.txt.meta.json").write_text((f.parent / "approved.txt.meta.json").read_text(), encoding="utf-8")
    with pytest.raises(IndexCompatibilityError):
        store.index_document(other)
