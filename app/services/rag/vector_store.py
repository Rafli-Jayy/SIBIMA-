"""Approved-source-only persistent Chroma index; not connected to AI UI yet.

All returned hits are re-authorized against the source document on disk, not
solely against mutable metadata inside Chroma. The DB is a local Chroma index,
not SIBIMA's PostgreSQL database.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .document_loader import ALLOWED_ROLES, DocumentAccessError, DocumentFormatError, load_document
from .chunker import TextChunk, chunk_document
from .embedding_client import EmbeddingError, normalize
from .relevance import is_relevant

COLLECTION_NAME = "sibima_rag_patch4c_v1"
SCHEMA = "sibima_rag_index_v1"


class IndexAccessError(PermissionError):
    pass


class IndexCompatibilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    document_id: str
    title: str
    section: str
    text: str
    source: str
    distance: float | None


class KnowledgeVectorStore:
    def __init__(self, *, source_root: str | Path, index_dir: str | Path,
                 embedder: Any, client: Any = None):
        self.source_root = Path(source_root).resolve()
        self.index_dir = Path(index_dir).resolve()
        self.embedder = embedder
        if not getattr(embedder, "identity", None) or not getattr(embedder, "dimension", None):
            raise ValueError("Embedder wajib memiliki identity dan dimension.")
        if self.source_root == self.index_dir or self.source_root in self.index_dir.parents:
            # Index files must never be treated as candidate source documents.
            raise IndexAccessError("Folder indeks tidak boleh berada di dalam folder sumber dokumen.")
        if client is None:
            try:
                import chromadb
            except ImportError as exc:
                raise RuntimeError("ChromaDB belum terinstal: python -m pip install chromadb") from exc
            self.index_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(self.index_dir))
        self._client = client

    def _source_path(self, relative: str) -> Path:
        source = self.source_root / relative
        # Reject path traversal, including symlinks and resolved escapes.
        if source.is_symlink():
            raise IndexAccessError("Symbolic link dokumen tidak didukung.")
        try:
            resolved = source.resolve(strict=True)
            resolved.relative_to(self.source_root)
        except (OSError, ValueError) as exc:
            raise IndexAccessError("Dokumen di luar folder sumber atau tidak tersedia.") from exc
        return resolved

    def _relative(self, source: str | Path) -> str:
        source_path = Path(source)
        if source_path.is_symlink():
            raise IndexAccessError("Symbolic link dokumen tidak didukung.")
        try:
            return source_path.resolve(strict=True).relative_to(self.source_root).as_posix()
        except (OSError, ValueError) as exc:
            raise IndexAccessError("Dokumen wajib berada di dalam folder sumber RAG.") from exc

    def _check_collection(self, col) -> None:
        metadata = col.metadata or {}
        if (metadata.get("schema") != SCHEMA or
                metadata.get("embedder_id") != self.embedder.identity or
                metadata.get("dim") != self.embedder.dimension):
            raise IndexCompatibilityError(
                "Indeks tidak kompatibel dengan model/dimensi saat ini. Gunakan folder indeks baru."
            )

    def _collection(self, *, create: bool):
        if create:
            col = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"schema": SCHEMA, "embedder_id": self.embedder.identity,
                          "dim": self.embedder.dimension},
                configuration={"hnsw": {"space": "cosine"}},
                embedding_function=None,
            )
        else:
            col = self._client.get_collection(name=COLLECTION_NAME, embedding_function=None)
        self._check_collection(col)
        return col

    def index_document(self, path: str | Path) -> int:
        """Index an explicitly approved source document; never index previews."""
        relative = self._relative(path)
        doc = load_document(self._source_path(relative), preview=False)
        chunks = chunk_document(doc, preview=False)
        if not chunks:
            raise DocumentFormatError("Tidak ada chunk untuk diindeks.")
        if len(chunks) > 3000:
            raise DocumentFormatError("Dokumen menghasilkan terlalu banyak chunk.")
        col = self._collection(create=True)
        old = col.get(where={"document_id": doc.document_id}, include=["metadatas"])
        for meta in old.get("metadatas") or []:
            if meta and meta.get("relative_source") != relative:
                raise IndexCompatibilityError("document_id digunakan oleh sumber lain.")
        digest = sha256(doc.text.encode("utf-8")).hexdigest()
        existing_ids = set(old.get("ids") or [])
        ids = [chunk.chunk_id for chunk in chunks]
        # No embedded API call when content and metadata unchanged.
        old_meta = {i: m for i, m in zip(old.get("ids") or [], old.get("metadatas") or [])}
        roles_flags = {f"allow_{role}": role in doc.allowed_roles for role in ALLOWED_ROLES}
        if set(ids) == existing_ids and all(
            old_meta.get(chunk.chunk_id, {}).get("content_sha256") == digest and
            all(old_meta.get(chunk.chunk_id, {}).get(k) == val for k, val in roles_flags.items())
            for chunk in chunks
        ):
            return len(chunks)
        vectors = self.embedder.embed_documents([chunk.text for chunk in chunks])
        if len(vectors) != len(chunks):
            raise EmbeddingError("Jumlah embedding tidak cocok dengan chunk.")
        vectors = [normalize(v, self.embedder.dimension) for v in vectors]
        # Batch so Chroma doesn't exceed request limits.
        for start in range(0, len(chunks), 100):
            batch = chunks[start:start + 100]
            metas = [dict(
                document_id=doc.document_id, document_version=doc.version,
                relative_source=relative, content_sha256=digest,
                section=chunk.section, title=chunk.title, page=chunk.page or 0,
                **roles_flags,
            ) for chunk in batch]
            col.upsert(
                ids=[c.chunk_id for c in batch],
                documents=[c.text for c in batch],
                embeddings=vectors[start:start + len(batch)],
                metadatas=metas,
            )
        outdated = list(existing_ids - set(ids))
        if outdated:
            col.delete(ids=outdated)
        return len(chunks)

    def search(self, query: str, *, role: str, limit: int = 3,
               max_distance: float = 0.65) -> list[SearchHit]:
        if role not in ALLOWED_ROLES:
            raise IndexAccessError("Role tidak valid.")
        if not isinstance(query, str) or not query.strip() or len(query) > 1500:
            raise ValueError("Pertanyaan pencarian kosong atau terlalu panjang.")
        if not 1 <= limit <= 10 or not 0 <= max_distance <= 2:
            raise ValueError("Batas hasil atau jarak tidak valid.")
        col = self._collection(create=False)
        if col.count() == 0:
            return []
        vector = normalize(self.embedder.embed_query(query), self.embedder.dimension)
        result = col.query(
            query_embeddings=[vector],
            n_results=min(col.count(), max(limit * 4, 10)),
            where={f"allow_{role}": True},
            include=["metadatas", "documents", "distances"],
        )
        rows = zip(
            (result.get("ids") or [[]])[0],
            (result.get("documents") or [[]])[0],
            (result.get("metadatas") or [[]])[0],
            (result.get("distances") or [[]])[0],
        )
        found: list[SearchHit] = []
        verified: dict[str, tuple[Any, dict[str, TextChunk], str] | None] = {}
        for chunk_id, content, metadata, distance in rows:
            if not isinstance(metadata, dict) or metadata.get(f"allow_{role}") is not True:
                continue
            if distance is None or float(distance) > max_distance:
                continue
            relative = metadata.get("relative_source")
            if not isinstance(relative, str):
                continue
            if relative not in verified:
                try:
                    source = self._source_path(relative)
                    doc = load_document(source, role=role, preview=False)
                    pieces = {c.chunk_id: c for c in chunk_document(doc, role=role, preview=False)}
                    verified[relative] = (doc, pieces, sha256(doc.text.encode("utf-8")).hexdigest())
                except (DocumentAccessError, DocumentFormatError, IndexAccessError):
                    verified[relative] = None
            item = verified[relative]
            if item is None:
                continue
            doc, pieces, current_hash = item
            chunk = pieces.get(chunk_id)
            if not chunk or metadata.get("content_sha256") != current_hash:
                continue
            if (metadata.get("document_id") != doc.document_id or
                    metadata.get("document_version") != doc.version or
                    chunk.text != content):
                continue
            if not is_relevant(query, doc.document_id, doc.title, chunk.section, chunk.text):
                continue
            source = chunk.source_label
            found.append(SearchHit(chunk.chunk_id, doc.document_id, doc.title,
                                   chunk.section, chunk.text, source, float(distance)))
            if len(found) >= limit:
                break
        return found
