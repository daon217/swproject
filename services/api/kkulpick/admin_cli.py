"""Owner-only grant/revoke; no default admin password and no public role editor.

python -m kkulpick.admin_cli grant LOGIN_ID --role admin
python -m kkulpick.admin_cli revoke LOGIN_ID
Use the member OWNER credential, never the API runtime account.
"""
import argparse
from sqlalchemy import create_engine,text
from .db import url


def change_access(conn, action, login_id, role):
    identity = conn.execute(text('''SELECT user_id,role FROM app.admin_identities
        WHERE lower(login_id)=lower(:l) FOR UPDATE'''), {'l': login_id}).mappings().one_or_none()
    if identity is not None:
        uid = identity['user_id']
        assigned_role = role if action == 'grant' else identity['role']
        audited_role = assigned_role
        conn.execute(text('''UPDATE app.admin_identities
            SET role=:r, enabled=:enabled, auth_version=auth_version+1 WHERE user_id=:u'''),
            {'u': uid, 'r': assigned_role, 'enabled': action == 'grant'})
        conn.execute(text('DELETE FROM app.admin_sessions WHERE user_id=:u'), {'u': uid})
    else:
        uid = conn.execute(text('''SELECT user_id FROM app.members
            WHERE lower(login_id)=lower(:l) AND deleted_at IS NULL FOR UPDATE'''),
            {'l': login_id}).scalar_one_or_none()
        if uid is None:
            raise SystemExit('Account not found. Complete the signup request first.')
        if action == 'grant':
            conn.execute(text('''INSERT INTO app.admin_accounts(user_id,role) VALUES(:u,:r)
                ON CONFLICT(user_id) DO UPDATE SET role=:r,enabled=true,updated_at=now()'''), {'u': uid, 'r': role})
            audited_role = role
        else:
            audited_role = conn.execute(text('''UPDATE app.admin_accounts SET enabled=false,updated_at=now()
                WHERE user_id=:u RETURNING role'''), {'u': uid}).scalar_one_or_none() or 'none'
    # 감사 기록에는 실제로 부여·회수된 역할을 남긴다(회수 때 --role 기본값 'support'가 찍히던 문제, #61).
    conn.execute(text('INSERT INTO app.admin_audit(target_id,action) VALUES(:u,:a)'),
                 {'u': uid, 'a': action + ':' + audited_role})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['grant','revoke'])
    p.add_argument('login_id')
    p.add_argument('--role',choices=['admin','support'],default='support')
    a=p.parse_args()
    engine=create_engine(url('owner','member'),hide_parameters=True)
    try:
        with engine.begin() as c:
            change_access(c, a.action, a.login_id, a.role)
        print('Administrator access updated; no passwords or tokens printed.')
    finally:engine.dispose()

if __name__=='__main__':main()
