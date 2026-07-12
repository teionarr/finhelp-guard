"""Judge calibration: ROC / PR / AUC / ECE + operating-point selection.

Pure functions over a list of (score, label) pairs, where `label=True` means the
item SHOULD be blocked (a positive) and `score` in [0,1] is the judge's concern
score. A threshold `t` predicts "block" iff `score >= t`. So:
  - recall (TPR)      = caught positives
  - false_refusal (FPR) = benign items wrongly blocked
These run with no model and no keys, so the calibration is unit-testable and CI-reproducible
from a committed scores file (`evals/calibrate.py --scores ...`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

Pair = Tuple[float, bool]


def confusion_at(pairs: List[Pair], thr: float):
    tp = fp = fn = tn = 0
    for s, y in pairs:
        pred = s >= thr
        tp += int(pred and y)
        fp += int(pred and not y)
        fn += int((not pred) and y)
        tn += int((not pred) and not y)
    return tp, fp, fn, tn


def _rates(pairs: List[Pair], thr: float):
    tp, fp, fn, tn = confusion_at(pairs, thr)
    tpr = tp / (tp + fn) if (tp + fn) else 0.0            # recall
    fpr = fp / (fp + tn) if (fp + tn) else 0.0            # false-refusal
    prec = tp / (tp + fp) if (tp + fp) else 1.0
    f1 = 2 * prec * tpr / (prec + tpr) if (prec + tpr) else 0.0
    return tpr, fpr, prec, f1


def _thresholds(pairs: List[Pair]) -> List[float]:
    return sorted({0.0} | {s for s, _ in pairs} | {1.0 + 1e-9})


def roc_points(pairs: List[Pair]) -> List[Tuple[float, float]]:
    return sorted((_rates(pairs, t)[1], _rates(pairs, t)[0]) for t in _thresholds(pairs))


def pr_points(pairs: List[Pair]) -> List[Tuple[float, float]]:
    return sorted((_rates(pairs, t)[0], _rates(pairs, t)[2]) for t in _thresholds(pairs))


def auc(points: List[Tuple[float, float]]) -> float:
    pts = sorted(points)
    return sum((x1 - x0) * (y0 + y1) / 2 for (x0, y0), (x1, y1) in zip(pts, pts[1:]))


def ece(pairs: List[Pair], bins: int = 10) -> float:
    """Expected calibration error: mean |accuracy - confidence| over score bins."""
    n = len(pairs)
    if not n:
        return float("nan")
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        bucket = [(s, y) for s, y in pairs if (lo <= s < hi or (b == bins - 1 and s == 1.0))]
        if not bucket:
            continue
        conf = sum(s for s, _ in bucket) / len(bucket)
        acc = sum(1 for _, y in bucket if y) / len(bucket)
        total += (len(bucket) / n) * abs(acc - conf)
    return total


@dataclass
class OperatingPoint:
    threshold: float
    recall: float
    false_refusal: float
    precision: float
    f1: float


def sweep(pairs: List[Pair]) -> List[OperatingPoint]:
    rows = []
    for t in _thresholds(pairs):
        tpr, fpr, prec, f1 = _rates(pairs, t)
        rows.append(OperatingPoint(round(t, 4), tpr, fpr, prec, f1))
    return rows


def pick_operating_point(pairs: List[Pair], max_false_refusal: float) -> Optional[OperatingPoint]:
    """Max recall subject to false_refusal <= ceiling (lower threshold => more recall
    and more false-refusal, so take the smallest threshold that still satisfies the ceiling)."""
    feasible = [op for op in sweep(pairs) if op.false_refusal <= max_false_refusal]
    return max(feasible, key=lambda op: (op.recall, -op.threshold)) if feasible else None


def report(pairs: List[Pair], max_false_refusal: float = 0.10) -> str:
    roc_auc = auc(roc_points(pairs))
    pr_auc = auc(pr_points(pairs))
    op = pick_operating_point(pairs, max_false_refusal)
    lines = [
        f"n={len(pairs)}  positives={sum(1 for _, y in pairs if y)}  "
        f"ROC-AUC={roc_auc:.3f}  PR-AUC={pr_auc:.3f}  ECE={ece(pairs):.3f}",
        "  thr    recall  false_refusal  precision   F1",
    ]
    for op_row in sweep(pairs):
        lines.append(f"  {op_row.threshold:<5.2f}  {op_row.recall:.3f}   "
                     f"{op_row.false_refusal:.3f}          {op_row.precision:.3f}    {op_row.f1:.3f}")
    if op:
        lines.append(f"\n  -> operating point (max recall s.t. false_refusal<={max_false_refusal:.2f}): "
                     f"threshold={op.threshold:.2f}  recall={op.recall:.3f}  "
                     f"false_refusal={op.false_refusal:.3f}  precision={op.precision:.3f}")
        lines.append(f"     apply with:  export FINHELP_JUDGE_THRESHOLD={op.threshold:.2f}")
    else:
        lines.append(f"\n  -> no threshold satisfies false_refusal<={max_false_refusal:.2f} on this data")
    return "\n".join(lines)
