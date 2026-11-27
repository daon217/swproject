"""일반 상품(식품 아님) 품목 분류: 보고 있는 상품과 같은 품목만 추천하기 위한 규칙 (식품은 food_types.py).

노트북 페이지에 키스킨·외장하드 케이스가 후보로 섞여, LLM 이 전부 버리면 '비슷한 상품 없음'이 되고
유사도 순으로 대신 보여주면 액세서리가 나왔다. 그래서 액세서리를 먼저 가려내고 품목을 비교한다.

- 액세서리를 가장 먼저 본다('노트북 키스킨'은 노트북이 아니라 액세서리).
- 상품명에 품목 이름이 없어도 사양으로 정한다('삼성전자 NT200B5C i5 4G SSD128G Win10' -> 노트북·PC).
- 수집된 분류(예: '프라이팬')가 있으면 그것을 먼저 쓴다.
"""
from __future__ import annotations

import re

ACCESSORY = "액세서리"

# (품목, 이 품목으로 볼 말, 같은 품목 후보를 이름으로 더 찾을 검색어). 순서가 우선순위다.
_TYPES: list[tuple[str, str, tuple[str, ...]]] = [
    # '파우치 증정'·'케이스 포함'은 덤이라 본품으로 본다. '리커버'(책)는 커버 아님.
    (ACCESSORY, r"(?:키스킨|키캡|케이스|보호필름|필름|파우치|거치대|스탠드|충전기|케이블|어댑터|(?<!리)커버|스킨|젠더|도킹)"
               r"(?!\s?(?:증정|포함|제공))", ()),
    ("스마트폰", r"스마트폰|휴대폰|아이폰|iphone|갤럭시\s?[sz]\d|갤럭시\s?노트|sm-[sfn]\d{3}", ("스마트폰", "갤럭시", "아이폰")),
    ("태블릿", r"태블릿|아이패드|ipad|갤럭시\s?탭", ("태블릿", "아이패드", "갤럭시탭")),
    ("모니터", r"모니터", ("모니터",)),
    # 사양 단어(i5·라이젠·Win10)는 노트북·PC 에만 쓴다. 다른 품목에서 틀리게 묶이면 여기서 고친다.
    ("노트북·PC", r"노트북|갤럭시\s?북|lg\s?그램|맥북|macbook|씽크패드|thinkpad|데스크[탑톱]|본체|게이밍\s?pc|미니\s?pc"
                 r"|(?<![a-z0-9])i[3579](?![0-9])|라이젠|ryzen|울트라\s?[579](?![0-9])|win(?:dows)?\s?1[01]",
     ("노트북", "갤럭시북", "그램", "데스크탑")),
    ("저장장치", r"외장\s?하드|외장\s?ssd|usb\s?메모리|메모리\s?카드|sd\s?카드", ("외장하드", "외장SSD")),
]
_COMPILED = [(name, re.compile(pattern, re.I), search) for name, pattern, search in _TYPES]


def product_type(name: str | None, category: str | None = None) -> str | None:
    """수집된 분류가 있으면 그것을 품목으로 쓰고('생선 저장 케이스'는 밀폐용기), 없으면 상품명으로 정한다. 모르면 None."""
    cat = (category or "").strip()
    if cat and cat.lower() != "product":
        return cat
    for kind, pattern, _ in _COMPILED:
        if pattern.search(name or ""):
            return kind
    return None


def product_search_terms(kind: str) -> tuple[str, ...]:
    return next((search for name, _, search in _COMPILED if name == kind), ())


def product_same_kind(query_kind: str | None, name: str, category: str | None) -> bool:
    """후보가 보고 있는 상품과 같은 품목인가. 품목을 모르면 액세서리만 뺀다."""
    kind = product_type(name, category)
    if query_kind is not None:
        return kind == query_kind
    return kind != ACCESSORY
