"""Provisional frontend-compatible member and subscription API.

Mock billing is explicitly opt-in, never contacts a payment provider, and never
accepts card numbers, bank credentials or payment success claims from a client.
"""
import hashlib
import hmac
import json
import os
import secrets
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

router = APIRouter()
bearer = HTTPBearer(auto_error=False)
LoginId = Annotated[str, Field(pattern=r'^[A-Za-z0-9]{4,16}$')]
Preference = Annotated[str, Field(min_length=1, max_length=100)]
Password = Annotated[SecretStr, Field(min_length=8, max_length=128)]


def fail(status, code):
    raise HTTPException(status, code)


def wrap(data, request):
    return {'data': data, 'request_id': request.state.request_id}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class IngredientFilter(Strict):
    avoid: list[Preference] = Field(default_factory=list, max_length=50)
    prefer: list[Preference] = Field(default_factory=list, max_length=50)


class Profile(Strict):
    gender: Literal['male', 'female', 'prefer_not_to_say'] | None = None
    birth_date: date | None = None
    allergies: list[Preference] = Field(default_factory=list, max_length=50)

    @field_validator('birth_date')
    @classmethod
    def past_birth(cls, value):
        if value and (value > datetime.now(ZoneInfo('Asia/Seoul')).date() or value.year < 1900):
            raise ValueError('invalid birth date')
        return value


class Signup(Profile):
    login_id: LoginId
    password: Password
    password_confirmation: Password
    consent_version: Annotated[str, Field(min_length=1, max_length=100)]
    consent_accepted: Literal[True]

    @model_validator(mode='after')
    def match(self):
        if self.password != self.password_confirmation:
            raise ValueError('password mismatch')
        return self


class Login(Strict):
    login_id: LoginId
    password: Annotated[SecretStr, Field(min_length=1, max_length=128)]


class ProfilePatch(Profile):
    expected_version: int = Field(ge=1)
    include_used: bool = False
    ingredient_filter: IngredientFilter | None = None


class PasswordChange(Strict):
    current_password: Annotated[SecretStr, Field(min_length=1, max_length=128)]
    new_password: Password
    new_password_confirmation: Password

    @model_validator(mode='after')
    def match(self):
        if self.new_password != self.new_password_confirmation:
            raise ValueError('password mismatch')
        return self


class SubscriptionRequest(Strict):
    plan_id: Annotated[str, Field(min_length=1, max_length=100)]
    payment_method: Literal['card', 'bank_transfer', 'naverpay', 'kakaopay', 'tosspay']


class Resolution(Strict):
    outcome: Literal['succeeded', 'failed']


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
    return 'scrypt$' + salt + '$' + key.hex()


def check_password(password, encoded):
    try:
        algorithm, salt, _ = encoded.split('$')
        return algorithm == 'scrypt' and hmac.compare_digest(hash_password(password, salt), encoded)
    except (ValueError, TypeError):
        return False


async def row(c, sql, **values):
    return (await c.execute(text(sql), values)).mappings().first()


async def execute(c, sql, **values):
    return await c.execute(text(sql), values)


async def throttle(req, operation):
    # Database-backed fixed-window limits shared across API workers. No raw IP saved.
    bucket = hashlib.sha256((operation + ':' + (req.client.host if req.client else 'unknown')).encode()).hexdigest()
    async with req.app.state.member_engine.begin() as c:
        r = await row(c, """INSERT INTO app.auth_attempts(bucket,attempts) VALUES(:b,1)
            ON CONFLICT(bucket) DO UPDATE SET
            attempts=CASE WHEN app.auth_attempts.window_start<now()-interval '1 minute' THEN 1 ELSE app.auth_attempts.attempts+1 END,
            window_start=CASE WHEN app.auth_attempts.window_start<now()-interval '1 minute' THEN now() ELSE app.auth_attempts.window_start END
            RETURNING attempts""", b=bucket)
    if r['attempts'] > int(os.getenv('AUTH_REQUESTS_PER_MINUTE', '30')):
        raise HTTPException(429, 'AUTH_RATE_LIMITED', headers={'Retry-After': '60'})


async def member(req: Request, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not auth or len(auth.credentials) > 256:
        fail(401, 'AUTH_REQUIRED')
    token_hash = hashlib.sha256(auth.credentials.encode()).hexdigest()
    async with req.app.state.member_engine.connect() as c:
        r = await row(c, 'SELECT user_id FROM app.sessions WHERE token_hash=:t AND expires_at>now()', t=token_hash)
    if not r:
        fail(401, 'AUTH_REQUIRED')
    req.state.session_hash = token_hash
    return r['user_id']


async def subscription_status(c, uid):
    r = await row(c, """SELECT subscription_id, entitlement_end, cancel_at_period_end,
        coalesce(entitlement_end>now() AND billing_mode=:mode AND :enabled,false) AS active,billing_mode
        FROM app.subscriptions WHERE user_id=:u""", u=uid,
        mode=os.getenv('BILLING_MODE','disabled'), enabled=os.getenv('APP_ENV','development')=='development')
    return dict(r) if r else {'active': False, 'entitlement_end': None, 'cancel_at_period_end': False}


async def me(c, uid):
    r = await row(c, 'SELECT * FROM app.members WHERE user_id=:u', u=uid)
    prefs = (await execute(c, 'SELECT kind,value FROM app.member_preferences WHERE user_id=:u ORDER BY value', u=uid)).mappings().all()
    values = {k: [p['value'] for p in prefs if p['kind'] == k] for k in ('allergy', 'avoid', 'prefer')}
    return {'user_id': uid, 'login_id': r['login_id'], 'premium': (await subscription_status(c, uid))['active'],
            'profile': {'version': r['profile_version'], 'gender': r['gender'], 'birth_date': r['birth_date'],
                        'include_used': r['include_used'], 'allergies': values['allergy'],
                        'ingredient_filter': {'avoid': values['avoid'], 'prefer': values['prefer']}}}


async def preferences(c, uid, kind, values):
    await execute(c, 'DELETE FROM app.member_preferences WHERE user_id=:u AND kind=:k', u=uid, k=kind)
    for value in sorted(set(values)):
        await execute(c, 'INSERT INTO app.member_preferences VALUES(:u,:k,:v)', u=uid, k=kind, v=value)


@router.post('/v2/auth/signup', status_code=201)
async def signup(data: Signup, req: Request):
    await throttle(req, 'signup')
    encoded = await run_in_threadpool(hash_password, data.password.get_secret_value())
    async with req.app.state.member_engine.begin() as c:
        r = await row(c, """INSERT INTO app.members(login_id,password_hash,gender,birth_date,consent_version)
            VALUES(:l,:p,:g,:b,:v) ON CONFLICT DO NOTHING RETURNING user_id""",
            l=data.login_id, p=encoded, g=data.gender, b=data.birth_date, v=data.consent_version)
        if not r:
            fail(409, 'LOGIN_ID_TAKEN')
        await preferences(c, r['user_id'], 'allergy', data.allergies)
    return wrap(dict(r), req)


@router.get('/v2/auth/login-id-availability')
async def login_available(req: Request, login_id: str = Query(pattern=r'^[A-Za-z0-9]{4,16}$')):
    await throttle(req, 'availability')
    async with req.app.state.member_engine.connect() as c:
        r = await row(c, 'SELECT user_id FROM app.members WHERE lower(login_id)=lower(:l)', l=login_id)
    return wrap({'available': r is None}, req)


@router.post('/v2/auth/login')
async def login(data: Login, req: Request):
    await throttle(req, 'login')
    async with req.app.state.member_engine.begin() as c:
        r = await row(c, 'SELECT user_id,password_hash FROM app.members WHERE lower(login_id)=lower(:l) FOR UPDATE', l=data.login_id)
        encoded = r['password_hash'] if r else 'scrypt$' + '00'*16 + '$' + '00'*32
        valid = await run_in_threadpool(check_password, data.password.get_secret_value(), encoded)
        if not r or not valid:
            fail(401, 'INVALID_CREDENTIALS')
        token = secrets.token_urlsafe(32)
        await execute(c, "INSERT INTO app.sessions(token_hash,user_id,expires_at) VALUES(:t,:u,now()+interval '7 days')",
                      t=hashlib.sha256(token.encode()).hexdigest(), u=r['user_id'])
    return wrap({'token': token, 'expires_in': 604800}, req)


@router.post('/v2/auth/logout', status_code=204)
async def logout(req: Request, uid=Depends(member)):
    async with req.app.state.member_engine.begin() as c:
        await execute(c, 'DELETE FROM app.sessions WHERE token_hash=:t', t=req.state.session_hash)
    return Response(status_code=204)


@router.get('/v2/me')
async def get_me(req: Request, uid=Depends(member)):
    async with req.app.state.member_engine.connect() as c:
        return wrap(await me(c, uid), req)


@router.patch('/v2/me/profile')
async def profile(data: ProfilePatch, req: Request, uid=Depends(member)):
    async with req.app.state.member_engine.begin() as c:
        old = await row(c, 'SELECT profile_version FROM app.members WHERE user_id=:u FOR UPDATE', u=uid)
        if old['profile_version'] != data.expected_version:
            fail(409, 'VERSION_CONFLICT')
        if 'ingredient_filter' in data.model_fields_set:
            if data.ingredient_filter is None:
                fail(422, 'INVALID_INPUT')
            if not (await subscription_status(c, uid))['active']:
                fail(403, 'PREMIUM_REQUIRED')
            for key in ('avoid', 'prefer'):
                await preferences(c, uid, key, getattr(data.ingredient_filter, key))
        for key in ('gender', 'birth_date', 'include_used'):
            if key in data.model_fields_set:
                await execute(c, f'UPDATE app.members SET {key}=:v WHERE user_id=:u', v=getattr(data, key), u=uid)
        if 'allergies' in data.model_fields_set:
            await preferences(c, uid, 'allergy', data.allergies)
        await execute(c, 'UPDATE app.members SET profile_version=profile_version+1 WHERE user_id=:u', u=uid)
        result = await me(c, uid)
    return wrap(result, req)


@router.patch('/v2/me/password', status_code=204)
async def password(data: PasswordChange, req: Request, uid=Depends(member)):
    async with req.app.state.member_engine.begin() as c:
        r = await row(c, 'SELECT password_hash FROM app.members WHERE user_id=:u FOR UPDATE', u=uid)
        if not await run_in_threadpool(check_password, data.current_password.get_secret_value(), r['password_hash']):
            fail(422, 'WRONG_PASSWORD')
        encoded = await run_in_threadpool(hash_password, data.new_password.get_secret_value())
        await execute(c, 'UPDATE app.members SET password_hash=:p WHERE user_id=:u', p=encoded, u=uid)
        await execute(c, 'DELETE FROM app.sessions WHERE user_id=:u AND token_hash<>:t', u=uid, t=req.state.session_hash)
    return Response(status_code=204)


def mock_only():
    if os.getenv('BILLING_MODE', 'disabled') != 'mock':
        fail(503, 'PAYMENT_PROVIDER_NOT_CONFIGURED')
    if os.getenv('APP_ENV', 'development') != 'development':
        fail(503, 'MOCK_BILLING_FORBIDDEN')


@router.get('/v2/subscription-plans')
async def plans(req: Request):
    async with req.app.state.member_engine.connect() as c:
        rows = (await execute(c, 'SELECT plan_id,name,price::text,currency,interval,benefits FROM app.subscription_plans WHERE enabled ORDER BY plan_id')).mappings().all()
    return wrap([dict(r) | {'billing_mode': os.getenv('BILLING_MODE', 'disabled')} for r in rows], req)


def payment_result(r, req, response, replay=False):
    if r['status'] == 'failed':
        fail(402, 'PAYMENT_FAILED')
    if r['status'] == 'refunded':
        fail(409, 'PAYMENT_ALREADY_REFUNDED')
    response.status_code = 202 if r['status'] == 'pending' else 200 if replay else 201
    return wrap({k: r[k] for k in ('subscription_id', 'invoice_id', 'payment_id')} |
                {'status': r['status'], 'billing_mode': 'mock'}, req)


@router.post('/v2/me/subscriptions')
async def subscribe(data: SubscriptionRequest, req: Request, response: Response,
                    idempotency_key: str = Header(min_length=8, max_length=128), uid=Depends(member)):
    mock_only()
    digest = hashlib.sha256(json.dumps(data.model_dump(), sort_keys=True).encode()).hexdigest()
    async with req.app.state.member_engine.begin() as c:
        await row(c, 'SELECT user_id FROM app.members WHERE user_id=:u FOR UPDATE', u=uid)
        prior = await row(c, """SELECT i.*,p.payment_id,p.status FROM app.invoices i JOIN app.payments p USING(invoice_id)
            WHERE i.user_id=:u AND i.idempotency_key=:k""", u=uid, k=idempotency_key)
        if prior:
            if prior['request_hash'] != digest:
                fail(409, 'IDEMPOTENCY_CONFLICT')
            return payment_result(prior, req, response, replay=True)
        sub = await subscription_status(c, uid)
        if sub['active']:
            fail(409, 'SUBSCRIPTION_ALREADY_ACTIVE')
        pending = await row(c, """SELECT p.payment_id FROM app.payments p JOIN app.invoices i USING(invoice_id)
            WHERE i.user_id=:u AND p.status='pending' LIMIT 1""", u=uid)
        if pending:
            fail(409, 'PAYMENT_PENDING')
        plan = await row(c, 'SELECT * FROM app.subscription_plans WHERE plan_id=:p AND enabled', p=data.plan_id)
        if not plan:
            fail(404, 'PLAN_NOT_FOUND')
        sub = await row(c, """INSERT INTO app.subscriptions(user_id,plan_id,billing_mode) VALUES(:u,:p,'mock')
            ON CONFLICT(user_id) DO UPDATE SET plan_id=:p,billing_mode='mock',cancel_at_period_end=false,updated_at=now()
            RETURNING subscription_id""", u=uid, p=data.plan_id)
        invoice = await row(c, """INSERT INTO app.invoices(subscription_id,user_id,idempotency_key,request_hash,amount,currency,period_start,period_end)
            VALUES(:s,:u,:k,:h,:a,:cc,now(),now()+CAST(:period AS interval)) RETURNING *""",
            s=sub['subscription_id'], u=uid, k=idempotency_key, h=digest, a=plan['price'] or 0, cc=plan['currency'],
            period='1 month' if plan['interval'] == 'month' else '1 year')
        outcome = os.getenv('MOCK_PAYMENT_OUTCOME', 'succeeded')
        if outcome not in {'succeeded', 'failed', 'pending'}:
            fail(503, 'INVALID_BILLING_CONFIGURATION')
        payment = await row(c, """INSERT INTO app.payments(invoice_id,method,provider,status,error_code,paid_at)
            VALUES(:i,:m,'mock',:s,:e,CASE WHEN :s='succeeded' THEN now() ELSE NULL END) RETURNING *""",
            i=invoice['invoice_id'], m=data.payment_method, s=outcome, e='MOCK_DECLINED' if outcome == 'failed' else None)
        if outcome == 'succeeded':
            await execute(c, 'UPDATE app.subscriptions SET entitlement_end=:e,updated_at=now() WHERE subscription_id=:s',
                          e=invoice['period_end'], s=sub['subscription_id'])
        result = dict(invoice) | dict(payment)
    # Return failures after committing the failed attempt, so retries remain idempotent.
    return payment_result(result, req, response)


@router.get('/v2/me/subscription')
async def get_subscription(req: Request, uid=Depends(member)):
    async with req.app.state.member_engine.connect() as c:
        return wrap(await subscription_status(c, uid), req)


@router.post('/v2/me/subscription/cancel')
async def cancel_subscription(req: Request, uid=Depends(member)):
    async with req.app.state.member_engine.begin() as c:
        await row(c, 'SELECT user_id FROM app.members WHERE user_id=:u FOR UPDATE', u=uid)
        r = await row(c, 'UPDATE app.subscriptions SET cancel_at_period_end=true,updated_at=now() WHERE user_id=:u RETURNING subscription_id', u=uid)
        if not r:
            fail(404, 'SUBSCRIPTION_NOT_FOUND')
        return wrap(await subscription_status(c, uid), req)


@router.get('/v2/me/payments')
async def payments(req: Request, uid=Depends(member), limit: int = Query(20, ge=1, le=100)):
    async with req.app.state.member_engine.connect() as c:
        rows = (await execute(c, """SELECT p.payment_id,i.invoice_id,i.amount::text,i.currency,p.status,p.provider,p.method,p.created_at,p.paid_at
            FROM app.payments p JOIN app.invoices i USING(invoice_id) WHERE i.user_id=:u ORDER BY i.created_at DESC,i.invoice_id DESC LIMIT :n""", u=uid, n=limit)).mappings().all()
    return wrap([dict(r) for r in rows], req)


@router.post('/v2/me/payments/{payment_id}/mock-refund')
async def mock_refund(payment_id: UUID, req: Request, uid=Depends(member)):
    mock_only()
    async with req.app.state.member_engine.begin() as c:
        await row(c, 'SELECT user_id FROM app.members WHERE user_id=:u FOR UPDATE', u=uid)
        r = await row(c, """SELECT i.*,p.status FROM app.invoices i JOIN app.payments p USING(invoice_id)
            WHERE p.payment_id=:p AND i.user_id=:u FOR UPDATE OF p""", p=payment_id, u=uid)
        if not r:
            fail(404, 'PAYMENT_NOT_FOUND')
        if r['status'] not in {'succeeded', 'refunded'}:
            fail(409, 'PAYMENT_NOT_REFUNDABLE')
        if r['status'] == 'succeeded':
            await execute(c, "UPDATE app.payments SET status='refunded',refunded_at=now() WHERE payment_id=:p", p=payment_id)
            # A refund of an older period must not revoke a subsequent paid period.
            await execute(c, """UPDATE app.subscriptions SET entitlement_end=least(entitlement_end,now()),updated_at=now()
                WHERE subscription_id=:s AND entitlement_end=:e""", s=r['subscription_id'], e=r['period_end'])
    return wrap({'payment_id': payment_id, 'status': 'refunded', 'billing_mode': 'mock'}, req)


@router.post('/internal/v2/mock-payments/{payment_id}/resolve')
async def resolve(payment_id: UUID, data: Resolution, req: Request,
                  auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    mock_only()
    token = os.getenv('BILLING_TEST_TOKEN', '')
    if len(token) < 32 or not auth or not secrets.compare_digest(auth.credentials.encode(), token.encode()):
        fail(401, 'BILLING_TEST_AUTH_REQUIRED')
    async with req.app.state.member_engine.begin() as c:
        r = await row(c, """SELECT i.*,p.status FROM app.invoices i JOIN app.payments p USING(invoice_id)
            WHERE p.payment_id=:p""", p=payment_id)
        if not r:
            fail(404, 'PAYMENT_NOT_FOUND')
        await row(c, 'SELECT user_id FROM app.members WHERE user_id=:u FOR UPDATE', u=r['user_id'])
        p = await row(c, 'SELECT status FROM app.payments WHERE payment_id=:p FOR UPDATE', p=payment_id)
        if p['status'] not in {'pending', data.outcome}:
            fail(409, 'PAYMENT_STATE_CONFLICT')
        if p['status'] == 'pending':
            await execute(c, """UPDATE app.payments SET status=:s,paid_at=CASE WHEN :s='succeeded' THEN now() ELSE NULL END,
                error_code=CASE WHEN :s='failed' THEN 'MOCK_DECLINED' ELSE NULL END WHERE payment_id=:p""", s=data.outcome, p=payment_id)
            if data.outcome == 'succeeded':
                # Reconciliation keeps the original invoice's period; no double extension.
                await execute(c, 'UPDATE app.subscriptions SET entitlement_end=:e,updated_at=now() WHERE subscription_id=:s',
                              e=r['period_end'], s=r['subscription_id'])
    return wrap({'payment_id': payment_id, 'status': data.outcome, 'billing_mode': 'mock'}, req)
