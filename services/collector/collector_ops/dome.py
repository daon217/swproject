"""Inject food evidence at the existing licensed delivery boundary, no source edits."""
from services.collector.domeggook_live.domeggook_delivery import DeliveryPipeline
from services.collector.food_evidence.extract import extract


class FoodDelivery(DeliveryPipeline):
    def __init__(self,*args,**kwargs):
        if kwargs.get('transport') is None and len(args)<3:
            from .backend_transport import DeferredBackend
            from services.collector.domeggook_live.domeggook_delivery import utcnow
            cfg=args[0] if args else kwargs['cfg']
            kwargs['transport']=DeferredBackend(cfg.get('backend_delivery',{}).get('base_url',''),kwargs.get('clock',utcnow))
        super().__init__(*args,**kwargs)
        from services.collector.domeggook_live.domeggook_backend import HTTPBackendTransport
        if isinstance(self.transport,HTTPBackendTransport):
            from .backend import configure_CA
            configure_CA(self.transport)
    def flush(self,stop=None):
        import os
        before=self.state['totals'].get('revoked',0)
        self.prune()
        if self.enabled and self.state['totals'].get('revoked',0)!=before:self.save()
        if os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes':return self.report()
        return super().flush(stop)
    def stage(self,row):
        licensed=row.get('detail_content_license_usable') is True
        text=row.get('description') if licensed else None
        evidence=extract(text,source='domeggook',source_url=row.get('product_url'),
            observed_at=row.get('observed_at'),name=row.get('product_name') or '',category=row.get('category') or '')
        if evidence['status']=='food_evidence':
            self.count('food_products_seen');self.count('food_allergens_'+evidence['allergen_status'])
            if evidence['ingredients'] is None:self.count('food_missing_ingredients')
            if self.cfg.get('food_policy','hold_until_contract')!='base_product_only':
                self.count('food_contract_held')
                if self.enabled:self.save()
                return {'status':'food_contract_required'}
        return super().stage(row)


def run(cfg,root,stop,once=False):
    from pathlib import Path
    from services.collector.domeggook_live.domeggook_operations import configuration, ROOT
    from services.collector.domeggook_live.domeggook_discovery import QueueClient, validate_discovery, queue_loop
    from services.collector.domeggook_live.domeggook_watch_delivery import DeliveryDiscoveryRun
    from services.collector.domeggook_live.runtime import FileState
    # Existing module ROOT must match the inherited KKULPICK_STATE_DIR layout.
    if Path(ROOT).resolve()!=Path(root).resolve()/'domeggook_ops':
        raise ValueError('existing_domeggook_state_root_must_match_environment')
    base=configuration();profile=cfg.get('backend_profile',{})
    allowed={'backend_enabled','backend_owner_approved','price_semantics_confirmed','storage_grants','backend_delivery'}
    if not isinstance(profile,dict) or set(profile)-allowed:raise ValueError('backend_profile_scope_invalid')
    base.update(profile);base['food_policy']=cfg.get('food_policy','hold_until_contract')
    base['cycle_interval_seconds']=max(7200,base['cycle_interval_seconds'])
    validate_discovery(base)
    with FileState(ROOT/'state').lock():
        client=QueueClient(base);pipeline=None
        try:
            pipeline=FoodDelivery(base,ROOT/'backend_delivery')
            worker=DeliveryDiscoveryRun(base,client,ROOT,delivery=pipeline);worker.stop=stop
            return queue_loop(worker,'combined',watch=not once,cycles=1 if once else None)
        finally:
            client.close()
            if pipeline:pipeline.close()
