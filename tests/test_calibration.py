"""Calibration harness: Cohen's kappa + ROC/PR/AUC/ECE/sweep/operating-point.

Keyless — the judge scores are read from a committed file produced by a real run
(data/gold/judge_scores_advice.jsonl), so the calibration is CI-reproducible."""
import json
import math
from pathlib import Path

from finhelp_guard import calibration
from finhelp_guard.config import advice_judge_threshold, grounded_judge_threshold
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


def test_per_judge_thresholds_are_independent(monkeypatch):
    assert advice_judge_threshold() == 0.5 and grounded_judge_threshold() == 0.5
    monkeypatch.setenv("FINHELP_ADVICE_THRESHOLD", "0.9")
    # advice threshold moves; groundedness does NOT (no cross-contamination — the bug we fixed)
    assert advice_judge_threshold() == 0.9 and grounded_judge_threshold() == 0.5


def test_average_precision_is_one_on_separable_data():
    pairs = [(0.9, True), (1.0, True), (0.1, False), (0.0, False)]
    assert math.isclose(calibration.average_precision(pairs), 1.0, abs_tol=1e-9)


def test_threshold_actually_flips_a_decision(monkeypatch):
    # The load-bearing property: a calibrated threshold must change a real gate decision.
    from finhelp_guard.models import LLMJudge
    from finhelp_guard.rails import groundedness_rail

    class _Mid:
        def invoke(self, messages):
            class _R:
                content = '{"score": 0.7, "reason": "possibly unsupported"}'
            return _R()

    j = LLMJudge(_Mid())
    draft, ctx = "Withdrawals clear quickly.", ["Withdrawals are processed within 2 business days."]
    assert not groundedness_rail.check(draft, ctx, judge=j).passed          # default 0.5: 0.7 -> block
    monkeypatch.setenv("FINHELP_GROUNDED_THRESHOLD", "0.8")
    assert groundedness_rail.check(draft, ctx, judge=j).passed              # 0.8: 0.7 -> allow (flipped)
