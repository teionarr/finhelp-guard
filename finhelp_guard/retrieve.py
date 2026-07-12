"""Tiny dependency-free retriever over a synthetic KB.

Pure-python TF-IDF cosine so the offline demo runs with zero installs. In live
mode you would swap this for a real vector store + embeddings; the graph only
depends on the `retrieve(query) -> list[str]` shape, not on this implementation.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import List

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
        self._tf = [Counter(_tok(d.text)) for d in docs]
        df: Counter = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(docs) or 1
        self._idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}

    def _vec(self, counts: Counter) -> dict:
        return {t: c * self._idf.get(t, math.log(len(self.docs) + 1) + 1)
                for t, c in counts.items()}

    @staticmethod
    def _cos(a: dict, b: dict) -> float:
        common = set(a) & set(b)
        num = sum(a[t] * b[t] for t in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return num / (na * nb) if na and nb else 0.0

    def retrieve(self, query: str, k: int = 2, lang: str | None = None) -> List[str]:
        qv = self._vec(Counter(_tok(query)))
        scored = []
        for doc, tf in zip(self.docs, self._tf):
            if lang and doc.lang != lang:
                continue
            scored.append((self._cos(qv, self._vec(tf)), doc.text))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for score, text in scored[:k] if score > 0]


def load_kb(path: str | Path) -> Retriever:
    docs: List[Doc] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        docs.append(Doc(id=d["id"], lang=d.get("lang", "en"), text=d["text"]))
    return Retriever(docs)
