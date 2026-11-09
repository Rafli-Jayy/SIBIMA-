"""Gemini embedding backend for SIBIMA RAG Patch 4C.

Embeddings transmit the provided text to Gemini API. Explicitly choose which
approved, non-sensitive documents to index before using this client.
"""
from __future__ import annotations

from math import isfinite, sqrt
from typing import Sequence


class EmbeddingError(RuntimeError):
    pass


def normalize(vector: Sequence[float], expected_dim: int) -> list[float]:
    """L2 normalization is required for reduced gemini-embedding-001 vectors."""
    if len(vector) != expected_dim:
        raise EmbeddingError("Dimensi embedding tidak sesuai dengan konfigurasi indeks.")
    numbers = [float(n) for n in vector]
    if any(not isfinite(n) for n in numbers):
        raise EmbeddingError("Embedding berisi angka tidak valid.")
    length = sqrt(sum(x*x for x in numbers))
    if length <= 0:
        raise EmbeddingError("Embedding kosong atau bernilai nol.")
    return [n / length for n in numbers]


class GeminiEmbedder:
    """Text-only embeddings with separate indexing and query task types."""

    def __init__(self, *, api_key: str, model: str = "gemini-embedding-001", dimension: int = 768, client=None):
        if not api_key and client is None:
            raise EmbeddingError("GEMINI_API_KEY belum tersedia.")
        if model != "gemini-embedding-001":
            raise EmbeddingError("Patch 4C hanya mendukung gemini-embedding-001 agar task_type konsisten.")
        if dimension not in (768, 1536, 3072):
            raise EmbeddingError("Dimensi embedding harus 768, 1536 atau 3072.")
        self.model = model
        self.dimension = dimension
        self.identity = f"{model}:{dimension}:retrieval-v1"
        if client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise EmbeddingError("Dependensi google-genai belum diinstal.") from exc
            client = genai.Client(api_key=api_key)
        self._client = client

    def _embed(self, texts: list[str], *, task_type: str) -> list[list[float]]:
        if not texts or any(not isinstance(t, str) or not t.strip() or len(t) > 12000 for t in texts):
            raise EmbeddingError("Teks embedding kosong atau terlalu panjang.")
        try:
            from google.genai import types
        except ImportError as exc:
            raise EmbeddingError("Dependensi google-genai belum diinstal.") from exc
        try:
            response = self._client.models.embed_content(
                model=self.model,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type, output_dimensionality=self.dimension,
                ),
            )
        except Exception as exc:
            # No remote exception text; SDK errors can include sensitive data.
            raise EmbeddingError(f"Gemini Embedding gagal ({type(exc).__name__}).") from exc
        embs = getattr(response, "embeddings", None)
        if not isinstance(embs, (tuple, list)) or len(embs) != len(texts):
            raise EmbeddingError("Jumlah embedding dari Gemini tidak sesuai.")
        return [normalize(getattr(emb, "values", None) or [], self.dimension) for emb in embs]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for offset in range(0, len(texts), 8):
            results.extend(self._embed(texts[offset: offset + 8], task_type="RETRIEVAL_DOCUMENT"))
        return results

    def embed_query(self, query: str) -> list[float]:
        if len(query) > 1500:
            raise EmbeddingError("Pertanyaan pencarian terlalu panjang.")
        return self._embed([query], task_type="RETRIEVAL_QUERY")[0]
