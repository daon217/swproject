"""Faster polling is opt-in; existing shared eBay budgets and uncertainty waits remain."""
from contextlib import ExitStack,contextmanager
from datetime import timedelta
from pathlib import Path
from services.collector.domeggook_live.runtime import FileState
from services.collector.domeggook_live.domeggook_delivery import load
from services.collector.marketplace_live.adapters import Adapter,EBAY
from services.collector.marketplace_live.http import ProviderHTTP
from services.collector.marketplace_live.normalize import validate_body
from services.collector.collector_ops.runtime import OpsWorker
from .backend import ApprovedOutbox
from services.collector.used_market_live.ebay_used import UsedAdapter,used_config
from .changes import ChangeDelivery,rekey
from .policy import interval

def used_interval(schedule):
    if schedule.get('mode')!='used' or not schedule.get('policy_reference'):
        return 7200,'provider_poll_permission_unconfirmed'
    seconds=interval(schedule)
    return seconds,'source_policy_minimum' if seconds>60 else 'approved_60_second_poll'

class DetailFields:
    def normalize(self,row,at):
        result=super().normalize(row,at)
        from .matching import provider_profile
        result.setdefault('metadata',{})['matching_profile']=provider_profile(row,self.cfg['source'],result.get('url') or '')
        description=row.get('shortDescription') or row.get('description')
        if result['observation'] and isinstance(description,str):
            from .parser import plain
            body=result['observation'];body['description']=plain(description)
            if 'description' not in body['field_presence']:body['field_presence'].append('description')
            rekey(body);validate_body(body,self.cfg)
        return result

class LatestUsedAdapter(DetailFields,UsedAdapter):
    def ebay_get(self,target,params=None):
        if target==EBAY+'item_summary/search':params=dict(params or {},sort='newlyListed',fieldgroups='EXTENDED')
        return super().ebay_get(target,params)
    def search(self,query,page):
        rows,more=super().search(query,page)
        self.origin_dates=[r['itemOriginDate'] for r in rows if isinstance(r.get('itemOriginDate'),str)]
        return rows,more

class FullAdapter(DetailFields,Adapter):pass

class ScheduledWorker(OpsWorker):
    def __init__(self,*args,schedule=None,**kwargs):
        self.schedule=schedule or {};super().__init__(*args,**kwargs)
    def complete_if_empty(self):
        super().complete_if_empty()
        if not self.state['tasks'] and self.cfg.get('collection_profile')=='ebay_used':
            seconds,_=used_interval(self.schedule)
            self.state['next_cycle_at']=(self.clock()+timedelta(seconds=seconds)).isoformat()
    def accept(self,row):
        # The base worker counts only staging results as success. Track content skips separately.
        before=self.delivery.data['totals'].get('unchanged',0)
        super().accept(row)
        if self.delivery.data['totals'].get('unchanged',0)>before:self.count('products_unchanged')
    def execute(self,task):
        result=super().execute(task)
        if task['kind']=='search' and self.cfg.get('collection_profile')=='ebay_used':
            from services.collector.marketplace_live.config import stamp
            dates=getattr(self.adapter.adapter,'origin_dates',[])
            watermarks=self.state.setdefault('latest_listing_watermarks',{})
            key=str(task['query_index'])
            parsed=[stamp(v).isoformat() for v in dates]
            if parsed:watermarks[key]=max(parsed+[watermarks[key]] if key in watermarks else parsed)
        return result
    def report(self):
        result=super().report()
        seconds,reason=used_interval(self.schedule) if self.cfg.get('collection_profile')=='ebay_used' else (self.cfg['cycle_interval_seconds'],'general_7200_seconds')
        result.update(effective_interval_seconds=seconds,interval_reason=reason,content_changes=self.delivery.data['totals'],
            schedule_semantics='next_cycle_after_previous_completion; rate_budget_and_backoff_may_delay',
            all_items_refreshed_each_minute=False)
        return result

@contextmanager
def open_worker(cfg,root,used=False,schedule=None):
    root=Path(root);source=cfg['source'];workroot=root/'ebay_used' if used else root
    if used:used_config(cfg)
    with ExitStack() as stack:
        stack.enter_context(FileState(root/source/'lock').lock())
        if used:stack.enter_context(FileState(workroot/source/'lock').lock())
        old=load(workroot/source/'checkpoint.json',{})
        shared=load(root/source/'request_ledger.json',{'requests':[]})
        if old.get('ledger_size',0)>len(shared['requests']):raise ValueError('missing_shared_history_no_reset')
        http=ProviderHTTP(cfg,root/source)
        try:
            cls=LatestUsedAdapter if used else FullAdapter
            box=ChangeDelivery(ApprovedOutbox(cfg,workroot/source),workroot/source)
            worker=ScheduledWorker(cfg,workroot,http=http,adapter=cls(cfg,http),delivery=box,schedule=schedule)
        except BaseException:http.close();raise
        try:yield worker
        finally:worker.stop.set();worker.close()
