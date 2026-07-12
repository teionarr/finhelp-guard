"""Append-only, hash-chained audit trail — one line per triage decision.

Each record carries `prev_hash` + its own `hash` (sha256 over the record + the previous
hash), so any silent edit/deletion of a past line breaks the chain and is detectable —
tamper-evidence without external infra. The input text is hashed, not stored, to avoid
persisting raw customer content.

Honest limits (see LIMITATIONS.md): a plain file is not OS-enforced WORM, and writes are
fail-open (a logging error does not block the reply). A regulated deployment would ship
the chain to append-only storage and choose fail-closed; the hook is here.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]


def _audit_path() -> Path:
    return Path(os.getenv("FINHELP_AUDIT_LOG", str(ROOT / "audit_log.jsonl")))


def _last_hash(path: Path) -> str:
    try:
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        return json.loads(lines[-1]).get("hash", "") if lines else ""
    except Exception:
        return ""


def audit_record(record: Dict) -> Dict:
    """Chain-append an arbitrary decision record (used by both the agent and graph paths)."""
    path = _audit_path()
    record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    prev = _last_hash(path)
    record["prev_hash"] = prev
    body = json.dumps({k: v for k, v in record.items() if k != "hash"}, sort_keys=True)
    record["hash"] = hashlib.sha256((prev + body).encode("utf-8")).hexdigest()
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass  # fail-open: auditing must not break the request path (see LIMITATIONS.md)
    return record


def audit_decision(ticket: Dict, result) -> Dict:
    return audit_record({
        "ticket_id": ticket.get("id"),
        "account_id": ticket.get("account_id"),
        "lang": ticket.get("lang"),
        "input_sha256": hashlib.sha256(str(ticket.get("text", "")).encode("utf-8")).hexdigest()[:16],
        "tools_used": list(result.tools_used),
        "gate_passed": result.gate_passed,
        "failed_rails": list(result.failed_rails),
        "route": result.route,
        "sent": result.sent,
        "latency_ms": getattr(result, "latency_ms", 0.0),
        "steps": getattr(result, "steps", 0),
        "model": os.getenv("NEBIUS_MODEL") or os.getenv("OPENAI_MODEL") or "scripted",
    })
