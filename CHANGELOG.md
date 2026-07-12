# Changelog

This is a pre-1.0 project; the API may change. Breaking changes are flagged.

## [0.1.0]

Support-ops guardrail + eval harness with a tool-calling triage agent, verified against a
real model, hardened across four adversarial red-team rounds.

### Added
- Tool-calling triage agent (`--triage` / `--triage --live`) with mocked CRM tools, an
  enforced guardrail gate, and an append-only **hash-chained** audit log (now incl.
  `latency_ms` + `steps`).
- Rails: `no_advice`, `groundedness` (anchored numeric matching), `pii` (email/phone/card/IBAN).
- Eval: interval-bound gate, per-rail + gate-level precision/recall/F1, McNemar `--compare`,
  dev/held-out split; **per-judge calibration** harness (ROC/PR-AUC/ECE + operating point) and
  a Cohen's-κ gold-set workflow (`data/gold/`).
- Real OSS integrations: `rank_bm25` retrieval, Guardrails-AI adapter (integration CI lane).
- `active_rails()` rollback flag (`FINHELP_DISABLE_RAILS`); ruff lint in CI.
- Docs: ADRs, ROADMAP, LIMITATIONS, live-run transcript.

### ⚠️ Breaking (no external consumers yet)
- **Judge threshold split into per-judge env vars.** `FINHELP_JUDGE_THRESHOLD` (single global)
  is removed; use `FINHELP_ADVICE_THRESHOLD` and `FINHELP_GROUNDED_THRESHOLD`. The global was a
  bug: an advice-calibrated value silently governed the groundedness judge.
- `config.judge_threshold()` → `config.advice_judge_threshold()` / `grounded_judge_threshold()`.
- `TriageResult` gained `sent`, `sent_reply`, `latency_ms`, `steps`; on a block, `.reply` is now a
  deflection/withheld notice (never the raw draft) and `.sent_reply` is the only sendable text.
- `evals/calibrate.py` now takes `--judge {advice,grounded}`.

### Fixed (from the adversarial rounds — see README "risks found & fixed")
- Cross-account data leak (authorization now enforced below the model).
- Groundedness substring bug ($3 "grounded" by $30); judge over-blocking; PR-AUC math; PII
  false-positive on reference numbers; the `reply` footgun; unaudited graph path.
