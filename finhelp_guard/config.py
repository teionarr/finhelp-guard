"""Per-rail judge thresholds (the operating points chosen by calibration).

Each judge has its OWN threshold env var, because their score distributions differ —
applying the advice judge's operating point to the groundedness judge is a category
error that silently changes an unmeasured decision boundary (red-team finding).
Default 0.5; override per judge after calibrating that specific judge:

    export FINHELP_ADVICE_THRESHOLD=0.90       # from evals/calibrate.py --judge advice
    export FINHELP_GROUNDED_THRESHOLD=0.70     # from evals/calibrate.py --judge grounded
"""
from __future__ import annotations

import os


def _thr(var: str) -> float:
    try:
        return float(os.getenv(var, "0.5"))
    except ValueError:
        return 0.5


def advice_judge_threshold() -> float:
    return _thr("FINHELP_ADVICE_THRESHOLD")


def grounded_judge_threshold() -> float:
    return _thr("FINHELP_GROUNDED_THRESHOLD")
