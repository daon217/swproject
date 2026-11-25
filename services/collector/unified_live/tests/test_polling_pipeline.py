"""Local fixtures only: discovery activation, failure isolation, used transitions."""
import json,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from services.collector.unified_live.mock import fixture_config,product,FakeHTTP,LIST
from services.collector.unified_live.discovery import DiscoveryStore,probe
from services.collector.unified_live.fleet import FleetSupervisor,registration
from services.collector.unified_live.engine import URLWorker
from services.collector.unified_live.transport import Wait
from services.collector.unified_live.parser import normalize
from services.collector.unified_live.policy import url
from services.collector.collector_ops.mock import SimulatedDelivery

class PollingPipeline(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.now=datetime.now(timezone.utc);self.cfg=fixture_config()
 def tearDown(self):self.tmp.cleanup()
 def approval(self):
  return dict(self.cfg['rights'],allowed_hosts=['store.example.test'],currencies=['USD'],backend_enabled=True,backend_owner_approved=True,price_semantics_confirmed=True,start_urls=['https://store.example.test/catalog'],queries=[],provider_min_interval_seconds=60)
 def worker(self,http=None):
  box=SimulatedDelivery(self.cfg,self.root/self.cfg['source'],clock=lambda:self.now)
  return URLWorker(self.cfg,self.root,transport=http or FakeHTTP(),delivery=box,clock=lambda:self.now)
 def test_discovery_uses_granted_start_and_detail_then_fleet_worker_ACK(self):
  store=DiscoveryStore(self.root/'discovery',lambda:self.now);ident=store.add({'domain':'store.example.test','kind':'used'},'SYNTHETIC');seen=[]
  class HTTP:
   def __init__(self,host,targets,*args):self.targets=targets;seen.extend(targets)
   def fetch(self,t):return 200,LIST if t.endswith('/catalog') else product()
   def allow_product(self,*args):pass
   def close(self):pass
  site=probe(store,ident,http_factory=HTTP,approval=self.approval());self.assertTrue(site['enabled']);self.assertEqual(seen,['https://store.example.test/catalog'])
  children=[]
  class Child:
   def __init__(child,command,**kwargs):
    cfg=json.loads(Path(command[command.index('--config')+1]).read_text());http=FakeHTTP();http.pages[cfg['start_urls'][0]]=(200,LIST)
    box=SimulatedDelivery(cfg,self.root/'child'/cfg['source'],clock=lambda:self.now)
    child.worker=URLWorker(cfg,self.root/'child',transport=http,delivery=box,clock=lambda:self.now);children.append(child)
   def poll(child):return None
   def terminate(child):child.worker.close()
   def wait(child,timeout):return 0
  with patch.dict(os.environ,{'COLLECTOR_RUN_APPROVED':'yes'},clear=True):
   fleet=FleetSupervisor(self.root/'fleet',store.root,{ident:self.approval()},clock=lambda:self.now,popen=Child)
   try:
    fleet.tick();self.assertEqual(len(children),1)
    child=children[0]
    child.worker.step();child.worker.step();self.assertEqual(child.worker.report()['content_changes'],{'new':1})
    self.assertEqual(len(child.worker.delivery.box.fake_API.calls),1)
    fleet.tick();self.assertEqual(len(children),1)
   finally:fleet.close()
 def test_html_directory_only_adds_disabled_candidate(self):
  store=DiscoveryStore(self.root);ident=store.add({'domain':'publisher.example.test'},'SYNTHETIC')
  class HTTP:
   def __init__(self,*args):pass
   def fetch(self,t):return 200,'<a class="shop" href="https://store.example.test/">shop</a><a class="shop" href="http://127.0.0.1/">bad</a>'
   def close(self):pass
  probe(store,ident,http_factory=HTTP,approval={'discovery_links_selector':'a.shop'})
  self.assertEqual(len(store.state['sites']),2);self.assertEqual(store.report()['enabled'],0)
 def test_failed_recheck_revokes_stale_product_quality(self):
  store=DiscoveryStore(self.root);ident=store.add({'domain':'store.example.test'},'SYNTHETIC');store.state['sites'][ident]['product_quality_verified']=True
  class HTTP:
   def __init__(self,*args):pass
   def fetch(self,t):return 200,'<html>no product</html>'
   def close(self):pass
  self.assertFalse(probe(store,ident,http_factory=HTTP,approval=self.approval())['enabled'])
 def test_ungranted_starts_are_never_fetched(self):
  store=DiscoveryStore(self.root);ident=store.add({'domain':'store.example.test'},'SYNTHETIC');targets=[]
  class HTTP:
   def __init__(self,h,ts,*args):targets.extend(ts)
   def fetch(self,t):return 200,'nothing'
   def close(self):pass
  probe(store,ident,http_factory=HTTP,approval={'start_urls':['https://store.example.test/private']});self.assertEqual(targets,['https://store.example.test/'])
 def test_bad_detail_does_not_stop_other_products_or_next_cycle(self):
  http=FakeHTTP();http.pages['https://store.example.test/item/bad']=(200,'<script type="application/ld+json">{"@type":"Product","offers":{"@type":"AggregateOffer"}}</script>')
  http.pages[url(self.cfg['search_url_template'].replace('{query}','keyboard').replace('{page}','1'))]=(200,LIST.replace('/item/1','/item/bad',1))
  w=self.worker(http)
  try:
   for _ in range(3):w.step()
   self.assertIsNone(w.report()['hold']);self.assertEqual(w.report()['totals']['products_failed'],1);self.assertEqual(w.report()['totals']['products_success'],1);self.assertIsNotNone(w.report()['next_cycle_at'])
  finally:w.close()
 def test_transient_retry_exhaustion_defers_to_next_cycle(self):
  class HTTP(FakeHTTP):
   def fetch(self,t):raise Wait('server_error',self_clock()+timedelta(seconds=1))
  self_clock=lambda:self.now;w=self.worker(HTTP())
  try:
   for _ in range(3):w.step();self.now+=timedelta(seconds=60)
   self.assertIsNone(w.report()['hold']);self.assertEqual(w.report()['totals']['tasks_deferred'],1);self.assertIsNotNone(w.report()['next_cycle_at'])
  finally:w.close()
 def test_uncertain_network_and_access_remain_global_holds(self):
  for reason in ('request_outcome_uncertain_review_required','robots_disallowed','nonpublic_DNS_forbidden'):
   with self.subTest(reason=reason),tempfile.TemporaryDirectory() as d:
    class HTTP(FakeHTTP):
     def fetch(self,t):raise Wait(reason,hold=True)
    cfg=fixture_config();box=SimulatedDelivery(cfg,Path(d)/cfg['source']);w=URLWorker(cfg,d,transport=HTTP(),delivery=box)
    try:w.step();self.assertEqual(w.report()['hold'],reason)
    finally:w.close()
 def test_used_new_price_sold_reserved_dedup_restart(self):
  http=FakeHTTP();w=self.worker(http)
  try:
   for _ in range(2):w.step()
   self.now+=timedelta(seconds=60);http.price='9.00'
   for _ in range(2):w.step()
   self.now+=timedelta(seconds=60);http.status='SoldOut'
   for _ in range(2):w.step()
   self.assertEqual(w.report()['content_changes'],{'new':1,'updated':2});self.assertEqual(next(iter(w.state['known'].values()))['extension']['availability'],'ended')
   calls=len(w.delivery.box.fake_API.calls);w.close()
   w=self.worker(http);w.step();self.assertEqual(len(w.delivery.box.fake_API.calls),0)
   self.now+=timedelta(seconds=60);http.status='reserved'
   for _ in range(2):w.step()
   ext=next(iter(w.state['known'].values()))['extension'];self.assertEqual(ext['listing_status'],'reserved');self.assertFalse(ext['purchase_available']);self.assertIsNone(ext['stock_quantity']);self.assertEqual(w.report()['totals']['hold_reserved_status_contract_required'],1)
  finally:w.close()
 def test_discovery_watch_releases_lock_before_idle_wait(self):
  from contextlib import contextmanager,redirect_stdout
  import io
  from services.collector.unified_live.discovery import main
  active=[False];waits=[]
  class State:
   def __init__(self,*args):pass
   @contextmanager
   def lock(self):
    active[0]=True
    try:yield
    finally:active[0]=False
  class Stop:
   def is_set(self):return False
   def wait(self,seconds):waits.append(active[0])
   def set(self):pass
  directory=self.root/'sites.json';directory.write_text(json.dumps({'sites':[],'reference':'SYNTHETIC'}))
  with patch('services.collector.unified_live.discovery.FileState',State),patch('services.collector.unified_live.discovery.threading.Event',Stop),redirect_stdout(io.StringIO()):
   result=main(['--state-dir',str(self.root/'watch'),'--directory',str(directory),'--watch','--max-ticks','2'])
  self.assertEqual(result,0);self.assertEqual(waits,[False])
 def test_bad_site_grant_does_not_stop_discovery_batch(self):
  from services.collector.unified_live.discovery import main
  from contextlib import redirect_stdout
  import io
  directory=self.root/'batch.json';directory.write_text(json.dumps({'reference':'SYNTHETIC','sites':[{'domain':'one.example.test'},{'domain':'two.example.test'}]}))
  with patch('services.collector.unified_live.discovery.probe',side_effect=[ValueError('bad_local_grant'),None]) as check,redirect_stdout(io.StringIO()):
   result=main(['--state-dir',str(self.root/'batch'),'--directory',str(directory),'--scan','--live-metadata','--max-sites','2'])
  self.assertEqual(result,0);self.assertEqual(check.call_count,2)
  sites=DiscoveryStore(self.root/'batch').state['sites'];self.assertEqual(sum(v['verification_status']=='local_grant_configuration_review' for v in sites.values()),1)
 def test_discovery_lock_retries_only_acquisition_contention(self):
  import errno
  from contextlib import contextmanager
  from services.collector.unified_live.discovery import shared_lock
  attempts=[];waits=[]
  class State:
   def __init__(self,*args):pass
   @contextmanager
   def lock(self):
    attempts.append(1)
    if len(attempts)==1:raise BlockingIOError(errno.EAGAIN,'synthetic busy')
    yield
  class Stop:
   def wait(self,seconds):waits.append(seconds);return False
  with patch('services.collector.unified_live.discovery.FileState',State):
   with shared_lock(self.root,Stop()):pass
   with self.assertRaises(OSError):
    with shared_lock(self.root,Stop()):raise OSError('synthetic disk failure')
  self.assertEqual(len(waits),1);self.assertEqual(len(attempts),3)
if __name__=='__main__':unittest.main()
