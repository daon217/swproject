"""Public HTTPS connections pinned after DNS validation; no proxy or HTTP fallback."""
import ipaddress
import socket
from urllib.parse import urlsplit
from requests.adapters import HTTPAdapter
from requests.exceptions import InvalidURL
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool
from urllib3.exceptions import NewConnectionError
from urllib3.util.connection import create_connection


def public_ips(host,port=443):
    addresses={r[4][0] for r in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise OSError('public_DNS_required')
    return sorted(addresses)


class PublicHTTPSConnection(HTTPSConnection):
    def _new_conn(self):
        try:
            if self.port!=443 or self.proxy is not None:raise OSError('public_HTTPS_no_proxy_required')
            address=public_ips(self._dns_host,self.port)[0]
            sock=create_connection((address,self.port),timeout=self.timeout,source_address=self.source_address,socket_options=self.socket_options)
            if sock.getpeername()[0]!=address:sock.close();raise OSError('public_peer_mismatch')
            self.debuglevel=0
            return sock
        except OSError:raise NewConnectionError(self,'public_HTTPS_connection_blocked_or_failed') from None


class PublicHTTPSPool(HTTPSConnectionPool):
    ConnectionCls=PublicHTTPSConnection


class DenyHTTPAdapter(HTTPAdapter):
    def send(self,*args,**kwargs):raise InvalidURL('HTTPS_required')


class PublicHTTPSAdapter(HTTPAdapter):
    def init_poolmanager(self,*args,**kwargs):
        super().init_poolmanager(*args,**kwargs)
        self.poolmanager.pool_classes_by_scheme=dict(self.poolmanager.pool_classes_by_scheme,https=PublicHTTPSPool)
    def proxy_manager_for(self,*args,**kwargs):raise InvalidURL('proxy_forbidden')
    def send(self,request,**kwargs):
        p=urlsplit(request.url)
        if p.scheme!='https' or p.port not in (None,443) or p.username or p.password or kwargs.get('verify') is False or kwargs.get('proxies'):
            raise InvalidURL('verified_public_HTTPS_required')
        return super().send(request,**kwargs)


def secure_public_session(session):
    session.trust_env=False
    session.mount('https://',PublicHTTPSAdapter(max_retries=0))
    session.mount('http://',DenyHTTPAdapter(max_retries=0))
    return session
