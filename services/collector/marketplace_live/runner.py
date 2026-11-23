"""Cooperative independent workers: one bounded provider action per tick."""
import hashlib
import json
import threading
import uuid
from datetime import timedelta
from pathlib import Path
from services.collector.domeggook_live.domeggook_delivery import atomic, load, utcnow
from .config import rights, stamp
from .http import ProviderHTTP, ProviderError, Pause
from .delivery import Outbox
from .adapters import Adapter

def context(cfg):
    keys=('source','queries','page_size','marketplace_id','gl','hl')
    return hashlib.sha256(json.dumps({k:cfg.get(k) for k in keys},sort_keys=True).encode()).hexdigest()

class Worker:
    def __init__(self,cfg,root,*,http=None,delivery=None,adapter=None,clock=utcnow):
        self.cfg=cfg;self.root=Path(root)/cfg['source'];self.path=self.root/'checkpoint.json';self.clock=clock
        self.stop=threading.Event()
        self.state=load(self.path,{'version':1,'source':cfg['source'],'context':context(cfg),'tasks':[],
            'cycle':0,'budget_epoch':str(uuid.uuid4()),'next_cycle_at':None,'next_action_at':None,
            'inflight':False,'hold':None,'totals':{},'ledger_size':0,'outbox_seen':False,
            'seen_ids':[],'seen_offer_hashes':[]})
        if self.state.get('version')!=1 or self.state.get('source')!=cfg['source'] or self.state.get('context')!=context(cfg):
            raise ValueError('checkpoint_context_mismatch_no_reset')
        if self.state.get('outbox_seen') and not (self.root/'backend_outbox.json').exists() and delivery is None:
            raise ValueError('missing_existing_outbox_no_reset')
        self.http=http or ProviderHTTP(cfg,self.root,clock)
        self.http.stop=self.stop
        if self.state['ledger_size']>len(self.http.state['requests']):raise ValueError('missing_request_history_no_reset')
        self.delivery=delivery or Outbox(cfg,self.root,clock=clock)
        self.adapter=adapter or Adapter(cfg,self.http)
        if self.state['inflight'] and self.state['tasks']:
            task=self.state['tasks'][0];task['attempts']+=1
            self.state['inflight']=False
            # Successful HTTP can still have lost its response before staging.
            # Keep the task/IDs; defer a fresh request and never claim success.
            due=clock()+timedelta(seconds=cfg['cycle_interval_seconds'])
            self.state['next_action_at']=due.isoformat();self.count('interrupted_tasks_deferred');self.save()

    def count(self,name,n=1):self.state['totals'][name]=self.state['totals'].get(name,0)+n
    def save(self):
        self.state['ledger_size']=len(self.http.state['requests'])
        self.state['outbox_seen']=self.delivery.path.exists()
        atomic(self.path,self.state)

    def task(self,kind,**kwargs):return dict(kind=kind,task_id=str(uuid.uuid4()),attempts=0,**kwargs)

    def accept(self,raw):
        self.count('products_seen');self.state['last_collection_at']=self.clock().isoformat()
        try:normalized=self.adapter.normalize(raw,self.clock().isoformat())
        except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError):
            self.count('normalization_rejected');self.count('products_failed')
            self.state['last_failure_at']=self.clock().isoformat();return
        if normalized['observation'] is None:
            self.count('incomplete_native_fields');self.count('products_held')
            for field in normalized['missing_fields']:self.count('missing_'+field)
            return
        if not isinstance(normalized.get('seller'),str) or not normalized['seller'].strip():
            self.count('missing_seller');self.count('products_held');return
        staged=self.delivery.stage(normalized)
        self.count('backend_stage_'+staged['status'])
        if staged['status']=='backpressure_needs_reobserve':raise Pause('backend_backpressure',self.clock()+timedelta(seconds=30))
        if staged['status'] in ('pending','delivered','quarantine'):
            self.count('products_success');self.state['last_success_at']=self.clock().isoformat()
        else:self.count('products_held')
        self.count('normalized')
        # Seller is deliberately retained only in this RAM result. Observation v2
        # forbids a seller field; adding it requires the backend owner's contract.
        if normalized.get('seller') is not None:self.count('seller_present_in_memory_only')

    def execute(self,task):
        if task['kind']=='detail':
            self.accept(self.adapter.detail(task['identity']));return []
        rows,more=self.adapter.search(self.cfg['queries'][task['query_index']],task['page'])
        self.state['last_collection_at']=self.clock().isoformat()
        additional=[];seen=set()
        for row in rows:
            if self.cfg['source'] in ('searchapi_google_shopping','serper_google_shopping'):
                native=(row.get('productId'),row.get('source'),row.get('link')) if self.cfg['source']=='serper_google_shopping' else (row.get('product_id'),row.get('seller'),row.get('link'))
                fingerprint=hashlib.sha256(json.dumps(native,sort_keys=True).encode()).hexdigest()
                if fingerprint in self.state['seen_offer_hashes']:
                    self.count('duplicate_search_offers');continue
                self.accept(row);self.state['seen_offer_hashes'].append(fingerprint);continue
            ident=row.get('itemId')
            if ident is None or isinstance(ident,bool):raise ProviderError('native_identity_missing')
            ident=str(ident)
            if not ident or len(ident)>180:raise ProviderError('native_identity_invalid')
            import re
            if self.cfg['source']=='yes24_api' and not ident.isdigit():raise ProviderError('native_identity_invalid')
            if self.cfg['source']=='ebay_browse' and not re.fullmatch(r'v1\|\d+\|\d+',ident):raise ProviderError('native_identity_invalid')
            if ident in seen or ident in self.state['seen_ids']:
                self.count('duplicate_search_IDs');continue
            seen.add(ident)
            # Search and detail both pass through the same normalizer. Search
            # projections are RAM-only; complete detail is the delivered event.
            try:self.adapter.normalize(row,self.clock().isoformat())
            except (ValueError,TypeError,KeyError,ArithmeticError):pass
            additional.append(self.task('detail',identity=ident))
        if more and task['page']<self.cfg['max_pages_per_cycle']:
            additional.append(self.task('search',query_index=task['query_index'],page=task['page']+1))
        return additional

    def step(self):
        current=self.clock()
        if not self.cfg['enabled'] or self.stop.is_set():return self.report()
        self.delivery.flush(stop=self.stop)
        if self.state['hold']:return self.report()
        if not rights(self.cfg,current):
            self.state['hold']='provider_permission_required';self.save();return self.report()
        if self.delivery.backpressure():return self.report()
        for name in ('next_action_at',):
            if self.state.get(name) and stamp(self.state[name])>current:return self.report()
        if not self.state['tasks']:
            if self.state.get('next_cycle_at') and stamp(self.state['next_cycle_at'])>current:return self.report()
            self.state['cycle']+=1;self.state['budget_epoch']=str(uuid.uuid4())
            self.state['seen_ids']=[];self.state['seen_offer_hashes']=[]
            self.state['tasks']=[self.task('search',query_index=i,page=1) for i in range(len(self.cfg['queries']))]
        task=self.state['tasks'][0]
        if task['attempts']>=self.cfg['max_task_attempts']:
            self.state['tasks'].pop(0);self.count('tasks_exhausted');self.complete_if_empty();self.save();return self.report()
        self.http.cycle_id=self.state['budget_epoch'];self.http.task_id=task['task_id']
        self.state['inflight']=True;self.save()
        try:
            additional=self.execute(task)
        except Pause as exc:
            if str(exc) not in ('request_interval_wait','provider_budget_wait','provider_deadline_wait','cycle_budget_wait','backend_backpressure','worker_stopping'):
                task['attempts']+=1
                self.state['last_failure_at']=self.clock().isoformat();self.count('provider_failed_actions')
            self.state['next_action_at']=exc.until.isoformat()
            if str(exc)=='cycle_budget_wait':self.state['budget_epoch']=str(uuid.uuid4())
            self.count('wait_'+str(exc))
        except ProviderError as exc:
            self.state['hold']=str(exc);self.count('provider_errors');self.state['last_failure_at']=self.clock().isoformat()
        except (ValueError,TypeError,KeyError,RuntimeError,ArithmeticError):
            self.state['hold']='provider_schema_or_credentials_review_required';self.count('provider_errors');self.state['last_failure_at']=self.clock().isoformat()
        else:
            self.state['tasks'].pop(0)
            # Deduplicate detail tasks across overlapping search pages.
            pending={(t['kind'],t.get('identity')) for t in self.state['tasks'] if t['kind']=='detail'}
            for candidate in additional:
                ident=(candidate['kind'],candidate.get('identity'))
                if candidate['kind']=='detail' and ident in pending:continue
                self.state['tasks'].append(candidate);pending.add(ident)
                if candidate['kind']=='detail':self.state['seen_ids'].append(candidate['identity'])
            self.state['next_action_at']=None;self.count('tasks_completed');self.complete_if_empty()
        self.state['inflight']=False;self.save()
        self.delivery.flush(stop=self.stop)
        return self.report()

    def complete_if_empty(self):
        if not self.state['tasks']:
            self.state['next_cycle_at']=(self.clock()+timedelta(seconds=self.cfg['cycle_interval_seconds'])).isoformat()
            self.count('cycles_completed')

    def report(self):return {'source':self.cfg['source'],'enabled':self.cfg['enabled'],'cycle':self.state['cycle'],
        'hold':self.state['hold'] or self.http.state.get('hold'),'next_cycle_at':self.state['next_cycle_at'],
        'next_action_at':self.state['next_action_at'],'pending_tasks':len(self.state['tasks']),
        'HTTP_attempts':len(self.http.state['requests']),'totals':dict(self.state['totals']),
        'products_success':self.state['totals'].get('products_success',0),
        'products_failed':self.state['totals'].get('products_failed',0),'products_held':self.state['totals'].get('products_held',0),
        'last_collection_at':self.state.get('last_collection_at'),'last_success_at':self.state.get('last_success_at'),
        'last_failure_at':self.state.get('last_failure_at'),
        'backend':self.delivery.report()}

    def close(self):self.http.close();self.delivery.close()
