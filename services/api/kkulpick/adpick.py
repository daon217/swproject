"""Convert a shopping URL into an Adpick affiliate link.

Upstream limits (from the Adpick account): 60 requests per minute, and HTTP 400 for URLs
it does not support. The key stays on the server; clients only ever see the converted link.

Configuration (services/api/.env, never committed):
  ADPICK_API_KEY              required, the issued key
  ADPICK_API_URL              required, the conversion endpoint (HTTPS)
  ADPICK_REQUESTS_PER_MINUTE  global upstream budget, default 60
  ADPICK_CLIENT_PER_MINUTE    per-client budget on our endpoint, default 10
  ADPICK_AUTH_HEADER          header carrying the key, default "Authorization"
  ADPICK_AUTH_SCHEME          prefix before the key, default "Bearer" (empty for a bare key)
  ADPICK_URL_PARAM            request field holding the original URL, default "url"
  ADPICK_TIMEOUT_SECONDS      default 8
"""
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request as UpstreamRequest, urlopen

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, field_validator
from starlette.concurrency import run_in_threadpool

from .extensions import _PRIVATE_HOST
from .members import Strict, row, wrap

router = APIRouter()
log = logging.getLogger('kkulpick.adpick')

SUCCESS_TTL = 24 * 3600
UNSUPPORTED_TTL = 3600
_CACHE_MAX = 5000
_cache: OrderedDict[str, tuple[float, str | None]] = OrderedDict()
# Response fields an affiliate link may come back in, checked in order (nested under "data" too).
_LINK_FIELDS = ('affiliate_url', 'affiliateUrl', 'deeplink', 'deep_link', 'short_url', 'shortUrl',
                'link', 'url', 'result')


class Conversion(Strict):
    url: str = Field(min_length=1, max_length=2048)

    @field_validator('url')
    @classmethod
    def public_web_url(cls, value):
        value = value.strip()
        u = urlsplit(value)
        host = (u.hostname or '').lower()
        if u.scheme not in ('http', 'https') or not host or u.username or u.password or _PRIVATE_HOST.match(host):
            raise ValueError('a public http(s) URL without credentials is required')
        return value


class UpstreamUnsupported(Exception):
    pass


class UpstreamUnavailable(Exception):
    def __init__(self, status=None, retry_after=None):
        super().__init__(status)
        self.status = status
        self.retry_after = retry_after


def _settings():
    key = os.getenv('ADPICK_API_KEY', '').strip()
    endpoint = os.getenv('ADPICK_API_URL', '').strip()
    if not key or not endpoint.startswith('https://'):
        raise HTTPException(503, 'AFFILIATE_LINK_NOT_CONFIGURED')
    return key, endpoint


def _cache_get(url):
    hit = _cache.get(url)
    if not hit:
        return None
    expires, link = hit
    if expires < time.monotonic():
        _cache.pop(url, None)
        return None
    _cache.move_to_end(url)
    return hit


def _cache_put(url, link, ttl):
    _cache[url] = (time.monotonic() + ttl, link)
    _cache.move_to_end(url)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def _extract_link(payload):
    if isinstance(payload, str):
        return payload if payload.startswith(('https://', 'http://')) else None
    if not isinstance(payload, dict):
        return None
    for scope in (payload, payload.get('data'), payload.get('result')):
        if isinstance(scope, dict):
            for field in _LINK_FIELDS:
                value = scope.get(field)
                if isinstance(value, str) and value.startswith(('https://', 'http://')):
                    return value
        elif isinstance(scope, str) and scope.startswith(('https://', 'http://')):
            return scope
    return None


def call_upstream(url, key, endpoint):
    """Blocking call (run in a thread). Never logs the key or the full upstream body."""
    scheme = os.getenv('ADPICK_AUTH_SCHEME', 'Bearer').strip()
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
               os.getenv('ADPICK_AUTH_HEADER', 'Authorization'): f'{scheme} {key}' if scheme else key}
    body = json.dumps({os.getenv('ADPICK_URL_PARAM', 'url'): url}).encode()
    request = UpstreamRequest(endpoint, data=body, headers=headers, method='POST')
    try:
        with urlopen(request, timeout=float(os.getenv('ADPICK_TIMEOUT_SECONDS', '8'))) as response:
            raw = response.read(65536)
    except HTTPError as error:
        if error.code == 400:
            raise UpstreamUnsupported() from None
        retry_after = error.headers.get('Retry-After') if error.headers else None
        raise UpstreamUnavailable(error.code, retry_after) from None
    except (URLError, TimeoutError, OSError) as error:
        raise UpstreamUnavailable(type(error).__name__) from None
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = raw.decode('utf-8', 'replace').strip()
    link = _extract_link(payload)
    if not link:
        raise UpstreamUnavailable('UNRECOGNIZED_RESPONSE')
    return link


async def _take_slot(req, bucket, limit, code):
    """Fixed one-minute window shared by every API worker (same table as auth throttling)."""
    digest = hashlib.sha256(bucket.encode()).hexdigest()
    async with req.app.state.member_engine.begin() as conn:
        r = await row(conn, """INSERT INTO app.auth_attempts(bucket,attempts) VALUES(:b,1)
            ON CONFLICT(bucket) DO UPDATE SET
            attempts=CASE WHEN app.auth_attempts.window_start<now()-interval '1 minute' THEN 1 ELSE app.auth_attempts.attempts+1 END,
            window_start=CASE WHEN app.auth_attempts.window_start<now()-interval '1 minute' THEN now() ELSE app.auth_attempts.window_start END
            RETURNING attempts, greatest(1, ceil(extract(epoch FROM window_start+interval '1 minute'-now())))::int AS wait""",
            b=digest)
    if r['attempts'] > limit:
        raise HTTPException(429, code, headers={'Retry-After': str(r['wait'])})


@router.post('/v2/links/convert')
async def convert(data: Conversion, req: Request):
    key, endpoint = _settings()
    cached = _cache_get(data.url)
    if cached:
        if cached[1] is None:
            raise HTTPException(400, 'AFFILIATE_URL_UNSUPPORTED')
        return wrap({'original_url': data.url, 'affiliate_url': cached[1], 'cached': True}, req)

    client = req.client.host if req.client else 'unknown'
    await _take_slot(req, 'adpick-client:' + client, int(os.getenv('ADPICK_CLIENT_PER_MINUTE', '10')),
                     'AFFILIATE_LINK_RATE_LIMITED')
    # Global budget last, so one noisy client cannot consume upstream quota it is not allowed to use.
    await _take_slot(req, 'adpick-upstream', int(os.getenv('ADPICK_REQUESTS_PER_MINUTE', '60')),
                     'AFFILIATE_LINK_BUSY')
    try:
        link = await run_in_threadpool(call_upstream, data.url, key, endpoint)
    except UpstreamUnsupported:
        _cache_put(data.url, None, UNSUPPORTED_TTL)
        raise HTTPException(400, 'AFFILIATE_URL_UNSUPPORTED') from None
    except UpstreamUnavailable as error:
        log.warning('adpick_unavailable request_id=%s status=%s', req.state.request_id, error.status)
        if error.status == 429:
            retry = error.retry_after if (error.retry_after or '').isdigit() else '60'
            raise HTTPException(429, 'AFFILIATE_LINK_BUSY', headers={'Retry-After': retry}) from None
        if error.status in (401, 403):
            raise HTTPException(503, 'AFFILIATE_LINK_NOT_CONFIGURED') from None
        raise HTTPException(503, 'AFFILIATE_LINK_UNAVAILABLE', headers={'Retry-After': '5'}) from None
    _cache_put(data.url, link, SUCCESS_TTL)
    return wrap({'original_url': data.url, 'affiliate_url': link, 'cached': False}, req)
