"""The tool-calling triage agent, end-to-end with the deterministic model (0 keys)."""
from pathlib import Path

from finhelp_guard.agent import DEMO_SCRIPT, DEMO_TICKETS, ScriptedModel, triage
from finhelp_guard.retrieve import load_kb

ROOT = Path(__file__).resolve().parents[1]
KB = load_kb(ROOT / "data" / "kb_synthetic.jsonl")


def _ticket(tid):
    return next(t for t in DEMO_TICKETS if t["id"] == tid)


def _model():
    return ScriptedModel(DEMO_SCRIPT)  # fresh per run (holds per-ticket step state)


def test_policy_ticket_calls_tools_and_is_ready():
    r = triage(_ticket("T-1"), KB, _model())
    assert "lookup_account" in r.tools_used and "search_kb" in r.tools_used
    assert r.gate_passed and r.route == "mark_ready"


def test_blocked_account_opens_followup_ticket():
    r = triage(_ticket("T-2"), KB, _model())
    assert "create_followup_ticket" in r.tools_used
    assert r.gate_passed and r.route == "mark_ready"


def test_advice_draft_is_blocked_and_deflected():
    r = triage(_ticket("T-3"), KB, _model())
    assert not r.gate_passed and "no_advice" in r.failed_rails
    assert r.route == "human_review" and "licensed financial advisor" in r.reply


def test_trace_records_tool_calls_then_finalize():
    r = triage(_ticket("T-2"), KB, _model())
    types = [s["type"] for s in r.trace]
    assert types.count("tool_call") == 3 and types[-1] == "finalize"
