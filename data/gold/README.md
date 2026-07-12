# Gold set + judge calibration

This is the harness that turns "author-labelled toy eval" into "calibrated against a
human gold set." **The code is done; the one remaining input is human labels.**

## Workflow

1. **Generate candidates** (done): `python evals/make_gold.py` → `candidates.jsonl`
   (47 items, stratified: in-distribution / paraphrase / cross-lingual / homoglyph /
   no-number / cross-fact / benign) + `labeling_template.csv`.
2. **Label, blind** — two annotators independently fill `annotator_a.jsonl` and
   `annotator_b.jsonl` (`{"id":..., "label":"block"|"allow"}`) per [`RUBRIC.md`](RUBRIC.md).
3. **Agreement** — `python evals/kappa.py` → Cohen's κ overall + per category.
   κ > 0.6 ("substantial") is what makes the labels defensible.
4. **Adjudicate** disagreements into the final gold label.
5. **Calibrate the judge** — `python evals/calibrate.py --live` runs the judge over
   the set and reports a threshold sweep + ROC/PR/AUC/ECE and the recommended operating
   point; `python evals/calibrate.py` reproduces it from committed scores (keyless).
6. **Apply** — `export FINHELP_JUDGE_THRESHOLD=<chosen>` (see `finhelp_guard/config.py`);
   the rails pick it up with no code change.

## Status
- ✅ rubric, stratified candidates, κ tool, calibration (ROC/PR/AUC/ECE/sweep/operating-point),
  threshold config wired into the rails, a committed real-scores file for CI reproducibility.
- ▢ **human labels** (`annotator_a/b.jsonl` are empty stubs) — ~2h for two people.

`judge_scores_advice.jsonl` holds real advice-judge scores over the advice+benign drafts
(interim author labels until the human gold lands — the calibration code is identical).
