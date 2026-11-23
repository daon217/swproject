"""One account writer: both eBay schedules share a single in-memory/persisted ledger."""
from contextlib import ExitStack,contextmanager
from pathlib import Path
from services.collector.domeggook_live.runtime import FileState
from services.collector.marketplace_live.http import ProviderHTTP
from services.collector.marketplace_live.config import rights
from services.collector.domeggook_live.domeggook_delivery import utcnow,load
from .used import ScheduledWorker,FullAdapter,LatestUsedAdapter
from .backend import ApprovedOutbox
from .changes import ChangeDelivery

class AccountWorker:
    def __init__(self,general,used,http):
        import threading
        self.general=general;self.used=used;self.http=http;self.stop=threading.Event()
    def step(self):
        for worker in (self.used,self.general):
            worker.stop=self.stop;worker.http.stop=self.stop
            try:worker.step()
            except Exception:
                # Schema/state failure in one catalogue must not reset its history or stop the other.
                worker.state['hold']='account_member_runtime_review_required';worker.save()
        return self.report()
    def report(self):return {'provider':'ebay_account','hold':self.http.state.get('hold'),
        'members':{'ebay':self.general.report(),'ebay_used':self.used.report()},'HTTP_attempts':len(self.http.state['requests']),
        'shared_ledger_single_writer':True,'general_interval_seconds':7200}
    def close(self):self.stop.set();self.general.close();self.used.close()

@contextmanager
def account_context(general_cfg,used_cfg,root,schedule):
    root=Path(root);source='ebay_browse'
    from services.collector.used_market_live.ebay_used import used_config
    used_config(used_cfg)
    with ExitStack() as stack:
        stack.enter_context(FileState(root/source/'lock').lock())
        stack.enter_context(FileState(root/'ebay_used'/source/'lock').lock())
        active=used_cfg if used_cfg['enabled'] and rights(used_cfg,utcnow()) else general_cfg
        shared=dict(active)
        for key in ('requests_per_hour','requests_per_24h','requests_per_cycle'):
            shared[key]=min(general_cfg[key],used_cfg[key])
        shared['request_interval_seconds']=max(general_cfg['request_interval_seconds'],used_cfg['request_interval_seconds'])
        http=ProviderHTTP(shared,root/source)
        workers=[]
        try:
            for cfg,path,cls in ((general_cfg,root,FullAdapter),(used_cfg,root/'ebay_used',LatestUsedAdapter)):
                old=load(path/source/'checkpoint.json',{})
                if old.get('ledger_size',0)>len(http.state['requests']):raise ValueError('shared_history_missing_no_reset')
                box=ChangeDelivery(ApprovedOutbox(cfg,path/source),path/source)
                workers.append(ScheduledWorker(cfg,path,http=http,delivery=box,adapter=cls(cfg,http),schedule=schedule))
            account=AccountWorker(*workers,http)
            try:yield account
            finally:account.close()
        finally:
            http.close()
