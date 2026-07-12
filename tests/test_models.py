"""Live-judge contract tests, with a fake chat model (no deps, no keys).

Proves the LLMJudge parses correctly AND that both rails wire the judge with the
right polarity — the bug a reviewer worried the untested live layer might hide.
"""
from finhelp_guard.models import LLMJudge
from finhelp_guard.rails import groundedness_rail, no_advice_rail


class _FakeMsg:
    def __init__(self, content):
        self.content = content


class _FakeModel:
    def __init__(self, content):
        self._content = content

    def invoke(self, messages):
        return _FakeMsg(self._content)


def test_judge_parses_score():
    j = LLMJudge(_FakeModel('{"score": 0.9, "reason": "gives advice"}'))
    score, reason = j.score("q", "text", [])
    assert score == 0.9 and reason == "gives advice"


def test_judge_fails_safe_on_garbage():
    j = LLMJudge(_FakeModel("not json at all"))
    score, _ = j.score("q", "t", [])
    assert score == 1.0  # unparseable -> treat the concern as present


def test_groundedness_polarity_high_score_blocks():
    # Judge says "a claim is NOT supported" (score high). Correct behaviour: BLOCK.
    j = LLMJudge(_FakeModel('{"score": 0.8, "reason": "unsupported claim"}'))
    r = groundedness_rail.check("Withdrawals are instant.", ["some context"], judge=j)
    assert not r.passed


def test_groundedness_polarity_low_score_passes():
    j = LLMJudge(_FakeModel('{"score": 0.1, "reason": "all supported"}'))
    r = groundedness_rail.check("Withdrawals take a while.", ["some context"], judge=j)
    assert r.passed


def test_no_advice_judge_catches_paraphrase():
    # A paraphrase the regex misses; the live judge flags it -> BLOCK.
    j = LLMJudge(_FakeModel('{"score": 0.9, "reason": "implicit advice"}'))
    r = no_advice_rail.check("That one is a screaming bargain.", [], judge=j)
    assert not r.passed and r.fix_value
