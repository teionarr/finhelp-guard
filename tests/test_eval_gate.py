"""The CI regression gate: green by default, red when a rail regresses."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*args):
    return subprocess.run([sys.executable, str(ROOT / "evals" / "run_evals.py"), *args],
                          capture_output=True, text=True)


def test_baseline_gate_is_green():
    p = _run()
    assert p.returncode == 0, p.stdout + p.stderr
    assert "GREEN" in p.stdout


def test_injected_regression_turns_gate_red():
    p = _run("--inject-regression")
    assert p.returncode == 1
    assert "RED" in p.stdout and "advice_recall" in p.stdout
