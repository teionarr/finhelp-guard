"""Generate a stratified, UNLABELLED candidate set for human gold labeling.

Usage:  python evals/make_gold.py
Writes data/gold/candidates.jsonl (no labels) + a CSV template. Two annotators then
copy the template to annotator_a.jsonl / annotator_b.jsonl and fill `label` per the
RUBRIC, blind to each other. `kappa.py` then measures their agreement.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "gold"

# id -> difficulty stratum for the adversarial held-out items.
_STRATUM = {
    "ho-adv-01": "paraphrase", "ho-adv-02": "paraphrase", "ho-adv-03": "paraphrase",
    "ho-adv-04": "cross-lingual", "ho-adv-05": "pronoun", "ho-adv-06": "homoglyph",
    "ho-grnd-01": "no-number", "ho-grnd-02": "cross-fact", "ho-grnd-03": "no-number",
    "ho-ok-01": "benign", "ho-ok-02": "benign-boundary",
}


def _load(name):
    return [json.loads(l) for l in (ROOT / "data" / name).read_text().splitlines() if l.strip()]


def main() -> int:
    GOLD.mkdir(parents=True, exist_ok=True)
    items = []
    for src, name in (("dev", "eval_dev.jsonl"), ("heldout", "eval_heldout.jsonl")):
        for d in _load(name):
            items.append({
                "id": d["id"], "source": src,
                "stratum": _STRATUM.get(d["id"], "in-distribution"),
                "category": d["category"], "lang": d["lang"],
                "query": d["query"], "draft": d["draft"],
                # NOTE: author's must_block kept ONLY as a hidden reference, not shown to annotators.
            })
    (GOLD / "candidates.jsonl").write_text("\n".join(json.dumps(i) for i in items) + "\n")

    # Annotator-facing template deliberately OMITS category/stratum — those are near-perfect
    # label proxies and would bias the blind labeling (and inflate kappa).
    with open(GOLD / "labeling_template.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "lang", "query", "draft", "label(block|allow)", "notes"])
        for i in items:
            w.writerow([i["id"], i["lang"], i["query"], i["draft"], "", ""])

    # Empty per-annotator stubs (fill `label` per data/gold/RUBRIC.md).
    for who in ("annotator_a", "annotator_b"):
        p = GOLD / f"{who}.jsonl"
        if not p.exists():
            p.write_text("\n".join(json.dumps({"id": i["id"], "label": ""}) for i in items) + "\n")

    by_stratum = {}
    for i in items:
        by_stratum[i["stratum"]] = by_stratum.get(i["stratum"], 0) + 1
    print(f"wrote {len(items)} candidates to {GOLD}/candidates.jsonl")
    print("strata:", by_stratum)
    print("next: two annotators fill data/gold/annotator_{a,b}.jsonl per RUBRIC.md, blind; then run kappa.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
