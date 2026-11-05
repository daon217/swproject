import hashlib
import json
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import text


async def one(connection, sql, **params):
    return (await connection.execute(text(sql), params)).mappings().first()


async def run(connection, sql, **params):
    await connection.execute(text(sql), params)


async def accept(c, rid, obs):
    source, key, at = obs.source, obs.observation_key, obs.observed_at
    data = obs.model_dump(mode="json", exclude_unset=True)
    data.update(schema_version=2, condition=obs.condition, field_presence=sorted(obs.field_presence))
    raw = json.dumps(data, sort_keys=True, separators=(",",":"), ensure_ascii=False)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    await run(c, "INSERT INTO app.crawl_runs(run_id,source) VALUES(:r,:s) ON CONFLICT DO NOTHING", r=rid,s=source)
    if (await one(c, "SELECT source FROM app.crawl_runs WHERE run_id=:r",r=rid))["source"] != source:
        raise HTTPException(409,"RUN_SOURCE_CONFLICT")
    row = await one(c, """INSERT INTO app.crawl_observations
        (run_id,source,observation_key,payload_hash,observed_at,normalized_payload,state)
        VALUES(:r,:s,:k,:h,:t,CAST(:p AS jsonb),'received')
        ON CONFLICT(source,observation_key) DO NOTHING RETURNING observation_id""",
                    r=rid,s=source,k=key,h=digest,t=at,p=raw)
    if not row:
        old = await one(c, """SELECT observation_id,state,error_code,offer_id,payload_hash FROM app.crawl_observations
                              WHERE source=:s AND observation_key=:k""",s=source,k=key)
        if old["payload_hash"] != digest:
            raise HTTPException(409,"PAYLOAD_CONFLICT")
        return {k:v for k,v in old.items() if k!="payload_hash"}, False

    oid = row["observation_id"]
    async def finish(state, offer=None, reason=None):
        r = await one(c, """UPDATE app.crawl_observations SET state=:s,offer_id=:f,error_code=:e
            WHERE observation_id=:id RETURNING observation_id,state,error_code,offer_id""",s=state,f=offer,e=reason,id=oid)
        return dict(r), True

    if not obs.source_listing_id or not obs.variant_key:
        return await finish("quarantine",reason="MISSING_IDENTITY")
    ident = dict(s=source,l=obs.source_listing_id,v=obs.variant_key)
    # Serialize the first two observations of a previously unseen listing as well as updates.
    await run(c, "SELECT pg_advisory_xact_lock(hashtextextended(:key,0))",key=json.dumps(list(ident.values())))
    old = await one(c, """SELECT o.*,i.name,i.description FROM app.offers o JOIN app.catalog_items i USING(item_id)
                           WHERE source=:s AND source_listing_id=:l AND variant_key=:v FOR UPDATE OF o,i""",**ident)
    offer = old["offer_id"] if old else None
    if old and (old["kind"] != obs.selected_domain or old["condition"] != obs.condition):
        return await finish("quarantine",offer,"IDENTITY_CONFLICT")
    if old:
        await run(c,"UPDATE app.offers SET last_checked_at=greatest(last_checked_at,:t) WHERE offer_id=:f",t=at,f=offer)
    if obs.result not in ("success","not_found"):
        return await finish("recorded",offer,obs.result)
    if obs.result=="not_found" and not old:
        return await finish("recorded",reason="NOT_FOUND")
    p = set(obs.field_presence)
    if not old and not {"price","currency","availability","url","name"} <= p:
        return await finish("quarantine",reason="INCOMPLETE_FIRST_OBSERVATION")
    fields = {}
    if "price" in p:
        fields["price_observed_at"] = dict(price=obs.price,currency=obs.currency,shipping_fee=obs.shipping_fee)
    if "availability" in p or obs.result=="not_found":
        fields["status_observed_at"] = dict(availability="suspect" if obs.result=="not_found" else obs.availability)
    if "url" in p:
        fields["url_observed_at"] = dict(current_url=str(obs.url))
    # Treat name and description as a public text snapshot only when name is supplied.
    if "name" in p or "description" in p:
        fields["content_observed_at"] = {k:getattr(obs,k) for k in p & {"name","description"}}
    if old and any(old[clock]==at and any(old[k]!=v for k,v in vals.items()) for clock,vals in fields.items()):
        return await finish("quarantine",offer,"SAME_TIME_CONFLICT")

    price_change = url_change = not old
    if not old:
        item = (await one(c, """INSERT INTO app.catalog_items(kind,name,description)
             VALUES(:k,:n,:d) RETURNING item_id""",k=obs.selected_domain,n=obs.name,d=obs.description))["item_id"]
        sub = {"product":"products","food":"foods"}[obs.selected_domain]
        await run(c,f"INSERT INTO app.{sub}(item_id) VALUES(:id)",id=item)
        offer = (await one(c, """INSERT INTO app.offers(item_id,kind,source,source_listing_id,variant_key,condition,
            price,currency,shipping_fee,current_url,availability,price_observed_at,status_observed_at,url_observed_at,
            content_observed_at,last_seen_at,last_checked_at,fresh_until)
            VALUES(:i,:k,:s,:l,:v,:c,:price,:cc,:ship,:u,:a,:t,:t,:t,:t,:t,:t,:fresh) RETURNING offer_id""",
            **ident,i=item,k=obs.selected_domain,c=obs.condition,price=obs.price,cc=obs.currency,ship=obs.shipping_fee,
            u=str(obs.url),a=obs.availability,t=at,fresh=at+timedelta(hours=24)))["offer_id"]
    else:
        applied = False
        for clock,vals in fields.items():
            if at <= old[clock]:
                continue
            applied = True
            changed = any(old[k]!=v for k,v in vals.items())
            if clock=="content_observed_at":
                if changed:
                    sets = ", ".join(f"{k}=:{k}" for k in vals)
                    await run(c,f"UPDATE app.catalog_items SET {sets},content_version=content_version+1 WHERE item_id=:i",**vals,i=old["item_id"])
                await run(c,"UPDATE app.offers SET content_observed_at=:t WHERE offer_id=:id",t=at,id=offer)
            else:
                extra=""
                if clock=="url_observed_at" and changed:
                    url_change=True
                    extra=",url_version=url_version+1"
                if clock=="price_observed_at" and changed:
                    price_change=True
                sets=", ".join(f"{k}=:{k}" for k in vals)
                await run(c,f"UPDATE app.offers SET {sets},{clock}=:t{extra} WHERE offer_id=:id",**vals,t=at,id=offer)
        if obs.result=="success":
            await run(c,"UPDATE app.offers SET last_seen_at=greatest(last_seen_at,:t) WHERE offer_id=:id",t=at,id=offer)
        if not applied:
            return await finish("recorded",offer,"NO_NEWER_FIELDS")
        await run(c,"""UPDATE app.offers SET fresh_until=least(price_observed_at,status_observed_at,url_observed_at)
                         + interval '24 hours' WHERE offer_id=:id""",id=offer)
    if price_change:
        await run(c,"""INSERT INTO app.price_history(offer_id,observation_id,price,currency,shipping_fee,observed_at)
                       VALUES(:f,:o,:p,:c,:ship,:t)""",f=offer,o=oid,p=obs.price,c=obs.currency,ship=obs.shipping_fee,t=at)
    if url_change:
        await run(c,"UPDATE app.offer_url_history SET valid_to=:t WHERE offer_id=:f AND valid_to IS NULL",t=at,f=offer)
        await run(c,"INSERT INTO app.offer_url_history(offer_id,url,valid_from) VALUES(:f,:u,:t)",f=offer,u=str(obs.url),t=at)
    return await finish("applied",offer)
