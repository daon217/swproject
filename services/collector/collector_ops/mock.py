"""In-process API simulator; exercise the real durable ACK/retry algorithm offline."""
from pathlib import Path
from services.collector.domeggook_live.domeggook_delivery import DeliveryPipeline
from services.collector.marketplace_live.synthetic import MockOutbox,SyntheticHTTP,fixture_config
from services.collector.marketplace_live.adapters import Adapter
from services.collector.used_market_live.ebay_used import UsedAdapter
from .catalog import SOURCES
from .runtime import OpsWorker


class _SyntheticAPI:
    def __init__(self,responses=None):self.responses=list(responses or []);self.calls=[]
    def __call__(self,path,body):
        self.calls.append((path,body))
        return self.responses.pop(0) if self.responses else (201,{'state':'applied','change_kind':'created'})


class SimulatedDelivery(MockOutbox):
    def __init__(self,cfg,root,responses=None,clock=None):
        from services.collector.domeggook_live.domeggook_delivery import utcnow
        self.fake_API=_SyntheticAPI(responses)
        super().__init__(cfg,root,transport=self.fake_API,clock=clock or utcnow)
    def flush(self,stop=None):
        # The ordinary Outbox still refuses synthetic_only files. Only this mock
        # subclass can drive its ancestor's algorithm with a fixed in-process API.
        if type(self.transport) is not _SyntheticAPI or self.state.get('synthetic_only') is not True:
            raise ValueError('sealed_inprocess_mock_transport_required')
        return DeliveryPipeline.flush(self,stop)


def run_mock(provider,root):
    if provider=='domeggook':
        from services.collector.domeggook_live.fixture_data import row,config
        api=_SyntheticAPI();cfg=config()
        box=DeliveryPipeline(cfg,Path(root)/'ops-mock-only/domeggook',transport=api)
        box.state['synthetic_only']=True
        staged=box.stage(row());box.flush()
        return {'provider':provider,'synthetic_only':True,'mode':'inprocess_mock',
                'external_HTTP_requests':0,'DB_writes':0,'simulated_team_API_requests':len(api.calls),
                'staged':staged['status'],'backend':box.report()}
    source=SOURCES[provider];cfg=fixture_config(source)
    http=SyntheticHTTP(source);cls=Adapter
    if provider=='ebay_used':
        cls=UsedAdapter
        for row in http.rows:row.update(conditionId='3000',condition='Used')
    path=Path(root)/'ops-mock-only'/provider
    box=SimulatedDelivery(cfg,path/source)
    worker=OpsWorker(cfg,path,http=http,adapter=cls(cfg,http,credential_reader=lambda _: 'SYNTHETIC_NOT_A_KEY'),delivery=box)
    # Search and at most three details. No external sockets or secret readers.
    for _ in range(5):
        worker.step()
        if not worker.state['tasks']:break
    for _ in range(5):
        if not box.pending_count():break
        box.flush()
    result=worker.report()
    result.update(provider=provider,synthetic_only=True,mode='inprocess_mock',
                  external_HTTP_requests=0,simulated_team_API_requests=len(box.fake_API.calls),
                  DB_writes=0,API_contract='v2',API_ack_created=box.state['totals'].get('change_created',0))
    return result
