"""One durable reservation per attempt, including OAuth and uncertain failures."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
import requests
from services.collector.domeggook_live.domeggook_delivery import atomic, load, utcnow
from .config import rights, stamp

class Pause(RuntimeError):
    def __init__(self,reason,until):super().__init__(reason);self.until=until

class ProviderError(RuntimeError):
    def __init__(self,reason,http_status=None):super().__init__(reason);self.http_status=http_status

ROUTES={
    'yes24_api':('apis.yes24.com',('/v1/goods/itemList','/v1/goods/itemDetail')),
    'searchapi_google_shopping':('www.searchapi.io',('/api/v1/search',)),
    'serper_google_shopping':('google.serper.dev',('/shopping',)),
    'ebay_browse':('api.ebay.com',('/identity/v1/oauth2/token','/buy/browse/v1/item_summary/search','/buy/browse/v1/item/')),
}

def retry_after(value,current):
    if not value:return current+timedelta(seconds=60)
    try:
        if str(value).isdigit():return current+timedelta(seconds=int(value))
        target=parsedate_to_datetime(value)
        if target.tzinfo is None:target=target.replace(tzinfo=timezone.utc)
        return max(current+timedelta(seconds=1),target)
    except (ValueError,TypeError,OverflowError):return current+timedelta(seconds=60)

class ProviderHTTP:
    def __init__(self,cfg,root,clock=utcnow,session=None):
        self.cfg=cfg;self.clock=clock;self.path=Path(root)/'request_ledger.json'
        self.state=load(self.path,{'version':1,'source':cfg['source'],'requests':[],'hold':None,'not_before':None})
        if self.state.get('version')!=1 or self.state.get('source')!=cfg['source'] or not isinstance(self.state.get('requests'),list):
            raise ValueError('request_ledger_schema_mismatch_no_reset')
        self.session=session or requests.Session();self.session.trust_env=False
        self.cycle_id=None;self.task_id=None;self.stop=None
        # Never replay a reservation immediately after an abrupt process exit.
        changed=False
        for entry in self.state['requests']:
            if entry['status']=='reserved':
                entry['status']='interrupted_uncertain';changed=True
                until=stamp(entry['at'])+timedelta(seconds=max(7200,cfg['cycle_interval_seconds']))
                old=stamp(self.state['not_before']) if self.state.get('not_before') else self.clock()
                self.state['not_before']=max(old,until).isoformat()
        if changed:self.save()

    def save(self):atomic(self.path,self.state)

    def permitted(self):return self.cfg['enabled'] and rights(self.cfg,self.clock())

    def route(self,method,url):
        p=urlsplit(url);host,paths=ROUTES[self.cfg['source']]
        if p.scheme!='https' or p.hostname!=host or p.port not in (None,443) or p.username or p.password or p.query or p.fragment:
            raise ValueError('fixed_provider_route_required')
        allowed=p.path in paths
        if self.cfg['source']=='ebay_browse' and p.path.startswith(paths[-1]):
            tail=p.path[len(paths[-1]):]
            allowed=bool(tail) and '/' not in tail
        if not allowed:raise ValueError('fixed_provider_route_required')
        if self.cfg['source']=='serper_google_shopping':
            if method!='POST':raise ValueError('Serper_shopping_POST_required')
        elif method=='POST' and p.path!='/identity/v1/oauth2/token':raise ValueError('only_OAuth_POST_allowed')
        if method=='GET' and p.path=='/identity/v1/oauth2/token':raise ValueError('OAuth_POST_required')

    def reserve(self,method,url,params):
        current=self.clock();cfg=self.cfg;entries=self.state['requests']
        if self.stop is not None and self.stop.is_set():raise Pause('worker_stopping',current)
        if not self.permitted():raise ProviderError('provider_permission_required')
        if self.state['hold']:raise ProviderError('provider_hold_requires_review')
        if self.state.get('not_before') and stamp(self.state['not_before'])>current:
            raise Pause('provider_deadline_wait',stamp(self.state['not_before']))
        if entries:
            due=stamp(entries[-1]['at'])+timedelta(seconds=cfg['request_interval_seconds'])
            if due>current:raise Pause('request_interval_wait',due)
        for seconds,limit in ((3600,cfg['requests_per_hour']),(86400,cfg['requests_per_24h'])):
            recent=sorted(stamp(e['at']) for e in entries if current-stamp(e['at'])<timedelta(seconds=seconds))
            if len(recent)>=limit:raise Pause('provider_budget_wait',recent[-limit]+timedelta(seconds=seconds))
        if sum(e.get('cycle_id')==self.cycle_id for e in entries)>=cfg['requests_per_cycle']:
            raise Pause('cycle_budget_wait',current+timedelta(seconds=cfg['cycle_interval_seconds']))
        month=[e for e in entries if stamp(e['at']).strftime('%Y-%m')==current.strftime('%Y-%m')]
        # UTC and adjacent provider billing zones can differ at month boundaries.
        # A rolling 31-day window is conservatively included as well.
        window=[e for e in entries if current-stamp(e['at'])<timedelta(days=31)]
        units=cfg.get('credits_per_request',0) if cfg['source']=='serper_google_shopping' else 1
        if type(units) is not int or units<1:raise ProviderError('provider_credit_or_cost_budget_exhausted')
        charged=max(sum(e.get('reserved_units',1) for e in month),sum(e.get('reserved_units',1) for e in window))
        cost=sum(Decimal(e['reserved_cost']) for e in window)
        if cfg['source'] in ('searchapi_google_shopping','serper_google_shopping') and (charged+units>cfg['max_units_per_month'] or
            cost+Decimal(cfg['cost_per_request'])>Decimal(cfg['max_cost_per_month'])):
            raise ProviderError('provider_credit_or_cost_budget_exhausted')
        fingerprint=hashlib.sha256(json.dumps([method,url,params],sort_keys=True,default=str).encode()).hexdigest()
        entry={'at':current.isoformat(),'status':'reserved','cycle_id':self.cycle_id,'task_id':self.task_id,
               'request_hash':fingerprint,'reserved_units':units,'reserved_cost':cfg['cost_per_request']}
        entries.append(entry);self.save();return entry

    def request(self,method,url,**options):
        self.route(method,url)
        entry=self.reserve(method,url,options.get('json',options.get('params',{})))
        try:
            response=self.session.request(method,url,timeout=(5,30),allow_redirects=False,stream=True,**options)
        except requests.RequestException:
            entry['status']='network_uncertain';entry['failed_at']=self.clock().isoformat()
            due=self.clock()+timedelta(seconds=max(7200,self.cfg['cycle_interval_seconds']))
            self.state['not_before']=due.isoformat();self.save()
            raise Pause('network_error_request_outcome_uncertain',due) from None
        try:
            code=response.status_code;entry['status']=code;self.save()
            if code==429 or code==503 and response.headers.get('Retry-After'):
                due=retry_after(response.headers.get('Retry-After'),self.clock())
                self.state['not_before']=due.isoformat();self.save();raise Pause('provider_retry_after',due)
            if code in (401,403) or 300<=code<400:
                # First eBay data 401 can invalidate and remint exactly once.
                if not (code==401 and self.cfg['source']=='ebay_browse' and '/buy/browse/' in url):
                    self.state['hold']='auth_or_redirect_review_required';self.save()
                raise ProviderError('provider_access_refused',code)
            if code in (408,425,500,502,503,504):
                raise Pause('provider_transient_failure',self.clock()+timedelta(seconds=60))
            if code!=200:raise ProviderError('provider_HTTP_error',code)
            chunks=[];size=0
            try:
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>4_000_000:raise ProviderError('provider_response_too_large')
                    chunks.append(chunk)
            except requests.RequestException:
                due=self.clock()+timedelta(seconds=max(7200,self.cfg['cycle_interval_seconds']))
                entry['status']='network_uncertain';self.state['not_before']=due.isoformat();self.save()
                raise Pause('response_outcome_uncertain',due) from None
            try:body=json.loads(b''.join(chunks),parse_float=Decimal)
            except (ValueError,UnicodeError):
                self.state['hold']='invalid_JSON_review_required';self.save();raise ProviderError('provider_invalid_JSON') from None
            if not isinstance(body,dict) or body.get('error') or body.get('errors') or body.get('success') is False:
                self.state['hold']='provider_error_review_required';self.save();raise ProviderError('provider_error_or_schema')
            if self.cfg['source']=='serper_google_shopping':
                actual=body.get('credits')
                if type(actual) is int and actual>entry['reserved_units']:
                    entry.update(reported_credits=actual,reserved_units=actual)
                    self.state['hold']='provider_credit_cost_review_required';self.save()
                    raise ProviderError('provider_credit_reservation_exceeded')
            entry['outcome']='success';self.save();return body
        finally:response.close()

    def get_json(self,url,**options):return self.request('GET',url,**options)
    def post_json(self,url,**options):return self.request('POST',url,**options)
    def close(self):self.session.close()
