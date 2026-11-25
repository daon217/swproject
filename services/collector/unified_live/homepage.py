"""Register one permitted homepage and run the existing URL worker; no API key."""
import argparse,copy,hashlib,json,os
from pathlib import Path
from urllib.parse import urlsplit
from .policy import url,validate,grant,interval
from .registry import register
from services.collector.domeggook_live.domeggook_delivery import atomic,utcnow

def profile(homepage,policy):
    target=url(homepage);host=urlsplit(target).hostname
    cfg={'source':'html_'+hashlib.sha256(host.encode()).hexdigest()[:20],
        'base_url':'https://'+host+'/','start_urls':[target],'search_url_template':'','queries':[],
        'homepage_crawl':True,'mode':'general','enabled':False,'backend_enabled':False,
        'backend_owner_approved':False,'price_semantics_confirmed':False,'render_javascript':False,'evidence_storage':False,
        'provider_min_interval_seconds':7200,'requests_per_hour':30,'requests_per_24h':200,'request_interval_seconds':3,
        'max_pages_per_cycle':8,'max_products_per_cycle':10,'refresh_items_per_cycle':5,'max_tracked_items':10000,'max_attempts':3,
        'allowed_product_hosts':[host],'currencies':['KRW','USD','EUR','GBP','JPY','CNY','AUD','INR'],'selectors':{},
        'rights':{},'backend_delivery':{},'region':'unknown'}
    allowed=set(cfg)-{'source','base_url','start_urls','search_url_template','queries','homepage_crawl','allowed_product_hosts','mode'}
    allowed|={'storefront_identity','backend_catalog','country','category_mapping'}
    if not isinstance(policy,dict) or set(policy)-allowed:raise ValueError('bounded_homepage_policy_fields_required')
    cfg.update(copy.deepcopy(policy));return validate(cfg)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',required=True);p.add_argument('--policy',required=True);p.add_argument('--state-dir',required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--plan',action='store_true');mode.add_argument('--register',action='store_true');mode.add_argument('--watch',action='store_true');a=p.parse_args(argv)
    try:
        cfg=profile(a.url,json.loads(Path(a.policy).read_text(encoding='utf-8-sig')));ready=cfg['enabled'] and grant(cfg,utcnow()) and os.environ.get('COLLECTOR_RUN_APPROVED')=='yes'
        if a.plan:
            print(json.dumps({'source':cfg['source'],'homepage':cfg['start_urls'][0],'ready':ready,'HTTP_requests':0,'interval_seconds':interval(cfg),'rights_confirmed':grant(cfg,utcnow()),'backend_delivery_enabled':cfg['backend_enabled'],'bounded_navigation_pages':cfg['max_pages_per_cycle'],'max_product_pages':cfg['max_products_per_cycle']}));return 0
        if a.watch and not ready:raise ValueError('enabled_source_valid_storage_terms_and_run_switch_required')
        root=Path(a.state_dir);config=root/'homepage_profiles'/(cfg['source']+'.json')
        if config.exists() and json.loads(config.read_text(encoding='utf-8-sig'))!=cfg:raise ValueError('existing_homepage_profile_requires_review_no_overwrite')
        result=register(cfg,root)
        if not config.exists():atomic(config,cfg)
        if a.register:print(json.dumps(dict(result,config=str(config))));return 0
        from .__main__ import main as run
        return run(['--provider','url','--config',str(config),'--state-dir',str(root),'--watch'])
    except (ValueError,TypeError,KeyError,OSError):
        print(json.dumps({'status':'blocked','reason':'homepage_policy_state_or_permission_review','HTTP_requests_not_started_by_registration':True}));return 2
if __name__=='__main__':raise SystemExit(main())
