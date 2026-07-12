# ADR 0002 — Layered policy: deterministic rails first, LLM judge only where blind

**Status:** accepted (revised after a live run)

**Context.** An early version let the LLM judge run on every reply. Live testing
(docs/live-run.md) showed the groundedness judge overriding correctly-grounded
numeric replies — gate precision collapsed to ~4/14 on benign items. High recall
was an illusion of over-blocking.

**Decision.** Compose the two as a **layered policy**, not an ensemble vote:
1. The deterministic rail is the **high-precision** layer. When it has a verdict on
   the numeric claims (grounded / ungrounded), we trust it and do **not** call the judge.
2. The judge is invoked **only where the deterministic detector is blind** — no-number
   fabrications, paraphrased/other-language advice the regex misses.

**Consequences.** DEV gate-level precision recovered to 0.917 (FP 2/36) with recall 1.0,
held-out precision 1.0, while the judge still recovers held-out advice recall 0→1.0. The
remaining cross-fact miss (right number, wrong fact) is a documented limitation that needs
subject-level claim binding (ROADMAP). The judge threshold (0.5) is not yet calibrated
against a human gold set — that is the top open eval item.
