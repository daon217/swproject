"""Supervise only locally approved URL registrations, one isolated process per site."""
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
from services.collector.domeggook_live.domeggook_delivery import atomic,load,utcnow
from services.collector.domeggook_live.runtime import FileState
from services.collector.marketplace_live.config import stamp
from .discovery import DiscoveryStore
from .policy import validate,grant
from .changes import digest

def registration(site,approval):
    if not site['enabled'] or site['adapter_name'] not in ('generic_jsonld','generic_html','generic_javascript'):return None
    if approval.get('allowed_hosts')!=[site['domain']]:raise ValueError('site_specific_local_grant_required')
    cfg={'source':'html_'+site['marketplace_id'].removeprefix('marketplace-'),'base_url':'https://'+site['domain']+'/',
        'search_url_template':approval.get('search_url_template') or site['search_url_template'] or '',
        'queries':approval.get('queries',[]),
        'mode':'used' if site['kind']=='used' else 'general','country':site['country'],
        'region':'domestic' if site['country']=='KR' else 'overseas' if site['country'] else 'unknown',
        'enabled':True,'backend_enabled':approval.get('backend_enabled') is True,
        'backend_owner_approved':approval.get('backend_owner_approved') is True,'price_semantics_confirmed':approval.get('price_semantics_confirmed') is True,
        'render_javascript':site['adapter_name']=='generic_javascript','evidence_storage':approval.get('evidence_storage') is True,
        'provider_min_interval_seconds':max(site['crawl_interval_seconds'],approval.get('provider_min_interval_seconds',7200)),
        'requests_per_hour':approval.get('requests_per_hour',10),'requests_per_24h':approval.get('requests_per_24h',40),
        'request_interval_seconds':approval.get('request_interval_seconds',3),'max_pages_per_cycle':1,
        'max_products_per_cycle':3,'refresh_items_per_cycle':1,'max_tracked_items':1000,'max_attempts':3,
        'allowed_product_hosts':[site['domain']],'currencies':approval.get('currencies'),
        'selectors':approval.get('selectors',{}),'category_mapping':approval.get('category_mapping',{}),
        'rights':{k:approval[k] for k in ('reference','terms_reference','expires_at','allowed_uses')},
        'backend_delivery':approval.get('backend_delivery',{})}
    if approval.get('start_urls'):cfg['start_urls']=approval['start_urls']
    return validate(cfg)

class FleetSupervisor:
    def __init__(self,root,discovery_root,grants,*,clock=utcnow,popen=subprocess.Popen):
        self.root=Path(root);self.discovery_root=Path(discovery_root);self.grants=grants;self.clock=clock;self.popen=popen
        self.path=self.root/'fleet_checkpoint.json';self.children={};self.last_desired={}
        self.state=load(self.path,{'version':1,'sources':{},'heartbeat_at':None})
        if self.state.get('version')!=1:raise ValueError('fleet_version_no_reset')
    def save(self):atomic(self.path,self.state)
    def desired(self):
        store=DiscoveryStore(self.discovery_root,self.clock);wanted={}
        # Never race the discovery writer while adding local grant decisions.
        with FileState(self.discovery_root/'lock').lock():
            for ident in list(store.state['sites']):
                approval=self.grants.get(ident,{})
                try:
                    site=store.evaluate(ident,approval)
                    cfg=registration(site,approval)
                except (ValueError,KeyError,TypeError):
                    store.state['sites'][ident].update(enabled=False,verification_status='local_grant_configuration_review');store.save();continue
                if cfg:wanted[ident]=cfg
        return wanted
    def tick(self):
        try:wanted=self.desired();self.last_desired=wanted;self.state['discovery_busy']=False
        except OSError:
            wanted={k:v for k,v in self.last_desired.items() if grant({'rights':self.grants.get(k,{})},self.clock()) and
                self.grants[k].get('backend_owner_approved') is True and self.grants[k].get('price_semantics_confirmed') is True}
            self.state['discovery_busy']=True
        if len(wanted)>8:
            order=sorted(wanted,key=lambda ident:(ident not in self.children,ident))
            for ident in order[8:]:self.state['sources'].setdefault(ident,{})['process_state']='capacity_review'
            wanted={ident:wanted[ident] for ident in order[:8]}
        approved=os.environ.get('COLLECTOR_RUN_APPROVED')=='yes'
        for ident,child in list(self.children.items()):
            status=self.state['sources'][ident]
            if ident not in wanted or not approved:
                if not status.get('stop_requested_at'):child.terminate();status['stop_requested_at']=self.clock().isoformat()
                try:child.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    status['process_state']='stopping_permission_revoked'
                    if self.clock()-stamp(status['stop_requested_at'])>timedelta(seconds=60):child.kill();child.wait(timeout=5)
                    else:continue
                self.children.pop(ident);status['process_state']='permission_revoked_stopped'
            elif child.poll() is not None:
                self.children.pop(ident);status['exit_code']=child.returncode;status['failures']=status.get('failures',0)+1
                status['next_start_at']=(self.clock()+timedelta(seconds=min(3600,5*2**min(status['failures'],10)))).isoformat()
                status['process_state']='restart_backoff' if status['failures']<10 else 'repeated_failure_review'
        for ident,cfg in wanted.items():
            status=self.state['sources'].setdefault(ident,{'failures':0,'process_state':'disabled'})
            if ident in self.children:
                if status.get('config_sha256')!=digest(cfg):status['process_state']='configuration_change_review_keep_existing_writer'
                continue
            if not approved:status['process_state']='run_approval_required';continue
            if status['failures']>=10 or status.get('next_start_at') and stamp(status['next_start_at'])>self.clock():continue
            path=self.root/'config'/f'{ident}.json'
            # Do not overwrite a different active history/config on automatic rediscovery.
            if path.exists() and load(path,None)!=cfg:status['process_state']='configuration_change_review';continue
            atomic(path,cfg);child_root=self.root/'sources'/ident
            command=[sys.executable,'-m','services.collector.unified_live','--provider','url','--config',str(path),'--state-dir',str(child_root),'--watch']
            env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','PYTHONPATH','PYTHONDONTWRITEBYTECODE',
                'COLLECTOR_BACKEND_TRANSPORT','COLLECTOR_BACKEND_BASE_URL','COLLECTOR_RUN_APPROVED','COLLECTOR_DELIVERY_APPROVED','KKULPICK_BACKEND_TOKEN','KKULPICK_BACKEND_TOKEN_FILE','COLLECTOR_BROWSER_CHANNEL','COLLECTOR_CA_FILE','LANG','LC_ALL'}}
            try:self.children[ident]=self.popen(command,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except OSError:
                status['failures']+=1;status['process_state']='start_failed_backoff';status['next_start_at']=(self.clock()+timedelta(seconds=60)).isoformat();continue
            status.update(process_state='running',started_at=self.clock().isoformat(),config_sha256=digest(cfg))
        self.state['heartbeat_at']=self.clock().isoformat();self.save();return self.report()
    def report(self):return {'running_children':len(self.children),'sources':self.state['sources'],'heartbeat_at':self.state['heartbeat_at'],
        'scope':'approved_generic_URL_sites_only; official_API_workers_keep_existing_compose_profiles'}
    def close(self):
        for child in self.children.values():
            if child.poll() is None:child.terminate()
        for ident,child in list(self.children.items()):
            try:child.wait(timeout=60)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
        self.children.clear()

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--state-dir',required=True);p.add_argument('--discovery-state',required=True);p.add_argument('--grants',required=True)
    p.add_argument('--plan',action='store_true');p.add_argument('--watch',action='store_true');p.add_argument('--health',action='store_true');p.add_argument('--max-ticks',type=int)
    args=p.parse_args(argv);stop=threading.Event();prior={}
    try:
        if args.health:
            heart=load(Path(args.state_dir)/'fleet_checkpoint.json',{})
            return 0 if heart.get('heartbeat_at') and utcnow()-stamp(heart['heartbeat_at'])<timedelta(seconds=120) else 1
        grants=load(Path(args.grants),{})
        with FileState(Path(args.state_dir)/'lock').lock():
            fleet=FleetSupervisor(args.state_dir,args.discovery_state,grants)
            try:
                if not args.watch:print(json.dumps({'eligible_URL_workers':len(fleet.desired()),'HTTP_requests_this_command':0}));return 0
                for sig in (signal.SIGINT,signal.SIGTERM):prior[sig]=signal.signal(sig,lambda *_:stop.set())
                ticks=0
                while not stop.is_set():
                    fleet.grants=load(Path(args.grants),{});fleet.tick();ticks+=1
                    if args.max_ticks and ticks>=args.max_ticks:break
                    stop.wait(1)
                print(json.dumps(fleet.report()));return 0
            finally:fleet.close()
    except Exception:
        print(json.dumps({'status':'blocked','reason':'fleet_grant_state_lock_or_child_review','automatic_reset':False}));return 2
    finally:
        for sig,handler in prior.items():signal.signal(sig,handler)

if __name__=='__main__':raise SystemExit(main())
