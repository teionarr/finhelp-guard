"""Model + judge factory for the LIVE pipeline.

Kept out of the offline import path. Azure OpenAI is the default (matches a
common enterprise setup); an OpenAI-compatible local server (Ollama/vLLM) is the
no-cloud, reproducible fallback.
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
    # OpenAI-compatible (local Ollama/vLLM or OpenAI)
    from langchain_openai import ChatOpenAI

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
        from langchain_core.messages import HumanMessage, SystemMessage

        ctx = "\n".join(f"- {c}" for c in contexts) or "(none)"
        msg = [
            SystemMessage(content=(
                "You are a strict compliance reviewer. Answer only with a JSON "
                'object {"score": <0..1>, "reason": "<short>"}. Higher score = the '
                "concern in the question IS present.")),
            HumanMessage(content=f"Question: {question}\n\nContext:\n{ctx}\n\nText:\n{text}"),
        ]
        raw = self._model.invoke(msg).content
        import json
        try:
            d = json.loads(raw)
            return float(d["score"]), str(d.get("reason", ""))
        except Exception:
            # Fail safe: if the judge is unparseable, treat as concern-present.
            return 1.0, f"unparseable judge output: {raw[:120]}"
