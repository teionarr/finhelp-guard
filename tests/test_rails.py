"""Rail behaviour tests — each asserts a concrete failure is caught."""
from finhelp_guard.rails import groundedness_rail, no_advice_rail, run_gate

CTX = ["A flat $5 withdrawal fee applies to each withdrawal, and withdrawals "
       "are processed within 2 business days."]


def test_no_advice_blocks_recommendation():
    r = no_advice_rail.check("You should buy Tesla now.", [])
    assert not r.passed and r.fix_value  # blocks and offers a compliant deflection


def test_no_advice_blocks_spanish():
    r = no_advice_rail.check("Deberia comprar Tesla ahora.", [])
    assert not r.passed


def test_no_advice_allows_compliant_deflection():
    r = no_advice_rail.check(
        "I can't advise whether to buy or sell any asset, but here are educational resources.", [])
    assert r.passed


def test_groundedness_blocks_invented_fee():
    r = groundedness_rail.check("The withdrawal fee is $12 and takes 7 business days.", CTX)
    assert not r.passed


def test_groundedness_allows_grounded_claim():
    r = groundedness_rail.check("The withdrawal fee is $5 and takes 2 business days.", CTX)
    assert r.passed


def test_gate_blocks_if_any_rail_fails():
    out = run_gate("You should buy $5 of Tesla.", CTX, [no_advice_rail, groundedness_rail])
    assert not out.passed and "no_advice" in out.failed_rails


def test_groundedness_substring_is_not_grounded():
    # $3 must NOT be "grounded" by $30 (the substring bug we fixed).
    assert not groundedness_rail.check("The fee is $3.", ["the minimum is $30"]).passed
    assert not groundedness_rail.check("It takes 2 days.", ["it takes 12 days"]).passed


def test_groundedness_blocks_figures_without_context():
    assert not groundedness_rail.check("The fee is $5.", []).passed


def test_groundedness_passes_reply_with_no_figures():
    # No numeric claim to verify (the documented no-digit limitation lives here).
    assert groundedness_rail.check("You can reset your password in Settings.", []).passed


def test_no_advice_ignores_benign_non_financial_text():
    assert no_advice_rail.check("You should buy travel insurance first.", []).passed
    assert no_advice_rail.check("Our great investment platform is easy to use.", []).passed
