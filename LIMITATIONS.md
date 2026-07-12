# Known limitations (honest register)

Tier-1 means stating exactly where the edges are. These are the residuals after several
adversarial red-team rounds; each has a mitigation on the [ROADMAP](ROADMAP.md).

## Guardrails
- **Groundedness LLM judge is imperfect and, as prompted, uncalibratable to a good point.**
  Calibrated (`evals/calibrate.py --judge grounded`) it scores **ROC-AUC ≈ 0.84, ECE ≈ 0.11** and
  false-positives a benign reply ("card deposits are credited instantly") at 1.0 — so no threshold
  gives both low false-refusal and useful recall. It needs a better prompt / stronger judge model.
  Impact is bounded because the **layered policy** trusts the precise deterministic check for numeric
  claims and only invokes this judge on no-number replies (ADR 0002).
- **Cross-fact groundedness miss** — a right number attached to the wrong fact can pass the numeric
  check (no subject binding). Needs sentence-level claim entailment.
- **Advice/PII regex are not exhaustive** — paraphrase/other-language/homoglyph advice, and obfuscated
  PII ("john [at] x dot com", digit-split cards) evade the deterministic rails; the LLM judge / Presidio
  are the swaps that close these, behind the same contracts.

## Security
- **Authorization gates tool *access*, not model *assertions*.** Cross-account tool reads are denied
  and audited, but a prompt-injected/hallucinating model could still *state* fabricated or another
  account's facts in prose. A reply-side account-id check narrows this; fully preventing hallucinated
  disclosure needs a stronger output policy. `ticket.account_id` is trusted and MUST be set by an
  authenticated intake channel — that boundary is upstream of this repo.
- **Audit log** is hash-chained (tamper-evident) but a plain file is not OS-enforced WORM, and writes
  are **fail-open** (a logging error doesn't block the reply). A regulated deployment ships the chain to
  append-only storage and chooses fail-closed.

## Evaluation
- **Human gold set is not yet labelled** — `data/gold/annotator_{a,b}.jsonl` are empty stubs; Cohen's κ
  has not been produced. Current calibration uses **interim author labels** and is illustrative. The
  harness is complete; the missing input is ~2h of human labeling.
- **Small n, ~50/50 prevalence, in-distribution dev.** The advice-judge AUC=1.0 reflects a trivially
  separable, in-distribution set — not a hard result. The dev slice is both rail-building and CI-gated
  (train-on-test); the held-out slice is reported, not gated. Realistic prevalence + a true held-out
  calibration split are open.
- **Single-run judge scores** — no variance/CIs on AUC/ECE yet (LLM judges are noisy).

## Retrieval
- **Dense/hybrid semantic recall is not exercised in the keyless unit lane.** With no provider
  key or `sentence-transformers`, the dense path falls back to a non-semantic `HashingEmbedder`
  (hashed bag-of-tokens) so the *code path* runs deterministically in CI — it does **not** match
  synonyms. Unit tests assert fusion/ranking **mechanics** (RRF order, self-similarity, language
  filtering); real "dense catches what BM25 misses" is demonstrated only in the integration/live
  lane (ADR 0004). Default retrieval remains BM25, so eval numbers are lexical-only today.

## Scope
- **`graph.py`** is the illustrative LangGraph RAG path (now audited); the **hardened tool-calling
  path with authorization is `agent.py` / `--triage`**. DeepEval / Ragas / Langfuse are documented
  swap-ins behind the `Judge`/rail contracts, not yet imported.
