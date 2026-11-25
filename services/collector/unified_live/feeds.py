"""Opt-in scheduled merchant feeds using retained native converters and v2 outbox."""
import argparse
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import signal
import threading
from services.collector.domeggook_live.domeggook_delivery import atomic,load,utcnow
from services.collector.domeggook_live.runtime import FileState
from services.collector.marketplace_live.config import stamp
from services.collector.real_feed_collectors.real_collectors.core import SOURCES,rows,convert,details
from .policy import validate as validate_URL,grant
from .backend import ApprovedOutbox
from .changes import ChangeDelivery,digest
from .transport import SafeHTTP,Wait
from .public_sources import POLICIES
from .food import evidence
from services.collector.marketplace_live.normalize import validate_body
from .parser import plain
from .changes import rekey

def validate(cfg):
    source=cfg.get('source')
    if source not in SOURCES or source not in POLICIES:raise ValueError('reviewed_feed_source_required')
    # Reuse URL config bounds without changing its html_* namespace rule.
    clone={k:v for k,v in cfg.items() if k not in ('merchant_name','merchant_reference','food_policy')}
    clone.update(source='html_feed_validation',base_url='https://'+POLICIES[source]['host']+'/',
        search_url_template='https://'+POLICIES[source]['host']+'/?q={query}',queries=['feed'],mode='general',selectors={},render_javascript=False,evidence_storage=False)
    validate_URL(clone)
    if cfg.get('food_policy','hold_until_contract')!='hold_until_contract':raise ValueError('food_contract_gate_required')
    if cfg.get('merchant_name') is not None and not isinstance(cfg['merchant_name'],str):raise ValueError('merchant_name_required')
    if cfg.get('merchant_reference') is not None and not isinstance(cfg['merchant_reference'],str):raise ValueError('merchant_reference_required')
    if cfg.get('provider_min_interval_seconds',7200)<7200:raise ValueError('feed_minimum_7200_seconds')
    if cfg.get('allowed_product_hosts')!=[POLICIES[source]['host']]:raise ValueError('fixed_feed_merchant_host_required')
    if source=='yappy_kids' and (cfg['requests_per_24h']>2000 or cfg['requests_per_hour']>600):raise ValueError('shared_IP_quota_headroom_required')
    return cfg

class FeedHTTP(SafeHTTP):
    def permitted(self,target):
        return target in (POLICIES[self.cfg['source']]['feed'],'https://'+self.host+'/robots.txt') and super().permitted(target)

class FeedWorker:
    def __init__(self,cfg,root,*,http=None,delivery=None,clock=utcnow):
        self.cfg=validate(cfg);self.clock=clock;self.stop=threading.Event();self.root=Path(root)/cfg['source'];self.path=self.root/'feed_checkpoint.json'
        self.state=load(self.path,{'version':1,'source':cfg['source'],'inflight':False,'next_cycle_at':None,'next_action_at':None,
            'hold':None,'cursor':0,'totals':{},'ledger_size':0,'outbox_seen':False})
        if self.state.get('version')!=1 or self.state.get('source')!=cfg['source']:raise ValueError('feed_state_mismatch_no_reset')
        if self.state['outbox_seen'] and not (self.root/'backend_outbox.json').exists() and delivery is None:raise ValueError('missing_feed_outbox_no_reset')
        self.http=http or FeedHTTP(dict(cfg,base_url='https://'+POLICIES[cfg['source']]['host']+'/'),self.root,clock)
        if self.state['ledger_size']>len(self.http.state['requests']):raise ValueError('missing_feed_request_history')
        self.delivery=ChangeDelivery(delivery or ApprovedOutbox(cfg,self.root,clock=clock),self.root)
        if self.state['inflight']:self.state['hold']='interrupted_feed_requires_review';self.state['inflight']=False;self.save()
    def count(self,k,n=1):self.state['totals'][k]=self.state['totals'].get(k,0)+n
    def save(self):
        self.state['ledger_size']=len(self.http.state['requests']);self.state['outbox_seen']=self.delivery.path.exists();atomic(self.path,self.state)
    def step(self):
        if not self.cfg['enabled'] or self.stop.is_set():return self.report()
        if not grant(self.cfg,self.clock()):self.state['hold']='feed_storage_reuse_permission_required';self.save();return self.report()
        self.delivery.flush(stop=self.stop)
        if self.state['hold'] or self.http.state.get('hold'):return self.report()
        for k in ('next_action_at','next_cycle_at'):
            if self.state.get(k) and stamp(self.state[k])>self.clock():return self.report()
        self.state['inflight']=True;self.save()
        try:
            code,text=self.http.fetch(POLICIES[self.cfg['source']]['feed'])
            if code!=200:raise Wait('feed_not_found_review',hold=True)
            native=list(rows(text.encode()))
            if len(native)>20000:raise Wait('feed_row_limit_review',hold=True)
            if self.state.get('last_feed_rows',0)>0 and not native:raise Wait('feed_structure_changed_review',hold=True)
            current_hash=hashlib.sha256(text.encode()).hexdigest()
            cursor=self.state['cursor'] if current_hash==self.state.get('feed_hash') else 0
            chosen=native[cursor:cursor+self.cfg['max_products_per_cycle']]
            consumed=0
            for raw in chosen:
                if self.stop.is_set():break
                consumed+=1
                self.count('products_seen');self.state['last_collection_at']=self.clock().isoformat()
                try:
                    body=convert(self.cfg['source'],raw,self.clock().isoformat());validate_body(body,self.cfg)
                except (ValueError,TypeError,KeyError,ArithmeticError):self.count('products_held');self.count('native_fields_or_condition_review');continue
                metadata=details(body,raw)
                from .matching import provider_profile
                metadata['matching_profile']=provider_profile(raw,self.cfg['source'],body['url'])
                ev=evidence({'name':body['name'],'category':metadata.get('category') or '', 'description':metadata.get('description')},
                    source=body['source'],url=body['url'],at=body['observed_at'])
                if ev['food_detected'] or ev['ingredients_raw'] or ev['allergens_declared'] is not None or any(s in str(metadata.get('category') or '').lower() for s in ('food','식품','음료')):
                    self.count('products_held');self.count('food_contract_required');continue
                if not self.cfg.get('merchant_name') or not self.cfg.get('merchant_reference'):
                    self.count('products_held');self.count('merchant_publisher_evidence_required');continue
                if isinstance(metadata.get('description'),str) and 'description_storage' in self.cfg['rights']['allowed_uses']:
                    body['description']=plain(metadata['description']);body['field_presence'].append('description');rekey(body);validate_body(body,self.cfg)
                key=digest([body['source'],body['source_listing_id'],body['variant_key']]);known=self.state.setdefault('known',{})
                meta_hash=digest({k:v for k,v in metadata.items() if k not in ('observation_key','observed_at')});content_hash=digest({k:v for k,v in body.items() if k not in ('observation_key','observed_at')})
                previous=known.get(key,{})
                if key in known or len(known)<self.cfg['max_tracked_items']:
                    changed=previous.get('metadata_hash')!=meta_hash or previous.get('content_hash')!=content_hash
                    if previous and previous.get('metadata_hash')!=meta_hash:self.count('metadata_change_contract_review')
                    known[key]={'first_seen_at':previous.get('first_seen_at',body['observed_at']),'last_checked_at':body['observed_at'],
                        'last_changed_at':body['observed_at'] if changed else previous['last_changed_at'],
                        'metadata_hash':meta_hash,'content_hash':content_hash,'country':self.cfg.get('country'),
                        'seller':self.cfg['merchant_name'],'seller_evidence':self.cfg['merchant_reference'],'is_synthetic':False}
                else:self.count('tracking_capacity_limited')
                result=self.delivery.stage({'observation':body,'seller':self.cfg['merchant_name'],'metadata':metadata})
                self.count('stage_'+result['status'])
                if result['status'] in ('pending','delivered'):self.count('products_success');self.state['last_success_at']=self.clock().isoformat()
                elif result['status']!='unchanged_skipped':self.count('products_held')
            self.state.update(cursor=0 if cursor+consumed>=len(native) else cursor+consumed,feed_hash=current_hash,last_feed_rows=len(native),attempts=0,
                coverage_limited=len(native)>self.cfg['max_products_per_cycle'],next_action_at=None,
                next_cycle_at=(self.clock()+timedelta(seconds=max(7200,self.cfg.get('provider_min_interval_seconds',7200)))).isoformat())
        except Wait as exc:
            if exc.hold:self.state['hold']=str(exc)
            else:
                if str(exc) not in ('rate_wait','budget_wait','request_wait','robots_crawl_delay','robots_request_rate'):
                    self.state['attempts']=self.state.get('attempts',0)+1
                if self.state.get('attempts',0)>=self.cfg['max_attempts']:self.state['hold']='feed_retry_exhausted_review'
                self.state['next_action_at']=max(exc.until or self.clock(),self.clock()+timedelta(seconds=min(3600,5*2**self.state.get('attempts',0)))).isoformat()
            self.count('HTTP_wait_or_failure');self.state['last_failure_at']=self.clock().isoformat()
        except (ValueError,TypeError,KeyError,ArithmeticError):
            self.state['hold']='feed_schema_review';self.count('products_failed');self.state['last_failure_at']=self.clock().isoformat()
        self.state['inflight']=False;self.save();self.delivery.flush(stop=self.stop);return self.report()
    def report(self):return {'source':self.cfg['source'],'configured_enabled':self.cfg['enabled'],'hold':self.state['hold'] or self.http.state.get('hold'),
        'last_collection_at':self.state.get('last_collection_at'),'last_success_at':self.state.get('last_success_at'),'last_failure_at':self.state.get('last_failure_at'),
        'next_cycle_at':self.state['next_cycle_at'],'cursor':self.state['cursor'],'coverage_limited':self.state.get('coverage_limited'),
        'totals':self.state['totals'],'content_changes':self.delivery.data['totals'],'backend':self.delivery.report(),
        'quantity_semantics':'not_inferred_from_availability; no_exact_quantity_claim'}
    def close(self):self.stop.set();self.http.close();self.delivery.close()

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--state-dir',required=True)
    m=p.add_mutually_exclusive_group(required=True)
    for name in ('plan','status','health','once','watch'):m.add_argument('--'+name,action='store_true')
    p.add_argument('--max-ticks',type=int);a=p.parse_args(argv);stop=threading.Event();prior={}
    try:
        cfg=validate(load(Path(a.config),{}));root=Path(a.state_dir);heart=root/cfg['source']/'heartbeat.json'
        if a.health:
            h=load(heart,{})
            return 0 if h.get('heartbeat_at') and utcnow()-stamp(h['heartbeat_at'])<timedelta(seconds=120) else 1
        if a.status:print(json.dumps(load(heart,{})));return 0
        ready=cfg['enabled'] and grant(cfg,utcnow()) and os.environ.get('COLLECTOR_RUN_APPROVED')=='yes'
        check={'source':cfg['source'],'ready':ready,'HTTP_requests_this_command':0,'minimum_interval_seconds':7200}
        if a.plan:print(json.dumps(check));return int(not ready)
        if ready and os.environ.get('COLLECTOR_DELIVERY_APPROVED')=='yes':
            from .backend import load_backend_token
            load_backend_token()
        for sig in (signal.SIGINT,signal.SIGTERM):prior[sig]=signal.signal(sig,lambda *_:stop.set())
        with FileState(root/cfg['source']/'lock').lock():
            worker=FeedWorker(cfg,root) if ready else None;ticks=0
            if worker:worker.stop=stop
            try:
                while not stop.is_set():
                    result=worker.step() if worker else dict(check,process_state='disabled_or_permission_wait')
                    atomic(heart,dict(result,heartbeat_at=utcnow().isoformat()));ticks+=1
                    if a.once or a.max_ticks and ticks>=a.max_ticks:break
                    stop.wait(1)
                print(json.dumps(result));return 0
            finally:
                if worker:worker.close()
    except Exception:
        print(json.dumps({'status':'blocked','reason':'feed_configuration_state_or_permission_review'}));return 2
    finally:
        for sig,handler in prior.items():signal.signal(sig,handler)

if __name__=='__main__':raise SystemExit(main())
