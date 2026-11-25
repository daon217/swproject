"""Explicit synthetic provider, real adapters/normalizers and a non-sendable queue."""
import copy
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from .adapters import Adapter
from .delivery import Outbox
from .probe import bounded_lookup

class MockOutbox(Outbox):
    synthetic_only=True
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.state['synthetic_only']=True;self.save()

def fixture_config(source):
    configs=json.loads((Path(__file__).parent/'config.example.json').read_text(encoding='utf-8'))['sources']
    cfg=next(c for c in configs if c['source']==source)
    cfg.update(enabled=True,backend_enabled=True,backend_owner_approved=True,price_semantics_confirmed=True,page_size=3)
    cfg['rights'].update(reference='SYNTHETIC_ONLY',allowed_uses=['lookup','systematic_collection','storage','reuse'],
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),exception_agreement_reference='SYNTHETIC_ONLY_NOT_A_LICENSE')
    return cfg

def fixture_rows(source):
    rows=[]
    for index in range(1,4):
        if source=='yes24_api':
            r={'itemId':99000000+index,'title':'SYNTHETIC book '+str(index),'salePrice':1000+index,
               'currency':'KRW','sku':'SYNTHETIC-'+str(index),'condition':'new','availability':'available',
               'seller':'SYNTHETIC seller','link':'https://www.yes24.com/product/goods/'+str(99000000+index),'itemStatus':'판매중'}
        elif source=='ebay_browse':
            r={'itemId':'v1|9900000'+str(index)+'|0','title':'SYNTHETIC item '+str(index),
               'price':{'value':'10.00','currency':'USD'},'conditionId':'1000','condition':'New',
               'buyingOptions':['FIXED_PRICE'],'seller':{'username':'SYNTHETIC merchant'},
               'estimatedAvailabilities':[{'estimatedAvailabilityStatus':'IN_STOCK'}],
               'itemWebUrl':'https://www.ebay.com/itm/9900000'+str(index)}
        elif source=='serper_google_shopping':
            r={'productId':'9900000'+str(index),'title':'SYNTHETIC Serper shopping '+str(index),'price':'$10.00',
               'currency':'USD','condition':'new','availability':'available','source':'SYNTHETIC merchant',
               'link':'https://merchant.example.test/product/'+str(index)}
        else:
            r={'product_id':'9900000'+str(index),'title':'SYNTHETIC shopping '+str(index),'extracted_price':'10.00',
               'currency':'USD','condition':'new','availability':'available','seller':'SYNTHETIC merchant',
               'link':'https://merchant.example.test/product/'+str(index)}
        if index==3:
            if source=='ebay_browse':r['estimatedAvailabilities']=[]
            else:r.pop('currency')
        rows.append(r)
    return rows

class SyntheticHTTP:
    def __init__(self,source):self.source=source;self.rows=fixture_rows(source);self.state={'requests':[],'hold':None};self.task_id='SYNTHETIC'
    def save(self):pass
    def get_json(self,url,**options):
        self.state['requests'].append({'status':200,'task_id':self.task_id})
        if self.source=='yes24_api':
            rows=self.rows
            if url.endswith('itemDetail'):rows=[r for r in rows if str(r['itemId'])==options['params']['query']]
            else:rows=rows[:options['params']['pageSize']]
            return {'success':True,'data':{'items':copy.deepcopy(rows),'currentPage':1}}
        if self.source=='ebay_browse':
            if url.endswith('/search'):return {'itemSummaries':copy.deepcopy(self.rows[:options['params']['limit']]),'total':3}
            from urllib.parse import unquote
            identity=unquote(url.rsplit('/',1)[-1])
            return copy.deepcopy(next(r for r in self.rows if r['itemId']==identity))
        return {'shopping_results':copy.deepcopy(self.rows),'pagination':{}}
    def post_json(self,url,**options):
        self.state['requests'].append({'status':200,'task_id':self.task_id})
        if self.source=='serper_google_shopping':return {'shopping':copy.deepcopy(self.rows),'searchParameters':{'type':'shopping'}}
        return {'access_token':'SYNTHETIC_NOT_REAL','expires_in':3600}

def run_mock(source,root,maximum=3):
    cfg=fixture_config(source);cfg['page_size']=maximum
    http=SyntheticHTTP(source)
    adapter=Adapter(cfg,http,credential_reader=lambda _: 'SYNTHETIC_NOT_A_KEY')
    # This path never shares a production outbox or provider request ledger.
    path=Path(root).resolve()/'mock-only'/source
    outbox=MockOutbox(cfg,path)
    def stage(result,normalized):
        if result['status']=='success':outbox.stage(normalized)
    result=bounded_lookup(adapter,cfg,maximum,on_result=stage)
    result.update(mode='mock',synthetic_only=True,queue_pending=outbox.pending_count(),
                  provider_HTTP_attempts=0,simulated_provider_actions=len(http.state['requests']),
                  backend_HTTP_requests=0,products_persisted='synthetic_queue_only')
    return result
