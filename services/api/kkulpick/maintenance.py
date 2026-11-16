"""Bounded catalog retention. Default is dry-run; --apply writes, --loop repeats.

One batch per interval, PostgreSQL autovacuum reclaims space for reuse. This does
not VACUUM FULL or erase billing records. Retention values are temporary policy.
"""
import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from .db import url
from .ingest import encode, one, run


@dataclass(frozen=True)
class Policy:
    unavailable_hours: int = 24
    payload_days: int = 7
    history_days: int = 90
    tombstone_days: int = 90
    batch: int = 500

    def __post_init__(self):
        if not (1 <= self.unavailable_hours and 1 <= self.payload_days <= self.history_days
                and self.history_days >= 30 and self.tombstone_days >= 30 and 1 <= self.batch <= 10000):
            raise ValueError('invalid retention settings; deletion markers must outlive accepted observations')


async def cleanup(c, policy=Policy(), apply=False, now=None):
    now = now or datetime.now(UTC)
    params = dict(unavailable=now-timedelta(hours=policy.unavailable_hours),
                  payload=now-timedelta(days=policy.payload_days), history=now-timedelta(days=policy.history_days),
                  tombstone=now-timedelta(days=policy.tombstone_days), n=policy.batch)
    if not (await one(c, "SELECT pg_try_advisory_xact_lock(hashtextextended('catalog-maintenance',0)) AS ok"))['ok']:
        return {'skipped': 'already_running'}
    counts = {}
    for label, sql in {
        'offers': "SELECT offer_id FROM app.offers WHERE availability IN ('out_of_stock','ended') AND status_observed_at<:unavailable ORDER BY status_observed_at,offer_id LIMIT :n",
        'payloads': "SELECT observation_id FROM app.crawl_observations WHERE received_at<:payload AND normalized_payload<>'{}'::jsonb ORDER BY received_at LIMIT :n",
        'price_history': 'SELECT price_history_id FROM app.price_history WHERE observed_at<:history LIMIT :n',
        'offer_changes': 'SELECT change_id FROM app.offer_changes WHERE observed_at<:history LIMIT :n',
        'closed_urls': 'SELECT url_history_id FROM app.offer_url_history WHERE valid_to<:history LIMIT :n',
        'tombstones': 'SELECT source FROM app.offer_tombstones WHERE deleted_at<:tombstone LIMIT :n',
    }.items():
        counts[label] = len((await c.execute(text(sql), params)).all())
    counts['apply'] = apply
    if not apply:
        return counts
    candidates = (await c.execute(text("""SELECT offer_id,source,source_listing_id,variant_key FROM app.offers
        WHERE availability IN ('out_of_stock','ended') AND status_observed_at<:unavailable
        ORDER BY status_observed_at,offer_id LIMIT :n"""), params)).mappings().all()
    deleted = 0
    for candidate in candidates:
        key = encode([candidate[k] for k in ('source', 'source_listing_id', 'variant_key')])
        if not (await one(c, 'SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0)) AS ok', key=key))['ok']:
            continue
        offer = await one(c, """SELECT * FROM app.offers WHERE offer_id=:id
            AND availability IN ('out_of_stock','ended') AND status_observed_at<:cutoff FOR UPDATE""",
            id=candidate['offer_id'], cutoff=params['unavailable'])
        if not offer:
            continue
        await one(c, 'SELECT item_id FROM app.catalog_items WHERE item_id=:id FOR UPDATE', id=offer['item_id'])
        clock = max(offer[k] for k in ('price_observed_at','status_observed_at','url_observed_at',
                    'content_observed_at','condition_observed_at','last_seen_at'))
        await run(c, """INSERT INTO app.offer_tombstones(source,source_listing_id,variant_key,observed_at)
            VALUES(:s,:l,:v,:at) ON CONFLICT(source,source_listing_id,variant_key) DO UPDATE
            SET observed_at=greatest(app.offer_tombstones.observed_at,excluded.observed_at),deleted_at=now()""",
            s=offer['source'], l=offer['source_listing_id'], v=offer['variant_key'], at=clock)
        for table in ('offer_changes','price_history','offer_url_history'):
            await run(c, f'DELETE FROM app.{table} WHERE offer_id=:id', id=offer['offer_id'])
        await run(c, 'UPDATE app.crawl_observations SET offer_id=NULL WHERE offer_id=:id', id=offer['offer_id'])
        await run(c, 'DELETE FROM app.offers WHERE offer_id=:id', id=offer['offer_id'])
        # Subtype and embedding rows cascade, but a shared item is retained.
        await run(c, 'DELETE FROM app.catalog_items WHERE item_id=:id AND NOT EXISTS(SELECT 1 FROM app.offers WHERE item_id=:id)', id=offer['item_id'])
        deleted += 1
    counts['offers_deleted'] = deleted
    statements = [
        "UPDATE app.crawl_observations SET normalized_payload='{}'::jsonb WHERE observation_id IN (SELECT observation_id FROM app.crawl_observations WHERE received_at<:payload AND normalized_payload<>'{}'::jsonb ORDER BY received_at LIMIT :n)",
        'DELETE FROM app.offer_changes WHERE change_id IN (SELECT change_id FROM app.offer_changes WHERE observed_at<:history LIMIT :n)',
        'DELETE FROM app.price_history WHERE price_history_id IN (SELECT price_history_id FROM app.price_history WHERE observed_at<:history LIMIT :n)',
        'DELETE FROM app.offer_url_history WHERE url_history_id IN (SELECT url_history_id FROM app.offer_url_history WHERE valid_to<:history LIMIT :n)',
        '''DELETE FROM app.crawl_observations WHERE observation_id IN (SELECT observation_id FROM app.crawl_observations o
           WHERE received_at<:history AND NOT EXISTS(SELECT 1 FROM app.price_history p WHERE p.observation_id=o.observation_id)
           AND NOT EXISTS(SELECT 1 FROM app.offer_changes h WHERE h.observation_id=o.observation_id) LIMIT :n)''',
        'DELETE FROM app.crawl_runs WHERE run_id IN (SELECT run_id FROM app.crawl_runs r WHERE started_at<:history AND NOT EXISTS(SELECT 1 FROM app.crawl_observations o WHERE o.run_id=r.run_id) LIMIT :n)',
        'DELETE FROM app.offer_tombstones WHERE (source,source_listing_id,variant_key) IN (SELECT source,source_listing_id,variant_key FROM app.offer_tombstones WHERE deleted_at<:tombstone LIMIT :n)',
    ]
    for statement in statements:
        await c.execute(text(statement), params)
    return counts


async def perform(apply, policy):
    catalog = create_async_engine(url('app'), hide_parameters=True, pool_size=1, max_overflow=0)
    member = create_async_engine(url('app','member'), hide_parameters=True, pool_size=1, max_overflow=0)
    try:
        async with catalog.begin() as c:
            result = await cleanup(c, policy, apply=apply)
        if apply:
            async with member.begin() as c:
                await run(c, 'DELETE FROM app.sessions WHERE token_hash IN (SELECT token_hash FROM app.sessions WHERE expires_at<now() LIMIT :n)', n=policy.batch)
                await run(c, "DELETE FROM app.auth_attempts WHERE bucket IN (SELECT bucket FROM app.auth_attempts WHERE window_start<now()-interval '1 day' LIMIT :n)", n=policy.batch)
        return result
    finally:
        await catalog.dispose()
        await member.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--loop', action='store_true')
    parser.add_argument('--batch', type=int, default=int(os.getenv('RETENTION_BATCH','500')))
    parser.add_argument('--interval', type=int, default=3600)
    args = parser.parse_args()
    if args.interval < 60:
        parser.error('interval must be at least 60 seconds')
    policy = Policy(batch=args.batch)
    async def worker():
        while True:
            try:
                print(json.dumps(await perform(args.apply, policy)), flush=True)
            except Exception as exc:
                logging.error('maintenance_failed type=%s; next scheduled run will retry', type(exc).__name__)
                if not args.loop:
                    raise SystemExit(1)
            if not args.loop:
                return
            await asyncio.sleep(args.interval)
    asyncio.run(worker())

if __name__ == '__main__':
    main()
