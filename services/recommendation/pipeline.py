"""추천 흐름: 벡터 후보 -> 알레르기 규칙 제외 -> 랭커(LLM 또는 규칙) -> 결과 검증."""
from __future__ import annotations

import logging
import re

from .allergens import assess
from .contracts import Candidate
from .contracts import Pick, RecommendationResult, SafetyVerdict, UserProfile
from .embedders import document_text
from .ports import CatalogRepository, Embedder, Ranker, VectorIndex
from .rankers import RuleRanker
from .used_check import AVAILABLE, ListingChecker, verify_used

log = logging.getLogger(__name__)

# 이름 일치 보완에 쓰지 않는 말(광고·리뷰·수량 표현). 이 말로 상품 이름을 찾으면 엉뚱한 상품이 섞인다.
_STOPWORDS = {
    "추천", "상품", "제품", "판매", "구매", "무료", "배송", "이벤트", "진행중", "쿠폰", "받기", "할인", "특가", "오늘",
    "리뷰", "후기", "재구매", "재구매율", "높아요", "좋아요", "인기", "정품", "새상품", "최저가", "세트", "용량",
}
_WORD = re.compile(r"[0-9A-Za-z가-힣]{2,}")


def name_keywords(query: str) -> list[str]:
    """상품 이름에서 찾을 말: 2글자 이상, 숫자·단위만인 말과 광고·리뷰 말 제외, 최대 5개."""
    out = []
    for w in _WORD.findall(query or ""):
        if w in _STOPWORDS or re.fullmatch(r"\d+(?:cm|mm|ml|kg|g|l|개|입|팩)?", w, re.I) or w in out:
            continue
        out.append(w)
    return out[:5]


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
                  candidate_limit: int = 30, min_score: float = 0.0, score_margin: float = 0.0) -> RecommendationResult:
        """min_score: 이보다 덜 비슷한 후보는 버린다(코사인 유사도). 0이면 끔.
        score_margin: 가장 비슷한 후보보다 이만큼 이상 낮으면 버린다(0이면 끔). 진짜 비슷한 상품이 있는데(예: 0.86)
        중고라 빠지면 남은 무관 상품(0.54)이 고정 기준점만 넘어 추천되던 문제를 막는다.
        검색어가 비어 있으면 추천하지 않는다 — 예전에는 '추천'이라는 말로 검색해 아무 상품이나 기본처럼 보여줬다."""
        notes: list[str] = []
        text = " ".join(x for x in (query.strip() if query else "", profile.preferences) if x)
        if not text:
            notes.append("검색어가 없어 추천하지 않음")
            return RecommendationResult(profile.user_id, query, [], [], self.ranker.name, notes)
        cands = self.index.search(self.embedder.embed_query(text), candidate_limit)
        if min_score > 0 or score_margin > 0:
            best = max((c.score for c in cands), default=0.0)
            cutoff = max(min_score, best - score_margin if score_margin > 0 else 0.0)
            weak = [c for c in cands if c.score < cutoff]
            if weak:
                notes.append(f"관련도 {round(cutoff, 3)} 미만 후보 {len(weak)}건 제외")
            cands = [c for c in cands if c.score >= cutoff]
            # 이름 일치 보완: 벡터 점수가 낮아도 상품 이름에 검색어가 그대로 들어 있으면 후보에 넣는다.
            # (식품은 긴 상세 설명까지 벡터에 들어가 '갈비탕'과 '[소반옥] 왕갈비탕'이 0.23점에 그치던 문제)
            # 최종 선택은 랭커(LLM)가 다시 판단한다.
            find = getattr(self.catalog, "name_matches", None)
            if find is not None:
                have = {c.product_id for c in cands}
                extra = [pid for pid in find(name_keywords(query), 20) if pid not in have]
                if extra:
                    notes.append(f"이름 일치 후보 {len(extra)}건 추가")
                    cands = cands + [Candidate(pid, cutoff) for pid in extra]
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
        hidden = overseas = 0
        for p, s in safe:
            if not profile.include_overseas and p.currency and p.currency != "KRW":
                overseas += 1  # 해외 상품 OFF: 원화가 아닌 가격의 판매처는 숨김
                continue
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
        if overseas:
            notes.append(f"해외 상품 {overseas}건 숨김 (해외 상품 꺼짐)")
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
