"""Administrator read APIs and durable, resumable account withdrawal."""
import secrets
import os
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field, SecretStr
from starlette.concurrency import run_in_threadpool
from .access import access, admin_member
from .members import Strict, member, row, execute, fail, wrap, check_password

router=APIRouter()

class Withdrawal(Strict):
    current_password: SecretStr = Field(min_length=1,max_length=128)


@router.get('/v2/admin/me')
async def admin_me(req:Request,uid=Depends(admin_member)):
    async with access(req,uid,{'admin','support'}):
        return wrap({'user_id':uid,'role':req.state.admin_role},req)


# One definition of the admin-visible member summary, shared by the member list and the support
# conversation list, so "subscribed" and the age band are computed the same way everywhere.
MEMBER_SUMMARY = '''SELECT m.user_id,m.login_id,m.created_at,m.gender,
    (extract(year FROM age(current_date,m.birth_date))::int/10)*10 AS age_decade,
    coalesce(s.entitlement_end>now() AND s.billing_mode=:mode AND :enabled,false) AS subscribed,
    (SELECT min(i.period_start) FROM app.invoices i JOIN app.payments p USING(invoice_id)
        WHERE i.user_id=m.user_id AND p.status='succeeded') AS subscription_started_at
    FROM app.members m LEFT JOIN app.subscriptions s USING(user_id)
    WHERE m.deleted_at IS NULL'''


def billing_params():
    return {'mode': os.getenv('BILLING_MODE','disabled'), 'enabled': os.getenv('APP_ENV','development')=='development'}


async def member_summaries(c, user_ids):
    """Summaries for the given members (deleted members are absent)."""
    if not user_ids:
        return {}
    rows=(await execute(c, MEMBER_SUMMARY+' AND m.user_id=ANY(CAST(:ids AS uuid[]))',
                        ids=[str(u) for u in user_ids], **billing_params())).mappings().all()
    return {r['user_id']: dict(r) for r in rows}


@router.get('/v2/admin/members')
async def member_list(req:Request,limit:int=Query(20,ge=1,le=100),uid=Depends(admin_member)):
    async with access(req,uid,{'admin'}) as c:
        rows=(await execute(c,MEMBER_SUMMARY+' ORDER BY m.created_at DESC,m.user_id DESC LIMIT :n',
                            n=limit,**billing_params())).mappings().all()
        return wrap([dict(r) for r in rows],req)


@router.post('/v2/me/withdrawal',status_code=202)
async def withdraw(data:Withdrawal,req:Request,uid=Depends(member)):
    async with req.app.state.member_engine.begin() as c:
        user=await row(c,'SELECT password_hash,deleted_at FROM app.members WHERE user_id=:u FOR UPDATE',u=uid)
        if not user or user['deleted_at'] is not None:
            fail(401,'AUTH_REQUIRED')
        if not await run_in_threadpool(check_password,data.current_password.get_secret_value(),user['password_hash']):
            fail(422,'WRONG_PASSWORD')
        pending=await row(c,'''SELECT p.payment_id FROM app.payments p JOIN app.invoices i USING(invoice_id)
            WHERE i.user_id=:u AND p.status='pending' LIMIT 1''',u=uid)
        if pending:
            fail(409,'PAYMENT_PENDING')
        await execute(c,'''UPDATE app.members SET deleted_at=now(),login_id=:l,password_hash='withdrawn',
            gender=NULL,birth_date=NULL,include_used=false,include_overseas=true,height_cm=NULL,weight_kg=NULL,foot_mm=NULL,consent_version='withdrawn',profile_version=profile_version+1
            WHERE user_id=:u''',u=uid,l='x'+secrets.token_hex(8)[:15])
        await execute(c,'DELETE FROM app.member_preferences WHERE user_id=:u',u=uid)
        await execute(c,'DELETE FROM app.sessions WHERE user_id=:u',u=uid)
        await execute(c,'''UPDATE app.subscriptions SET cancel_at_period_end=true,
            entitlement_end=least(entitlement_end,now()),updated_at=now() WHERE user_id=:u''',u=uid)
        # Runtime cannot grant or revoke admin roles. deleted_at is checked on every access.
        r=await row(c,'INSERT INTO app.account_deletions(user_id) VALUES(:u) RETURNING request_id,state',u=uid)
    return wrap(dict(r),req)


async def process_deletions(member_engine,catalog_engine,support_engine,batch=100):
    completed=0
    for _ in range(batch):
        async with member_engine.begin() as c:
            r=await row(c,'''SELECT * FROM app.account_deletions WHERE state='pending'
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1''')
            if not r:break
            # These commits are deliberately idempotent: a failure leaves the outbox
            # pending and the next run repeats already completed deletions safely.
            async with support_engine.begin() as support:
                await execute(support,'DELETE FROM app.conversations WHERE owner_id=:u',u=r['user_id'])
            from .images import remove_image
            async with catalog_engine.begin() as catalog:
                jobs=(await execute(catalog,'DELETE FROM app.analyses WHERE owner_id=:u RETURNING image_id',u=r['user_id'])).mappings().all()
                for job in jobs:remove_image(job['image_id'])
            await execute(c,"UPDATE app.account_deletions SET state='completed',completed_at=now() WHERE request_id=:r",r=r['request_id'])
            completed+=1
    return completed
