"""Remove a catalog offer while preserving the crawl observation record."""
from .ingest import one, run


async def purge_offer(conn, offer, *, removed_at=None):
    offer_id = offer['offer_id']
    item_id = offer['item_id']
    await one(conn, 'SELECT item_id FROM app.catalog_items WHERE item_id=:id FOR UPDATE', id=item_id)
    clock = max(offer[key] for key in (
        'price_observed_at', 'status_observed_at', 'url_observed_at',
        'content_observed_at', 'condition_observed_at', 'last_seen_at',
    ))
    if removed_at is not None:
        clock = max(clock, removed_at)
    await run(conn, '''INSERT INTO app.offer_tombstones(source,source_listing_id,variant_key,observed_at)
        VALUES(:s,:l,:v,:at) ON CONFLICT(source,source_listing_id,variant_key) DO UPDATE
        SET observed_at=greatest(app.offer_tombstones.observed_at,excluded.observed_at),deleted_at=now()''',
        s=offer['source'], l=offer['source_listing_id'], v=offer['variant_key'], at=clock)

    for table in ('offer_changes', 'price_history', 'offer_url_history'):
        await run(conn, f'DELETE FROM app.{table} WHERE offer_id=:id', id=offer_id)
    await run(conn, 'UPDATE app.crawl_observations SET offer_id=NULL WHERE offer_id=:id', id=offer_id)
    await run(conn, 'DELETE FROM app.offers WHERE offer_id=:id', id=offer_id)
    # Keep items shared by other sales listings.
    await run(conn, '''DELETE FROM app.catalog_items WHERE item_id=:id
        AND NOT EXISTS(SELECT 1 FROM app.offers WHERE item_id=:id)''', id=item_id)
