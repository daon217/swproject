"""Recheck membership and privileges while holding a lock across domain DB work."""
from contextlib import asynccontextmanager
from .members import row, fail


@asynccontextmanager
async def access(req, uid, roles=None):
    async with req.app.state.member_engine.begin() as c:
        user = await row(c, '''SELECT m.user_id FROM app.members m JOIN app.sessions s USING(user_id)
            WHERE m.user_id=:u AND m.deleted_at IS NULL AND s.token_hash=:t AND s.expires_at>now()
            FOR SHARE OF m,s''', u=uid, t=req.state.session_hash)
        if not user:
            fail(401,'AUTH_REQUIRED')
        if roles:
            admin = await row(c, 'SELECT role FROM app.admin_accounts WHERE user_id=:u AND enabled FOR SHARE',u=uid)
            if not admin or admin['role'] not in roles:
                fail(403,'ADMIN_REQUIRED')
        yield c
