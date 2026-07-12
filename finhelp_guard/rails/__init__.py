import os

from .base import GateOutcome, Judge, Rail, RailResult, run_gate
from .groundedness import groundedness_rail
from .no_advice import no_advice_rail
from .pii import pii_rail

DEFAULT_RAILS = [no_advice_rail, groundedness_rail, pii_rail]


def active_rails():
    """Runtime rail set, minus any disabled via env — the rollback/feature-flag knob
    (e.g. FINHELP_DISABLE_RAILS=pii to hot-disable the PII rail without a deploy).
    Evals/tests use DEFAULT_RAILS directly so they always exercise the full set."""
    disabled = {x.strip() for x in os.getenv("FINHELP_DISABLE_RAILS", "").split(",") if x.strip()}
    return [r for r in DEFAULT_RAILS if r.name not in disabled]


__all__ = [
    "GateOutcome", "Judge", "Rail", "RailResult", "run_gate",
    "groundedness_rail", "no_advice_rail", "pii_rail", "DEFAULT_RAILS", "active_rails",
]
