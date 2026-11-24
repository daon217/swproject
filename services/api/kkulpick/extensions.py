"""Idempotent listing extension ingestion (matching profile & food evidence) and candidate matching."""
import hashlib
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from .ingest import encode, one, run
from .models import Key

router = APIRouter()
bearer = HTTPBearer(auto_error=False)
_PRIVATE_HOST = re.compile(
    r"^(?:localhost|127(?:\.\d{1,3}){3}|10(?:\.\d{1,3}){3}|169\.254(?:\.\d{1,3}){2}|"
    r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|\[?::1\]?|0\.0\.0\.0)$",
    re.I,
)


def collector_auth(req: Request, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not auth or not secrets.compare_digest(auth.credentials.encode(), req.app.state.token.encode()):
        raise HTTPException(401, "COLLECTOR_AUTH_REQUIRED")


def canonical_gtin(raw: str) -> str:
    value = raw.strip() if isinstance(raw, str) else ""
    if not value.isdigit() or len(value) not in (8, 12, 13, 14):
        raise ValueError("GTIN must be an 8, 12, 13, or 14 digit string")
    padded = value.zfill(14)
    total = sum((3 if idx % 2 == 0 else 1) * int(ch) for idx, ch in enumerate(padded[:13]))
    check = (10 - (total % 10)) % 10
    if check != int(padded[13]):
        raise ValueError("invalid GTIN check digit")
    return padded


def check_image_url(value: HttpUrl) -> HttpUrl:
    host = (value.host or "").lower()
    if value.scheme != "https" or value.username or value.password or not host or _PRIVATE_HOST.match(host):
        raise ValueError("image URL must be public HTTPS without credentials")
    allowed = [h.strip().lower() for h in os.getenv("CATALOG_IMAGE_HOSTS", "").split(",") if h.strip()]
    if allowed and host not in allowed:
        raise ValueError("image URL host is not in CATALOG_IMAGE_HOSTS")
    return value


class ProductIdentifier(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    type: Literal["gtin", "mpn", "sku"] = "gtin"
    value: Annotated[str, Field(min_length=1, max_length=128)]
    source_field: Annotated[str, Field(min_length=1, max_length=64)] | None = None

    @model_validator(mode="after")
    def normalize_identifier(self):
        if self.type == "gtin":
            object.__setattr__(self, "value", canonical_gtin(self.value))
        return self


class MatchingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    brand: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    manufacturer: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    model_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    model_number: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    mpn: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    gtin: Annotated[str, Field(min_length=8, max_length=14)] | None = None
    identifiers: list[ProductIdentifier] = Field(default_factory=list, max_length=8)
    image_url: HttpUrl | None = None
    image_urls: list[HttpUrl] = Field(default_factory=list, max_length=8)
    color: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    size: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    options: dict[str, str] = Field(default_factory=dict)
    category: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    seller_id: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    seller_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    exact_match_confirmed: bool = False

    @field_validator("gtin")
    @classmethod
    def valid_gtin(cls, value):
        return canonical_gtin(value) if value is not None else None

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

    @field_validator("options")
    @classmethod
    def bounded_options(cls, value):
        if len(value) > 16:
            raise ValueError("options may contain at most 16 attributes")
        cleaned = {}
        for k, v in value.items():
            key = str(k).strip()
            val = str(v).strip()
            if not key or len(key) > 64 or not val or len(val) > 200:
                raise ValueError("invalid option key or value length")
            cleaned[key] = val
        return cleaned


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


def compute_variant_signature(color: str | None, size: str | None, options: dict[str, str]) -> str | None:
    merged = {k.strip().casefold(): v.strip().casefold() for k, v in (options or {}).items() if k and v}
    if color:
        merged["color"] = color.strip().casefold()
    if size:
        merged["size"] = size.strip().casefold()
    if not merged:
        return None
    return hashlib.sha256(encode(merged).encode()).hexdigest()


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
        (run_id,source,observation_key,schema_version,payload_hash,observed_at,normalized_payload,state,change_kind)
        VALUES(:r,:s,:k,:sv,:h,:t,CAST(:p AS jsonb),'received','pending')
        ON CONFLICT(source,observation_key) DO NOTHING RETURNING extension_id""",
        r=run_id, s=source, k=key, sv=ext.schema_version, h=digest, t=at, p=raw)

    if not row:
        old = await one(c, """SELECT extension_id,offer_id,state,error_code,payload_hash,change_kind,changed_fields
            FROM app.listing_extensions WHERE source=:s AND observation_key=:k""", s=source, k=key)
        if old["payload_hash"] != digest:
            raise HTTPException(409, "EXTENSION_PAYLOAD_CONFLICT")
        return {k: v for k, v in old.items() if k != "payload_hash"}, False

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
        return dict(result), True

    if at < datetime.now(UTC) - timedelta(days=30):
        return await finish("quarantine", reason="OBSERVATION_TOO_OLD", kind="quarantined")

    ident = dict(s=source, l=ext.source_listing_id, v=ext.variant_key)
    await run(c, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))", key=encode(list(ident.values())))

    tombstone = await one(c, """SELECT observed_at FROM app.offer_tombstones
        WHERE source=:s AND source_listing_id=:l AND variant_key=:v""", **ident)
    if tombstone and at <= tombstone["observed_at"]:
        return await finish("recorded", reason="DELETED_STALE_OBSERVATION", kind="stale")

    current = await one(c, """SELECT o.offer_id,o.item_id,o.kind,o.seller_id,o.seller_name,o.detail_observed_at,
        i.brand,i.manufacturer,i.category,i.image_url,i.image_urls,i.content_version
        FROM app.offers o JOIN app.catalog_items i USING(item_id)
        WHERE o.source=:s AND o.source_listing_id=:l AND o.variant_key=:v FOR UPDATE OF o,i""", **ident)
    if not current:
        raise HTTPException(404, "OFFER_NOT_FOUND")

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
                ("manufacturer", mp.manufacturer),
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

            offer_updates = {"detail_observed_at": at, "id": offer_id}
            offer_sets = ["detail_observed_at=:detail_observed_at"]
            for col in ("seller_id", "seller_name"):
                val = getattr(mp, col)
                if val is not None and current[col] != val:
                    before[col] = current[col]
                    after[col] = val
                    offer_updates[col] = val
                    offer_sets.append(f"{col}=:{col}")
            await run(c, f"UPDATE app.offers SET {','.join(offer_sets)} WHERE offer_id=:id", **offer_updates)

            if kind == "product":
                prod = await one(c, "SELECT * FROM app.products WHERE item_id=:id FOR UPDATE", id=item_id)
                gtin_val = mp.gtin or next((i.value for i in mp.identifiers if i.type == "gtin"), None)
                ident_list = [i.model_dump(exclude_none=True) for i in mp.identifiers]
                if gtin_val and not any(i.get("type") == "gtin" and i.get("value") == gtin_val for i in ident_list):
                    ident_list.insert(0, {"type": "gtin", "value": gtin_val})

                merged_options = dict(prod["options"] or {})
                merged_options.update(mp.options or {})
                color_val = mp.color if mp.color is not None else prod["color"]
                size_val = mp.size if mp.size is not None else prod["size"]
                sig = compute_variant_signature(color_val, size_val, merged_options)

                prod_updates = {}
                for col, val in (
                    ("model_name", mp.model_name),
                    ("model_number", mp.model_number),
                    ("mpn", mp.mpn),
                    ("gtin", gtin_val),
                    ("color", mp.color),
                    ("size", mp.size),
                    ("variant_signature", sig),
                ):
                    if val is not None and prod[col] != val:
                        before[col] = prod[col]
                        after[col] = val
                        prod_updates[col] = val
                if ident_list and list(prod["identifiers"] or []) != ident_list:
                    before["identifiers"] = prod["identifiers"]
                    after["identifiers"] = ident_list
                    prod_updates["identifiers"] = encode(ident_list)
                if merged_options and dict(prod["options"] or {}) != merged_options:
                    before["options"] = prod["options"]
                    after["options"] = merged_options
                    prod_updates["options"] = encode(merged_options)

                if prod_updates:
                    sets = []
                    params = {"id": item_id}
                    for col, val in prod_updates.items():
                        if col in ("identifiers", "options"):
                            sets.append(f"{col}=CAST(:{col} AS jsonb)")
                        else:
                            sets.append(f"{col}=:{col}")
                        params[col] = val
                    await run(c, f"UPDATE app.products SET {','.join(sets)} WHERE item_id=:id", **params)

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


@router.post("/internal/v2/crawl-runs/{run_id}/extensions", dependencies=[Depends(collector_auth)])
async def ingest_run_extension(run_id: UUID, ext: ListingExtension, response: Response, req: Request):
    async with req.app.state.engine.begin() as c:
        result, created = await accept_extension(c, run_id, ext)
    response.status_code = 201 if created else 200
    return result


@router.post("/internal/v2/listing-extensions", dependencies=[Depends(collector_auth)])
async def ingest_listing_extension(ext: ListingExtension, response: Response, req: Request):
    async with req.app.state.engine.begin() as c:
        result, created = await accept_extension(c, None, ext)
    response.status_code = 201 if created else 200
    return result


def _compare_options(base_row, cand_row) -> tuple[str, list[str]]:
    conflicts = []
    partial = False
    for key in ("color", "size"):
        a, b = base_row.get(key), cand_row.get(key)
        if a and b:
            if a.strip().casefold() != b.strip().casefold():
                conflicts.append(key)
        elif a or b:
            partial = True
    opts_a = {k.casefold(): str(v).casefold() for k, v in (base_row.get("options") or {}).items()}
    opts_b = {k.casefold(): str(v).casefold() for k, v in (cand_row.get("options") or {}).items()}
    for k in set(opts_a) | set(opts_b):
        if k in opts_a and k in opts_b:
            if opts_a[k] != opts_b[k]:
                conflicts.append(f"options.{k}")
        else:
            partial = True
    if conflicts:
        return "conflict", conflicts
    if partial:
        return "partially_specified", []
    return "complete", []


@router.get("/v2/offers/{offer_id}/matches")
async def offer_matches(
    offer_id: UUID,
    req: Request,
    include_used: bool = Query(True),
    limit: int = Query(20, ge=1, le=100),
):
    async with req.app.state.engine.connect() as c:
        target = await one(c, """SELECT o.offer_id,o.item_id,o.kind,o.source,o.source_listing_id,o.variant_key,
            o.condition,o.price::text AS price,o.currency,o.current_url,o.availability,
            i.name,i.brand,i.manufacturer,i.category,i.image_url,
            p.model_name,p.model_number,p.mpn,p.gtin,p.color,p.size,p.options,p.variant_signature
            FROM app.offers o
            JOIN app.catalog_items i USING(item_id)
            LEFT JOIN app.products p USING(item_id)
            WHERE o.offer_id=:id""", id=offer_id)
        if not target:
            raise HTTPException(404, "OFFER_NOT_FOUND")

        t_gtin = target["gtin"]
        t_brand = (target["brand"] or "").strip().casefold() or None
        t_model_num = (target["model_number"] or "").strip().casefold() or None
        t_mpn = (target["mpn"] or "").strip().casefold() or None
        t_model_name = (target["model_name"] or "").strip().casefold() or None
        t_cat = (target["category"] or "").strip().casefold() or None

        if not any((t_gtin, t_brand, t_model_num, t_mpn, t_model_name)):
            return {
                "offer_id": offer_id,
                "exact_candidates": [],
                "similar_candidates": [],
            }

        match_clauses = []
        exact_rank_clauses = []
        query_params: dict[str, object] = {
            "kind": target["kind"],
            "id": offer_id,
            "include_used": include_used,
            "candidate_cap": max(200, limit * 10),
        }
        if t_gtin:
            match_clauses.append("p.gtin = :gtin")
            exact_rank_clauses.append("p.gtin = :gtin")
            query_params["gtin"] = t_gtin
        if t_brand:
            match_clauses.append("lower(i.brand) = :brand")
            query_params["brand"] = t_brand
        if t_model_num:
            match_clauses.append("lower(p.model_number) = :model_num")
            query_params["model_num"] = t_model_num
            if t_brand:
                exact_rank_clauses.append("(lower(i.brand) = :brand AND lower(p.model_number) = :model_num)")
        if t_mpn:
            match_clauses.append("lower(p.mpn) = :mpn")
            query_params["mpn"] = t_mpn
            if t_brand:
                exact_rank_clauses.append("(lower(i.brand) = :brand AND lower(p.mpn) = :mpn)")

        if not match_clauses:
            return {
                "offer_id": offer_id,
                "exact_candidates": [],
                "similar_candidates": [],
            }

        where_filter = " OR ".join(match_clauses)
        # Rank before the candidate cap: exact identifiers, then brand+model name, then the rest by price.
        # Without this a brand with many cheap listings pushes real similar items past LIMIT.
        rank_cases = []
        if exact_rank_clauses:
            rank_cases.append(f"WHEN ({' OR '.join(exact_rank_clauses)}) THEN 0")
        if t_brand and t_model_name:
            rank_cases.append("WHEN lower(i.brand) = :brand AND lower(p.model_name) = :model_name THEN 1")
            query_params["model_name"] = t_model_name
        order_priority = f"CASE {' '.join(rank_cases)} ELSE 2 END ASC," if rank_cases else ""

        from sqlalchemy import text
        rows = (await c.execute(text(f"""SELECT o.offer_id,o.source,o.source_listing_id,o.variant_key,
            o.condition,o.price::text AS price,o.currency,o.shipping_fee::text AS shipping_fee,
            o.current_url,o.availability,o.price_observed_at,o.last_seen_at,o.last_checked_at,o.seller_name,
            i.name,i.brand,i.manufacturer,i.category,i.image_url,
            p.model_name,p.model_number,p.mpn,p.gtin,p.color,p.size,p.options,p.variant_signature
            FROM app.offers o
            JOIN app.catalog_items i USING(item_id)
            LEFT JOIN app.products p USING(item_id)
            WHERE o.kind=:kind AND o.offer_id<>:id AND o.availability='available'
              AND (:include_used OR o.condition='new')
              AND ({where_filter})
            ORDER BY {order_priority} o.price ASC, o.offer_id ASC
            LIMIT :candidate_cap"""),
            query_params)).mappings().all()

    exact_candidates = []
    similar_candidates = []

    for r in rows:
        c_gtin = r["gtin"]
        c_brand = (r["brand"] or "").strip().casefold()
        c_model_num = (r["model_number"] or "").strip().casefold()
        c_mpn = (r["mpn"] or "").strip().casefold()
        c_model_name = (r["model_name"] or "").strip().casefold()
        c_cat = (r["category"] or "").strip().casefold()

        if t_gtin and c_gtin and t_gtin != c_gtin:
            continue
        if t_brand and c_brand and t_brand != c_brand:
            continue
        if t_model_num and c_model_num and t_model_num != c_model_num:
            continue
        if t_mpn and c_mpn and t_mpn != c_mpn:
            continue

        completeness, conflicts = _compare_options(target, r)
        if conflicts:
            continue

        basis = []
        if t_gtin and c_gtin and t_gtin == c_gtin:
            basis.append("gtin")
        if t_brand and c_brand == t_brand and t_model_num and c_model_num == t_model_num:
            basis.append("brand_model_number")
        if t_brand and c_brand == t_brand and t_mpn and c_mpn == t_mpn:
            basis.append("brand_mpn")

        card = {
            "offer_id": r["offer_id"],
            "source": r["source"],
            "source_listing_id": r["source_listing_id"],
            "variant_key": r["variant_key"],
            "name": r["name"],
            "brand": r["brand"],
            "model_name": r["model_name"],
            "model_number": r["model_number"],
            "mpn": r["mpn"],
            "gtin": r["gtin"],
            "image_url": r["image_url"],
            "seller_name": r["seller_name"],
            "condition": r["condition"],
            "price": r["price"],
            "currency": r["currency"],
            "shipping_fee": r["shipping_fee"],
            "current_url": r["current_url"],
            "availability": r["availability"],
            "last_seen_at": r["last_seen_at"],
            "options": r["options"] or {},
            "color": r["color"],
            "size": r["size"],
            "option_completeness": completeness,
            "exact_match_confirmed": False,
            "requires_review": True,
        }

        if basis:
            if len(exact_candidates) < limit:
                exact_candidates.append(card | {"match_basis": basis})
        elif (t_brand and c_brand == t_brand and t_model_name and c_model_name == t_model_name) or (
            t_brand and c_brand == t_brand and t_cat and c_cat == t_cat
        ):
            sim_basis = ["brand_model_name"] if (t_model_name and c_model_name == t_model_name) else ["brand_category"]
            if len(similar_candidates) < limit:
                similar_candidates.append(card | {"match_basis": sim_basis})

    return {
        "offer_id": offer_id,
        "exact_candidates": exact_candidates,
        "similar_candidates": similar_candidates,
    }
