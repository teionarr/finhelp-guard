# ADR 0004 — Retrieval is a pluggable component; hybrid = BM25 + dense via RRF

**Status:** accepted

**Context.** RAG quality lives or dies on retrieval, and no single retriever is
sufficient: lexical BM25 nails exact terms (fees, policy names, IDs) but misses
paraphrase; dense embeddings catch semantics but can drift on rare tokens and
numbers. The system-under-test is illustrative, but the *seam* has to be the real
one a production RAG plugs into — and CI must stay keyless and deterministic.

**Decision.** Keep every caller on one contract, `retrieve(query, k, lang) -> list[str]`,
and make the implementation swappable via `FINHELP_RETRIEVER`:
- `bm25` (default) — Okapi BM25; deterministic, zero-dependency, keeps CI keyless.
- `dense` — embeddings + cosine, behind an `Embedder` protocol.
- `hybrid` — fuse the two rankings with **Reciprocal Rank Fusion** (`1/(k+rank)`,
  k=60), which needs no score normalization across the two very different scales.

The `Embedder` has three backings, strongest-available: a **provider** endpoint
(Azure/OpenAI/Nebius) for live, **`sentence-transformers`** for the integration
lane, and a deterministic dependency-free **`HashingEmbedder`** for keyless CI.

**Honesty constraint.** The `HashingEmbedder` is a hashed bag-of-tokens — **not
semantic**. It exists only so the dense/fusion *code path* runs in CI; we never
claim it gives synonym recall. The unit tests therefore assert **mechanics**
(RRF order against a hand computation, self-similarity, language filtering), and
the semantic "dense catches what BM25 misses" property is exercised in the
integration/live lane, not faked offline.

**Consequences.** Default behaviour and all eval numbers are unchanged (still
BM25), so the CI gate doesn't move; hybrid is opt-in. A production RAG — pgvector,
Azure AI Search, a managed vector DB — is added by implementing `Embedder`; no
caller, gate, agent, or eval code changes. The fusion is one small pure function,
independently testable.
