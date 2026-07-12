"""Integration test: our rails running inside the real Guardrails AI framework.

Auto-skips when `guardrails` isn't installed (the fast unit lane), so it only
runs in the integration CI lane. Proves the same rail logic composes into a
standard `Guard()` — not just our own gate.
"""
import pytest

pytest.importorskip("guardrails")

from finhelp_guard.guardrails_adapter import build_guard, validate_draft  # noqa: E402

CTX = ["A flat $5 withdrawal fee applies to each withdrawal, and withdrawals "
       "are processed within 2 business days."]


def test_guard_blocks_advice():
    assert validate_draft("You should buy Tesla now.", []).validation_passed is False


def test_guard_passes_grounded_reply():
    assert validate_draft("The withdrawal fee is $5 and takes 2 business days.", CTX).validation_passed is True


def test_guard_blocks_ungrounded_reply():
    assert validate_draft("The withdrawal fee is $12.", CTX).validation_passed is False


def test_build_guard_composes_both_validators():
    # Behavioural check (robust to guardrails internals): one Guard enforces BOTH
    # rails — an advice violation and a groundedness violation are each caught.
    assert build_guard() is not None
    assert validate_draft("You should buy Tesla now.", []).validation_passed is False
    assert validate_draft("The fee is $999.", ["the fee is $5"]).validation_passed is False
