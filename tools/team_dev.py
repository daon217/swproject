"""Team developer helpers. Python 3.11+, standard library only. Run from any directory."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def private_ip(value):
    ip = ipaddress.IPv4Address(value)
    ranges = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '127.0.0.0/8')
    if not any(ip in ipaddress.ip_network(n) for n in ranges):
        raise argparse.ArgumentTypeError('Use the host private IPv4 address.')
    return str(ip)


def port(value):
    n = int(value)
    if not 1024 <= n <= 65535:
        raise argparse.ArgumentTypeError('Use a port between 1024 and 65535.')
    return n


def doctor(role):
    failed = sys.version_info < (3, 11)
    print(('FAIL' if failed else 'OK'), 'Python', sys.version.split()[0], '(3.11+ required)')
    commands = [['git', '--version'], ['ssh', '-V'], ['ssh-keygen', '-?']]
    # ssh-keygen -? intentionally exits nonzero; availability is sufficient here.
    for command in commands:
        found = shutil.which(command[0])
        print('OK' if found else 'FAIL', command[0])
        failed |= not bool(found)
    if role == 'host':
        for command in [['docker', 'info', '--format', '{{.OSType}}'], ['docker', 'compose', 'version']]:
            try:
                result = run(command, capture_output=True, text=True, timeout=20)
                output = result.stdout.strip()
                if command[1] == 'info' and output != 'linux':
                    raise ValueError('Docker Desktop must use Linux containers')
                print('OK', ' '.join(command[:2]), output)
            except (OSError, ValueError, subprocess.SubprocessError):
                print('FAIL', ' '.join(command[:2]), '- start Docker Desktop with Linux containers')
                failed = True
        for relative in ['infra/db/.env', 'services/api/.env']:
            exists = (ROOT / relative).is_file()
            print('OK' if exists else 'FAIL', relative, '(values hidden)')
            failed |= not exists
    exe = shutil.which('tailscale') or str(Path(os.getenv('ProgramFiles', 'C:/Program Files')) / 'Tailscale/tailscale.exe')
    try:
        result = run([exe, 'ip', '-4'], capture_output=True, text=True, timeout=10)
        ip = result.stdout.strip()
        if ipaddress.ip_address(ip) not in ipaddress.ip_network('100.64.0.0/10'):
            raise ValueError('not connected')
        print('OK Tailscale IPv4:', ip)
    except (OSError, ValueError, subprocess.SubprocessError):
        print('WARN Tailscale not connected. Required for home access, unless using another team VPN.')
    return int(failed)


def connect(host, local_port, key):
    key = Path(key).expanduser().resolve()
    if not key.is_file():
        raise ValueError('Private key missing. Generate your own kkulpick_team key first; do not send it to anyone.')
    with socket.create_connection((host, 2222), timeout=5):
        pass
    print('Compare the first SSH host fingerprint with the value supplied by the host.', flush=True)
    print(f'Keep this window open. In another window: python tools/team_dev.py check --port {local_port}', flush=True)
    run(['ssh', '-p', '2222', '-i', str(key), '-o', 'IdentitiesOnly=yes',
         '-o', 'StrictHostKeyChecking=ask', '-o', 'ExitOnForwardFailure=yes',
         '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
         '-N', '-L', f'127.0.0.1:{local_port}:api:8000', f'tunnel@{host}'])


def check(local_port):
    base = f'http://127.0.0.1:{local_port}'
    for path in ['/health', '/v2/offers?selected_domain=product', '/v2/offers?selected_domain=food', '/openapi.json']:
        with urlopen(base + path, timeout=10) as response:
            data = json.load(response)
        if path == '/health':
            if data.get('status') != 'ok':
                raise ValueError('API health check failed')
            print('OK API and catalog DB')
        elif path == '/openapi.json':
            if '/v2/offers' not in data.get('paths', {}):
                raise ValueError('Unexpected API contract')
            print('OK OpenAPI contract')
        else:
            if not isinstance(data.get('items'), list):
                raise ValueError('Unexpected offers response')
            print('OK', path, 'rows:', len(data['items']))
    print('An empty list is valid; seed data expires after 24 hours.')


def db_command(*args):
    env = ROOT / 'infra/db/.env'
    if not env.is_file():
        raise ValueError('Initialize the host first: python services/api/dev.py init')
    return ['docker', 'compose', '--env-file', str(env), '-f', str(ROOT / 'infra/db/compose.yaml'),
            'exec', '-T', 'postgres', *args]


def backup():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    destination = ROOT / 'infra/team/local/backups' / stamp
    destination.mkdir(parents=True, mode=0o700)
    manifest = {'created_utc': stamp, 'format': 'pg_dump custom', 'databases': []}
    for domain in ('member', 'catalog', 'support'):
        name = 'kkulpick_' + domain
        target = destination / (name + '.dump')
        partial = target.with_suffix('.partial')
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as output:
            run(db_command('sh', '-c', 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -h 127.0.0.1 -U postgres -Fc "$1"', 'backup', name), stdout=output)
        with partial.open('rb') as archive:
            run(db_command('pg_restore', '--list'), stdin=archive, stdout=subprocess.DEVNULL)
        partial.rename(target)
        digest = hashlib.sha256()
        with target.open('rb') as archive:
            for block in iter(lambda: archive.read(1024 * 1024), b''):
                digest.update(block)
        manifest['databases'].append({'database': name, 'file': target.name, 'sha256': digest.hexdigest(), 'bytes': target.stat().st_size})
        print('OK backup archive:', name)
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Complete:', destination)
    print('Separate per-DB snapshots. Copy this directory to another private disk; not a scheduled/offsite backup.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    d = sub.add_parser('doctor'); d.add_argument('--role', choices=['host', 'client'], default='client')
    c = sub.add_parser('connect'); c.add_argument('host', type=private_ip)
    c.add_argument('--port', type=port, default=18000)
    c.add_argument('--key', default=str(Path.home() / '.ssh/kkulpick_team'))
    h = sub.add_parser('check'); h.add_argument('--port', type=port, default=18000)
    sub.add_parser('backup')
    args = parser.parse_args()
    if args.action == 'doctor':
        return doctor(args.role)
    if args.action == 'connect':
        connect(args.host, args.port, args.key)
    elif args.action == 'check':
        check(args.port)
    else:
        backup()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('FAILED:', exc, file=sys.stderr)
        sys.exit(1)
