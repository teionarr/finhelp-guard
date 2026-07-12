"""PII / data-minimisation rail on the OUTBOUND reply.

A regulated broker's support agent must not emit raw PII (emails, phone numbers,
payment-card or IBAN numbers). This is a deterministic, keyless detector (regex +
Luhn) — Presidio is the drop-in for the live path behind the same RailResult
contract. Account balances the customer asks about are their own and are handled
by authorization, not flagged here. KNOWN LIMITATION: obfuscated PII ("john [at] x
dot com", digits split across tokens) evades regex — the Presidio/NER swap closes
that (see LIMITATIONS.md).
"""
from __future__ import annotations

import re
from typing import List, Optional

from .base import Judge, Rail, RailResult

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_CARDISH = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
# Phone: require actual phone structure (a leading + or grouping separators), so a
# bare reference/confirmation number ("100200300") is NOT flagged as a phone.
_PHONEISH = re.compile(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)")


def _is_phone(s: str) -> bool:
    digits = sum(c.isdigit() for c in s)
    has_structure = s.startswith("+") or any(c in " ().-" for c in s)
    return 9 <= digits <= 15 and has_structure


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
    if any(_is_phone(m.group()) for m in _PHONEISH.finditer(draft)):
        found.append("phone")
    if found:
        return RailResult("pii", False, f"outbound reply contains PII: {sorted(set(found))}")
    return RailResult("pii", True, "no PII detected in the reply")


pii_rail = Rail(name="pii", fn=_detector)
