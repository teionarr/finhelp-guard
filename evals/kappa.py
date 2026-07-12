"""Cohen's kappa between two annotators' gold labels.

Usage:  python evals/kappa.py [a.jsonl] [b.jsonl]
Each file is JSONL of {"id":..., "label":"block"|"allow"}. Reports kappa overall and
per category (categories read from data/gold/candidates.jsonl).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from finhelp_guard.stats import cohens_kappa  # noqa: E402

GOLD = ROOT / "data" / "gold"


def _load(p):
    return {d["id"]: d["label"] for d in (json.loads(l) for l in Path(p).read_text().splitlines() if l.strip())}


def main() -> int:
    a = _load(sys.argv[1] if len(sys.argv) > 1 else GOLD / "annotator_a.jsonl")
    b = _load(sys.argv[2] if len(sys.argv) > 2 else GOLD / "annotator_b.jsonl")
    cats = {d["id"]: d["category"] for d in
            (json.loads(l) for l in (GOLD / "candidates.jsonl").read_text().splitlines() if l.strip())}
    ids = [i for i in a if i in b and a[i] and b[i]]          # both labeled
    if not ids:
        print("No labeled items yet. Fill annotator_a.jsonl / annotator_b.jsonl per RUBRIC.md.")
        return 0
    print(f"labeled items: {len(ids)}")
    print(f"overall kappa: {cohens_kappa([a[i] for i in ids], [b[i] for i in ids]):.3f}")
    for cat in sorted(set(cats.get(i, '?') for i in ids)):
        sub = [i for i in ids if cats.get(i) == cat]
        if len(sub) >= 2:
            print(f"  {cat:12s} kappa: {cohens_kappa([a[i] for i in sub], [b[i] for i in sub]):.3f}  (n={len(sub)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
