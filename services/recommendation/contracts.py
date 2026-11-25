"""추천 파이프라인이 주고받는 데이터 계약.

DB 스키마와 무관하게 고정된 형식입니다. 수집기(최준서)는 CollectedProduct JSON을
보내고, 어떤 저장소(로컬 JSON, 이후 소병선 DB)를 쓰든 이 형식으로 읽고 씁니다.
DB가 확정되면 어댑터만 이 형식 <-> DB 행으로 변환하면 됩니다.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

PRODUCT_SCHEMA = "kkulpick.collected-product/1"
PROFILE_SCHEMA = "kkulpick.user-profile/1"

_SOURCE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_PRICE = re.compile(r"^\d{1,16}(\.\d{1,4})?$")


class ContractError(ValueError):
    """계약 위반. errors 에 필드별 사유가 들어갑니다."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class CollectedProduct:
    """수집기가 보내는 상품 1건 (JSON Lines 한 줄)."""

    source: str                      # 수집처 코드. 예: "coupang", "demo"
    source_listing_id: str           # 수집처 안에서의 상품 id
    name: str
    category: str | None = None      # 예: "과자", "음료"
    brand: str | None = None
    price: str | None = None         # 소수 문자열. 예: "12000" (API Observation 과 같은 규칙)
    currency: str | None = None      # 예: "KRW"
    url: str | None = None
    image_url: str | None = None
    ingredients_raw: str | None = None      # 성분표 원문 (OCR 결과 포함)
    allergen_notice_raw: str | None = None  # "우유, 대두 함유" 같은 알레르기 표시 원문
    cross_contact_raw: str | None = None    # "같은 제조시설에서 땅콩 ... 제조" 원문
    ingredients: list[str] | None = None    # 수집기가 이미 나눈 성분 목록 (없으면 원문을 파싱)
    allergens_declared: list[str] | None = None  # 판매처가 신고한 알레르기 코드. 예: ["milk", "soybean"] (글자 매칭 안 함)
    description: str | None = None
    collected_at: str | None = None         # ISO-8601
    condition: str | None = None            # "new" | "used" (없으면 new 로 봄)
    availability: str | None = None         # "available" | "out_of_stock" | "ended" | "suspect"
    checked_at: str | None = None           # 판매 상태를 마지막으로 확인한 시각 (ISO-8601)
    schema: str = PRODUCT_SCHEMA

    @property
    def product_id(self) -> str:
        return f"{self.source}:{self.source_listing_id}"

    @property
    def is_used(self) -> bool:
        return self.condition == "used"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CollectedProduct":
        errors: list[str] = []
        known = set(cls.__dataclass_fields__)
        extra = set(data) - known
        if extra:
            errors.append(f"알 수 없는 필드: {sorted(extra)}")
        if data.get("schema", PRODUCT_SCHEMA) != PRODUCT_SCHEMA:
            errors.append(f"schema 는 {PRODUCT_SCHEMA} 이어야 함")
        for key in ("source", "source_listing_id", "name"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                errors.append(f"{key} 필수(문자열)")
        if isinstance(data.get("source"), str) and not _SOURCE.match(data["source"]):
            errors.append("source 는 소문자 영문/숫자/_/- (API Observation 과 같은 규칙)")
        price, cur = data.get("price"), data.get("currency")
        if price is not None and (not isinstance(price, str) or not _PRICE.match(price)):
            errors.append('price 는 "12000" 같은 소수 문자열')
        if (price is None) != (cur is None):
            errors.append("price 와 currency 는 함께 보내야 함")
        if cur is not None and (not isinstance(cur, str) or not _CURRENCY.match(cur)):
            errors.append("currency 는 KRW 같은 3글자 대문자")
        if data.get("condition") not in (None, "new", "used"):
            errors.append("condition 은 new | used")
        if data.get("availability") not in (None, "available", "out_of_stock", "ended", "suspect"):
            errors.append("availability 는 available | out_of_stock | ended | suspect")
        ing = data.get("ingredients")
        if ing is not None and (not isinstance(ing, list) or not all(isinstance(x, str) for x in ing)):
            errors.append("ingredients 는 문자열 목록")
        dec = data.get("allergens_declared")
        if dec is not None and (not isinstance(dec, list) or not all(isinstance(x, str) for x in dec)):
            errors.append("allergens_declared 는 문자열 목록")
        if not any(data.get(k) for k in ("ingredients_raw", "ingredients", "allergen_notice_raw", "allergens_declared")):
            # 저장은 허용하지만 알레르기 사용자에게는 추천되지 않음 (정보 없음 = 안전 확인 불가)
            pass
        if errors:
            raise ContractError(errors)
        clean = {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items() if k in known}
        return cls(**clean)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class UserProfile:
    user_id: str
    allergens: list[str] = field(default_factory=list)          # allergens.py 의 코드. 예: ["milk", "peanut"]
    avoid_ingredients: list[str] = field(default_factory=list)  # 자유 입력 성분. 예: ["카페인"]
    preferences: str = ""                                       # 자연어 선호. 예: "단백질 많은 간식"
    exclude_cross_contact: bool = True   # "같은 시설 제조" 표시도 제외할지
    exclude_unknown: bool = True         # 성분 정보 없는 상품을 제외할지 (알레르기가 있을 때만 적용)
    include_used: bool = False           # 중고 포함 (member DB user_profiles.include_used, 식품에는 적용 안 함)
    schema: str = PROFILE_SCHEMA

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        from .allergens import ALLERGENS  # 순환 import 방지

        errors = []
        if not isinstance(data.get("user_id"), str) or not data["user_id"]:
            errors.append("user_id 필수")
        unknown = [a for a in data.get("allergens", []) if a not in ALLERGENS]
        if unknown:
            errors.append(f"모르는 알레르기 코드: {unknown} (가능: {sorted(ALLERGENS)})")
        extra = set(data) - set(cls.__dataclass_fields__)
        if extra:
            errors.append(f"알 수 없는 필드: {sorted(extra)}")
        if errors:
            raise ContractError(errors)
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Candidate:
    """벡터 검색 결과 1건. 점수만 있고 안전 판정은 없음."""

    product_id: str
    score: float  # 코사인 유사도 (클수록 비슷)


@dataclass(frozen=True)
class SafetyVerdict:
    product_id: str
    safe: bool
    reasons: list[str]          # 제외 사유. 예: ["우유(milk): 성분 '탈지분유'"]
    detected: list[str]         # 감지된 알레르기 코드


@dataclass(frozen=True)
class Pick:
    product_id: str
    name: str
    reason: str
    score: float


@dataclass(frozen=True)
class RecommendationResult:
    """프론트로 넘길 응답 형식."""

    user_id: str
    query: str
    picks: list[Pick]
    excluded: list[SafetyVerdict]
    ranker: str                 # "claude" | "rule" | "rule-fallback"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
