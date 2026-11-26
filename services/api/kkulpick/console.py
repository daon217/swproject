"""Read-only administrator aggregates, never client-side demonstration totals."""
import os
from datetime import UTC, datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from .access import access, admin_member
from .catalog_deletion import purge_offer
from .ingest import encode
from .members import Strict, row, execute, wrap

router=APIRouter()


class OfferDeletion(Strict):
    offer_ids: list[UUID] = Field(min_length=1, max_length=50)


@router.post('/v2/admin/catalog/offers/delete')
async def delete_catalog_offers(data: OfferDeletion, req: Request, uid=Depends(admin_member)):
    requested = list(dict.fromkeys(data.offer_ids))
    deleted, protected = [], []
    async with access(req, uid, {'admin'}):
        async with req.app.state.engine.begin() as catalog:
            candidates = (await execute(catalog, '''SELECT offer_id,source,source_listing_id,variant_key
                FROM app.offers WHERE offer_id=ANY(CAST(:ids AS uuid[]))
                ORDER BY source,source_listing_id,variant_key''', ids=requested)).mappings().all()
            # Match the ingestion lock and take every identity lock before row locks.
            for candidate in candidates:
                key = encode([candidate[k] for k in ('source', 'source_listing_id', 'variant_key')])
                await execute(catalog, 'SELECT pg_advisory_xact_lock(hashtextextended(:key,0))', key=key)

            removed_at = datetime.now(UTC)
            for candidate in candidates:
                offer_id = candidate['offer_id']
                offer = await row(catalog, 'SELECT * FROM app.offers WHERE offer_id=:id FOR UPDATE', id=offer_id)
                if offer is None:
                    continue
                # Affiliate registration takes the same offer-row lock before checking or creating the link.
                if await row(catalog, 'SELECT offer_id FROM app.affiliate_offers WHERE offer_id=:id', id=offer_id):
                    protected.append(offer_id)
                    continue
                await purge_offer(catalog, offer, removed_at=removed_at)
                await execute(catalog, '''INSERT INTO app.catalog_admin_audit(actor_id,offer_id,action)
                    VALUES(:actor,:offer,'catalog.offer.delete')''', actor=uid, offer=offer_id)
                deleted.append(offer_id)

    handled = set(deleted) | set(protected)
    return wrap({'deleted_offer_ids': deleted, 'protected_offer_ids': protected,
                 'missing_offer_ids': [offer_id for offer_id in requested if offer_id not in handled]}, req)


@router.get('/v2/admin/overview')
async def overview(req:Request,uid=Depends(admin_member)):
    async with access(req,uid,{'admin'}) as m:
        members=await row(m,'''SELECT count(*) AS members,
            count(*) FILTER (WHERE s.entitlement_end>now() AND s.billing_mode=:mode AND :enabled) AS subscribers
            FROM app.members m LEFT JOIN app.subscriptions s USING(user_id) WHERE m.deleted_at IS NULL''',
            mode=os.getenv('BILLING_MODE','disabled'),enabled=os.getenv('APP_ENV','development')=='development')
        daily=await row(m,'''WITH today AS (
                SELECT (now() AT TIME ZONE 'Asia/Seoul')::date AS day
            ), first_subscriptions AS (
                SELECT min(i.period_start) AS started_at
                FROM app.invoices i JOIN app.payments p USING(invoice_id)
                JOIN app.members m ON m.user_id=i.user_id
                WHERE p.status='succeeded' AND m.deleted_at IS NULL
                GROUP BY i.user_id
            )
            SELECT today.day::text AS today_subscribers_date,
                (SELECT count(*) FROM first_subscriptions
                    WHERE started_at >= (today.day::timestamp AT TIME ZONE 'Asia/Seoul')
                    AND started_at < ((today.day+1)::timestamp AT TIME ZONE 'Asia/Seoul')) AS today_subscribers
            FROM today''')
        # Mock payments only (BILLING_MODE=mock). Today = KST calendar day, like today_subscribers.
        revenue=await row(m,'''SELECT coalesce(sum(i.amount),0)::text AS mock_revenue_krw,
            coalesce(sum(i.amount) FILTER (WHERE (p.paid_at AT TIME ZONE 'Asia/Seoul')::date
                = (now() AT TIME ZONE 'Asia/Seoul')::date),0)::text AS today_mock_revenue_krw
            FROM app.payments p JOIN app.invoices i USING(invoice_id)
            WHERE p.status='succeeded' AND p.provider='mock' AND i.currency='KRW'
            AND p.paid_at>=now()-interval '30 days' ''')
        # 통계 매출 차트용 KST 날짜별 모의 결제 합계(최근 1년, #74). 화면이 일·월·연 단위로 묶는다.
        revenue_days=(await execute(m,'''SELECT (p.paid_at AT TIME ZONE 'Asia/Seoul')::date::text AS date,
            sum(i.amount)::text AS mock_revenue_krw
            FROM app.payments p JOIN app.invoices i USING(invoice_id)
            WHERE p.status='succeeded' AND p.provider='mock' AND i.currency='KRW' AND p.paid_at>=now()-interval '366 days'
            GROUP BY 1 ORDER BY 1''')).mappings().all()
        async with req.app.state.engine.connect() as c:
            catalog=await row(c,"SELECT count(*) AS offers,count(*) FILTER(WHERE availability='available') AS available FROM app.offers")
            days=(await execute(c,'''SELECT (received_at AT TIME ZONE 'Asia/Seoul')::date::text AS date,
                count(*) AS count,count(*) FILTER(WHERE state='applied') AS applied
                FROM app.crawl_observations WHERE received_at>=now()-interval '30 days'
                GROUP BY 1 ORDER BY 1 DESC''')).mappings().all()
    return wrap(dict(members)|dict(daily)|dict(revenue)|dict(catalog)|{'crawl_days':[dict(d) for d in days],'revenue_days':[dict(d) for d in revenue_days],
        'billing_mode':os.getenv('BILLING_MODE','disabled'),'period':'최근 30일 · KST'},req)
