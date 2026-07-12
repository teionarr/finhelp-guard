"""Support-triage agent: a real tool-calling loop with the guardrail gate wrapped
around its output, and a full trace.

The loop is model-agnostic: a `Model` returns either a ToolCall or a Finalize on
each step. Two implementations —
  - `ScriptedModel`: deterministic, runs the entire loop in CI with 0 keys/spend.
  - `LLMModel`: a real chat model (Azure/OpenAI/Ollama) via structured output,
    for `python -m finhelp_guard --live` (see models.chat_model()).
Same loop, same tools, same gate — you swap the brain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Union

from . import tools as T
from .rails import DEFAULT_RAILS, run_gate


@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Finalize:
    reply: str


Action = Union[ToolCall, Finalize]


class Model(Protocol):
    def act(self, ticket: Dict, history: List[Dict]) -> Action: ...


@dataclass
class TriageResult:
    ticket_id: str
    reply: str
    route: str                 # "mark_ready" (clean) | "human_review" (flagged)
    gate_passed: bool
    failed_rails: List[str]
    tools_used: List[str]
    trace: List[Dict]

    def summary(self) -> str:
        return (f"[{self.ticket_id}] tools={self.tools_used} "
                f"gate={'PASS' if self.gate_passed else 'FAIL ' + str(self.failed_rails)} "
                f"-> {self.route}")


def _run_tool(call: ToolCall, retriever, ticket: Dict) -> Any:
    if call.name == "lookup_account":
        return T.lookup_account(call.args.get("account_id") or ticket.get("account_id", ""))
    if call.name == "search_kb":
        return retriever.retrieve(call.args.get("query", ticket.get("text", "")), k=2, lang=ticket.get("lang", "en"))
    if call.name == "create_followup_ticket":
        return T.create_followup_ticket(call.args.get("account_id") or ticket.get("account_id", ""),
                                        call.args.get("summary", ""))
    return {"error": f"unknown tool {call.name}"}


def triage(ticket: Dict, retriever, model: Model, judge=None, max_steps: int = 6) -> TriageResult:
    history: List[Dict] = []
    trace: List[Dict] = []
    contexts: List[str] = []
    tools_used: List[str] = []

    for step in range(max_steps):
        action = model.act(ticket, history)

        if isinstance(action, ToolCall):
            result = _run_tool(action, retriever, ticket)
            if action.name == "search_kb" and isinstance(result, list):
                contexts.extend(result)
            history.append({"tool": action.name, "args": action.args, "result": result})
            tools_used.append(action.name)
            trace.append({"step": step, "type": "tool_call", "name": action.name,
                          "args": action.args, "result": result})
            continue

        # Finalize: run the guardrail gate over the draft + everything retrieved.
        gate = run_gate(action.reply, contexts, DEFAULT_RAILS, judge=judge)
        route = "mark_ready" if gate.passed else "human_review"
        reply = action.reply
        for r in gate.results:                       # apply a rail's repair if it offers one
            if not r.passed and r.fix_value:
                reply = r.fix_value
        trace.append({"step": step, "type": "finalize", "draft": action.reply,
                      "gate_passed": gate.passed, "failed_rails": gate.failed_rails,
                      "route": route, "sent_reply": reply})
        return TriageResult(ticket["id"], reply, route, gate.passed, gate.failed_rails, tools_used, trace)

    trace.append({"step": max_steps, "type": "aborted", "reason": "max_steps reached"})
    return TriageResult(ticket["id"], "", "human_review", False, ["max_steps"], tools_used, trace)


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
    """Live model (Azure/OpenAI/Ollama) that chooses the next action via structured
    output. Used only by `--live`; never run in CI. Model-agnostic so it works with
    a local Ollama/vLLM server for a keyless real-LLM run."""

    def __init__(self, model=None):
        from .models import chat_model
        self._model = model or chat_model()

    def act(self, ticket: Dict, history: List[Dict]) -> Action:
        import json
        tool_docs = json.dumps(T.TOOL_SCHEMAS)
        sys = ("You are a support-ops triage agent for a regulated broker. Use tools to "
               "gather facts, then draft a reply grounded ONLY in tool results. Never give "
               "investment advice. Respond with ONE JSON object: either "
               '{"tool": "<name>", "args": {...}} or {"final": "<reply>"}. Tools: ' + tool_docs)
        convo = json.dumps({"ticket": ticket, "history": history})
        raw = self._model.invoke([("system", sys), ("human", convo)]).content
        try:
            d = json.loads(raw)
        except Exception:
            return Finalize("I'll route this to a human colleague to be safe.")
        if "tool" in d:
            return ToolCall(d["tool"], d.get("args", {}))
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
    # Straightforward policy question: look up account, search KB, answer grounded.
    "T-1": [
        ToolCall("lookup_account", {"account_id": "AC-1001"}),
        ToolCall("search_kb", {"query": "withdrawal fee and time"}),
        Finalize("The withdrawal fee is $5 and withdrawals are processed within 2 business days."),
    ],
    # Blocked account: look up (not verified), search KB, open a follow-up, explain grounded.
    "T-2": [
        ToolCall("lookup_account", {"account_id": "AC-2002"}),
        ToolCall("search_kb", {"query": "account verification"}),
        ToolCall("create_followup_ticket", {"account_id": "AC-2002", "summary": "KYC not complete; withdrawal blocked"}),
        Finalize("Your account isn't verified yet, so withdrawals are on hold. Identity "
                 "verification is usually completed within 3 business days after you upload a "
                 "valid government ID and proof of address. I've opened a ticket for our team."),
    ],
    # Advice solicitation: the drafted reply crosses the line -> gate blocks -> deflection.
    "T-3": [
        ToolCall("lookup_account", {"account_id": "AC-1001"}),
        Finalize("You should buy Tesla now with your balance — it looks strong."),
    ],
}
