import os
import secrets
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .db import url
from .ingest import accept
from .models import Observation


@asynccontextmanager
async def lifespan(app):
    key = os.environ["COLLECTOR_TOKEN"]
    if len(key) < 32:
        raise RuntimeError("COLLECTOR_TOKEN must have at least 32 characters")
    app.state.token = key
    app.state.engine = create_async_engine(url("app"), hide_parameters=True, pool_pre_ping=True, pool_size=4, max_overflow=2)
    try:
        yield
    finally:
        await app.state.engine.dispose()


app = FastAPI(title="꿀픽 카탈로그 개발 API", version="0.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("DEV_ORIGINS","http://localhost:3000").split(","),
                   allow_methods=["GET"], allow_headers=["Content-Type"])
bearer = HTTPBearer(auto_error=False)


def collector(req: Request, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not auth or not secrets.compare_digest(auth.credentials.encode(), req.app.state.token.encode()):
        raise HTTPException(401, "COLLECTOR_AUTH_REQUIRED")


@app.exception_handler(RequestValidationError)
async def invalid(req, exc):
    return JSONResponse(status_code=422,content={"error":"INVALID_INPUT","fields":[e["loc"] for e in exc.errors()]})


@app.get("/health")
async def health(req: Request):
    async with req.app.state.engine.connect() as c:
        await c.execute(text("SELECT offer_id FROM app.offers LIMIT 0"))
    return {"status":"ok","database":"kkulpick_catalog"}


@app.post("/internal/v2/crawl-runs/{run_id}/observations", dependencies=[Depends(collector)])
async def ingest(run_id: UUID, obs: Observation, response: Response, req: Request):
    async with req.app.state.engine.begin() as c:
        result, created = await accept(c,run_id,obs)
    response.status_code = 201 if created else 200
    return result


@app.get("/v2/offers")
async def offers(req: Request, selected_domain: Literal["product","food"],
                 after: UUID | None = None, limit: int = Query(20,ge=1,le=100)):
    async with req.app.state.engine.connect() as c:
        rows = (await c.execute(text("""SELECT o.offer_id,i.name,o.source,o.variant_key,o.price::text AS price,
          o.currency,o.shipping_fee::text AS shipping_fee,o.current_url,o.price_observed_at
          FROM app.offers o JOIN app.catalog_items i USING(item_id)
          WHERE o.kind=:k AND o.condition='new' AND o.availability='available' AND o.fresh_until>now()
          AND (CAST(:after AS uuid) IS NULL OR o.offer_id>CAST(:after AS uuid)) ORDER BY o.offer_id LIMIT :n"""),
          {"k":selected_domain,"after":after,"n":limit+1})).mappings().all()
    return {"items":[dict(x) for x in rows[:limit]],"next_cursor":rows[limit-1]["offer_id"] if len(rows)>limit else None}
