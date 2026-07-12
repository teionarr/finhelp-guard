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
    path never requires langchain. Bounded with a request timeout + one retry so
    a hung/slow provider can't stall a support request."""
    budget = dict(timeout=float(os.getenv("FINHELP_LLM_TIMEOUT", "30")), max_retries=1)
    if os.getenv("AZURE_OPENAI_API_KEY"):
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview"),
            temperature=temperature, **budget,
        )
    from langchain_openai import ChatOpenAI

    # Nebius Token Factory (OpenAI-compatible) — cheap open models, good for verification.
    if os.getenv("NEBIUS_API_KEY"):
        return ChatOpenAI(
            model=os.getenv("NEBIUS_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct"),
            base_url=os.getenv("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1"),
            api_key=os.getenv("NEBIUS_API_KEY"),
            temperature=temperature, **budget,
        )
    # Any other OpenAI-compatible endpoint (OpenAI, local Ollama/vLLM).
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        temperature=temperature, **budget,
    )


def embedding_model():
    """Return a LangChain embeddings client from env — the dense side of hybrid
    retrieval. Mirrors ``chat_model()``'s provider selection and request budget so
    a hung provider can't stall retrieval. Imported lazily so the offline path
    never needs langchain."""
    budget = dict(timeout=float(os.getenv("FINHELP_LLM_TIMEOUT", "30")), max_retries=1)
    if os.getenv("AZURE_OPENAI_API_KEY"):
        from langchain_openai import AzureOpenAIEmbeddings

        return AzureOpenAIEmbeddings(
            azure_deployment=os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-small"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-01-preview"),
            **budget,
        )
    from langchain_openai import OpenAIEmbeddings

    if os.getenv("NEBIUS_API_KEY"):
        return OpenAIEmbeddings(
            model=os.getenv("NEBIUS_EMBED_MODEL", "BAAI/bge-en-icl"),
            base_url=os.getenv("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1"),
            api_key=os.getenv("NEBIUS_API_KEY"),
            check_embedding_ctx_length=False,  # non-OpenAI endpoint: skip tiktoken re-chunking
            **budget,
        )
    base_url = os.getenv("OPENAI_BASE_URL") or None
    return OpenAIEmbeddings(
        model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
        base_url=base_url,
        # a non-OpenAI backend (local Ollama/vLLM) doesn't share tiktoken; skip
        # ctx re-chunking there, but keep it for real OpenAI (base_url unset).
        check_embedding_ctx_length=base_url is None,
        **budget,
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
