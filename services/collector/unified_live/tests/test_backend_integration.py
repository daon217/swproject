import copy,os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from services.collector.unified_live.mock import fixture_config,product,FakeHTTP
from services.collector.unified_live.parser import normalize
from services.collector.unified_live.changes import ChangeDelivery,rekey
from services.collector.unified_live.delivery_extras import extension
from services.collector.collector_ops.mock import SimulatedDelivery
from services.collector.collector_ops.delivery_contract import safe_error,safe_checks,catalog_review,ListingExtension
from services.collector.collector_ops.backend_transport import origin_check

class BackendIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.cfg=fixture_config();self.now=datetime.now(timezone.utc)
 def tearDown(self):self.tmp.cleanup()
 def n(self,price='12.00'):return normalize(product(price),'https://store.example.test/item/1',self.now.isoformat(),self.cfg)
 def gate(self,responses=None,extras=False):
  cfg=copy.deepcopy(self.cfg);cfg['test_extensions_enabled']=extras
  return ChangeDelivery(SimulatedDelivery(cfg,self.root,responses=responses,clock=lambda:self.now),self.root)
 def test_409_item_isolated_and_normal_item_delivers(self):
  g=self.gate([(409,{'error_code':'PAYLOAD_CONFLICT'}),(201,{'state':'applied'})]);g.stage(self.n());g.flush()
  n=self.n('13');n['observation']['source_listing_id']='OTHER';rekey(n['observation']);g.stage(n);g.flush()
  self.assertFalse(g.box.state['hold']);self.assertEqual([e['status'] for e in g.box.state['entries'].values()],['held','delivered']);self.assertEqual(len(g.box.fake_API.calls),2)
 def test_409_run_conflict_still_holds_source(self):
  g=self.gate([(409,{'error_code':'RUN_SOURCE_CONFLICT'})]);g.stage(self.n());g.flush();self.assertTrue(g.box.state['hold'])
 def test_validation_rejection_changed_data_only(self):
  g=self.gate([(422,{'error_code':'INVALID_INPUT','fields':[['body','price']]})]);g.stage(self.n());g.flush();self.now+=timedelta(seconds=1)
  self.assertEqual(g.stage(self.n())['status'],'previous_event_requires_review');self.assertEqual(g.stage(self.n('13'))['status'],'pending');self.assertEqual(len(g.box.fake_API.calls),1)
 def test_quarantine_reason_controls_changed_revalidation(self):
  for code,expected in [('PRICE_ANOMALY','pending'),('IDENTITY_CONFLICT','previous_event_requires_review')]:
   with self.subTest(code=code),tempfile.TemporaryDirectory() as d:
    self.root=Path(d);g=self.gate([(201,{'state':'quarantine','error_code':code})]);g.stage(self.n());g.flush();self.now+=timedelta(seconds=1);self.assertEqual(g.stage(self.n('13'))['status'],expected)
 def test_exhausted_transient_recovers_exact_body_after_cooldown(self):
  g=self.gate([(503,{})]*3);g.box.settings['max_recovery_rounds']=1;g.stage(self.n())
  for _ in range(3):g.flush();self.now+=timedelta(seconds=100)
  self.assertEqual(g.stage(self.n('13'))['status'],'previous_event_requires_review');self.now+=timedelta(hours=1);g.flush();calls=g.box.fake_API.calls
  self.assertEqual(len(calls),4);self.assertTrue(all(x[1]==calls[0][1] for x in calls));self.assertEqual(g.report()['states']['delivered'],1)
 def test_exhausted_validation_not_recovered(self):
  g=self.gate();g.stage(self.n());e=next(iter(g.box.state['entries'].values()));e.update(status='exhausted',last_status=422,attempts=5);g.box.save();self.now+=timedelta(hours=2);g.flush();self.assertEqual(len(g.box.fake_API.calls),0)
 def test_extension_mapping_identity_and_no_invented_seller(self):
  n=self.n();n['metadata']['matching_profile'].update(brand='Native brand',model_number='MODEL-1',color='red',size='L');e=extension(n);ListingExtension.model_validate(e)
  self.assertEqual(e['matching_profile']['seller_name'],'SYNTHETIC seller');self.assertEqual(e['variant_key'],n['observation']['variant_key']);self.assertNotEqual(e['observation_key'],n['observation']['observation_key']);n['seller']=None;self.assertNotIn('seller_name',extension(n)['matching_profile'])
 def test_extension_waits_for_observation_ACK(self):
  g=self.gate([(503,{})],True)
  with patch.dict(os.environ,COLLECTOR_DELIVERY_APPROVED='yes'):g.stage(self.n());g.flush()
  self.assertEqual(len(g.box.fake_API.calls),1);self.assertEqual(g.extras.report()['extension_states']['pending'],1)
 def test_pending_extension_retries_same_payload_and_survives_restart(self):
  g=self.gate([(201,{'state':'applied'}),(202,{'state':'pending','error_code':'OFFER_NOT_YET_OBSERVED'}),(201,{'state':'applied'})],True)
  with patch.dict(os.environ,COLLECTOR_DELIVERY_APPROVED='yes'):
   g.stage(self.n());g.flush();self.assertEqual(g.extras.report()['extension_states']['retry_wait'],1);g=ChangeDelivery(g.box,self.root);self.now+=timedelta(minutes=1);g.flush()
  self.assertEqual(g.extras.report()['extension_states']['delivered'],1);self.assertEqual(g.box.fake_API.calls[1],g.box.fake_API.calls[2])
 def test_check_confirmed_or_mismatch(self):
  for mismatch in (False,True):
   with self.subTest(mismatch=mismatch),tempfile.TemporaryDirectory() as d:
    self.root=Path(d);g=self.gate(extras=True);g.stage(self.n());g.box.flush();self.now+=timedelta(seconds=1);n=self.n();g.stage(n);g.extras.data['extensions'].clear();b=n['observation'];ident={k:b[k] for k in ('source_listing_id','variant_key')}
    g.box.fake_API.responses=[(200,{'confirmed':0 if mismatch else 1,'mismatch':[ident] if mismatch else [],'unknown':[],'rejected':[]})]
    with patch.dict(os.environ,COLLECTOR_DELIVERY_APPROVED='yes'):g.flush()
    self.assertEqual(g.extras.report()['pending_checks'],0);self.assertEqual(len(g.box.state['entries']),2 if mismatch else 1)
 def test_auxiliary_routes_reject_wrong_origin_or_query(self):
  base='http://api:8000';origin_check(base+'/internal/v2/listing-checks',base)
  for url in ('http://evil:8000/internal/v2/listing-checks',base+'/admin',base+'/internal/v2/listing-checks?token=x'):
   with self.subTest(url=url),self.assertRaises(Exception):origin_check(url,base)
 def test_error_sanitizer_does_not_persist_input_or_token(self):
  self.assertEqual(safe_error({'detail':'secret token','error':{'code':'INVALID_INPUT','message':'secret'},'input':'secret','fields':[['body','currency']]}),{'error_code':'INVALID_INPUT','fields':[['body','currency']]})
 def test_catalog_approval_failure_does_not_expand_allowlist(self):
  b=self.n()['observation'];cfg=copy.deepcopy(self.cfg);cfg['backend_catalog']={'url_hosts':['other.test'],'currencies':['KRW']};self.assertEqual(catalog_review(b,cfg)['missing_fields'],['url','currency']);self.assertEqual(cfg['backend_catalog']['url_hosts'],['other.test'])
 def test_food_raw_notice_and_unknown_not_safe_claims(self):
  n=self.n();n['observation']['selected_domain']='food';n['food_evidence']={'ingredients_raw':'Native raw flour, milk','allergen_notice_raw':'Contains milk','allergens_declared':['milk'],'allergen_status':'reported'};e=extension(n);self.assertEqual(e['food_evidence']['ingredients_raw'],'Native raw flour, milk');self.assertNotIn('safe_to_consume',e['food_evidence']);n['food_evidence']={};self.assertEqual(extension(n)['food_evidence'],{'evidence_status':'not_reported'})
 def test_unknown_YES24_missing_fields_never_default(self):
  from services.collector.marketplace_live.normalize import yes24
  cfg=copy.deepcopy(self.cfg);cfg['allowed_product_hosts']=['www.yes24.com'];n=yes24({'itemId':'1','title':'Native title','link':'https://www.yes24.com/Product/Goods/1'},self.now.isoformat(),cfg);self.assertIsNone(n['observation']);self.assertEqual(set(n['missing_fields']),{'price','currency','condition','availability','variant_key'});self.assertTrue(n['normalization_diagnostics']['unknown_values_not_defaulted'])

 def test_real_outbox_reaches_exhausted_recovery_not_only_mock_subclass(self):
  from services.collector.marketplace_live.delivery import Outbox
  from unittest.mock import Mock
  tx=Mock(return_value=(201,{'state':'applied'}));box=Outbox(self.cfg,self.root,transport=tx,clock=lambda:self.now);box.stage(self.n());e=next(iter(box.state['entries'].values()));e.update(status='exhausted',last_status=503,attempts=3,next_attempt_at=(self.now-timedelta(hours=1)).isoformat());box.save();box.flush();self.assertEqual(tx.call_count,1);self.assertEqual(box.report()['states']['delivered'],1)
 def test_already_queued_product_is_catalog_held_and_restored_exactly(self):
  from services.collector.marketplace_live.delivery import Outbox
  from unittest.mock import Mock
  tx=Mock(return_value=(201,{'state':'applied'}));box=Outbox(self.cfg,self.root,transport=tx,clock=lambda:self.now);n=self.n();box.stage(n)
  with patch.dict(os.environ,COLLECTOR_BACKEND_CATALOG_HOSTS='other.test',COLLECTOR_BACKEND_CATALOG_CURRENCIES='USD'):
   box.flush();self.assertEqual(tx.call_count,0);self.assertEqual(box.report()['states']['catalog_held'],1)
  with patch.dict(os.environ,COLLECTOR_BACKEND_CATALOG_HOSTS='store.example.test',COLLECTOR_BACKEND_CATALOG_CURRENCIES='USD'):box.flush()
  self.assertEqual(tx.call_count,1);self.assertEqual(tx.call_args.args[1],n['observation'])
 def test_catalog_recovery_is_offline_and_targeted(self):
  from services.collector.marketplace_live.delivery import Outbox
  from services.collector.collector_ops.recover_delivery import recover
  from unittest.mock import Mock
  box=Outbox(self.cfg,self.root,transport=Mock(return_value=(422,{'error_code':'INVALID_INPUT','fields':[['body','url']]})),clock=lambda:self.now);box.stage(self.n());box.flush();cfg=dict(self.cfg,backend_catalog={'url_hosts':['store.example.test'],'currencies':['USD']})
  self.assertEqual(recover(box.path,cfg)['restorable_catalog_events'],1);self.assertEqual(recover(box.path,cfg,True)['HTTP_requests'],0)
 def test_food_notice_raw_survives_description_label_extraction(self):
  from services.collector.unified_live.food import evidence
  e=evidence({'name':'native food','category':'food','description':'원재료명: 우유, 밀\n알레르기: 우유, 밀'},source='html_test',url='https://store.example.test/item/1',at=self.now.isoformat());self.assertEqual(e['ingredients_raw'],'우유, 밀');self.assertEqual(e['allergen_notice_raw'],'우유, 밀');self.assertIsNone(e['safe_to_consume'])

 def test_invalid_extension_field_does_not_block_valid_observation(self):
  g=self.gate(extras=True);n=self.n();n['metadata']['matching_profile']['brand']='x'*201;self.assertEqual(g.stage(n)['status'],'pending');self.assertEqual(g.extras.data['totals']['extension_validation_held'],1);g.box.flush();self.assertEqual(g.box.report()['states']['delivered'],1)

 def test_dome_matching_requires_real_field_storage_and_reuse_grant(self):
  g=self.gate(extras=True);g.box.source='domeggook';self.assertEqual(g.extras.licensed_matching_fields(),set());g.box.cfg['storage_grants']={'brand':{'storage':True,'reuse':True,'reference':'SYNTHETIC_ONLY','expires_at':(self.now+timedelta(days=1)).isoformat()}};self.assertEqual(g.extras.licensed_matching_fields(),{'brand'})
 def test_extension_profile_reversion_is_not_suppressed_by_old_history(self):
  g=self.gate(extras=True)
  for brand in ('A','B','A'):
   n=self.n();n['metadata']['matching_profile']['brand']=brand;g.stage(n);g.box.flush();self.now+=timedelta(seconds=1)
  self.assertEqual(len(g.extras.data['extensions']),3)
 def test_missing_runtime_token_stops_auxiliary_delivery(self):
  g=self.gate(extras=True);g.stage(self.n());g.box.flush();g.box.state['synthetic_only']=False
  with patch.dict(os.environ,COLLECTOR_DELIVERY_APPROVED='yes',KKULPICK_BACKEND_TOKEN=''):g.extras.flush()
  self.assertEqual(len(g.box.fake_API.calls),1)

 def test_corrected_observation_recovers_unsent_extension_dependency(self):
  g=self.gate([(201,{'state':'quarantine','error_code':'PRICE_ANOMALY'}),(201,{'state':'applied'}),(201,{'state':'applied'})],True);g.stage(self.n());g.box.flush();self.now+=timedelta(seconds=1);g.stage(self.n('13'))
  with patch.dict(os.environ,COLLECTOR_DELIVERY_APPROVED='yes'):g.flush()
  self.assertEqual(g.extras.report()['extension_states']['delivered'],1);self.assertEqual(g.extras.data['totals']['extension_dependency_recovered'],1)

 def test_exhausted_legacy_entry_without_due_time_gets_persistent_cooldown(self):
  from services.collector.marketplace_live.delivery import Outbox
  from unittest.mock import Mock
  tx=Mock(return_value=(201,{'state':'applied'}));box=Outbox(self.cfg,self.root,transport=tx,clock=lambda:self.now);box.stage(self.n());e=next(iter(box.state['entries'].values()));e.update(status='exhausted',last_status=503,attempts=3);box.save();box.flush();self.assertEqual(tx.call_count,0);self.assertIn('recovery_after',e);self.now+=timedelta(seconds=901);box.flush();self.assertEqual(tx.call_count,1)
