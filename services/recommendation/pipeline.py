"""추천 흐름: 벡터 후보 -> 알레르기 규칙 제외 -> 랭커(LLM 또는 규칙) -> 결과 검증."""
from __future__ import annotations

import logging
import re
from collections import Counter

from .allergens import assess, focus_query
from .contracts import Candidate
from .contracts import Pick, RecommendationResult, SafetyVerdict, UserProfile
from .embedders import document_text
from .food_types import food_type, same_kind, type_search_terms
from .product_types import product_same_kind, product_search_terms, product_type
from .ports import CatalogRepository, Embedder, Ranker, VectorIndex
from .rankers import RuleRanker
from .used_check import AVAILABLE, ListingChecker, verify_used

log = logging.getLogger(__name__)
MIN_PICKS = 5  # 식품·일반 상품 추천을 최소 이만큼 보여준다 (후보가 모자라면 그만큼만)
MAX_SAME_NAME = 2  # 채울 때 보고 있는 상품과 이름이 겹치는 상품(같은 상품 다른 용량)은 이만큼까지 먼저

# 단독으로 상품을 매칭하면 안 되지만, 핵심 품목과 함께 일치할 때 우선순위를 높여줄 선호 수식어('무가당 땅콩버터', '제로 초콜릿', '볶은 메밀' 등).
_PREF_MODIFIERS = {
    "무가당", "저당", "무설탕", "제로", "슈가프리", "저칼로리", "무첨가", "유기농", "고단백", "비건",
    "글루텐프리", "디카페인", "볶은", "구운", "무소음", "저소음", "초경량", "경량", "무선", "게이밍",
}

# 이름 일치 보완에 쓰지 않는 말(광고·리뷰·수량·수식어 표현).
# '무가당 땅콩 버터'에서 '무가당'만으로, '제로 카카오 초콜릿'에서 '제로'만으로 다른 상품을 찾으면 엉뚱한 상품이 섞인다.
_STOPWORDS = {
    "추천", "상품", "제품", "판매", "구매", "무료", "배송", "이벤트", "진행중", "쿠폰", "받기", "할인", "특가", "오늘",
    "리뷰", "후기", "재구매", "재구매율", "높아요", "좋아요", "인기", "정품", "새상품", "최저가", "세트", "용량",
    "프리미엄", "친환경", "대용량", "소용량", "미니", "휴대용", "방수", "고속",
    "국내산", "미국산", "국산", "수제", "전통", "오리지널", "클래식", "스페셜", "에디션", "단독", "기획", "공식",
    "크런치", "스무스", "크리미", "마일드",
    "블랙", "화이트", "그레이", "브라운", "실버", "골드", "네이비", "베이지", "핑크", "레드", "블루", "그린",
    "black", "white", "grey", "gray", "brown", "silver", "gold", "free", "new",
} | _PREF_MODIFIERS


def modifier_keywords(query: str) -> list[str]:
    """검색어에 포함된 선호 수식어('무가당', '제로' 등)를 추출한다. 핵심 품목이 일치하는 후보 안에서 우선순위를 높이는 데 쓴다."""
    out: list[str] = []
    for w in _WORD.findall(query or ""):
        low = w.lower()
        if low in _PREF_MODIFIERS and low not in out:
            out.append(low)
        else:
            for mod in _PREF_MODIFIERS:
                if len(mod) >= 2 and mod in low and mod not in out:
                    out.append(mod)
    return out[:4]
_WORD = re.compile(r"[0-9A-Za-z가-힣]{2,}")


# 한영 브랜드·품목 별칭: 상품명에 한글 브랜드('에이수스'·'나이키')나 하위 모델명('비보북'·'맥북')만 있을 때도
# 영문 브랜드('ASUS'·'Nike')나 상위 품목('노트북'·'스니커즈')으로 등록된 카탈로그 상품을 놓치지 않고 후보에 넣는다.
_KEYWORD_ALIASES: dict[str, tuple[str, ...]] = {
    # 컴퓨터 / 노트북 / 주변기기 브랜드·품목
    "에이수스": ("asus", "노트북", "rog", "tuf"),
    "아수스": ("asus", "노트북", "rog", "tuf"),
    "asus": ("에이수스", "아수스", "노트북"),
    "비보북": ("노트북", "asus", "vivobook"),
    "vivobook": ("노트북", "asus", "비보북"),
    "젠북": ("노트북", "asus", "zenbook"),
    "zenbook": ("노트북", "asus", "젠북"),
    "터프": ("노트북", "tuf", "asus"),
    "tuf": ("노트북", "asus"),
    "아스트랄": ("astral", "asus", "rog", "rtx"),
    "맥북": ("노트북", "apple", "애플", "macbook"),
    "macbook": ("노트북", "apple", "애플", "맥북"),
    "애플": ("apple", "맥북", "아이폰", "아이패드"),
    "apple": ("애플", "맥북", "iphone", "ipad"),
    "아이폰": ("iphone", "apple", "애플"),
    "iphone": ("아이폰", "apple", "애플"),
    "아이패드": ("ipad", "apple", "애플", "태블릿"),
    "ipad": ("아이패드", "apple", "애플", "태블릿"),
    "갤럭시북": ("노트북", "삼성", "samsung", "갤럭시"),
    "갤럭시": ("삼성", "samsung", "galaxy"),
    "galaxy": ("갤럭시", "삼성", "samsung"),
    "삼성": ("samsung", "갤럭시", "갤럭시북"),
    "samsung": ("삼성", "갤럭시"),
    "그램": ("노트북", "lg", "엘지", "gram"),
    "엘지": ("lg", "그램"),
    "lg": ("엘지", "그램"),
    "레노버": ("lenovo", "노트북", "씽크패드", "아이디어패드"),
    "lenovo": ("레노버", "노트북", "thinkpad", "ideapad"),
    "씽크패드": ("노트북", "레노버", "lenovo", "thinkpad"),
    "아이디어패드": ("노트북", "레노버", "lenovo", "ideapad"),
    "엠에스아이": ("msi", "노트북", "그래픽카드", "rtx"),
    "msi": ("엠에스아이", "노트북", "rtx"),
    "기가바이트": ("gigabyte", "노트북", "그래픽카드", "rtx"),
    "gigabyte": ("기가바이트", "rtx"),
    "에이서": ("acer", "노트북"),
    "acer": ("에이서", "노트북"),
    "델": ("dell", "노트북", "모니터"),
    "dell": ("델", "노트북", "모니터"),
    "에이치피": ("hp", "노트북"),
    "hp": ("노트북",),
    "로지텍": ("logitech", "마우스", "키보드"),
    "logitech": ("로지텍", "마우스", "키보드"),
    "랩탑": ("노트북", "laptop"),
    "laptop": ("노트북",),
    "노트북": ("asus", "에이수스", "비보북", "맥북", "그램", "갤럭시북", "레노버", "msi"),
    "라이젠": ("노트북", "ryzen", "amd"),
    "라이젠5": ("노트북", "ryzen"),
    "라이젠7": ("노트북", "ryzen"),
    "라이젠9": ("노트북", "ryzen"),
    "인텔": ("intel", "노트북"),
    "intel": ("인텔", "노트북"),
    "지포스": ("rtx", "gtx", "그래픽카드", "geforce"),
    "geforce": ("지포스", "rtx", "그래픽카드"),
    "라데온": ("그래픽카드", "radeon"),
    "그래픽카드": ("rtx", "gtx", "지포스", "geforce"),
    "rtx": ("그래픽카드", "지포스", "geforce"),
    "에스에스디": ("ssd", "nvme"),
    "ssd": ("nvme", "wd", "저장"),
    # 패션 / 신발 / 의류 브랜드·품목
    "나이키": ("nike", "스니커즈", "운동화", "에어포스"),
    "nike": ("나이키", "스니커즈", "운동화", "air force"),
    "아디다스": ("adidas", "스니커즈", "운동화"),
    "adidas": ("아디다스", "스니커즈", "운동화"),
    "뉴발란스": ("new balance", "스니커즈", "운동화"),
    "아식스": ("asics", "젤", "운동화", "스니커즈"),
    "asics": ("아식스", "젤", "운동화"),
    "스킴스": ("skims",),
    "skims": ("스킴스",),
    "운동화": ("스니커즈", "로우", "레이서", "nike", "나이키"),
    "스니커즈": ("운동화", "로우", "레이서", "nike", "나이키"),
    "패딩": ("다운", "구스", "자켓", "재킷", "down", "jacket"),
    "자켓": ("재킷", "jacket", "패딩", "점퍼"),
    "재킷": ("자켓", "jacket", "패딩", "점퍼"),
    "가방": ("숄더백", "백팩", "토트백", "파우치", "bag"),
    "숄더백": ("가방", "백", "bag"),
    # 반려동물 / 생활용품
    "사료": ("팬시피스트", "프리스키", "퓨리나", "고양이", "강아지"),
    "고양이사료": ("고양이", "사료", "팬시피스트", "프리스키", "퓨리나"),
    "강아지사료": ("강아지", "사료", "퓨리나"),
    # 식품 / 국물 / 간편식
    "해장국": ("갈비탕", "찌개", "탕", "국"),
    "설렁탕": ("갈비탕", "찌개", "탕", "국"),
    "곰탕": ("갈비탕", "찌개", "탕", "국"),
    "삼계탕": ("갈비탕", "찌개", "탕", "국"),
    "감자탕": ("갈비탕", "찌개", "탕", "국"),
    "육개장": ("갈비탕", "찌개", "탕", "국"),
    "국밥": ("갈비탕", "찌개", "탕", "국"),
    "갈비탕": ("왕갈비탕", "전통 갈비탕", "탕", "찌개"),
    "부대찌개": ("찌개", "갈비탕", "탕"),
    "김치찌개": ("찌개", "부대찌개", "탕"),
    "된장찌개": ("찌개", "부대찌개", "탕"),
    "돈까스": ("생선까스", "치킨까스", "까스"),
    "돈가스": ("생선까스", "치킨까스", "까스"),
    "치킨까스": ("생선까스", "돈까스", "까스", "닭가슴살"),
    "생선까스": ("치킨까스", "돈까스", "까스"),
    "파스타": ("오븐파스타", "스파게티", "면"),
    "스파게티": ("파스타", "오븐파스타"),
}


def name_keywords(query: str) -> list[str]:
    """상품 이름에서 찾을 말: 2글자 이상, 숫자·단위만인 말과 광고·리뷰·수식어 말 제외, 최대 6개."""
    out: list[str] = []
    for w in _WORD.findall(query or ""):
        if w in _STOPWORDS or re.fullmatch(r"\d+(?:cm|mm|ml|kg|g|l|개|입|팩)?", w, re.I) or w in out:
            continue
        out.append(w)
    return out[:6]


def expand_keywords(query: str) -> list[str]:
    """직접 추출된 핵심 키워드(name_keywords)에 붙여쓴 복합어 분리 및 한·영 브랜드/품목 별칭을 더해 최대 12개로 확장한다."""
    base = name_keywords(query)
    aliases: list[str] = []
    for w in base:
        low = w.lower()
        for al in _KEYWORD_ALIASES.get(low, ()):
            if al not in base and al not in aliases:
                aliases.append(al)
        for key, vals in _KEYWORD_ALIASES.items():
            if len(key) >= 2 and key != low and key in low:
                if key not in base and key not in aliases:
                    aliases.append(key)
                for al in vals:
                    if al not in base and al not in aliases:
                        aliases.append(al)
    combined = list(base)
    for al in aliases:
        if al not in combined:
            combined.append(al)
    return combined[:12]


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
                  candidate_limit: int = 30, min_score: float = 0.0, score_margin: float = 0.0,
                  domain: str | None = None) -> RecommendationResult:
        """min_score: 이보다 덜 비슷한 후보는 버린다(코사인 유사도). 0이면 끔.
        score_margin: 가장 비슷한 후보보다 이만큼 이상 낮으면 버린다(0이면 끔). 진짜 비슷한 상품이 있는데(예: 0.86)
        중고라 빠지면 남은 무관 상품(0.54)이 고정 기준점만 넘어 추천되던 문제를 막는다.
        검색어가 비어 있으면 추천하지 않는다 — 예전에는 '추천'이라는 말로 검색해 아무 상품이나 기본처럼 보여줬다."""
        notes: list[str] = []
        original = query
        # 알레르기 단어는 검색에서 빼고 나머지에 집중 (새우 알레르기 + '새우튀김' -> '튀김' 대체품). 안전 판정은 아래 assess 가 그대로 함.
        query, removed = focus_query(query or "", profile.allergens)
        if removed:
            notes.append(f"{'·'.join(dict.fromkeys(removed))} 알레르기: '{original}' 대신 '{query or '-'}' 중심으로 추천")
        text = " ".join(x for x in (query.strip(), profile.preferences) if x)
        if not text:
            notes.append("검색어가 없어 추천하지 않음")
            return RecommendationResult(profile.user_id, original, [], [], self.ranker.name, notes)
        cands = self.index.search(self.embedder.embed_query(text), candidate_limit)
        best = max((c.score for c in cands), default=0.0)
        cutoff = 0.0
        if min_score > 0 or score_margin > 0:
            cutoff = max(min_score, best - score_margin if score_margin > 0 else 0.0)
            weak = [c for c in cands if c.score < cutoff]
            if weak:
                notes.append(f"관련도 {round(cutoff, 3)} 미만 후보 {len(weak)}건 제외")
            cands = [c for c in cands if c.score >= cutoff]
        # 이름 일치 보완: 벡터 점수가 낮아도 상품 이름·브랜드에 검색어(또는 한영·품목 별칭)가 들어 있으면 후보에 넣는다.
        # (식품은 긴 상세 설명까지 벡터에 들어가 '갈비탕'과 '[소반옥] 왕갈비탕'이 0.23점에 그치던 문제,
        #  노트북은 '에이수스 비보북'과 'ASUS TUF A14 노트북'의 벡터 점수가 0.20점에 그치던 문제)
        # compact_candidates(상위 12개)와 중고 상위 창에서 잘리지 않도록 최고 점수(best)로 후보 앞에 넣는다.
        # 식품·일반 상품 모두 보고 있는 상품과 같은 품목만 추천한다 (food_types.py / product_types.py).
        food = domain == "food"
        typed = domain in ("food", "product")
        # 품목은 원래 상품명으로 ('매일두유'에서 두유를 빼면 품목을 잃음)
        query_kind = food_type(original or "") if food else product_type(original or "") if typed else None
        kind_terms = type_search_terms if food else product_search_terms
        find = getattr(self.catalog, "name_matches", None)
        if find is not None:
            have = {c.product_id for c in cands}
            core_kws = expand_keywords(query)
            mod_kws = modifier_keywords(query)
            try:
                raw_matched = find(core_kws, 20, modifiers=mod_kws)
            except TypeError:
                raw_matched = find(core_kws, 20)
            if query_kind:
                # 대체품(대두 알레르기면 아몬드·귀리 음료)은 벡터 상위 30개에 안 들 수 있어 품목 이름으로도 찾는다.
                raw_matched = list(raw_matched) + list(find(list(kind_terms(query_kind)), 20))
            matched = list(dict.fromkeys(raw_matched))
            if matched:
                extra_n = sum(1 for pid in matched if pid not in have)
                if extra_n:
                    notes.append(f"이름 일치 후보 {extra_n}건 추가")
                boost = max(best, cutoff)
                matched_set = set(matched)
                boosted = [Candidate(pid, round(boost + (len(matched) - idx) * 1e-4, 6)) for idx, pid in enumerate(matched)]
                cands = boosted + [c for c in cands if c.product_id not in matched_set]
        products = self.catalog.get_many([c.product_id for c in cands])
        if food and query_kind is None:
            # 상품명에 품목 말이 없으면('해태제과 아이비, 58g, 2개') 이름이 겹치는 후보('해태 아이비 크래커 309g')의
            # 품목을 빌린다. 안 그러면 '아이비'가 든 상품만 남아 다른 크래커가 전부 빠졌다.
            words = name_keywords(query)
            kinds = Counter(food_type(p.name, p.category) for p in products.values()
                            if same_kind(None, p.name, p.category, words))
            kinds.pop(None, None)
            if kinds:
                query_kind = kinds.most_common(1)[0][0]
                notes.append(f"품목을 같은 이름 상품에서 추정: {query_kind}")
                if find is not None:  # 같은 품목 다른 상품은 벡터 상위에 없을 수 있어 품목 이름으로도 찾는다
                    have = {c.product_id for c in cands}
                    extra = [pid for pid in dict.fromkeys(find(list(kind_terms(query_kind)), 20)) if pid not in have]
                    cands = cands + [Candidate(pid, round(cutoff, 6)) for pid in extra]
                    products.update(self.catalog.get_many(extra))

        safe, excluded = [], []
        query_words = name_keywords(query) if food else []
        # 품목 말이 없어 품목을 모르는 상품도 이름이 겹치면('해태제과 아이비 309g') 같은 상품으로 남긴다.
        same_name = lambda p: food_type(p.name, p.category) is None and same_kind(None, p.name, p.category, query_words)
        off_kind = 0
        for c in cands:
            p = products.get(c.product_id)
            if p is None:
                notes.append(f"인덱스에만 있고 카탈로그에 없음: {c.product_id}")
                continue
            # 알레르기 검사로 비슷한 상품이 다 빠진 뒤 점수만 넘은 다른 품목(두유 -> 한우)이 남지 않게 먼저 거른다.
            if food and not (same_kind(query_kind, p.name, p.category, query_words) or same_name(p)) or                     typed and not food and not product_same_kind(query_kind, p.name, p.category):
                off_kind += 1
                continue
            v = assess(p, profile)
            if v.safe:
                safe.append((p, c.score))
            else:
                excluded.append(v)
        if off_kind:
            unknown = "모름, 상품명 단어로 비교" if food else "모름, 액세서리만 제외"
            notes.append(f"다른 품목 {off_kind}건 제외 (품목: {query_kind or unknown})")

        safe, sale_excluded = self._sale_filter(profile, safe, top_k, notes)
        excluded.extend(sale_excluded)

        ranker_name = self.ranker.name
        picks_raw: list[tuple[str, str]] = []
        if safe:
            try:
                # LLM 에는 원래 상품명 + 대체품이라는 사실을 줘야 '새우튀김과 다르다'며 다른 튀김을 버리지 않음
                rank_query = f"{original} ({'·'.join(dict.fromkeys(removed))} 없는 대체품)" if removed else query
                picks_raw = self.ranker.rank(profile, rank_query, safe, top_k)
            except Exception as e:  # LLM 장애가 추천 전체를 막지 않도록
                log.warning("ranker 실패, 규칙 순위로 대체: %s", e)
                notes.append(f"{ranker_name} 실패 → 유사도 순으로 대체: {type(e).__name__}")
                ranker_name = "rule-fallback"
                picks_raw = RuleRanker().rank(profile, query, safe, top_k)
            # 같은 품목 확인은 코드가 이미 했다. LLM은 '요청과 똑같은 것'만 고르는 경향이 있어(아이비 크래커 페이지에서
            # 아이비 1개만), LLM 이 고른 것을 앞에 두고 MIN_PICKS 개까지 같은 품목 안에서 유사도 순으로 채운다.
            safe_ids = {p.product_id for p, _ in safe}
            chosen = list(dict.fromkeys(pid for pid, _ in picks_raw if pid in safe_ids))
            want = min(MIN_PICKS, top_k, len(safe))
            if typed and len(chosen) < want:
                if chosen:
                    notes.append(f"{ranker_name} {len(chosen)}개 + 같은 품목 유사도 순으로 {want}개까지 채움")
                else:
                    notes.append(f"{ranker_name}가 고른 후보 없음 → 같은 품목 안에서 유사도 순")
                    ranker_name = "rule-fallback"
                # 이름이 겹치는 같은 상품(아이비 309g·270g…)이 점수가 높아 다 차지하지 않게 MAX_SAME_NAME 개까지만 먼저 넣고,
                # 다른 상품(슈가·통밀 크래커)을 채운 뒤에도 모자라면 나머지를 넣는다.
                by_id = {p.product_id: p for p, _ in safe}
                # '크래커' 같은 품목 말은 모든 크래커가 공유하므로 '같은 상품' 판단에서 뺀다
                kind_of = food_type if food else product_type
                words = [w for w in name_keywords(query) if kind_of(w) is None]
                same = lambda pid: same_kind(None, by_id[pid].name, None, words)
                n_same = sum(1 for pid in chosen if same(pid))
                fill, later = [], []
                for pid, _ in RuleRanker().rank(profile, query, safe, len(safe)):
                    if pid in chosen:
                        continue
                    if same(pid) and n_same >= MAX_SAME_NAME:
                        later.append(pid)
                        continue
                    n_same += same(pid)
                    fill.append(pid)
                fill = (fill + later)[:want - len(chosen)]
                picks_raw = list(picks_raw) + [(pid, "같은 종류의 비슷한 상품") for pid in fill]

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
        return RecommendationResult(profile.user_id, original, picks, excluded, ranker_name, notes)

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
