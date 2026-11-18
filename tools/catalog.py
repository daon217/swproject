"""Import a local JSON observation array through the authenticated catalog API."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / 'services/api/.env'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def read_rows(path):
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError('Split files larger than 50 MiB before importing')
    raw = path.read_bytes()
    rows = json.loads(raw)
    if not isinstance(rows, list) or not rows or len(rows) > 100000:
        raise ValueError('Expected a non-empty JSON array, at most 100000 observations')
    hosts = set()
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not isinstance(row.get('source'), str) or not row['source']:
            raise ValueError(f'Row {i}: missing source')
        if row.get('url'):
            url = urlsplit(row['url'])
            if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password:
                raise ValueError(f'Row {i}: invalid product URL')
            hosts.add(url.hostname)
    return rows, hosts, hashlib.sha256(raw).hexdigest()


def config():
    if not ENV.is_file():
        raise ValueError('Run py tools/workspace.py init first')
    return dict(line.strip().split('=', 1) for line in ENV.read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.lstrip().startswith('#'))


def configure_hosts(hosts):
    cfg = config()
    allowed = {h.strip() for h in cfg.get('CATALOG_URL_HOSTS', 'store.example.test').split(',') if h.strip()}
    allowed.update(hosts)
    lines = [line for line in ENV.read_text(encoding='utf-8').splitlines()
             if not line.startswith('CATALOG_URL_HOSTS=')]
    lines.append('CATALOG_URL_HOSTS=' + ','.join(sorted(allowed)))
    # Preserve other local credentials; never print them or commit this file.
    with ENV.open('w', encoding='utf-8', newline='\n') as out:
        out.write('\n'.join(lines) + '\n')
    print('Allowed product URL hosts:', ', '.join(sorted(hosts)))
    print('Restart API: py tools/workspace.py up --scope core')


def import_rows(rows, digest, cfg, opener=None):
    port = os.environ.get('API_PORT', cfg.get('API_PORT', '8000'))
    if not port.isdigit() or not 1024 <= int(port) <= 65535:
        raise ValueError('Invalid API_PORT')
    token = cfg['COLLECTOR_TOKEN']
    opener = opener or build_opener(NoRedirect())
    counts = Counter()
    failures = []
    for i, row in enumerate(rows, 1):
        # One deterministic run per source/file. Retry leaves observation identifiers and timestamps intact.
        run_id = uuid5(NAMESPACE_URL, 'kkulpick:' + digest + ':' + row['source'])
        url = f'http://127.0.0.1:{port}/internal/v2/crawl-runs/{run_id}/observations'
        request = Request(url, data=json.dumps(row, ensure_ascii=False).encode('utf-8'),
                          headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
        for attempt in range(3):
            try:
                with opener.open(request, timeout=30) as response:
                    result = json.load(response)
                    kind = 'duplicate' if response.status == 200 else result.get('change_kind') or result['state']
                    counts[kind] += 1
                    if result.get('state') == 'quarantine':
                        failures.append({'row': i, 'code': result.get('error_code')})
                break
            except HTTPError as error:
                if error.code >= 500 and attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                counts['rejected'] += 1
                failures.append({'row': i, 'http_status': error.code})
                break
            except (URLError, TimeoutError, ConnectionError):
                if attempt < 2:
                    time.sleep(attempt + 1)
                    continue
                # Do not hammer an offline server for every remaining row. Replay the file safely later.
                counts['unconfirmed'] += 1
                failures.append({'row': i, 'code': 'NETWORK_ERROR_REPLAY_FILE'})
                counts['not_attempted'] = len(rows) - i
                return counts, failures
        if i % 50 == 0:
            print(f'Processed {i}/{len(rows)}')
    return counts, failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'configure-hosts', 'import'])
    parser.add_argument('--file', type=Path, required=True)
    args = parser.parse_args()
    rows, hosts, digest = read_rows(args.file)
    if args.action == 'inspect':
        print(json.dumps({'rows': len(rows), 'sources': dict(Counter(r['source'] for r in rows)),
                          'hosts': sorted(hosts)}, ensure_ascii=False, indent=2))
        print('Structure inspection only; API performs full schema validation on import.')
        return 0
    if args.action == 'configure-hosts':
        configure_hosts(hosts)
        return 0
    counts, failures = import_rows(rows, digest, config())
    print(json.dumps({'counts': dict(counts), 'failures': failures}, ensure_ascii=False, indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error))
