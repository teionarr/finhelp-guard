"""No-unlicensed-investment-advice rail.

Failure it prevents: the assistant answers "should I buy TSLA?" with a
personalized recommendation — an unlicensed-advice line a regulated broker
cannot cross.

Offline (this module): a deterministic detector of advice-*giving* language in
the draft. Live: swap `judge` for DeepEval MisuseMetric(domain="financial
services") — same RailResult contract, no graph change.

On fail we don't just block: `fix_value` is a compliant deflection the agent can
send instead, so the rail is a repair, not only a veto.
"""
from __future__ import annotations

import re
from typing import List, Optional

from .base import Judge, Rail, RailResult

# Advice-*giving* patterns in the drafted reply (what the bot must never emit).
# English + Spanish covered deterministically; further languages need the live
# LLM judge (documented stretch) — the honest cross-lingual parity gap.
_ADVICE_GIVING = [
    # English
    r"\byou should (buy|sell|invest|short|go long|allocate)\b",
    r"\bi (recommend|suggest|advise)\b.*\b(buy|sell|invest|stock|crypto|position)\b",
    r"\b(is|it'?s) a (good|great|strong) (buy|sell|investment|time to (buy|sell))\b",
    r"\b(guaranteed|risk-free|sure) (returns?|profit|gains?)\b",
    r"\b(will|going to) (definitely|certainly|surely) (go up|rise|moon|increase)\b",
    r"\bput your (money|savings|pension) (in|into)\b",
    # Spanish
    r"\bdeber[ií]as? (comprar|vender|invertir|poner)\b",
    r"\b(recomiendo|sugiero|aconsejo)\b",
    r"\b(retornos?|ganancias?|beneficios?) (garantizados?|sin riesgo|seguros?)\b",
    r"\bva a (subir|bajar) seguro\b",
    r"\b(subir[aá]|bajar[aá]) seguro\b",
]

_DEFLECTION = (
    "I can't provide personalized investment advice or tell you whether to buy or "
    "sell a specific asset. I can share factual, educational information and point "
    "you to our learning resources. For advice tailored to your situation, please "
    "consult a licensed financial advisor. Capital is at risk."
)


def _detector(draft: str, contexts: List[str], judge: Optional[Judge]) -> RailResult:
    text = draft.lower()
    for pat in _ADVICE_GIVING:
        if re.search(pat, text):
            return RailResult(
                rail="no_advice",
                passed=False,
                reason=f"advice-giving language matched /{pat}/",
                fix_value=_DEFLECTION,
            )
    # Live mode: an LLM judge catches paraphrased advice the regex misses.
    if judge is not None:
        score, why = judge.score(
            "Does this reply give personalized investment advice or guarantee returns?",
            draft, contexts,
        )
        if score >= 0.5:
            return RailResult("no_advice", False, f"judge: {why}", _DEFLECTION)
    return RailResult("no_advice", True, "no advice-giving language detected")


no_advice_rail = Rail(name="no_advice", fn=_detector)
