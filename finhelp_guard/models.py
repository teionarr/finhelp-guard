"""Model + judge factory for the LIVE pipeline.

Kept out of the offline import path. Azure OpenAI is used when
AZURE_OPENAI_API_KEY is set (matches a common enterprise setup); otherwise it
falls back to an OpenAI-compatible endpoint (OpenAI, or a local Ollama/vLLM
server) for a no-cloud, reproducible run.
"""
from __future__ import annotations

import os
from typing import List

from .rails.base import Judge


def chat_model(temperature: float = 0.0):
    """Return a LangChain chat model from env. Imported lazily so the offline
    path never requires langchain."""
    if os.getenv("AZURE_OPENAI_API_KEY"):
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview"),
            temperature=temperature,
        )
    from langchain_openai import ChatOpenAI

    # Nebius Token Factory (OpenAI-compatible) — cheap open models, good for verification.
    if os.getenv("NEBIUS_API_KEY"):
        return ChatOpenAI(
            model=os.getenv("NEBIUS_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct"),
            base_url=os.getenv("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1"),
            api_key=os.getenv("NEBIUS_API_KEY"),
            temperature=temperature,
        )
    # Any other OpenAI-compatible endpoint (OpenAI, local Ollama/vLLM).
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        temperature=temperature,
    )


class LLMJudge(Judge):
    """Live LLM-as-judge implementing the Judge protocol used by the rails.

    In a full build this delegates to DeepEval MisuseMetric / Ragas Faithfulness;
    here it's a thin structured-output judge so the contract is concrete. Its
    scores are themselves validated against a human-labelled gold subset — you
    don't trust an evaluator you haven't checked.
    """

    def __init__(self, model=None):
        self._model = model or chat_model()

    def score(self, question: str, text: str, contexts: List[str]) -> tuple[float, str]:
        import json

        ctx = "\n".join(f"- {c}" for c in contexts) or "(none)"
        # LangChain chat models accept (role, content) tuples — no extra imports,
        # and it keeps the judge trivially unit-testable with a fake model.
        messages = [
            ("system",
             "You are a strict compliance reviewer. Answer only with a JSON object "
             '{"score": <0..1>, "reason": "<short>"}. Higher score = the concern in '
             "the question IS present."),
            ("human", f"Question: {question}\n\nContext:\n{ctx}\n\nText:\n{text}"),
        ]
        raw = self._model.invoke(messages).content
        try:
            d = json.loads(raw)
            return float(d["score"]), str(d.get("reason", ""))
        except Exception:
            # Fail safe: if the judge is unparseable, treat as concern-present.
            return 1.0, f"unparseable judge output: {str(raw)[:120]}"
