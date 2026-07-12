"""Run finhelp-guard's rails through the real Guardrails AI framework.

The same rail logic that powers the dependency-free offline gate is exposed here
as genuine `guardrails` Validators, so in a Guardrails-AI shop these plug into a
standard `Guard()` (and could be published to the Guardrails Hub) with no rewrite.

This module imports `guardrails`, so it is optional — the core offline path never
touches it. Install with `pip install -r requirements-integration.txt`.

    from finhelp_guard.guardrails_adapter import build_guard
    guard = build_guard()
    outcome = guard.validate(draft, metadata={"contexts": retrieved})
    outcome.validation_passed  # bool
"""
from __future__ import annotations

from typing import Dict, List, Optional

from guardrails import Guard
from guardrails.validators import (
    FailResult,
    PassResult,
    ValidationResult,
    Validator,
    register_validator,
)

from .rails.groundedness import groundedness_rail
from .rails.no_advice import no_advice_rail


def _validator_from_rail(rail, name: str):
    """Wrap one of our rails as a Guardrails Validator (reuses identical logic)."""

    @register_validator(name=name, data_type="string")
    class _RailValidator(Validator):
        def validate(self, value: str, metadata: Optional[Dict] = None) -> ValidationResult:
            md = metadata or {}
            res = rail.fn(value, md.get("contexts", []), md.get("judge"))
            if res.passed:
                return PassResult()
            kwargs = {"error_message": res.reason}
            if res.fix_value is not None:
                kwargs["fix_value"] = res.fix_value
            return FailResult(**kwargs)

    _RailValidator.__name__ = f"{name.split('/')[-1]}_validator"
    return _RailValidator


NoUnlicensedAdvice = _validator_from_rail(no_advice_rail, "finhelp/no_unlicensed_advice")
Groundedness = _validator_from_rail(groundedness_rail, "finhelp/groundedness")


def _use(guard: Guard, validator_cls) -> Guard:
    # guardrails moved `on_fail` from Guard.use() onto the validator across
    # versions; support both so a minor upgrade can't break the lane.
    try:
        return guard.use(validator_cls(on_fail="noop"))   # newer: on_fail on the validator
    except TypeError:
        return guard.use(validator_cls, on_fail="noop")   # older: on_fail on .use()


def build_guard() -> Guard:
    """A real Guardrails `Guard` running both finhelp rails (on_fail=noop so the
    caller decides; a validator's on_fail can be 'fix' to auto-apply the
    deflection, or 'exception' to hard-block)."""
    guard = Guard()
    for validator_cls in (NoUnlicensedAdvice, Groundedness):
        guard = _use(guard, validator_cls)
    return guard


def validate_draft(draft: str, contexts: List[str], judge=None):
    """Validate a drafted reply through the real Guard; returns the ValidationOutcome."""
    return build_guard().validate(draft, metadata={"contexts": contexts, "judge": judge})
