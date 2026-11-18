from pathlib import Path
import ast,json,os,secrets,socket,subprocess,sys,time
assert os.environ.get('KKULPICK_DEVTEST_APPROVED')=='1','explicit_synthetic_devtest_approval_required'
ROOT=Path(os.environ['KKULPICK_DEVTEST_ROOT']).resolve()
BIN=Path(os.environ['KKULPICK_DEVTEST_PG_BIN']).resolve();DATA=ROOT/'pgdata'
DATA.resolve().relative_to(ROOT.resolve())
def free(preferred):
    with socket.socket() as s:
        try:s.bind(('127.0.0.1',preferred))
        except OSError:s.bind(('127.0.0.1',0))
        return s.getsockname()[1]
secret=ROOT/'private_test_secrets.json'
if not secret.exists():
    secret.write_text(json.dumps({'db_port':free(55473),'api_port':free(18765),'dbname':'kkulpick_fixture_'+secrets.token_hex(4),
        'admin_password':secrets.token_urlsafe(36),'app_password':secrets.token_urlsafe(36),'api_token':secrets.token_urlsafe(40)}),encoding='utf-8')
settings=json.loads(secret.read_text())
def cmd(args,env=None):
    r=subprocess.run([str(x) for x in args],capture_output=True,env=env,creationflags=0x08000000 if os.name=='nt' else 0)
    if r.returncode:raise RuntimeError('isolated_PG_command_failed:'+Path(args[0]).name+':'+r.stderr.decode(errors='replace')[:250])
    return r
if not DATA.exists():
    password=ROOT/'initdb-password.private';password.write_text(settings['admin_password'],encoding='utf-8')
    try:cmd([BIN/'initdb.exe','-D',DATA,'-U','kkulpick_fixture_admin','--pwfile',password,'--auth=scram-sha-256','--encoding=UTF8','--locale=C'])
    finally:password.unlink(missing_ok=True)
    with (DATA/'postgresql.conf').open('a',encoding='utf-8') as f:
        f.write("\nlisten_addresses='127.0.0.1'\nport="+str(settings['db_port'])+"\nmax_connections=20\n")
log=(ROOT/'postgres.log').open('ab')
server=subprocess.Popen([str(BIN/'postgres.exe'),'-D',str(DATA),'-h','127.0.0.1','-p',str(settings['db_port'])],stdout=log,stderr=log,
    creationflags=0x08000000 if os.name=='nt' else 0)
(ROOT/'postgres_process.json').write_text(json.dumps({'pid':server.pid,'data':str(DATA)}),encoding='utf-8')
import psycopg
conn={'host':'127.0.0.1','port':settings['db_port'],'user':'kkulpick_fixture_admin','password':settings['admin_password'],'autocommit':True}
deadline=time.monotonic()+20
while True:
    try:
        with psycopg.connect(dbname='postgres',connect_timeout=1,**conn):break
    except psycopg.OperationalError:
        if server.poll() is not None or time.monotonic()>deadline:raise RuntimeError('direct_isolated_PG_start_failed_see_local_log') from None
        time.sleep(.2)
with psycopg.connect(dbname='postgres',**conn) as c:
    assert Path(c.execute('SHOW data_directory').fetchone()[0]).resolve()==DATA.resolve()
    if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(settings['dbname'],)).fetchone():
        c.execute('CREATE DATABASE '+settings['dbname'])
with psycopg.connect(dbname=settings['dbname'],**conn) as c:
    if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='kkulpick_fixture_api'").fetchone():
        from psycopg import sql
        c.execute(sql.SQL('CREATE ROLE kkulpick_fixture_api LOGIN PASSWORD {}').format(sql.Literal(settings['app_password'])))
    if not c.execute("SELECT 1 FROM information_schema.schemata WHERE schema_name='app'").fetchone():
        assert json.loads((ROOT/'mock_results.json').read_text())['status']=='passed'
        c.execute('CREATE SCHEMA app')
        migrations=Path(os.environ['KKULPICK_DEVTEST_BACKEND'])/'migrations/versions'
        c.execute((migrations/'catalog.sql').read_text(encoding='utf-8'))
        for filename in ('0002_arrival_updates.py','0003_retention.py'):
            tree=ast.parse((migrations/filename).read_text(encoding='utf-8'))
            upgrade=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='upgrade')
            for call in ast.walk(upgrade):
                if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=='execute':c.execute(ast.literal_eval(call.args[0]))
        c.execute('GRANT USAGE ON SCHEMA app TO kkulpick_fixture_api')
        c.execute('GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA app TO kkulpick_fixture_api')
    version=c.execute('SELECT version()').fetchone()[0]
(ROOT/'approval_manifest.json').write_text(json.dumps({'approved_by':'user explicit approval in this chat','scope':'isolated synthetic test only',
    'data_directory':str(DATA),'db_host':'127.0.0.1','db_port':settings['db_port'],'dbname':settings['dbname'],
    'api_base_url':'http://127.0.0.1:'+str(settings['api_port']),'postgres_version':version,
    'team_DB_used':False,'team_sources_modified':False,'real_Domeggook_data_allowed':False},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'isolated_PG_started':True,'db_port':settings['db_port'],'api_port':settings['api_port'],'schema':'exact catalog.sql +0002/0003; vectors/member/support not loaded'}))
