"""One-shot or 2-hour live Open API -> team HTTP ingestion test.

No manual SQLite; no fabricated native variant IDs. Uses existing collection budgets
and checkpoints. Explicitly separate from production HTTPS delivery configuration.
"""
import argparse
import getpass
import hashlib
import json
import os
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import requests

from .domeggook_operations import ROOT, configuration, BudgetWait
from .domeggook_discovery import DiscoveryRun, QueueClient, queue_loop, validate_discovery
from .domeggook_backend_contract import Observation
from .runtime import FileState
from .stable_identity import resolve

# Collector delivery address comes from the environment (same variable as collector_ops/unified_live);
# server addresses are not stored in this public repository. KKULPICK_API_BASE is the reader address.
BASE = os.environ.get('COLLECTOR_BACKEND_BASE_URL', '').strip().rstrip('/')


class ForwardStore:
    def __init__(self, original, sender):
        self.original, self.sender = original, sender

    @property
    def memory(self):
        return self.original.memory

    def put(self, row):
        # Store retains its normal field-permission behavior; the forwarding test
        # uses the live in-memory observation only after explicit authorization.
        result = self.original.put(row)
        self.sender.accept(row)
        return result


class Sender:
    def __init__(self, token, max_products):
        self.token = token
        self.max_products = max_products
        self.seen = set()
        self.attempted = self.applied = self.created = self.quarantined = self.failed = 0
        self.skipped = {}
        self.run_id = str(uuid.uuid4())
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})

    def skip(self, cause):
        self.skipped[cause] = self.skipped.get(cause, 0) + 1

    def accept(self, row):
        if self.attempted >= self.max_products:
            return
        try:
            row = resolve(row)
            sid, variant = row['source_listing_id'], row['variant_key']
            if row['source'] != 'domeggook' or row.get('identity_status') != 'verified_native_tuple' or not variant:
                return self.skip('native_identity_unverified')
            if sid in self.seen:
                return
            if row.get('price_conditions', {}).get('variant_price') != 'selected_native_option':
                return self.skip('variant_price_unconfirmed')
            price = row.get('unit_price')
            try:
                amount = Decimal(str(price))
                if not amount.is_finite() or amount < 0:
                    raise ValueError('invalid_price')
            except (InvalidOperation, ValueError, TypeError):
                return self.skip('invalid_option_price')
            name, currency, availability, url = (row.get(k) for k in ('product_name', 'currency', 'availability', 'product_url'))
            if not all((name, currency, availability, url)):
                return self.skip('missing_required_fields')
            parsed = urlsplit(str(url))
            if parsed.scheme != 'https' or parsed.hostname not in ('domeggook.com', 'www.domeggook.com'):
                return self.skip('unapproved_product_url')
            stamp = row.get('last_observed_at') or row.get('observed_at')
            body = {
                'schema_version': 2,
                'source': 'domeggook',
                'source_listing_id': str(sid),
                'variant_key': str(variant),
                'observed_at': stamp,
                'result': 'success',
                'selected_domain': 'product',
                'condition': 'new',
                'name': str(name),
                'price': str(amount),
                'currency': str(currency),
                'availability': str(availability),
                'url': str(url),
                'field_presence': ['name', 'price', 'currency', 'availability', 'url'],
            }
            key_source = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
            body['observation_key'] = 'domeggook:' + hashlib.sha256(key_source.encode()).hexdigest()
            Observation.model_validate(body, context={'hosts': ['domeggook.com', 'www.domeggook.com'], 'currencies': ['KRW']})
            self.seen.add(str(sid))
            self.attempted += 1
            try:
                r = self.session.post(
                    f'{BASE}/internal/v2/crawl-runs/{self.run_id}/observations',
                    json=body, timeout=20, allow_redirects=False,
                )
                try:
                    ack = r.json()
                except ValueError:
                    ack = {}
                state, kind, offer = ack.get('state'), ack.get('change_kind'), ack.get('offer_id')
                print(f'[POST {self.attempted}/{self.max_products}] HTTP={r.status_code} '
                      f'product={sid} variant={variant} state={state} change={kind} '
                      f'offer_id={offer} error={ack.get("error_code") or ack.get("detail")}', flush=True)
                if r.status_code in (200, 201) and state == 'applied' and offer:
                    self.applied += 1
                    if kind == 'created':
                        self.created += 1
                elif state == 'quarantine':
                    self.quarantined += 1
                else:
                    self.failed += 1
                if r.status_code in (401, 403):
                    raise RuntimeError('backend_auth_rejected_stop')
            except requests.RequestException as exc:
                self.failed += 1
                print('HTTP_REQUEST_ERROR:', type(exc).__name__, flush=True)
        except RuntimeError:
            raise
        except Exception as exc:
            self.skip('invalid_live_row_' + type(exc).__name__)

    def report(self):
        return {'attempted': self.attempted, 'applied': self.applied,
                'created': self.created, 'quarantined': self.quarantined,
                'failed': self.failed, 'skipped': self.skipped, 'run_id': self.run_id}

    def close(self):
        self.session.close()
        self.token = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--watch', action='store_true', help='repeat collection cycles at 7200-second interval')
    parser.add_argument('--max-products', type=int, default=10)
    parser.add_argument('--confirm-provider-rights', action='store_true',
                        help='attest actual provider authorization to store/reuse live product data')
    parser.add_argument('--confirm-price-semantics', action='store_true',
                        help='attest that variant prices at MOQ are suitable for the target catalog')
    args = parser.parse_args()
    if not 1 <= args.max_products <= 10:
        parser.error('--max-products must be 1..10')
    if urlsplit(BASE).scheme not in ('http', 'https') or not urlsplit(BASE).netloc:
        parser.error('Set COLLECTOR_BACKEND_BASE_URL to the team API address, e.g. http://<server>:8000')
    if not args.confirm_provider_rights or not args.confirm_price_semantics:
        parser.error('Both --confirm-provider-rights and --confirm-price-semantics are required; do not use until verified')
    cfg = validate_discovery(configuration())
    cfg['cycle_interval_seconds'] = 7200
    print('LIVE API ONLY; no manual SQLite; source=domeggook; POST over HTTP TEST only', flush=True)
    print('Existing internal API request cap and persisted ledger remain unchanged.', flush=True)
    token = getpass.getpass('Disposable Collector Token: ').strip()
    if not token:
        raise SystemExit('TOKEN MISSING')
    sender = Sender(token, args.max_products)
    client = None
    try:
        with FileState(ROOT / 'state').lock():
            client = QueueClient(cfg)
            run = DiscoveryRun(cfg, client)
            run.store = ForwardStore(run.store, sender)
            try:
                report = queue_loop(run, 'combined', watch=args.watch)
                print('COLLECTION:', json.dumps(report, ensure_ascii=False, default=str), flush=True)
            except KeyboardInterrupt:
                run.stop.set()
                run.checkpoint()
                print('INTERRUPTED', flush=True)
            except Exception as exc:
                print('COLLECTOR_STOP:', type(exc).__name__, str(exc), flush=True)
    finally:
        print('DB_RESULT:', json.dumps(sender.report(), ensure_ascii=False), flush=True)
        sender.close()
        if client is not None:
            client.close()


if __name__ == '__main__':
    main()
