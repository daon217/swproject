"""Observation v2 mapper and HTTP transport. No PostgreSQL or implicit credential loading."""
import hashlib,json,re
from decimal import Decimal
from uuid import UUID
from urllib.parse import urlsplit
import requests
from .stable_identity import resolve
from .domeggook_operations import grant_valid
from .domeggook_backend_contract import Observation

FIELD_MAP={'name':'product_name','price':'unit_price','currency':'currency','availability':'availability',
           'url':'product_url','shipping_fee':'shipping_fee','description':'description'}
ACK_FIELDS={'name','description','price','currency','shipping_fee','availability','url','current_url','condition'}

def synthetic_proven(row):
    return (row.get('test_data') is True and (row.get('evidence') or {}).get('mode')=='synthetic' and
        row.get('source')=='domeggook_test' and str(row.get('source_listing_id','')).startswith('TEST-') and
        urlsplit(row.get('product_url','')).hostname=='store.example.test')

def prepare_observation(row,cfg,*,selected_domain,condition,model=None):
    row=resolve(row)
    test=cfg.get('backend_delivery',{}).get('mode')=='synthetic_test'
    if test:
        if not synthetic_proven(row):raise PermissionError('synthetic_namespace_and_provenance_required')
    elif row['source']!='domeggook':raise ValueError('source_not_approved')
    if not row.get('variant_key'):raise ValueError('nonempty_native_variant_required')
    if not test and not cfg.get('price_semantics_confirmed'):raise PermissionError('backend_unit_price_MOQ_display_agreement_required')
    if condition not in ('new','used') or selected_domain not in ('product','food'):raise ValueError('explicit_domain_and_condition_required')
    stamp=row.get('observed_at') or row.get('last_observed_at')
    body={'schema_version':2,'source':row['source'],'source_listing_id':row['source_listing_id'],'variant_key':row['variant_key'],
          'observed_at':stamp,'result':'success','selected_domain':selected_domain,'condition':condition}
    grants=cfg.get('storage_grants',{})
    for target,source in FIELD_MAP.items():
        if target=='description' and row.get('detail_content_license_usable') is not True:
            body[target]=None;continue
        if not test and (not grant_valid(grants,source) or grants[source].get('reuse') is not True):continue
        value=row.get(source)
        if value is not None:body[target]=str(Decimal(str(value))) if target in ('price','shipping_fee') else value
    if not {'name','price','currency','availability','url'}.issubset(body):raise PermissionError('required_field_storage_reuse_or_value_missing')
    body['field_presence']=sorted(set(body)&set(FIELD_MAP))
    body['observation_key']='domeggook:'+hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    body=validate_body(body,cfg)
    if model is not None:model.model_validate(body)
    return body

def validate_body(body,cfg):
    settings=cfg.get('backend_delivery',{})
    Observation.model_validate(body,context={'hosts':settings.get('allowed_product_hosts',['domeggook.com','www.domeggook.com']),
                                           'currencies':settings.get('currencies',['KRW'])})
    if len(json.dumps(body,ensure_ascii=False,separators=(',',':')).encode())>65536:raise ValueError('observation_body_too_large')
    return body

def safe_ack(value):
    if not isinstance(value,dict):return {}
    result={}
    if value.get('state') in ('applied','recorded','quarantine'):result['state']=value['state']
    if value.get('change_kind') in ('created','updated','unchanged','stale','failed','not_found','quarantined'):result['change_kind']=value['change_kind']
    for key in ('offer_id','observation_id'):
        try:result[key]=str(UUID(str(value[key])))
        except (KeyError,ValueError,TypeError,AttributeError):pass
    if isinstance(value.get('error_code'),str) and re.fullmatch(r'[A-Z0-9_]{1,80}',value['error_code']):result['error_code']=value['error_code']
    if isinstance(value.get('changed_fields'),list):result['changed_fields']=[k for k in value['changed_fields'] if k in ACK_FIELDS]
    return result

class HTTPBackendTransport:
    def __init__(self,base_url,token,*,approved_loopback_test=False):
        parsed=urlsplit(base_url)
        loopback=approved_loopback_test and parsed.scheme=='http' and parsed.hostname=='127.0.0.1'
        if parsed.scheme!='https' and not loopback or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('approved_HTTPS_or_explicit_loopback_test_required')
        if not isinstance(token,str) or len(token)<32 or any(c in token for c in '\r\n'):raise ValueError('valid_collector_token_required')
        from .network import secure_public_session
        self.base=base_url.rstrip('/');self.session=requests.Session();self.session.trust_env=False
        if not loopback:secure_public_session(self.session)
        self.session.headers.update({'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    def __call__(self,path,body):
        if not re.fullmatch(r'/internal/v2/crawl-runs/[0-9a-f-]{36}/observations',path):raise ValueError('fixed_observation_route_required')
        try:
            response=self.session.post(self.base+path,json=body,timeout=(5,15),allow_redirects=False)
            if response.status_code not in (200,201):return response.status_code,{}
            return response.status_code,safe_ack(response.json())
        except (requests.RequestException,ValueError):return 0,{}
    def close(self):
        self.session.headers.pop('Authorization',None);self.session.close()

class BackendAdapter:
    def __init__(self,cfg,transport=None):self.cfg=cfg;self.transport=transport
    def send(self,run_id,row,*,selected_domain,condition,model=None):
        if not self.cfg.get('backend_enabled') or not self.cfg.get('backend_owner_approved'):return {'sent':False,'reason':'backend_disabled_or_owner_approval_missing'}
        body=prepare_observation(row,self.cfg,selected_domain=selected_domain,condition=condition,model=model)
        if self.transport is None:raise ValueError('approved_transport_required')
        status,ack=self.transport('/internal/v2/crawl-runs/'+str(UUID(str(run_id)))+'/observations',body)
        ack=safe_ack(ack)
        return {'sent':status in (200,201) and 'state' in ack,'status':status,'applied':ack.get('state')=='applied',**ack}
