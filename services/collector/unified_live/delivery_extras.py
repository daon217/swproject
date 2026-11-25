"""Durable extension and unchanged check queues; exact backend-test b51ffdc contract.
No SQL or provider request is performed here. Separate event keys and ACK states.
"""
import copy
from datetime import timedelta
from services.collector.domeggook_live.domeggook_delivery import atomic,load,parsed
from services.collector.collector_ops.delivery_contract import ListingExtension,catalog_review
from .changes import digest

MP=('brand','manufacturer','model_name','model_number','mpn','identifiers','image_url','image_urls','color','size','options','category')
def extension(normalized,synthetic=False):
    body=normalized['observation'];meta=normalized.get('metadata') or {}
    native=meta.get('matching_profile') or {};mp={k:copy.deepcopy(native[k]) for k in MP if native.get(k) not in (None,'',[],{})}
    seller=normalized.get('seller')
    if isinstance(seller,str) and seller.strip():mp['seller_name']=seller
    if isinstance(meta.get('seller_id'),str):mp['seller_id']=meta['seller_id']
    for k in ('brand','manufacturer','category','image_url'):
        if k not in mp and meta.get(k):mp[k]=meta[k]
    if mp:mp['exact_match_confirmed']=False
    fe=normalized.get('food_evidence');food=None
    if isinstance(fe,dict) and body['selected_domain']=='food':
        food={k:fe[k] for k in ('ingredients_raw','allergen_notice_raw','cross_contact_raw') if isinstance(fe.get(k),str) and fe[k]}
        ingredients=fe.get('ingredients_normalized') or []
        names=[v['name'] for v in ingredients if isinstance(v,dict) and v.get('name')]
        if names:food['ingredients']=names
        if isinstance(fe.get('allergens_declared'),list):food['allergens_declared']=[{'soy':'soybean','sulfites':'sulfite'}.get(v,v) for v in fe['allergens_declared']]
        food['evidence_status']=fe.get('allergen_status') if fe.get('allergen_status') in ('reported','negative_claim_unverified','conflicting','image_only','ocr_unverified') else 'not_reported'
    if not mp and food is None:return None
    out={k:body[k] for k in ('source','source_listing_id','variant_key','observed_at')}
    out.update(schema_version='listing-extension-v1',product_url=body.get('url'),is_synthetic=synthetic)
    if mp:out['matching_profile']=mp
    if food is not None:out['food_evidence']=food
    out['observation_key']='extension:'+digest(out)
    ListingExtension.model_validate(out)
    return out

class Extras:
    def __init__(self,owner):
        self.owner=owner;self.box=owner.box;self.path=owner.path.parent/'delivery_extras.json'
        self.enabled=not self.box.state.get('synthetic_only') or getattr(self.box,'cfg',{}).get('test_extensions_enabled') is True
        self.data=load(self.path,{'version':1,'source':self.box.source,'extensions':{},'checks':{},'totals':{}}) if self.enabled else {'extensions':{},'checks':{},'totals':{}}
        if self.enabled and (self.data.get('version')!=1 or self.data.get('source')!=self.box.source):raise ValueError('auxiliary_state_mismatch_no_reset')
        latest=self.data.setdefault('latest_extensions',{})
        if not latest:
            for key,e in self.data['extensions'].items():
                b=e.get('body') or {}
                if all(b.get(k) for k in ('source','source_listing_id','variant_key')):
                    latest[digest([b['source'],b['source_listing_id'],b['variant_key']])]=key
    def save(self):
        if self.enabled:atomic(self.path,self.data)
    def count(self,k):self.data['totals'][k]=self.data['totals'].get(k,0)+1
    def licensed_matching_fields(self):
        if self.box.source!='domeggook':return None
        from services.collector.domeggook_live.domeggook_operations import grant_valid
        grants=self.box.cfg.get('storage_grants',{})
        def allowed(field):
            try:return grant_valid(grants,field,self.box.clock()) and grants[field].get('reuse') is True
            except (ValueError,TypeError,KeyError):return False
        if allowed('matching_profile'):return None
        return {field for field in MP+('seller_name','seller_id') if allowed(field)}
    def stage(self,n,result):
        if not self.enabled:return
        body=n['observation'];ident=digest([body['source'],body['source_listing_id'],body['variant_key']])
        if result['status']=='unchanged_skipped' and all(body.get(k) is not None for k in ('price','currency','availability')):
            # Coalesce unsent checks by identity, preserving full fresh body for mismatch recovery.
            self.data['checks'][ident]={'body':copy.deepcopy(body),'observation_dependency':result['observation_key'],'attempts':0}
        if n.get('food_evidence') and (not self.box.cfg.get('evidence_storage') or 'evidence_storage' not in self.box.cfg.get('rights',{}).get('allowed_uses',[])):
            self.count('food_evidence_permission_held');self.save();return
        try:ext=extension(n,bool(self.box.state.get('synthetic_only') or (n.get('metadata') or {}).get('synthetic')))
        except (ValueError,TypeError,KeyError):self.count('extension_validation_held');self.save();return
        if ext:
            allowed=self.licensed_matching_fields()
            if allowed is not None and ext.get('matching_profile'):
                ext['matching_profile']={k:v for k,v in ext['matching_profile'].items() if k in allowed or k=='exact_match_confirmed'}
                if set(ext['matching_profile'])<={'exact_match_confirmed'}:ext.pop('matching_profile')
                if not ext.get('matching_profile') and not ext.get('food_evidence'):self.save();return
                ext.pop('observation_key');ext['observation_key']='extension:'+digest(ext)
            signature=digest({k:v for k,v in ext.items() if k not in ('observed_at','observation_key')})
            latest=self.data['extensions'].get(self.data['latest_extensions'].get(ident))
            if latest and latest['signature']==signature and latest['status']=='pending' and latest['attempts']==0:
                previous=self.box.state['entries'].get(latest['dependency'],{})
                dependency=result.get('observation_key') or body['observation_key']
                if previous.get('status') in ('quarantine','rejected') and dependency!=latest['dependency']:
                    # Nothing was sent: associate the immutable extension with the corrected,
                    # validated observation for exactly the same source/listing/variant.
                    latest['dependency']=dependency;self.count('extension_dependency_recovered')
            if not latest or latest['signature']!=signature:
                if len(self.data['extensions'])>=100000:self.count('extension_capacity_held')
                else:
                    self.data['extensions'][ext['observation_key']]={'signature':signature,'body':ext,'dependency':result.get('observation_key') or body['observation_key'],'status':'pending','attempts':0}
                    self.data['latest_extensions'][ident]=ext['observation_key']
        self.save()
    def permitted(self,body):
        # Same time-sensitive storage/reuse checks as the observation queue.
        return self.box.ready and self.box.permitted_body({'body':body}) and catalog_review(body,getattr(self.box,'cfg',{})) is None
    def flush(self,stop=None):
        if not self.enabled or self.box.state.get('hold') or stop is not None and stop.is_set():return
        import os
        if os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes' or self.box.transport is None:return
        if not self.box.state.get('synthetic_only') and len(os.environ.get('KKULPICK_BACKEND_TOKEN',''))<32:return
        if self.box.state.get('not_before') and parsed(self.box.state['not_before'])>self.box.clock():return
        due=getattr(self.box.transport,'retry_not_before',None)
        if due and due>self.box.clock():return
        calls=0
        for key,e in self.data['extensions'].items():
            if calls>=10 or stop is not None and stop.is_set():break
            if e['status'] not in ('pending','retry_wait'):continue
            if e.get('next_at') and parsed(e['next_at'])>self.box.clock():continue
            dep=self.box.state['entries'].get(e['dependency'],{})
            if dep.get('status')!='delivered':continue
            # Permission revocation suppresses extension data too; never leak persisted native evidence.
            if not self.permitted(dict(e['body'],url=e['body'].get('product_url'),field_presence=[])):
                e['status']='permission_held';self.save();continue
            allowed=self.licensed_matching_fields()
            if allowed is not None and set(e['body'].get('matching_profile',{}))-{'exact_match_confirmed'}-allowed:
                e['status']='permission_held';self.save();continue
            # Food evidence has a separate explicit persistence/use permission.
            if e['body'].get('food_evidence') and not self.box.cfg.get('evidence_storage'):
                e['status']='permission_held';self.save();continue
            e['attempts']+=1;self.save()
            try:code,ack=self.box.transport('/internal/v2/crawl-runs/'+self.box.state['run_id']+'/extensions',copy.deepcopy(e['body']))
            except Exception:code,ack=0,{}
            calls+=1;e['last_status']=code
            if code in (200,201) and ack.get('state') in ('applied','recorded','quarantine'):
                e.update(status='quarantine' if ack['state']=='quarantine' else 'delivered',ack=ack);self.count('extension_'+e['status'])
            elif code in (0,200,201,202,408,425,429,500,502,503,504):
                e['status']='retry_wait' if e['attempts']<20 else 'exhausted'
                e['next_at']=(self.box.clock()+timedelta(seconds=min(3600,5*2**min(e['attempts'],10)))).isoformat()
                if ack.get('state')=='pending':e['pending_reason']=ack.get('error_code');self.count('extension_pending')
            else:e.update(status='held',error_code=ack.get('error_code'),error_fields=ack.get('fields',[]));self.count('extension_held')
            self.save()
            if code in (429,503):return
        self.checks(stop)
    def checks(self,stop):
        if stop is not None and stop.is_set():return
        due=[]
        for ident,e in self.data['checks'].items():
            if e.get('held') or e.get('next_at') and parsed(e['next_at'])>self.box.clock():continue
            if self.box.state['entries'].get(e['observation_dependency'],{}).get('status')!='delivered':continue
            if not self.permitted(e['body']):continue
            due.append((ident,e))
            if len(due)==500:break
        if not due:return
        keys=('source_listing_id','variant_key','observed_at','price','currency','availability')
        body={'source':self.box.source,'items':[{k:e['body'][k] for k in keys} for _,e in due]}
        try:code,ack=self.box.transport('/internal/v2/listing-checks',body)
        except Exception:code,ack=0,{}
        from services.collector.collector_ops.delivery_contract import safe_checks
        ack=safe_checks(ack,body) if code==200 else {}
        if not ack:
            for _,e in due:
                e['attempts']+=1;e['next_at']=(self.box.clock()+timedelta(seconds=min(3600,5*2**min(e['attempts'],10)))).isoformat()
                if code in (400,401,403,404,409,410,422) or e['attempts']>=20:e['held']=True
            self.count('check_failures');self.save();return
        retry={(x['source_listing_id'],x['variant_key']) for k in ('mismatch','unknown') for x in ack[k]}
        rejected={(x['source_listing_id'],x['variant_key']) for x in ack['rejected']}
        for ident,e in due:
            b=e['body'];identity=(b['source_listing_id'],b['variant_key'])
            if identity in retry:
                result=self.box.stage({'observation':b})
                if result['status'] not in ('pending','delivered'):continue
                old=self.owner.data['items'][ident];old['key']=b['observation_key']
                atomic(self.owner.path,self.owner.data);self.count('check_reobserved')
            elif identity in rejected:self.count('check_timestamp_rejected')
            self.data['checks'].pop(ident,None)
        self.count('check_batches');self.data['totals']['check_confirmed']=self.data['totals'].get('check_confirmed',0)+ack['confirmed'];self.save()
    def report(self):
        return {'enabled':self.enabled,'totals':self.data['totals'],'pending_checks':len(self.data['checks']),
                'extension_states':{s:sum(x['status']==s for x in self.data['extensions'].values()) for s in ('pending','retry_wait','delivered','quarantine','held','exhausted','permission_held')}}
