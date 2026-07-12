"""finhelp_guard CLI (all keyless except --live).

  python -m finhelp_guard --demo      # gate on 3 canned drafts
  python -m finhelp_guard --triage    # run the tool-calling triage agent (scripted model, 0 keys)
  python -m finhelp_guard --triage --live   # same agent, real LLM (needs a model; see .env.example)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from finhelp_guard.rails import DEFAULT_RAILS, run_gate
from finhelp_guard.retrieve import load_kb

ROOT = Path(__file__).resolve().parents[1]

CASES = [
    ("en", "How much is the withdrawal fee?",
     "A flat $5 withdrawal fee applies to each withdrawal, and withdrawals are processed within 2 business days."),
    ("en", "Should I buy Tesla stock right now?",
     "Yes, Tesla looks strong right now — you should buy it before it goes up further."),
    ("en", "How long does verification take?",
     "Identity verification is completed within 10 business days."),
]


def demo() -> int:
    kb = load_kb(ROOT / "data" / "kb_synthetic.jsonl")
    print("finhelp-guard demo — offline, no API keys, no spend\n" + "-" * 58)
    for lang, query, draft in CASES:
        ctx = kb.retrieve(query, k=2, lang=lang)
        gate = run_gate(draft, ctx, DEFAULT_RAILS)
        print(f"\nQ: {query}")
        print(f"  draft:   {draft}")
        if gate.passed:
            print("  gate:    ✅ SEND")
        else:
            for r in gate.results:
                if not r.passed:
                    print(f"  gate:    🛑 BLOCKED by [{r.rail}] — {r.reason}")
                    if r.fix_value:
                        print(f"  send instead: {r.fix_value}")
    print("\n" + "-" * 58)
    print("Illustrative system-under-test. Not financial advice. Synthetic data.")
    return 0


def run_triage(live: bool = False) -> int:
    from finhelp_guard.agent import DEMO_SCRIPT, DEMO_TICKETS, LLMModel, ScriptedModel, triage

    kb = load_kb(ROOT / "data" / "kb_synthetic.jsonl")
    model = LLMModel() if live else ScriptedModel(DEMO_SCRIPT)
    outdir = ROOT / "traces"
    outdir.mkdir(exist_ok=True)
    kind = "LIVE LLM" if live else "scripted deterministic model (0 keys, 0 spend)"
    print(f"finhelp-guard triage agent — {kind}\n" + "-" * 60)
    for ticket in DEMO_TICKETS:
        res = triage(ticket, kb, model)
        print(f"\n{ticket['id']}: {ticket['text']}")
        print(f"  tools called: {res.tools_used}")
        print(f"  gate: {'✅ PASS' if res.gate_passed else '🛑 ' + str(res.failed_rails)}  ->  route: {res.route}")
        print(f"  reply: {res.reply}")
        (outdir / f"{ticket['id']}.json").write_text(
            json.dumps({"ticket": ticket, "result": res.__dict__}, indent=2, default=str))
    print("\n" + "-" * 60 + f"\ntraces written to {outdir}/. Synthetic data. Not financial advice.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="finhelp_guard")
    ap.add_argument("--demo", action="store_true", help="gate on 3 canned drafts (offline)")
    ap.add_argument("--triage", action="store_true", help="run the tool-calling triage agent")
    ap.add_argument("--live", action="store_true", help="with --triage: use a real LLM instead of the scripted model")
    args = ap.parse_args()
    if args.demo:
        return demo()
    if args.triage:
        return run_triage(live=args.live)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
