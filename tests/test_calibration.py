"""Calibration harness: Cohen's kappa + ROC/PR/AUC/ECE/sweep/operating-point.

Keyless — the judge scores are read from a committed file produced by a real run
(data/gold/judge_scores_advice.jsonl), so the calibration is CI-reproducible."""
import json
import math
from pathlib import Path

from finhelp_guard import calibration
from finhelp_guard.config import judge_threshold
from finhelp_guard.stats import cohens_kappa

ROOT = Path(__file__).resolve().parents[1]


def test_cohens_kappa_known_value():
    # a=[1,1,0,0], b=[1,0,0,0]: po=0.75, pe=0.5 -> kappa=0.5
    assert math.isclose(cohens_kappa([1, 1, 0, 0], [1, 0, 0, 0]), 0.5, abs_tol=1e-9)
    assert cohens_kappa([1, 0, 1], [1, 0, 1]) == 1.0  # perfect agreement


def test_perfect_separation_auc_is_one():
    pairs = [(0.9, True), (0.95, True), (0.1, False), (0.0, False)]
    assert math.isclose(calibration.auc(calibration.roc_points(pairs)), 1.0, abs_tol=1e-9)


def test_operating_point_respects_ceiling():
    pairs = [(0.9, True), (0.8, True), (0.4, False), (0.2, False)]
    op = calibration.pick_operating_point(pairs, max_false_refusal=0.0)
    assert op is not None and op.false_refusal == 0.0 and op.recall == 1.0


def test_ece_in_bounds():
    pairs = [(0.9, True), (0.1, False), (0.8, True), (0.2, False)]
    assert 0.0 <= calibration.ece(pairs) <= 1.0


def test_confusion_at():
    pairs = [(0.9, True), (0.1, False)]
    assert calibration.confusion_at(pairs, 0.5) == (1, 0, 0, 1)


def test_report_reproduces_from_committed_scores():
    path = ROOT / "data" / "gold" / "judge_scores_advice.jsonl"
    pairs = [(float(d["score"]), bool(d["label"]))
             for d in (json.loads(l) for l in path.read_text().splitlines() if l.strip())]
    out = calibration.report(pairs, max_false_refusal=0.10)
    assert "operating point" in out and "ROC-AUC" in out


def test_judge_threshold_env(monkeypatch):
    assert judge_threshold() == 0.5
    monkeypatch.setenv("FINHELP_JUDGE_THRESHOLD", "0.9")
    assert judge_threshold() == 0.9
