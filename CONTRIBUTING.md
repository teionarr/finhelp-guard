# Contributing

## Dev loop
```bash
pip install -r requirements-dev.txt
ruff check finhelp_guard evals tests      # lint (CI gate)
pytest -q                                  # 48 unit tests, keyless
python evals/run_evals.py                  # eval gate (must be GREEN)
```
The integration lane (`pip install -r requirements-integration.txt && pytest tests/test_guardrails_integration.py`)
runs the rails inside a real Guardrails-AI `Guard()`. Live runs need a model — see `.env.example`.

## Workflow
- **Changes should go through a PR against `main`**, one logical change per PR, with CI (lint +
  both test lanes) green. (The initial build was committed to `main` directly as a solo
  prototype; ongoing work should use PRs. Enable branch protection with
  `gh api -X PUT repos/:owner/finhelp-guard/branches/main/protection ...` if you want it enforced.)
- Update `CHANGELOG.md` for anything user-facing; flag breaking changes explicitly.
- New rails/judges plug in behind the `Rail` / `Judge` contracts (`finhelp_guard/rails/base.py`).

## Operational knobs (rollback / feature-flags)
- `FINHELP_DISABLE_RAILS=pii` — hot-disable a rail without a deploy (`active_rails()`).
- `FINHELP_ADVICE_THRESHOLD` / `FINHELP_GROUNDED_THRESHOLD` — per-judge operating points from calibration.
- `FINHELP_LLM_TIMEOUT`, `FINHELP_AUDIT_LOG` — request timeout, audit path.

Known limitations and residual risks are tracked honestly in [LIMITATIONS.md](LIMITATIONS.md).
