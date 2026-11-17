"""Administrator read APIs and durable, resumable account withdrawal."""
import secrets
from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field, SecretStr
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from .access import access
from .members import Strict, member, row, execute, fail, wrap, check_password

router=APIRouter()

class Withdrawal(Strict):
    current_password: SecretStr = Field(min_length=1,max_length=128)


@router.get('/v2/admin/me')
async def admin_me(req:Request,uid=Depends(member)):
    async with access(req,uid,{'admin','support'}) as c:
        r=await row(c,'SELECT role FROM app.admin_accounts WHERE user_id=:u',u=uid)
        return wrap({'user_id':uid,'role':r['role']},req)


@router.get('/v2/admin/members')
async def member_list(req:Request,limit:int=Query(20,ge=1,le=100),uid=Depends(member)):
    async with access(req,uid,{'admin'}) as c:
        rows=(await execute(c,'''SELECT user_id,login_id,created_at FROM app.members
            WHERE deleted_at IS NULL ORDER BY created_at DESC,user_id DESC LIMIT :n''',n=limit)).mappings().all()
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
            gender=NULL,birth_date=NULL,include_used=false,consent_version='withdrawn',profile_version=profile_version+1
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
