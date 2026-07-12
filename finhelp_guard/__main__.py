"""`python -m finhelp_guard --demo` — runs the pipeline offline, 0 keys, 0 spend.

Shows the guardrail gate doing its job on three cases: a benign grounded reply
(passes), an advice-seeking case (refused with a compliant deflection), and an
ungrounded fee (blocked).
"""
from __future__ import annotations

import argparse
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


def main() -> int:
    ap = argparse.ArgumentParser(prog="finhelp_guard")
    ap.add_argument("--demo", action="store_true", help="run the offline demo")
    args = ap.parse_args()
    if args.demo:
        return demo()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
