"""Mocked CRM / ticketing tools the triage agent can call.

Deterministic in-memory fakes — no network, no keys — so the whole agent loop
runs in CI. In production these become a Salesforce Service Cloud / Zendesk /
in-house client behind the SAME function signatures; the agent doesn't change.
All data here is synthetic.
"""
from __future__ import annotations

from typing import Dict, List

# Fake CRM — synthetic accounts.
_ACCOUNTS: Dict[str, Dict] = {
    "AC-1001": {"id": "AC-1001", "name": "Jordan Lee", "verified": True, "can_withdraw": True, "balance_usd": 240.0},
    "AC-2002": {"id": "AC-2002", "name": "Sam Rivera", "verified": False, "can_withdraw": False, "balance_usd": 0.0},
}

# Tool schemas advertised to the LLM in the live path (OpenAI/LC tool-calling format).
TOOL_SCHEMAS: List[Dict] = [
    {"name": "lookup_account", "description": "Look up an account's verification and withdrawal status.",
     "parameters": {"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]}},
    {"name": "search_kb", "description": "Search the help-center knowledge base for relevant policy snippets.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "create_followup_ticket", "description": "Open a follow-up ticket for a human team (e.g. verification).",
     "parameters": {"type": "object", "properties": {"account_id": {"type": "string"}, "summary": {"type": "string"}},
                    "required": ["account_id", "summary"]}},
]

def lookup_account(account_id: str) -> Dict:
    acct = _ACCOUNTS.get(account_id)
    return acct.copy() if acct else {"error": f"account {account_id} not found"}


def create_followup_ticket(account_id: str, summary: str) -> Dict:
    # Deterministic id (no global state) so committed traces are stable.
    return {"followup_ticket_id": f"FUP-{account_id}", "status": "open", "summary": summary}
