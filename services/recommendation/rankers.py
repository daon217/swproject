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

DEFAULT_MODEL = os.getenv("RECO_LLM_MODEL") or "claude-opus-5-5"  # 빈 값(compose 기본)도 기본 모델로
FALLBACK_MODEL = os.getenv("RECO_FALLBACK_LLM_MODEL") or "claude-sonnet-4-6"  # DB 추천 0건 시 실시간 폴백 전용 가벼운 모델


class RuleRanker:
    name = "rule"

    def rank(self, profile, query, items, top_k):
        ordered = sorted(items, key=lambda x: -x[1])[:top_k]
        return [(p.product_id, f"검색어와 유사도 {s:.2f}") for p, s in ordered]


class _Pick(BaseModel):
    id: str = Field(description="후보 번호. 예: c1")
    reason: str = Field(description="한국어 한 문장, 40자 이내")


class _Picks(BaseModel):
    picks: list[_Pick]


def render_candidates(fmt: str, profile: UserProfile, query: str, items, top_k: int, **opts):
    """LLM 입력 만들기. (system, user, id_map). fmt: compact(우리 압축) | json(압축 전) | toon.
    opts 는 compact_candidates 로 (max_items, ing_limit, show_category ...)."""
    from .compress import SYSTEM_PROMPT, compact_candidates, user_message

    c = compact_candidates(profile, query, items, **opts)
    if fmt == "compact":
        return SYSTEM_PROMPT, user_message(profile, query, c, top_k), c.id_map
    rows = []
    by_pid = {p.product_id: p for p, _ in items}
    for cid, pid in c.id_map.items():  # 같은 후보·같은 순서로 형식만 바꿈 (공정 비교)
        p = by_pid[pid]
        rows.append({"id": cid, "name": p.name, "category": p.category, "brand": p.brand, "price": p.price,
                     "currency": p.currency, "ingredients": p.ingredients_raw or ", ".join(p.ingredients or []),
                     "condition": p.condition or "new"})
    if fmt == "json":
        body = json.dumps(rows, ensure_ascii=False, indent=1)
    elif fmt == "toon":
        import toon_format  # pip install toon-format

        body = toon_format.encode({"candidates": rows})
    else:
        raise ValueError("fmt 는 compact | json | toon")
    head = user_message(profile, query, c, top_k).split("후보:")[0]
    return SYSTEM_PROMPT.replace('"번호|이름|분류|가격|주요성분|중고표시"', f"{fmt} 형식"), head + "후보:\n" + body, c.id_map


class ClaudeRanker:
    name = "claude"

    def __init__(self, model: str = DEFAULT_MODEL, client=None, fmt: str = "compact", max_tokens: int = 600,
                 **render_opts):
        import anthropic

        self.model, self.fmt, self.max_tokens, self.render_opts = model, fmt, max_tokens, render_opts
        self.client = client or anthropic.Anthropic()
        self.last_usage = None  # 실험 로그용 (input_tokens, output_tokens)

    def rank(self, profile: UserProfile, query: str, items: list[tuple[CollectedProduct, float]], top_k: int):
        return self.rank_rendered(*render_candidates(self.fmt, profile, query, items, top_k, **self.render_opts))

    def rank_rendered(self, system: str, user: str, id_map: dict[str, str]):
        import anthropic
        self.last_usage = None  # 실패한 호출에 이전 호출의 토큰 수가 남지 않도록
        kw = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=_Picks,
        )
        try:
            resp = self.client.messages.parse(**kw, output_config={"effort": "low"})
        except anthropic.BadRequestError as e:
            if "effort" not in str(e):
                raise
            resp = self.client.messages.parse(**kw)
        u = getattr(resp, "usage", None)
        self.last_usage = (getattr(u, "input_tokens", None), getattr(u, "output_tokens", None)) if u else None
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise RuntimeError(f"LLM 응답 없음 (stop_reason={resp.stop_reason})")
        # 짧은 번호 -> 실제 id. 모르는 번호는 그대로 넘겨서 pipeline 이 "후보 밖" 으로 버리게 함
        return [(id_map.get(x.id, f"unknown:{x.id}"), x.reason) for x in resp.parsed_output.picks]


def _parse_picks(text: str) -> list[_Pick]:
    """로컬 모델은 JSON 앞뒤로 말을 붙이기도 함 -> 첫 { ... } 만 꺼내서 검증."""
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("JSON 없음")
    return _Picks.model_validate_json(text[a:b + 1]).picks


class LocalLLMRanker:
    """OpenAI 호환 /v1/chat/completions (Ollama, vLLM, LM Studio, llama.cpp server). 추가 패키지 없음.

    환경변수: LOCAL_LLM_BASE_URL, LOCAL_LLM_MODEL, LOCAL_LLM_API_KEY (없으면 SUNMOON_API_KEY)
    기본값은 학교 지원 서버 (https://llm.deepaibit.com/v1, gemma-4-26b). 키는 코드에 적지 말고 환경변수로만.
    """
    name = "local"

    def __init__(self, base_url: str | None = None, model: str | None = None, fmt: str = "compact",
                 max_tokens: int = 600, timeout: float = 120.0, api_key: str | None = None, **render_opts):
        self.base = (base_url or os.getenv("LOCAL_LLM_BASE_URL") or "https://llm.deepaibit.com/v1").rstrip("/")
        self.model = model or os.getenv("LOCAL_LLM_MODEL") or "gemma-4-26b"
        self.api_key = api_key or os.getenv("LOCAL_LLM_API_KEY") or os.getenv("SUNMOON_API_KEY")
        self.fmt, self.max_tokens, self.timeout, self.render_opts = fmt, max_tokens, timeout, render_opts
        self.last_usage = None

    def rank(self, profile, query, items, top_k):
        return self.rank_rendered(*render_candidates(self.fmt, profile, query, items, top_k, **self.render_opts))

    def _post(self, body: dict, headers: dict, retries: int = 3) -> dict:
        import re
        import time
        import urllib.error
        import urllib.request

        url = f"{self.base}/chat/completions"
        for attempt in range(retries + 1):
            req = urllib.request.Request(url, json.dumps(body).encode(), headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code == 400 and "response_format" in body:  # json 모드 미지원 서버
                    body = {k: v for k, v in body.items() if k != "response_format"}
                    continue
                if e.code == 429 and attempt < retries:  # 학교 서버: 키당 요청 수 제한
                    wait = e.headers.get("Retry-After")
                    time.sleep(min(float(wait), 120) if wait and wait.replace(".", "").isdigit() else 20 * (attempt + 1))
                    continue
                detail = e.read(300).decode("utf-8", "replace").replace("\n", " ")
                detail = re.sub(r"(api_key:?\s*)\S+", r"\1***", detail)  # 키 식별값은 기록에 남기지 않음
                raise RuntimeError(f"LLM 서버 HTTP {e.code}: {detail}") from None
        raise RuntimeError("LLM 서버 재시도 초과")

    def rank_rendered(self, system: str, user: str, id_map: dict[str, str]):
        self.last_usage = None  # 실패한 호출에 이전 호출의 토큰 수가 남지 않도록

        body = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system + '\n\n출력: {"picks":[{"id":"c1","reason":"..."}]} JSON 만.'},
                             {"role": "user", "content": user}]}
        # Python 기본 User-Agent(Python-urllib) 는 Cloudflare 등에서 403 으로 막히는 경우가 많음
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": "kkulpick-recommendation/0.1"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = self._post(body, headers)
        u = data.get("usage") or {}
        self.last_usage = (u.get("prompt_tokens"), u.get("completion_tokens"))
        picks = _parse_picks(data["choices"][0]["message"]["content"] or "")
        return [(id_map.get(x.id, f"unknown:{x.id}"), x.reason) for x in picks]


def make_ranker(kind: str, model: str | None = None):
    if kind == "rule":
        return RuleRanker()
    if kind == "claude":
        return ClaudeRanker(model=model or DEFAULT_MODEL)
    if kind == "local":
        return LocalLLMRanker(model=model)
    if kind == "auto":
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                return ClaudeRanker(model=model or DEFAULT_MODEL)
            except ImportError:
                pass
        return RuleRanker()
    raise ValueError("ranker 는 auto | rule | claude | local")
