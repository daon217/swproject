"""Operational paths: explicit URL -> extraction -> queue -> ACK; no external calls."""
import copy,json,os,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from services.collector.unified_live.mock import fixture_config,product,FakeHTTP
from services.collector.unified_live.policy import validate
from services.collector.unified_live.parser import links,normalize
from services.collector.unified_live.engine import URLWorker
from services.collector.collector_ops.mock import SimulatedDelivery
from services.collector.collector_ops.backend_transport import endpoint_plan
from services.collector.unified_live.fleet import registration,FleetSupervisor
from services.collector.unified_live.discovery import DiscoveryStore,probe

class OperationalWeb(unittest.TestCase):
 def setUp(self):
  self.cfg=fixture_config();self.now=datetime.now(timezone.utc)
 def norm(self,html):return normalize(html,'https://store.example.test/item/1',self.now.isoformat(),self.cfg)
 def test_explicit_product_url_without_search(self):
  self.cfg.pop('queries');self.cfg.pop('search_url_template');self.cfg['start_urls']=['https://store.example.test/item/1']
  self.assertIs(validate(self.cfg),self.cfg)
  with tempfile.TemporaryDirectory() as d:
   http=FakeHTTP();box=SimulatedDelivery(self.cfg,Path(d)/self.cfg['source'],clock=lambda:self.now)
   w=URLWorker(self.cfg,d,transport=http,delivery=box,clock=lambda:self.now)
   try:
    w.step();self.assertEqual(w.report()['tracked_items'],1);self.assertEqual(len(box.fake_API.calls),1)
    w.step();self.assertEqual(len(box.fake_API.calls),1)
   finally:w.close()
 def test_direct_jsonld_without_own_url(self):
  result=self.norm(product().replace('"url": "https://store.example.test/item/1",',''))
  self.assertIsNotNone(result['observation'])
 def test_start_urls_reject_external_http_and_origin(self):
  for value in ('http://store.example.test/item','https://127.0.0.1/x','https://evil.example.test/x'):
   cfg=dict(self.cfg,start_urls=[value])
   with self.subTest(value=value),self.assertRaises(ValueError):validate(cfg)
 def test_itemlist_bare_urls_and_cards_and_pagination(self):
  html='<script type="application/ld+json">'+json.dumps({'@type':'ItemList','itemListElement':['/item/1',{'url':'/item/2'}]})+'</script><a rel="next" href="/catalog?page=2">next</a>'
  found,nxt=links(html,self.cfg['base_url'],self.cfg)
  self.assertEqual(len(found),2);self.assertIn('page=2',nxt)
  cfg=dict(self.cfg,selectors={'card':'.card'})
  found,_=links('<article class="card"><a href="/item/3">p</a></article>',cfg['base_url'],cfg)
  self.assertEqual(found,['https://store.example.test/item/3'])
 def test_cross_origin_pagination_is_ignored(self):
  self.assertIsNone(links('<a rel="next" href="http://evil.test/">next</a>',self.cfg['base_url'],self.cfg)[1])
 def test_jsonld_missing_fields_use_native_evidence(self):
  p=json.loads(product().split('application/ld+json">')[1].split('</script>')[0]);p['offers'].pop('priceCurrency');p.pop('image')
  html='<script type="application/ld+json">'+json.dumps(p)+'</script><meta property="product:price:currency" content="USD"><meta property="og:image" content="https://store.example.test/a.jpg">'
  result=self.norm(html);self.assertIsNotNone(result['observation']);self.assertTrue(result['metadata']['image_url'].endswith('a.jpg'))
 def test_css_native_state_and_lazy_image(self):
  cfg=self.cfg;cfg['selectors']={k:'.'+k for k in ('name','price','currency','seller','condition','availability','image')}
  html=''.join('<span class="'+k+'">'+v+'</span>' for k,v in dict(name='SYNTHETIC keyboard',price='12.00',currency='USD',seller='SYNTHETIC seller',condition='중고',availability='판매중').items())+'<img class="image" data-src="/a.jpg">'
  result=self.norm(html);self.assertIsNotNone(result['observation']);self.assertIsNone(result['metadata']['stock_quantity']);self.assertTrue(result['metadata']['purchase_available'])
 def test_missing_state_is_held_never_invented(self):
  result=self.norm(product().replace('https://schema.org/UsedCondition','UNKNOWN'))
  self.assertIsNone(result['observation']);self.assertIn('condition',result['missing_fields'])
 def test_partial_jsonld_does_not_override_explicit_price(self):
  result=self.norm(product()+'<meta property="product:price:amount" content="999">')
  self.assertEqual(str(result['price']),'12.00')
 def test_http_plan_uses_environment_override_ignores_https_ca(self):
  with patch.dict(os.environ,{'COLLECTOR_BACKEND_TRANSPORT':'internal_http','COLLECTOR_BACKEND_BASE_URL':'http://192.168.0.254:8000','COLLECTOR_DELIVERY_APPROVED':'yes','COLLECTOR_CA_FILE':'/missing-cert'},clear=True):
   self.assertTrue(endpoint_plan('https://team.invalid')['ready'])
 def test_http_plan_requires_explicit_env_and_switch(self):
  with patch.dict(os.environ,{'COLLECTOR_BACKEND_TRANSPORT':'internal_http'},clear=True):self.assertFalse(endpoint_plan('http://api:8000')['ready'])
 def test_https_plan_rejects_http(self):
  with patch.dict(os.environ,{},clear=True):self.assertFalse(endpoint_plan('http://api:8000')['ready'])
 def test_discovery_css_quality_reaches_registration(self):
  cfg=self.cfg;approval=dict(cfg['rights'],allowed_hosts=cfg['allowed_product_hosts'],currencies=['USD'],backend_enabled=True,backend_owner_approved=True,price_semantics_confirmed=True,start_urls=['https://store.example.test/item/1'],selectors={'name':'h1'})
  class HTTP:
   def __init__(self,*a):pass
   def fetch(self,t):return 200,product().replace('"name": "SYNTHETIC mechanical keyboard",','')+'<h1>SYNTHETIC keyboard</h1>'
   def close(self):pass
  with tempfile.TemporaryDirectory() as d:
   store=DiscoveryStore(d);ident=store.add({'domain':'store.example.test','kind':'used'},'SYNTHETIC_ONLY')
   # add returns identifier; evaluate only with explicit local grants.
   if isinstance(ident,dict):ident=ident['marketplace_id']
   site=probe(store,ident,http_factory=HTTP,approval=approval)
   self.assertTrue(site['enabled']);registered=registration(site,approval);self.assertEqual(registered['start_urls'],approval['start_urls'])
 def test_fleet_passes_backend_environment(self):
  cfg=self.cfg;captures=[]
  class Child:
   def poll(self):return None
   def terminate(self):pass
   def wait(self,timeout):return 0
  def popen(command,**kw):captures.append(kw['env']);return Child()
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'COLLECTOR_RUN_APPROVED':'yes','COLLECTOR_BACKEND_TRANSPORT':'internal_http','COLLECTOR_BACKEND_BASE_URL':'http://api:8000'},clear=True):
   f=FleetSupervisor(Path(d)/'fleet',Path(d)/'discovery',{},popen=popen)
   with patch.object(f,'desired',return_value={'fixture':cfg}):f.tick()
   f.close();self.assertEqual(captures[0]['COLLECTOR_BACKEND_BASE_URL'],'http://api:8000');self.assertEqual(captures[0]['COLLECTOR_BACKEND_TRANSPORT'],'internal_http')
 def test_provider_preflight_http_override_keeps_permissions(self):
  from services.collector.collector_ops.__main__ import preflight
  from services.collector.marketplace_live.tests.fixtures import config
  environment={'COLLECTOR_RUN_APPROVED':'yes','COLLECTOR_DELIVERY_APPROVED':'yes','COLLECTOR_BACKEND_TRANSPORT':'internal_http','COLLECTOR_BACKEND_BASE_URL':'http://192.168.0.254:8000','EBAY_CLIENT_ID':'SYNTHETIC','EBAY_CLIENT_SECRET':'SYNTHETIC','YES24_API_KEY':'SYNTHETIC','KKULPICK_BACKEND_TOKEN':'SYNTHETIC_TOKEN_'+'x'*40}
  with patch.dict(os.environ,environment,clear=True):
   for provider,source in (('ebay','ebay_browse'),('yes24','yes24_api')):
    cfg=config(source);cfg.update(enabled=True,backend_enabled=True,backend_owner_approved=True,price_semantics_confirmed=True)
    cfg['backend_delivery']['base_url']='https://team.invalid'
    check=preflight(provider,cfg)
    self.assertTrue(check['backend_transport']['ready']);self.assertNotIn('approved_HTTPS_team_API_endpoint_required',check['reasons'])
    cfg['rights']={};check=preflight(provider,cfg)
    self.assertIn('systematic_storage_reuse_grants_required',check['reasons'])
if __name__=='__main__':unittest.main()
