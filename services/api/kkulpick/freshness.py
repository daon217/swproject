"""Listing freshness: collectors confirm unchanged listings, clients see how recent the data is.

The collector only sends a full observation when content changes. Without a separate
confirmation, last_seen_at froze at the last change and a listing that was still on sale looked
exactly like one that silently disappeared from the shop. A check-in moves last_seen_at /
last_checked_at forward only when the collector's view still matches what the catalog stores.
Prices, statuses and their field clocks are never touched here; changes go through observations.
"""
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text

from .extensions import collector_auth
from .models import Key, Money

router = APIRouter()
MAX_AGE = timedelta(days=30)


def stale_hours() -> int:
    """Hours after the last successful sighting at which a card is flagged stale (CATALOG_STALE_HOURS)."""
    return max(1, int(os.getenv('CATALOG_STALE_HOURS', '72')))


# Shared card columns: last successful sighting and whether it is older than the stale threshold.
# Every product card also carries condition (new | used | unknown) so clients can label "중고"/"상태 미확인";
# unknown is never presented as new.
CARD_FRESHNESS = ("o.condition, o.last_seen_at AS seen_at, "
                  "(o.last_seen_at < now() - make_interval(hours => CAST(:stale_hours AS int))) AS stale")


class Check(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    source_listing_id: Key
    variant_key: Key
    observed_at: AwareDatetime
    # What the collector saw. The catalog is refreshed only if it still holds the same values,
    # so a check-in can never make an out-of-date row look current.
    price: Money
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    availability: Literal['available', 'out_of_stock', 'ended']

    @field_validator('observed_at')
    @classmethod
    def utc(cls, value):
        return value.astimezone(UTC)


class CheckBatch(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    source: Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')]
    items: list[Check] = Field(min_length=1, max_length=500)


def _ident(item):
    return item.source_listing_id, item.variant_key


@router.post('/internal/v2/listing-checks', dependencies=[Depends(collector_auth)])
async def listing_checks(batch: CheckBatch, req: Request):
    now = datetime.now(UTC)
    # Latest check per identity within the batch; duplicates are harmless but counted once.
    latest = {}
    rejected = []
    for item in batch.items:
        if item.observed_at > now + timedelta(minutes=5) or item.observed_at < now - MAX_AGE:
            rejected.append({'source_listing_id': item.source_listing_id, 'variant_key': item.variant_key,
                             'reason': 'OBSERVED_AT_OUT_OF_RANGE'})
            continue
        key = _ident(item)
        if key not in latest or item.observed_at > latest[key].observed_at:
            latest[key] = item
    items = list(latest.values())
    confirmed, mismatch, unknown = [], [], []
    if items:
        params = dict(s=batch.source,
                      l=[i.source_listing_id for i in items], v=[i.variant_key for i in items],
                      t=[i.observed_at for i in items], p=[str(i.price) for i in items],
                      c=[i.currency for i in items], a=[i.availability for i in items])
        async with req.app.state.engine.begin() as conn:
            rows = (await conn.execute(text('''
                WITH c AS (
                  SELECT * FROM unnest(CAST(:l AS text[]), CAST(:v AS text[]), CAST(:t AS timestamptz[]),
                                       CAST(:p AS numeric[]), CAST(:c AS text[]), CAST(:a AS text[]))
                    AS c(listing, variant, seen, price, currency, availability)
                ), matched AS (
                  UPDATE app.offers o
                     SET last_seen_at = greatest(o.last_seen_at, c.seen),
                         last_checked_at = greatest(o.last_checked_at, c.seen)
                    FROM c
                   WHERE o.source = :s AND o.source_listing_id = c.listing AND o.variant_key = c.variant
                     AND o.price = c.price AND o.currency = c.currency AND o.availability = c.availability
                  RETURNING o.source_listing_id, o.variant_key
                )
                SELECT c.listing, c.variant,
                       EXISTS(SELECT 1 FROM matched m WHERE m.source_listing_id = c.listing AND m.variant_key = c.variant) AS ok,
                       EXISTS(SELECT 1 FROM app.offers o WHERE o.source = :s AND o.source_listing_id = c.listing
                              AND o.variant_key = c.variant) AS known
                  FROM c'''), params)).mappings().all()
        for r in rows:
            ident = {'source_listing_id': r['listing'], 'variant_key': r['variant']}
            if r['ok']:
                confirmed.append(ident)
            elif r['known']:
                mismatch.append(ident)  # catalog differs: resend a full observation
            else:
                unknown.append(ident)   # never observed, or deleted: resend a full observation
    # Plain body like the other collector endpoints (observations/extensions).
    return {'confirmed': len(confirmed), 'mismatch': mismatch, 'unknown': unknown, 'rejected': rejected}
