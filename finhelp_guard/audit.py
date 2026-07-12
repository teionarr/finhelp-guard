"""Append-only JSONL audit trail — one immutable line per triage decision.

Regulated ops needs a defensible record of every automated decision: what account,
which tools ran, the gate verdict, and where it routed. This also makes the
"observability" claim a runnable, testable feature rather than a name-drop.

The input text is hashed, not stored, to avoid persisting raw customer content.
Auditing never raises — a logging failure must not break a support request.
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


def audit_decision(ticket: Dict, result) -> Dict:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ticket_id": ticket.get("id"),
        "account_id": ticket.get("account_id"),
        "lang": ticket.get("lang"),
        "input_sha256": hashlib.sha256(str(ticket.get("text", "")).encode("utf-8")).hexdigest()[:16],
        "tools_used": list(result.tools_used),
        "gate_passed": result.gate_passed,
        "failed_rails": list(result.failed_rails),
        "route": result.route,
        "sent": result.sent,
        "model": os.getenv("NEBIUS_MODEL") or os.getenv("OPENAI_MODEL") or "scripted",
    }
    try:
        with open(_audit_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass  # auditing must never break the request path
    return record
