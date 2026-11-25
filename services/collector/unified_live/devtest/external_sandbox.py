"""Explicit, bounded public scraping sandbox check; never a commercial-site grant.

No secrets, raw HTML persistence, backend construction, provider API or DB access.
"""
import argparse,json,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import urljoin
from services.collector.unified_live.mock import fixture_config
from services.collector.unified_live.transport import SafeHTTP,Wait
from services.collector.unified_live.parser import links,document,normalize
from services.collector.unified_live.analysis import value
from services.collector.unified_live.policy import url
from services.collector.marketplace_live.probe import lookup_permitted

def run(root):
 cfg=fixture_config();host='books.toscrape.com';base='https://'+host+'/'
 cfg.update(source='html_external_sandbox',base_url=base,allowed_product_hosts=[host],mode='general',backend_enabled=False,backend_owner_approved=False,price_semantics_confirmed=False,requests_per_hour=12,requests_per_24h=12,request_interval_seconds=2,max_products_per_cycle=3)
 cfg['rights']={'reference':'https://sites.toscrape.com/','terms_reference':'https://books.toscrape.com/','expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),'allowed_uses':['lookup']}
 # Lookup-only sandbox permission: never enables a production URLWorker/storage grant.
 cfg['selectors']={'product_links':'.product_pod h3 a','next_page':'li.next a','name':'.product_main h1','price':'.product_main .price_color','availability':'.product_main .availability','image':'.carousel-inner img'}
 class SandboxLookup(SafeHTTP):
  def permitted(self,target):
   # Testing permission is not a grant to persist/reuse commercial product data.
   return self.host=='books.toscrape.com' and lookup_permitted(self.cfg,self.clock())
 http=SandboxLookup(cfg,Path(root));result={'kind':'external_published_fictional_bookstore','permission_reference':'https://sites.toscrape.com/','commercial_live_products':0,'backend_requests':0,'products':[],'max_source_requests':12}
 def fetch(target):
  for _ in range(4):
   try:return http.fetch(target)
   except Wait as exc:
    delay=(exc.until-http.clock()).total_seconds() if exc.until else 999
    if exc.hold or str(exc)!='rate_wait' or not 0<=delay<=3:raise
    time.sleep(delay)
  raise RuntimeError('bounded_rate_wait_exhausted')
 try:
  code,text=fetch(base);assert code==200
  found,nxt=links(text,base,cfg);result['detail_links_selected']=len(found);result['pagination_link_detected']=bool(nxt)
  for target in found[:3]:
   code,text=fetch(target);assert code==200;soup=document(text)
   image=value(soup,'image',cfg['selectors']);price=value(soup,'price',cfg['selectors']);name=value(soup,'name',cfg['selectors'])
   missing=[]
   try:native=normalize(text,target,datetime.now(timezone.utc).isoformat(),cfg);missing=native['missing_fields']
   except (ValueError,ArithmeticError):missing=['explicit_currency_condition_seller_and_price_normalization_require_review']
   result['products'].append({'name':name,'price_raw':price,'image_url':url(urljoin(target,image)) if image else None,'url':target,'availability_raw':value(soup,'availability',cfg['selectors']),'brand':value(soup,'brand',cfg['selectors']),'model_number':value(soup,'model_number',cfg['selectors']),'held':True,'hold_reasons':missing,'synthetic':True})
  result['network_validation_passed']=len(result['products'])==3 and all(p['name'] and p['price_raw'] and p['image_url'] for p in result['products'])
 except (Wait,OSError,ValueError,AssertionError) as exc:
  result.update(network_validation_passed=False,error=str(exc)[:160])
 finally:
  result.update(source_requests=len(http.state['requests']),request_statuses=[r['status'] for r in http.state['requests']],held_products=len(result['products']),eligible_Observation_v2=0)
  http.close()
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--state-dir',required=True);a=p.parse_args()
 if not a.run:print(json.dumps({'source_requests':0,'requires_explicit_run':True}))
 else:print(json.dumps(run(a.state_dir),ensure_ascii=True))
