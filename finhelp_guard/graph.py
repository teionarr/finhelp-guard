"""Live LangGraph 1.x pipeline.

Same rails and gate as the offline path — this just wires them behind real model
calls, structured output, and a human-in-the-loop interrupt. Requires the
`requirements.txt` deps and model credentials; the offline demo/evals/tests do NOT
import this module.

    from finhelp_guard.graph import build_graph
    app = build_graph()
    app.invoke({"query": "How much is the withdrawal fee?", "lang": "en"},
               config={"configurable": {"thread_id": "t1"}})
"""
from __future__ import annotations

from pathlib import Path
from typing import List, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from .audit import audit_record
from .models import LLMJudge, chat_model
from .rails import DEFAULT_RAILS, run_gate
from .retrieve import load_kb

ROOT = Path(__file__).resolve().parents[1]


class Draft(BaseModel):
    answer: str = Field(description="the reply to the customer, grounded in the context")


class State(TypedDict, total=False):
    query: str
    lang: str
    contexts: List[str]
    draft: str
    gate_passed: bool
    failed_rails: List[str]
    final: str


def build_graph(kb_path: str | Path = ROOT / "data" / "kb_synthetic.jsonl"):
    kb = load_kb(kb_path)
    llm = chat_model()
    drafter = llm.with_structured_output(Draft)
    judge = LLMJudge(llm)

    def detect_language(s: State) -> State:
        return {"lang": s.get("lang") or "en"}

    def retrieve(s: State) -> State:
        return {"contexts": kb.retrieve(s["query"], k=2, lang=s.get("lang"))}

    def draft(s: State) -> State:
        ctx = "\n".join(s.get("contexts") or [])
        d: Draft = drafter.invoke(
            "You are a support agent for a regulated broker. Answer ONLY from the "
            "context; never give investment advice. If the context lacks the answer, "
            f"say so.\n\nContext:\n{ctx}\n\nCustomer: {s['query']}")
        return {"draft": d.answer}

    def guardrail_gate(s: State) -> State:
        out = run_gate(s["draft"], s.get("contexts") or [], DEFAULT_RAILS, judge=judge)
        audit_record({"path": "graph", "lang": s.get("lang"), "gate_passed": out.passed,
                      "failed_rails": out.failed_rails,
                      "route": "mark_ready" if out.passed else "human_review"})
        # If a rail offers a repair (e.g. the compliant deflection), use it.
        repaired = s["draft"]
        for r in out.results:
            if not r.passed and r.fix_value:
                repaired = r.fix_value
        return {"gate_passed": out.passed, "failed_rails": out.failed_rails, "draft": repaired}

    def human_review(s: State) -> State:
        # A rail flagged this reply. Structural HITL: a person must approve before
        # anything is sent. The graph pauses here and resumes with Command(resume=...).
        decision = interrupt({
            "needs_review": s["draft"],
            "failed_rails": s.get("failed_rails"),
        })
        return {"final": s["draft"] if decision == "approve" else ""}

    def mark_ready(s: State) -> State:
        # Clean + grounded + no-advice → eligible to send. A stricter regulated
        # deployment can still route these to review; that's a one-line change to
        # `route`, which is exactly why this is a real branch and not a straight edge.
        return {"final": s["draft"]}

    def route(s: State) -> str:
        return "mark_ready" if s.get("gate_passed") else "human_review"

    g = StateGraph(State)
    g.add_node("detect_language", detect_language)
    g.add_node("retrieve", retrieve)
    g.add_node("draft", draft)
    g.add_node("guardrail_gate", guardrail_gate)
    g.add_node("human_review", human_review)
    g.add_node("mark_ready", mark_ready)

    g.add_edge(START, "detect_language")
    g.add_edge("detect_language", "retrieve")
    g.add_edge("retrieve", "draft")
    g.add_edge("draft", "guardrail_gate")
    g.add_conditional_edges("guardrail_gate", route,
                            {"mark_ready": "mark_ready", "human_review": "human_review"})
    g.add_edge("mark_ready", END)
    g.add_edge("human_review", END)

    return g.compile(checkpointer=MemorySaver())
