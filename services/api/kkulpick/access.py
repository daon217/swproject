"""Recheck membership and privileges while holding a lock across domain DB work."""
from contextlib import asynccontextmanager
import hashlib
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from .members import bearer, fail, member, row


async def admin_member(req: Request, auth: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not auth or len(auth.credentials) > 256:
        fail(401, 'AUTH_REQUIRED')
    token_hash = hashlib.sha256(auth.credentials.encode()).hexdigest()
    async with req.app.state.member_engine.connect() as conn:
        identity = await row(conn, '''SELECT s.user_id
            FROM app.admin_sessions s JOIN app.admin_identities a USING(user_id)
            WHERE s.token_hash=:t AND s.expires_at>now() AND s.auth_version=a.auth_version AND a.enabled''',
            t=token_hash)
    if identity is None:
        return await member(req, auth)
    req.state.session_hash = token_hash
    req.state.admin_identity = True
    return identity['user_id']


@asynccontextmanager
async def access(req, uid, roles=None):
    async with req.app.state.member_engine.begin() as c:
        if getattr(req.state, 'admin_identity', False):
            if not roles:
                fail(403, 'ADMIN_REQUIRED')
            # Keep this session locked until domain work completes so revocation waits.
            admin = await row(c, '''SELECT a.role
                FROM app.admin_sessions s JOIN app.admin_identities a USING(user_id)
                WHERE s.user_id=:u AND s.token_hash=:t AND s.expires_at>now()
                AND s.auth_version=a.auth_version AND a.enabled FOR SHARE OF s''',
                u=uid, t=req.state.session_hash)
            if not admin:
                fail(401, 'AUTH_REQUIRED')
            if admin['role'] not in roles:
                fail(403, 'ADMIN_REQUIRED')
            req.state.admin_role = admin['role']
            yield c
            return
        user = await row(c, '''SELECT m.user_id FROM app.members m JOIN app.sessions s USING(user_id)
            WHERE m.user_id=:u AND m.deleted_at IS NULL AND s.token_hash=:t AND s.expires_at>now()
            FOR SHARE OF m,s''', u=uid, t=req.state.session_hash)
        if not user:
            fail(401,'AUTH_REQUIRED')
        if roles:
            # Row-locking the read-only role table would require UPDATE rights.
            # The owner CLI serializes role changes on the member row locked above.
            admin = await row(c, 'SELECT role FROM app.admin_accounts WHERE user_id=:u AND enabled',u=uid)
            if not admin or admin['role'] not in roles:
                fail(403,'ADMIN_REQUIRED')
            req.state.admin_role = admin['role']
        yield c
