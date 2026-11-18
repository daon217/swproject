"""추천 흐름: 벡터 후보 -> 알레르기 규칙 제외 -> 랭커(LLM 또는 규칙) -> 결과 검증."""
from __future__ import annotations

import logging

from .allergens import assess
from .contracts import Pick, RecommendationResult, SafetyVerdict, UserProfile
from .embedders import document_text
from .ports import CatalogRepository, Embedder, Ranker, VectorIndex
from .rankers import RuleRanker
from .used_check import AVAILABLE, ListingChecker, verify_used

log = logging.getLogger(__name__)


class Recommender:
    def __init__(self, catalog: CatalogRepository, index: VectorIndex, embedder: Embedder, ranker: Ranker,
                 used_checker: ListingChecker | None = None, max_used: int = 3):
        self.catalog, self.index, self.embedder, self.ranker = catalog, index, embedder, ranker
        self.used_checker, self.max_used = used_checker, max_used

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

        safe, sale_excluded = self._sale_filter(profile, safe, top_k, notes)
        excluded.extend(sale_excluded)

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
        picks, seen, used_n = [], set(), 0
        for pid, reason in picks_raw:
            if pid not in allowed:
                notes.append(f"랭커가 후보 밖 상품을 골라 버림: {pid}")
                continue
            if pid in seen:
                continue
            seen.add(pid)
            p, s = allowed[pid]
            if p.is_used:
                if used_n >= self.max_used:
                    continue
                used_n += 1
            picks.append(Pick(pid, p.name, reason, round(s, 4)))
            if len(picks) >= top_k:
                break
        return RecommendationResult(profile.user_id, query, picks, excluded, ranker_name, notes)

    def _sale_filter(self, profile: UserProfile, safe, top_k: int, notes: list[str]):
        """판매 상태 필터. 중고는 설정·도메인 확인 후 상위 후보만 실시간 재확인."""
        keep, excluded, used = [], [], []
        hidden = 0
        for p, s in safe:
            if p.is_used:
                if not profile.include_used or p.category == "food":
                    hidden += 1  # 중고 OFF 이거나 식품이면 숨김 (UI 에서도 중고 구역 자체를 숨김)
                    continue
                used.append((p, s))
            elif p.availability in ("ended", "out_of_stock"):
                excluded.append(SafetyVerdict(p.product_id, False, [f"판매 상태 {p.availability}"], []))
            else:
                keep.append((p, s))
        if hidden:
            notes.append(f"중고 {hidden}건 숨김 (중고 포함 꺼짐 또는 식품)")
        if not used:
            return keep, excluded

        used.sort(key=lambda x: -x[1])
        window = used[: max(top_k, self.max_used) * 2]  # 보여줄 가능성이 있는 것만 확인
        if len(used) > len(window):
            notes.append(f"중고 후보 {len(used) - len(window)}건은 확인 범위 밖이라 제외")
        if self.used_checker is None:
            notes.append("중고 실시간 확인 꺼짐: 저장된 판매 상태만 사용")
            for p, s in window:
                if p.availability == "available":
                    keep.append((p, s))
                else:
                    excluded.append(SafetyVerdict(p.product_id, False, ["중고: 판매 중 확인 안 됨"], []))
            keep.sort(key=lambda x: -x[1])
            return keep, excluded

        live = verify_used([p for p, _ in window], self.used_checker)
        for p, s in window:
            st = live.get(p.product_id)
            if st and st.status == AVAILABLE:
                keep.append((p, s))
            else:
                why = f"{st.status}: {st.evidence}" if st else "확인 결과 없음"
                excluded.append(SafetyVerdict(p.product_id, False, [f"중고 재확인 {why}"], []))
        keep.sort(key=lambda x: -x[1])
        return keep, excluded
