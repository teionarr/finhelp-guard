# Roadmap — how a small squad would carry this

The repo is a working slice with an honest boundary. This is how the remaining work
decomposes into team-ownable streams, and what's done vs. next in each.

### 1. Detectors & rails (owner: rails)
- ✅ no-advice (EN/ES), groundedness (anchored numeric), PII (email/phone/card-Luhn/IBAN)
- ▢ subject-level claim binding to kill the cross-fact miss (right number, wrong fact)
- ▢ more languages via the live judge; Presidio behind the PII contract

### 2. Evaluation & calibration (owner: eval)
- ✅ interval-bound gate, per-rail recall, gate-level precision/recall/F1, McNemar, dev/held-out split
- ▢ **human-adjudicated gold set + rubric + Cohen's κ** (top open item — turns "author-labelled" into defensible ground truth)
- ▢ judge threshold **sweep / ROC / PR + calibration (ECE)** to choose the operating point
- ▢ scale + stratify the corpus (category × language × difficulty) at realistic prevalence
- ▢ judge variance across repeated runs (LLM judges are noisy)

### 3. Agent & safety (owner: agent)
- ✅ tool-calling loop, tool-layer authorization, enforced gate, escalation on bad output, step/tool/input budgets
- ▢ multi-turn conversation memory (infra present via LangGraph `MemorySaver`; not yet demonstrated)
- ▢ richer tool surface (real CRM/ticketing client behind the mock's signatures)

### 4. Serving & observability (owner: platform)
- ✅ append-only JSONL audit log per decision; committed traces
- ▢ FastAPI `/triage` endpoint + Dockerfile so ops can call it
- ▢ real Langfuse spans; latency/cost per decision in the audit record

### 5. Ops adoption (owner: lead)
- ▢ threshold/policy config surfaced for compliance sign-off; runbook; on-call/rollback for the judge path

**Sequencing:** the gold set + judge calibration (stream 2) unblock every accuracy claim and
are the highest-value next work; the FastAPI/Docker slice (stream 4) is the cheapest way to
raise perceived production-readiness.
