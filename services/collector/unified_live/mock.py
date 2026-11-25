"""Bounded, entirely in-process URL -> v2 -> outbox -> simulated ACK."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
from services.collector.collector_ops.mock import SimulatedDelivery
from .engine import URLWorker

def fixture_config():
    return {'source':'html_synthetic','base_url':'https://store.example.test/',
        'search_url_template':'https://store.example.test/search?q={query}&page={page}','queries':['keyboard'],'mode':'used',
        'region':'overseas','enabled':True,'backend_enabled':True,'backend_owner_approved':True,'price_semantics_confirmed':True,
        'render_javascript':False,'evidence_storage':False,'provider_min_interval_seconds':60,
        'requests_per_hour':100,'requests_per_24h':1000,'request_interval_seconds':1,'max_pages_per_cycle':2,
        'max_products_per_cycle':3,'refresh_items_per_cycle':1,'max_tracked_items':100,'max_attempts':3,
        'allowed_product_hosts':['store.example.test'],'currencies':['USD'],'selectors':{},
        'rights':{'reference':'SYNTHETIC_ONLY','terms_reference':'SYNTHETIC_ONLY','allowed_uses':['lookup','systematic_collection','storage','reuse'],
            'expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()},
        'backend_delivery':{'base_url':'https://team.example.test','max_pending':100,'max_attempts':3,'retry_base_seconds':5}}

def product(price='12.00',availability='InStock'):
    import json
    p={'@context':'https://schema.org','@type':'Product','productID':'SYNTHETIC-1','sku':'SYNTHETIC-SKU',
       'name':'SYNTHETIC mechanical keyboard','url':'https://store.example.test/item/1','description':'SYNTHETIC clean keyboard',
       'itemCondition':'https://schema.org/UsedCondition','image':'https://store.example.test/image/1.jpg',
       'offers':{'@type':'Offer','price':price,'priceCurrency':'USD','availability':'https://schema.org/'+availability,'seller':{'name':'SYNTHETIC seller'}}}
    return '<html><script type="application/ld+json">'+json.dumps(p)+'</script></html>'

LIST='<script type="application/ld+json">{"@type":"ItemList","itemListElement":[{"@type":"ListItem","item":{"url":"https://store.example.test/item/1"}},{"@type":"ListItem","item":{"url":"https://store.example.test/item/1"}}]}</script>'

class FakeHTTP:
    synthetic_only=True
    def __init__(self):self.state={'requests':[],'hold':None};self.price='12.00';self.status='InStock';self.pages={}
    def fetch(self,target):
        self.state['requests'].append({'status':200})
        if target in self.pages:return self.pages[target]
        return 200,LIST if '/search?' in target else product(self.price,self.status)
    def close(self):pass

def run_mock(root):
    now=[datetime.now(timezone.utc)];cfg=fixture_config();http=FakeHTTP();root=Path(root)
    box=SimulatedDelivery(cfg,root/cfg['source'],clock=lambda:now[0])
    worker=URLWorker(cfg,root,transport=http,delivery=box,clock=lambda:now[0])
    try:
        for _ in range(2):worker.step()
        first=len(box.fake_API.calls)
        now[0]+=timedelta(seconds=60)
        for _ in range(2):worker.step()
        unchanged=len(box.fake_API.calls)==first
        http.price='10.00';now[0]+=timedelta(seconds=60)
        for _ in range(2):worker.step()
        result=worker.report()
        result.update(mode='inprocess_mock',synthetic=True,external_HTTP_requests=0,DB_writes=0,
            simulated_team_API_requests=len(box.fake_API.calls),unchanged_no_API_write=unchanged,
            simulated_provider_actions=len(http.state['requests']))
        return result
    finally:worker.close()
