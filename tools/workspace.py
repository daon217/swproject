"""Entire team development environment. Requires Python 3.11+ and Docker Compose v2."""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / 'infra/workspace/.env'


def run(args):
    subprocess.run(args, cwd=ROOT, check=True)


def env_file_value(relative, name):
    path = ROOT / relative
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.startswith(name + '='):
                return line.split('=', 1)[1].strip()
    return ''


def apply_dev_url_hosts():
    """services/api/.env의 수집·제휴 허용 호스트에 저장소의 개발용 쇼핑몰 목록을 더한다.
    예전에는 기본값이 store.example.test뿐이라 새로 init한 팀원 환경에서 크롤러 상품이 모두 거절되고
    관리자 제휴상품 등록도 422로 실패했다. 셸 환경변수는 --env-file보다 우선한다."""
    listing = ROOT / 'infra/workspace/shop_hosts.txt'
    if not listing.is_file():
        return
    base = [h.strip() for h in listing.read_text(encoding='utf-8').splitlines() if h.strip() and not h.startswith('#')]
    extra = base + ['www.' + h for h in base if h != 'store.example.test' and not h.startswith('www.')]
    for key in ('CATALOG_URL_HOSTS', 'AFFILIATE_URL_HOSTS'):
        current = os.environ.get(key) or env_file_value('services/api/.env', key) or 'store.example.test'
        hosts = [h.strip() for h in current.split(',') if h.strip()]
        os.environ[key] = ','.join(dict.fromkeys(hosts + extra))


def apply_dev_billing(scope):
    """integrated(팀 통합 실행)에서는 결제를 개발용 모의 결제로 켠다(실제 돈이 오가지 않음).
    services/api/.env.example의 BILLING_MODE=disabled 때문에 문서와 달리 프리미엄 화면이
    '결제 서비스가 연결되지 않았습니다'로 막혔다. 끄려면 infra/workspace/.env에 WORKSPACE_MOCK_BILLING=off."""
    if scope != 'integrated' or workspace_setting('WORKSPACE_MOCK_BILLING', 'on').lower() in ('off', '0', 'false', 'no'):
        return
    mode = os.environ.get('BILLING_MODE') or env_file_value('services/api/.env', 'BILLING_MODE') or 'disabled'
    app_env = os.environ.get('APP_ENV') or env_file_value('services/api/.env', 'APP_ENV') or 'development'
    if mode == 'disabled' and app_env == 'development':
        os.environ['BILLING_MODE'] = 'mock'


def apply_api_reload():
    """API 코드 자동 반영(uvicorn --reload)은 WORKSPACE_API_RELOAD=on일 때만. 기본은 꺼서 쉬는 동안 파일 감시 부하를 없앤다."""
    on = workspace_setting('WORKSPACE_API_RELOAD', 'off').lower() in ('on', '1', 'true', 'yes')
    os.environ['API_RELOAD_ARGS'] = '--reload --reload-dir /srv/kkulpick' if on else ''


def trim_build_cache():
    """up은 매번 --build로 이미지를 다시 만들어 옛 레이어가 빌드 캐시에 계속 쌓인다(실측: 몇 시간 만에 3GB → 10GB,
    도커 디스크 파일 17.6GB → 24.3GB). 빌드가 끝난 뒤 이름 없는 옛 이미지와, 지금 이미지가 쓰지 않는 빌드 캐시만 지운다
    (실측 10.2GB → 5.8GB). 현재 이미지의 레이어는 남으므로 다음 빌드 속도는 그대로다.
    (--max-used-space 상한 방식은 이 도커 환경에서 아무것도 지우지 않아 쓰지 않는다.) WORKSPACE_TRIM_BUILD_CACHE=off면 끔."""
    if workspace_setting('WORKSPACE_TRIM_BUILD_CACHE', 'on').lower() in ('off', '0', 'false', 'no'):
        return
    for command in (['docker', 'image', 'prune', '-f'], ['docker', 'builder', 'prune', '-f']):
        subprocess.run(command, cwd=ROOT, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def compose_command(scope='full', shared=False):
    apply_dev_url_hosts()
    apply_api_reload()
    apply_dev_billing(scope)
    command = ['docker', 'compose']
    for relative in ['infra/db/.env', 'services/api/.env', 'infra/workspace/.env']:
        path = ROOT / relative
        if not path.is_file():
            raise ValueError('Run python tools/workspace.py init first')
        command += ['--env-file', str(path)]
    files = ['infra/db/compose.yaml', 'infra/db/api.compose.yaml']
    if scope in ('full','integrated'):
        files.append('infra/workspace/compose.yaml')
    if scope in ('ui', 'full','integrated'):
        files.append('infra/ui/compose.yaml')
    if scope == 'integrated':
        files.append('infra/integration/compose.yaml')
    if scope in ('full', 'integrated'):
        files.append('infra/integration/embeddings.compose.yaml')
    files.append('infra/workspace/local.compose.yaml')
    for relative in files:
        command += ['-f', str(ROOT / relative)]
    # Local development never starts a gateway just because an old enrollment exists.
    host = ROOT / 'infra/team/local/bind_address'
    if shared and host.is_file():
        os.environ['TEAM_BIND_IP'] = host.read_text().strip()
        command += ['-f', str(ROOT / 'infra/team/team.compose.yaml')]
    return command


def workspace_setting(name, default=''):
    if name in os.environ:
        return os.environ[name]
    if ENV.is_file():
        for line in ENV.read_text(encoding='utf-8').splitlines():
            if line.startswith(name + '='):
                return line.split('=', 1)[1].strip()
    return default


def dev_adapters_enabled():
    """integrated: 연결 확인용 어댑터 8개를 켤지(기본 켜짐, WORKSPACE_DEV_ADAPTERS=off면 끔)."""
    return workspace_setting('WORKSPACE_DEV_ADAPTERS', 'on').lower() not in ('off', '0', 'false', 'no')


def compose(*args, scope='full', shared=False):
    # compose_command가 os.environ에 쇼핑몰 목록·모의 결제를 넣으므로 env를 복사하기 전에 먼저 부른다.
    command = compose_command(scope, shared) + list(args)
    env = None
    if scope == 'integrated' and dev_adapters_enabled():
        profiles = [p for p in os.environ.get('COMPOSE_PROFILES', '').split(',') if p]
        env = os.environ | {'COMPOSE_PROFILES': ','.join(profiles + ['dev-adapters'])}
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def doctor():
    """Check local prerequisites only: no VPN, SSH keys, cloud account or API key."""
    failed = sys.version_info < (3, 11)
    print('FAIL' if failed else 'OK', 'Python 3.11+ (3.12 recommended)')
    for executable in ('git', 'docker'):
        found = shutil.which(executable) is not None
        print('OK' if found else 'FAIL', executable)
        failed |= not found
    for command in (['docker', 'compose', 'version', '--short'],
                    ['docker', 'info', '--format', '{{.OSType}}']):
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=20)
            if command[1] == 'info' and result.stdout.strip() != 'linux':
                raise ValueError('Linux containers required')
            print('OK', ' '.join(command[:2]))
        except (OSError, ValueError, subprocess.SubprocessError):
            failed = True
            print('FAIL', ' '.join(command[:2]), '- start Docker Desktop with Linux containers / Compose v2')
    print('Local mode: no Tailscale, SSH enrollment, shared host, or Claude key required.')
    return int(failed)


def api_port():
    values = dict(line.strip().split('=', 1)
                  for line in (ROOT / 'services/api/.env').read_text(encoding='utf-8').splitlines()
                  if line.strip() and not line.lstrip().startswith('#'))
    value = os.environ.get('API_PORT', values.get('API_PORT', '8000'))
    if not value.isdigit() or not 1024 <= int(value) <= 65535:
        raise ValueError('API_PORT must be between 1024 and 65535')
    return value


def initialize():
    run([sys.executable, 'services/api/dev.py', 'init'])
    api_env=ROOT / 'services/api/.env'
    api_settings=dict(line.split('=',1) for line in api_env.read_text().splitlines() if '=' in line and not line.startswith('#'))
    if not api_settings.get('ANALYSIS_WORKER_TOKEN'):
        with api_env.open('a',encoding='utf-8') as out:
            out.write('\nANALYSIS_WORKER_TOKEN='+secrets.token_hex(32)+'\n')
        print('Created private analysis worker credential.')
    if not ENV.exists():
        fd = os.open(ENV, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            out.write('WORKSPACE_TOKEN=' + secrets.token_hex(32) + '\n')
            out.write('REDIS_PASSWORD=' + secrets.token_hex(32) + '\n')
            out.write('WEB_PORT=3000\nDEV_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001\nTEMP_IMAGE_TTL_SECONDS=3600\nLLM_MODE=disabled\nANTHROPIC_API_KEY=\nANTHROPIC_MODEL=\n')
        print('Created workspace settings. Credentials not printed.')
    else:
        print('Existing workspace credentials preserved.')
    for app in ('web', 'admin', 'mobile', 'extension'):
        target = ROOT / 'apps' / app / '.env.local'
        if not target.exists():
            with target.open('x', encoding='utf-8', newline='\n') as output:
                output.write((target.parent / '.env.example').read_text(encoding='utf-8'))
            print('Created', 'apps/' + app + '/.env.local')
        else:
            print('Preserved', 'apps/' + app + '/.env.local (check old tunnel URLs manually)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['doctor', 'init', 'up', 'check', 'seed', 'backup', 'status', 'logs', 'stop', 'share', 'maintenance', 'admin', 'validate', 'monitor'])
    parser.add_argument('--login-id', help='Existing member login ID for owner-only admin grant/revoke')
    parser.add_argument('--role', choices=['admin','support'], default='support')
    parser.add_argument('--revoke', action='store_true')
    parser.add_argument('--apply', action='store_true', help='Apply maintenance deletions; otherwise preview only')
    parser.add_argument('--scope', choices=['core', 'ui', 'full', 'integrated'], default=None,
                        help='up/check default to core; other actions default to full. core: DB + API; ui: DB + API + UI previews; full: all development services')
    parser.add_argument('--shared', action='store_true', help='Explicitly include an already enrolled VPN gateway')
    args = parser.parse_args()
    if args.scope is None:
        args.scope = 'core' if args.action in ('up', 'check', 'validate', 'monitor') else 'integrated' if args.action in ('stop','status','logs') else 'full'
    options = {'scope': args.scope, 'shared': args.shared or args.action == 'share'}
    if args.action == 'share' and args.scope != 'full':
        parser.error('share requires --scope full')
    if args.action == 'doctor':
        return doctor()
    elif args.action == 'init':
        initialize()
    elif args.action in ('validate','monitor'):
        if args.scope in ('ui','integrated'):
            parser.error('validate/monitor use --scope core or full; UI uses check --scope ui')
        run([sys.executable,'tools/operations.py',args.action,'--scope',args.scope])
    elif args.action in ('up', 'share'):
        compose('up', '-d', '--build', '--wait', '--wait-timeout', '1200' if args.scope == 'integrated' else '300', **options)
        trim_build_cache()
        if args.action == 'share':
            run([sys.executable, 'infra/team/team.py', 'home'])
    elif args.action == 'check':
        if args.scope in ('core', 'ui'):
            run([sys.executable, 'tools/team_dev.py', 'check', '--port', api_port()])
            compose('exec', '-T', 'postgres', 'bash', '/opt/kkulpick/check.sh', **options)
            if args.scope == 'ui':
                import urllib.request
                for port in (5174, 8081):
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/backend/health', timeout=10) as response:
                        assert response.status == 200
                    print('OK UI and API proxy', port)
        else:
            smoke_env = [] if args.scope != 'integrated' or dev_adapters_enabled() else ['-e', 'SMOKE_DEV_ADAPTERS=off']
            compose('run', '--rm', '--no-deps', *smoke_env, 'smoke', **options)
    elif args.action == 'seed':
        run([sys.executable, 'services/api/dev.py', 'seed'])
    elif args.action == 'backup':
        run([sys.executable, 'tools/team_dev.py', 'backup'])
    elif args.action == 'admin':
        if not args.login_id:
            parser.error('admin requires --login-id')
        compose('run', '--rm', '--no-deps', 'migrate', 'python', '-m', 'kkulpick.admin_cli',
                'revoke' if args.revoke else 'grant', args.login_id, '--role', args.role, **options)
    elif args.action == 'maintenance':
        compose('run', '--rm', '--no-deps', 'maintenance', 'python', '-m', 'kkulpick.maintenance',
                *(['--apply'] if args.apply else []), **options)
    elif args.action == 'status':
        compose('ps', **options)
    elif args.action == 'logs':
        compose('logs', '--tail', '50', **options)
    else:
        compose('stop', **options)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
