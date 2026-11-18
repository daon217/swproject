"""Next-restart integration. Uses the existing watch lock; never replaces a running worker."""
import argparse,json
from pathlib import Path
from .runtime import FileState
from .domeggook_operations import ROOT,configuration,BudgetWait
from .domeggook_discovery import DiscoveryRun,queue_loop,status,validate_discovery
from .domeggook_delivery import DeliveryPipeline

class DeliveryStore:
    def __init__(self,store,pipeline,on_result=None):self.store=store;self.pipeline=pipeline;self.needs_reobserve=0;self.on_result=on_result
    @property
    def memory(self):return self.store.memory
    def put(self,row):
        result=self.store.put(row)
        try:
            staged=self.pipeline.stage(row)
            if staged['status']=='backpressure_needs_reobserve':self.needs_reobserve+=1
            if self.on_result:self.on_result(row,staged['status'])
        except Exception:
            # Existing source values/checkpoint survive a delivery/contract failure.
            self.needs_reobserve+=1
            if self.on_result:self.on_result(row,'stage_failed')
        return result

class DeliveryDiscoveryRun(DiscoveryRun):
    def __init__(self,cfg,client,root=ROOT,delivery=None):
        super().__init__(cfg,client,root)
        self.delivery=delivery or DeliveryPipeline(cfg,Path(root)/'backend_delivery')
        self.store=DeliveryStore(self.store,self.delivery,self.delivery_result)
    def delivery_result(self,row,status):
        key=json.dumps([row['source'],row['source_listing_id'],row['variant_key']],separators=(',',':'))
        markers=self.state.setdefault('backend_reobserve',{})
        if status in ('stage_failed','backpressure_needs_reobserve'):
            markers[key]={'observed_at':row.get('observed_at') or row.get('last_observed_at'),'reason':status}
        elif status in ('pending','delivered','quarantine'):markers.pop(key,None)
    def cycle(self,mode='combined'):
        self.delivery.flush()
        if self.delivery.backpressure():raise BudgetWait(30,'backend_outbox_backpressure')
        result=super().cycle(mode);self.delivery.flush();result['backend_delivery']=self.delivery.report();return result
    def report(self):
        report=super().report()
        if hasattr(self,'delivery'):
            report['backend_delivery']=self.delivery.report()
            report['backend_delivery']['needs_reobserve_tuples']=len(self.state.get('backend_reobserve',{}))
        return report

def main():
    from .domeggook_operations import main as run
    return run()
