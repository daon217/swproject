"""임베딩 모델.

- HashEmbedder: 의존성 없는 글자 n-gram 해시 임베딩. 모델 다운로드 없이 파이프라인 전체를
  돌려볼 때 사용. 의미 검색 품질은 낮음(같은 글자가 많으면 비슷하다고 봄).
- SentenceTransformerEmbedder: 실제 모델. sentence-transformers 설치 + 모델 파일 필요.
"""
from __future__ import annotations

import hashlib
import math
from typing import Sequence

from .contracts import CollectedProduct


def document_text(p: CollectedProduct) -> str:
    """상품 -> 임베딩 입력 문장. 형식이 바뀌면 임베딩을 다시 만들어야 함."""
    parts = [p.name, p.category or "", p.brand or "", p.description or "",
             "성분: " + (p.ingredients_raw or ", ".join(p.ingredients or []))]
    return " | ".join(x for x in parts if x)


class HashEmbedder:
    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions
        self.name = f"hash-ngram-{dimensions}"

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dimensions
        t = "".join(text.lower().split())
        grams = [t[i:i + n] for n in (1, 2, 3) for i in range(max(len(t) - n + 1, 0))]
        for g in grams:
            h = int.from_bytes(hashlib.blake2b(g.encode(), digest_size=8).digest(), "big")
            v[h % self.dimensions] += 1.0 if (h >> 32) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", revision: str | None = None):
        from sentence_transformers import SentenceTransformer  # 무거운 import 는 필요할 때만

        self._model = SentenceTransformer(model_name, device="cpu", revision=revision, trust_remote_code=False)
        self.name = model_name
        self.dimensions = int(self._model.get_sentence_embedding_dimension())

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._model.encode(list(texts), normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode([text], normalize_embeddings=True)[0].tolist()


def make_embedder(kind: str):
    if kind == "hash":
        return HashEmbedder()
    if kind.startswith("st:"):
        return SentenceTransformerEmbedder(kind[3:])
    if kind == "st":
        return SentenceTransformerEmbedder()
    raise ValueError("embedder 는 hash | st | st:<모델명>")
