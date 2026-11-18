"""추천 흐름: 벡터 후보 -> 알레르기 규칙 제외 -> 랭커(LLM 또는 규칙) -> 결과 검증."""
from __future__ import annotations

import logging

from .allergens import assess
from .contracts import Pick, RecommendationResult, UserProfile
from .embedders import document_text
from .ports import CatalogRepository, Embedder, Ranker, VectorIndex
from .rankers import RuleRanker

log = logging.getLogger(__name__)


class Recommender:
    def __init__(self, catalog: CatalogRepository, index: VectorIndex, embedder: Embedder, ranker: Ranker):
        self.catalog, self.index, self.embedder, self.ranker = catalog, index, embedder, ranker

    def reindex(self, product_ids: list[str] | None = None) -> int:
        ids = product_ids if product_ids is not None else self.catalog.all_ids()
        products = list(self.catalog.get_many(ids).values())
        if not products:
            return 0
        vecs = self.embedder.embed_documents([document_text(p) for p in products])
        self.index.upsert([(p.product_id, v) for p, v in zip(products, vecs)])
        return len(products)

    def recommend(self, profile: UserProfile, query: str, top_k: int = 5,
                  candidate_limit: int = 30) -> RecommendationResult:
        notes: list[str] = []
        text = " ".join(x for x in (query, profile.preferences) if x) or "추천"
        cands = self.index.search(self.embedder.embed_query(text), candidate_limit)
        products = self.catalog.get_many([c.product_id for c in cands])

        safe, excluded = [], []
        for c in cands:
            p = products.get(c.product_id)
            if p is None:
                notes.append(f"인덱스에만 있고 카탈로그에 없음: {c.product_id}")
                continue
            v = assess(p, profile)
            if v.safe:
                safe.append((p, c.score))
            else:
                excluded.append(v)

        ranker_name = self.ranker.name
        picks_raw: list[tuple[str, str]] = []
        if safe:
            try:
                picks_raw = self.ranker.rank(profile, query, safe, top_k)
            except Exception as e:  # LLM 장애가 추천 전체를 막지 않도록
                log.warning("ranker 실패, 규칙 순위로 대체: %s", e)
                notes.append(f"{ranker_name} 실패 → 유사도 순으로 대체: {type(e).__name__}")
                ranker_name = "rule-fallback"
                picks_raw = RuleRanker().rank(profile, query, safe, top_k)

        # 랭커가 무엇을 돌려주든 안전 후보 안에서만, 중복 없이, top_k 까지.
        allowed = {p.product_id: (p, s) for p, s in safe}
        picks, seen = [], set()
        for pid, reason in picks_raw:
            if pid not in allowed:
                notes.append(f"랭커가 후보 밖 상품을 골라 버림: {pid}")
                continue
            if pid in seen:
                continue
            seen.add(pid)
            p, s = allowed[pid]
            picks.append(Pick(pid, p.name, reason, round(s, 4)))
            if len(picks) >= top_k:
                break
        return RecommendationResult(profile.user_id, query, picks, excluded, ranker_name, notes)
