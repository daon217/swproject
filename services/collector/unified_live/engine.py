"""One bounded URL task per tick, durable discovery/refresh and unchanged suppression."""
import hashlib
import threading
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote,urlsplit
from services.collector.domeggook_live.domeggook_delivery import atomic,load,utcnow
from services.collector.marketplace_live.config import stamp
from .backend import ApprovedOutbox
from .changes import ChangeDelivery,digest
from .policy import validate,interval,grant,url
from .transport import SafeHTTP,Wait
from .parser import links,normalize
from .food import evidence

class URLWorker:
    def __init__(self,cfg,root,*,transport=None,delivery=None,renderer=None,clock=utcnow):
        self.cfg=validate(cfg);self.clock=clock;self.root=Path(root)/cfg['source'];self.path=self.root/'url_checkpoint.json';self.stop=threading.Event()
        self.synthetic=getattr(transport,'synthetic_only',False) is True
        context={k:cfg.get(k,[] if k=='queries' else '') for k in ('source','base_url','search_url_template','queries','mode','selectors','render_javascript')}
        if cfg.get('start_urls'):context['start_urls']=cfg['start_urls']
        if cfg.get('storefront_identity'):context['storefront_identity']=cfg['storefront_identity']
        self.context=digest(context)
        self.state=load(self.path,{'version':1,'synthetic_only':self.synthetic,'context':self.context,'tasks':[],'known':{},'cycle_seen':[], 'cycle_products':0,
            'next_cycle_at':None,'next_action_at':None,'hold':None,'totals':{},'cycle':0,'inflight':False,'shape':{},'checkpoint_outbox_seen':False})
        if self.state.get('version')!=1 or self.state.get('context')!=self.context:raise ValueError('URL_checkpoint_context_mismatch_no_reset')
        if self.state.get('synthetic_only') is not self.synthetic:raise ValueError('mock_and_live_URL_state_must_not_mix')
        if self.state['checkpoint_outbox_seen'] and not (self.root/'backend_outbox.json').exists() and delivery is None:raise ValueError('missing_URL_outbox_no_reset')
        self.http=transport or SafeHTTP(cfg,self.root,clock)
        self.delivery=ChangeDelivery(delivery or ApprovedOutbox(dict(cfg,source=cfg['source']),self.root,clock=clock),self.root)
        self.renderer=renderer
        if self.state['inflight']:
            self.state['hold']='interrupted_URL_task_review_required';self.state['inflight']=False;self.save()
    def save(self):
        if hasattr(self,'delivery'):self.state['checkpoint_outbox_seen']=self.delivery.path.exists()
        atomic(self.path,self.state)
    def count(self,name):self.state['totals'][name]=self.state['totals'].get(name,0)+1
    def task(self,kind,target,**kw):return dict(kind=kind,url=target,attempts=0,**kw)
    def begin(self):
        self.state['cycle']+=1;self.state['cycle_seen']=[];self.state['cycle_products']=0
        self.state['tasks']=[self.task('list',url(self.cfg['search_url_template'].replace('{query}',quote(q,safe='')).replace('{page}','1')),page=1) for q in self.cfg.get('queries',[])]
        self.state['tasks'] += [self.task('auto',url(t),page=1) for t in dict.fromkeys(self.cfg.get('start_urls',[]))]
        self.state['refresh_queued']=False
    def complete(self):
        if not self.state['tasks'] and not self.state.get('refresh_queued'):
            self.state['refresh_queued']=True
            candidates=sorted((v['last_checked_at'],k) for k,v in self.state['known'].items() if k not in self.state['cycle_seen'])
            self.state['tasks']=[self.task('detail',target) for _,target in candidates[:self.cfg['refresh_items_per_cycle']]]
        if not self.state['tasks']:
            self.state['next_cycle_at']=(self.clock()+timedelta(seconds=interval(self.cfg))).isoformat();self.count('cycles_completed')
    def page(self,task):
        code,text=self.http.fetch(task['url'])
        if code in (404,410):
            self.count('missing_requires_verification')
            known=self.state['known'].get(task['url'])
            if known:known.update(last_checked_at=self.clock().isoformat(),verification_required=True,last_HTTP_status=code)
            return
        if self.cfg['render_javascript']:
            if self.renderer is None:
                from .render import PlaywrightRenderer
                self.renderer=PlaywrightRenderer()
            text=self.renderer.render(task['url'],self.http)
        now=self.clock().isoformat();self.state['last_collection_at']=now
        if task['kind']=='auto':
            from .parser import document,structured
            soup=document(text)
            detail=len(structured(soup))==1 or bool(soup.select_one('[itemtype$="/Product"]'))
            if not detail:
                selectors=self.cfg.get('selectors',{})
                from .analysis import value
                detail=bool(value(soup,'price',selectors) and value(soup,'name',selectors))
            if detail:
                if task['url'] in self.state['cycle_seen']:self.count('duplicates_skipped');return
                if self.state['cycle_products']>=self.cfg['max_products_per_cycle']:self.count('cycle_coverage_limited');return
                self.state['cycle_seen'].append(task['url']);self.state['cycle_products']+=1
            else:task['kind']='list'
        if task['kind']=='list':
            found,next_page=links(text,task['url'],self.cfg)
            shape_key=hashlib.sha256(task['url'].encode()).hexdigest()
            if self.state['shape'].get(shape_key,0)>0 and not found:raise Wait('site_structure_changed_review_required',hold=True)
            self.state['shape'][shape_key]=len(found)
            for target in found:
                if target in self.state['cycle_seen']:self.count('duplicates_skipped');continue
                if self.state['cycle_products']>=self.cfg['max_products_per_cycle']:self.count('cycle_coverage_limited');break
                self.state['cycle_seen'].append(target);self.state['cycle_products']+=1
                self.state['tasks'].append(self.task('detail',target))
            if next_page and task['page']<self.cfg['max_pages_per_cycle'] and self.state['cycle_products']<self.cfg['max_products_per_cycle']:
                queued={t['url'] for t in self.state['tasks']}
                if next_page not in queued:self.state['tasks'].append(self.task('list',next_page,page=task['page']+1))
            return
        result=normalize(text,task['url'],now,self.cfg)
        if self.synthetic:result['metadata'].update(synthetic=True,data_source='inprocess_mock')
        known=self.state['known'].get(task['url'],{'first_seen_at':now})
        fields=result.pop('food_input');fields.update(manufacturer=result['metadata']['manufacturer'],brand=result['metadata']['brand'])
        ev=evidence(fields,source=self.cfg['source'],url=result['url'],at=now,previous_hash=known.get('evidence_hash'))
        is_food=bool(ev['food_detected'] or ev['ingredients_raw'] or ev['allergens_declared'] is not None or ev['cross_contact_raw'] or any(k in str(fields['category']).lower() for k in ('food','식품','간식','음료')))
        if is_food:
            self.count('food_evidence_seen')
            # Original evidence is persisted only under an explicit separate evidence grant.
            if self.cfg['evidence_storage'] and 'evidence_storage' in self.cfg['rights']['allowed_uses']:
                side=self.root/'evidence'/ (hashlib.sha256(task['url'].encode()).hexdigest()+'.json')
                atomic(side,ev);known['evidence_hash']=ev['raw_sha256']
            if self.cfg['evidence_storage'] and 'evidence_storage' in self.cfg['rights']['allowed_uses'] and result['observation'] and result['observation']['condition']=='new':
                result['food_evidence']=dict(ev)
                result['observation']['selected_domain']='food'
                from .changes import rekey
                rekey(result['observation'])
            else:
                result['observation']=None;result['missing_fields'].append('food_extension_contract_required')
        previous_meta=known.get('metadata_hash')
        # verified_at changes alone are not a product change.
        meta_hash=digest({k:v for k,v in result['metadata'].items() if k!='verified_at'})
        if previous_meta and previous_meta!=meta_hash:self.count('metadata_change_contract_review')
        observation=result.get('observation') or {}
        content_hash=digest({k:v for k,v in observation.items() if k not in ('observed_at','observation_key')})
        if previous_meta!=meta_hash or known.get('content_hash')!=content_hash:known['last_changed_at']=now
        known['content_hash']=content_hash
        known.update(last_checked_at=now,verification_required=False,metadata_hash=meta_hash,
            extension={'schema_version':'listing-extension-v1',**result['metadata'],
                'source':self.cfg['source'],'source_listing_id':result.get('product_number'),
                'name':result.get('name'),'price':result.get('price'),'currency':result.get('currency'),
                'url':result.get('url'),'condition':result.get('condition'),'availability':result.get('availability'),
                'marketplace':self.cfg['source'],'source_product_id':result.get('product_number'),
                'collected_at':known['first_seen_at'],'last_checked_at':now,'last_changed_at':known.get('last_changed_at'),
                'is_synthetic':self.synthetic,'evidence_source':self.cfg['source'],
                'API_contract_ready':False})
        if task['url'] in self.state['known'] or len(self.state['known'])<self.cfg['max_tracked_items']:
            self.state['known'][task['url']]=known
        else:self.count('tracking_capacity_limited')
        if result['observation'] is None:
            self.count('products_held')
            for reason in result['missing_fields']:self.count('hold_'+reason)
        else:
            staged=self.delivery.stage(result)
            self.count('stage_'+staged['status'])
            if staged['status'] in ('pending','delivered'):self.count('products_success');self.state['last_success_at']=now
            elif staged['status']!='unchanged_skipped':self.count('products_held')
    def defer_failed_task(self,task,reason):
        """Bounded page-local failure; retain evidence/history, revisit next cycle.

        Policy/auth/robots/DNS/network-uncertain holds never enter this path.
        """
        self.count('tasks_deferred');self.state['last_failure_at']=self.clock().isoformat()
        failures=self.state.setdefault('recent_task_failures',[])
        failures.append({'url_sha256':hashlib.sha256(task['url'].encode()).hexdigest(),
            'kind':task['kind'],'reason':reason,'at':self.clock().isoformat()})
        self.state['recent_task_failures']=failures[-50:]
        self.state['tasks'].pop(0);self.state['next_action_at']=None;self.complete()
    def step(self):
        if self.stop.is_set() or not self.cfg['enabled']:return self.report()
        if not grant(self.cfg,self.clock()):self.state['hold']='permission_expired_or_missing';self.save();return self.report()
        self.delivery.flush(stop=self.stop)
        if self.state['hold'] or self.http.state.get('hold'):return self.report()
        for key in ('next_action_at',):
            if self.state.get(key) and stamp(self.state[key])>self.clock():return self.report()
        if not self.state['tasks']:
            if self.state['next_cycle_at'] and stamp(self.state['next_cycle_at'])>self.clock():return self.report()
            self.begin()
        task=self.state['tasks'][0]
        self.state['inflight']=True;self.save()
        try:self.page(task)
        except Wait as exc:
            if exc.hold:self.state['hold']=str(exc)
            else:
                if str(exc) not in ('rate_wait','budget_wait','request_wait','robots_crawl_delay','robots_request_rate'):
                    task['attempts']+=1;self.count('request_failures');self.state['last_failure_at']=self.clock().isoformat()
                due=exc.until or self.clock()+timedelta(seconds=min(3600,5*2**task['attempts']))
                self.state['next_action_at']=max(due,self.clock()+timedelta(seconds=min(3600,5*2**task['attempts']))).isoformat()
                if task['attempts']>=self.cfg['max_attempts']:self.defer_failed_task(task,'transient_retry_exhausted')
        except (ValueError,TypeError,KeyError,ArithmeticError):
            self.count('products_failed');self.defer_failed_task(task,'parser_or_contract_review_required')
        else:
            self.state['tasks'].pop(0);self.state['next_action_at']=None;self.complete()
        self.state['inflight']=False;self.save();self.delivery.flush(stop=self.stop)
        return self.report()
    def report(self):
        return {'source':self.cfg['source'],'mode':'URL_mock' if self.synthetic else 'URL_live_configured','synthetic':self.synthetic,'configured_enabled':self.cfg['enabled'],
            'effective_interval_seconds':interval(self.cfg),'next_cycle_at':self.state['next_cycle_at'],
            'last_collection_at':self.state.get('last_collection_at'),'last_success_at':self.state.get('last_success_at'),'last_failure_at':self.state.get('last_failure_at'),
            'hold':self.state['hold'] or self.http.state.get('hold'),'pending_tasks':len(self.state['tasks']),'tracked_items':len(self.state['known']),
            'totals':self.state['totals'],'content_changes':self.delivery.data['totals'],'backend':self.delivery.report(),
            'recent_task_failures':self.state.get('recent_task_failures',[]),'HTTP_attempts':len(self.http.state['requests']),'all_items_refreshed_each_minute':False}
    def close(self):self.stop.set();self.http.close();self.delivery.close()
