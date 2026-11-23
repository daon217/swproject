"""One isolated provider per process. Unapproved/incomplete configuration stays idle."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import threading

from services.collector.domeggook_live.domeggook_delivery import atomic,load
from services.collector.marketplace_live.config import load_config,rights,stamp
from .catalog import SOURCES,BLOCKED,PROVIDERS
from .runtime import worker_context,source_status
from .secrets import KEYS,load as load_secrets


def config(provider,path):
    if provider=='domeggook':
        cfg=load(Path(path),{'enabled':False})
        if type(cfg.get('enabled')) is not bool:raise ValueError('explicit_enabled_required')
        if cfg.get('food_policy','hold_until_contract') not in ('hold_until_contract','base_product_only'):
            raise ValueError('explicit_food_policy_required')
        return cfg
    choices=load_config(path)
    matched=[c for c in choices if c['source']==SOURCES[provider]]
    if len(matched)!=1:raise ValueError('one_matching_source_required')
    cfg=matched[0]
    if provider=='ebay_used':
        from services.collector.used_market_live.ebay_used import used_config
        used_config(cfg)
    elif cfg.get('collection_profile')=='ebay_used':
        raise ValueError('used_profile_requires_used_provider')
    return cfg


def preflight(provider,cfg,current=None):
    current=current or datetime.now(timezone.utc);reasons=[]
    if not cfg.get('enabled'):reasons.append('configuration_disabled')
    if os.environ.get('COLLECTOR_RUN_APPROVED')!='yes':reasons.append('explicit_run_approval_required')
    if provider=='domeggook':
        from services.collector.domeggook_live.domeggook_operations import configuration,grant_valid
        base=configuration();profile=cfg.get('backend_profile',{})
        allowed={'backend_enabled','backend_owner_approved','price_semantics_confirmed','storage_grants','backend_delivery'}
        if not isinstance(profile,dict) or set(profile)-allowed:raise ValueError('backend_profile_scope_invalid')
        base.update(profile)
        grants=base.get('storage_grants',{})
        if not all(grant_valid(grants,f,current) and grants[f].get('reuse') is True for f in ('product_name','unit_price','currency','availability','product_url')):
            reasons.append('storage_reuse_grants_required')
        delivery=base
    else:
        if not rights(cfg,current,storage=True):reasons.append('systematic_storage_reuse_grants_required')
        delivery=cfg
    if not all(delivery.get(k) is True for k in ('backend_enabled','backend_owner_approved','price_semantics_confirmed')):
        reasons.append('backend_owner_and_price_approval_required')
    from urllib.parse import urlsplit
    endpoint=urlsplit(delivery.get('backend_delivery',{}).get('base_url',''))
    if endpoint.scheme!='https' or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
        reasons.append('approved_HTTPS_team_API_endpoint_required')
    elif endpoint.hostname.endswith(('.invalid','.example','.test')):
        reasons.append('placeholder_team_API_endpoint_forbidden')
    if os.environ.get('COLLECTOR_CA_FILE') and not Path(os.environ['COLLECTOR_CA_FILE']).is_file():
        reasons.append('trusted_CA_file_missing')
    presence={n:bool(os.environ.get(n) or os.environ.get(n+'_FILE') and Path(os.environ[n+'_FILE']).is_file()) for n in KEYS[provider]+['KKULPICK_BACKEND_TOKEN']}
    if not all(presence.values()):reasons.append('required_credentials_missing')
    return {'provider':provider,'ready':not reasons,'configured_enabled':cfg['enabled'],
            'reasons':reasons,'credential_presence':presence,
            'budget':{k:delivery[k] for k in ('requests_per_cycle','requests_per_hour','requests_per_24h','requests_per_kst_day',
                 'request_interval_seconds','max_units_per_month','cost_per_request','max_cost_per_month','cost_currency','credits_per_request') if k in delivery},
            'cycle_interval_seconds':max(7200,cfg.get('cycle_interval_seconds',7200)),
            'HTTP_requests_this_command':0,'team_API_only':True}


def snapshot(provider,cfg,root):
    if provider in SOURCES:return source_status(cfg,root,provider)
    state=load(Path(root)/'domeggook_ops/discovery_checkpoint.json',{})
    ledger=load(Path(root)/'domeggook_ops/request_ledger.json',{'requests':[]})
    box=load(Path(root)/'domeggook_ops/backend_delivery/backend_outbox.json',{'totals':{}})
    listings=list(state.get('listings',{}).values());totals=state.get('totals',{});acks=box.get('totals',{})
    last=max((j['last_success_at'] for j in listings if j.get('last_success_at')),default=None)
    failed=max((j['last_failure_at'] for j in listings if j.get('last_failure_at')),default=None)
    processed=state.get('discovery',{}).get('last_processed') or {}
    last_collection=max((t for t in (last,failed,processed.get('observed_at')) if t),default=None)
    return {'provider':provider,'configured_enabled':cfg['enabled'],'last_success_at':last,
            'last_collection_at':last_collection,'last_failure_at':failed,
            'currently_quarantined_items':sum(j.get('detail_status')=='quarantine' for j in listings),
            'currently_failed_items':sum(j.get('detail_status')=='failed' for j in listings),
            'products_success_current':sum(j.get('detail_status')=='success' and j.get('identity_status')=='verified' for j in listings),
            'products_held_current':sum(j.get('identity_status')=='quarantine' for j in listings),
            'product_count_semantics':'current_listing_states; cumulative_attempts_in_source_metrics',
            'source_metrics':totals,'HTTP_attempts':len(ledger['requests']),
            'hold':ledger.get('hold') or state.get('recovery_hold') or box.get('hold'),
            'DB_ack_created':acks.get('change_created',0),'DB_ack_updated':acks.get('change_updated',0),
            'DB_ack_quarantined':acks.get('ack_quarantine',0),'backend_metrics':acks,
            'HTTP_requests_this_command':0}


def heartbeat(path,provider,cfg,root,stop,reason=None):
    while not stop.is_set():
        try:
            data=snapshot(provider,cfg,root)
            data.update(heartbeat_at=datetime.now(timezone.utc).isoformat(),process_state=reason or 'running')
            atomic(path,data)
        except Exception:stop.set();return
        stop.wait(20)


def start_heartbeat(path,provider,cfg,root,stop,reason=None):
    data=snapshot(provider,cfg,root)
    data.update(heartbeat_at=datetime.now(timezone.utc).isoformat(),process_state=reason or 'running')
    atomic(path,data)
    thread=threading.Thread(target=heartbeat,args=(path,provider,cfg,root,stop,reason),daemon=True)
    thread.start();return thread


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider',choices=PROVIDERS,required=True)
    p.add_argument('--config',default=os.environ.get('COLLECTOR_CONFIG'))
    p.add_argument('--state-dir',default=os.environ.get('KKULPICK_MARKETPLACE_STATE_DIR') or os.environ.get('KKULPICK_STATE_DIR'))
    modes=p.add_mutually_exclusive_group()
    for mode in ('plan','status','health','once','watch','mock'):modes.add_argument('--'+mode,action='store_true')
    p.add_argument('--max-ticks',type=int)
    args=p.parse_args(argv);stop=threading.Event();previous={};thread=None
    try:
        if args.max_ticks is not None and args.max_ticks<1:raise ValueError('positive_max_ticks_required')
        root=Path(args.state_dir or '/state');path=root/'ops'/args.provider/'heartbeat.json'
        if args.health:
            data=load(path,{})
            return 0 if data.get('heartbeat_at') and (datetime.now(timezone.utc)-stamp(data['heartbeat_at'])).total_seconds()<120 else 1
        if args.provider in BLOCKED:
            if args.mock and args.provider in ('bunjang','joongna'):
                from services.collector.used_market_live.mock import run_mock
                print(json.dumps(run_mock(args.provider,root)));return 0
            print(json.dumps({'provider':args.provider,'status':'disabled','reason':BLOCKED[args.provider],'HTTP_requests':0}));return 2 if args.once or args.watch else 0
        if args.mock:
            from .mock import run_mock
            print(json.dumps(run_mock(args.provider,root)));return 0
        if not args.config:raise ValueError('explicit_configuration_required')
        cfg=config(args.provider,args.config)
        if args.status:
            data=snapshot(args.provider,cfg,root);data['process']=load(path,None)
            print(json.dumps(data));return 0
        check=preflight(args.provider,cfg)
        if not (args.once or args.watch):print(json.dumps(check));return int(not check['ready'])
        if not args.state_dir:raise ValueError('persistent_state_required')
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT,signal.SIGTERM):previous[sig]=signal.signal(sig,lambda *_:stop.set())
        if not check['ready']:
            if args.once:print(json.dumps(check));return 2
            # Keep disabled containers stable across NAS reboot; never read secrets or request data.
            thread=start_heartbeat(path,args.provider,cfg,root,stop,'disabled_or_permission_wait')
            ticks=0
            while not stop.is_set():
                ticks+=1
                if args.max_ticks and ticks>=args.max_ticks:break
                stop.wait(1)
            print(json.dumps(check));return 0
        load_secrets(args.provider,backend=True)
        thread=start_heartbeat(path,args.provider,cfg,root,stop)
        if args.provider=='domeggook':
            from .dome import run
            print(json.dumps(run(cfg,root,stop,once=args.once)));return 0
        with worker_context(cfg,root,used=args.provider=='ebay_used') as worker:
            worker.stop=stop;worker.http.stop=stop;ticks=0
            while not stop.is_set():
                worker.step();ticks+=1
                if args.once or args.max_ticks and ticks>=args.max_ticks:break
                stop.wait(1)
            result=worker.report();result['provider']=args.provider
            print(json.dumps(result));return int(bool(result['hold']))
    except Exception:
        print(json.dumps({'provider':args.provider,'status':'blocked','reason':'configuration_secret_lock_state_or_runtime_requires_review','automatic_state_reset':False}));return 2
    finally:
        stop.set()
        if thread:thread.join(timeout=3)
        for sig,handler in previous.items():signal.signal(sig,handler)


if __name__=='__main__':raise SystemExit(main())
