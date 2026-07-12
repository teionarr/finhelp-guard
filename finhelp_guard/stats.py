"""Honest small-sample statistics for eval reporting.

Implemented in pure Python on purpose: for a support-ops eval you are at small n
and rates near 0/1, where the choices below actually matter — so the harness
should *own* them rather than hide them behind a library call.

- Wilson score interval (not Wald): Wald has poor coverage at small n and near
  p=0 or p=1 and can fall outside [0,1]; Wilson stays in bounds.
- McNemar exact test (not a t-test): the two systems are scored on the *same*
  items, so outcomes are paired binary; McNemar conditions on the discordant
  pairs (b, c). We use the exact binomial form, correct at small counts.

`test_stats.py` cross-checks these against statsmodels when it is installed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Z_95 = 1.959963984540054  # two-sided 95%


@dataclass(frozen=True)
class Interval:
    point: float
    low: float
    high: float

    def __str__(self) -> str:  # e.g. "0.960 [0.881, 0.988]"
        return f"{self.point:.3f} [{self.low:.3f}, {self.high:.3f}]"


def wilson_interval(successes: int, n: int, z: float = Z_95) -> Interval:
    """Wilson score confidence interval for a binomial proportion."""
    if n == 0:
        return Interval(float("nan"), 0.0, 1.0)
    if successes < 0 or successes > n:
        raise ValueError("successes must be in [0, n]")
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom
    return Interval(p, max(0.0, center - margin), min(1.0, center + margin))


@dataclass(frozen=True)
class McNemarResult:
    b: int  # A pass, B fail
    c: int  # A fail, B pass
    p_value: float
    statistic: float  # discordant-pair count used

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05


def mcnemar_exact(b: int, c: int) -> McNemarResult:
    """Exact McNemar test on the discordant counts b and c.

    Under H0 each discordant pair is a fair coin flip; the two-sided exact
    p-value is the binomial tail for min(b, c) out of n = b + c at p = 0.5.
    """
    if b < 0 or c < 0:
        raise ValueError("b and c must be non-negative")
    n = b + c
    if n == 0:
        return McNemarResult(b, c, 1.0, 0.0)
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) * (0.5 ** n)
    p = min(1.0, 2.0 * tail)
    return McNemarResult(b, c, p, float(k))
