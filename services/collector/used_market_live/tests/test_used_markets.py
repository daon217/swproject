import copy
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import requests

from services.collector.marketplace_live.adapters import Adapter, EBAY
from services.collector.marketplace_live.delivery import Outbox
from services.collector.marketplace_live.http import ProviderHTTP, ProviderError, Pause
from services.collector.marketplace_live.runner import Worker
from services.collector.marketplace_live.synthetic import SyntheticHTTP
from services.collector.marketplace_live.tests.fixtures import config, ebay, response
from services.collector.domeggook_live.domeggook_delivery import atomic
from services.collector.domeggook_live.runtime import FileState
from ..__main__ import main
from ..domestic import blocked, fixtures, normalize_synthetic, bunjang_catalog_mock
from ..ebay_used import UsedAdapter, FILTER, open_worker, used_config, status
from ..mock import run_mock


class UsedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.cfg=config('ebay_browse');self.cfg['collection_profile']='ebay_used'
        self.at=datetime.now(timezone.utc)
    def tearDown(self):self.tmp.cleanup()
    def row(self):
        row=ebay();row.update(conditionId='3000',condition='Used');return row
    def test_official_used_filter_added_without_changing_general_adapter(self):
        h=Mock();h.state={'requests':[]};h.task_id='SYNTHETIC';h.get_json.return_value={'itemSummaries':[],'total':0}
        for cls, expected in [(UsedAdapter,FILTER),(Adapter,'buyingOptions:{FIXED_PRICE}')]:
            a=cls(self.cfg,h);a.oauth=Mock();a.oauth._get_access_token.return_value='SYNTHETIC'
            a.search('mechanical keyboard',1)
            self.assertEqual(h.get_json.call_args.kwargs['params']['filter'],expected)
            self.assertEqual(h.get_json.call_args.kwargs['params']['limit'],3)
        self.assertIn('conditions:{USED}',FILTER)
        self.assertNotIn('2500',FILTER)
    def test_detail_rechecks_used_scope_even_if_search_filter_was_ignored(self):
        a=UsedAdapter(self.cfg,Mock())
        for identity,label in [('1000','New'),('1500','Open box'),('2000','Certified Refurbished'),('7000','For parts or not working')]:
            with self.subTest(identity=identity):
                row=self.row();row.update(conditionId=identity,condition=label)
                result=a.normalize(row,self.at.isoformat())
                self.assertIsNone(result['observation'])
                self.assertIn('used_condition_required',result['missing_fields'])
    def test_used_v2_identity_and_idempotency_match_existing_ebay(self):
        row=self.row();at=self.at.isoformat()
        actual=UsedAdapter(self.cfg,Mock()).normalize(row,at)
        original=Adapter(self.cfg,Mock()).normalize(row,at)
        self.assertEqual(actual['observation'],original['observation'])
        self.assertEqual(actual['observation']['source'],'ebay_browse')
        self.assertEqual(actual['observation']['variant_key'],'v1|123456789|0')
        queue=Outbox(self.cfg,self.root,transport=Mock())
        self.assertEqual(queue.stage(actual)['status'],'pending')
        self.assertTrue(queue.stage(original)['duplicate'])
        self.assertEqual(queue.pending_count(),1)
    def test_unknown_quantity_is_not_fabricated_and_sold_end_date_is_ended(self):
        row=self.row();row['estimatedAvailabilities']=[{'estimatedAvailabilityStatus':'LIMITED_STOCK'}]
        result=UsedAdapter(self.cfg,Mock()).normalize(row,self.at.isoformat())
        self.assertIsNone(result['stock_quantity']);self.assertEqual(result['availability'],'available')
        row['itemEndDate']=(self.at-timedelta(seconds=1)).isoformat()
        self.assertEqual(UsedAdapter(self.cfg,Mock()).normalize(row,self.at.isoformat())['availability'],'ended')
    def test_missing_stock_and_seller_not_assumed(self):
        row=self.row();row.pop('estimatedAvailabilities');row.pop('seller')
        result=UsedAdapter(self.cfg,Mock()).normalize(row,self.at.isoformat())
        self.assertIsNone(result['observation']);self.assertIsNone(result['seller'])
        self.assertIsNone(result['stock_quantity'])
    def test_shared_ledger_preserves_general_ebay_debits(self):
        self.cfg.update(requests_per_hour=1,backend_enabled=False)
        h=ProviderHTTP(self.cfg,self.root/'ebay_browse',session=Mock())
        h.cycle_id='GENERAL';h.task_id='GENERAL'
        entry=h.reserve('GET',EBAY+'item_summary/search',{})
        entry['status']=200;entry['at']=(self.at-timedelta(seconds=20)).isoformat();h.save();h.close()
        before=(self.root/'ebay_browse/request_ledger.json').read_bytes()
        with open_worker(self.cfg,self.root) as w:
            self.assertEqual(len(w.http.state['requests']),1)
            with self.assertRaisesRegex(Pause,'budget'):
                w.http.reserve('GET',EBAY+'item_summary/search',{})
            self.assertEqual(w.path,self.root/'ebay_used/ebay_browse/checkpoint.json')
            self.assertEqual(w.http.path,self.root/'ebay_browse/request_ledger.json')
        self.assertEqual((self.root/'ebay_browse/request_ledger.json').read_bytes(),before)
    def test_general_writer_lock_excludes_used_without_affecting_yes24_lock(self):
        with FileState(self.root/'ebay_browse/lock').lock():
            with self.assertRaises(OSError):
                with open_worker(self.cfg,self.root):pass
            with FileState(self.root/'yes24_api/lock').lock():pass
    def test_missing_general_history_or_wrong_profile_fails_closed(self):
        atomic(self.root/'ebay_browse/checkpoint.json',{'ledger_size':2})
        with self.assertRaisesRegex(ValueError,'history'):
            with open_worker(self.cfg,self.root):pass
        wrong=copy.deepcopy(self.cfg);wrong.pop('collection_profile')
        with self.assertRaises(ValueError):used_config(wrong)
    def test_permission_and_price_guards_still_prevent_queue(self):
        result=UsedAdapter(self.cfg,Mock()).normalize(self.row(),self.at.isoformat())
        for field in ('price_semantics_confirmed','backend_owner_approved','backend_enabled'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as directory:
                cfg=copy.deepcopy(self.cfg);cfg[field]=False
                queue=Outbox(cfg,Path(directory),transport=Mock())
                self.assertEqual(queue.stage(result)['status'],'permission_blocked')
        cfg=copy.deepcopy(self.cfg);cfg['rights']['allowed_uses']=['lookup','systematic_collection']
        queue=Outbox(cfg,self.root/'revoked',transport=Mock())
        self.assertEqual(queue.stage(result)['status'],'permission_blocked')
    def test_worker_reuses_tasks_metrics_and_7200_second_schedule(self):
        http=SyntheticHTTP('ebay_browse')
        for row in http.rows:row.update(conditionId='3000',condition='Used')
        delivery=Mock();delivery.path=self.root/'unused';delivery.backpressure.return_value=False
        delivery.stage.return_value={'status':'pending'};delivery.report.return_value={}
        worker=Worker(self.cfg,self.root/'ebay_used',http=http,adapter=UsedAdapter(self.cfg,http,lambda _: 'SYNTHETIC'),delivery=delivery,clock=lambda:self.at)
        worker.step()
        self.assertEqual(len(worker.state['tasks']),3)
        resumed=Worker(self.cfg,self.root/'ebay_used',http=http,adapter=worker.adapter,delivery=delivery,clock=lambda:self.at)
        for _ in range(3):resumed.step()
        report=resumed.report()
        self.assertEqual((report['products_success'],report['products_held']),(2,1))
        self.assertEqual(report['last_collection_at'],self.at.isoformat())
        self.assertEqual(report['last_success_at'],self.at.isoformat())
        self.assertEqual(datetime.fromisoformat(report['next_cycle_at'])-self.at,timedelta(seconds=7200))
        actions=len(http.state['requests']);resumed.step()
        self.assertEqual(len(http.state['requests']),actions)
    def test_provider_failure_isolated_from_other_provider_worker(self):
        def delivery():
            d=Mock();d.path=self.root/'absent';d.backpressure.return_value=False;d.report.return_value={};return d
        broken=Mock();broken.search.side_effect=ProviderError('provider_access_refused',403)
        failed=Worker(self.cfg,self.root,http=Mock(state={'requests':[]}),adapter=broken,delivery=delivery())
        cfg=config('yes24_api');healthy=Mock();healthy.search.return_value=([],False)
        good=Worker(cfg,self.root,http=Mock(state={'requests':[]}),adapter=healthy,delivery=delivery())
        failed.step();good.step()
        self.assertEqual(failed.state['hold'],'provider_access_refused')
        self.assertIsNone(good.state['hold']);self.assertEqual(good.state['totals']['cycles_completed'],1)
    def test_uncertain_shared_request_survives_restart_and_other_source_unblocked(self):
        session=Mock();session.request.side_effect=requests.Timeout('SYNTHETIC_SECRET')
        h=ProviderHTTP(self.cfg,self.root/'ebay_browse',session=session)
        with self.assertRaises(Pause):h.get_json(EBAY+'item_summary/search')
        with open_worker(self.cfg,self.root) as worker:
            with self.assertRaisesRegex(Pause,'deadline'):
                worker.http.get_json(EBAY+'item_summary/search')
        self.assertEqual(session.request.call_count,1)
        self.assertNotIn('SYNTHETIC_SECRET',(self.root/'ebay_browse/request_ledger.json').read_text())
        self.assertEqual(status(self.root)['HTTP_attempts_shared_with_general_ebay'],1)
    def test_mock_uses_synthetic_non_sendable_queue(self):
        result=run_mock('ebay_used',self.root)
        self.assertEqual((result['success'],result['held'],result['failed']),(2,1,0))
        self.assertEqual(result['queue_pending'],2)
        self.assertEqual(result['provider_HTTP_attempts'],0)
        with self.assertRaisesRegex(ValueError,'synthetic'):
            Outbox(self.cfg,self.root/'mock-only/ebay_used',transport=Mock())
    def test_status_neither_reads_credentials_nor_creates_state(self):
        empty=self.root/'absent'
        with patch('requests.sessions.Session.request',side_effect=AssertionError('network')),patch.dict(main.__globals__, {'load_ebay_env':Mock(side_effect=AssertionError('keys'))}):
            with redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(main(['--provider','ebay_used','--status','--state-dir',str(empty),'--env-file','ignored']),0)
        self.assertFalse(empty.exists())
        result=json.loads(stream.getvalue());self.assertEqual(result['products_success'],0)

    def test_collection_plan_reports_worker_retry_budgets_not_lookup_five_call_cap(self):
        cfgfile=self.root/'profile.json';cfgfile.write_text(json.dumps({'sources':[self.cfg]}))
        with patch.dict('os.environ',{'EBAY_CLIENT_ID':'SYNTHETIC','EBAY_CLIENT_SECRET':'SYNTHETIC'}),patch('requests.sessions.Session.request',side_effect=AssertionError('network')):
            with redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(main(['--provider','ebay_used','--plan','--config',str(cfgfile)]),0)
        result=json.loads(stream.getvalue())
        self.assertEqual(result['mode'],'collection_plan')
        self.assertEqual(result['HTTP_attempts_per_cycle'],self.cfg['requests_per_cycle'])
        self.assertEqual(result['max_task_attempts'],3)
        self.assertTrue(result['OAuth_and_retries_included_in_budget'])
        self.assertNotIn('planned_HTTP_requests_max',result)
        self.assertNotIn('retries',result)


class DomesticTests(unittest.TestCase):
    def test_normalization_and_authoritative_lifecycle_rules(self):
        for provider in ('bunjang','joongna'):
            with self.subTest(provider=provider):
                rows=list(fixtures(provider))
                results=[normalize_synthetic(provider,row) for row in rows]
                self.assertEqual([r['availability'] for r in results],['available','ended','ended','ended',None,None])
                self.assertTrue(all(r['stock_quantity'] is None for r in results))
                self.assertTrue(all(r['observation'] is None for r in results))
                self.assertEqual(results[0]['price'],'12000')
                self.assertEqual(results[0]['sale_status'],'active')
    def test_no_implicit_currency_seller_or_unknown_condition(self):
        row=next(fixtures('bunjang'));row.pop('currency');row.pop('seller');row['condition']='almost new'
        result=normalize_synthetic('bunjang',row)
        self.assertEqual(set(result['missing_fields']),{'currency','seller','condition','approved_currency'})
        self.assertFalse(result['draft_ready'])
    def test_live_input_unknown_provider_and_unapproved_URL_rejected(self):
        row=next(fixtures('joongna'));row.pop('synthetic_only')
        with self.assertRaises(ValueError):normalize_synthetic('joongna',row)
        with self.assertRaises(ValueError):blocked('unknown')
        row['synthetic_only']=True;row['url']='https://evil.example/item'
        with self.assertRaises(ValueError):normalize_synthetic('joongna',row)
    def test_native_bunjang_catalog_mock_keeps_undocumented_fields_missing(self):
        row={'synthetic_only':True,'pid':990001,'name':'SYNTHETIC catalog item','price':12000,
             'condition':'LIKE_NEW','saleStatus':'SELLING','uid':999,'quantity':2}
        result=bunjang_catalog_mock(row)
        self.assertEqual(result['provider_seller_id'],999)
        self.assertEqual(result['condition'],'used')
        self.assertIsNone(result['stock_quantity'])
        self.assertEqual(set(result['missing_fields']),{'currency','seller','url','approved_currency'})
        row['condition']='DAMAGED';row['saleStatus']='DELETED'
        self.assertEqual(bunjang_catalog_mock(row)['availability'],'ended')
        self.assertEqual(bunjang_catalog_mock(row)['condition'],'damaged')
    def test_native_quantity_conflicts_do_not_create_available_draft(self):
        row={'synthetic_only':True,'pid':990001,'name':'SYNTHETIC','price':1,'condition':'USED','saleStatus':'SELLING','quantity':0}
        result=bunjang_catalog_mock(row)
        self.assertIn('quantity_status_review',result['missing_fields']);self.assertFalse(result['draft_ready'])
    def test_live_and_watch_blocked_even_with_fake_env_keys_and_config(self):
        for provider in ('bunjang','joongna'):
            for mode in ('--once','--watch'):
                with self.subTest(provider=provider,mode=mode),patch('requests.sessions.Session.request',side_effect=AssertionError('network')):
                    with redirect_stdout(io.StringIO()) as stream:
                        self.assertEqual(main(['--provider',provider,mode,'--config','untrusted','--env-file','untrusted']),2)
                    result=json.loads(stream.getvalue())
                    self.assertFalse(result['live_supported']);self.assertEqual(result['backend_requests'],0)
    def test_domestic_mock_metrics_are_isolated_and_truthful(self):
        with tempfile.TemporaryDirectory() as directory:
            a=run_mock('bunjang',directory);b=run_mock('joongna',directory)
            for result in (a,b):
                self.assertEqual((result['draft_ready'],result['products_held'],result['products_success']),(4,6,0))
                self.assertIsNotNone(result['last_collection_at'])
                self.assertIsNone(result['last_success_at'])
            self.assertTrue((Path(directory)/'mock-only/bunjang/last_mock_summary.json').exists())
            self.assertTrue((Path(directory)/'mock-only/joongna/last_mock_summary.json').exists())

    def test_bad_mock_row_does_not_stop_later_rows_or_other_provider(self):
        row=next(fixtures('bunjang'));bad={**row,'price':'NaN'}
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(run_mock.__globals__, {'fixtures':lambda _: [bad,row,row]}):
                result=run_mock('bunjang',directory)
            other=run_mock('joongna',directory)
        self.assertEqual((result['products_failed'],result['products_held'],result['duplicate_ids_ignored']),(1,1,1))
        self.assertIsNotNone(result['last_failure_at'])
        self.assertEqual(other['products_failed'],0)


class DeploymentTests(unittest.TestCase):
    def test_docker_mock_is_offline_and_live_defaults_to_status(self):
        root=Path(__file__).parents[1]/'deploy'
        mocked=json.loads((root/'compose.mock.yaml').read_text())
        for service in mocked['services'].values():
            self.assertEqual(service['network_mode'],'none')
            self.assertNotIn('env_file',service);self.assertIn('--mock',service['command'])
        live=json.loads((root/'compose.ebay.yaml').read_text())['services']['ebay-used']
        self.assertIn('--status',live['command']);self.assertNotIn('--watch',live['command'])
        self.assertTrue(live['read_only']);self.assertEqual(live['cap_drop'],['ALL'])
        self.assertIn('existing shared state root',live['volumes'][0])
    def test_image_copies_only_code_and_uses_nonroot(self):
        root=Path(__file__).parents[1]/'deploy'
        image=(root/'Dockerfile').read_text()
        self.assertIn('USER 10001:10001',image)
        self.assertNotIn('COPY . ',image)
        self.assertNotIn('.env',image)
        self.assertTrue((root/'Dockerfile.dockerignore').read_text().startswith('**\n'))
