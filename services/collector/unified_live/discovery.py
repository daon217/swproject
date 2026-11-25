"""Bounded publisher-directory discovery; remote metadata cannot approve collection."""
import argparse
from contextlib import contextmanager
import errno
import copy
from datetime import timedelta
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import threading
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit,urljoin
from services.collector.domeggook_live.domeggook_delivery import atomic,load,utcnow
from services.collector.domeggook_live.runtime import FileState
from services.collector.marketplace_live.config import stamp
from .policy import url,dedicated,grant
from .analysis import analyze,opensearch_template
from .transport import SafeHTTP,Wait
from .parser import normalize,links
from services.collector.marketplace_live.probe import lookup_permitted

SEEDS=Path(__file__).with_name('seed_sites.json')
ADAPTERS={'domeggook','yes24','ebay','elevenst_offline','smartify','perfume_registry','public_yappy','blocked_partner_required'}

def domain(value):
    host=urlsplit(url(value if '://' in value else 'https://'+value+'/')).hostname
    return host[4:] if host.startswith('www.') else host

def marketplace_id(host):return 'marketplace-'+hashlib.sha256(domain(host).encode()).hexdigest()[:20]

def select_adapter(site,approval=None):
    approval=approval or {};ded=dedicated(site['domain'])
    known=site.get('existing_adapter')
    if ded=='blocked_partner_required' or known=='blocked_partner_required':return 'blocked_partner_required'
    if site.get('official_api_available') is True and approval.get('api_entitlement_confirmed') and known in ADAPTERS:return known
    if known in ADAPTERS:return known
    caps=site.get('capabilities',{})
    if caps.get('javascript_reviewed'):return 'generic_javascript'
    if caps.get('css_product_reviewed'):return 'generic_html'
    if caps.get('jsonld_product_count',0):return 'generic_jsonld'
    if caps.get('microdata_product_count',0) or caps.get('open_graph'):return 'generic_html'
    return 'dedicated_parser_review_required'

class DiscoveryStore:
    def __init__(self,root,clock=utcnow):
        self.root=Path(root);self.clock=clock;self.path=self.root/'discovery_registry.json'
        self.state=load(self.path,{'version':1,'sites':{},'next_scan_at':None,'last_scan_at':None,'totals':{}})
        if self.state.get('version')!=1:raise ValueError('discovery_version_mismatch_no_reset')
        changed=False
        for site in self.state['sites'].values():
            if not site.get('last_product_check') and not site.get('product_quality_verified') and site.get('verification_status','').startswith('metadata_') and not site.get('last_metadata_success_at') and site.get('last_success_at'):
                site['last_metadata_success_at']=site['last_success_at'];site['last_success_at']=None;changed=True
        if changed:self.save()
    def save(self):atomic(self.path,self.state)
    def add(self,item,reference):
        if not isinstance(reference,str) or not reference or len(reference)>2048:raise ValueError('bounded_directory_reference_required')
        host=urlsplit(url('https://'+item['domain']+'/')).hostname;ident=marketplace_id(host)
        sites=self.state['sites']
        if ident in sites:
            if reference not in sites[ident]['discovery_references']:sites[ident]['discovery_references'].append(reference)
            self.save();return ident
        if len(sites)>=2000:raise ValueError('discovery_capacity_review_required')
        known=item.get('adapter') if item.get('adapter') in ADAPTERS else dedicated(host)
        # Do not import enabled/permission/verified/callback configuration from a directory.
        site={'marketplace_id':ident,'marketplace_name':str(item.get('name') or host)[:200],'domain':host,
            'country':item.get('country') if isinstance(item.get('country'),str) and re.fullmatch('[A-Z]{2}',item['country']) else None,
            'source_type':'official_API_candidate' if item.get('official_api') is True else 'public_site_candidate',
            'official_api_available':item.get('official_api') if type(item.get('official_api')) is bool else None,
            'access_policy':'not_checked','collection_permission':'unverified','search_url_template':None,
            'existing_adapter':known,'adapter_name':known or 'dedicated_parser_review_required',
            'supports_pagination':None,'supports_product_detail':None,'supports_price':None,'supports_stock_status':None,
            'supports_used_products':None,'rate_limit':{'review_required':True},
            'crawl_interval_seconds':60 if item.get('kind')=='used' else 7200,
            'last_success_at':None,'last_failure_at':None,'last_metadata_success_at':None,'enabled':False,'verification_status':'candidate',
            'kind':item.get('kind') if item.get('kind') in ('general','used','used_and_general','food_information','food_and_general') else 'unknown','metadata_urls':[], 'discovery_references':[reference],
            'capabilities':{},'probes':[],'product_quality_verified':False}
        for target in item.get('metadata_urls',[])[:5]:site['metadata_urls'].append(url(target,host))
        sites[ident]=site;self.state['totals']['discovered']=self.state['totals'].get('discovered',0)+1;self.save();return ident
    def ingest(self,data,reference):
        if not isinstance(data,list) or len(data)>2000:raise ValueError('bounded_directory_required')
        added=[]
        for item in data:
            try:
                if not isinstance(item,dict) or not isinstance(item.get('domain'),str):raise ValueError()
                added.append(self.add(item,reference))
            except (ValueError,KeyError,TypeError):self.state['totals']['rejected_candidates']=self.state['totals'].get('rejected_candidates',0)+1
        self.save();return added
    def evaluate(self,ident,approval=None):
        site=self.state['sites'][ident];approval=approval or {}
        site['adapter_name']=select_adapter(site,approval)
        okay=grant({'rights':approval},self.clock())
        # Automatic registration is allowed; activation requires independently verified data and local grant.
        site['enabled']=bool(okay and site['product_quality_verified'] and site['access_policy']=='metadata_accessible' and
            site['adapter_name'] not in ('blocked_partner_required','dedicated_parser_review_required','elevenst_offline') and
            approval.get('backend_owner_approved') is True and approval.get('price_semantics_confirmed') is True)
        site['activation_wait_reasons']=[reason for reason,passed in (('storage_reuse_grant_required',okay),('product_quality_check_required',site['product_quality_verified']),('metadata_access_required',site['access_policy']=='metadata_accessible'),('backend_owner_approval_required',approval.get('backend_owner_approved') is True),('price_semantics_confirmation_required',approval.get('price_semantics_confirmed') is True)) if not passed]
        site['collection_permission']='storage_reuse_confirmed' if okay else 'unverified'
        if site['enabled']:site['verification_status']='activation_ready_backend_contract_still_required'
        elif site['product_quality_verified']:site['verification_status']='lookup_verified_storage_or_backend_permission_wait'
        self.save();return site
    def record_product_check(self,ident,*,valid,held):
        site=self.state['sites'][ident]
        if type(valid) is not int or type(held) is not int or min(valid,held)<0:raise ValueError('verified_counts_required')
        site['product_quality_verified']=valid>0;site['last_product_check']={'valid':valid,'held':held,'at':self.clock().isoformat()}
        if valid:site['last_success_at']=self.clock().isoformat()
        return self.evaluate(ident)
    def report(self):
        sites=self.state['sites'].values()
        return {'candidates':len(self.state['sites']),'enabled':sum(s['enabled'] for s in sites),
            'last_scan_at':self.state['last_scan_at'],'next_scan_at':self.state['next_scan_at'],
            'verification_states':{k:sum(s['verification_status']==k for s in sites) for k in {s['verification_status'] for s in sites}},
            'product_quality_verified':sum(s['product_quality_verified'] for s in sites),'automatic_unverified_activation':False}

class MetadataHTTP(SafeHTTP):
    def __init__(self,host,targets,root,clock=utcnow):
        self.allowed={url(t,host) for t in targets}|{'https://'+host+'/robots.txt'}
        self.metadata_targets=set(self.allowed);self.preview_grants={}
        self.metadata_deadline=clock()+timedelta(hours=1)
        cfg={'source':'html_metadata_'+hashlib.sha256(host.encode()).hexdigest()[:12],'base_url':'https://'+host+'/',
            'enabled':True,'requests_per_hour':20,'requests_per_24h':40,'request_interval_seconds':1}
        super().__init__(cfg,root,clock)
    def permitted(self,target):
        if self.clock()>=self.metadata_deadline:return False
        if target in self.metadata_targets:return True
        approval=self.preview_grants.get(target,{})
        if not approval and getattr(self,'render_approval',None):approval=self.render_approval
        return bool(approval.get('terms_reference') and lookup_permitted({'rights':approval},self.clock()))
    def allow_product(self,target,approval):
        target=url(target,self.host);self.preview_grants[target]=copy.deepcopy(approval);self.allowed.add(target)
    def allow_metadata(self,target):
        target=url(target,self.host);self.metadata_targets.add(target);self.allowed.add(target)

def wait_fetch(http,target,stop=None):
    stop=stop or threading.Event()
    for _ in range(4):
        try:return http.fetch(target)
        except Wait as exc:
            delay=(exc.until-http.clock()).total_seconds() if exc.until else 999
            if exc.hold or str(exc) not in ('rate_wait','robots_crawl_delay','robots_request_rate') or not 0<=delay<=10:raise
            if stop.wait(delay):raise Wait('discovery_stopping',hold=True)
    raise Wait('metadata_rate_review_required',hold=True)

def catalogue_links(text,base):
    data=json.loads(text)
    if not isinstance(data,dict):raise ValueError('API_catalogue_object_required')
    output=[]
    for entry in data.get('linkset',[])[:100]:
        if not isinstance(entry,dict):continue
        for rel,value in entry.items():
            if rel=='anchor':continue
            for link in (value if isinstance(value,list) else [value]):
                href=link.get('href') if isinstance(link,dict) else None
                if isinstance(href,str):
                    try:output.append({'relation':rel,'url':url(urljoin(base,href))})
                    except ValueError:pass
    return output[:100]

def probe(store,ident,http_factory=MetadataHTTP,stop=None,approval=None,renderer=None):
    site=store.state['sites'][ident];approval=approval or {}
    targets=list(site['metadata_urls'] or ['https://'+site['domain']+'/'])
    # Explicit local starts are evidence targets, not rights inferred from a page.
    starts=approval.get('start_urls',[])
    if not isinstance(starts,list) or len(starts)>10:raise ValueError('bounded_local_starts_required')
    if starts and lookup_permitted({'rights':approval},store.clock()) and approval.get('terms_reference'):
        targets=list(dict.fromkeys(url(t,site['domain']) for t in starts))[:5]
    site['product_quality_verified']=False  # Never keep a stale success after a failed recheck.
    site['capabilities'].pop('css_product_reviewed',None)
    site['capabilities'].pop('javascript_reviewed',None)
    site['last_metadata_attempt_at']=store.clock().isoformat();store.save()
    http=http_factory(site['domain'],targets,store.root/'metadata'/ident,store.clock)
    try:
        for target in targets:
            atomic(store.root/'heartbeat.json',{'heartbeat_at':store.clock().isoformat(),'stage':'metadata_request','marketplace_id':ident})
            code,text=wait_fetch(http,target,stop)
            if code!=200:raise Wait('metadata_not_found',hold=True)
            info={'url':target,'sha256':hashlib.sha256(text.encode()).hexdigest(),'at':store.clock().isoformat(),'status':code}
            if text.lstrip().startswith('{'):
                info['published_links']=catalogue_links(text,target)
                # Links to a different publisher become disabled candidates, never request targets in this probe.
                for link in info['published_links']:
                    host=urlsplit(link['url']).hostname
                    if domain(host)!=domain(site['domain']):store.add({'domain':host},target)
            else:
                if approval.get('render_javascript') is True:
                    if not lookup_permitted({'rights':approval},store.clock()) or not approval.get('terms_reference'):
                        raise Wait('render_lookup_grant_required',hold=True)
                    if not isinstance(http,MetadataHTTP):raise Wait('render_grant_transport_required',hold=True)
                    http.render_approval=copy.deepcopy(approval)
                    if renderer is None:
                        from .render import PlaywrightRenderer
                        renderer=PlaywrightRenderer()
                    text=renderer.render(target,http)
                    site['capabilities']['javascript_reviewed']=True
                selector=approval.get('discovery_links_selector')
                if selector:
                    if not isinstance(selector,str) or len(selector)>200:raise ValueError('bounded_directory_selector_required')
                    from .parser import document
                    for node in document(text).select(selector)[:20]:
                        try:
                            candidate=url(urljoin(target,node.get('href','')))
                            host=urlsplit(candidate).hostname
                            if domain(host)!=domain(site['domain']):store.add({'domain':host},target)
                        except ValueError:continue
                caps=analyze(text,target);site['capabilities'].update(caps)
                if caps['search_url_template']:site['search_url_template']=caps['search_url_template']
                elif caps['opensearch_descriptions']:
                    link=caps['opensearch_descriptions'][0]
                    if not hasattr(http,'allow_metadata'):raise Wait('metadata_transport_review',hold=True)
                    http.allow_metadata(link);search_code,search_text=wait_fetch(http,link,stop)
                    if search_code==200:site['search_url_template']=opensearch_template(search_text,link)
                for k in ('supports_pagination','supports_product_detail','supports_price','supports_stock_status','supports_used_products'):site[k]=caps[k]
                check_cfg={'source':'html_'+ident.removeprefix('marketplace-'),'allowed_product_hosts':[site['domain']],
                    'currencies':['KRW','USD','AUD','EUR','INR','GBP','JPY','CNY','PLN'],'mode':'used' if site['kind']=='used' else 'general',
                    'selectors':approval.get('selectors',{}),'max_products_per_cycle':1,'country':site['country']}
                detail_text=text;detail_target=target
                # A directory/listing page needs an independently granted, bounded product preview.
                if not (caps['jsonld_product_count']==1 or caps['microdata_product_count']==1 or caps['open_graph'] and caps['supports_price']):
                    found,_=links(text,target,check_cfg)
                    if found and select_adapter(site,approval) not in ADAPTERS and lookup_permitted({'rights':approval},store.clock()) and approval.get('terms_reference'):
                        detail_target=found[0]
                        if not hasattr(http,'allow_product'):raise Wait('grant_enforcing_preview_transport_required',hold=True)
                        http.allow_product(detail_target,approval)
                        detail_code,detail_text=wait_fetch(http,detail_target,stop)
                        if detail_code!=200:detail_text=''
                        elif approval.get('render_javascript') is True:detail_text=renderer.render(detail_target,http)
                if detail_text:
                    try:
                        normalized=normalize(detail_text,detail_target,store.clock().isoformat(),check_cfg)
                        valid=normalized['observation'] is not None
                        site['quality_preview']={'valid':int(valid),'held':int(not valid),'missing_fields':normalized['missing_fields'],
                            'at':store.clock().isoformat(),'scope':'one_document_or_granted_detail','DB_sent':False}
                        if valid:
                            detail_caps=analyze(detail_text,detail_target)
                            for field in ('jsonld_product_count','microdata_product_count','open_graph','supports_product_detail','supports_price','supports_stock_status','supports_used_products'):
                                site['capabilities'][field]=detail_caps[field]
                            site['product_quality_verified']=True;site['last_success_at']=store.clock().isoformat()
                            if approval.get('selectors'):site['capabilities']['css_product_reviewed']=True
                    except (ValueError,TypeError,KeyError,ArithmeticError):
                        site['quality_preview']={'valid':0,'held':1,'reason':'native_parser_review','at':store.clock().isoformat(),'DB_sent':False}
            site['probes']=(site['probes']+[info])[-20:]
        site.update(access_policy='metadata_accessible',verification_status='metadata_verified_not_product_verified',last_metadata_success_at=store.clock().isoformat())
    except (Wait,ValueError,TypeError,KeyError):
        site.update(enabled=False,access_policy='metadata_blocked_or_review_required',verification_status='policy_or_structure_review',last_failure_at=store.clock().isoformat())
    finally:http.close();store.evaluate(ident,approval)
    return site

@contextmanager
def shared_lock(root,stop):
    """Retry brief fleet contention; never swallow I/O failures in the body."""
    acquired=None
    for attempt in range(20):
        candidate=FileState(Path(root)/'lock').lock()
        try:candidate.__enter__()
        except OSError as exc:
            if exc.errno not in (errno.EACCES,errno.EAGAIN) or attempt==19:raise
            if stop.wait(.1):raise ValueError('discovery_stopping') from None
        else:acquired=candidate;break
    try:yield
    finally:acquired.__exit__(None,None,None)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state-dir',required=True);p.add_argument('--directory',default=str(SEEDS));p.add_argument('--grants')
    mode=p.add_mutually_exclusive_group(required=True)
    for k in ('plan','status','health','scan','watch'):mode.add_argument('--'+k,action='store_true')
    p.add_argument('--live-metadata',action='store_true');p.add_argument('--max-sites',type=int,default=3);p.add_argument('--max-ticks',type=int)
    args=p.parse_args(argv);stop=threading.Event();prior={}
    args.live_metadata=args.live_metadata or os.environ.get('DISCOVERY_METADATA_APPROVED')=='yes'
    try:
        if not 1<=args.max_sites<=10:raise ValueError('bounded_metadata_batch_required')
        root=Path(args.state_dir)
        if args.health:
            heart=load(root/'heartbeat.json',{})
            return 0 if heart.get('heartbeat_at') and utcnow()-stamp(heart['heartbeat_at'])<timedelta(seconds=120) else 1
        if args.status:
            print(json.dumps(DiscoveryStore(root).report()));return 0
        data=json.loads(Path(args.directory).read_text(encoding='utf-8'))
        if args.plan:
            print(json.dumps({'directory_candidates':len(data['sites']),'metadata_requests_authorized':args.live_metadata,
                'max_sites':args.max_sites,'enabled_by_discovery':0,'HTTP_requests_this_command':0}));return 0
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT,signal.SIGTERM):prior[sig]=signal.signal(sig,lambda *_:stop.set())
        with shared_lock(root,stop):
            store=DiscoveryStore(root);store.ingest(data['sites'],data.get('reference','operator_directory'))
        ticks=0
        while not stop.is_set():
            with shared_lock(root,stop):
                store=DiscoveryStore(root)
                due=args.scan or not store.state['next_scan_at'] or stamp(store.state['next_scan_at'])<=store.clock()
                if due:
                    # Prefer explicitly published metadata endpoints; do not crawl every seed on first boot.
                    order=sorted(store.state['sites'],key=lambda i:(bool(store.state['sites'][i].get('last_metadata_attempt_at')),
                        store.state['sites'][i].get('last_metadata_attempt_at') or '',not bool(store.state['sites'][i]['metadata_urls'])))
                    if args.live_metadata:
                        approvals=load(Path(args.grants),{}) if args.grants else {}
                        for ident in order[:args.max_sites]:
                            if stop.is_set():break
                            try:probe(store,ident,stop=stop,approval=approvals.get(ident,{}))
                            except (ValueError,TypeError,KeyError):
                                store.state['sites'][ident].update(enabled=False,product_quality_verified=False,
                                    access_policy='local_grant_configuration_review',verification_status='local_grant_configuration_review',
                                    last_failure_at=store.clock().isoformat())
                                store.save()
                    store.state['last_scan_at']=store.clock().isoformat();store.state['next_scan_at']=(store.clock()+timedelta(days=1)).isoformat();store.save()
                atomic(root/'heartbeat.json',dict(store.report(),heartbeat_at=store.clock().isoformat(),mode='metadata_only' if args.live_metadata else 'offline_directory_only'))
            ticks+=1
            if args.scan or args.max_ticks and ticks>=args.max_ticks:break
            stop.wait(1)
        print(json.dumps(store.report()));return 0
    except Exception:
        print(json.dumps({'status':'blocked','reason':'discovery_configuration_state_or_lock_review','automatic_reset':False}));return 2
    finally:
        stop.set()
        for sig,handler in prior.items():signal.signal(sig,handler)

if __name__=='__main__':raise SystemExit(main())
