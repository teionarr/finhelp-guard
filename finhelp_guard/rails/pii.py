"""PII / data-minimisation rail on the OUTBOUND reply.

A regulated broker's support agent must not emit raw PII (emails, phone numbers,
payment-card or IBAN numbers). This is a deterministic, keyless detector (regex +
Luhn) — Presidio is the drop-in for the live path behind the same RailResult
contract. Account balances the customer asks about are their own and are handled
by authorization, not flagged here.
"""
from __future__ import annotations

import re
from typing import List, Optional

from .base import Judge, Rail, RailResult

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_CARDISH = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_PHONEISH = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")


def _luhn(s: str) -> bool:
    digits = [int(c) for c in s if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _detector(draft: str, contexts: List[str], judge: Optional[Judge] = None) -> RailResult:
    found = []
    if _EMAIL.search(draft):
        found.append("email")
    if any(_luhn(m.group()) for m in _CARDISH.finditer(draft)):
        found.append("card")
    if _IBAN.search(draft):
        found.append("iban")
    for m in _PHONEISH.finditer(draft):
        if sum(c.isdigit() for c in m.group()) >= 9:   # avoid fees/timeframes
            found.append("phone")
            break
    if found:
        return RailResult("pii", False, f"outbound reply contains PII: {sorted(set(found))}")
    return RailResult("pii", True, "no PII detected in the reply")


pii_rail = Rail(name="pii", fn=_detector)
