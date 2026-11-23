"""Opt-in operations layer; all provider budgets, locks and outbox semantics reused."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
from services.collector.domeggook_live.runtime import FileState
from services.collector.domeggook_live.domeggook_delivery import load, atomic, utcnow
from services.collector.marketplace_live.adapters import Adapter
from services.collector.marketplace_live.http import ProviderHTTP,ProviderError
from services.collector.marketplace_live.runner import Worker
from services.collector.used_market_live.ebay_used import UsedAdapter, used_config
from .evidence import EvidenceAdapter
from .backend import OpsOutbox


class OpsWorker(Worker):
    def __init__(self,cfg,*args,**kwargs):
        for key,default,maximum in (('max_tracked_items',10000,1000000),('refresh_items_per_cycle',1,100)):
            value=cfg.get(key,default)
            if type(value) is not int or not 1<=value<=maximum:raise ValueError('bounded_refresh_configuration_required')
        if cfg.get('food_policy','hold_until_contract') not in ('hold_until_contract','base_product_only'):
            raise ValueError('explicit_food_policy_required')
        super().__init__(cfg,*args,**kwargs)
        self.adapter=EvidenceAdapter(self.adapter,self.evidence_seen)
    def evidence_seen(self,result,row):
        evidence=result['food_evidence']
        if evidence['status']=='food_evidence':
            self.count('food_products_seen')
            self.count('food_allergens_'+evidence['allergen_status'])
            if evidence.get('ingredients') is None:self.count('food_missing_ingredients')
        if 'food_contract_required' in result['missing_fields']:self.count('food_contract_held')
        if self.cfg['source']=='ebay_browse':
            import re
            identity=row.get('itemId')
            if isinstance(identity,str) and re.fullmatch(r'v1\|\d+\|\d+',identity):
                known=self.state.setdefault('ops_known_items',{})
                if identity in known or len(known)<self.cfg.get('max_tracked_items',10000):
                    known[identity]={'last_observed_at':self.clock().isoformat(),'last_checked_at':self.clock().isoformat(),
                        'availability':result.get('availability'),'verification_required':False}
                else:self.count('refresh_tracking_capacity_exceeded')
    def accept(self,row):
        self.adapter.accepting=True
        try:super().accept(row)
        finally:self.adapter.accepting=False
    def complete_if_empty(self):
        if not self.state['tasks'] and self.cfg['source']=='ebay_browse' and self.state.get('ops_refresh_cycle')!=self.state['cycle']:
            self.state['ops_refresh_cycle']=self.state['cycle']
            seen=set(self.state['seen_ids'])
            candidates=sorted(((v.get('last_checked_at') or v.get('last_observed_at') or '',k) for k,v in self.state.get('ops_known_items',{}).items() if k not in seen))
            for _,identity in candidates[:self.cfg.get('refresh_items_per_cycle',1)]:
                self.state['tasks'].append(self.task('detail',identity=identity))
            if self.state['tasks']:self.count('refresh_tasks_scheduled',len(self.state['tasks']))
        super().complete_if_empty()
    def execute(self,task):
        try:return super().execute(task)
        except ProviderError as exc:
            if self.cfg['source']=='ebay_browse' and task['kind']=='detail' and exc.http_status in (404,410):
                known=self.state.get('ops_known_items',{}).get(task['identity'])
                if known is not None:
                    known.update(verification_required=True,last_missing_at=self.clock().isoformat(),last_checked_at=self.clock().isoformat(),last_HTTP_status=exc.http_status)
                self.count('products_held');self.count('missing_item_requires_verification')
                self.state['last_failure_at']=self.clock().isoformat()
                return []
            raise


@contextmanager
def worker_context(cfg,root,used=False):
    root=Path(root);source=cfg['source']
    if used:used_config(cfg)
    with ExitStack() as stack:
        stack.enter_context(FileState(root/source/'lock').lock())
        workroot=root/'ebay_used' if used else root
        if used:
            stack.enter_context(FileState(workroot/source/'lock').lock())
            old=load(root/source/'checkpoint.json',{})
            ledger=load(root/source/'request_ledger.json',{'requests':[]})
            if old.get('ledger_size',0)>len(ledger['requests']):raise ValueError('missing_shared_history_no_reset')
        http=ProviderHTTP(cfg,root/source)
        try:
            adapter=(UsedAdapter if used else Adapter)(cfg,http)
            delivery=OpsOutbox(cfg,workroot/source)
            worker=OpsWorker(cfg,workroot,http=http,adapter=adapter,delivery=delivery)
        except Exception:http.close();raise
        try:yield worker
        finally:worker.stop.set();worker.close()


def source_status(cfg,root,provider,clock=utcnow):
    root=Path(root);source=cfg['source']
    workroot=root/'ebay_used' if provider=='ebay_used' else root
    checkpoint=load(workroot/source/'checkpoint.json',{})
    ledger=load(root/source/'request_ledger.json',{'requests':[]})
    box=load(workroot/source/'backend_outbox.json',{'entries':{},'totals':{}})
    totals=checkpoint.get('totals',{});acks=box.get('totals',{})
    last=checkpoint.get('last_success_at');stale=None
    if last:
        from services.collector.marketplace_live.config import stamp
        stale=(clock()-stamp(last)).total_seconds()>cfg['cycle_interval_seconds']*2
    return {'provider':provider,'configured_enabled':cfg['enabled'],
        'state':'disabled' if not cfg['enabled'] else 'held' if checkpoint.get('hold') or ledger.get('hold') or box.get('hold') else 'enabled',
        'last_collection_at':checkpoint.get('last_collection_at'),'last_success_at':last,
        'last_failure_at':checkpoint.get('last_failure_at'),'stale':stale,
        'products_success':totals.get('products_success',0),'products_held':totals.get('products_held',0),
        'products_failed':totals.get('products_failed',0),
        'provider_failures':totals.get('provider_failed_actions',0)+totals.get('provider_errors',0),
        'DB_ack_created':acks.get('change_created',0),'DB_ack_updated':acks.get('change_updated',0),
        'DB_ack_unchanged':acks.get('change_unchanged',0),'DB_ack_quarantined':acks.get('ack_quarantine',0),
        'next_cycle_at':checkpoint.get('next_cycle_at'),'HTTP_attempts':len(ledger['requests']),
        'hold':checkpoint.get('hold') or ledger.get('hold') or box.get('hold'),
        'food':{k:v for k,v in totals.items() if k.startswith('food_')},
        'refresh_tracking':{'tracked_items':len(checkpoint.get('ops_known_items',{})),
             'verification_required':sum(v.get('verification_required') is True for v in checkpoint.get('ops_known_items',{}).values()),
             'coverage_limited':totals.get('refresh_tracking_capacity_exceeded',0)>0,
             'refresh_items_per_cycle':cfg.get('refresh_items_per_cycle',1),
             'oldest_check_at':min((v.get('last_checked_at') or v.get('last_observed_at') or '' for v in checkpoint.get('ops_known_items',{}).values()),default=None)},
        'backend_states':{state:sum(e['status']==state for e in box['entries'].values())
                          for state in {e['status'] for e in box['entries'].values()}},
        'metrics_semantics':'local_queue_success_and_separate_backend_ack_counts',
        'HTTP_requests_this_command':0}
