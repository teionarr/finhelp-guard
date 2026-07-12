"""Pluggable retrieval over the KB.

The rest of the system depends only on the contract `retrieve(query, k, lang) -> list[str]`,
so retrieval is a swappable component:

- ``BM25Retriever``  — lexical (Okapi BM25), the zero-dependency default.
- ``DenseRetriever`` — embeddings + cosine, behind an ``Embedder`` protocol whose
  three backings are a provider endpoint (Azure/OpenAI/Nebius) for live runs,
  ``sentence-transformers`` for the integration lane, and a deterministic
  ``HashingEmbedder`` so the dense code path runs keyless in CI.
- ``HybridRetriever`` — fuses lexical + dense rankings with Reciprocal Rank
  Fusion (RRF), the standard normalization-free fusion.

Selected by ``FINHELP_RETRIEVER`` (``bm25`` | ``dense`` | ``hybrid``); default
``bm25`` keeps CI deterministic and keyless. In production the ``Embedder`` is a
real vector store (pgvector / Azure AI Search) — same caller, no code change.
"""
from __future__ import annotations

import json
import math
import os
import sys
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol

from rank_bm25 import BM25Okapi

_TOKEN = re.compile(r"[a-z0-9]+")


def _tok(text: str) -> List[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Doc:
    id: str
    lang: str
    text: str


# --- Embedder contract + backings -------------------------------------------
class Embedder(Protocol):
    """Turns text into vectors. Real backing = a vector store's embedding model."""

    def embed(self, texts: List[str]) -> List[List[float]]: ...


class HashingEmbedder:
    """Deterministic, dependency-free feature-hashing vectorizer.

    Exists so the dense/fusion **code path** runs with no model and no API key in
    CI. It is a hashed bag-of-tokens — NOT semantic: it will not match synonyms,
    so it is used only to exercise mechanics, never to claim semantic recall.
    Real semantic embeddings come from ``SentenceTransformerEmbedder`` (integration
    lane) or ``ProviderEmbedder`` (live).
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _vec(self, text: str) -> List[float]:
        v = [0.0] * self.dim
        for t in _tok(text):
            h = int.from_bytes(hashlib.blake2b(t.encode(), digest_size=8).digest(), "big")
            v[h % self.dim] += 1.0
        return v

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._vec(t) for t in texts]


class SentenceTransformerEmbedder:
    """Local semantic embeddings via sentence-transformers (integration lane)."""

    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # lazy: optional dep

        self._model = SentenceTransformer(model)

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [list(map(float, row)) for row in self._model.encode(texts)]


class ProviderEmbedder:
    """Semantic embeddings via an OpenAI-compatible endpoint (Azure/OpenAI/Nebius)."""

    def __init__(self, model=None):
        from .models import embedding_model  # lazy: keeps offline path langchain-free

        self._model = model or embedding_model()

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [list(map(float, v)) for v in self._model.embed_documents(texts)]


def make_embedder() -> Embedder:
    """Pick the strongest embedder available without failing the keyless path.

    provider key present → ProviderEmbedder (live, semantic)
    else sentence-transformers importable → SentenceTransformerEmbedder (local, semantic)
    else → HashingEmbedder (deterministic, non-semantic; prints an honest notice)
    """
    forced = os.getenv("FINHELP_EMBEDDER", "").strip().lower()
    if forced not in ("", "hashing", "provider", "sentence-transformers"):
        # Symmetric with load_kb: a typo shouldn't silently degrade to non-semantic.
        raise ValueError(f"unknown FINHELP_EMBEDDER={forced!r} "
                         "(expected hashing|provider|sentence-transformers)")
    if forced == "hashing":
        return HashingEmbedder()
    if forced == "provider" or (not forced and (
        os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("NEBIUS_API_KEY") or os.getenv("OPENAI_API_KEY")
    )):
        return ProviderEmbedder()
    if forced == "sentence-transformers":
        return SentenceTransformerEmbedder()
    try:
        return SentenceTransformerEmbedder()
    except Exception:
        print("finhelp-guard: no embedding model available; using non-semantic "
              "HashingEmbedder (set a provider key or install sentence-transformers "
              "for real dense recall).", file=sys.stderr)
        return HashingEmbedder()


# --- Fusion ------------------------------------------------------------------
def rrf_fuse(rankings: List[List[str]], k: int = 60) -> List[str]:
    """Reciprocal Rank Fusion: combine ranked id-lists without score normalization.

    Each ranker contributes 1 / (k + rank) per doc (rank is 1-based); scores sum
    across rankers. ``k`` damps the influence of low ranks (RRF's standard 60).
    """
    scores: Dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


# --- Retrievers --------------------------------------------------------------
class BM25Retriever:
    def __init__(self, docs: List[Doc]):
        self.docs = docs
        self._bm25 = BM25Okapi([_tok(d.text) for d in docs])

    def _ranked(self, query: str, lang: Optional[str]) -> List[Doc]:
        scores = self._bm25.get_scores(_tok(query))
        ranked = sorted(
            ((s, d) for s, d in zip(scores, self.docs) if not lang or d.lang == lang),
            key=lambda x: x[0], reverse=True,
        )
        return [d for s, d in ranked if s > 0]

    def retrieve(self, query: str, k: int = 2, lang: Optional[str] = None) -> List[str]:
        return [d.text for d in self._ranked(query, lang)[:k]]


class DenseRetriever:
    def __init__(self, docs: List[Doc], embedder: Embedder):
        self.docs = docs
        self.embedder = embedder
        self._emb = embedder.embed([d.text for d in docs])

    def _ranked(self, query: str, lang: Optional[str]) -> List[Doc]:
        q = self.embedder.embed([query])[0]
        scored = [
            (_cosine(q, e), d) for e, d in zip(self._emb, self.docs)
            if not lang or d.lang == lang
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for s, d in scored if s > 0]

    def retrieve(self, query: str, k: int = 2, lang: Optional[str] = None) -> List[str]:
        return [d.text for d in self._ranked(query, lang)[:k]]


class HybridRetriever:
    """Lexical + dense, fused with RRF. Catches both exact-term and semantic hits."""

    def __init__(self, lexical: BM25Retriever, dense: DenseRetriever, rrf_k: int = 60):
        self.lexical = lexical
        self.dense = dense
        self.rrf_k = rrf_k
        self._by_id = {d.id: d for d in lexical.docs}

    def retrieve(self, query: str, k: int = 2, lang: Optional[str] = None) -> List[str]:
        lex = [d.id for d in self.lexical._ranked(query, lang)]
        den = [d.id for d in self.dense._ranked(query, lang)]
        fused = rrf_fuse([lex, den], k=self.rrf_k)
        return [self._by_id[i].text for i in fused[:k]]


def _load_docs(path: str | Path) -> List[Doc]:
    docs: List[Doc] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        docs.append(Doc(id=d["id"], lang=d.get("lang", "en"), text=d["text"]))
    return docs


def load_kb(path: str | Path, mode: Optional[str] = None):
    """Load the KB and return a retriever.

    ``mode`` (or ``FINHELP_RETRIEVER``): ``bm25`` (default) | ``dense`` | ``hybrid``.
    Dense/hybrid build an embedder via ``make_embedder()``.
    """
    mode = (mode or os.getenv("FINHELP_RETRIEVER", "bm25")).strip().lower()
    docs = _load_docs(path)
    bm25 = BM25Retriever(docs)
    if mode == "bm25":
        return bm25
    dense = DenseRetriever(docs, make_embedder())
    if mode == "dense":
        return dense
    if mode == "hybrid":
        return HybridRetriever(bm25, dense)
    raise ValueError(f"unknown FINHELP_RETRIEVER={mode!r} (expected bm25|dense|hybrid)")
