"""Retriever over the KB, backed by the `rank_bm25` library (Okapi BM25).

We compose a proven retrieval library rather than hand-roll scoring — BM25 is the
standard lexical baseline. The graph only depends on `retrieve(query) -> list[str]`,
so in production you swap this for a vector store + embeddings with no caller change.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from rank_bm25 import BM25Okapi

_TOKEN = re.compile(r"[a-z0-9]+")


def _tok(text: str) -> List[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Doc:
    id: str
    lang: str
    text: str


class Retriever:
    def __init__(self, docs: List[Doc]):
        self.docs = docs
        self._bm25 = BM25Okapi([_tok(d.text) for d in docs])

    def retrieve(self, query: str, k: int = 2, lang: Optional[str] = None) -> List[str]:
        scores = self._bm25.get_scores(_tok(query))
        ranked = sorted(
            ((s, d) for s, d in zip(scores, self.docs) if not lang or d.lang == lang),
            key=lambda x: x[0], reverse=True,
        )
        return [d.text for s, d in ranked[:k] if s > 0]


def load_kb(path: str | Path) -> Retriever:
    docs: List[Doc] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        docs.append(Doc(id=d["id"], lang=d.get("lang", "en"), text=d["text"]))
    return Retriever(docs)
