"""Owner-only grant/revoke; no default admin password and no public role editor.

python -m kkulpick.admin_cli grant LOGIN_ID --role admin
python -m kkulpick.admin_cli revoke LOGIN_ID
Use the member OWNER credential, never the API runtime account.
"""
import argparse
from sqlalchemy import create_engine,text
from .db import url


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['grant','revoke'])
    p.add_argument('login_id')
    p.add_argument('--role',choices=['admin','support'],default='support')
    a=p.parse_args()
    engine=create_engine(url('owner','member'),hide_parameters=True)
    try:
        with engine.begin() as c:
            uid=c.execute(text('SELECT user_id FROM app.members WHERE lower(login_id)=lower(:l) AND deleted_at IS NULL FOR UPDATE'),{'l':a.login_id}).scalar_one_or_none()
            if uid is None:raise SystemExit('Active member not found. Sign up first.')
            if a.action=='grant':
                c.execute(text('''INSERT INTO app.admin_accounts(user_id,role) VALUES(:u,:r)
                    ON CONFLICT(user_id) DO UPDATE SET role=:r,enabled=true,updated_at=now()'''),{'u':uid,'r':a.role})
            else:
                c.execute(text('UPDATE app.admin_accounts SET enabled=false,updated_at=now() WHERE user_id=:u'),{'u':uid})
            c.execute(text('INSERT INTO app.admin_audit(target_id,action) VALUES(:u,:a)'),{'u':uid,'a':a.action+':'+a.role})
        print('Administrator access updated; no passwords or tokens printed.')
    finally:engine.dispose()

if __name__=='__main__':main()
