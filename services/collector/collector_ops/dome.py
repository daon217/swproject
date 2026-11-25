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
        if self.cfg.get('food_policy')=='extension_v1':
            from services.collector.unified_live.delivery_extras import Extras
            from types import SimpleNamespace
            self.source='domeggook'
            self.food_extras=Extras(SimpleNamespace(box=self,path=self.path))
    def flush(self,stop=None):
        import os
        before=self.state['totals'].get('revoked',0)
        self.prune()
        if self.enabled and self.state['totals'].get('revoked',0)!=before:self.save()
        if os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes':return self.report()
        result=super().flush(stop)
        if hasattr(self,'food_extras'):self.food_extras.flush(stop)
        return result
    def stage(self,row):
        cls=row.get('classification') or {}
        if cls and cls.get('selected_domain') not in ('product','food'):
            self.count('classification_held');return {'status':'classification_unconfirmed'}
        if cls.get('selected_domain')=='food' and cls.get('condition')=='used':
            self.count('classification_held');return {'status':'classification_contract_conflict'}
        if self.cfg.get('food_policy')=='extension_v1':
            return self.stage_food_extension(row)
        if cls.get('is_food') is False:return super().stage(row)
        # Missing optional food/component evidence must not hold a valid core observation.
        return super().stage(row)


    def stage_food_extension(self,row):
        from services.collector.domeggook_live.food import food_evidence
        from services.collector.domeggook_live.domeggook_backend import prepare_observation
        from services.collector.unified_live.delivery_extras import Extras
        from types import SimpleNamespace
        domain=(row.get('classification') or {}).get('selected_domain') or self.settings.get('selected_domain')
        if domain not in ('food','product'):return {'status':'classification_unconfirmed'}
        evidence_allowed=self.cfg.get('evidence_storage') is True and 'evidence_storage' in self.cfg.get('rights',{}).get('allowed_uses',[])
        if row.get('variant_key') is None and row.get('native_option_state')=='explicit_null':
            import copy
            row=copy.deepcopy(row)
            # Backend ListingExtension.variant_key defaults to "default" for
            # listing-level evidence. This is not a provider option identifier.
            # Only explicit API null qualifies; absent/malformed options stay held.
            row['variant_key']='default'
            row['variant_scope']='backend_listing_default'
            row.setdefault('identity_evidence',{})['variant_key']={
                'value':'default',
                'path':'backend.ListingExtension.variant_key.default',
                'basis':'backend listing-level contract; domeggook.selectOpt explicitly null'}
        components=None
        if self.ready and evidence_allowed:
            try:
                from services.collector.domeggook_live.components import collect,source_description
                components=collect(row,self.cfg.get('food_ocr'))
                row=source_description(row,components,self.cfg)
            except Exception:
                self.count('optional_component_extraction_failed')
        result=super().stage(row)
        if result['status'] not in ('pending','delivered'):return result
        body=prepare_observation(row,self.cfg,selected_domain=domain,condition=self.settings['condition'])
        if components is not None:
            from services.collector.domeggook_live.components import persist
            try:persist(self.path.parent,row,components,body['observation_key'])
            except OSError:self.count('optional_component_persistence_failed')
        self.source='domeggook'
        if not hasattr(self,'food_extras'):
            self.food_extras=Extras(SimpleNamespace(box=self,path=self.path))
        normalized={'observation':body,
                    'seller':row.get('seller'),'metadata':{'image_url':row.get('image_url'),
                    'category':row.get('category'),'manufacturer':row.get('manufacturer')}}
        from services.collector.product_evidence.identifiers import public_image
        profile=dict(row.get('matching_profile') or {})
        images=[u for u in [row.get('image_url')]+(row.get('detail_image_urls') or []) if public_image(u)]
        profile.update(image_urls=list(dict.fromkeys(images))[:8])
        if row.get('option_id'):
            profile['options']={'native_option_code':str(row['option_id'])}
            if isinstance(row.get('option_name'),str) and 0<len(row['option_name'])<=200:profile['options']['native_option_name']=row['option_name']
        normalized['metadata']['matching_profile']=profile
        if row.get('seller_id'):normalized['metadata']['seller_id']=row['seller_id']
        if not public_image(normalized['metadata']['image_url']):normalized['metadata']['image_url']=None
        manufacturer=profile.get('manufacturer')
        normalized['metadata']['manufacturer']=manufacturer
        if not isinstance(normalized['metadata']['category'],str) or not 0<len(normalized['metadata']['category'])<=200:normalized['metadata']['category']=None
        if domain=='food' and evidence_allowed:
            try:
                normalized['food_evidence']=food_evidence(row,ocr_config=self.cfg.get('food_ocr'))
                if components is not None:
                    from services.collector.product_evidence.extract import merge_food_evidence
                    normalized['food_evidence']=merge_food_evidence(normalized['food_evidence'],components)
            except Exception:self.count('optional_food_extraction_failed')
        source_image=(normalized.get('food_evidence') or {}).get('source_image_url')
        if not source_image and components is not None:
            source_image=next((s['source_url'] for f in components['fields'].values() for s in f['sources'] if s['method']=='ocr'),None)
        if source_image:
            normalized['metadata']['matching_profile']['image_urls']=list(dict.fromkeys([source_image]+profile.get('image_urls',[])))[:8]
        try:self.food_extras.stage(normalized,result)
        except (ValueError,TypeError,KeyError,OSError):self.count('optional_extension_stage_failed')
        return result


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
    allowed={'backend_enabled','backend_owner_approved','price_semantics_confirmed','storage_grants','backend_delivery','evidence_storage','rights','food_ocr'}
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
