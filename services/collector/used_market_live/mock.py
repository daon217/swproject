"""Offline scenarios: real eBay policies, synthetic domestic contract drafts."""
from datetime import datetime, timezone
from pathlib import Path

from services.collector.domeggook_live.domeggook_delivery import atomic
from services.collector.marketplace_live.probe import bounded_lookup
from services.collector.marketplace_live.synthetic import SyntheticHTTP, fixture_config, MockOutbox
from .domestic import fixtures, normalize_synthetic, PROVIDERS
from .ebay_used import UsedAdapter


def run_mock(provider, root):
    path = Path(root)/'mock-only'/provider
    if provider == 'ebay_used':
        cfg = fixture_config('ebay_browse')
        http = SyntheticHTTP('ebay_browse')
        for row in http.rows:
            row.update(conditionId='3000', condition='Used')
        http.rows[2].update(conditionId='2000', condition='Certified Refurbished',
                           estimatedAvailabilities=[{'estimatedAvailabilityStatus':'IN_STOCK'}])
        # Isolated synthetic outbox can never be opened by real delivery.
        queue = MockOutbox(cfg,path)
        adapter = UsedAdapter(cfg,http,credential_reader=lambda _: 'SYNTHETIC_NOT_A_KEY')
        def stage(checked, normalized):
            if checked['status'] == 'success':
                queue.stage(normalized)
        summary = bounded_lookup(adapter,cfg,3,on_result=stage)
        summary.update(provider=provider, mode='mock', synthetic_only=True,
                       queue_pending=queue.pending_count(), provider_HTTP_attempts=0)
        summary.update(products_success=summary['success'], products_held=summary['held'],
                       products_failed=summary['failed'])
    elif provider in PROVIDERS:
        summary = {'provider':provider, 'mode':'mock', 'synthetic_only':True,
                   'products_success':0, 'products_held':0, 'products_failed':0,
                   'draft_ready':0, 'hold_reasons':{}, 'backend_requests':0,
                   'HTTP_requests_this_command':0, 'last_collection_at':None,
                   'last_success_at':None, 'last_failure_at':None,
                   'live_supported':False, 'API_contract_ready':False}
        seen = set()
        summary['duplicate_ids_ignored'] = 0
        for row in fixtures(provider):
            summary['last_collection_at'] = datetime.now(timezone.utc).isoformat()
            try:
                result = normalize_synthetic(provider,row)
            except (ValueError,TypeError,KeyError,ArithmeticError):
                summary['products_failed'] += 1
                summary['last_failure_at'] = summary['last_collection_at']
                summary['hold_reasons']['synthetic_normalization_rejected'] = summary['hold_reasons'].get('synthetic_normalization_rejected',0)+1
                continue
            if result['source_listing_id'] in seen:
                summary['duplicate_ids_ignored'] += 1
                continue
            seen.add(result['source_listing_id'])
            if result['draft_ready']:
                summary['draft_ready'] += 1
            # A valid draft is still held for access/storage + backend schema approval.
            summary['products_held'] += 1
            for reason in result['missing_fields'] or ['partner_and_backend_contract_required']:
                summary['hold_reasons'][reason] = summary['hold_reasons'].get(reason,0)+1
    else:
        raise ValueError('unknown_provider')
    atomic(path/'last_mock_summary.json',summary)
    return summary
