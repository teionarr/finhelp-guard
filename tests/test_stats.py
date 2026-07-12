"""Known-answer tests for the statistics — the numbers a reviewer will probe."""
import math

import pytest

from finhelp_guard.stats import mcnemar_exact, wilson_interval


def test_wilson_stays_in_bounds_at_extremes():
    # Wald would give a zero-width or out-of-range interval here; Wilson must not.
    lo, hi = wilson_interval(100, 100).low, wilson_interval(100, 100).high
    assert hi == 1.0 and 0.0 < lo < 1.0
    z = wilson_interval(0, 100)
    assert z.point == 0.0 and z.low < 1e-9 and 0.0 < z.high < 1.0


def test_wilson_known_value():
    ci = wilson_interval(50, 100)
    assert ci.point == 0.5
    # Standard Wilson 95% interval for 50/100 is ~[0.404, 0.596].
    assert math.isclose(ci.low, 0.4038, abs_tol=1e-3)
    assert math.isclose(ci.high, 0.5962, abs_tol=1e-3)


def test_wilson_rejects_bad_input():
    with pytest.raises(ValueError):
        wilson_interval(5, 3)


def test_mcnemar_no_discordant_pairs_is_not_significant():
    r = mcnemar_exact(0, 0)
    assert r.p_value == 1.0 and not r.significant


def test_mcnemar_known_value():
    # b=8, c=1: two-sided exact p = 2 * (C(9,0)+C(9,1)) / 2^9 = 20/512.
    r = mcnemar_exact(8, 1)
    assert math.isclose(r.p_value, 20 / 512, abs_tol=1e-6)
    assert r.significant


def test_mcnemar_symmetric_in_bc():
    assert mcnemar_exact(8, 1).p_value == mcnemar_exact(1, 8).p_value


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("statsmodels") is None,
    reason="statsmodels not installed",
)
def test_cross_check_statsmodels():
    from statsmodels.stats.contingency_tables import mcnemar as sm_mcnemar
    from statsmodels.stats.proportion import proportion_confint

    lo, hi = proportion_confint(50, 100, alpha=0.05, method="wilson")
    ci = wilson_interval(50, 100)
    assert math.isclose(ci.low, lo, abs_tol=1e-6)
    assert math.isclose(ci.high, hi, abs_tol=1e-6)

    sm = sm_mcnemar([[0, 8], [1, 0]], exact=True)
    assert math.isclose(mcnemar_exact(8, 1).p_value, sm.pvalue, abs_tol=1e-6)
