"""최종 선별. 입력은 이미 알레르기 검사를 통과한 후보뿐입니다.

- RuleRanker: 유사도 순. API 키 없이 테스트할 때 / LLM 실패 시 대체.
- ClaudeRanker: Claude 가 후보 중 고르고 이유를 씀. 응답은 JSON 스키마로 고정하고,
  후보 목록에 없는 id 는 코드에서 버림 (LLM 이 안전 검사를 우회할 수 없음).
"""
from __future__ import annotations

import json
import os

from pydantic import BaseModel, Field

from .contracts import CollectedProduct, UserProfile

DEFAULT_MODEL = os.getenv("RECO_LLM_MODEL", "claude-opus-5-5")


class RuleRanker:
    name = "rule"

    def rank(self, profile, query, items, top_k):
        ordered = sorted(items, key=lambda x: -x[1])[:top_k]
        return [(p.product_id, f"검색어와 유사도 {s:.2f}") for p, s in ordered]


class _Pick(BaseModel):
    product_id: str
    reason: str = Field(description="사용자에게 보여줄 한국어 추천 이유 1~2문장")


class _Picks(BaseModel):
    picks: list[_Pick]


SYSTEM_PROMPT = """너는 식품 쇼핑 추천 도우미다.
후보 상품은 이미 사용자의 알레르기 성분 검사를 통과했다. 너는 그중에서 사용자의 요청과 선호에
가장 잘 맞는 상품을 고르고, 왜 맞는지 짧게 설명한다.
- 반드시 후보 목록에 있는 product_id 만 쓴다.
- 알레르기 안전성을 새로 판단하거나 보장한다고 쓰지 않는다 (그 판단은 별도 시스템이 한다).
- 이유는 성분·카테고리·선호와 연결해 한국어 1~2문장으로 쓴다.
- 요청에 맞는 상품이 적으면 적게 골라도 된다."""


class ClaudeRanker:
    name = "claude"

    def __init__(self, model: str = DEFAULT_MODEL, client=None):
        import anthropic

        self.model = model
        self.client = client or anthropic.Anthropic()

    def rank(self, profile: UserProfile, query: str, items: list[tuple[CollectedProduct, float]], top_k: int):
        candidates = [{
            "product_id": p.product_id, "name": p.name, "category": p.category, "brand": p.brand,
            "price": p.price, "ingredients": p.ingredients_raw or ", ".join(p.ingredients or []),
            "similarity": round(s, 3),
        } for p, s in items]
        user = (f"사용자 요청: {query}\n선호: {profile.preferences or '없음'}\n"
                f"최대 {top_k}개까지 골라줘.\n\n후보(JSON):\n"
                + json.dumps(candidates, ensure_ascii=False, indent=1))
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": user}],
            output_format=_Picks,
        )
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise RuntimeError(f"LLM 응답 없음 (stop_reason={resp.stop_reason})")
        return [(x.product_id, x.reason) for x in resp.parsed_output.picks]


def make_ranker(kind: str):
    if kind == "rule":
        return RuleRanker()
    if kind == "claude":
        return ClaudeRanker()
    if kind == "auto":
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                return ClaudeRanker()
            except ImportError:
                pass
        return RuleRanker()
    raise ValueError("ranker 는 auto | rule | claude")
