"""Backend-only routing. Internal HTTP never shares external collection transport policy."""
import os,re
from urllib.parse import urlsplit
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import InvalidURL
from urllib3.connection import HTTPConnection
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.util.connection import create_connection
from services.collector.domeggook_live.network import PublicHTTPSAdapter,DenyHTTPAdapter
from services.collector.marketplace_live.delivery import RetryAwareBackend
from services.collector.marketplace_live.http import retry_after
from .internal_network import InternalPolicy

ROUTE=re.compile(r'/internal/v2/crawl-runs/[0-9a-f-]{36}/observations')

def origin_check(value,origin):
    p=urlsplit(value);o=urlsplit(origin)
    if (p.scheme,p.hostname,p.port)!=(o.scheme,o.hostname,o.port) or p.username or p.password or p.query or p.fragment or not ROUTE.fullmatch(p.path):
        raise InvalidURL('backend_origin_and_route_must_match')


class OriginHTTPSAdapter(PublicHTTPSAdapter):
    def __init__(self,origin):self.origin=origin;super().__init__(max_retries=0)
    def send(self,request,**kwargs):
        origin_check(request.url,self.origin)
        return super().send(request,**kwargs)


class InternalHTTPAdapter(HTTPAdapter):
    def __init__(self,policy,origin):self.policy=policy;self.origin=origin;super().__init__(max_retries=0)
    def init_poolmanager(self,*args,**kwargs):
        policy=self.policy
        class PinnedInternalConnection(HTTPConnection):
            def _new_conn(self):
                try:
                    destination,source=policy.check()
                    if self.host!=policy.host or self.port!=policy.port:raise ValueError('internal_origin_mismatch')
                    sock=create_connection((destination,self.port),timeout=self.timeout,source_address=(source,0),socket_options=self.socket_options)
                    if sock.getpeername()[0]!=destination or sock.getsockname()[0]!=source:
                        sock.close();raise ValueError('internal_peer_or_source_mismatch')
                    self.debuglevel=0;return sock
                except (OSError,ValueError,KeyError):raise NewConnectionError(self,'reviewed_internal_connection_blocked_or_failed') from None
        class InternalPool(HTTPConnectionPool):ConnectionCls=PinnedInternalConnection
        super().init_poolmanager(*args,**kwargs)
        self.poolmanager.pool_classes_by_scheme=dict(self.poolmanager.pool_classes_by_scheme,http=InternalPool)
    def proxy_manager_for(self,*args,**kwargs):raise InvalidURL('backend_proxy_forbidden')
    def send(self,request,**kwargs):
        origin_check(request.url,self.origin)
        if kwargs.get('proxies'):raise InvalidURL('backend_proxy_forbidden')
        self.policy.check()  # Also recheck reused connections, freshness, revocation and direct route.
        return super().send(request,**kwargs)


class RoutedBackend(RetryAwareBackend):
    def __init__(self,base_url,token,clock):
        mode=os.environ.get('COLLECTOR_BACKEND_TRANSPORT','https');p=urlsplit(base_url)
        self.policy=None
        if p.path not in ('','/') or p.query or p.fragment or p.username or p.password:raise ValueError('backend_origin_only_required')
        if mode=='https' and p.scheme=='https' and p.port in (None,443):
            super().__init__(base_url,token,clock)
            self.session.mount('https://',OriginHTTPSAdapter(self.base))
            self.session.mount('http://',DenyHTTPAdapter(max_retries=0))
        elif mode=='internal_http' and p.scheme=='http':
            self.policy=InternalPolicy(base_url)
            if not isinstance(token,str) or len(token)<32 or any(not 33<=ord(c)<=126 for c in token):raise ValueError('valid_backend_token_required')
            self.base=base_url.rstrip('/');self.clock=clock;self.retry_not_before=None
            self.session=requests.Session();self.session.trust_env=False
            self.session.headers.update({'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            self.session.mount('http://',InternalHTTPAdapter(self.policy,self.base))
            self.session.mount('https://',DenyHTTPAdapter(max_retries=0))
            def observe(response,*_,**__):
                if response.status_code in (429,503) and response.headers.get('Retry-After'):
                    self.retry_not_before=retry_after(response.headers['Retry-After'],clock())
            self.session.hooks['response'].append(observe)
        else:raise ValueError('backend_transport_mode_or_scheme_not_approved')
    def __call__(self,path,body):
        if os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes':return 403,{}
        if self.policy:
            try:self.policy.check()
            except Exception:return 403,{}  # Known preflight rejection: hold without sending token/body.
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
