import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import threading
from services.collector.domeggook_live.runtime import FileState
from services.collector.domeggook_live.domeggook_delivery import load, atomic
from .config import load_config,SOURCES
from .runner import Worker

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--config',default=os.environ.get('KKULPICK_MARKETPLACE_CONFIG'))
    p.add_argument('--state-dir',default=os.environ.get('KKULPICK_MARKETPLACE_STATE_DIR'))
    modes=p.add_mutually_exclusive_group();modes.add_argument('--status',action='store_true')
    modes.add_argument('--once',action='store_true');modes.add_argument('--watch',action='store_true')
    p.add_argument('--source',choices=SOURCES)
    p.add_argument('--env-file',help='Explicit dotenv file; reads SERPER_API_KEY only')
    args=p.parse_args(argv)
    try:
        if args.source=='searchapi_google_shopping' and (args.once or args.watch):
            print(json.dumps({'source':args.source,'status':'retired','reason':'use_serper_google_shopping','HTTP_requests':0}));return 2
        if args.env_file:
            if args.source!='serper_google_shopping':raise ValueError('env_file_only_for_Serper')
            from .credentials import load_serper_env
            load_serper_env(args.env_file)
        if not args.config or not args.state_dir:raise ValueError('config_and_independent_state_directory_required')
        configs=load_config(args.config)
        if args.source:configs=[c for c in configs if c['source']==args.source]
        if args.source=='serper_google_shopping' and not configs:raise ValueError('Serper_source_not_configured')
        root=Path(args.state_dir).resolve()
        if not (args.once or args.watch):
            # No state creation, credential reads, workers or transports.
            reports=[]
            for cfg in configs:
                state=load(root/cfg['source']/'checkpoint.json',{})
                ledger=load(root/cfg['source']/'request_ledger.json',{'requests':[]})
                outbox=load(root/cfg['source']/'backend_outbox.json',{'entries':{}})
                counts={}
                for entry in outbox['entries'].values():counts[entry['status']]=counts.get(entry['status'],0)+1
                reports.append({'source':cfg['source'],'enabled':cfg['enabled'],'hold':state.get('hold') or ledger.get('hold'),
                    'next_cycle_at':state.get('next_cycle_at'),'next_action_at':state.get('next_action_at'),
                    'totals':state.get('totals',{}),'HTTP_attempts':len(ledger['requests']),
                    'backend_hold':outbox.get('hold'),'backend_states':counts,'HTTP_requests_this_command':0,
                    'products_success':state.get('totals',{}).get('products_success',0),
                    'products_failed':state.get('totals',{}).get('products_failed',0),
                    'products_held':state.get('totals',{}).get('products_held',0),
                    'last_collection_at':state.get('last_collection_at'),'last_success_at':state.get('last_success_at'),
                    'last_failure_at':state.get('last_failure_at'),
                    'last_lookup':load(root/cfg['source']/'last_lookup_summary.json',None)})
            print(json.dumps(reports));return 0
        stop=threading.Event();workers=[];previous={};initialization_failures=[]
        try:
            with ExitStack() as stack:
                for cfg in configs:
                    if not cfg['enabled']:continue
                    if cfg['source']=='searchapi_google_shopping':
                        initialization_failures.append({'source':cfg['source'],'hold':'retired_use_serper_google_shopping'});continue
                    # One source may be run independently alongside another.
                    try:
                        stack.enter_context(FileState(root/cfg['source']/'lock').lock())
                        workers.append(Worker(cfg,root))
                    except Exception:
                        initialization_failures.append({'source':cfg['source'],'hold':'source_initialization_or_lock_requires_review'})
                if threading.current_thread() is threading.main_thread():
                    def request_stop(*_):
                        stop.set()
                        for worker in workers:worker.stop.set()
                    for sig in (signal.SIGTERM,signal.SIGINT):
                        previous[sig]=signal.signal(sig,request_stop)
                while not stop.is_set():
                    for worker in workers:
                        if stop.is_set():break
                        try:worker.step()
                        except OSError:
                            # A storage failure stops this source; never discard
                            # the outbox or run a fresh request to hide a failed save.
                            worker.state['hold']='local_storage_failure';worker.stop.set()
                        except Exception:
                            worker.state['hold']='source_failed_review_required';worker.stop.set()
                            try:worker.save()
                            except OSError:pass
                    if not args.watch or not workers:break
                    if all(w.stop.is_set() for w in workers):break
                    stop.wait(1)
                print(json.dumps([w.report() for w in workers]+initialization_failures))
                return int(bool(initialization_failures) or any(w.state['hold'] or w.http.state.get('hold') or w.delivery.state.get('hold') for w in workers))
        finally:
            for w in workers:w.stop.set();w.close()
            for sig,handler in previous.items():signal.signal(sig,handler)
    except (ValueError,OSError,RuntimeError):
        print(json.dumps({'safe_error':'configuration_state_or_lock_requires_review'}));return 2

if __name__=='__main__':raise SystemExit(main())
