"""Rail contract.

A rail is a pure function of (draft, retrieved_contexts) -> RailResult, optionally
using an injected `judge` (an LLM in live mode; a deterministic stub offline).
This one seam is where a new rail plugs into the graph's guardrail gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol


@dataclass(frozen=True)
class RailResult:
    rail: str
    passed: bool
    reason: str = ""
    # Programmatic repair (e.g. append a disclaimer / strip an ungrounded claim).
    fix_value: Optional[str] = None


class Judge(Protocol):
    """LLM-as-judge in live mode; a deterministic stub offline.

    Returns a score in [0, 1] and a short reason for the given question.
    """

    def score(self, question: str, text: str, contexts: List[str]) -> tuple[float, str]:
        ...


@dataclass
class Rail:
    name: str
    fn: Callable[[str, List[str], Optional[Judge]], RailResult]

    def check(self, draft: str, contexts: List[str], judge: Optional[Judge] = None) -> RailResult:
        return self.fn(draft, contexts, judge)


@dataclass
class GateOutcome:
    passed: bool
    results: List[RailResult] = field(default_factory=list)

    @property
    def failed_rails(self) -> List[str]:
        return [r.rail for r in self.results if not r.passed]


def run_gate(draft: str, contexts: List[str], rails: List[Rail],
             judge: Optional[Judge] = None) -> GateOutcome:
    results = [rail.check(draft, contexts, judge) for rail in rails]
    return GateOutcome(passed=all(r.passed for r in results), results=results)
