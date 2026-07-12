"""Groundedness rail.

Failure it prevents: the draft states a fee, limit, or timeframe that is NOT in
the retrieved knowledge base — a confidently-wrong answer to a customer.

Offline (this module): extract concrete claim tokens (currency amounts,
percentages, timeframes) from the draft, canonicalise each to a typed value, and
require it to appear in the *set* of claims extracted from the retrieved context.
This is anchored value matching, NOT substring matching — so `$3` is not
"grounded" by `$30`, and `2 days` is not grounded by `12 days`.

KNOWN, DELIBERATE limitations of this offline stand-in (why the live judge exists):
  - It only checks *numeric* claims; a no-number fabrication ("withdrawals are
    instant and free") is not caught here.
  - It does not bind a number to its subject, so a right number attached to the
    wrong fact (cross-fact) can still pass if that number appears elsewhere in
    the retrieved context. Sentence-level claim entailment (the live
    Ragas/DeepEval faithfulness judge) is what closes both gaps.
Empty retrieved context -> insufficient evidence -> block (never auto-"grounded").
"""
from __future__ import annotations

import re
from typing import List, Optional, Set, Tuple

from .base import Judge, Rail, RailResult

Claim = Tuple[str, ...]  # a typed, canonical claim, e.g. ("money","USD",5.0) or ("time",2.0,"day")

_CURRENCY = {"$": "USD", "€": "EUR", "£": "GBP", "usd": "USD", "eur": "EUR", "gbp": "GBP"}
_UNIT = {
    "day": "day", "days": "day", "dia": "day", "dias": "day", "día": "day", "días": "day",
    "hour": "hour", "hours": "hour", "hora": "hour", "horas": "hour",
    "minute": "minute", "minutes": "minute", "min": "minute", "mins": "minute",
    "week": "week", "weeks": "week", "semana": "week", "semanas": "week",
    "month": "month", "months": "month", "mes": "month", "meses": "month",
}

_MONEY_SYMBOL_FIRST = re.compile(r"([$€£]|usd|eur|gbp)\s?(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
_MONEY_AMOUNT_FIRST = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s?([$€£]|usd|eur|gbp)", re.IGNORECASE)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")
_TIME = re.compile(
    r"(\d+)\s?(?:business\s+)?"
    r"(days?|d[ií]as?|hours?|horas?|minutes?|mins?|weeks?|semanas?|months?|meses)\b",
    re.IGNORECASE,
)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def claims(text: str) -> Set[Claim]:
    out: Set[Claim] = set()
    for sym, amt in _MONEY_SYMBOL_FIRST.findall(text):
        out.add(("money", _CURRENCY[sym.lower()], _num(amt)))
    for amt, sym in _MONEY_AMOUNT_FIRST.findall(text):
        out.add(("money", _CURRENCY[sym.lower()], _num(amt)))
    for v in _PERCENT.findall(text):
        out.add(("pct", _num(v)))
    for n, unit in _TIME.findall(text):
        out.add(("time", _num(n), _UNIT[unit.lower()]))
    return out


def _detector(draft: str, contexts: List[str], judge: Optional[Judge]) -> RailResult:
    # Offline numeric check (this is the deterministic stand-in's whole scope).
    draft_claims = claims(draft)
    if draft_claims:
        if not contexts:
            return RailResult("groundedness", False,
                              "reply states figures but no context was retrieved — insufficient evidence")
        ungrounded = [c for c in draft_claims if c not in claims(" ".join(contexts))]
        if ungrounded:
            return RailResult("groundedness", False,
                              f"claim(s) not supported by context: {sorted(map(str, ungrounded))}")

    # Live faithfulness judge (Ragas/DeepEval) — evaluates the WHOLE reply, so it
    # also catches no-number fabrications ("instant and free") the numeric check
    # can't see. Negated question to match the judge's "high = concern present".
    if judge is not None:
        score, why = judge.score(
            "Does the reply contain any claim that is NOT supported by the provided context?",
            draft, contexts,
        )
        return (RailResult("groundedness", False, f"judge: {why}") if score >= 0.5
                else RailResult("groundedness", True, "judge: all claims supported"))

    # Offline, no judge: numeric claims (if any) matched. A no-number fabrication
    # is NOT caught here — the documented limitation the live judge closes.
    if not draft_claims:
        return RailResult("groundedness", True, "no concrete numeric claim to verify (offline)")
    return RailResult("groundedness", True, "all concrete numeric claims matched a context claim")


groundedness_rail = Rail(name="groundedness", fn=_detector)
