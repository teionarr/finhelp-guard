"""Integration lane: real semantic embeddings via sentence-transformers.

Unlike the keyless unit tests (which use the non-semantic HashingEmbedder and only
assert fusion *mechanics*), this exercises the actual value of dense/hybrid retrieval:
a paraphrased query with no shared terms is caught by embeddings where BM25 misses it.
Skips cleanly when sentence-transformers isn't installed.
"""
import pytest

pytest.importorskip("sentence_transformers")

from finhelp_guard.retrieve import (  # noqa: E402
    BM25Retriever, DenseRetriever, Doc, HybridRetriever, SentenceTransformerEmbedder,
)

_DOCS = [
    Doc("pw", "en", "Reset your sign-in details from the profile security settings."),
    Doc("wire", "en", "International wire transfers can take up to five business days."),
    Doc("hours", "en", "Our office is open on weekday mornings."),
]
_EMB = SentenceTransformerEmbedder()  # load the model once for the module
_QUERY = "I forgot my password, how do I change my login?"


def test_dense_catches_paraphrase_that_bm25_misses():
    dense = DenseRetriever(_DOCS, _EMB)
    assert dense.retrieve(_QUERY, k=1) == [_DOCS[0].text]      # semantic hit
    assert _DOCS[0].text not in BM25Retriever(_DOCS).retrieve(_QUERY, k=1)  # lexical miss


def test_hybrid_surfaces_the_semantic_hit():
    hybrid = HybridRetriever(BM25Retriever(_DOCS), DenseRetriever(_DOCS, _EMB))
    assert _DOCS[0].text in hybrid.retrieve(_QUERY, k=2)
