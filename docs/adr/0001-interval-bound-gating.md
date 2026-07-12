# ADR 0001 — Gate on confidence-interval bounds, not point estimates

**Status:** accepted

**Context.** Eval sets are small and failure rates sit near 0/1. A point estimate
(e.g. "advice recall = 1.0 on 12 items") over-claims certainty and hides that the
true rate could be much lower.

**Decision.** The CI gate decides on the **Wilson** interval bound: recall must have
a lower bound ≥ floor; false-refusal an upper bound ≤ ceiling. We report Wilson over
Wald because Wald has poor coverage at small n / extreme p and can leave [0,1].

**Consequences.** The gate certifies only what the eval size supports — a demo cannot
certify a 100% floor, and the harness says so. Scaling the corpus (see ROADMAP) is the
way to tighten the certified bound, not relabelling.
