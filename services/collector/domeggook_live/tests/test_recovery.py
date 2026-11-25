"""Offline fault injection: no credentials, provider calls or team DB."""
import copy
import threading
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from ..runtime import STATE_ROOT, now
from ..progress import save
from ..domeggook_open import OpenClient, SafeAPIError
from ..domeggook_operations import budget_delay, FileState
from ..domeggook_discovery import DiscoveryRun, initial_state, queue_loop
from ..domeggook_delivery import DeliveryPipeline
from ..domeggook_watch_delivery import DeliveryDiscoveryRun
from ..fixture_data import row, config
from .test_discovery import fixture_config, FakeQueueClient

PKG=__package__.rsplit('.tests',1)[0]


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=STATE_ROOT)
        self.root=Path(self.tmp.name)
        self.current=datetime.now(timezone.utc)

    def tearDown(self):self.tmp.cleanup()

    def client(self):
        with patch(PKG+'.domeggook_open.read_key',return_value='SYNTHETIC'):
            c=OpenClient(cap=10,ledger_path=self.root/'request_ledger.json')
        self.addCleanup(c.close)
        return c

    def uncertain(self,status='network_error',age=7201,hold='uncertain_request_no_auto_resend'):
        entry={'mode':'getItemList','status':status,'at':(self.current-timedelta(seconds=age)).isoformat(),
               'task_id':'page:1:0:1','queue':'discovery'}
        save(self.root/'request_ledger.json',{'requests':[entry],'hold':hold})
        return entry

    def test_timeout_no_immediate_resend_and_cooldown_survives_restart(self):
        c=self.client();c.session.get=Mock(side_effect=requests.Timeout('SYNTHETIC'))
        with self.assertRaisesRegex(SafeAPIError,'network_error_request_outcome_uncertain'):
            c.get('getItemList',kw='SYNTHETIC',pg=1)
        with self.assertRaises(SafeAPIError):c.get('getItemList',kw='SYNTHETIC',pg=1)
        self.assertEqual(c.session.get.call_count,1)
        restarted=self.client()
        self.assertGreater(restarted.recover_uncertain(current=self.current),7190)
        self.assertEqual(len(restarted.state['requests']),1)

    def test_recovery_retains_budget_debit_and_is_idempotent(self):
        # Fix the fixture at 15:00 KST: a 7201-second-old request must remain
        # in the same KST day. Around midnight the old wall-clock fixture
        # crossed the daily reset and incorrectly expected a budget hold.
        self.current=self.current.replace(hour=6,minute=0,second=0,microsecond=0)
        original=self.uncertain();c=self.client()
        self.assertEqual(c.recover_uncertain(current=self.current),0)
        entry=c.state['requests'][0]
        for k,v in original.items():self.assertEqual(entry[k],v)
        self.assertEqual(entry['outcome'],'uncertain_counted_no_response')
        self.assertIsNone(c.recover_uncertain(current=self.current))
        cfg=fixture_config();cfg['requests_per_kst_day']=1
        self.assertEqual(budget_delay(c.state['requests'],cfg,self.current)[1],'daily_budget_wait')
        self.assertIsNone(self.client().state['hold'])

    def test_reserved_crash_recovers_without_HTTP(self):
        self.uncertain(status='reserved',hold=None);c=self.client();c.session.get=Mock()
        self.assertEqual(c.state['hold'],'interrupted_request_outcome_unknown')
        c.recover_uncertain(current=self.current);c.session.get.assert_not_called()
        self.assertIsNone(self.client().state['hold'])

    def test_security_schema_and_circuit_holds_never_auto_clear(self):
        for hold in ('access_refused_or_redirect','API_reported_error_requires_review',
                     'non_JSON_or_challenge','failure_rate_circuit_open'):
            self.uncertain(hold=hold);c=self.client()
            self.assertIsNone(c.recover_uncertain(current=self.current))
            self.assertEqual(c.state['hold'],hold)

    def test_inflight_page_recovery_keeps_cursor_and_counts_failed_task_once(self):
        self.uncertain();cfg=fixture_config();c=self.client()
        state=initial_state(cfg)
        state['inflight']={'kind':'page','task_id':'page:1:0:1','key':'1:0:1','ledger_start':0}
        save(self.root/'discovery_checkpoint.json',state)
        run=DiscoveryRun(cfg,c,self.root)
        self.assertIsNotNone(run.state['inflight'])
        c.recover_uncertain(current=self.current);run.recover_inflight();run.recover_inflight()
        self.assertEqual(run.state['discovery']['page'],1)
        self.assertEqual(run.state['discovery']['failures']['1:0:1'],1)
        self.assertIsNone(run.state['inflight'])

    def test_inflight_detail_failure_does_not_double_count_or_invent_response(self):
        cfg=fixture_config();self.uncertain();c=self.client()
        c.state['requests'][0].update(mode='getItemView',task_id='new:123')
        state=initial_state(cfg);state['listings']['123']={'attempts':1,'detail_status':'failed'}
        state['pending_ids']=['123']
        state['inflight']={'kind':'detail','pid':'123','task_id':'new:123','ledger_start':0,'failure_recorded':True}
        save(self.root/'discovery_checkpoint.json',state)
        run=DiscoveryRun(cfg,c,self.root);c.recover_uncertain(current=self.current);run.recover_inflight()
        self.assertEqual(run.state['listings']['123']['attempts'],1)
        self.assertNotIn('last_success_at',run.state['listings']['123'])
        self.assertEqual(run.state['pending_ids'],['123'])

    def test_restart_obeys_persisted_next_cycle_and_stop(self):
        cfg=fixture_config();fake=FakeQueueClient(cfg,self.root)
        run=DiscoveryRun(cfg,fake,self.root)
        run.state['next_cycle_at']=(self.current+timedelta(seconds=7200)).isoformat();run.checkpoint()
        resumed=DiscoveryRun(cfg,fake,self.root)
        waited=[]
        def stop(seconds,event):waited.append(seconds);event.set()
        result=queue_loop(resumed,'combined',watch=True,wait=stop)
        self.assertEqual(result['status'],'stopped');self.assertGreater(waited[0],7190)
        self.assertEqual(fake.calls,[])

    def test_watch_recovers_uncertainty_but_propagates_other_errors(self):
        run=Mock();run.stop=threading.Event();run.state={};run.root=self.root;run.cfg=fixture_config()
        run.client.state={'hold':'uncertain_request_no_auto_resend'}
        run.client.recover_uncertain.return_value=7200
        run.cycle.side_effect=SafeAPIError('network_error_request_outcome_uncertain')
        waits=[]
        def wait(seconds,event):waits.append(seconds);event.set()
        # Mock has arbitrary attributes; supply the actual wait implementation explicitly.
        run.wait=wait
        self.assertEqual(queue_loop(run,'combined',True)['status'],'stopped')
        self.assertEqual(waits,[7200])
        run.stop.clear();run.client.state['hold']='access_refused_or_redirect'
        with self.assertRaises(SafeAPIError):queue_loop(run,'combined',True)

    def test_sending_crash_replays_same_run_key_and_body(self):
        cfg=config();tx=Mock(return_value=(201,{'state':'applied'}))
        p=DeliveryPipeline(cfg,self.root,tx);p.stage(row())
        key,entry=next(iter(p.state['entries'].items()))
        entry.update(status='sending',attempts=1);p.save()
        before=copy.deepcopy(entry['body']);run=p.state['run_id']
        p=DeliveryPipeline(cfg,self.root,tx);p.flush();p.flush()
        self.assertEqual(tx.call_count,1)
        self.assertEqual(tx.call_args.args,('/internal/v2/crawl-runs/'+run+'/observations',before))
        self.assertEqual(p.state['entries'][key]['status'],'delivered')

    def test_delivery_retries_during_collection_sleep(self):
        cfg=config();current=[self.current]
        tx=Mock(side_effect=[(503,{}),(201,{'state':'applied'})])
        p=DeliveryPipeline(cfg,self.root,tx,clock=lambda:current[0]);p.stage(row());p.flush()
        worker=object.__new__(DeliveryDiscoveryRun);worker.delivery=p
        event=threading.Event();elapsed=[0]
        def advance(seconds):
            elapsed[0]+=seconds;current[0]+=timedelta(seconds=seconds)
            if tx.call_count==2:event.set()
        event.wait=advance
        with patch(PKG+'.domeggook_watch_delivery.time.monotonic',side_effect=lambda:elapsed[0]):
            worker.wait(7200,event)
        self.assertEqual(tx.call_count,2);self.assertLess(elapsed[0],60)

    def test_lock_prevents_second_worker_and_releases_on_crash(self):
        with self.assertRaises(RuntimeError):
            with FileState(self.root).lock():
                with self.assertRaises(OSError):
                    with FileState(self.root).lock():pass
                raise RuntimeError('SYNTHETIC crash')
        with FileState(self.root).lock():pass

    def test_backend_token_from_environment_is_required_and_not_persisted(self):
        cfg=config();cfg['backend_delivery']['base_url']='https://collector.example.test'
        with patch.dict('os.environ',{'KKULPICK_BACKEND_TOKEN':'SYNTHETIC_'+'x'*32}):
            p=DeliveryPipeline(cfg,self.root)
        self.addCleanup(p.close)
        self.assertEqual(p.transport.session.headers['Authorization'],'Bearer SYNTHETIC_'+'x'*32)
        self.assertNotIn('SYNTHETIC_',p.path.read_text())

    def test_delivery_shutdown_stops_before_next_POST(self):
        stop=threading.Event();tx=Mock(return_value=(201,{'state':'applied'}))
        p=DeliveryPipeline(config(),self.root,tx);p.stage(row());stop.set();p.flush(stop=stop)
        tx.assert_not_called();self.assertEqual(p.pending_count(),1)

    def test_recovered_page_still_stops_at_existing_task_attempt_cap(self):
        cfg=fixture_config();fake=FakeQueueClient(cfg,self.root)
        run=DiscoveryRun(cfg,fake,self.root)
        run.state['discovery']['failures'][run.page_key()]=cfg['discovery']['max_task_attempts']
        self.assertIsNone(run._page_task());self.assertEqual(fake.calls,[])

    def test_expired_required_grant_prunes_existing_live_payload(self):
        from ..domeggook_pipeline import normalize_detail
        from ..domeggook_options import option_offers
        from .fixtures import fixture
        cfg=config();cfg.update(price_semantics_confirmed=True)
        cfg['backend_delivery'].update(mode='live_authorized',allowed_product_hosts=['domeggook.com'])
        cfg['storage_grants']={f:{'storage':True,'reuse':True,'reference':'SYNTHETIC grant',
                                  'expires_at':(self.current+timedelta(hours=1)).isoformat()}
                               for f in ('product_name','unit_price','currency','availability','product_url')}
        listing,payload=fixture();offer=option_offers(normalize_detail(listing,payload,now()))[0][0]
        tx=Mock();p=DeliveryPipeline(cfg,self.root,tx,clock=lambda:self.current)
        self.assertEqual(p.stage(offer)['status'],'pending')
        cfg['storage_grants']['unit_price']['reuse']=False
        p.flush();tx.assert_not_called()
        self.assertEqual(p.report()['states']['revoked'],1)
        self.assertNotIn('body',next(iter(p.state['entries'].values())))

    def test_transient_HTTP_failure_defers_next_cycle_without_stopping_watch(self):
        run=Mock();run.stop=threading.Event();run.state={};run.root=self.root;run.cfg=fixture_config()
        run.cfg['cycle_interval_seconds']=7200  # Independent of the operator's local config.
        run.client.state={'hold':None};run.cycle.side_effect=SafeAPIError('HTTP_unsuccessful')
        waits=[]
        def wait(seconds,event):waits.append(seconds);event.set()
        run.wait=wait
        result=queue_loop(run,'combined',True)
        self.assertEqual(result['status'],'stopped');self.assertGreater(waits[0],7190)
        self.assertEqual(run.state['phase'],'cycle_complete')
