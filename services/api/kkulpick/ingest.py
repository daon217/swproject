"""Merge trusted observations by stable source identity and observation time."""
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text


async def one(connection, sql, **params):
    return (await connection.execute(text(sql), params)).mappings().first()


async def run(connection, sql, **params):
    await connection.execute(text(sql), params)


def encode(data):
    return json.dumps(data, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


async def accept(c, rid, obs):
    source, key, at = obs.source, obs.observation_key, obs.observed_at
    data = obs.model_dump(mode="json", exclude_unset=True)
    data.update(schema_version=2, field_presence=sorted(obs.field_presence))
    raw = encode(data)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    await run(c, "INSERT INTO app.crawl_runs(run_id,source) VALUES(:r,:s) ON CONFLICT DO NOTHING", r=rid, s=source)
    if (await one(c, "SELECT source FROM app.crawl_runs WHERE run_id=:r", r=rid))["source"] != source:
        raise HTTPException(409, "RUN_SOURCE_CONFLICT")
    row = await one(c, """INSERT INTO app.crawl_observations
        (run_id,source,observation_key,payload_hash,observed_at,normalized_payload,state)
        VALUES(:r,:s,:k,:h,:t,CAST(:p AS jsonb),'received')
        ON CONFLICT(source,observation_key) DO NOTHING RETURNING observation_id""",
        r=rid, s=source, k=key, h=digest, t=at, p=raw)
    if not row:
        old = await one(c, """SELECT observation_id,state,error_code,offer_id,payload_hash,normalized_payload,
            change_kind,changed_fields FROM app.crawl_observations WHERE source=:s AND observation_key=:k""",
            s=source, k=key)
        # v1 always materialized the default condition. Accept its historical exact replay too.
        legacy = dict(data)
        legacy.setdefault("condition", obs.condition)
        if old["payload_hash"] != digest and old["normalized_payload"] != legacy:
            raise HTTPException(409, "PAYLOAD_CONFLICT")
        return {k: v for k, v in old.items() if k not in ("payload_hash", "normalized_payload")}, False

    oid = row["observation_id"]

    async def finish(state, offer=None, reason=None, kind=None, changed=()):
        result = await one(c, """UPDATE app.crawl_observations SET state=:s,offer_id=:f,error_code=:e,
            change_kind=:k,changed_fields=CAST(:fields AS jsonb) WHERE observation_id=:id
            RETURNING observation_id,state,error_code,offer_id,change_kind,changed_fields""",
            s=state, f=offer, e=reason, k=kind, fields=encode(sorted(changed)), id=oid)
        return dict(result), True

    if not obs.source_listing_id or not obs.variant_key:
        return await finish("quarantine", reason="MISSING_IDENTITY", kind="quarantined")
    if at < datetime.now(UTC) - timedelta(days=30):
        return await finish("quarantine", reason="OBSERVATION_TOO_OLD", kind="quarantined")
    ident = dict(s=source, l=obs.source_listing_id, v=obs.variant_key)
    # All inserts and updates of the same identity serialize, including concurrent first observations.
    await run(c, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))", key=encode(list(ident.values())))
    tombstone = await one(c, """SELECT observed_at FROM app.offer_tombstones
        WHERE source=:s AND source_listing_id=:l AND variant_key=:v""", **ident)
    if tombstone and at <= tombstone['observed_at']:
        return await finish("recorded", reason="DELETED_STALE_OBSERVATION", kind="stale")
    old = await one(c, """SELECT o.*,i.name,i.description FROM app.offers o
        JOIN app.catalog_items i USING(item_id)
        WHERE source=:s AND source_listing_id=:l AND variant_key=:v FOR UPDATE OF o,i""", **ident)
    offer = old["offer_id"] if old else None
    if old and old["kind"] != obs.selected_domain:
        return await finish("quarantine", offer, "IDENTITY_CONFLICT", "quarantined")
    if old:
        await run(c, "UPDATE app.offers SET last_checked_at=greatest(last_checked_at,:t) WHERE offer_id=:f", t=at, f=offer)
    if obs.result not in ("success", "not_found"):
        return await finish("recorded", offer, obs.result, "failed")
    if obs.result == "not_found" and not old:
        return await finish("recorded", reason="NOT_FOUND", kind="not_found")
    present = set(obs.field_presence)
    ratio = Decimal(os.getenv('CATALOG_PRICE_RATIO', '10'))
    if old and obs.result == 'success' and 'price' in present and obs.currency == old['currency'] and at > old['price_observed_at'] and ratio > 1:
        previous = old['price']
        if previous > 0 and (obs.price > previous * ratio or obs.price < previous / ratio):
            return await finish('quarantine', offer, 'PRICE_ANOMALY', 'quarantined')
    if not old and not {"price", "currency", "availability", "url", "name"} <= present:
        return await finish("quarantine", reason="INCOMPLETE_FIRST_OBSERVATION", kind="quarantined")

    # Each optional field has its own clock: an omitted description must not prevent a later backfill.
    fields = {}
    if "price" in present:
        fields["price_observed_at"] = dict(price=obs.price, currency=obs.currency)
        if "shipping_fee" in present:
            fields["shipping_observed_at"] = dict(shipping_fee=obs.shipping_fee)
        elif old and old["currency"] != obs.currency:
            # Shipping is expressed in the offer currency; never carry its amount across currencies.
            fields["shipping_observed_at"] = dict(shipping_fee=None)
        if old and at < old["price_observed_at"] and old["currency"] != obs.currency:
            fields.pop("shipping_observed_at", None)
    if "availability" in present or obs.result == "not_found":
        fields["status_observed_at"] = dict(availability="suspect" if obs.result == "not_found" else obs.availability)
    if "url" in present:
        fields["url_observed_at"] = dict(current_url=str(obs.url))
    if "name" in present:
        fields["content_observed_at"] = dict(name=obs.name)
    if "description" in present:
        fields["description_observed_at"] = dict(description=obs.description)
    if obs.result == "success" and "condition" in obs.model_fields_set:
        fields["condition_observed_at"] = dict(condition=obs.condition)
    if old and any(old[clock] == at and any(old[k] != v for k, v in values.items())
                   for clock, values in fields.items()):
        return await finish("quarantine", offer, "SAME_TIME_CONFLICT", "quarantined")

    before, after = {}, {}
    price_change = url_change = not old
    if not old:
        item = (await one(c, """INSERT INTO app.catalog_items(kind,name,description)
            VALUES(:k,:n,:d) RETURNING item_id""", k=obs.selected_domain, n=obs.name, d=obs.description))["item_id"]
        subtype = {"product": "products", "food": "foods"}[obs.selected_domain]
        await run(c, f"INSERT INTO app.{subtype}(item_id) VALUES(:id)", id=item)
        offer = (await one(c, """INSERT INTO app.offers(item_id,kind,source,source_listing_id,variant_key,condition,
            price,currency,shipping_fee,current_url,availability,price_observed_at,status_observed_at,url_observed_at,
            content_observed_at,last_seen_at,last_checked_at,condition_observed_at,description_observed_at,
            shipping_observed_at,last_changed_at)
            VALUES(:i,:k,:s,:l,:v,:c,:price,:cc,:ship,:u,:a,:t,:t,:t,:t,:t,:t,:t,:dt,:st,:t) RETURNING offer_id""",
            **ident, i=item, k=obs.selected_domain, c=obs.condition, price=obs.price, cc=obs.currency,
            ship=obs.shipping_fee, u=str(obs.url), a=obs.availability, t=at,
            dt=at if "description" in present else None, st=at if "shipping_fee" in present else None))["offer_id"]
        after = dict(name=obs.name, price=obs.price, currency=obs.currency, current_url=str(obs.url),
                     availability=obs.availability, condition=obs.condition)
        for k in ("description", "shipping_fee"):
            if k in present:
                after[k] = getattr(obs, k)
        change_kind = "created"
    else:
        advanced = False
        content_changes = {}
        for clock, values in fields.items():
            if old[clock] is not None and at <= old[clock]:
                continue
            advanced = True
            changes = {k: v for k, v in values.items() if old[k] != v}
            before.update({k: old[k] for k in changes})
            after.update(changes)
            if clock in ("content_observed_at", "description_observed_at"):
                content_changes.update(changes)
                await run(c, f"UPDATE app.offers SET {clock}=:t WHERE offer_id=:id", t=at, id=offer)
            else:
                assignments = ",".join(f"{k}=:{k}" for k in values)
                extra = ",url_version=url_version+1" if clock == "url_observed_at" and changes else ""
                await run(c, f"UPDATE app.offers SET {assignments},{clock}=:t{extra} WHERE offer_id=:id",
                          **values, t=at, id=offer)
            price_change |= bool(changes.keys() & {"price", "currency", "shipping_fee"})
            url_change |= "current_url" in changes
        if content_changes:
            assignments = ",".join(f"{k}=:{k}" for k in content_changes)
            await run(c, f"UPDATE app.catalog_items SET {assignments},content_version=content_version+1 WHERE item_id=:i",
                      **content_changes, i=old["item_id"])
        if obs.result == "success":
            await run(c, "UPDATE app.offers SET last_seen_at=greatest(last_seen_at,:t) WHERE offer_id=:id", t=at, id=offer)
        if after:
            await run(c, "UPDATE app.offers SET last_changed_at=greatest(last_changed_at,:t) WHERE offer_id=:id", t=at, id=offer)
        change_kind = "updated" if after else "unchanged" if advanced else "stale"

    if after:
        await run(c, """INSERT INTO app.offer_changes(offer_id,observation_id,observed_at,before_data,after_data)
            VALUES(:f,:o,:t,CAST(:b AS jsonb),CAST(:a AS jsonb))""", f=offer, o=oid, t=at, b=encode(before), a=encode(after))
    if price_change:
        # Read the merged values, not a partial/stale incoming price snapshot.
        await run(c, """INSERT INTO app.price_history(offer_id,observation_id,price,currency,shipping_fee,observed_at)
            SELECT offer_id,:o,price,currency,shipping_fee,:t FROM app.offers WHERE offer_id=:f""", f=offer, o=oid, t=at)
    if url_change:
        await run(c, "UPDATE app.offer_url_history SET valid_to=:t WHERE offer_id=:f AND valid_to IS NULL", t=at, f=offer)
        await run(c, "INSERT INTO app.offer_url_history(offer_id,url,valid_from) VALUES(:f,:u,:t)", f=offer, u=str(obs.url), t=at)
    return await finish("recorded" if change_kind == "stale" else "applied", offer,
                        "NO_NEWER_FIELDS" if change_kind == "stale" else None, change_kind, after)
