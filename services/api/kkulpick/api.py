import os
import secrets
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from .errors import install_errors
from .members import router as member_router
from .accounts import router as account_router
from .support import router as support_router
from .affiliates import router as affiliate_router
from .analyses import router as analysis_router
from .console import router as console_router

from .db import url
from .ingest import accept
from .models import Observation
from .limits import RequestBodyLimit


@asynccontextmanager
async def lifespan(app):
    key = os.environ["COLLECTOR_TOKEN"]
    if len(key) < 32:
        raise RuntimeError("COLLECTOR_TOKEN must have at least 32 characters")
    app.state.token = key
    app.state.engine = create_async_engine(url("app"), hide_parameters=True, pool_pre_ping=True, pool_size=4, max_overflow=2)
    app.state.member_engine = create_async_engine(url("app", "member"), hide_parameters=True, pool_pre_ping=True, pool_size=3, max_overflow=1)
    app.state.support_engine = create_async_engine(url("app", "support"), hide_parameters=True, pool_pre_ping=True, pool_size=2, max_overflow=1)
    try:
        yield
    finally:
        await app.state.engine.dispose()
        await app.state.member_engine.dispose()
        await app.state.support_engine.dispose()


app = FastAPI(title="꿀픽 카탈로그 개발 API", version="0.1", lifespan=lifespan)
for router in (member_router, account_router, support_router, affiliate_router, analysis_router, console_router):
    app.include_router(router)
app.add_middleware(RequestBodyLimit)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("DEV_ORIGINS","http://localhost:3000").split(","),
                   allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
                   expose_headers=["X-Request-ID", "Retry-After"])
bearer = HTTPBearer(auto_error=False)


def collector(req: Request, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not auth or not secrets.compare_digest(auth.credentials.encode(), req.app.state.token.encode()):
        raise HTTPException(401, "COLLECTOR_AUTH_REQUIRED")


install_errors(app)


@app.get("/health")
async def health(req: Request):
    async with req.app.state.engine.connect() as c:
        await c.execute(text("SELECT offer_id FROM app.offers LIMIT 0"))
    async with req.app.state.member_engine.connect() as c:
        await c.execute(text("SELECT user_id FROM app.members LIMIT 0"))
    async with req.app.state.support_engine.connect() as c:
        await c.execute(text("SELECT conversation_id FROM app.conversations LIMIT 0"))
    return {"status":"ok","database":"kkulpick_catalog"}


@app.post("/internal/v2/crawl-runs/{run_id}/observations", dependencies=[Depends(collector)])
async def ingest(run_id: UUID, obs: Observation, response: Response, req: Request):
    async with req.app.state.engine.begin() as c:
        result, created = await accept(c,run_id,obs)
    response.status_code = 201 if created else 200
    return result


@app.get("/v2/offers")
async def offers(req: Request, selected_domain: Literal["product","food"],
                 after: UUID | None = None, limit: int = Query(20,ge=1,le=100),
                 condition: Literal["new", "used", "all"] = "new",
                 availability: Literal["available", "out_of_stock", "ended", "suspect", "all"] = "available",
                 source: str | None = Query(None, max_length=64),
                 currency: str | None = Query(None, pattern=r"^[A-Z]{3}$")):
    async with req.app.state.engine.connect() as c:
        rows = (await c.execute(text("""SELECT o.offer_id,i.name,i.description,o.source,o.variant_key,o.price::text AS price,
          o.currency,o.shipping_fee::text AS shipping_fee,o.current_url,o.price_observed_at,
          o.condition,o.availability,o.source_listing_id,o.last_seen_at,o.last_checked_at,o.last_changed_at
          FROM app.offers o JOIN app.catalog_items i USING(item_id)
          WHERE o.kind=:k AND (:condition='all' OR o.condition=:condition)
          AND (:availability='all' OR o.availability=:availability)
          AND (CAST(:source AS text) IS NULL OR o.source=:source)
          AND (CAST(:currency AS text) IS NULL OR o.currency=:currency)
          AND (CAST(:after AS uuid) IS NULL OR o.offer_id>CAST(:after AS uuid)) ORDER BY o.offer_id LIMIT :n"""),
          {"k":selected_domain,"after":after,"n":limit+1,"condition":condition,
           "availability":availability,"source":source,"currency":currency})).mappings().all()
    return {"items":[dict(x) for x in rows[:limit]],"next_cursor":rows[limit-1]["offer_id"] if len(rows)>limit else None}
