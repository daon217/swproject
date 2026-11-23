PKG=__package__.rsplit('.tests',1)[0]
import copy,importlib.util,json,tempfile,unittest,os
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import Mock,patch
from ..domeggook_backend import prepare_observation,HTTPBackendTransport
from ..domeggook_delivery import DeliveryPipeline
from ..fixture_data import row,config

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='delivery_');self.root=Path(self.tmp.name).resolve()
        self.now=datetime.now(timezone.utc);self.cfg=config()
    def tearDown(self):self.tmp.cleanup()
    def pipeline(self,tx):return DeliveryPipeline(self.cfg,self.root,tx,clock=lambda:self.now)
    def test_backend_schema_compatibility_and_contract_gap(self):
        from jsonschema import Draft202012Validator,FormatChecker
        schema=json.loads((Path(__file__).parent/'fixtures/backend_observation_v2.schema.json').read_text(encoding='utf-8'))
        body=prepare_observation(row(),self.cfg,selected_domain='product',condition='new')
        Draft202012Validator(schema,format_checker=FormatChecker()).validate(body)
        self.assertIsInstance(body['price'],str);self.assertIsNone(body['description'])
        for key in ('stock_quantity','minimum_order_quantity','minimum_product_total','image_url','description_html'):self.assertNotIn(key,body)
    def test_disabled_does_not_read_credentials_or_write_outbox(self):
        cfg=config();cfg['backend_enabled']=False;tx=Mock()
        p=DeliveryPipeline(cfg,self.root,tx);self.assertEqual(p.stage(row())['status'],'disabled');p.flush()
        tx.assert_not_called();self.assertFalse(p.path.exists())
    def test_synthetic_gate_rejects_real_source_and_URL(self):
        p=self.pipeline(Mock());real=row();real['source']='domeggook'
        self.assertEqual(p.stage(real)['status'],'permission_blocked');self.assertEqual(p.pending_count(),0)
        real=row();real['product_url']='https://domeggook.com/1234'
        self.assertEqual(p.stage(real)['status'],'permission_blocked')
    def test_live_storage_permission_gate_keeps_actual_rows_out(self):
        cfg=config();cfg['backend_delivery']['mode']='live_authorized';cfg['price_semantics_confirmed']=False
        p=DeliveryPipeline(cfg,self.root,Mock());real=row();real['source']='domeggook'
        self.assertEqual(p.stage(real)['status'],'permission_blocked');self.assertNotIn('SYNTHETIC 꿀픽',p.path.read_text())
    def test_identical_restage_and_restart_deliver_once(self):
        tx=Mock(return_value=(201,{'state':'applied','change_kind':'created'}));p=self.pipeline(tx);r=row()
        p.stage(r);p.stage(r);p.flush();p=self.pipeline(tx);p.stage(r);p.flush()
        self.assertEqual(tx.call_count,1);self.assertEqual(p.report()['states']['delivered'],1)
        self.assertFalse(any('body' in e for e in p.state['entries'].values()))
    def test_outage_retry_preserves_exact_event_and_body_across_restart(self):
        tx=Mock(return_value=(0,{}));p=self.pipeline(tx);p.stage(row());p.flush()
        first=tx.call_args.args;self.assertEqual(p.report()['states']['retry_wait'],1)
        p=self.pipeline(tx);p.flush();self.assertEqual(tx.call_count,1)
        self.now+=timedelta(seconds=6);tx.return_value=(200,{'state':'applied','change_kind':'created'});p.flush()
        self.assertEqual(first,tx.call_args.args);self.assertEqual(p.pending_count(),0)
    def test_auth_and_conflict_hold_never_blindly_retry(self):
        tx=Mock(return_value=(409,{}));p=self.pipeline(tx);p.stage(row());p.flush();p.flush()
        self.assertEqual(tx.call_count,1);self.assertTrue(p.report()['hold'])
    def test_retry_bounded_and_quarantine_not_reported_applied(self):
        tx=Mock(return_value=(503,{}));p=self.pipeline(tx);p.stage(row())
        for _ in range(8):p.flush();self.now+=timedelta(hours=1)
        self.assertEqual(tx.call_count,5);self.assertEqual(p.report()['states']['exhausted'],1)
    def test_backend_quarantine_is_terminal_review(self):
        tx=Mock(return_value=(201,{'state':'quarantine','change_kind':'quarantined'}));p=self.pipeline(tx);p.stage(row());p.flush()
        self.assertEqual(p.report()['states']['quarantine'],1);self.assertNotIn('ack_applied',p.report()['totals'])
    def test_new_timestamp_updates_have_new_event_same_product_tuple(self):
        first=row();second=row((datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat(),1200,0)
        a=prepare_observation(first,self.cfg,selected_domain='product',condition='new');b=prepare_observation(second,self.cfg,selected_domain='product',condition='new')
        self.assertNotEqual(a['observation_key'],b['observation_key'])
        self.assertEqual((a['source'],a['source_listing_id'],a['variant_key']),(b['source'],b['source_listing_id'],b['variant_key']))
        self.assertEqual(b['availability'],'out_of_stock')
    def test_HTTP_loopback_requires_explicit_test_approval_and_no_redirect(self):
        with self.assertRaises(ValueError):HTTPBackendTransport('http://127.0.0.1:18765','x'*32)
        tx=HTTPBackendTransport('http://127.0.0.1:18765','SYNTHETIC_TOKEN_'+'x'*32,approved_loopback_test=True)
        tx.session=Mock();tx.session.post.return_value=Mock(status_code=302)
        code,_=tx('/internal/v2/crawl-runs/00000000-0000-0000-0000-000000000001/observations',{})
        self.assertEqual(code,302);self.assertFalse(tx.session.post.call_args.kwargs['allow_redirects'])
    def test_permission_revocation_erases_pending_payload(self):
        tx=Mock(return_value=(0,{}));p=self.pipeline(tx);p.stage(row());p.flush()
        # Change the profile to a live profile without grants: no fixture bypass remains.
        self.cfg['backend_delivery']['mode']='live_authorized';self.cfg['price_semantics_confirmed']=True
        p=DeliveryPipeline(self.cfg,self.root,tx,clock=lambda:self.now)
        self.assertEqual(p.report()['states']['revoked'],1);self.assertFalse(any('body' in e for e in p.state['entries'].values()))
    def test_collection_store_survives_delivery_stage_failure(self):
        from ..domeggook_watch_delivery import DeliveryStore
        store=Mock();store.put.return_value=('update',False);sender=Mock();sender.stage.side_effect=OSError('SYNTHETIC unavailable disk')
        callback=Mock();proxy=DeliveryStore(store,sender,callback)
        self.assertEqual(proxy.put(row()),('update',False));self.assertEqual(proxy.needs_reobserve,1)
        self.assertEqual(callback.call_args.args[1],'stage_failed')
    def test_watch_cycle_flushes_before_and_after_collection(self):
        from ..domeggook_watch_delivery import DeliveryDiscoveryRun
        import threading
        worker=object.__new__(DeliveryDiscoveryRun);worker.stop=threading.Event();worker.delivery=Mock();worker.delivery.backpressure.return_value=False
        with patch(PKG+'.domeggook_discovery.DiscoveryRun.cycle',return_value={'source_checkpoint':'preserved'}) as collect:
            for _ in range(3):self.assertEqual(worker.cycle()['source_checkpoint'],'preserved')
        self.assertEqual(collect.call_count,3);self.assertEqual(worker.delivery.flush.call_count,6)
