"""Used-only policy around existing OAuth, normalization and durable runtime."""
from contextlib import ExitStack, contextmanager
from pathlib import Path

from services.collector.marketplace_live.adapters import Adapter, EBAY
from services.collector.marketplace_live.config import validate
from services.collector.marketplace_live.http import ProviderHTTP
from services.collector.marketplace_live.runner import Worker
from services.collector.domeggook_live.domeggook_delivery import load
from services.collector.domeggook_live.runtime import FileState

PROFILE = 'ebay_used'
# conditions:USED is broad; the ID allowlist excludes refurbished, open-box and parts.
USED_IDS = '2750|2990|3000|3010|4000|5000|6000'
FILTER = 'buyingOptions:{FIXED_PRICE},conditions:{USED},conditionIds:{' + USED_IDS + '}'


def used_config(cfg):
    validate(cfg)
    if cfg['source'] != 'ebay_browse' or cfg.get('collection_profile') != PROFILE:
        raise ValueError('explicit_ebay_used_profile_required')
    return cfg


class UsedAdapter(Adapter):
    def ebay_get(self, url, params=None):
        if url == EBAY + 'item_summary/search':
            params = dict(params or {}, filter=FILTER)
        return super().ebay_get(url, params)

    def normalize(self, row, at):
        result = super().normalize(row, at)
        if result['condition'] != 'used':
            result['observation'] = None
            result['missing_fields'] = sorted(set(result['missing_fields']) | {'used_condition_required'})
        return result


def profile_root(root):
    return Path(root) / PROFILE


@contextmanager
def open_worker(cfg, root):
    """Hold the original eBay writer lock while sharing its durable request ledger.

    This intentionally excludes the general eBay process on the same state root.
    Other providers retain their independent locks and can run concurrently.
    """
    used_config(cfg)
    root = Path(root)
    with ExitStack() as stack:
        stack.enter_context(FileState(root/'ebay_browse'/'lock').lock())
        stack.enter_context(FileState(profile_root(root)/'ebay_browse'/'lock').lock())
        shared = root/'ebay_browse'
        checkpoint = load(shared/'checkpoint.json', {})
        ledger = load(shared/'request_ledger.json', {'requests': []})
        if checkpoint.get('ledger_size', 0) > len(ledger['requests']):
            raise ValueError('missing_original_ebay_history_no_reset')
        http = ProviderHTTP(cfg, shared)
        try:
            worker = Worker(cfg, profile_root(root), http=http, adapter=UsedAdapter(cfg, http))
        except Exception:
            http.close()
            raise
        try:
            yield worker
        finally:
            worker.stop.set()
            worker.close()


def status(root):
    root = Path(root)
    checkpoint = load(profile_root(root)/'ebay_browse'/'checkpoint.json', {})
    ledger = load(root/'ebay_browse'/'request_ledger.json', {'requests': []})
    outbox = load(profile_root(root)/'ebay_browse'/'backend_outbox.json', {'entries': {}})
    totals = checkpoint.get('totals', {})
    return {'provider': PROFILE, 'source': 'ebay_browse', 'HTTP_requests_this_command': 0,
            'HTTP_attempts_shared_with_general_ebay': len(ledger['requests']),
            'products_success': totals.get('products_success', 0),
            'products_held': totals.get('products_held', 0),
            'products_failed': totals.get('products_failed', 0),
            'provider_failed_actions': totals.get('provider_failed_actions', 0),
            'provider_errors': totals.get('provider_errors', 0),
            'last_collection_at': checkpoint.get('last_collection_at'),
            'last_success_at': checkpoint.get('last_success_at'),
            'last_failure_at': checkpoint.get('last_failure_at'),
            'next_cycle_at': checkpoint.get('next_cycle_at'),
            'hold': checkpoint.get('hold') or ledger.get('hold'),
            'last_mock': load(root/'mock-only'/PROFILE/'last_mock_summary.json',None),
            'totals': totals, 'backend_states': {
                state: sum(e['status'] == state for e in outbox['entries'].values())
                for state in {e['status'] for e in outbox['entries'].values()}},
            'backend_hold': outbox.get('hold')}
