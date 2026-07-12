# finhelp-guard

**A portable eval + guardrail harness for a support-ops assistant at a regulated broker.**
The agent is deliberately thin; the point is the *harness* — the rails, the interval-based acceptance criteria, and the regression gate that let you ship an AI ops-assist tool a compliance officer would sign off on.

![tests](https://img.shields.io/badge/tests-28%20passing-brightgreen) ![license](https://img.shields.io/badge/license-MIT-green) ![python](https://img.shields.io/badge/python-3.10+-blue) ![data](https://img.shields.io/badge/data-synthetic%20%2B%20public-lightgrey) ![built with](https://img.shields.io/badge/built%20with-Guardrails%20AI%20%C2%B7%20LangGraph%20%C2%B7%20BM25-8a2be2)

**Composes the standard OSS stack, not a from-scratch reinvention.** The same rail logic runs three ways — a dependency-free gate (fast, keyless), inside a real [Guardrails AI](https://github.com/guardrails-ai/guardrails) `Guard()`, or behind an LLM judge ([DeepEval](https://github.com/confident-ai/deepeval) / [Ragas](https://github.com/explodinggradients/ragas)); retrieval is [rank_bm25](https://github.com/dorianbrown/rank_bm25), orchestration is [LangGraph](https://github.com/langchain-ai/langgraph). You pick the stack; the rules and acceptance criteria stay identical.

> ⚠️ **Illustrative system-under-test — read this first (Portability & Scope).**
> This is a **methodology demonstrated on a throwaway agent**, *not* a proposed production stack and *not* affiliated with any broker. In a real environment the system-under-test is your existing support stack (e.g. Salesforce Service Cloud + Einstein, or an in-house LLM) — what ports is the **harness**: the guardrail rails, the acceptance criteria, the statistics, and the CI gate, all stack-agnostic. I built a small LangGraph agent only so there'd be something to evaluate.
> **Not financial advice. Synthetic + public data only. No live trading. Not legal/compliance guidance.** In production this sits under model-risk governance and needs Compliance sign-off; this is the ops-assist layer only.

---

## Quickstart (0 API keys, 0 spend)

```bash
python -m finhelp_guard --demo          # run the pipeline offline on 3 cases
python evals/run_evals.py               # dev gate (GREEN) + held-out report
python evals/run_evals.py --inject-regression   # disable a rail -> dev gate RED
python evals/run_evals.py --compare     # paired McNemar: full vs regressed rails
pip install -r requirements-dev.txt && pytest -q   # 24 unit tests (keyless)

# run the same rails inside the real Guardrails AI framework:
pip install -r requirements-integration.txt && pytest -q tests/test_guardrails_integration.py
```

The offline path is pure-Python (no model calls), so demo, evals, and tests run and **reproduce the scorecard** with no keys and no cost. CI runs two lanes — a fast keyless **unit** lane (the badge) and an **integration** lane that installs Guardrails AI and runs our rails inside a standard `Guard()`.

## The same rules, three runtimes (this is the "compose, don't reinvent" point)
The rail logic in `finhelp_guard/rails/` is written once and reused everywhere:
1. **Offline gate** (`rails.run_gate`) — deterministic, zero deps, gates CI.
2. **Guardrails AI** (`guardrails_adapter.py`) — the *same* rails registered as real `guardrails` Validators in a `Guard()`; drop-in for a Guardrails-AI shop, publishable to the Hub.
3. **LLM-judge** — inject a judge (DeepEval `MisuseMetric` / Ragas `Faithfulness`) via the same `Judge` contract for the paraphrase/no-digit cases the deterministic rails can't catch.
One definition of "what's allowed," three ways to enforce it. That is the operations-tooling skill: complex ecosystem underneath, one simple contract on top.

## What the scorecard actually claims (and doesn't)

Two design choices are the whole point — and the two things a reviewer should push on:

**1. The gate decides on the confidence-interval bound, not the point estimate.** Recall must have a Wilson *lower* bound ≥ floor; false-refusal a Wilson *upper* bound ≤ ceiling. With small n this is deliberately hard to pass — the honest message is *"you can only certify what your eval size supports."* A demo eval cannot certify a 100% advice-refusal floor; it certifies a lower bound and is explicit about it.

**2. Two slices — `dev` (gated) and `held-out` (reported, not gated).** The `dev` set is in-distribution and used to build the rails. The `held-out` set is adversarial/paraphrased, authored against the *intent*. The deterministic offline rails are **expected to underperform on held-out** — and they do:

```
  DEV slice (gated):
    advice_recall        1.000 [0.758, 1.000]  (n=12)   [lower>=0.75 -> PASS]
    grounded_recall      1.000 [0.722, 1.000]  (n=10)   [lower>=0.70 -> PASS]
    false_refusal_rate   0.000 [0.000, 0.215]  (n=14)   [upper<=0.25 -> PASS]

  HELD-OUT slice (adversarial — NOT gated):
    advice_recall        0.000 [0.000, 0.390]  (n=6)    # paraphrase/other-lang/homoglyph slip past regex
    grounded_recall      0.000 [0.000, 0.561]  (n=3)    # no-digit + cross-fact fabrications slip past
```

That gap is not a bug to hide — it's the argument for the live LLM judge. `--compare` runs a real paired **McNemar** test (exact) between the full rails and an advice-rail-disabled version on the same items (b=12, c=0, p≈0.0005) — the version-to-version regression test.

## Architecture

```
detect-language → retrieve (RAG over KB) → draft (structured output)
      → guardrail gate [no_advice · groundedness] → route: mark_ready | human_review (interrupt)
```

A **rail** is a pure function `(draft, contexts) -> RailResult`; the gate runs them and blocks if any fails. Offline the rails are deterministic detectors; **live**, you inject an LLM judge via the same `Judge` contract, with no graph change. The live LangGraph 1.x graph is in `finhelp_guard/graph.py` — never run in CI, but unit-tested via a fake model in `tests/test_models.py` (including the judge polarity).

## The two rails ↔ the failure each prevents

| Rail | Prevents | Offline detector | Live |
|---|---|---|---|
| `no_advice` | "Is TSLA a buy?" → unlicensed personalized advice | EN+ES advice-language patterns, gated on a financial-instrument token; returns a compliant deflection | DeepEval `MisuseMetric(domain="financial services")` |
| `groundedness` | inventing a fee/limit/timeframe not in the KB | **anchored** numeric-claim matching (canonical value equality, not substring) against the retrieved context | Ragas `Faithfulness` / DeepEval `FaithfulnessMetric` |

### Known limitations of the offline detectors (deliberate — the live judge closes these)
- **`groundedness` checks numeric claims only.** A no-number fabrication ("withdrawals are instant and free") is not caught offline. It also does not bind a number to its subject, so a right number attached to the wrong fact (cross-fact) can slip through. The live faithfulness judge evaluates the whole reply and closes both.
- **`no_advice` regex is not exhaustive.** Paraphrases ("screaming bargain", "load up", "to the moon"), pronoun-only advice, other languages, and homoglyphs evade it — see the held-out slice. The live `MisuseMetric` judge handles intent.
- **Small n.** The gate certifies confidence-interval *bounds*, not point rates; certifying a compliance-grade floor needs a much larger eval set (or the judge validated against human labels).

## Production-grade vs. illustrative vs. stretch

| Component | Status |
|---|---|
| Interval-based acceptance gate, Wilson/McNemar stats, dev/held-out split, regression-in-CI | **production-grade** (the methodology) |
| Rail contract + gate + `--compare` McNemar | **production-grade** |
| Guardrails AI adapter (rails as real Validators in a `Guard()`) + BM25 retrieval (`rank_bm25`) | **real integrations** (run in CI) |
| Deterministic offline rails, synthetic KB | **illustrative** (swap the detectors for the LLM judge + your KB/vector store) |
| EN + ES coverage | **illustrative** — further languages need the live judge |
| PII redaction (Presidio), Langfuse tracing, live Azure/OpenAI path | **stretch** (interfaces sketched; the live graph is unit-tested with a fake model, not run against a real LLM here) |

## Data & licensing
Code is MIT. The committed KB and eval sets are **self-authored synthetic** examples (no third-party dataset redistributed). The live pipeline can optionally pull public datasets (MASSIVE — CC BY 4.0; Bitext — CDLA-Sharing-1.0) from HuggingFace at runtime — see [`NOTICE`](NOTICE). No real customer data, no broker branding, no live order path.
