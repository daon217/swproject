"""Reuse licensed Domeggook discovery and food gates, add content-based queue dedup."""
from pathlib import Path
import os
from services.collector.collector_ops.dome import FoodDelivery
from services.collector.domeggook_live.domeggook_backend import prepare_observation
from .changes import ChangeDelivery

class DomeBridge(FoodDelivery):
    source='domeggook'
    def stage(self,result):
        if '_native_row' in result:return super().stage(result['_native_row'])
        from services.collector.domeggook_live.domeggook_backend import validate_body
        from services.collector.domeggook_live.domeggook_delivery import digest
        import copy
        body=result['observation'];validate_body(body,self.cfg)
        if not self.ready or not self.permitted_body({'body':body}):return {'status':'permission_blocked'}
        key=body['observation_key'];sha=digest(body);old=self.state['entries'].get(key)
        if old:
            if old['sha256']!=sha:raise ValueError('immutable_outbox_payload_conflict')
            return {'status':old['status'],'duplicate':True}
        if self.backpressure():return {'status':'backpressure_needs_reobserve'}
        self.state['entries'][key]={'body':copy.deepcopy(body),'sha256':sha,'status':'pending','attempts':0,'created_at':self.clock().isoformat()}
        self.count('staged');self.save();return {'status':'pending','observation_key':key}
    def flush(self,stop=None):
        if os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes':return self.report()
        return super().flush(stop)

class DomeContent:
    def __init__(self,box,root):self.gate=ChangeDelivery(box,root)
    def __getattr__(self,k):return getattr(self.gate,k)
    def stage(self,row):
        try:body=prepare_observation(row,self.cfg,selected_domain=self.settings['selected_domain'],condition=self.settings['condition'])
        except (PermissionError,ValueError):return {'status':'native_fields_or_permissions_required'}
        from .matching import provider_profile
        result=self.gate.stage({'observation':body,'_native_row':row,'seller':row.get('seller'),
            'metadata':{'matching_profile':provider_profile(row,'domeggook',row.get('product_url') or '')}})
        if result['status']=='unchanged_skipped':
            result=dict(result,status=self.state['entries'][result['observation_key']]['status'],unchanged=True)
        return result
    def report(self):
        return dict(self.gate.report(),content_changes=self.gate.data['totals'])

def run(cfg,root,stop,once=False):
    from services.collector.domeggook_live.domeggook_operations import configuration,ROOT
    from services.collector.domeggook_live.domeggook_discovery import QueueClient,validate_discovery,queue_loop
    from services.collector.domeggook_live.domeggook_watch_delivery import DeliveryDiscoveryRun
    from services.collector.domeggook_live.runtime import FileState
    if Path(ROOT).resolve()!=Path(root).resolve()/'domeggook_ops':raise ValueError('domeggook_existing_state_layout_required')
    base=configuration();profile=cfg.get('backend_profile',{})
    if set(profile)-{'backend_enabled','backend_owner_approved','price_semantics_confirmed','storage_grants','backend_delivery'}:raise ValueError('invalid_backend_profile')
    base.update(profile);base['food_policy']=cfg.get('food_policy','hold_until_contract');base['cycle_interval_seconds']=max(7200,base['cycle_interval_seconds'])
    validate_discovery(base)
    with FileState(ROOT/'state').lock():
        client=QueueClient(base);box=None
        try:
            box=DomeContent(DomeBridge(base,ROOT/'backend_delivery'),ROOT/'backend_delivery')
            worker=DeliveryDiscoveryRun(base,client,ROOT,delivery=box);worker.stop=stop
            return queue_loop(worker,'combined',watch=not once,cycles=1 if once else None)
        finally:
            client.close()
            if box:box.close()
