"""No-unlicensed-investment-advice rail.

Failure it prevents: the assistant answers "should I buy TSLA?" with a
personalized recommendation — an unlicensed-advice line a regulated broker
cannot cross.

Offline (this module): a deterministic detector. "Strong" cues (guaranteed
returns, put your pension into ...) fire on their own; generic advice verbs
(you should buy/sell ...) fire only when a financial-instrument token is also
present, which cuts false refusals on benign text ("you should buy insurance",
"sell your old phone", "a great investment *platform*").

KNOWN, DELIBERATE limitation (why the live judge exists): the regex cannot cover
the open-ended space of advice phrasings — paraphrases like "TSLA is a screaming
bargain", "load up on crypto", or advice with only a pronoun ("you should buy
it") slip through, and further languages are uncovered. Live, swap `judge` for
DeepEval MisuseMetric(domain="financial services") — same RailResult contract.

On fail, `fix_value` is a compliant deflection the agent can send instead.
"""
from __future__ import annotations

import re
from typing import List, Optional

from .base import Judge, Rail, RailResult

# A concrete financial instrument / asset must be present for the generic verb
# patterns to fire. Deliberately excludes "investment" so marketing copy
# ("great investment platform") doesn't trip it.
_FIN = re.compile(
    r"\b(stocks?|shares?|equit(?:y|ies)|etfs?|funds?|bonds?|crypto|bitcoin|btc|"
    r"ethereum|eth|coins?|tokens?|portfolios?|pension|forex|commodit(?:y|ies)|"
    r"positions?|assets?|tesla|tsla|nvidia|nvda|apple|aapl|bitcoin)\b",
    re.IGNORECASE,
)

# Fire regardless of instrument token — these are inherently investment advice.
_ADVICE_STRONG = [
    r"\b(guaranteed|risk-free|sure) (returns?|profit|gains?)\b",
    r"\bput your (money|savings|pension) (in|into)\b",
    r"\b(retornos?|ganancias?|beneficios?) (garantizados?|sin riesgo|seguros?)\b",
    r"\bva a (subir|bajar) seguro\b",
    r"\b(subir[aá]|bajar[aá]) seguro\b",
]

# Fire only if a financial instrument token co-occurs in the draft.
_ADVICE_VERB = [
    r"\byou should (buy|sell|invest|short|go long|allocate)\b",
    r"\bi (recommend|suggest|advise)\b.*\b(buy|sell|invest|short|allocate)\b",
    r"\b(is|it'?s) a (good|great|strong) (buy|sell|investment|time to (buy|sell))\b",
    r"\b(great|good) time to (buy|sell)\b",
    r"\bdeber[ií]as? (comprar|vender|invertir|poner)\b",
    r"\b(recomiendo|sugiero|aconsejo)\b",
]

_DEFLECTION = (
    "I can't provide personalized investment advice or tell you whether to buy or "
    "sell a specific asset. I can share factual, educational information and point "
    "you to our learning resources. For advice tailored to your situation, please "
    "consult a licensed financial advisor. Capital is at risk."
)


def _detector(draft: str, contexts: List[str], judge: Optional[Judge]) -> RailResult:
    text = draft.lower()
    has_fin = bool(_FIN.search(text))
    for pat in _ADVICE_STRONG:
        if re.search(pat, text):
            return RailResult("no_advice", False, f"advice language matched /{pat}/", _DEFLECTION)
    if has_fin:
        for pat in _ADVICE_VERB:
            if re.search(pat, text):
                return RailResult("no_advice", False, f"advice-on-instrument matched /{pat}/", _DEFLECTION)
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
