"""Read-only administrator aggregates, never client-side demonstration totals."""
import os
from fastapi import APIRouter, Depends, Request
from .access import access, admin_member
from .members import row, execute, wrap

router=APIRouter()

@router.get('/v2/admin/overview')
async def overview(req:Request,uid=Depends(admin_member)):
    async with access(req,uid,{'admin'}) as m:
        members=await row(m,'''SELECT count(*) AS members,
            count(*) FILTER (WHERE s.entitlement_end>now() AND s.billing_mode=:mode AND :enabled) AS subscribers
            FROM app.members m LEFT JOIN app.subscriptions s USING(user_id) WHERE m.deleted_at IS NULL''',
            mode=os.getenv('BILLING_MODE','disabled'),enabled=os.getenv('APP_ENV','development')=='development')
        revenue=await row(m,'''SELECT coalesce(sum(i.amount),0)::text AS mock_revenue_krw
            FROM app.payments p JOIN app.invoices i USING(invoice_id)
            WHERE p.status='succeeded' AND p.provider='mock' AND i.currency='KRW'
            AND p.paid_at>=now()-interval '30 days' ''')
        async with req.app.state.engine.connect() as c:
            catalog=await row(c,"SELECT count(*) AS offers,count(*) FILTER(WHERE availability='available') AS available FROM app.offers")
            days=(await execute(c,'''SELECT (received_at AT TIME ZONE 'Asia/Seoul')::date::text AS date,
                count(*) AS count,count(*) FILTER(WHERE state='applied') AS applied
                FROM app.crawl_observations WHERE received_at>=now()-interval '30 days'
                GROUP BY 1 ORDER BY 1 DESC''')).mappings().all()
    return wrap(dict(members)|dict(revenue)|dict(catalog)|{'crawl_days':[dict(d) for d in days],
        'billing_mode':os.getenv('BILLING_MODE','disabled'),'period':'최근 30일 · KST'},req)
