"""Request staff accounts and authenticate approved staff."""
import hashlib
import secrets
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool

from .access import access, admin_member
from .members import (
    Login, LoginId, Password, Strict, check_password, execute, fail,
    hash_password, row, throttle, wrap,
)

router = APIRouter(prefix='/v2/admin/auth')


class AdminSignup(Strict):
    login_id: LoginId
    password: Password
    password_confirmation: Password
    consent_version: str = Field(min_length=1, max_length=100)
    consent_accepted: Literal[True]

    @model_validator(mode='after')
    def match(self):
        if self.password != self.password_confirmation:
            raise ValueError('password mismatch')
        return self


class AdminApproval(Strict):
    role: Literal['admin', 'support']


@router.post('/signup', status_code=201)
async def signup(data: AdminSignup, req: Request):
    await throttle(req, 'signup')
    encoded = await run_in_threadpool(hash_password, data.password.get_secret_value())
    async with req.app.state.member_engine.begin() as conn:
        existing = await row(conn, 'SELECT user_id FROM app.members WHERE lower(login_id)=lower(:id)',
                             id=data.login_id)
        if existing:
            fail(409, 'LOGIN_ID_TAKEN')
        identity = await row(conn, '''INSERT INTO app.admin_identities(login_id,password_hash,consent_version)
            VALUES (:id,:p,:v) ON CONFLICT DO NOTHING RETURNING user_id''',
            id=data.login_id, p=encoded, v=data.consent_version)
        if not identity:
            fail(409, 'LOGIN_ID_TAKEN')
    return wrap({'user_id': identity['user_id'], 'status': 'pending_approval'}, req)


@router.post('/login')
async def login(data: Login, req: Request):
    await throttle(req, 'login')
    async with req.app.state.member_engine.begin() as conn:
        identity = await row(conn, '''SELECT user_id,password_hash,role,enabled,auth_version
            FROM app.admin_identities WHERE lower(login_id)=lower(:id)''', id=data.login_id)
        if identity is None:
            legacy = await row(conn, '''SELECT m.user_id,m.password_hash
                FROM app.members m JOIN app.admin_accounts a USING(user_id)
                WHERE lower(m.login_id)=lower(:id) AND m.deleted_at IS NULL AND a.enabled
                FOR UPDATE OF m''', id=data.login_id)
        else:
            legacy = None
        account = identity or legacy
        encoded = account['password_hash'] if account else 'scrypt$' + '00'*16 + '$' + '00'*32
        valid = await run_in_threadpool(check_password, data.password.get_secret_value(), encoded)
        if not account or not valid:
            fail(401, 'INVALID_CREDENTIALS')
        if identity is not None and not identity['enabled']:
            fail(403, 'ADMIN_APPROVAL_REQUIRED' if identity['role'] is None else 'ADMIN_REQUIRED')

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        if identity is not None:
            await execute(conn, '''INSERT INTO app.admin_sessions(token_hash,user_id,auth_version,expires_at)
                VALUES (:t,:u,:v,now()+interval '7 days')''',
                t=token_hash, u=identity['user_id'], v=identity['auth_version'])
        else:
            await execute(conn, '''INSERT INTO app.sessions(token_hash,user_id,expires_at)
                VALUES (:t,:u,now()+interval '7 days')''', t=token_hash, u=legacy['user_id'])
    return wrap({'token': token, 'expires_in': 604800}, req)


@router.post('/logout', status_code=204)
async def logout(req: Request, uid=Depends(admin_member)):
    async with req.app.state.member_engine.begin() as conn:
        if getattr(req.state, 'admin_identity', False):
            await execute(conn, 'DELETE FROM app.admin_sessions WHERE token_hash=:t AND user_id=:u',
                          t=req.state.session_hash, u=uid)
        else:
            await execute(conn, 'DELETE FROM app.sessions WHERE token_hash=:t AND user_id=:u',
                          t=req.state.session_hash, u=uid)
    return Response(status_code=204)


@router.get('/requests')
async def signup_requests(req: Request, limit: int = Query(100, ge=1, le=100), uid=Depends(admin_member)):
    async with access(req, uid, {'admin'}) as conn:
        result = await execute(conn, '''SELECT user_id, login_id, created_at
            FROM app.admin_identities WHERE role IS NULL AND NOT enabled
            ORDER BY created_at, user_id LIMIT :limit''', limit=limit)
        return wrap([dict(item) for item in result.mappings()], req)


@router.post('/requests/{user_id}/approve')
async def approve_signup(user_id: UUID, data: AdminApproval, req: Request, uid=Depends(admin_member)):
    async with access(req, uid, {'admin'}) as conn:
        result = await execute(conn, 'SELECT app.approve_admin_signup(:reviewer, :target, :role)',
                               reviewer=req.state.session_hash, target=user_id, role=data.role)
        status = result.scalar_one()
        if status == 'forbidden':
            fail(403, 'ADMIN_REQUIRED')
        if status == 'missing':
            fail(404, 'ADMIN_SIGNUP_NOT_FOUND')
        if status == 'not_pending':
            fail(409, 'ADMIN_SIGNUP_ALREADY_PROCESSED')
        if status != 'approved':
            fail(422, 'INVALID_INPUT')
    return wrap({'user_id': user_id, 'role': data.role, 'status': 'approved'}, req)
