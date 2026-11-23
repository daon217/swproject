"""Independent used-market commands. Default plan/status never performs HTTP."""
import argparse
import json
import os
from pathlib import Path
import signal
import threading

from services.collector.marketplace_live.config import load_config, rights
from services.collector.marketplace_live.probe import plan
from services.collector.marketplace_live.ebay_credentials import load_ebay_env
from services.collector.domeggook_live.domeggook_delivery import load
from .domestic import PROVIDERS, blocked
from .ebay_used import FILTER, open_worker, status, used_config
from .mock import run_mock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=('ebay_used',)+PROVIDERS, required=True)
    parser.add_argument('--config', default=os.environ.get('KKULPICK_USED_CONFIG'))
    parser.add_argument('--state-dir', default=os.environ.get('KKULPICK_MARKETPLACE_STATE_DIR'))
    parser.add_argument('--env-file', help='eBay credentials only; never loaded for domestic providers/status')
    modes = parser.add_mutually_exclusive_group()
    for mode in ('plan','status','mock','once','watch'):
        modes.add_argument('--'+mode,action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.mock:
            if not args.state_dir:
                raise ValueError('mock_state_directory_required')
            print(json.dumps(run_mock(args.provider,args.state_dir)));return 0
        if args.provider in PROVIDERS:
            result = blocked(args.provider)
            if args.status and args.state_dir:
                result['last_mock'] = load(Path(args.state_dir)/'mock-only'/args.provider/'last_mock_summary.json',None)
            print(json.dumps(result));return 2 if args.once or args.watch else 0
        if args.status:
            if not args.state_dir:
                raise ValueError('state_directory_required')
            print(json.dumps(status(args.state_dir)));return 0
        cfg_path = args.config or Path(__file__).parent/'ebay_used.example.json'
        configs = load_config(cfg_path)
        if len(configs) != 1:
            raise ValueError('one_used_profile_required')
        cfg = used_config(configs[0])
        if args.env_file:
            load_ebay_env(args.env_file)
        if not (args.once or args.watch):
            result = plan(cfg,3)
            # The reused plan checks credentials/grants, but its five-request
            # lookup estimate does not describe a retrying collection Worker.
            for field in ('sample_policy','max_products_inspected','planned_oauth_requests_max',
                          'planned_search_requests','planned_detail_requests_max',
                          'planned_HTTP_requests_max','retries','YES24_DB_allowed'):
                result.pop(field,None)
            result.update(mode='collection_plan', page_size=cfg['page_size'],
                queries_count=len(cfg['queries']), max_pages_per_query=cfg['max_pages_per_cycle'],
                HTTP_attempts_per_cycle=cfg['requests_per_cycle'],
                HTTP_attempts_per_hour=cfg['requests_per_hour'],
                HTTP_attempts_per_24h=cfg['requests_per_24h'],
                OAuth_and_retries_included_in_budget=True,
                auth_recovery='existing_bounded_401_refresh', max_task_attempts=cfg['max_task_attempts'],
                request_interval_seconds=cfg['request_interval_seconds'],
                cycle_interval_seconds=cfg['cycle_interval_seconds'])
            result.update(provider='ebay_used', search_filter=FILTER,
                collection_enabled=cfg['enabled'], shared_ebay_request_ledger=True,
                runtime_permission='lookup_and_systematic_collection_required',
                backend_permission='storage_reuse_price_and_owner_approval_required')
            from datetime import datetime, timezone
            result['collection_ready'] = bool(result['ready'] and cfg['enabled'] and rights(cfg,datetime.now(timezone.utc)))
            print(json.dumps(result));return int(not result['ready'])
        if not args.state_dir or not cfg['enabled']:
            print(json.dumps({'provider':'ebay_used','status':'blocked',
                              'reason':'enabled_profile_and_existing_shared_state_root_required','HTTP_requests':0}));return 2
        previous = {}
        with open_worker(cfg,args.state_dir) as worker:
            try:
                if threading.current_thread() is threading.main_thread():
                    for sig in (signal.SIGTERM,signal.SIGINT):
                        previous[sig] = signal.signal(sig,lambda *_: worker.stop.set())
                while not worker.stop.is_set():
                    worker.step()
                    if not args.watch:
                        break
                    if worker.state['hold'] or worker.http.state.get('hold'):
                        break
                    worker.stop.wait(1)
                result = worker.report();result['provider']='ebay_used'
                print(json.dumps(result))
                return int(bool(result['hold'] or result['backend'].get('hold')))
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig,handler)
    except Exception:
        print(json.dumps({'provider':args.provider,'status':'blocked',
                          'reason':'configuration_state_lock_or_runtime_requires_review',
                          'request_history_preserved':True,'automatic_state_reset':False}));return 2


if __name__=='__main__':
    raise SystemExit(main())
