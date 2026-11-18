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


def compose_command(scope='full', shared=False):
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
    files.append('infra/workspace/local.compose.yaml')
    for relative in files:
        command += ['-f', str(ROOT / relative)]
    # Local development never starts a gateway just because an old enrollment exists.
    host = ROOT / 'infra/team/local/bind_address'
    if shared and host.is_file():
        os.environ['TEAM_BIND_IP'] = host.read_text().strip()
        command += ['-f', str(ROOT / 'infra/team/team.compose.yaml')]
    return command


def compose(*args, scope='full', shared=False):
    run(compose_command(scope, shared) + list(args))


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
            compose('run', '--rm', '--no-deps', 'smoke', **options)
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
