"""Local operations: validate, monitor, backup-auto, verify-backup, restore-check.

Standard library only. No external calls, live restore, paid API or secret output.
backup-auto --loop runs only while this process, Docker and the PC are running.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen
from uuid import uuid4

import team_dev
import workspace

ROOT=Path(__file__).resolve().parents[1]
DOMAINS=('member','catalog','support')
BACKUPS=ROOT/'infra/team/local/backups'


def result(name,ok,code):
    return {'check':name,'ok':bool(ok),'code':code}


def captured(command,timeout=30,**kwargs):
    return subprocess.run(command,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          timeout=timeout,**kwargs).stdout


def config_checks(config,scope):
    """Inspect Compose's effective configuration, including env-file/OS precedence."""
    checks=[];services=config.get('services',{})
    for name in ('postgres','api','maintenance','migrate'):
        checks.append(result(name+'.configured',name in services,'SERVICE_REQUIRED'))
    pg=services.get('postgres',{}).get('environment',{})
    api=services.get('api',{}).get('environment',{})
    secrets_to_check={'POSTGRES_PASSWORD':pg.get('POSTGRES_PASSWORD')}
    for domain in DOMAINS:
        owner=pg.get(domain.upper()+'_OWNER_PASSWORD');runtime=pg.get(domain.upper()+'_APP_PASSWORD')
        secrets_to_check[domain+'_owner']=owner;secrets_to_check[domain+'_app']=runtime
        checks.append(result(domain+'.separate_roles',owner!=runtime,'OWNER_RUNTIME_SEPARATE'))
        checks.append(result(domain+'.runtime_password',api.get(domain.upper()+'_PASSWORD')==runtime,'RUNTIME_PASSWORD_MATCH'))
    secrets_to_check['COLLECTOR_TOKEN']=api.get('COLLECTOR_TOKEN')
    for key,value in secrets_to_check.items():
        valid=isinstance(value,str) and len(value)>=32 and value.lower() not in {'generated-by-init','changeme'}
        checks.append(result(key,valid,'SECRET_MIN_32'))
    checks.append(result('billing_mode',api.get('BILLING_MODE','disabled') in {'disabled','mock'},'SUPPORTED_BILLING_MODE'))
    checks.append(result('mock_environment',api.get('BILLING_MODE')!='mock' or api.get('APP_ENV')=='development','MOCK_DEVELOPMENT_ONLY'))
    for key in ('BILLING_TEST_TOKEN','ANALYSIS_WORKER_TOKEN'):
        value=api.get(key,'')
        checks.append(result(key,not value or (len(value)>=32 and value!=api.get('COLLECTOR_TOKEN')),'OPTIONAL_SEPARATE_TOKEN'))
    if api.get('ANALYSIS_WORKER_TOKEN') and api.get('BILLING_TEST_TOKEN'):
        checks.append(result('worker_billing_tokens',api['ANALYSIS_WORKER_TOKEN']!=api['BILLING_TEST_TOKEN'],'TOKENS_MUST_DIFFER'))
    origins=api.get('DEV_ORIGINS','http://localhost:3000').split(',')
    checks.append(result('origins',all(re.fullmatch(r'https?://[^/\s,*]+',x) for x in origins),'EXPLICIT_ORIGINS_REQUIRED'))
    for key in ('CATALOG_URL_HOSTS','AFFILIATE_URL_HOSTS'):
        hosts=api.get(key,'store.example.test').split(',')
        checks.append(result(key,all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',x) for x in hosts),'HOSTNAMES_ONLY'))
    try:valid=0<=float(api.get('CATALOG_PRICE_RATIO','10'))<float('inf')
    except (ValueError,TypeError):valid=False
    checks.append(result('price_ratio',valid,'FINITE_NONNEGATIVE_RATIO'))
    published=set()
    for name,service in services.items():
        for port in service.get('ports',[]):
            value=str(port.get('published',''))
            local=port.get('host_ip') in {'127.0.0.1','::1'}
            checks.append(result(name+'.port',local and value.isdigit() and 1024<=int(value)<=65535,'LOCAL_PORT_REQUIRED'))
            unique=(port.get('host_ip'),value,port.get('protocol','tcp')) not in published
            checks.append(result(name+'.port_unique',unique,'DUPLICATE_PORT'))
            published.add((port.get('host_ip'),value,port.get('protocol','tcp')))
    if scope=='full':
        env=services.get('vision',{}).get('environment',{})
        for key in ('WORKSPACE_TOKEN','REDIS_PASSWORD'):
            checks.append(result(key,isinstance(env.get(key),str) and len(env[key])>=32,'SECRET_MIN_32'))
        checks.append(result('llm',env.get('LLM_MODE')=='disabled','DEV_LLM_DISABLED'))
    return checks


def validate(scope='core'):
    api_port=None
    try:
        config=json.loads(captured(workspace.compose_command(scope)+['config','--format','json']))
        checks=config_checks(config,scope)
        for port in config.get('services',{}).get('api',{}).get('ports',[]):
            if str(port.get('target'))=='8000' and port.get('host_ip')=='127.0.0.1':
                value=str(port.get('published',''))
                if value.isdigit() and 1024<=int(value)<=65535:api_port=value
    except (OSError,ValueError,subprocess.SubprocessError):
        checks=[result('compose',False,'COMPOSE_CONFIG_UNAVAILABLE')]
    return {'ok':all(c['ok'] for c in checks),'checks':checks,'api_port':api_port}


def verify_backup(directory):
    """Validate the local manifest before any pg_restore command. No arbitrary paths."""
    directory=Path(directory)
    if directory.is_symlink() or not directory.is_dir():raise ValueError('INVALID_BACKUP_DIRECTORY')
    manifest_path=directory/'manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size>65536:raise ValueError('INVALID_MANIFEST')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    entries=manifest.get('databases',[])
    if len(entries)!=3:raise ValueError('INCOMPLETE_BACKUP')
    seen=set()
    for entry in entries:
        name=entry['database'];filename=entry['file']
        if name not in {'kkulpick_'+d for d in DOMAINS} or name in seen or filename!=name+'.dump':
            raise ValueError('INVALID_BACKUP_ENTRY')
        seen.add(name);path=directory/filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=entry['bytes'] or entry['bytes']<=0:
            raise ValueError('BACKUP_SIZE_MISMATCH')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
        if digest.hexdigest()!=entry['sha256']:raise ValueError('BACKUP_CHECKSUM_MISMATCH')
    stamp=datetime.strptime(manifest['created_utc'][:16],'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
    if stamp.timestamp()>time.time()+300:raise ValueError('BACKUP_TIMESTAMP_IN_FUTURE')
    return stamp


def latest_backup():
    """Newest completed set; do not silently hide corruption by using an older set."""
    paths=sorted((p.parent for p in BACKUPS.glob('*/manifest.json')),reverse=True)
    return paths[0] if paths else None


@contextmanager
def backup_lock():
    BACKUPS.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (BACKUPS/'.scheduler.lock').open('a+b') as stream:
        if stream.tell()==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            if os.name=='nt':
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream,fcntl.LOCK_UN)


def backup_due(hours=24):
    with backup_lock():
        previous=latest_backup()
        if previous:
            remaining=hours*3600-(time.time()-verify_backup(previous).timestamp())
            if remaining>0:return {'ok':True,'state':'not_due','next_check_seconds':math.ceil(remaining)}
        path=team_dev.backup(quiet=True)
        verify_backup(path)
        return {'ok':True,'state':'created','directory':str(path),'next_check_seconds':hours*3600}


def monitor(scope='core',max_backup_hours=48,min_free_gib=2):
    configuration=validate(scope);checks=configuration['checks']
    try:
        if configuration['api_port'] is None:raise ValueError('API_PORT_MISSING')
        with urlopen('http://127.0.0.1:'+configuration['api_port']+'/health',timeout=5) as response:
            healthy=json.load(response).get('status')=='ok'
    except (OSError,ValueError):healthy=False
    checks.append(result('api_and_three_databases',healthy,'HEALTH_UNAVAILABLE'))
    try:
        raw=captured(workspace.compose_command(scope)+['ps','--all','--format','json']).decode()
        rows=json.loads(raw) if raw.lstrip().startswith('[') else [json.loads(line) for line in raw.splitlines() if line.strip()]
        states={r['Service']:r for r in rows}
        required=('postgres','api','maintenance')
        if scope=='full':required+=('broker','cache','web','admin','vision','recommendation','collector',
                                    'worker','vision-worker','recommendation-worker','collector-worker','image-cleanup')
        for name in required:
            r=states.get(name,{})
            checks.append(result(name+'.running',r.get('State')=='running' and r.get('Health','') in {'','healthy'},'SERVICE_NOT_READY'))
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):
        checks.append(result('containers',False,'CONTAINER_STATUS_UNAVAILABLE'))
    free=shutil.disk_usage(ROOT).free
    checks.append(result('workspace_disk',free>=min_free_gib*1024**3,'LOW_FREE_DISK'))
    age=None
    try:
        path=latest_backup()
        if path:age=max(0,(time.time()-verify_backup(path).timestamp())/3600)
        checks.append(result('backup',age is not None and age<=max_backup_hours,'BACKUP_MISSING_OLD_OR_INVALID'))
    except (OSError,ValueError,KeyError,TypeError):
        checks.append(result('backup',False,'BACKUP_MISSING_OLD_OR_INVALID'))
    return {'ok':all(x['ok'] for x in checks),'checks':checks,
            'backup_age_hours':round(age,2) if age is not None else None,'workspace_free_gib':round(free/1024**3,2)}


def restore_check(directory):
    """Restore only into newly generated throwaway DBs, never existing/live DBs."""
    verify_backup(directory)
    names=[];checks=[]
    def pg(program,*args,**kwargs):
        return captured(team_dev.db_command('sh','-c','PGPASSWORD="$POSTGRES_PASSWORD" exec "$@"',
            'operations',program,'-h','127.0.0.1','-U','postgres',*args),timeout=1800,**kwargs)
    try:
        for domain in DOMAINS:
            target='kkulpick_verify_'+uuid4().hex
            pg('createdb',target);names.append(target)
            with (Path(directory)/('kkulpick_'+domain+'.dump')).open('rb') as stream:
                pg('pg_restore','--exit-on-error','-d',target,stdin=stream)
            table={'member':'members','catalog':'offers','support':'conversations'}[domain]
            # Check schema readability and the restored migration version, not private rows.
            pg('psql','-X','-v','ON_ERROR_STOP=1','-d',target,'-c',f'SELECT 1 FROM app.{table} LIMIT 0')
            revision=pg('psql','-X','-At','-v','ON_ERROR_STOP=1','-d',target,'-c','SELECT version_num FROM app.alembic_version').decode().strip()
            checks.append({'database':domain,'ok':bool(revision)})
    finally:
        failed=[]
        for target in names:
            try:pg('dropdb','--if-exists',target)
            except (OSError,subprocess.SubprocessError):failed.append(target)
        if failed:raise RuntimeError('TEMP_DATABASE_CLEANUP_FAILED: '+','.join(failed))
    return {'ok':all(c['ok'] for c in checks),'checks':checks,'temporary_databases_removed':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['validate','monitor','backup-auto','verify-backup','restore-check'])
    parser.add_argument('--scope',choices=['core','full'],default='core')
    parser.add_argument('--directory',type=Path)
    parser.add_argument('--loop',action='store_true')
    parser.add_argument('--interval-hours',type=int,default=24)
    parser.add_argument('--max-backup-hours',type=int,default=48)
    parser.add_argument('--min-free-gib',type=int,default=2)
    args=parser.parse_args()
    if not 1<=args.interval_hours<=168 or args.max_backup_hours<1 or args.min_free_gib<0:
        parser.error('invalid interval or disk threshold')
    if args.loop and args.action!='backup-auto':parser.error('--loop is only for backup-auto')
    while True:
        try:
            if args.action=='validate':report=validate(args.scope)
            elif args.action=='monitor':report=monitor(args.scope,args.max_backup_hours,args.min_free_gib)
            elif args.action=='backup-auto':report=backup_due(args.interval_hours)
            else:
                path=args.directory or latest_backup()
                if path is None:raise ValueError('NO_COMPLETED_BACKUP')
                if args.action=='restore-check':report=restore_check(path)
                else:verify_backup(path);report={'ok':True,'state':'checksum_verified'}
        except (OSError,ValueError,KeyError,TypeError,RuntimeError,subprocess.SubprocessError) as exc:
            # Never print subprocess stdout/stderr or configuration values.
            report={'ok':False,'code':type(exc).__name__}
            if isinstance(exc,RuntimeError) and str(exc).startswith('TEMP_DATABASE_CLEANUP_FAILED:'):
                report['cleanup_required']=str(exc).split(': ',1)[1]
        print(json.dumps(report,ensure_ascii=False),flush=True)
        if not args.loop:return 0 if report['ok'] else 1
        # Hash large backups once per scheduled attempt, not every minute.
        # Interruptible chunks keep Ctrl+C responsive without busy polling.
        until=time.monotonic()+report.get('next_check_seconds',60)
        while time.monotonic()<until:time.sleep(max(0,min(60,until-time.monotonic())))


if __name__=='__main__':
    try:sys.exit(main())
    except KeyboardInterrupt:sys.exit(130)
