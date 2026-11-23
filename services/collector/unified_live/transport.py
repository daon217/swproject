"""Pinned public IP + TLS hostname checks, durable budgets, no redirects or cookies."""
import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from services.collector.domeggook_live.domeggook_delivery import atomic,load,utcnow
from services.collector.marketplace_live.config import stamp
from services.collector.marketplace_live.http import retry_after
from .policy import url,grant,AGENT

class Wait(RuntimeError):
    def __init__(self,reason,until=None,hold=False):super().__init__(reason);self.until=until;self.hold=hold

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,address):super().__init__(host,timeout=20,context=ssl.create_default_context());self.address=address
    def connect(self):
        sock=socket.create_connection((self.address,443),self.timeout)
        try:self.sock=self._context.wrap_socket(sock,server_hostname=self.host)
        except BaseException:sock.close();raise

def public_address(host):
    addresses={row[4][0] for row in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):raise Wait('nonpublic_DNS_forbidden',hold=True)
    return sorted(addresses)[0]

class SafeHTTP:
    def __init__(self,cfg,root,clock=utcnow):
        self.cfg=cfg;self.clock=clock;self.host=urlsplit(cfg['base_url']).hostname
        self.path=Path(root)/'url_request_ledger.json';self.robots=None;self.robots_at=None
        self.state=load(self.path,{'version':1,'source':cfg['source'],'requests':[],'hold':None,'not_before':None})
        if self.state.get('version')!=1 or self.state.get('source')!=cfg['source']:raise ValueError('ledger_mismatch_no_reset')
        if any(e['status']=='reserved' for e in self.state['requests']):
            for e in self.state['requests']:
                if e['status']=='reserved':e['status']='interrupted_uncertain'
            self.state['hold']='request_outcome_uncertain_review_required';self.save()
    def save(self):atomic(self.path,self.state)
    def permitted(self,target):return self.cfg['enabled'] and grant(self.cfg,self.clock())
    def method_permitted(self,method,target,body):return method=='GET'
    def user_agent(self):return AGENT
    def reserve(self,target):
        now=self.clock()
        if not self.permitted(target):raise Wait('storage_and_terms_grant_required',hold=True)
        if self.state['hold']:raise Wait(self.state['hold'],hold=True)
        if self.state['not_before'] and stamp(self.state['not_before'])>now:raise Wait('request_wait',stamp(self.state['not_before']))
        entries=self.state['requests']
        if entries:
            due=stamp(entries[-1]['at'])+timedelta(seconds=self.cfg['request_interval_seconds'])
            if due>now:raise Wait('rate_wait',due)
        for secs,key in ((3600,'requests_per_hour'),(86400,'requests_per_24h')):
            recent=sorted(stamp(e['at']) for e in entries if now-stamp(e['at'])<timedelta(seconds=secs))
            if len(recent)>=self.cfg[key]:raise Wait('budget_wait',recent[-self.cfg[key]]+timedelta(seconds=secs))
        entry={'at':now.isoformat(),'url_sha256':hashlib.sha256(target.encode()).hexdigest(),'status':'reserved'}
        entries.append(entry);self.save();return entry
    def _get(self,target):return self._request('GET',target)
    def _request(self,method,target,body=None):
        target=url(target,self.host)
        if not self.method_permitted(method,target,body):raise ValueError('read_only_transport_method_required')
        entry=self.reserve(target);conn=None
        entry['method']=method
        if body is not None:entry['request_sha256']=hashlib.sha256(body if isinstance(body,bytes) else body.encode()).hexdigest()
        self.save()
        try:
            address=public_address(self.host);conn=PinnedHTTPS(self.host,address)
            p=urlsplit(target);headers={'User-Agent':self.user_agent(),'Accept':'text/html,text/plain,application/json','Accept-Encoding':'identity'}
            if method!='GET':headers['Content-Type']='application/json'
            conn.request(method,p.path+('?' + p.query if p.query else ''),body=body,headers=headers)
            response=conn.getresponse();entry['status']=response.status;self.save()
            if response.status==429 or response.status==503 and response.getheader('Retry-After'):
                due=retry_after(response.getheader('Retry-After'),self.clock());self.state['not_before']=due.isoformat();self.save();raise Wait('retry_after',due)
            if response.status in (401,403) or 300<=response.status<400:
                self.state['hold']='access_or_redirect_review_required';self.save();raise Wait(self.state['hold'],hold=True)
            if response.status>=500:raise Wait('server_error',self.clock()+timedelta(seconds=60))
            if response.status in (404,410):return response.status,'',response.getheader('Content-Type','')
            if response.status!=200:raise Wait('HTTP_error',hold=True)
            if response.getheader('Content-Encoding','identity') not in ('','identity'):raise Wait('encoded_response_unsupported',hold=True)
            chunks=[];size=0;start=time.monotonic()
            while True:
                if time.monotonic()-start>30:raise TimeoutError()
                chunk=response.read(65536)
                if not chunk:break
                size+=len(chunk)
                if size>2_000_000:raise Wait('response_too_large',hold=True)
                chunks.append(chunk)
            # UTF-8 is conservative: legacy encodings need a reviewed adapter.
            text=b''.join(chunks).decode('utf-8-sig')
            return 200,text,response.getheader('Content-Type','')
        except Wait:raise
        except (OSError,http.client.HTTPException,UnicodeError):
            entry['status']='network_uncertain';self.state['hold']='request_outcome_uncertain_review_required';self.save()
            raise Wait(self.state['hold'],hold=True) from None
        finally:
            if conn:conn.close()
    def fetch(self,target):
        target=url(target,self.host)
        if not self.robots or not self.robots_at or (self.clock()-self.robots_at).total_seconds()>3600:
            code,text,_=self._get('https://'+self.host+'/robots.txt')
            self.robots=RobotFileParser()
            self.robots.parse(text.splitlines() if code==200 else ['User-agent: *','Allow: /'] if code==404 else ['User-agent: *','Disallow: /'])
            self.robots_at=self.clock()
        if not self.robots.can_fetch(AGENT,target):raise Wait('robots_disallowed',hold=True)
        delay=self.robots.crawl_delay(AGENT) or self.robots.crawl_delay('*')
        if delay and self.state['requests']:
            due=stamp(self.state['requests'][-1]['at'])+timedelta(seconds=delay)
            if due>self.clock():raise Wait('robots_crawl_delay',due)
        rate=self.robots.request_rate(AGENT) or self.robots.request_rate('*')
        if rate:
            recent=sorted(stamp(e['at']) for e in self.state['requests'] if self.clock()-stamp(e['at'])<timedelta(seconds=rate.seconds))
            if len(recent)>=rate.requests:raise Wait('robots_request_rate',recent[-rate.requests]+timedelta(seconds=rate.seconds))
        code,text,mime=self._get(target)
        if code==200 and not any(k in mime.lower() for k in ('html','json','javascript','text/','xml')):raise Wait('unsupported_content_type',hold=True)
        return code,text
    def close(self):pass
