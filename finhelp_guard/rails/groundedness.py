"""Groundedness rail.

Failure it prevents: the draft states a fee, limit, or timeframe that is NOT in
the retrieved knowledge base — a confidently-wrong answer to a customer.

Offline (this module): every concrete claim token in the draft (currency amounts,
percentages, and "N business days"-style figures) must appear in a retrieved
context. This is deliberately strict on *numbers*, which is where support-bot
hallucinations do real damage. Live: swap `judge` for Ragas Faithfulness /
DeepEval FaithfulnessMetric — same RailResult contract.
"""
from __future__ import annotations

import re
from typing import List, Optional

from .base import Judge, Rail, RailResult

# Concrete, checkable claim tokens (currency both symbol-first "$5" and
# amount-first "5 $"; English + Spanish timeframes).
_CLAIM_PATTERNS = [
    r"[$€£]\s?\d[\d,]*(?:\.\d+)?",                 # $5, £30
    r"\d[\d,]*(?:\.\d+)?\s?[$€£]",                 # 5 $, 30 €
    r"\d+(?:\.\d+)?\s?%",                          # percentages
    r"\b\d+\s?(?:business\s+)?days?\b",            # N (business) days
    r"\b\d+\s?(?:hours?|weeks?|months?)\b",
    r"\b\d+\s?(?:d[ií]as?(?:\s+h[aá]biles)?|horas?|semanas?|meses)\b",  # ES timeframes
]


def _normalize(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


def _claims(text: str) -> List[str]:
    out: List[str] = []
    for pat in _CLAIM_PATTERNS:
        out.extend(m.group(0) for m in re.finditer(pat, text, flags=re.IGNORECASE))
    return out


def _detector(draft: str, contexts: List[str], judge: Optional[Judge]) -> RailResult:
    haystack = _normalize(" ".join(contexts))
    ungrounded = [c for c in _claims(draft) if _normalize(c) not in haystack]
    if ungrounded:
        return RailResult(
            rail="groundedness",
            passed=False,
            reason=f"claim(s) not supported by retrieved context: {ungrounded}",
        )
    if judge is not None:
        score, why = judge.score(
            "Is every claim in the reply supported by the provided context?",
            draft, contexts,
        )
        if score < 0.5:
            return RailResult("groundedness", False, f"judge: {why}")
    return RailResult("groundedness", True, "all concrete claims grounded in context")


groundedness_rail = Rail(name="groundedness", fn=_detector)
