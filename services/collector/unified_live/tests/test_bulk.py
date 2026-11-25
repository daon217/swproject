"""All fixtures local; external batch is executed and reported separately."""
import copy,csv,json,os,tempfile,threading,time,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.robotparser import RobotFileParser
from unittest.mock import patch
from services.collector.unified_live.bulk import Batch,export,candidates,publisher_candidates,sitemap_links,BatchHTTP
from services.collector.unified_live.mock import fixture_config,product,LIST
from services.collector.unified_live.transport import Wait
from services.collector.unified_live.fleet import FleetSupervisor

class FakeHTTP:
 calls=[];active=0;peak=0;mutex=threading.Lock();fail=set();incomplete=False
 def __init__(self,cfg,root,approval,clock):
  self.cfg=cfg;self.host=cfg['allowed_product_hosts'][0];self.clock=clock;self.state={'requests':[],'hold':None};self.robots=RobotFileParser();self.robots.parse(['User-agent: *','Allow: /'])
 def fetch(self,target):
  with self.mutex:FakeHTTP.active+=1;FakeHTTP.peak=max(FakeHTTP.peak,FakeHTTP.active)
  try:
   time.sleep(.005);FakeHTTP.calls.append(target);self.state['requests'].append({'status':200})
   if self.host in self.fail:raise Wait('robots_disallowed',hold=True)
   if '/bad' in target:return 200,'<script type="application/ld+json">{"@type":"Product","offers":{"@type":"AggregateOffer"}}</script>'
   if '/item/' not in target:return 200,LIST.replace('store.example.test',self.host)
   html=product().replace('store.example.test',self.host)
   if self.incomplete:html=html.replace('UsedCondition','UNKNOWN')
   return 200,html
  finally:
   with self.mutex:FakeHTTP.active-=1
 def close(self):pass

class BulkTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);FakeHTTP.calls=[];FakeHTTP.fail=set();FakeHTTP.incomplete=False;FakeHTTP.active=0;FakeHTTP.peak=0
 def tearDown(self):self.tmp.cleanup()
 def item(self,host='store.example.test',kind='local_fixture'):return {'domain':host,'url':'https://'+host+'/','reference':'SYNTHETIC','platform':'fixture','sample_kind':kind}
 def approval(self,host='store.example.test',storage=False):
  a=fixture_config()['rights'];a.update(test_allowed=True,allowed_hosts=[host],start_urls=['https://'+host+'/search'],backend_enabled=True,backend_owner_approved=True,price_semantics_confirmed=True,currencies=['USD'],backend_delivery=fixture_config()['backend_delivery'])
  if not storage:a['allowed_uses']=['lookup']
  return a
 def runbatch(self,items=None,approvals=None,activate=False):return Batch(self.root,http_factory=FakeHTTP).run(items or [self.item()],approvals or {'store.example.test':self.approval()},activate=activate)
 def test_candidate_dns_and_www_dedup_and_private_exclusion(self):
  seen=[]
  def resolver(h):
   seen.append(h)
   if h=='missing.example.test':raise OSError()
  rows,stats=candidates([{'url':'https://www.shop.example.test/'},{'url':'https://shop.example.test/x'},{'url':'http://bad.test/'},{'url':'https://127.0.0.1/'},{'url':'https://missing.example.test/'}],resolver)
  self.assertEqual(len(rows),1);self.assertEqual(len(stats['rejected']),3);self.assertEqual(len(seen),2)
 def test_public_directory_does_not_import_activation(self):
  found=publisher_candidates('<a class="shop" href="https://new.example.test/">store</a><a class="shop" href="http://127.0.0.1/">bad</a>','https://directory.example.test/','a.shop')
  self.assertEqual(len(found),1);self.assertNotIn('enabled',found[0])
 def test_unpermitted_domain_zero_network(self):
  rows=self.runbatch(approvals={'store.example.test':{}});self.assertEqual(rows[0]['test_status'],'ACCESS_REVIEW');self.assertEqual(FakeHTTP.calls,[])
 def test_prohibited_is_blocked_without_requests(self):
  rows=self.runbatch(approvals={'store.example.test':{'explicitly_prohibited':True}});self.assertEqual(rows[0]['test_status'],'BLOCKED');self.assertFalse(FakeHTTP.calls)
 def test_lookup_only_verifies_but_cannot_activate(self):
  row=self.runbatch(activate=True)[0];self.assertEqual(row['test_status'],'VERIFIED');self.assertEqual(row['valid_product_count'],1);self.assertEqual(row['permission_status'],'lookup_test_only');self.assertFalse(row['profile_registered'])
 def test_storage_and_repeat_approval_registers_profile_and_fleet(self):
  a=self.approval(storage=True);a['activation_approved']=True
  rows=self.runbatch(approvals={'store.example.test':a},activate=True);self.assertEqual(rows[0]['test_status'],'ACTIVE');self.assertEqual(len(list((self.root/'profiles').glob('*.json'))),1)
  ident=next(iter(json.loads((self.root/'discovery/discovery_registry.json').read_text())['sites']))
  fleet=FleetSupervisor(self.root/'fleet',self.root/'discovery',json.loads((self.root/'fleet-grants.json').read_text()));self.assertEqual(len(fleet.desired()),1)
 def test_no_automatic_external_demo_activation(self):
  a=self.approval(storage=True);a['activation_approved']=True;row=self.runbatch(items=[self.item(kind='external_demo')],approvals={'store.example.test':a},activate=True)[0];self.assertEqual(row['test_status'],'VERIFIED');self.assertFalse(row['profile_registered'])
 def test_incomplete_product_held_not_success(self):
  FakeHTTP.incomplete=True;row=self.runbatch()[0];self.assertEqual(row['test_status'],'INCOMPLETE');self.assertEqual(row['valid_product_count'],0);self.assertIn('condition',row['missing_fields'])
 def test_site_failure_does_not_stop_other_sites(self):
  FakeHTTP.fail={'bad.example.test'};items=[self.item(h) for h in ('bad.example.test','store.example.test')];approvals={h:self.approval(h) for h in ('bad.example.test','store.example.test')};rows=self.runbatch(items,approvals);self.assertEqual([r['test_status'] for r in rows],['BLOCKED','VERIFIED'])
 def test_concurrency_is_bounded(self):
  hosts=[f's{i}.example.test' for i in range(12)];Batch(self.root,concurrency=2,http_factory=FakeHTTP).run([self.item(h) for h in hosts],{h:self.approval(h) for h in hosts});self.assertLessEqual(FakeHTTP.peak,2);self.assertGreater(FakeHTTP.peak,1)
 def test_duplicate_input_only_one_domain_writer(self):
  rows=self.runbatch(items=[self.item(),self.item()]);self.assertEqual(len(rows),1);self.assertEqual(len(FakeHTTP.calls),2)
 def test_sitemap_rejects_external_HTTP_and_entities(self):
  xml='<urlset><url><loc>https://store.example.test/item/1</loc></url><url><loc>http://127.0.0.1/</loc></url></urlset>';self.assertEqual(len(sitemap_links(xml,'https://store.example.test/','store.example.test')),1)
  with self.assertRaises(ValueError):sitemap_links('<!DOCTYPE xml><x/>','https://store.example.test/','store.example.test')
 def test_csv_separates_local_success_and_sanitizes_formulas(self):
  rows=self.runbatch();rows[0]['platform']='=CMD()';export(rows,self.root/'out')
  with (self.root/'out/korean-mall-success.csv').open(encoding='utf-8-sig') as f:self.assertEqual(list(csv.DictReader(f)),[])
  with (self.root/'out/korean-mall-candidates.csv').open(encoding='utf-8-sig') as f:self.assertEqual(list(csv.DictReader(f))[0]['platform'],"'=CMD()")
 def test_expired_permission_never_fetches(self):
  a=self.approval();a['expires_at']='2000-01-01T00:00:00+00:00';row=self.runbatch(approvals={'store.example.test':a})[0];self.assertEqual(row['test_status'],'ACCESS_REVIEW');self.assertFalse(FakeHTTP.calls)
 def test_invalid_global_concurrency_rejected(self):
  with self.assertRaises(ValueError):Batch(self.root,concurrency=50)
 def test_bad_product_does_not_stop_following_details(self):
  class HTTP(FakeHTTP):
   def fetch(self,target):
    if '/search' in target:return 200,LIST.replace('/item/1','/bad',1)
    return super().fetch(target)
  row=Batch(self.root,http_factory=HTTP).run([self.item()],{'store.example.test':self.approval()})[0]
  self.assertEqual(row['valid_product_count'],1);self.assertEqual(row['test_status'],'VERIFIED')
 def test_domain_budget_persists_without_reset(self):
  a=self.approval();cfg={'source':'html_test_budget','base_url':'https://store.example.test/','enabled':True,'requests_per_hour':1,'requests_per_24h':2,'request_interval_seconds':2};clock=lambda:datetime.now(timezone.utc)
  http=BatchHTTP(cfg,self.root/'ledger',a,clock);entry=http.reserve(cfg['base_url']);entry['status']=200;http.save();http.close()
  http=BatchHTTP(cfg,self.root/'ledger',a,clock)
  with self.assertRaises(Wait):http.reserve(cfg['base_url'])
  self.assertEqual(len(http.state['requests']),1);http.close()
 def test_activation_preserves_existing_profile(self):
  a=self.approval(storage=True);a['activation_approved']=True
  self.runbatch(approvals={'store.example.test':a},activate=True);path=next((self.root/'profiles').glob('*.json'));before=path.read_bytes()
  a['selectors']={'name':'h1'};row=self.runbatch(approvals={'store.example.test':a},activate=True)[0]
  self.assertEqual(path.read_bytes(),before);self.assertEqual(row['failure_reason'],'activation_configuration_or_history_review')
 def test_reusable_harvest_serializes_same_publisher_domain(self):
  from services.collector.unified_live.bulk_discover import harvest
  active={};peak={};guard=threading.Lock()
  class Reader:
   def __init__(self,host,targets,root):self.host=host;self.cfg={'request_interval_seconds':1};self.state={'requests':[]}
   def fetch(self,target):
    with guard:active[self.host]=active.get(self.host,0)+1;peak[self.host]=max(peak.get(self.host,0),active[self.host])
    try:
     time.sleep(.02);self.state['requests'].append({'status':200});return 200,'<a href="https://store.example.test/">store.example.test</a>'
    finally:
     with guard:active[self.host]-=1
   def close(self):pass
  specs=[{'url':'https://publisher.example.test/'+str(i),'metadata_read_approved':True,'selector':'a[href]','domain_label_only':True} for i in range(4)]
  rows,audit=harvest(specs,self.root,http_factory=Reader,resolver=lambda h:'93.184.216.34')
  self.assertEqual(len(rows),1);self.assertEqual(peak['publisher.example.test'],1);self.assertEqual(audit['raw_candidate_links'],4)
 def test_unapproved_publisher_does_not_fetch(self):
  from services.collector.unified_live.bulk_discover import harvest
  class Reader:
   def __init__(self,*args):raise AssertionError('must not create network reader')
  rows,audit=harvest([{'url':'https://publisher.example.test/','selector':'a'}],self.root,http_factory=Reader)
  self.assertEqual(rows,[]);self.assertEqual(audit['publisher_results'][0]['status'],'ACCESS_REVIEW')
 def test_discovery_evaluation_can_be_persisted_once_per_fleet_tick(self):
  from services.collector.unified_live.discovery import DiscoveryStore
  store=DiscoveryStore(self.root);ident=store.add({'domain':'store.example.test'},'SYNTHETIC')
  with patch.object(store,'save') as save:store.evaluate(ident,persist=False);save.assert_not_called()
if __name__=='__main__':unittest.main()
