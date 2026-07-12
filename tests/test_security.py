"""Tier-1 safety properties: authorization, enforced gate, escalation, de-dup, PII, audit."""
import json
from pathlib import Path

from finhelp_guard.agent import (Escalate, Finalize, LLMModel, ScriptedModel, ToolCall,
                                 _run_tool, triage)
from finhelp_guard.rails import pii_rail, run_gate, DEFAULT_RAILS
from finhelp_guard.retrieve import load_kb

ROOT = Path(__file__).resolve().parents[1]
KB = load_kb(ROOT / "data" / "kb_synthetic.jsonl")


# --- Authorization (cross-account) ---
def test_cross_account_lookup_is_denied():
    r = _run_tool(ToolCall("lookup_account", {"account_id": "AC-1001"}), None, {"account_id": "AC-2002"})
    assert r.get("denied") and "unauthorized" in r["error"]


def test_own_account_lookup_is_allowed():
    r = _run_tool(ToolCall("lookup_account", {"account_id": "AC-2002"}), None, {"account_id": "AC-2002"})
    assert r.get("id") == "AC-2002"


def test_cross_account_data_never_reaches_reply(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHELP_AUDIT_LOG", str(tmp_path / "a.jsonl"))
    ticket = {"id": "SEC-1", "account_id": "AC-2002", "lang": "en", "text": "compare accounts"}
    model = ScriptedModel({"SEC-1": [
        ToolCall("lookup_account", {"account_id": "AC-1001"}),   # attacker tries another account
        Finalize("Here is what I found."),
    ]})
    res = triage(ticket, KB, model)
    # The other account's name/balance must not have entered grounding/reply.
    assert "Jordan" not in res.reply and "240" not in res.reply
    denied = [s for s in res.trace if s.get("type") == "tool_call" and s.get("result", {}).get("denied")]
    assert denied  # the cross-account call was denied


# --- Enforced gate: a blocked reply is not sendable ---
def test_blocked_reply_is_not_sendable(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHELP_AUDIT_LOG", str(tmp_path / "a.jsonl"))
    ticket = {"id": "ADV", "account_id": "AC-1001", "lang": "en", "text": "advice?"}
    model = ScriptedModel({"ADV": [Finalize("You should buy Tesla now with your stocks.")]})
    res = triage(ticket, KB, model)
    assert res.gate_passed is False and res.sent is False and res.sent_reply is None


# --- Escalation on unparseable model output (not a gate-passing platitude) ---
class _Garbage:
    def invoke(self, messages):
        class _R:
            content = "here is my reasoning, no json at all"
        return _R()


def test_unparseable_output_escalates(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHELP_AUDIT_LOG", str(tmp_path / "a.jsonl"))
    m = LLMModel(model=_Garbage())
    assert isinstance(m.act({"id": "x", "account_id": "AC-1001", "text": "hi"}, []), Escalate)
    res = triage({"id": "ESC", "account_id": "AC-1001", "lang": "en", "text": "hi"}, KB, m)
    assert res.route == "human_review" and res.sent is False


def test_json_extraction_handles_code_fences():
    m = LLMModel(model=_Garbage())
    from finhelp_guard.agent import _extract_json
    assert _extract_json('```json\n{"final": "ok"}\n```') == {"final": "ok"}


# --- PII rail ---
def test_pii_rail_blocks_email_and_card():
    assert not pii_rail.check("Reach me at john@example.com", []).passed
    assert not pii_rail.check("Your card 4111 1111 1111 1111 is on file", []).passed  # valid Luhn
    assert pii_rail.check("The withdrawal fee is $5 and takes 2 business days.", []).passed  # no PII


# --- Audit log ---
def test_audit_log_is_appended(tmp_path, monkeypatch):
    log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("FINHELP_AUDIT_LOG", str(log))
    ticket = {"id": "AUD", "account_id": "AC-1001", "lang": "en", "text": "hi"}
    triage(ticket, KB, ScriptedModel({"AUD": [Finalize("Card deposits are credited instantly.")]}))
    lines = log.read_text().strip().splitlines()
    rec = json.loads(lines[-1])
    assert rec["ticket_id"] == "AUD" and "input_sha256" in rec and "route" in rec


def test_audit_is_hash_chained(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHELP_AUDIT_LOG", str(tmp_path / "a.jsonl"))
    from finhelp_guard.audit import audit_record
    r1 = audit_record({"x": 1})
    r2 = audit_record({"x": 2})
    assert r1["hash"] and r2["prev_hash"] == r1["hash"] and r2["hash"] != r1["hash"]


def test_blocked_reply_field_is_not_the_raw_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHELP_AUDIT_LOG", str(tmp_path / "a.jsonl"))
    # A PII draft (no fix_value) must not surface the raw draft in `reply`.
    t = {"id": "PII", "account_id": "AC-1001", "lang": "en", "text": "x"}
    res = triage(t, KB, ScriptedModel({"PII": [Finalize("Reach me at leak@example.com")]}))
    assert res.sent_reply is None and "leak@example.com" not in res.reply
