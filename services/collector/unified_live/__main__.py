"""Unified entry point. Plan/status do not fetch. Existing collectors remain usable."""
import argparse
import json
import os
import signal
import threading
from datetime import timedelta
from pathlib import Path
from services.collector.domeggook_live.domeggook_delivery import atomic,load,utcnow
from services.collector.domeggook_live.runtime import FileState
from services.collector.marketplace_live.config import stamp
from .policy import validate,grant,interval
from .used import used_interval

def emit(data):print(json.dumps(data,ensure_ascii=False,default=str))

def plan(provider,data):
    if provider=='url':
        cfg=validate(data);per_cycle=len(cfg['queries'])*cfg['max_pages_per_cycle']+cfg['max_products_per_cycle']+cfg['refresh_items_per_cycle']
        seconds=interval(cfg)
        ready=cfg['enabled'] and grant(cfg,utcnow()) and os.environ.get('COLLECTOR_RUN_APPROVED')=='yes'
        return {'provider':provider,'source':cfg['source'],'ready':ready,'effective_interval_seconds':seconds,
            'requests_per_cycle_upper_bound_without_JS_or_robots':per_cycle,'robots_and_JS_resources_count_in_budget':True,
            'requests_per_24h_budget':cfg['requests_per_24h'],'HTTP_requests_this_command':0,
            'backend_send_approved':os.environ.get('COLLECTOR_DELIVERY_APPROVED')=='yes',
            'parser':'JSONLD_then_reviewed_CSS','schedule_coverage':'bounded_not_all_catalogue',
            'reasons':[] if ready else ['disabled_or_missing_collection_storage_terms_grant_or_run_approval']}
    from services.collector.collector_ops.__main__ import config,preflight
    cfg=config(provider,data)
    result=preflight(provider,cfg)
    if provider=='ebay_used':
        source=json.loads(Path(data).read_text(encoding='utf-8-sig'));schedule=source.get('schedule',{})
        seconds,reason=used_interval(schedule)
        estimated=len(cfg['queries'])*cfg['max_pages_per_cycle']*(1+cfg['page_size'])+cfg.get('refresh_items_per_cycle',1)
        result.update(effective_interval_seconds=seconds,interval_reason=reason,estimated_max_data_requests_per_24h=estimated*86400/seconds,
            shared_ebay_daily_budget=cfg['requests_per_24h'],quota_can_delay_polls=True)
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider',choices=('url','ebay_account','ebay_used','ebay','yes24','serper','domeggook','bunjang','joongna','elevenst'),required=True)
    parser.add_argument('--config',default=os.environ.get('COLLECTOR_CONFIG'))
    parser.add_argument('--used-config',default=os.environ.get('COLLECTOR_USED_CONFIG'))
    parser.add_argument('--state-dir',default=os.environ.get('KKULPICK_STATE_DIR'))
    mode=parser.add_mutually_exclusive_group(required=True)
    for name in ('plan','status','health','register','mock','once','watch'):mode.add_argument('--'+name,action='store_true')
    parser.add_argument('--max-ticks',type=int)
    args=parser.parse_args(argv);stop=threading.Event();previous={}
    try:
        if args.max_ticks is not None and args.max_ticks<1:raise ValueError('positive_max_ticks')
        if args.mock:
            if args.provider=='ebay_account':
                from services.collector.collector_ops.mock import run_mock as existing_mock
                emit({'mode':'inprocess_mock','members':[existing_mock(p,Path(args.state_dir or '/tmp')/'account-mock') for p in ('ebay','ebay_used')],'external_HTTP_requests':0});return 0
            if args.provider=='url':
                from .mock import run_mock
                emit(run_mock(Path(args.state_dir or '/tmp')/'unified-mock-only'));return 0
            from services.collector.collector_ops.__main__ import main as existing
            return existing(['--provider',args.provider,'--mock','--state-dir',args.state_dir or '/tmp'])
        if not args.state_dir:raise ValueError('explicit_persistent_state_directory_required')
        root=Path(args.state_dir);heart=root/'unified_ops'/args.provider/'heartbeat.json'
        if args.health:
            record=load(heart,{})
            return 0 if record.get('heartbeat_at') and utcnow()-stamp(record['heartbeat_at'])<timedelta(seconds=120) else 1
        if args.status:
            emit({'provider':args.provider,'process':load(heart,None),'HTTP_requests_this_command':0,
                'real_live_success_is_not_process_health':True});return 0
        if not args.config:raise ValueError('explicit_configuration_required')
        if args.provider in ('bunjang','joongna','elevenst'):
            if args.register:raise ValueError('URL_only_registration')
            if (args.once or args.watch) and os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes':
                check={'provider':args.provider,'ready':False,'HTTP_requests_this_command':0,'reason':'legacy_live_worker_requires_separate_delivery_approval'}
                if args.once:emit(check);return 2
                for sig in (signal.SIGINT,signal.SIGTERM):previous[sig]=signal.signal(sig,lambda *_:stop.set())
                ticks=0
                while not stop.is_set():
                    atomic(heart,dict(check,heartbeat_at=utcnow().isoformat(),process_state='disabled_or_permission_wait'))
                    ticks+=1
                    if args.max_ticks and ticks>=args.max_ticks:break
                    stop.wait(1)
                return 0
            from services.collector.collector_ops.__main__ import main as existing
            mode_name='plan' if args.plan else 'once' if args.once else 'watch'
            return existing(['--provider',args.provider,'--config',args.config,'--state-dir',args.state_dir,'--'+mode_name]+(['--max-ticks',str(args.max_ticks)] if args.max_ticks else []))
        data=json.loads(Path(args.config).read_text(encoding='utf-8-sig')) if args.provider=='url' else args.config
        if args.register:
            if args.provider!='url':raise ValueError('URL_only_registration')
            from .registry import register
            emit(register(data,root));return 0
        if args.provider=='ebay_account':
            if not args.used_config:raise ValueError('used_config_required')
            checks={'ebay':plan('ebay',args.config),'ebay_used':plan('ebay_used',args.used_config)}
            check={'provider':'ebay_account','ready':any(c['ready'] for c in checks.values()),'members':checks,'HTTP_requests_this_command':0,'shared_ledger_single_writer':True}
        else:check=plan(args.provider,data)
        if args.plan:emit(check);return 0 if check['ready'] else 1
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT,signal.SIGTERM):previous[sig]=signal.signal(sig,lambda *_:stop.set())
        # Disabled workers heartbeat without touching provider state or constructing HTTP clients.
        if not check['ready']:
            if args.once:emit(check);return 2
            ticks=0
            while not stop.is_set():
                atomic(heart,dict(check,heartbeat_at=utcnow().isoformat(),process_state='disabled_or_permission_wait'))
                ticks+=1
                if args.max_ticks and ticks>=args.max_ticks:break
                stop.wait(1)
            return 0
        if args.provider=='domeggook':
            from services.collector.collector_ops.__main__ import config,start_heartbeat
            from services.collector.collector_ops.secrets import load as secrets
            from .dome import run
            cfg=config('domeggook',args.config);secrets('domeggook',backend=True)
            thread=start_heartbeat(heart,'domeggook',cfg,root,stop)
            try:emit(run(cfg,root,stop,once=args.once));return 0
            finally:stop.set();thread.join(timeout=3)
        if args.provider=='url':
            if os.environ.get('COLLECTOR_DELIVERY_APPROVED')=='yes':
                name='KKULPICK_BACKEND_TOKEN';value=os.environ.get(name,'');secret=os.environ.get(name+'_FILE')
                if secret:
                    f=Path(secret)
                    if not f.is_file() or f.stat().st_size>16384:raise ValueError('backend_secret_file_invalid')
                    stored=f.read_text(encoding='utf-8-sig').strip()
                    if value and value!=stored:raise ValueError('backend_secret_conflict')
                    value=stored
                if len(value)<32 or any(not 33<=ord(c)<=126 for c in value):raise ValueError('backend_secret_invalid')
                os.environ[name]=value
            from .engine import URLWorker
            from contextlib import contextmanager
            @contextmanager
            def context():
                with FileState(root/data['source']/'lock').lock():
                    worker=URLWorker(data,root)
                    try:yield worker
                    finally:worker.close()
        else:
            from services.collector.collector_ops.__main__ import config
            from services.collector.collector_ops.secrets import load as secrets
            from .used import open_worker
            secrets('ebay' if args.provider=='ebay_account' else args.provider,backend=os.environ.get('COLLECTOR_DELIVERY_APPROVED')=='yes')
            if args.provider=='ebay_account':
                from .account import account_context
                cfg=config('ebay',args.config);used_cfg=config('ebay_used',args.used_config)
                for name,c in (('ebay',cfg),('ebay_used',used_cfg)):
                    if not checks[name]['ready']:c['enabled']=False
                schedule=json.loads(Path(args.used_config).read_text(encoding='utf-8-sig')).get('schedule',{})
                def context():return account_context(cfg,used_cfg,root,schedule)
            else:
                cfg=config(args.provider,args.config)
                schedule=json.loads(Path(args.config).read_text(encoding='utf-8-sig')).get('schedule',{})
                def context():return open_worker(cfg,root,args.provider=='ebay_used',schedule)
        with context() as worker:
            worker.stop=stop
            if hasattr(worker.http,'stop'):worker.http.stop=stop
            ticks=0
            while not stop.is_set():
                result=worker.step();ticks+=1
                atomic(heart,dict(result,heartbeat_at=utcnow().isoformat(),process_state='held' if result.get('hold') else 'running'))
                if args.once or args.max_ticks and ticks>=args.max_ticks:break
                stop.wait(1)
            emit(result);return int(bool(result.get('hold')))
    except Exception:
        # Never serialize exception text, settings, URLs or credentials.
        emit({'provider':args.provider,'status':'blocked','reason':'configuration_permission_lock_or_runtime_review_required','automatic_state_reset':False});return 2
    finally:
        stop.set()
        for sig,handler in previous.items():signal.signal(sig,handler)

if __name__=='__main__':raise SystemExit(main())
