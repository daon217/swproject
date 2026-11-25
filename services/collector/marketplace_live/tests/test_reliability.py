import copy
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from ..config import validate,rights
from ..http import ProviderHTTP,ProviderError,Pause,retry_after
from ..delivery import Outbox
from ..runner import Worker
from ..normalize import yes24 as normalize_yes24
from ..__main__ import main
from .. import normalize
from .fixtures import config,yes24,shopping,response

class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.current=datetime.now(timezone.utc);self.cfg=config();self.session=Mock()
        self.session.request.return_value=response({'success':True,'data':{}})
    def tearDown(self):self.temp.cleanup()
    def http(self,cfg=None):
        h=ProviderHTTP(cfg or self.cfg,self.root,clock=lambda:self.current,session=self.session)
        h.cycle_id='SYNTHETIC_CYCLE';h.task_id='SYNTHETIC_TASK';return h

    def test_no_request_without_valid_grant_and_no_yes24_DB_permission_by_default(self):
        self.cfg['rights']['exception_agreement_reference']='';h=self.http()
        with self.assertRaisesRegex(ProviderError,'permission'):h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.session.request.assert_not_called();self.assertFalse(h.path.exists())

    def test_actual_reservation_keeps_interval_and_all_window_budgets(self):
        h=self.http();h.get_json('https://apis.yes24.com/v1/goods/itemList')
        with self.assertRaisesRegex(Pause,'interval'):h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.assertEqual(len(h.state['requests']),1)
        self.current+=timedelta(seconds=11);h.cfg['requests_per_hour']=1
        with self.assertRaisesRegex(Pause,'budget'):h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.assertEqual(self.session.request.call_count,1)
        self.assertFalse(self.session.request.call_args.kwargs['allow_redirects'])

    def test_network_uncertainty_survives_restart_and_conserves_debit(self):
        h=self.http();self.session.request.side_effect=requests.Timeout('SYNTHETIC secret')
        with self.assertRaisesRegex(Pause,'uncertain'):h.get_json('https://apis.yes24.com/v1/goods/itemList')
        h=self.http()
        with self.assertRaisesRegex(Pause,'deadline'):h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.assertEqual(len(h.state['requests']),1);self.assertEqual(self.session.request.call_count,1)
        self.assertNotIn('SYNTHETIC secret',h.path.read_text())
        self.current+=timedelta(seconds=7201);self.session.request.side_effect=None
        h.get_json('https://apis.yes24.com/v1/goods/itemList');self.assertEqual(len(h.state['requests']),2)

    def test_reserved_crash_defers_instead_of_resetting_ledger(self):
        h=self.http();h.reserve('GET','https://apis.yes24.com/v1/goods/itemList',{})
        h=self.http();self.assertEqual(h.state['requests'][0]['status'],'interrupted_uncertain')
        with self.assertRaises(Pause):h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.session.request.assert_not_called()

    def test_retry_after_numeric_date_and_long_deadline_not_capped(self):
        self.assertEqual((retry_after('9000',self.current)-self.current).total_seconds(),9000)
        date=(self.current+timedelta(hours=3)).strftime('%a, %d %b %Y %H:%M:%S GMT')
        self.assertGreater((retry_after(date,self.current)-self.current).total_seconds(),10798)
        h=self.http();self.session.request.return_value=response({},429,{'Retry-After':'9000'})
        with self.assertRaises(Pause) as exc:h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.assertEqual((exc.exception.until-self.current).total_seconds(),9000)
        with self.assertRaises(Pause):self.http().get_json('https://apis.yes24.com/v1/goods/itemList')
        self.assertEqual(self.session.request.call_count,1)

    def test_access_redirect_and_bad_JSON_remain_held(self):
        for status in (401,403,302):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as d:
                self.session.request.return_value=response({},status)
                h=ProviderHTTP(self.cfg,Path(d),session=self.session)
                with self.assertRaises(ProviderError):h.get_json('https://apis.yes24.com/v1/goods/itemList')
                self.assertIsNotNone(h.state['hold'])
        h=self.http();r=response();r.iter_content.return_value=[b'not JSON'];self.session.request.return_value=r
        with self.assertRaises(ProviderError):h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.assertEqual(h.state['hold'],'invalid_JSON_review_required')

    def test_SearchAPI_paid_budget_is_persistent_and_counts_failed_attempts(self):
        cfg=config('searchapi_google_shopping');cfg['max_units_per_month']=1
        h=self.http(cfg);self.session.request.return_value=response({},500)
        with self.assertRaises(Pause):h.get_json('https://www.searchapi.io/api/v1/search')
        self.current+=timedelta(seconds=61)
        with self.assertRaisesRegex(ProviderError,'budget'):self.http(cfg).get_json('https://www.searchapi.io/api/v1/search')
        self.assertEqual(self.session.request.call_count,1)
        self.assertEqual(h.state['requests'][0]['reserved_cost'],'0.001')

    def test_SearchAPI_cost_ceiling_and_disabled_cost_configuration(self):
        cfg=config('searchapi_google_shopping');cfg['max_cost_per_month']='0.0005'
        with self.assertRaisesRegex(ProviderError,'cost'):self.http(cfg).get_json('https://www.searchapi.io/api/v1/search')
        self.session.request.assert_not_called()
        cfg['cost_per_request']='0'
        with self.assertRaises(ValueError):validate(cfg)

    def test_source_and_task_state_isolation_and_missing_ledger_detection(self):
        d=Outbox(self.cfg,self.root/'yes24_api',Mock(),clock=lambda:self.current)
        w=Worker(self.cfg,self.root,delivery=d,clock=lambda:self.current)
        w.state['ledger_size']=2;w.save();w.state['ledger_size']=2
        # Simulate deletion of a ledger that a checkpoint already acknowledged.
        data=dict(w.state,ledger_size=2);w.path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'history'):Worker(self.cfg,self.root,delivery=d,clock=lambda:self.current)
        other=config('ebay_browse');o=Worker(other,self.root,clock=lambda:self.current)
        self.assertIsNone(o.state['hold']);self.assertNotEqual(o.path,w.path)

    def test_outbox_commit_response_lost_retries_identical_event(self):
        tx=Mock(side_effect=[(0,{}),(201,{'state':'applied','change_kind':'created'})])
        d=Outbox(self.cfg,self.root,tx,clock=lambda:self.current)
        r=normalize_yes24(yes24(),self.current.isoformat(),self.cfg);d.stage(r);d.stage(r);d.flush()
        first=copy.deepcopy(tx.call_args.args)
        d=Outbox(self.cfg,self.root,tx,clock=lambda:self.current);d.flush();self.assertEqual(tx.call_count,1)
        self.current+=timedelta(seconds=6);d.flush();d.stage(r);d.flush()
        self.assertEqual(tx.call_count,2);self.assertEqual(tx.call_args.args,first)
        self.assertEqual(d.report()['states']['delivered'],1)

    def test_outbox_sending_crash_auth_hold_exhaustion_and_expiry(self):
        tx=Mock(return_value=(403,{}));d=Outbox(self.cfg,self.root,tx,clock=lambda:self.current)
        d.stage(normalize_yes24(yes24(),self.current.isoformat(),self.cfg))
        entry=next(iter(d.state['entries'].values()));entry.update(status='sending',attempts=1);d.save()
        d=Outbox(self.cfg,self.root,tx,clock=lambda:self.current);d.flush();d.flush()
        self.assertEqual(tx.call_count,1);self.assertTrue(d.state['hold'])
        self.current+=timedelta(days=2);d.flush();self.assertNotIn('body',next(iter(d.state['entries'].values())))

    def test_outbox_five_attempt_cap_and_payload_survives_exhaustion(self):
        tx=Mock(return_value=(503,{}));d=Outbox(self.cfg,self.root,tx,clock=lambda:self.current);d.settings['max_recovery_rounds']=0
        d.stage(normalize_yes24(yes24(),self.current.isoformat(),self.cfg))
        for _ in range(8):d.flush();self.current+=timedelta(minutes=10)
        self.assertEqual(tx.call_count,5);self.assertEqual(d.report()['states']['exhausted'],1)
        self.assertIn('body',next(iter(d.state['entries'].values())))

    def test_context_changes_cannot_reset_independent_state(self):
        w=Worker(self.cfg,self.root,clock=lambda:self.current);w.save()
        cfg=copy.deepcopy(self.cfg);cfg['queries']=['OTHER QUERY']
        with self.assertRaisesRegex(ValueError,'context'):Worker(cfg,self.root,clock=lambda:self.current)

    def test_worker_search_detail_API_delivery_and_two_hour_restart_schedule(self):
        tx=Mock(return_value=(201,{'state':'applied'}));d=Outbox(self.cfg,self.root/'yes24_api',tx,clock=lambda:self.current)
        adapter=Mock();adapter.search.return_value=([yes24(),yes24()],False);adapter.detail.return_value=yes24()
        adapter.normalize.side_effect=lambda row,at:normalize_yes24(row,at,self.cfg)
        w=Worker(self.cfg,self.root,delivery=d,adapter=adapter,clock=lambda:self.current)
        w.step();self.assertEqual(len(w.state['tasks']),1);w.step()
        self.assertEqual(tx.call_count,1);self.assertEqual(w.state['totals']['cycles_completed'],1)
        w=Worker(self.cfg,self.root,delivery=d,adapter=adapter,clock=lambda:self.current);w.step()
        self.assertEqual(adapter.search.call_count,1)
        self.current+=timedelta(seconds=7201);w.step();self.assertEqual(adapter.search.call_count,2)

    def test_worker_uncertain_recovery_keeps_task_until_deadline_and_attempt_cap(self):
        adapter=Mock();adapter.search.side_effect=Pause('network_error_request_outcome_uncertain',self.current+timedelta(seconds=7200))
        d=Outbox(self.cfg,self.root/'yes24_api',Mock(),clock=lambda:self.current)
        w=Worker(self.cfg,self.root,delivery=d,adapter=adapter,clock=lambda:self.current)
        for _ in range(3):w.step();self.current+=timedelta(seconds=7201)
        w.step();self.assertEqual(adapter.search.call_count,3)
        self.assertEqual(w.state['totals']['tasks_exhausted'],1)

    def test_partial_official_shopping_results_are_not_sent_to_DB(self):
        cfg=config('searchapi_google_shopping');tx=Mock();d=Outbox(cfg,self.root/cfg['source'],tx,clock=lambda:self.current)
        adapter=Mock();adapter.search.return_value=([shopping(False)],False)
        adapter.normalize.side_effect=lambda row,at:normalize.shopping(row,at,cfg)
        w=Worker(cfg,self.root,delivery=d,adapter=adapter,clock=lambda:self.current);w.step()
        tx.assert_not_called();self.assertEqual(w.state['totals']['missing_currency'],1)

    def test_readonly_status_never_reads_credentials_or_writes_state(self):
        p=self.root/'config.json';p.write_text(json.dumps({'sources':[self.cfg]}),encoding='utf-8')
        state=self.root/'nonexistent'
        with patch(__package__.rsplit('.tests',1)[0]+'.adapters.credential',side_effect=AssertionError('credential read')):
            self.assertEqual(main(['--config',str(p),'--state-dir',str(state),'--status']),0)
        self.assertFalse(state.exists())

    def test_provider_route_injection_never_leaks_authentication(self):
        h=self.http()
        for url in ('http://apis.yes24.com/v1/goods/itemList','https://evil.example/v1/goods/itemList',
                    'https://apis.yes24.com/v1/goods/itemList?api_key=secret'):
            with self.assertRaises(ValueError):h.get_json(url,headers={'X-Api-Key':'SYNTHETIC'})
        self.session.request.assert_not_called()

    def test_backend_retry_after_deadline_survives_outbox_restart(self):
        tx=Mock(return_value=(429,{}));tx.retry_not_before=self.current+timedelta(hours=3)
        d=Outbox(self.cfg,self.root,tx,clock=lambda:self.current)
        d.stage(normalize_yes24(yes24(),self.current.isoformat(),self.cfg));d.flush()
        self.current+=timedelta(seconds=301)
        d=Outbox(self.cfg,self.root,tx,clock=lambda:self.current);d.flush()
        self.assertEqual(tx.call_count,1)
        self.current+=timedelta(hours=3);tx.retry_not_before=None;tx.return_value=(201,{'state':'applied'})
        d.flush();self.assertEqual(tx.call_count,2)

    def test_inflight_task_crash_defers_without_losing_native_ID(self):
        d=Outbox(self.cfg,self.root/'yes24_api',Mock(),clock=lambda:self.current)
        w=Worker(self.cfg,self.root,delivery=d,clock=lambda:self.current)
        w.state['tasks']=[w.task('detail',identity='12345678')];w.state['inflight']=True;w.save()
        w=Worker(self.cfg,self.root,delivery=d,clock=lambda:self.current)
        self.assertEqual(w.state['tasks'][0]['identity'],'12345678')
        self.assertEqual(w.state['tasks'][0]['attempts'],1)
        self.assertGreater((datetime.fromisoformat(w.state['next_action_at'])-self.current).total_seconds(),7199)

    def test_stop_and_backpressure_prevent_new_provider_calls(self):
        tx=Mock(return_value=(503,{}));self.cfg['backend_delivery']['max_pending']=1
        d=Outbox(self.cfg,self.root/'yes24_api',tx,clock=lambda:self.current)
        d.stage(normalize_yes24(yes24(),self.current.isoformat(),self.cfg));adapter=Mock()
        w=Worker(self.cfg,self.root,delivery=d,adapter=adapter,clock=lambda:self.current)
        w.step();adapter.search.assert_not_called()
        w.stop.set();w.step();self.assertEqual(tx.call_count,1)

    def test_duplicate_ID_on_later_page_does_not_schedule_new_detail(self):
        self.cfg['max_pages_per_cycle']=2
        tx=Mock(return_value=(201,{'state':'applied'}));d=Outbox(self.cfg,self.root/'yes24_api',tx,clock=lambda:self.current)
        adapter=Mock();adapter.search.return_value=([yes24()],True);adapter.detail.return_value=yes24()
        adapter.normalize.side_effect=lambda row,at:normalize_yes24(row,at,self.cfg)
        w=Worker(self.cfg,self.root,delivery=d,adapter=adapter,clock=lambda:self.current)
        w.step();w.step();w.step()
        self.assertEqual(adapter.detail.call_count,1);self.assertEqual(adapter.search.call_count,2)
        self.assertEqual(w.state['totals']['duplicate_search_IDs'],1)

    def test_same_source_lock_and_other_source_independent_lock(self):
        from services.collector.domeggook_live.runtime import FileState
        with FileState(self.root/'yes24_api').lock():
            with self.assertRaises(OSError):
                with FileState(self.root/'yes24_api').lock():pass
            with FileState(self.root/'ebay_browse').lock():pass

    def test_cycle_and_rolling_day_caps_survive_restart_without_reset(self):
        self.cfg['requests_per_cycle']=1
        h=self.http();h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.current+=timedelta(seconds=11)
        with self.assertRaisesRegex(Pause,'cycle_budget'):self.http().get_json('https://apis.yes24.com/v1/goods/itemList')
        self.cfg['requests_per_24h']=1;h=self.http();h.cycle_id='NEXT_CYCLE'
        with self.assertRaisesRegex(Pause,'provider_budget'):h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.assertEqual(len(h.state['requests']),1);self.assertEqual(self.session.request.call_count,1)

    def test_failed_source_initialization_does_not_block_another_source(self):
        cfg2=config('ebay_browse');p=self.root/'config.json'
        p.write_text(json.dumps({'sources':[self.cfg,cfg2]}),encoding='utf-8')
        good=Mock();good.state={'hold':None};good.http.state={'hold':None};good.delivery.state={'hold':None}
        good.report.return_value={'source':'ebay_browse','status':'SYNTHETIC passed'}
        module=__package__.rsplit('.tests',1)[0]+'.__main__.Worker'
        with patch(module,side_effect=[ValueError('SYNTHETIC source failure'),good]):
            result=main(['--config',str(p),'--state-dir',str(self.root/'state'),'--once'])
        self.assertEqual(result,1);good.step.assert_called_once();good.close.assert_called_once()

    def test_oversized_provider_response_never_persists_raw_payload(self):
        h=self.http();r=response();r.iter_content.return_value=[b'x'*4_000_001]
        self.session.request.return_value=r
        with self.assertRaisesRegex(ProviderError,'too_large'):h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.assertLess(h.path.stat().st_size,2000);r.close.assert_called_once()

    def test_shutdown_blocks_next_provider_or_OAuth_reservation(self):
        h=self.http();h.stop=threading.Event();h.stop.set()
        with self.assertRaisesRegex(Pause,'worker_stopping'):h.get_json('https://apis.yes24.com/v1/goods/itemList')
        self.assertEqual(h.state['requests'],[]);self.session.request.assert_not_called()
