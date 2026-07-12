"""Support-triage agent: a real tool-calling loop with the guardrail gate wrapped
around its output, an append-only audit trail, and enforced (not advisory) blocking.

The loop is model-agnostic: a `Model` returns a ToolCall, a Finalize, or an
Escalate on each step.
  - `ScriptedModel`: deterministic, runs the entire loop in CI with 0 keys/spend.
  - `LLMModel`: a real chat model (Azure/OpenAI/Nebius/Ollama), for `--triage --live`.

Tier-1 safety properties enforced here (see the red-team findings in docs/):
  - **Authorization**: tools may only touch the ticket's OWN account (no cross-account
    reads), enforced in the tool layer below the model — the prompt cannot override it.
  - **Enforced gate**: a blocked reply has `sent_reply=None` — there is no code path
    that emits text unless the gate passed.
  - **Fail-safe parsing**: unparseable model output escalates to a human, it does not
    ship a gate-passing platitude.
  - **Budgets**: capped input, truncated history, de-duplicated tool calls, bounded steps.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Union

from . import tools as T
from .audit import audit_decision
from .rails import DEFAULT_RAILS, run_gate

MAX_TICKET_CHARS = 4000
MAX_HISTORY_STEPS = 8


@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Finalize:
    reply: str


@dataclass
class Escalate:
    reason: str


Action = Union[ToolCall, Finalize, Escalate]


class Model(Protocol):
    def act(self, ticket: Dict, history: List[Dict]) -> Action: ...


@dataclass
class TriageResult:
    ticket_id: str
    reply: str                    # text surfaced (draft if clean, deflection/draft if blocked)
    route: str                    # "mark_ready" (clean) | "human_review" (flagged/escalated)
    gate_passed: bool
    failed_rails: List[str]
    tools_used: List[str]
    trace: List[Dict]
    sent: bool = False            # true only when the reply may actually be sent
    sent_reply: Optional[str] = None  # the ONLY sendable text; None when blocked

    def summary(self) -> str:
        return (f"[{self.ticket_id}] tools={self.tools_used} "
                f"gate={'PASS' if self.gate_passed else 'FAIL ' + str(self.failed_rails)} "
                f"-> {self.route}")


def _tool_facts(name: str, result: Dict) -> str:
    """Turn an AUTHORIZED tool result into grounding evidence (cross-account results
    never reach here — they're denied in _run_tool)."""
    if name == "lookup_account":
        return (f"Account {result.get('id')}: balance ${result.get('balance_usd', 0):.2f}; "
                f"verified={result.get('verified')}; can_withdraw={result.get('can_withdraw')}.")
    if name == "create_followup_ticket":
        return f"Opened follow-up ticket {result.get('followup_ticket_id')} (status {result.get('status')})."
    return str(result)


def _run_tool(call: ToolCall, retriever, ticket: Dict) -> Any:
    owner = ticket.get("account_id", "")
    if call.name in ("lookup_account", "create_followup_ticket"):
        requested = call.args.get("account_id") or owner
        # AUTHORIZATION (below the model): only the ticket's own account.
        if requested != owner:
            return {"error": "unauthorized", "denied": True,
                    "detail": f"tool {call.name} may only access the ticket's own account ({owner}), not {requested}"}
        if call.name == "lookup_account":
            return T.lookup_account(owner)
        return T.create_followup_ticket(owner, call.args.get("summary", ""))
    if call.name == "search_kb":
        return retriever.retrieve(call.args.get("query", ticket.get("text", "")), k=2, lang=ticket.get("lang", "en"))
    return {"error": f"unknown tool {call.name}"}


def triage(ticket: Dict, retriever, model: Model, judge=None, max_steps: int = 6) -> TriageResult:
    ticket = {**ticket, "text": str(ticket.get("text", ""))[:MAX_TICKET_CHARS]}  # input cap
    history: List[Dict] = []
    trace: List[Dict] = []
    contexts: List[str] = []
    tools_used: List[str] = []
    seen_calls: set = set()

    def finish(res: TriageResult) -> TriageResult:
        audit_decision(ticket, res)   # append-only audit log for every decision
        return res

    for step in range(max_steps):
        action = model.act(ticket, history[-MAX_HISTORY_STEPS:])

        if isinstance(action, Escalate):
            trace.append({"step": step, "type": "escalate", "reason": action.reason})
            return finish(TriageResult(ticket["id"], "", "human_review", False, ["escalated"],
                                       tools_used, trace, sent=False, sent_reply=None))

        if isinstance(action, ToolCall):
            key = (action.name, json.dumps(action.args, sort_keys=True, default=str))
            if key in seen_calls:                     # de-dup: block tool-call amplification
                result: Any = {"error": "duplicate tool call skipped", "denied": True}
            else:
                seen_calls.add(key)
                result = _run_tool(action, retriever, ticket)
            if isinstance(result, list):                       # KB snippets
                contexts.extend(result)
            elif isinstance(result, dict) and "error" not in result:   # authorized tool facts
                contexts.append(_tool_facts(action.name, result))
            history.append({"tool": action.name, "args": action.args, "result": result})
            tools_used.append(action.name)
            trace.append({"step": step, "type": "tool_call", "name": action.name,
                          "args": action.args, "result": result})
            continue

        # Finalize -> run the guardrail gate over the draft + everything retrieved.
        gate = run_gate(action.reply, contexts, DEFAULT_RAILS, judge=judge)
        passed = gate.passed
        route = "mark_ready" if passed else "human_review"
        # `reply` is the surfaced field. On block it is a compliant deflection (if a rail
        # offers one) or a withheld notice — NEVER the raw blocked draft (which lives only
        # in the trace/audit record for the human reviewer). `sent_reply` is the only sendable.
        if passed:
            display = action.reply
        else:
            display = next((r.fix_value for r in gate.results if not r.passed and r.fix_value),
                           f"[blocked by {gate.failed_rails}; routed to human review — draft withheld]")
        sent_reply = action.reply if passed else None  # ENFORCED: no sendable text when blocked
        trace.append({"step": step, "type": "finalize", "draft": action.reply,
                      "gate_passed": passed, "failed_rails": gate.failed_rails,
                      "route": route, "sent": passed, "sent_reply": sent_reply})
        return finish(TriageResult(ticket["id"], display, route, passed, gate.failed_rails,
                                   tools_used, trace, sent=passed, sent_reply=sent_reply))

    trace.append({"step": max_steps, "type": "aborted", "reason": "max_steps reached"})
    return finish(TriageResult(ticket["id"], "", "human_review", False, ["max_steps"],
                               tools_used, trace, sent=False, sent_reply=None))


def _extract_json(raw: str) -> dict:
    """Robust: strip code fences / prose and parse the first JSON object."""
    s = str(raw).strip()
    if "```" in s:
        s = s.split("```", 2)[1]
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start:end + 1]
    return json.loads(s)


class ScriptedModel:
    """Deterministic model: replays a fixed action sequence per ticket id."""

    def __init__(self, scripts: Dict[str, List[Action]]):
        self._scripts = scripts
        self._idx: Dict[str, int] = {}

    def act(self, ticket: Dict, history: List[Dict]) -> Action:
        tid = ticket["id"]
        i = self._idx.get(tid, 0)
        self._idx[tid] = i + 1
        seq = self._scripts.get(tid, [Finalize("I'm not able to help with that here.")])
        return seq[i] if i < len(seq) else Finalize("(no further action)")


class LLMModel:
    """Live model that chooses the next action via structured JSON. Model-agnostic
    (works with a local Ollama/vLLM server for a keyless real-LLM run)."""

    def __init__(self, model=None):
        from .models import chat_model
        self._model = model or chat_model()

    def act(self, ticket: Dict, history: List[Dict]) -> Action:
        tool_docs = json.dumps(T.TOOL_SCHEMAS)
        sys = ("You are a support-ops triage agent for a regulated broker. Use tools to "
               "gather facts about the CUSTOMER'S OWN account only, then draft a reply grounded "
               "ONLY in tool/KB results. Never give investment advice. Respond with ONE JSON "
               'object: {"tool":"<name>","args":{...}} or {"final":"<reply>"}. Tools: ' + tool_docs)
        convo = json.dumps({"ticket": ticket, "history": history})[:8000]  # bounded prompt
        raw = self._model.invoke([("system", sys), ("human", convo)]).content
        try:
            d = _extract_json(raw)
        except Exception:
            # Fail safe: unparseable output escalates to a human (never ships a platitude).
            return Escalate(reason=f"unparseable model output: {str(raw)[:120]}")
        if "tool" in d:
            return ToolCall(str(d["tool"]), d.get("args", {}) if isinstance(d.get("args"), dict) else {})
        return Finalize(str(d.get("final", "")))


# --- Demo tickets + a deterministic script for the keyless run -----------------

DEMO_TICKETS: List[Dict] = [
    {"id": "T-1", "account_id": "AC-1001", "lang": "en",
     "text": "How much is the withdrawal fee and how long does a withdrawal take?"},
    {"id": "T-2", "account_id": "AC-2002", "lang": "en",
     "text": "Why can't I withdraw my money?"},
    {"id": "T-3", "account_id": "AC-1001", "lang": "en",
     "text": "Should I buy Tesla with my balance right now?"},
]

DEMO_SCRIPT: Dict[str, List[Action]] = {
    "T-1": [
        ToolCall("lookup_account", {"account_id": "AC-1001"}),
        ToolCall("search_kb", {"query": "withdrawal fee and time"}),
        Finalize("The withdrawal fee is $5 and withdrawals are processed within 2 business days."),
    ],
    "T-2": [
        ToolCall("lookup_account", {"account_id": "AC-2002"}),
        ToolCall("search_kb", {"query": "account verification"}),
        ToolCall("create_followup_ticket", {"account_id": "AC-2002", "summary": "KYC not complete; withdrawal blocked"}),
        Finalize("Your account isn't verified yet, so withdrawals are on hold. Identity "
                 "verification is usually completed within 3 business days after you upload a "
                 "valid government ID and proof of address. I've opened a ticket for our team."),
    ],
    "T-3": [
        ToolCall("lookup_account", {"account_id": "AC-1001"}),
        Finalize("You should buy Tesla now with your balance — it looks strong."),
    ],
}
