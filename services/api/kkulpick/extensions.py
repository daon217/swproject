"""수집기가 보내는 상품 부가 정보(브랜드·분류·이미지)와 식품 성분 근거를 멱등하게 반영한다."""
import hashlib
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from sqlalchemy import text

from .ingest import encode, one, run
from .models import Key

router = APIRouter()
bearer = HTTPBearer(auto_error=False)
_PRIVATE_HOST = re.compile(
    r"^(?:localhost|127(?:\.\d{1,3}){3}|10(?:\.\d{1,3}){3}|169\.254(?:\.\d{1,3}){2}|"
    r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|\[?::1\]?|0\.0\.0\.0)$",
    re.I,
)


# Food allergen codes shared with the extension/mobile clients and member profiles.
FOOD_ALLERGENS = {
    "egg": "알류", "milk": "우유", "buckwheat": "메밀", "peanut": "땅콩", "soybean": "대두", "wheat": "밀",
    "mackerel": "고등어", "crab": "게", "shrimp": "새우", "pork": "돼지고기", "peach": "복숭아", "tomato": "토마토",
    "sulfite": "아황산류", "walnut": "호두", "chicken": "닭고기", "beef": "쇠고기", "squid": "오징어",
    "shellfish": "조개류", "pine_nut": "잣",
    "almond": "아몬드", "cashew": "캐슈넛", "pistachio": "피스타치오", "hazelnut": "헤이즐넛", "macadamia": "마카다미아",
    "sesame": "참깨", "kiwi": "키위", "banana": "바나나", "apple": "사과", "mango": "망고", "salmon": "연어",
    "tuna": "참치", "octopus": "문어·낙지", "lamb": "양고기", "celery": "셀러리", "mustard": "겨자", "corn": "옥수수",
}
_ALLERGEN_ALIASES = {"soy": "soybean", "pinenut": "pine_nut", "sulfites": "sulfite", "sulphite": "sulfite", "sulphites": "sulfite"} | {label: code for code, label in FOOD_ALLERGENS.items()}


def canonical_allergen(value: str) -> str | None:
    """'Soybean', 'soy', '대두', 'pine nut' -> client code; None when not a known code or label."""
    key = re.sub(r"[\s\-]+", "_", value.strip().lower())
    if key in FOOD_ALLERGENS:
        return key
    return _ALLERGEN_ALIASES.get(key) or _ALLERGEN_ALIASES.get(key.replace("_", "")) or _ALLERGEN_ALIASES.get(value.strip())


def collector_auth(req: Request, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not auth or not secrets.compare_digest(auth.credentials.encode(), req.app.state.token.encode()):
        raise HTTPException(401, "COLLECTOR_AUTH_REQUIRED")


def check_image_url(value: HttpUrl) -> HttpUrl:
    host = (value.host or "").lower()
    if value.scheme != "https" or value.username or value.password or not host or _PRIVATE_HOST.match(host):
        raise ValueError("image URL must be public HTTPS without credentials")
    allowed = [h.strip().lower() for h in os.getenv("CATALOG_IMAGE_HOSTS", "").split(",") if h.strip()]
    if allowed and host not in allowed:
        raise ValueError("image URL host is not in CATALOG_IMAGE_HOSTS")
    return value


class MatchingProfile(BaseModel):
    """상품 부가 정보. 저장하는 값은 브랜드·분류·대표/추가 이미지뿐이다.
    바코드(gtin)·부품번호(mpn)·모델명·색상·사이즈·옵션·제조사·판매자 정보는 읽는 기능이 없어 2026-11-27 DB에서
    지웠다. 도매꾹·11번가 수집기가 이 값을 보내도 오류 없이 받되 저장하지 않는다(팀원 수집 코드가 깨지지 않게)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    brand: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    image_url: HttpUrl | None = None
    image_urls: list[HttpUrl] = Field(default_factory=list, max_length=8)
    category: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    exact_match_confirmed: bool = False
    # 받기만 하고 저장하지 않는 예전 필드
    manufacturer: str | None = None
    model_name: str | None = None
    model_number: str | None = None
    mpn: str | None = None
    gtin: str | None = None
    identifiers: list[dict] = Field(default_factory=list, max_length=8)
    color: str | None = None
    size: str | None = None
    options: dict[str, str | None] = Field(default_factory=dict)
    seller_id: str | None = None
    seller_name: str | None = None

    @field_validator("image_url")
    @classmethod
    def valid_single_image(cls, value):
        return check_image_url(value) if value is not None else None

    @field_validator("image_urls")
    @classmethod
    def valid_image_list(cls, values):
        seen_urls: set[str] = set()
        deduped: list[HttpUrl] = []
        for v in values:
            check_image_url(v)
            s = str(v)
            if s not in seen_urls:
                seen_urls.add(s)
                deduped.append(v)
        return deduped


class FoodEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    ingredients_raw: Annotated[str, Field(min_length=1, max_length=4000)] | None = None
    ingredients: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=120)
    allergen_notice_raw: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    cross_contact_raw: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    allergens_declared: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(default_factory=list, max_length=32)
    evidence_status: Literal[
        "not_reported", "reported", "negative_claim_unverified", "conflicting", "image_only", "ocr_unverified"
    ] = "reported"

    @field_validator("allergens_declared")
    @classmethod
    def canonical_allergens(cls, values):
        # Store the client/profile code set (soybean, pine_nut, ...) so every reader compares the same codes (#59).
        # Unknown text is kept verbatim (never dropped): the recommender still text-matches it, safety first.
        out = []
        for value in values:
            code = canonical_allergen(value) or value
            if code not in out:
                out.append(code)
        return out


class ListingExtension(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schema_version: Literal[
        "listing-matching-extension-v1", "food-evidence-v1", "listing-extension-v1"
    ] = "listing-matching-extension-v1"
    source: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
    source_listing_id: Key
    variant_key: Key = "default"
    observation_key: Key
    observed_at: AwareDatetime
    product_url: HttpUrl | None = None
    is_synthetic: bool = False
    matching_profile: MatchingProfile | None = None
    food_evidence: FoodEvidence | None = None

    @field_validator("observed_at")
    @classmethod
    def timestamp(cls, value):
        if value > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("extension observation is in the future")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def has_extension_body(self):
        if self.matching_profile is None and self.food_evidence is None:
            raise ValueError("at least one of matching_profile or food_evidence is required")
        return self


async def accept_extension(c, run_id: UUID | None, ext: ListingExtension):
    source, key, at = ext.source, ext.observation_key, ext.observed_at
    data = ext.model_dump(mode="json", exclude_unset=True)
    raw = encode(data)
    digest = hashlib.sha256(raw.encode()).hexdigest()

    if run_id is not None:
        await run(c, "INSERT INTO app.crawl_runs(run_id,source) VALUES(:r,:s) ON CONFLICT DO NOTHING", r=run_id, s=source)
        if (await one(c, "SELECT source FROM app.crawl_runs WHERE run_id=:r", r=run_id))["source"] != source:
            raise HTTPException(409, "RUN_SOURCE_CONFLICT")

    row = await one(c, """INSERT INTO app.listing_extensions
        (run_id,source,observation_key,schema_version,payload_hash,observed_at,normalized_payload,state,change_kind,
         source_listing_id,variant_key)
        VALUES(:r,:s,:k,:sv,:h,:t,CAST(:p AS jsonb),'received','pending',:l,:v)
        ON CONFLICT(source,observation_key) DO NOTHING RETURNING extension_id""",
        r=run_id, s=source, k=key, sv=ext.schema_version, h=digest, t=at, p=raw,
        l=ext.source_listing_id, v=ext.variant_key)

    created = row is not None
    if not row:
        old = await one(c, """SELECT extension_id,offer_id,state,error_code,payload_hash,change_kind,changed_fields
            FROM app.listing_extensions WHERE source=:s AND observation_key=:k""", s=source, k=key)
        if old["payload_hash"] != digest:
            raise HTTPException(409, "EXTENSION_PAYLOAD_CONFLICT")
        if old["state"] != "pending":
            return {k: v for k, v in old.items() if k != "payload_hash"}, False
        # Held earlier because the offer did not exist yet: try again (resend or first observation).
        row = old

    eid = row["extension_id"]

    async def finish(state, offer=None, reason=None, kind=None, before=None, after=None):
        changed = sorted((after or {}).keys())
        result = await one(c, """UPDATE app.listing_extensions
            SET state=:s,offer_id=:f,error_code=:e,change_kind=:k,
                changed_fields=CAST(:fields AS jsonb),
                before_data=CAST(:b AS jsonb),after_data=CAST(:a AS jsonb)
            WHERE extension_id=:id
            RETURNING extension_id,offer_id,state,error_code,change_kind,changed_fields""",
            s=state, f=offer, e=reason, k=kind,
            fields=encode(changed), b=encode(before or {}), a=encode(after or {}), id=eid)
        return dict(result), created

    if at < datetime.now(UTC) - timedelta(days=30):
        return await finish("quarantine", reason="OBSERVATION_TOO_OLD", kind="quarantined")

    ident = dict(s=source, l=ext.source_listing_id, v=ext.variant_key)
    await run(c, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))", key=encode(list(ident.values())))

    tombstone = await one(c, """SELECT observed_at FROM app.offer_tombstones
        WHERE source=:s AND source_listing_id=:l AND variant_key=:v""", **ident)
    if tombstone and at <= tombstone["observed_at"]:
        return await finish("recorded", reason="DELETED_STALE_OBSERVATION", kind="stale")

    current = await one(c, """SELECT o.offer_id,o.item_id,o.kind,o.detail_observed_at,
        i.brand,i.category,i.image_url,i.image_urls,i.content_version
        FROM app.offers o JOIN app.catalog_items i USING(item_id)
        WHERE o.source=:s AND o.source_listing_id=:l AND o.variant_key=:v FOR UPDATE OF o,i""", **ident)
    if not current:
        # The collector may send details before the listing's first observation (separate queues).
        # Keep it; the first observation for this identity applies it. Maintenance expires stale ones.
        return await finish("pending", reason="OFFER_NOT_YET_OBSERVED", kind="pending")

    offer_id = current["offer_id"]
    item_id = current["item_id"]
    kind = current["kind"]

    if ext.food_evidence is not None and kind != "food":
        return await finish("quarantine", offer=offer_id, reason="DOMAIN_CONFLICT", kind="quarantined")

    before, after = {}, {}
    advanced = False

    if ext.matching_profile is not None:
        mp = ext.matching_profile
        if current["detail_observed_at"] is None or at > current["detail_observed_at"]:
            advanced = True
            images = [str(u) for u in mp.image_urls]
            primary_image = str(mp.image_url) if mp.image_url else (images[0] if images else None)
            if primary_image and primary_image not in images:
                images = [primary_image] + images[:7]

            item_updates = {}
            for col, val in (
                ("brand", mp.brand),
                ("category", mp.category),
                ("image_url", primary_image),
            ):
                if val is not None and current[col] != val:
                    before[col] = current[col]
                    after[col] = val
                    item_updates[col] = val
            if images and list(current["image_urls"] or []) != images:
                before["image_urls"] = current["image_urls"]
                after["image_urls"] = images
                item_updates["image_urls"] = encode(images)

            if item_updates:
                sets = []
                params = {"id": item_id}
                for col, val in item_updates.items():
                    if col == "image_urls":
                        sets.append("image_urls=CAST(:image_urls AS jsonb)")
                    else:
                        sets.append(f"{col}=:{col}")
                    params[col] = val
                await run(c, f"UPDATE app.catalog_items SET {','.join(sets)} WHERE item_id=:id", **params)

            await run(c, "UPDATE app.offers SET detail_observed_at=:at WHERE offer_id=:id", at=at, id=offer_id)

    if ext.food_evidence is not None:
        fe = ext.food_evidence
        food = await one(c, "SELECT * FROM app.foods WHERE item_id=:id FOR UPDATE", id=item_id)
        if food["food_observed_at"] is None or at > food["food_observed_at"]:
            advanced = True
            food_sets = ["food_observed_at=:at"]
            food_params = {"id": item_id, "at": at}
            for col in ("ingredients_raw", "allergen_notice_raw", "cross_contact_raw", "evidence_status"):
                val = getattr(fe, col)
                if val is not None and food[col] != val:
                    before[col] = food[col]
                    after[col] = val
                    food_sets.append(f"{col}=:{col}")
                    food_params[col] = val
            if fe.ingredients and list(food["ingredients"] or []) != fe.ingredients:
                before["ingredients"] = food["ingredients"]
                after["ingredients"] = fe.ingredients
                food_sets.append("ingredients=CAST(:ingredients AS jsonb)")
                food_params["ingredients"] = encode(fe.ingredients)
            if fe.allergens_declared and list(food["allergens_declared"] or []) != fe.allergens_declared:
                before["allergens_declared"] = food["allergens_declared"]
                after["allergens_declared"] = fe.allergens_declared
                food_sets.append("allergens_declared=CAST(:allergens_declared AS jsonb)")
                food_params["allergens_declared"] = encode(fe.allergens_declared)
            await run(c, f"UPDATE app.foods SET {','.join(food_sets)} WHERE item_id=:id", **food_params)

    if after:
        await run(c, "UPDATE app.offers SET last_changed_at=greatest(last_changed_at,:t) WHERE offer_id=:id", t=at, id=offer_id)
    change_kind = "updated" if after else "unchanged" if advanced else "stale"
    state = "recorded" if change_kind == "stale" else "applied"
    reason = "NO_NEWER_FIELDS" if change_kind == "stale" else None
    return await finish(state, offer=offer_id, reason=reason, kind=change_kind, before=before, after=after)


async def apply_pending_extensions(c, source: str, listing_id: str, variant_key: str) -> int:
    """Apply extensions held for an identity whose offer now exists. Runs inside the observation's
    transaction (same identity lock). Each one gets a savepoint, so a held extension that no longer
    validates (e.g. CATALOG_IMAGE_HOSTS changed) is quarantined instead of failing the observation."""
    held = (await c.execute(text("""SELECT extension_id,run_id,normalized_payload FROM app.listing_extensions
        WHERE state='pending' AND source=:s AND source_listing_id=:l AND variant_key=:v
        ORDER BY observed_at,extension_id"""), dict(s=source, l=listing_id, v=variant_key))).mappings().all()
    applied = 0
    for item in held:
        try:
            async with c.begin_nested():
                await accept_extension(c, item["run_id"], ListingExtension.model_validate(item["normalized_payload"]))
            applied += 1
        except (ValueError, HTTPException):
            await run(c, """UPDATE app.listing_extensions SET state='quarantine',change_kind='quarantined',
                error_code='INVALID_PENDING_EXTENSION' WHERE extension_id=:id""", id=item["extension_id"])
    return applied


def _status(result, created):
    if result.get("state") == "pending":
        return 202
    return 201 if created else 200


@router.post("/internal/v2/crawl-runs/{run_id}/extensions", dependencies=[Depends(collector_auth)])
async def ingest_run_extension(run_id: UUID, ext: ListingExtension, response: Response, req: Request):
    async with req.app.state.engine.begin() as c:
        result, created = await accept_extension(c, run_id, ext)
    response.status_code = _status(result, created)
    return result


@router.post("/internal/v2/listing-extensions", dependencies=[Depends(collector_auth)])
async def ingest_listing_extension(ext: ListingExtension, response: Response, req: Request):
    async with req.app.state.engine.begin() as c:
        result, created = await accept_extension(c, None, ext)
    response.status_code = _status(result, created)
    return result
