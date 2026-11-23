"""Reuse the existing durable HTTP outbox engine; never import database code."""
import copy
import uuid
from datetime import datetime
from pathlib import Path
from services.collector.domeggook_live.domeggook_delivery import DeliveryPipeline, atomic, load, digest, utcnow
from services.collector.domeggook_live.domeggook_backend import HTTPBackendTransport
from .config import rights
from .normalize import validate_body
from .config import stamp
from .http import retry_after

class RetryAwareBackend(HTTPBackendTransport):
    def __init__(self,base_url,token,clock):
        super().__init__(base_url,token)
        self.clock=clock;self.retry_not_before=None
        def observe(response,*_,**__):
            if response.status_code in (429,503) and response.headers.get('Retry-After'):
                self.retry_not_before=retry_after(response.headers['Retry-After'],clock())
        self.session.hooks['response'].append(observe)

class Outbox(DeliveryPipeline):
    synthetic_only=False
    def __init__(self,cfg,root,transport=None,clock=utcnow):
        self.cfg=copy.deepcopy(cfg);self.source=cfg['source'];self.clock=clock
        self.settings=dict(cfg.get('backend_delivery',{}),mode='live_authorized',
                           allowed_product_hosts=cfg['allowed_product_hosts'],currencies=cfg['currencies'])
        # Respect a Retry-After before another entry is attempted in this flush.
        self.settings['max_requests_per_flush']=1
        self.cfg['backend_delivery']=self.settings
        self.path=Path(root)/'backend_outbox.json';self.skipped=0;self.transport=transport;self.test=False
        self.enabled=cfg['backend_enabled'] and cfg['backend_owner_approved']
        self.ready=self.enabled and cfg['price_semantics_confirmed'] and rights(self.cfg,clock(),storage=True)
        self.state=load(self.path,{'version':1,'source':self.source,'run_id':str(uuid.uuid4()),'entries':{},'hold':None,'totals':{}})
        if self.state.get('synthetic_only') and not self.synthetic_only:raise ValueError('synthetic_outbox_forbidden_in_live_delivery')
        if self.state.get('source')!=self.source:raise ValueError('outbox_source_mismatch')
        uuid.UUID(self.state['run_id'])
        if self.enabled:
            self.prune();self.save()

    def permitted_body(self,entry):
        return (self.cfg['price_semantics_confirmed'] and rights(self.cfg,self.clock(),storage=True)
                and entry['body'].get('source')==self.source)

    def stage(self,normalized):
        body=normalized.get('observation')
        if not body:return {'status':'incomplete_native_fields'}
        if not self.ready or not self.permitted_body({'body':body}):return {'status':'permission_blocked'}
        validate_body(body,self.cfg);key=body['observation_key'];sha=digest(body)
        old=self.state['entries'].get(key)
        if old:
            if old['sha256']!=sha:raise ValueError('immutable_outbox_payload_conflict')
            return {'status':old['status'],'duplicate':True}
        if self.backpressure():return {'status':'backpressure_needs_reobserve'}
        self.state['entries'][key]={'body':copy.deepcopy(body),'sha256':sha,'status':'pending','attempts':0,
                                  'created_at':self.clock().isoformat()}
        self.count('staged');self.save()
        return {'status':'pending','observation_key':key}

    def flush(self,stop=None):
        if self.state.get('synthetic_only'):raise ValueError('synthetic_outbox_cannot_send_HTTP')
        # Avoid constructing a token-bearing transport for a read-only status or
        # a source without an actual staged payload.
        revoked=self.state['totals'].get('revoked',0)
        self.prune()
        if self.state['totals'].get('revoked',0)!=revoked:self.save()
        if not self.enabled or not self.ready or self.state['hold'] or stop is not None and stop.is_set():return self.report()
        actionable=any(e['status'] in ('pending','retry_wait','sending') and 'body' in e and
                       (not e.get('next_attempt_at') or stamp(e['next_attempt_at'])<=self.clock())
                       for e in self.state['entries'].values())
        if not actionable:return self.report()
        if self.state.get('not_before') and stamp(self.state['not_before'])>self.clock():
            return self.report()
        if self.ready and not self.state['hold'] and self.pending_count() and self.transport is None:
            import os
            self.transport=RetryAwareBackend(self.settings.get('base_url',''),os.environ.get('KKULPICK_BACKEND_TOKEN',''),self.clock)
        result=super().flush(stop=stop)
        due=getattr(self.transport,'retry_not_before',None)
        if isinstance(due,datetime) and due>self.clock():
            self.state['not_before']=due.isoformat();self.save()
        return result
