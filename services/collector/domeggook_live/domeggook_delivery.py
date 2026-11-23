"""Permission-gated durable HTTP outbox; replay always keeps the exact observation key/body."""
import copy,hashlib,json,os,uuid
from pathlib import Path
from datetime import datetime,timezone,timedelta
from .domeggook_backend import prepare_observation,validate_body,safe_ack,synthetic_proven,FIELD_MAP,HTTPBackendTransport
from .domeggook_operations import grant_valid
from .progress import replace_with_retry

def utcnow():return datetime.now(timezone.utc)
def parsed(value):return datetime.fromisoformat(value.replace('Z','+00:00')) if value else None
def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,allow_nan=False);stream.flush();os.fsync(stream.fileno())
    replace_with_retry(temp,path)
def load(path,default):return json.loads(path.read_text(encoding='utf-8')) if path.exists() else copy.deepcopy(default)
def digest(body):return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

class DeliveryPipeline:
    def __init__(self,cfg,root,transport=None,clock=utcnow):
        self.cfg=cfg;self.settings=cfg.get('backend_delivery',{});self.clock=clock;self.path=Path(root)/'backend_outbox.json'
        self.test=self.settings.get('mode')=='synthetic_test';self.transport=transport;self.skipped=0
        self.enabled=cfg.get('backend_enabled') is True and cfg.get('backend_owner_approved') is True
        grants=cfg.get('storage_grants',{})
        self.ready=self.enabled and (self.test or cfg.get('price_semantics_confirmed') is True and all(
            grant_valid(grants,f,clock()) and grants[f].get('reuse') is True for f in ('product_name','unit_price','currency','availability','product_url')))
        self.state=load(self.path,{'version':1,'run_id':str(uuid.uuid4()),'entries':{},'hold':None,'totals':{}}) if self.enabled else {'entries':{},'hold':None,'totals':{}}
        if self.enabled:
            if self.test and self.settings.get('synthetic_test_approved') is not True:raise PermissionError('isolated_synthetic_test_approval_required')
            if not self.test and self.settings.get('mode')!='live_authorized':raise PermissionError('explicit_delivery_mode_required')
            if self.settings.get('selected_domain') not in ('product','food') or self.settings.get('condition') not in ('new','used'):raise ValueError('explicit_domain_condition_required')
            if self.settings.get('run_id'):
                run=str(uuid.UUID(self.settings['run_id']))
                if self.path.exists() and run!=self.state['run_id']:raise ValueError('outbox_run_id_cannot_change')
                self.state['run_id']=run
            if self.transport is None and self.ready:
                token=os.environ.get('KKULPICK_BACKEND_TOKEN','')
                self.transport=HTTPBackendTransport(self.settings.get('base_url',''),token,approved_loopback_test=self.test)
            self.prune();self.save()
    def count(self,key,n=1):self.state['totals'][key]=self.state['totals'].get(key,0)+n
    def save(self):atomic(self.path,self.state)
    def permitted_body(self,entry):
        if self.test:
            body=entry['body'];return body['source']=='domeggook_test' and body['source_listing_id'].startswith('TEST-') and body.get('url','').startswith('https://store.example.test/')
        if not self.cfg.get('price_semantics_confirmed'):return False
        grants=self.cfg.get('storage_grants',{})
        if not all(grant_valid(grants,f,self.clock()) and grants[f].get('reuse') is True for f in ('product_name','unit_price','currency','availability','product_url')):return False
        grants=self.cfg.get('storage_grants',{})
        return all(grant_valid(grants,FIELD_MAP[k],self.clock()) and grants[FIELD_MAP[k]].get('reuse') is True
                   for k in entry['body']['field_presence'] if k in FIELD_MAP and entry['body'].get(k) is not None)
    def prune(self):
        for entry in self.state['entries'].values():
            if 'body' in entry and not self.permitted_body(entry):entry.pop('body');entry['status']='revoked';self.count('revoked')
    def pending_count(self):return sum('body' in e for e in self.state['entries'].values())
    def backpressure(self):return self.enabled and self.pending_count()>=self.settings.get('max_pending',5000)
    def stage(self,row):
        if not self.enabled:self.skipped+=1;return {'status':'disabled'}
        if not self.ready:self.count('permission_blocked');return {'status':'permission_blocked'}
        try:body=prepare_observation(row,self.cfg,selected_domain=self.settings['selected_domain'],condition=self.settings['condition'])
        except PermissionError:self.count('permission_blocked');return {'status':'permission_blocked'}
        key=body['observation_key'];sha=digest(body);previous=self.state['entries'].get(key)
        if previous:
            if previous['sha256']!=sha:raise ValueError('immutable_outbox_payload_conflict')
            return {'status':previous['status'],'duplicate':True}
        # Revocation of content invalidates older pending bodies; never rewrite an idempotency payload.
        if row.get('detail_content_license_usable') is not True:
            for entry in self.state['entries'].values():
                old=entry.get('body')
                if old and old['source_listing_id']==body['source_listing_id'] and old.get('description'):
                    entry.pop('body');entry['status']='revoked';self.count('revoked')
        if self.backpressure():return {'status':'backpressure_needs_reobserve'}
        entry={'body':body,'sha256':sha,'status':'pending','attempts':0,'created_at':self.clock().isoformat(),
               'source':body['source'],'source_listing_id':body['source_listing_id'],'variant_key':body['variant_key']}
        self.state['entries'][key]=entry;self.count('staged');self.save()
        return {'status':'pending','observation_key':key}
    def flush(self,stop=None):
        if not self.enabled:return self.report()
        self.prune()
        if not self.ready:self.save();return self.report()
        if self.state['hold']:self.save();return self.report()
        sent=0
        for key,entry in self.state['entries'].items():
            if stop is not None and stop.is_set():break
            if sent>=self.settings.get('max_requests_per_flush',10):break
            if entry['status'] not in ('pending','retry_wait','sending') or 'body' not in entry:continue
            if entry.get('next_attempt_at') and parsed(entry['next_attempt_at'])>self.clock():continue
            if entry['attempts']>=self.settings.get('max_attempts',5):entry['status']='exhausted';continue
            validate_body(entry['body'],self.cfg)
            if digest(entry['body'])!=entry['sha256']:raise ValueError('persisted_body_changed')
            entry.update(status='sending',attempts=entry['attempts']+1);self.save()
            try:code,ack=self.transport('/internal/v2/crawl-runs/'+self.state['run_id']+'/observations',copy.deepcopy(entry['body']))
            except Exception:code,ack=0,{}  # No raw exception/URL/token is serialized.
            sent+=1;self.count('HTTP_attempts');ack=safe_ack(ack);entry['last_status']=code
            if code in (200,201) and ack.get('state'):
                entry.update(status='quarantine' if ack['state']=='quarantine' else 'delivered',ack=ack,delivered_at=self.clock().isoformat())
                entry.pop('body');entry.pop('next_attempt_at',None)
                self.count('ack_'+ack['state']);self.count('change_'+ack.get('change_kind','unknown'))
            elif code in (401,403,409) or 300<=code<400:
                entry['status']='held';self.state['hold']='backend_auth_identity_or_redirect_review_required';self.count('held')
            elif code in (0,408,425,429,500,502,503,504) or code in (200,201):
                entry['status']='retry_wait' if entry['attempts']<self.settings.get('max_attempts',5) else 'exhausted'
                delay=min(300,self.settings.get('retry_base_seconds',5)*2**(entry['attempts']-1))
                entry['next_attempt_at']=(self.clock()+timedelta(seconds=delay)).isoformat();self.count('transient_failures')
            else:entry['status']='rejected';entry.pop('body');self.count('rejected')
            self.save()
            if self.state['hold']:break
        self.save();return self.report()
    def retry_delay(self):
        if not self.ready or self.state['hold']:return 30
        delays=[max(1,(parsed(e['next_attempt_at'])-self.clock()).total_seconds()) if e.get('next_attempt_at') else 1
                for e in self.state['entries'].values() if e['status'] in ('pending','retry_wait','sending') and 'body' in e]
        return min(delays,default=30)

    def report(self):return {'enabled':self.enabled,'ready':self.ready,'mode':self.settings.get('mode','disabled'),'pending':self.pending_count(),
        'hold':self.state['hold'],'skipped_disabled':self.skipped,'totals':copy.deepcopy(self.state['totals']),
        'states':{name:sum(e['status']==name for e in self.state['entries'].values()) for name in ('pending','retry_wait','delivered','quarantine','held','exhausted','rejected','revoked')}}
    def close(self):
        if self.transport and hasattr(self.transport,'close'):self.transport.close()
