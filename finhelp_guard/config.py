"""Runtime config for the rails.

The judge threshold is the operating point chosen by calibration (evals/calibrate.py)
against the human gold set. It defaults to 0.5 and is overridable via env so a
calibrated value can be applied without a code change:  export FINHELP_JUDGE_THRESHOLD=0.6
"""
from __future__ import annotations

import os


def judge_threshold(default: float = 0.5) -> float:
    try:
        return float(os.getenv("FINHELP_JUDGE_THRESHOLD", default))
    except ValueError:
        return default
