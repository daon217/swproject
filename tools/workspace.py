"""Entire team development environment. Requires Python 3.11+ and Docker Compose v2."""
import argparse
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / 'infra/workspace/.env'


def run(args):
    subprocess.run(args, cwd=ROOT, check=True)


def compose(*args):
    command = ['docker', 'compose']
    for relative in ['infra/db/.env', 'services/api/.env', 'infra/workspace/.env']:
        path = ROOT / relative
        if not path.is_file():
            raise ValueError('Run python tools/workspace.py init first')
        command += ['--env-file', str(path)]
    for relative in ['infra/db/compose.yaml', 'infra/db/api.compose.yaml', 'infra/workspace/compose.yaml']:
        command += ['-f', str(ROOT / relative)]
    # Keep the enrolled gateway in the same Compose project when sharing is configured.
    host = ROOT / 'infra/team/local/bind_address'
    if host.is_file():
        os.environ['TEAM_BIND_IP'] = host.read_text().strip()
        command += ['-f', str(ROOT / 'infra/team/team.compose.yaml')]
    run(command + list(args))


def initialize():
    run([sys.executable, 'services/api/dev.py', 'init'])
    if not ENV.exists():
        fd = os.open(ENV, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as out:
            out.write('WORKSPACE_TOKEN=' + secrets.token_hex(32) + '\n')
            out.write('REDIS_PASSWORD=' + secrets.token_hex(32) + '\n')
            out.write('WEB_PORT=3000\nDEV_ORIGINS=http://localhost:3000,http://127.0.0.1:3000\nTEMP_IMAGE_TTL_SECONDS=3600\nLLM_MODE=disabled\nANTHROPIC_API_KEY=\nANTHROPIC_MODEL=\n')
        print('Created workspace settings. Credentials not printed.')
    else:
        print('Existing workspace credentials preserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'up', 'check', 'status', 'logs', 'stop', 'share'])
    args = parser.parse_args()
    if args.action == 'init':
        initialize()
    elif args.action in ('up', 'share'):
        compose('up', '-d', '--build', '--wait', '--wait-timeout', '300')
        if args.action == 'share':
            run([sys.executable, 'infra/team/team.py', 'home'])
    elif args.action == 'check':
        compose('run', '--rm', '--no-deps', 'smoke')
    elif args.action == 'status':
        compose('ps')
    elif args.action == 'logs':
        compose('logs', '--tail', '50')
    else:
        compose('stop')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
