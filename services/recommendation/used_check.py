"""중고 매물 실시간 재확인 (기술 명세서 9.4 / T09).

사용자가 검색했을 때 추천 후보에 든 중고 매물만 판매 페이지를 다시 확인합니다.
- 최근 TTL 안에 "판매 중" 으로 확인된 매물은 다시 확인하지 않음 (요청 수 절약).
- 404/410, 페이지의 판매완료·예약중 표시 -> ended (추천에서 제외).
- 403/timeout/알 수 없는 페이지 -> unknown. **판매종료로 바꾸지 않고**, 지금 구매 가능하다고도 보지 않아 제외.
- 허용한 판매처 호스트(CATALOG_URL_HOSTS)의 https 주소만 접속. 다른 호스트로 리다이렉트되면 따라가지 않음.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Iterable, Protocol

from .contracts import CollectedProduct

AVAILABLE, ENDED, UNKNOWN = "available", "ended", "unknown"


@dataclass(frozen=True)
class LiveStatus:
    product_id: str
    status: str            # available | ended | unknown
    evidence: str          # 사람이 읽는 근거. 예: "HTTP 410", "JSON-LD SoldOut", "최근 확인(3분 전)"
    checked_at: str


class ListingChecker(Protocol):
    def check(self, product: CollectedProduct) -> LiveStatus: ...


_SOLD_WORDS = re.compile(r"판매\s*완료|거래\s*완료|예약\s*중|판매\s*종료|품절|sold\s*out|reserved", re.I)
_LDJSON = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
_SCHEMA_ENDED = ("soldout", "outofstock", "discontinued")
_SCHEMA_OK = ("instock", "limitedavailability", "instoreonly", "onlineonly")


def _now() -> datetime:
    return datetime.now(UTC)


def _schema_availability(html: str) -> str | None:
    """JSON-LD Offer.availability 를 찾음. 'https://schema.org/InStock' -> 'instock'."""
    for block in _LDJSON.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                v = x.get("availability")
                if isinstance(v, str):
                    return v.rsplit("/", 1)[-1].lower()
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
    return None


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).hostname != urllib.parse.urlsplit(req.full_url).hostname:
            return None  # 다른 호스트로는 안 따라감 -> HTTPError 로 끝남
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpListingChecker:
    def __init__(self, allowed_hosts: Iterable[str], timeout: float = 4.0, max_bytes: int = 1_500_000,
                 user_agent: str = "kkulpick-used-check/0.1", schemes: tuple[str, ...] = ("https",)):
        self.allowed = {h.strip().lower() for h in allowed_hosts if h.strip()}
        self.timeout, self.max_bytes, self.ua, self.schemes = timeout, max_bytes, user_agent, schemes
        self._opener = urllib.request.build_opener(_SameHostRedirect)

    def _result(self, p: CollectedProduct, status: str, evidence: str) -> LiveStatus:
        return LiveStatus(p.product_id, status, evidence, _now().isoformat())

    def check(self, p: CollectedProduct) -> LiveStatus:
        url = p.url or ""
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in self.schemes or (parts.hostname or "").lower() not in self.allowed:
            return self._result(p, UNKNOWN, "허용되지 않은 주소라 확인 안 함")
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "text/html"})
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                html = r.read(self.max_bytes).decode(r.headers.get_content_charset() or "utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return self._result(p, ENDED, f"HTTP {e.code}")
            return self._result(p, UNKNOWN, f"HTTP {e.code}")  # 403·429·5xx 는 판매종료가 아님
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return self._result(p, UNKNOWN, f"접속 실패: {type(e).__name__}")

        sa = _schema_availability(html)
        if sa in _SCHEMA_ENDED:
            return self._result(p, ENDED, f"페이지 표시 {sa}")
        if sa in _SCHEMA_OK:
            return self._result(p, AVAILABLE, f"페이지 표시 {sa}")
        m = _SOLD_WORDS.search(html)
        if m:
            return self._result(p, ENDED, f"페이지 문구 '{m.group(0)}'")
        return self._result(p, UNKNOWN, "판매 상태를 페이지에서 찾지 못함")


def _fresh(p: CollectedProduct, ttl: timedelta, now: datetime) -> bool:
    if p.availability != "available" or not p.checked_at:
        return False
    try:
        t = datetime.fromisoformat(p.checked_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return t.tzinfo is not None and now - t <= ttl


def verify_used(products: list[CollectedProduct], checker: ListingChecker, *, ttl: timedelta = timedelta(minutes=10),
                max_workers: int = 6, budget_s: float = 6.0,
                now: Callable[[], datetime] = _now) -> dict[str, LiveStatus]:
    """중고 매물만 동시에 확인. 시간 안에 못 끝난 건 unknown. 신품은 건드리지 않음."""
    t0 = now()
    out: dict[str, LiveStatus] = {}
    todo = []
    for p in products:
        if not p.is_used:
            continue
        if p.availability in ("ended", "out_of_stock"):
            out[p.product_id] = LiveStatus(p.product_id, ENDED, f"저장된 상태 {p.availability}", t0.isoformat())
        elif _fresh(p, ttl, t0):
            out[p.product_id] = LiveStatus(p.product_id, AVAILABLE, "최근 확인됨", p.checked_at)
        else:
            todo.append(p)
    if not todo:
        return out
    pool = ThreadPoolExecutor(max_workers=min(max_workers, len(todo)))
    futs = {pool.submit(checker.check, p): p for p in todo}
    done, pending = wait(futs, timeout=budget_s)
    for f in done:
        p = futs[f]
        try:
            out[p.product_id] = f.result()
        except Exception as e:  # 확인기 버그가 추천 전체를 막지 않도록
            out[p.product_id] = LiveStatus(p.product_id, UNKNOWN, f"확인 오류: {type(e).__name__}", now().isoformat())
    for f in pending:
        p = futs[f]
        out[p.product_id] = LiveStatus(p.product_id, UNKNOWN, "확인 시간 초과", now().isoformat())
    pool.shutdown(wait=False, cancel_futures=True)
    return out
