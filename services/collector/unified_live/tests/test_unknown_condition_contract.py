import json,copy,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from services.collector.unified_live.mock import fixture_config,product,FakeHTTP
from services.collector.unified_live.parser import normalize
from services.collector.unified_live.engine import URLWorker
from services.collector.collector_ops.mock import SimulatedDelivery
from services.collector.collector_ops import backend_transport as transport
from services.collector.domeggook_live.domeggook_backend_contract import Observation

BASE='https://store.example.test'

class UnknownConditionContract(unittest.TestCase):
 def setUp(self):
  self.cfg=fixture_config();self.cfg.update(homepage_crawl=True,mode='general');self.at=datetime.now(timezone.utc).isoformat()
 def norm(self,html):return normalize(html,BASE+'/item/1',self.at,self.cfg)
 def test_missing_and_explicit_unknown_are_explicit_v2_values(self):
  for value in ('','unknown'):
   with self.subTest(value=value):
    r=self.norm(product().replace('https://schema.org/UsedCondition',value));body=r['observation']
    self.assertIsNotNone(body);self.assertEqual(body['condition'],'unknown');self.assertEqual(body['schema_version'],2)
    self.assertNotIn('condition',body['field_presence']);self.assertIsNone(r['metadata']['stock_quantity'])
 def test_known_values_and_legacy_default_preserved(self):
  for value,expected in [('UsedCondition','used'),('NewCondition','new')]:
   body=self.norm(product().replace('UsedCondition',value))['observation'];self.assertEqual(body['condition'],expected)
   context={'hosts':self.cfg['allowed_product_hosts'],'currencies':self.cfg['currencies']}
   self.assertEqual(Observation.model_validate(body,context=context).condition,expected)
   del body['condition'];self.assertEqual(Observation.model_validate(body,context=context).condition,'new')
 def test_unknown_is_not_used_and_unsupported_condition_is_not_downgraded(self):
  self.cfg['mode']='used';r=self.norm(product().replace('https://schema.org/UsedCondition',''))
  self.assertIsNone(r['observation']);self.assertIn('used_condition_required',r['missing_fields'])
  self.cfg['mode']='general';r=self.norm(product().replace('UsedCondition','RefurbishedCondition'));self.assertIsNone(r['observation'])
 def test_unknown_does_not_invent_other_required_values(self):
  original=json.loads(product().split('application/ld+json">')[1].split('</script>')[0]);original.pop('itemCondition')
  for field in ('price','priceCurrency','availability'):
   native=copy.deepcopy(original);native['offers'].pop(field)
   r=self.norm('<script type="application/ld+json">'+json.dumps(native)+'</script>');self.assertIsNone(r['observation'])
 def test_unknown_worker_observation_extension_ACK_and_duplicate(self):
  from services.collector.unified_live.changes import ChangeDelivery
  with tempfile.TemporaryDirectory() as root:
   box=SimulatedDelivery(dict(self.cfg,test_extensions_enabled=True),Path(root));gate=ChangeDelivery(box,Path(root))
   try:
    r=self.norm(product().replace('https://schema.org/UsedCondition',''));gate.stage(r)
    with patch.dict(os.environ,{'COLLECTOR_DELIVERY_APPROVED':'yes'}):gate.flush()
    self.assertEqual(len(box.fake_API.calls),2);self.assertEqual(box.fake_API.calls[0][1]['condition'],'unknown')
    self.assertEqual(len(gate.extras.data['extensions']),1)
    self.assertEqual(next(iter(gate.extras.data['extensions'].values()))['status'],'delivered')
    self.assertEqual(gate.stage(r)['status'],'unchanged_skipped');self.assertEqual(len(box.fake_API.calls),2)
   finally:gate.close()

 def test_unknown_food_keeps_existing_evidence_permission_gate(self):
  self.cfg.update(evidence_storage=True)
  self.cfg['rights']['allowed_uses'].append('evidence_storage')
  html=product().replace('https://schema.org/UsedCondition','').replace('"name": "SYNTHETIC mechanical keyboard"','"name": "SYNTHETIC food", "category": "food", "ingredients": "milk", "allergens": "Contains milk"')
  with tempfile.TemporaryDirectory(dir=Path.cwd()) as root:
   http=FakeHTTP();http.pages[BASE+'/item/1']=(200,html)
   box=SimulatedDelivery(self.cfg,Path(root)/self.cfg['source'])
   worker=URLWorker(self.cfg,Path(root),transport=http,delivery=box)
   try:
    (worker.root/'evidence').mkdir(exist_ok=True)
    worker.page(worker.task('detail',BASE+'/item/1'));worker.delivery.flush()
    self.assertEqual(len(box.fake_API.calls),1);body=box.fake_API.calls[0][1]
    self.assertEqual((body['selected_domain'],body['condition']),('food','unknown'))
   finally:worker.close()

class BackendAddressRoles(unittest.TestCase):
 def test_explicit_collector_origin_overrides_config_not_reader(self):
  env={'COLLECTOR_BACKEND_TRANSPORT':'internal_http','COLLECTOR_DELIVERY_APPROVED':'yes','COLLECTOR_BACKEND_BASE_URL':'http://collector.example.test:8000','KKULPICK_API_BASE':'https://reader.example.com'}
  with patch.dict(os.environ,env,clear=True),patch.object(transport,'RoutedBackend') as backend:
   transport.build_backend('https://configured.example.com','',None)
   self.assertEqual(backend.call_args.args[0],env['COLLECTOR_BACKEND_BASE_URL'])
   plan=transport.endpoint_plan('https://configured.example.com');self.assertTrue(plan['ready']);self.assertTrue(plan['environment_override'])
 def test_reader_variable_does_not_override_collector_config(self):
  with patch.dict(os.environ,{'KKULPICK_API_BASE':'https://reader.example.com'},clear=True),patch.object(transport,'RoutedBackend') as backend:
   transport.build_backend('https://configured.example.com','',None)
   self.assertEqual(backend.call_args.args[0],'https://configured.example.com');self.assertTrue(transport.endpoint_plan('https://configured.example.com')['ready'])
   self.assertFalse(transport.endpoint_plan('')['ready'])
