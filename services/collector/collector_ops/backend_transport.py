"""Backend-only routing. Internal HTTP never shares external collection transport policy."""
import os,re
from urllib.parse import urlsplit
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import InvalidURL
from urllib3.connection import HTTPConnection
from urllib3.connectionpool import HTTPConnectionPool
from services.collector.domeggook_live.network import PublicHTTPSAdapter,DenyHTTPAdapter
from services.collector.marketplace_live.delivery import RetryAwareBackend
from services.collector.marketplace_live.http import retry_after

ROUTE=re.compile(r'/internal/v2/(?:crawl-runs/[0-9a-f-]{36}/(?:observations|extensions)|listing-checks)')

def origin_check(value,origin):
    p=urlsplit(value);o=urlsplit(origin)
    if (p.scheme,p.hostname,p.port)!=(o.scheme,o.hostname,o.port) or p.username or p.password or p.query or p.fragment or not ROUTE.fullmatch(p.path):
        raise InvalidURL('backend_origin_and_route_must_match')


class OriginHTTPSAdapter(PublicHTTPSAdapter):
    def __init__(self,origin):self.origin=origin;super().__init__(max_retries=0)
    def send(self,request,**kwargs):
        origin_check(request.url,self.origin)
        return super().send(request,**kwargs)


def configured_http_origin():
    """The administrator's URL is the backend authority; no topology discovery or approval."""
    value=os.environ.get('COLLECTOR_BACKEND_BASE_URL','')
    if os.environ.get('COLLECTOR_BACKEND_TRANSPORT')!='internal_http' or os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes' or not value:
        raise InvalidURL('explicit_HTTP_backend_and_enabled_delivery_required')
    if not isinstance(value,str) or any(ord(c)<33 for c in value) or '\\' in value:raise InvalidURL('valid_backend_origin_required')
    p=urlsplit(value)
    if p.scheme!='http' or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('','/'):
        raise InvalidURL('HTTP_backend_origin_only_required')
    p.port  # Validate a supplied port, without forcing a particular port or network.
    return requests.Request('POST',value).prepare().url.rstrip('/')


class InternalHTTPAdapter(HTTPAdapter):
    """Ordinary HTTP connection with exact-origin/route and credential forwarding guards."""
    def __init__(self,origin):self.origin=origin;super().__init__(max_retries=0)
    def init_poolmanager(self,*args,**kwargs):
        class QuietHTTPConnection(HTTPConnection):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);self.debuglevel=0
        class BackendHTTPPool(HTTPConnectionPool):ConnectionCls=QuietHTTPConnection
        super().init_poolmanager(*args,**kwargs)
        self.poolmanager.pool_classes_by_scheme=dict(self.poolmanager.pool_classes_by_scheme,http=BackendHTTPPool)
    def proxy_manager_for(self,*args,**kwargs):raise InvalidURL('backend_proxy_forbidden')
    def send(self,request,**kwargs):
        origin_check(request.url,self.origin)
        if configured_http_origin()!=self.origin:raise InvalidURL('backend_configuration_changed')
        if kwargs.get('proxies'):raise InvalidURL('backend_proxy_forbidden')
        return super().send(request,**kwargs)


class RoutedBackend(RetryAwareBackend):
    def __init__(self,base_url,token,clock):
        mode=os.environ.get('COLLECTOR_BACKEND_TRANSPORT','https');p=urlsplit(base_url)
        self.internal_http=False
        if p.path not in ('','/') or p.query or p.fragment or p.username or p.password:raise ValueError('backend_origin_only_required')
        if mode=='https' and p.scheme=='https' and p.port in (None,443):
            super().__init__(base_url,token,clock)
            self.session.mount('https://',OriginHTTPSAdapter(self.base))
            self.session.mount('http://',DenyHTTPAdapter(max_retries=0))
        elif mode=='internal_http' and p.scheme=='http':
            configured=configured_http_origin()
            if requests.Request('POST',base_url).prepare().url.rstrip('/')!=configured:raise ValueError('only_configured_backend_origin_allowed')
            self.internal_http=True
            if not isinstance(token,str) or len(token)<32 or any(not 33<=ord(c)<=126 for c in token):raise ValueError('valid_backend_token_required')
            self.base=configured;self.clock=clock;self.retry_not_before=None
            self.session=requests.Session();self.session.trust_env=False
            self.session.headers.update({'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            self.session.mount('http://',InternalHTTPAdapter(self.base))
            self.session.mount('https://',DenyHTTPAdapter(max_retries=0))
            def observe(response,*_,**__):
                if response.status_code in (429,503) and response.headers.get('Retry-After'):
                    self.retry_not_before=retry_after(response.headers['Retry-After'],clock())
            self.session.hooks['response'].append(observe)
        else:raise ValueError('backend_transport_mode_or_scheme_not_approved')
    def __call__(self,path,body):
        if os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes':return 403,{}
        if self.internal_http:
            try:
                if configured_http_origin()!=self.base:return 403,{}
            except (ValueError,requests.RequestException):return 403,{}
        return super().__call__(path,body)


def build_backend(base_url,token,clock):
    # Only backend destination is overridden. Product/API URLs never read these variables.
    target=os.environ.get('COLLECTOR_BACKEND_BASE_URL') or base_url
    return RoutedBackend(target,token,clock)


class DeferredBackend:
    """Domeggook's existing queue constructs transports eagerly; postpone only transport creation."""
    def __init__(self,base_url,clock):self.base_url=base_url;self.clock=clock;self.actual=None
    def __call__(self,path,body):
        if os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes':return 403,{}
        if self.actual is None:
            from .backend import configure_CA
            self.actual=configure_CA(build_backend(self.base_url,os.environ.get('KKULPICK_BACKEND_TOKEN',''),self.clock))
        return self.actual(path,body)
    def close(self):
        if self.actual:self.actual.close()


def endpoint_plan(configured_url):
    """Pure preflight for the same effective destination used by build_backend.

    No provider entitlement is inferred here, and no network or secret is read.
    """
    mode=os.environ.get('COLLECTOR_BACKEND_TRANSPORT','https')
    target=os.environ.get('COLLECTOR_BACKEND_BASE_URL') or configured_url
    reasons=[]
    try:
        if mode=='internal_http':
            configured_http_origin()  # Explicit URL and existing delivery switch.
        elif mode=='https':
            p=urlsplit(target)
            if (p.scheme!='https' or not p.hostname or p.port not in (None,443) or
                p.username or p.password or p.query or p.fragment or p.path not in ('','/') or
                any(ord(c)<33 for c in target) or '\\' in target):
                raise ValueError('approved_HTTPS_team_API_endpoint_required')
            if p.hostname.endswith(('.invalid','.example','.test')):
                raise ValueError('placeholder_team_API_endpoint_forbidden')
            from pathlib import Path
            if os.environ.get('COLLECTOR_CA_FILE') and not Path(os.environ['COLLECTOR_CA_FILE']).is_file():
                raise ValueError('trusted_CA_file_missing')
        else:raise ValueError('backend_transport_mode_invalid')
    except (ValueError,TypeError):
        reasons.append('explicit_internal_HTTP_endpoint_and_delivery_switch_required' if mode=='internal_http' else
            'approved_HTTPS_team_API_endpoint_required' if mode=='https' else 'backend_transport_mode_invalid')
    return {'transport':mode,'ready':not reasons,'reasons':reasons,'environment_override':bool(os.environ.get('COLLECTOR_BACKEND_BASE_URL'))}
