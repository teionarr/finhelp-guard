"""Retrieval: RRF fusion math (known-answer), dense ranking mechanics, hybrid wiring.

Keyless and deterministic — the dense path uses the non-semantic HashingEmbedder,
so these assert *mechanics* (fusion order, self-similarity, lang filtering), never
semantic recall. Real semantic behaviour is exercised in the integration/live lane.
"""
from pathlib import Path

import pytest

from finhelp_guard.retrieve import (BM25Retriever, DenseRetriever, Doc, HashingEmbedder,
                                    HybridRetriever, load_kb, make_embedder, rrf_fuse)

ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "kb_synthetic.jsonl"


# --- RRF fusion (the real contribution — unit-tested against a hand computation) ---
def test_rrf_fuse_known_answer():
    # a: 1/61+1/63=.03227  b: 1/62+1/61=.03252  c: 1/63+1/62=.03200  ->  b, a, c
    assert rrf_fuse([["a", "b", "c"], ["b", "c", "a"]], k=60) == ["b", "a", "c"]


def test_rrf_single_ranker_preserves_order():
    assert rrf_fuse([["x", "y", "z"]]) == ["x", "y", "z"]


def test_rrf_rewards_agreement():
    # d appears top of both rankers -> must win over items only one ranker likes.
    assert rrf_fuse([["d", "a", "b"], ["d", "c", "e"]])[0] == "d"


# --- Dense ranking mechanics (HashingEmbedder: deterministic, non-semantic) ---
_DOCS = [
    Doc("d1", "en", "the withdrawal fee is 5 dollars"),
    Doc("d2", "en", "deposits are credited to your account instantly"),
    Doc("d3", "es", "la comision de retiro es cinco dolares"),
]


def test_dense_ranks_identical_text_first():
    dense = DenseRetriever(_DOCS, HashingEmbedder())
    assert dense.retrieve(_DOCS[1].text, k=1) == [_DOCS[1].text]


def test_dense_and_hybrid_honor_lang():
    dense = DenseRetriever(_DOCS, HashingEmbedder())
    hybrid = HybridRetriever(BM25Retriever(_DOCS), dense)
    for r in (dense, hybrid):
        got = r.retrieve("withdrawal fee", k=3, lang="en")
        assert got and all("comision" not in t for t in got)  # no Spanish doc leaks in


# --- Hybrid wiring: exact-term hit still surfaces after fusion ---
def test_hybrid_surfaces_lexical_exact_match():
    hybrid = HybridRetriever(BM25Retriever(_DOCS), DenseRetriever(_DOCS, HashingEmbedder()))
    assert hybrid.retrieve("withdrawal fee", k=1, lang="en") == ["the withdrawal fee is 5 dollars"]


# --- load_kb factory: default stays bm25; hybrid opt-in runs keyless ---
def test_load_kb_defaults_to_bm25(monkeypatch):
    monkeypatch.delenv("FINHELP_RETRIEVER", raising=False)  # assert the *default*, not ambient env
    assert isinstance(load_kb(KB), BM25Retriever)


def test_unknown_retriever_mode_raises():
    with pytest.raises(ValueError):
        load_kb(KB, mode="bogus")


def test_unknown_embedder_raises(monkeypatch):
    monkeypatch.setenv("FINHELP_EMBEDDER", "providr")  # typo must fail loudly, not degrade
    with pytest.raises(ValueError):
        make_embedder()


def test_load_kb_hybrid_mode_runs_keyless(monkeypatch):
    monkeypatch.setenv("FINHELP_EMBEDDER", "hashing")
    kb = load_kb(KB, mode="hybrid")
    assert isinstance(kb, HybridRetriever)
    hits = kb.retrieve("How much is the withdrawal fee?", k=2, lang="en")
    assert 1 <= len(hits) <= 2 and all(isinstance(h, str) for h in hits)


def test_bm25_still_retrieves_on_keyword(monkeypatch):
    monkeypatch.delenv("FINHELP_RETRIEVER", raising=False)
    kb = load_kb(KB)  # default bm25
    hits = kb.retrieve("withdrawal fee", k=2, lang="en")
    assert hits and any("fee" in h.lower() for h in hits)
