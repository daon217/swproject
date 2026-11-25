"""Explicit grants and public, same-origin URLs; robots is not a storage licence."""
import ipaddress
import math
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from services.collector.marketplace_live.config import stamp

DEDICATED = {'ebay.com':'ebay', 'yes24.com':'yes24', 'domeggook.com':'domeggook',
             'bunjang.co.kr':'blocked_partner_required', 'joongna.com':'blocked_partner_required'}
AGENT = 'KkulpickCollector/1.0'

def dedicated(host):
    return next((v for k,v in DEDICATED.items() if host == k or host.endswith('.'+k)),None)

def url(value, host=None):
    if not isinstance(value,str) or len(value)>2048 or any(ord(c)<33 for c in value) or '\\' in value:
        raise ValueError('invalid_public_URL')
    p=urlsplit(value)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):
        raise ValueError('HTTPS_public_URL_required')
    name=p.hostname.lower().encode('idna').decode('ascii')
    if host and name!=host:raise ValueError('cross_origin_forbidden')
    if name=='localhost' or name.endswith(('.local','.localhost','.internal')) or '.' not in name:
        raise ValueError('public_host_required')
    try:address=ipaddress.ip_address(name)
    except ValueError:address=None
    if address is not None and not address.is_global:raise ValueError('nonpublic_IP_forbidden')
    pairs=parse_qsl(p.query,keep_blank_values=True)
    if any(re.search(r'token|secret|password|signature|session|auth|credential|api[-_]?key',k,re.I) or k.lower()=='key' for k,_ in pairs):
        raise ValueError('credential_URL_forbidden')
    pairs=[(k,v) for k,v in pairs if not k.lower().startswith('utm_') and k.lower() not in ('gclid','fbclid')]
    return urlunsplit(('https',name,p.path or '/',urlencode(sorted(pairs)),''))

def interval(cfg):
    requested=60 if cfg.get('mode')=='used' else 7200
    minimum=cfg.get('provider_min_interval_seconds',requested)
    if type(minimum) not in (int,float) or not math.isfinite(minimum) or minimum<60:
        raise ValueError('provider_min_interval_required')
    return max(requested,minimum)

def grant(cfg,now,storage=True):
    g=cfg.get('rights',{})
    uses={'lookup','systematic_collection'}|({'storage','reuse'} if storage else set())
    try:return bool(g.get('reference') and g.get('terms_reference') and uses<=set(g.get('allowed_uses',[])) and stamp(g['expires_at'])>now)
    except (KeyError,ValueError,TypeError):return False

def validate(cfg):
    allowed={'storefront_identity','start_urls','source','base_url','search_url_template','queries','mode','enabled','rights','provider_min_interval_seconds',
        'requests_per_hour','requests_per_24h','request_interval_seconds','max_pages_per_cycle','max_products_per_cycle',
        'refresh_items_per_cycle','max_tracked_items','max_attempts','selectors','render_javascript','evidence_storage',
        'allowed_product_hosts','currencies','backend_enabled','backend_owner_approved','price_semantics_confirmed','backend_delivery','region','country','category_mapping'}
    if set(cfg)-allowed:raise ValueError('unknown_configuration_fields')
    if not re.fullmatch(r'html_[a-z0-9_]{1,50}',cfg.get('source','')):raise ValueError('html_source_namespace_required')
    base=url(cfg['base_url']);host=urlsplit(base).hostname
    if dedicated(host):raise ValueError('dedicated_adapter_required:'+dedicated(host))
    if cfg.get('allowed_product_hosts')!=[host]:raise ValueError('single_origin_hosts_required')
    if cfg.get('mode') not in ('general','used'):raise ValueError('mode_required')
    if cfg.get('region','unknown') not in ('domestic','overseas','unknown'):raise ValueError('explicit_region_required')
    if cfg.get('country') is not None and not re.fullmatch('[A-Z]{2}',cfg['country']):raise ValueError('ISO_country_required')
    mapping=cfg.get('category_mapping',{})
    if not isinstance(mapping,dict) or len(mapping)>2000 or any(not isinstance(k,str) or not isinstance(v,str) or len(k)>500 or len(v)>500 for k,v in mapping.items()):raise ValueError('bounded_operator_category_mapping_required')
    for k in ('enabled','backend_enabled','backend_owner_approved','price_semantics_confirmed','render_javascript','evidence_storage'):
        if type(cfg.get(k)) is not bool:raise ValueError('explicit_boolean:'+k)
    for key,low,high in (('requests_per_hour',1,1000),('requests_per_24h',1,5000),('request_interval_seconds',1,86400),
        ('max_pages_per_cycle',1,10),('max_products_per_cycle',1,100),('refresh_items_per_cycle',0,50),('max_tracked_items',1,100000),('max_attempts',1,5)):
        if type(cfg.get(key)) is not int or not low<=cfg[key]<=high:raise ValueError('invalid_'+key)
    interval(cfg)
    starts=cfg.get('start_urls',[])
    if not isinstance(starts,list) or len(starts)>10:raise ValueError('bounded_start_URLs_required')
    for target in starts:url(target,host)
    qs=cfg.get('queries',[]);template=cfg.get('search_url_template','')
    if not starts or template or qs:
        if not isinstance(qs,list) or not 1<=len(qs)<=10 or any(not isinstance(q,str) or not q.strip() or len(q)>100 for q in qs):raise ValueError('bounded_queries_required')
        if template.count('{query}')!=1 or template.count('{page}')>1:raise ValueError('search_template_required')
        url(template.replace('{query}','test').replace('{page}','1'),host)
    if not isinstance(cfg.get('currencies'),list) or not cfg['currencies'] or any(not re.fullmatch('[A-Z]{3}',c) for c in cfg['currencies']):raise ValueError('currency_allowlist_required')
    selectors=cfg.get('selectors',{})
    if not isinstance(selectors,dict) or set(selectors)-{'sku','url','product_links','next_page','card','id','name','price','currency','seller','condition','availability','image','description','category','ingredients','allergens','cross_contact','brand','manufacturer','model','model_number','mpn','gtin','color','size'}:
        raise ValueError('unsupported_selectors')
    if any(not isinstance(v,str) or len(v)>200 for v in selectors.values()):raise ValueError('bounded_CSS_required')
    identity=cfg.get('storefront_identity')
    if identity is not None:
        if not isinstance(identity,dict) or set(identity)!={'domain','single_merchant','reference','expires_at'} or identity.get('domain')!=host or identity.get('single_merchant') is not True:
            raise ValueError('explicit_same_domain_single_merchant_evidence_required')
        url(identity['reference'],host);stamp(identity['expires_at'])
    return cfg
