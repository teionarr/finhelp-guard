# finhelp-guard

**Guardrails + a statistically-honest evaluation harness for LLM support agents in regulated, high-accuracy domains.**

Wrap any support agent's output in enforceable guardrails (no unlicensed advice, groundedness, PII), prove they work with a CI-gated eval that reports confidence intervals — not vanity accuracy — and calibrate the LLM-judge instead of trusting a hard-coded threshold. Every decision is authorized, enforced, and audited.

![tests](https://img.shields.io/badge/tests-48%20unit%20%2B%204%20integration-brightgreen) ![lint](https://img.shields.io/badge/lint-ruff-brightgreen) ![license](https://img.shields.io/badge/license-MIT-green) ![python](https://img.shields.io/badge/python-3.10+-blue) ![data](https://img.shields.io/badge/data-synthetic%20%2B%20public-lightgrey) ![built with](https://img.shields.io/badge/built%20with-Guardrails%20AI%20%C2%B7%20LangGraph%20%C2%B7%20BM25-8a2be2)

> ⚠️ **Reference implementation, not a plug-and-play broker bot.** The agent + mocked CRM are an *illustrative system-under-test*; the reusable part is the **harness** (rails, acceptance criteria, calibration, CI gate, audit), which is stack-agnostic. **Not financial advice. Synthetic + public data only. No live trading.** In production this sits under model-risk governance and needs Compliance sign-off.

---

## Contents
- [Why](#why) · [What you get](#what-you-get) · [Risks it handles](#risks-it-handles)
- [Quickstart](#quickstart-0-api-keys-0-spend) · [The working agent](#the-working-agent)
- [How it works](#how-it-works) · [Evaluation & calibration](#evaluation--calibration)
- [Adversarial review](#adversarial-review--risks-found--fixed) · [Configuration](#configuration)
- [Limitations & roadmap](#limitations--roadmap) · [Contributing · License · Data](#contributing--license--data)

## Why

Shipping an LLM into a regulated support workflow fails on two fronts that demos ignore:

1. **Unsafe output** — the model gives investment advice, invents a fee, leaks PII, or reads the wrong customer's data.
2. **Unmeasured safety** — teams claim "it's safe" from a handful of happy-path examples, with no honest accuracy number, no regression gate, and an LLM-judge trusted at a magic `0.5`.

`finhelp-guard` addresses both: **enforceable guardrails** on every reply, and a **calibrated, CI-gated evaluation** that is explicit about what it can and cannot certify.

## What you get

- **Three guardrail rails** — `no_advice`, `groundedness`, `pii` — behind one simple `(draft, contexts) -> RailResult` contract.
- **An enforcing gate** — a blocked reply is *physically unsendable*, routed to a human; nothing is advisory.
- **A working tool-calling agent** (`--triage`) with a mocked CRM, so there's a real system-under-test; runs end-to-end in CI with 0 keys.
- **A statistically-honest eval** — confidence-interval gating (Wilson), per-rail + gate-level precision/recall, McNemar regression test, dev/held-out split.
- **Judge calibration** — ROC / PR-AUC / ECE + per-judge operating points, plus a Cohen's-κ gold-set workflow.
- **Authorization, budgets, and a hash-chained audit log** for regulated ops.
- **Composes real OSS** — [Guardrails AI](https://github.com/guardrails-ai/guardrails), [rank_bm25](https://github.com/dorianbrown/rank_bm25), [LangGraph](https://github.com/langchain-ai/langgraph) — behind stable contracts, with deterministic fallbacks so CI is keyless.

## Risks it handles

Explicit threat coverage — each risk maps to a mechanism and where it lives. Residual risks are documented, not hidden, in [LIMITATIONS.md](LIMITATIONS.md).

| Risk / threat | How it's handled | Where |
|---|---|---|
| **Unlicensed investment advice** | `no_advice` rail: EN/ES advice-language patterns + LLM-judge for paraphrase/intent; returns a compliant deflection | `rails/no_advice.py` |
| **Hallucinated / ungrounded claims** (wrong fee, limit, timeframe) | `groundedness` rail: anchored numeric-claim matching + faithfulness judge for no-number claims | `rails/groundedness.py` |
| **PII leakage in a reply** (email / phone / card / IBAN) | `pii` rail: regex + Luhn on every outbound reply | `rails/pii.py` |
| **Cross-account data access** (broken auth / prompt injection) | Authorization enforced in the **tool layer, below the model** — tools may only touch the ticket's own account | `agent._run_tool` |
| **Prompt injection** | Tool-layer authorization + input/step budgets + output rails; injected instructions can't grant access | `agent.py` |
| **Blocked content being sent anyway** | Enforced gate — `sent_reply=None` on block; no code path emits text unless the gate passed | `agent.py` |
| **Malformed / adversarial model output** | Fail-safe — unparseable output *escalates to a human*, never ships a gate-passing platitude | `agent.py` |
| **Cost / latency blowup, tool loops** | Budgets: per-call timeout + retry, `max_steps`, tool-call de-dup, capped input/history | `agent.py`, `models.py` |
| **Undetected quality regressions** | CI eval gate on confidence-interval bounds + paired McNemar version compare | `evals/run_evals.py` |
| **Guardrail drift / over-blocking** | Judge calibration (ROC/PR/ECE) + per-judge thresholds instead of a hard-coded 0.5 | `evals/calibrate.py` |
| **No decision trail for auditors** | Append-only, **hash-chained** audit log per decision (account, tools, gate verdict, route, latency) | `audit.py` |

## Quickstart (0 API keys, 0 spend)

```bash
pip install -r requirements-dev.txt
python -m finhelp_guard --triage        # tool-calling triage agent, end-to-end (scripted model)
python -m finhelp_guard --triage --live # same agent, real LLM (Azure/OpenAI/Nebius/Ollama)
python -m finhelp_guard --demo          # just the guardrail gate on 3 canned drafts
python evals/run_evals.py               # eval gate (GREEN) + held-out report + precision/recall
python evals/run_evals.py --compare     # paired McNemar: full vs regressed rails
python evals/calibrate.py --judge grounded   # judge threshold sweep + ROC/PR/AUC/ECE
pytest -q                               # 48 unit tests, keyless
ruff check finhelp_guard evals tests    # lint

# run the same rails inside the real Guardrails AI framework:
pip install -r requirements-integration.txt && pytest -q tests/test_guardrails_integration.py
```

The offline path is pure-Python — demo, evals, and tests **reproduce the scorecard with no keys and no cost**. CI runs two lanes: a fast keyless **unit** lane (lint + tests + eval gate) and an **integration** lane that runs the rails inside a real `Guard()`.

## The working agent

`--triage` runs a real **tool-calling loop** over synthetic tickets: look up the account, search the KB, optionally open a follow-up ticket, draft a reply — then the **guardrail gate wraps the output** and routes it. A full trace is written to [`traces/`](traces/); every decision is audited.

```
T-1: How much is the withdrawal fee and how long does a withdrawal take?
  tools: [lookup_account, search_kb]   gate: ✅ PASS   route: mark_ready
  reply: The withdrawal fee is $5 and withdrawals are processed within 2 business days.

T-3: Should I buy Tesla with my balance right now?
  tools: [lookup_account]              gate: 🛑 no_advice   route: human_review
  reply: I can't provide personalized investment advice ... consult a licensed financial advisor.
```

The loop is **model-agnostic**: `--triage` uses a deterministic scripted model (CI, 0 keys); `--triage --live` swaps in a real LLM via the same interface. Tools (`finhelp_guard/tools.py`) are a **mocked CRM/ticketing backend** — in production they become a Salesforce Service Cloud / Zendesk client behind the same signatures, no agent change.

> **✅ Verified against a real model** — the agent + judge were run against `Qwen/Qwen3-30B-A3B-Instruct-2507` via Nebius ([docs/live-run.md](docs/live-run.md)). The live run *surfaced real bugs that then drove fixes*: a cross-account data leak (→ authorization below the model), a wrongly-flagged CRM balance (→ tool outputs count as grounding), and the groundedness judge over-blocking (→ layered policy).

## How it works

### Architecture (the `--triage` path)
```
ticket → [tool-calling loop: lookup_account · search_kb · create_followup_ticket]
       → draft → guardrail gate [no_advice · groundedness · pii]
       → route: mark_ready (sendable) | human_review (blocked, sent_reply=None)
       → hash-chained audit log
```
Authorization is enforced inside the tools; the gate is enforcing (not advisory); unparseable output escalates. The LangGraph 1.x variant of the pipeline is in `finhelp_guard/graph.py`.

### The three rails
| Rail | Prevents | Offline detector (built) | Live judge (swap-in) |
|---|---|---|---|
| `no_advice` | unlicensed personalized advice | EN+ES advice patterns gated on a financial-instrument token; compliant deflection | `LLMJudge` (DeepEval `MisuseMetric`) |
| `groundedness` | inventing a fee/limit/timeframe | **anchored** numeric-claim matching (value equality, not substring) vs. retrieved context | `LLMJudge` (Ragas `Faithfulness`) |
| `pii` | emitting email / phone / card / IBAN | regex + Luhn on the outbound reply | Presidio |

The live judge today is a thin structured-output prompt (`models.LLMJudge`); DeepEval/Ragas/Presidio are **documented swap-ins behind the same contracts, not current dependencies**. Deliberate offline limits (no-number & cross-fact groundedness, paraphrase/other-language advice, obfuscated PII) are what the live judge / Presidio close — see [LIMITATIONS.md](LIMITATIONS.md).

### One definition, three runtimes
The rail logic is written once and runs (1) as the dependency-free **offline gate** (CI), (2) inside a real **Guardrails AI `Guard()`** (`guardrails_adapter.py`, integration lane), and (3) behind an **LLM judge**. You pick the stack; the rules stay identical.

## Evaluation & calibration

The honest measurement is the point. Two design choices a reviewer should push on:

**1. The gate decides on the confidence-interval bound, not the point estimate** (Wilson lower bound ≥ floor for recall; upper bound ≤ ceiling for false-refusal). You can only certify what your eval size supports — and it says so.

**2. `dev` (gated) vs `held-out` (adversarial, reported)** — the deterministic rails are *expected* to underperform on held-out, and do:
```
  DEV (gated):     advice_recall 1.000 [0.758,1.000]  grounded_recall 1.000 [0.722,1.000]  false_refusal 0.000 [0.000,0.215]
  HELD-OUT (adv.): advice_recall 0.000 [0.000,0.390]  grounded_recall 0.000 [0.000,0.561]   # paraphrase / no-number slip past regex
```
`--compare` runs an exact paired **McNemar** test between rail versions (regression test). Gate-level **precision/recall/F1** is reported, not just recall.

**Judge calibration, per judge** (`evals/calibrate.py --judge {advice,grounded}`): sweeps the threshold, reports **ROC / PR-AUC / ECE**, and picks the operating point (max recall s.t. a false-refusal ceiling), applied via `FINHELP_ADVICE_THRESHOLD` / `FINHELP_GROUNDED_THRESHOLD`. Honestly: the advice judge is trivially separable in-distribution (AUC 1.0 — not a hard result); the **groundedness judge is genuinely imperfect (ROC-AUC ≈ 0.84, ECE ≈ 0.11)**. The Cohen's-κ **gold-set workflow** is built in [`data/gold/`](data/gold/README.md); the remaining input is ~2h of human labeling — until then calibration uses interim author labels and is illustrative.

## Adversarial review — risks found & fixed

Put through **four rounds of adversarial red-teaming** + live stress tests: **~30 issues fixed**, **~10 residuals documented** ([LIMITATIONS.md](LIMITATIONS.md)). Each fixed item is a risk a team skipping the red-team would ship.

| Category | Fixed | Flagship example (real, verified failure) |
|---|---|---|
| Security | ~8 | Cross-account data leak → authorization below the model; advisory gate → enforcing; unaudited path → audited |
| Evaluation & calibration | ~10 | Decorative CI (gated on point estimate) → interval gate; judge over-blocking 10/14 → layered policy; one global threshold that broke the other judge → per-judge; PR-AUC math bug |
| Correctness / robustness | ~6 | Groundedness substring bug ($3 "grounded" by $30) → anchored matching; escalate-on-unparseable; code-fence-robust parsing |
| Honesty / consistency | ~6 | Stale/contradictory metrics, overclaimed integrations, empty "gold set" claim — all corrected; standing limitations register added |

## Configuration

Operational knobs (rollback / feature-flags) — see [CONTRIBUTING.md](CONTRIBUTING.md):

| Env var | Effect |
|---|---|
| `FINHELP_DISABLE_RAILS=pii` | Hot-disable a rail without a deploy (`active_rails()`) |
| `FINHELP_ADVICE_THRESHOLD` / `FINHELP_GROUNDED_THRESHOLD` | Per-judge operating points from calibration |
| `FINHELP_LLM_TIMEOUT` | Per-call model timeout (seconds) |
| `FINHELP_AUDIT_LOG` | Audit-log path |
| `NEBIUS_API_KEY` / `AZURE_OPENAI_*` / `OPENAI_BASE_URL` | Live model provider (see `.env.example`) |

## Limitations & roadmap

Honesty is a feature: the full residual-risk register is in **[LIMITATIONS.md](LIMITATIONS.md)** and the team-ownable work streams in **[ROADMAP.md](ROADMAP.md)**. Headlines: the groundedness judge needs a stronger prompt/model; the gold set needs human labels; the eval is small-n / ~50-50 prevalence; obfuscated PII needs Presidio; the audit log is hash-chained but not OS-enforced WORM.

## Contributing · License · Data

- **Contributing:** PR-per-change against `main`, CI (lint + both test lanes) green — see [CONTRIBUTING.md](CONTRIBUTING.md). Changes are logged in [CHANGELOG.md](CHANGELOG.md). Key design decisions in [`docs/adr/`](docs/adr/).
- **License:** code MIT.
- **Data:** committed KB and eval sets are **self-authored synthetic** (no third-party dataset redistributed). The live pipeline can optionally pull public datasets (MASSIVE — CC BY 4.0; Bitext — CDLA-Sharing-1.0) at runtime — see [`NOTICE`](NOTICE). No real customer data, no broker branding.
