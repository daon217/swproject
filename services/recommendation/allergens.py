"""알레르기 판정 (규칙 기반). LLM 은 여기를 통과한 상품만 봅니다.

기준: 식품 등의 표시기준 알레르기 유발물질 19종(조개류에 굴·전복·홍합 포함).
판정은 '놓치지 않기'가 우선이라, 애매하면 제외 쪽으로 기웁니다.
"""
from __future__ import annotations

import re

from .contracts import CollectedProduct, SafetyVerdict, UserProfile

# 코드 -> (표시 이름, 동의어/파생 성분). 2글자 이상은 부분 문자열로, 1글자는 성분 단어 전체가 같을 때만 매칭.
ALLERGENS: dict[str, tuple[str, list[str]]] = {
    "egg": ("알류", ["알류", "계란", "달걀", "난백", "난황", "전란", "메추리알", "오리알", "egg"]),
    "milk": ("우유", ["우유", "원유", "유청", "유당", "분유", "탈지분유", "전지분유", "버터", "치즈", "크림", "카제인",
                      "연유", "요거트", "요구르트", "밀크", "유크림", "유단백", "milk", "whey", "casein", "lactose"]),
    "buckwheat": ("메밀", ["메밀", "buckwheat"]),
    "peanut": ("땅콩", ["땅콩", "피넛", "낙화생", "peanut"]),
    "soy": ("대두", ["대두", "콩", "두유", "두부", "간장", "된장", "레시틴(대두)", "대두레시틴", "soy", "soybean"]),
    "wheat": ("밀", ["밀", "밀가루", "소맥", "소맥분", "글루텐", "밀전분", "통밀", "wheat", "gluten"]),
    "mackerel": ("고등어", ["고등어", "mackerel"]),
    "crab": ("게", ["게", "게살", "꽃게", "대게", "크랩", "crab"]),
    "shrimp": ("새우", ["새우", "건새우", "새우젓", "쉬림프", "shrimp"]),
    "pork": ("돼지고기", ["돼지고기", "돈육", "돼지", "포크", "라드", "젤라틴(돼지)", "pork"]),
    "peach": ("복숭아", ["복숭아", "황도", "백도", "peach"]),
    "tomato": ("토마토", ["토마토", "케첩", "케찹", "tomato"]),
    "sulfite": ("아황산류", ["아황산", "메타중아황산", "이산화황", "sulfite", "sulphite"]),
    "walnut": ("호두", ["호두", "walnut"]),
    "chicken": ("닭고기", ["닭고기", "계육", "닭", "치킨", "chicken"]),
    "beef": ("쇠고기", ["쇠고기", "소고기", "우육", "beef"]),
    "squid": ("오징어", ["오징어", "squid"]),
    "shellfish": ("조개류", ["조개", "굴", "전복", "홍합", "바지락", "가리비", "모시조개", "oyster", "clam", "mussel",
                             "abalone", "scallop"]),
    "pine_nut": ("잣", ["잣", "pine nut"]),
}

# '콩'은 대두 외에 강낭콩·완두콩 등도 있지만, 표시상 혼동 위험이 커서 대두로 간주(안전 쪽).
_SPLIT = re.compile(r"[,，、/·\n;]+")
_PAREN = re.compile(r"[()\[\]{}]")
_CROSS_HINT = re.compile(r"(같은|동일한?)\s*(제조)?\s*(시설|공장|라인)|혼입|cross[- ]?contact|may contain", re.I)


def split_ingredients(raw: str | None) -> list[str]:
    """'밀가루, 설탕, 유청분말(우유), 쇼트닝(대두유)' -> 괄호 안 포함 평탄화한 성분 목록."""
    if not raw:
        return []
    text = _PAREN.sub(",", raw)
    items = []
    for part in _SPLIT.split(text):
        part = re.sub(r"\d+(\.\d+)?\s*%", "", part).strip(" .:-")
        if part:
            items.append(part)
    return items


# 알레르기 단어를 품고 있지만 그 알레르기와 무관한 성분 (5차 실험에서 발견한 오탐).
# 예: '메밀가루' 안의 '밀가루', '코코아버터' 안의 '버터'. 원재료 표시에 '(우유)' 처럼 따로 적혀 있으면 그건 그대로 잡힘.
_FALSE_FRIENDS: dict[str, tuple[str, ...]] = {
    "milk": ("코코아버터", "카카오버터", "땅콩버터", "피넛버터", "아몬드버터", "시어버터", "쉐어버터",
             "코코넛밀크", "코코넛크림", "아몬드밀크", "오트밀크", "귀리밀크", "라이스밀크", "cocoabutter",
             "coconutmilk"),
    "wheat": ("메밀",),
}


def _match(token: str, synonyms: list[str], code: str | None = None) -> str | None:
    low = token.lower().replace(" ", "")
    for ff in _FALSE_FRIENDS.get(code or "", ()):
        low = low.replace(ff, "")
    for s in synonyms:
        s2 = s.lower().replace(" ", "")
        if len(s2) == 1:
            if low == s2:
                return s
        elif s2 in low:
            return s
    return None


def detect(texts: list[str]) -> dict[str, str]:
    """텍스트 조각들에서 감지된 {알레르기코드: 근거 성분}."""
    found: dict[str, str] = {}
    for token in texts:
        for code, (_, syn) in ALLERGENS.items():
            if code not in found and _match(token, syn, code):
                found[code] = token
    return found


def ingredient_tokens(p: CollectedProduct) -> list[str]:
    return list(p.ingredients or []) + split_ingredients(p.ingredients_raw)


def assess(product: CollectedProduct, profile: UserProfile) -> SafetyVerdict:
    reasons: list[str] = []
    detected: set[str] = set()
    wanted = set(profile.allergens)

    tokens = ingredient_tokens(product)
    notice = split_ingredients(product.allergen_notice_raw)
    has_info = bool(tokens or notice)

    for source_name, texts in (("성분", tokens), ("알레르기 표시", notice)):
        for code, hit in detect(texts).items():
            if code in wanted and code not in detected:
                detected.add(code)
                reasons.append(f"{ALLERGENS[code][0]}({code}): {source_name} '{hit}'")

    if profile.exclude_cross_contact and product.cross_contact_raw:
        cross = split_ingredients(_CROSS_HINT.sub(",", product.cross_contact_raw))
        for code, hit in detect(cross).items():
            if code in wanted and code not in detected:
                detected.add(code)
                reasons.append(f"{ALLERGENS[code][0]}({code}): 혼입 가능 표시 '{hit}'")

    for word in profile.avoid_ingredients:
        w = word.strip().lower()
        if w and any(w in t.lower() for t in tokens):
            reasons.append(f"피하는 성분 '{word}'")

    if (wanted or profile.avoid_ingredients) and not has_info and profile.exclude_unknown:
        reasons.append("성분 정보 없음: 알레르기 안전 확인 불가")

    return SafetyVerdict(product.product_id, not reasons, reasons, sorted(detected))
