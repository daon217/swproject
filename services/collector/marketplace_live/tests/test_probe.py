import contextlib
import copy
from datetime import datetime,timezone,timedelta
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
import requests
from ..adapters import Adapter
from ..config import load_config
from ..delivery import Outbox
from ..http import ProviderHTTP,ProviderError,Pause
from ..probe import LookupHTTP,bounded_lookup,inspect_item,main,plan
from ..synthetic import fixture_config,fixture_rows,run_mock,SyntheticHTTP,MockOutbox
from ..delivery_probe import main as delivery_main,check_payloads
from ..runner import Worker
from .fixtures import response

PKG=__package__.rsplit('.tests',1)[0]

class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.cfg=fixture_config('yes24_api');self.cfg['rights']['allowed_uses']=['lookup']
        self.cfg['rights']['exception_agreement_reference']=''
        self.cfg.update(enabled=False,backend_enabled=False,backend_owner_approved=False,price_semantics_confirmed=False)
    def tearDown(self):self.temp.cleanup()

    def test_mock_all_sources_without_credentials_reaches_non_sendable_queue(self):
        with patch.dict(os.environ,{},clear=True),patch('requests.sessions.Session.request',side_effect=AssertionError('network forbidden')):
            for source in ('yes24_api','searchapi_google_shopping','ebay_browse'):
                r=run_mock(source,self.root)
                self.assertEqual((r['success'],r['failed'],r['held'],r['queue_pending']),(2,0,1,2))
                self.assertEqual(r['provider_HTTP_attempts'],0);self.assertEqual(r['backend_HTTP_requests'],0)
                self.assertTrue(r['synthetic_only']);self.assertIsNotNone(r['last_collection_at'])
                cfg=fixture_config(source)
                with self.assertRaisesRegex(ValueError,'synthetic_outbox'):
                    Outbox(cfg,self.root/'mock-only'/source)
                queue=MockOutbox(cfg,self.root/'mock-only'/source)
                with self.assertRaisesRegex(ValueError,'cannot_send_HTTP'):queue.flush()

    def test_mock_limit_1_2_3_and_invalid_limit(self):
        for n in (1,2,3):
            with tempfile.TemporaryDirectory() as d:
                result=run_mock('yes24_api',d,n)
                self.assertLessEqual(result['selected_count'],n);self.assertLessEqual(result['queue_pending'],n)
        with self.assertRaises(ValueError):bounded_lookup(Mock(),self.cfg,4)

    def test_lookup_grant_does_not_weaken_normal_collection_permission(self):
        cfg=copy.deepcopy(self.cfg);cfg['enabled']=True;session=Mock()
        normal=ProviderHTTP(cfg,self.root/'normal',session=session)
        with self.assertRaises(ProviderError):normal.get_json('https://apis.yes24.com/v1/goods/itemList')
        session.request.assert_not_called()
        lookup=LookupHTTP(cfg,self.root/'lookup',session=session)
        self.assertTrue(lookup.permitted())

    def test_live_yes24_only_mocked_HTTP_never_outbox_or_raw_persistence(self):
        profile=self.root/'profile.json';profile.write_text(json.dumps({'sources':[self.cfg]}),encoding='utf-8')
        current=[datetime.now(timezone.utc)]
        rows=fixture_rows('yes24_api')
        rows[0]['title']='PRIVATE PRODUCT NAME';rows[0]['seller']='PRIVATE SELLER'
        session=Mock()
        session.request.side_effect=[response({'success':True,'data':{'items':rows,'currentPage':1}})]+[
            response({'success':True,'data':{'items':[r]}}) for r in rows]
        def build(cfg,root):return LookupHTTP(cfg,root,session=session,clock=lambda:current[0])
        def advance(seconds):current[0]+=timedelta(seconds=seconds+0.01)
        output=io.StringIO()
        with (patch.dict(os.environ,{'YES24_API_KEY':'SYNTHETIC_API_SECRET'}),
              patch(PKG+'.probe.LookupHTTP',side_effect=build),
              patch(PKG+'.probe.time.sleep',side_effect=advance),
              patch(PKG+'.delivery.Outbox.__init__',side_effect=AssertionError('no outbox')),
              contextlib.redirect_stdout(output)):
            rc=main(['--source','yes24_api','--live','--config',str(profile),'--state-dir',str(self.root/'state')])
        result=json.loads(output.getvalue());self.assertEqual(rc,1)
        self.assertEqual(session.request.call_count,4);self.assertEqual((result['success'],result['held']),(2,1))
        self.assertEqual(result['backend_HTTP_requests'],0)
        for p in (self.root/'state').rglob('*.json'):
            text=p.read_text(encoding='utf-8')
            for secret in ('PRIVATE PRODUCT NAME','PRIVATE SELLER','SYNTHETIC_API_SECRET'):
                self.assertNotIn(secret,text)
        self.assertFalse(list((self.root/'state').rglob('backend_outbox.json')))

    def test_SearchAPI_only_first_three_rows_inspected_and_one_search(self):
        class Poison(dict):
            def get(self,*args):raise AssertionError('unselected item inspected')
        cfg=fixture_config('searchapi_google_shopping');http=SyntheticHTTP(cfg['source'])
        adapter=Adapter(cfg,http,credential_reader=lambda _: 'SYNTHETIC')
        normal_search=adapter.search
        def search(*args):
            rows,more=normal_search(*args);return rows+[Poison() for _ in range(57)],True
        adapter.search=Mock(side_effect=search)
        r=bounded_lookup(adapter,cfg,3)
        self.assertEqual(r['returned_count'],60);self.assertEqual(r['ignored_count'],57)
        self.assertEqual(adapter.search.call_count,1);self.assertEqual(len(http.state['requests']),1)

    def test_ebay_OAuth_and_three_details_without_keys(self):
        cfg=fixture_config('ebay_browse');http=SyntheticHTTP(cfg['source'])
        adapter=Adapter(cfg,http,credential_reader=lambda _: 'SYNTHETIC')
        r=bounded_lookup(adapter,cfg)
        self.assertEqual(len(http.state['requests']),5);self.assertEqual((r['success'],r['held']),(2,1))
        self.assertIn('missing_availability',r['hold_reasons'])

    def test_probe_network_failure_is_not_retried(self):
        cfg=copy.deepcopy(self.cfg);cfg['enabled']=True
        session=Mock();session.request.side_effect=requests.Timeout('SYNTHETIC_API_SECRET')
        http=LookupHTTP(cfg,self.root,session=session)
        adapter=Adapter(cfg,http,credential_reader=lambda _: 'SYNTHETIC')
        r=bounded_lookup(adapter,cfg)
        self.assertEqual(session.request.call_count,1);self.assertEqual(r['status'],'deferred')
        self.assertEqual(len(http.state['requests']),1);self.assertNotIn('SYNTHETIC_API_SECRET',json.dumps(r))

    def test_detail_refusal_stops_remaining_products(self):
        adapter=Mock();adapter.search.return_value=(fixture_rows('yes24_api'),False)
        adapter.detail.side_effect=ProviderError('provider_access_refused',403)
        r=bounded_lookup(adapter,self.cfg)
        self.assertEqual((r['failed'],r['held']),(1,2));adapter.detail.assert_called_once()

    def test_missing_seller_held_even_if_v2_body_is_otherwise_complete(self):
        cfg=fixture_config('yes24_api');row=fixture_rows(cfg['source'])[0];row.pop('seller')
        adapter=Adapter(cfg,SyntheticHTTP(cfg['source']))
        result,_=inspect_item(adapter,row)
        self.assertEqual(result['status'],'held');self.assertIn('missing_seller',result['reasons'])

    def test_plan_is_readonly_and_missing_keys_blocks_before_session(self):
        cfg=copy.deepcopy(self.cfg)
        with patch.dict(os.environ,{},clear=True),patch('requests.Session',side_effect=AssertionError('no session')):
            r=plan(cfg,3)
        self.assertFalse(r['ready']);self.assertEqual(r['provider_HTTP_requests'],0)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_yes24_DB_probe_is_always_blocked_before_config_or_token(self):
        with patch(PKG+'.delivery_probe.load_config',side_effect=AssertionError('should not load')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(delivery_main(['--source','yes24_api','--live']),2)

    def test_DB_probe_rejects_incomplete_or_wrong_source_before_POST(self):
        cfg=fixture_config('ebay_browse');adapter=Adapter(cfg,SyntheticHTTP(cfg['source']))
        body=adapter.normalize(fixture_rows(cfg['source'])[0],datetime.now(timezone.utc).isoformat())['observation']
        self.assertEqual(check_payloads([{'observation':body,'seller':'SYNTHETIC merchant'}],cfg),[body])
        with self.assertRaises(ValueError):check_payloads([body],cfg)
        with self.assertRaises(ValueError):check_payloads([{'observation':body}],cfg)
        for field in ('price','currency','condition','availability','url','source_listing_id','variant_key'):
            bad=copy.deepcopy(body);bad.pop(field)
            with self.assertRaises(ValueError):check_payloads([{'observation':bad,'seller':'SYNTHETIC merchant'}],cfg)
        bad=copy.deepcopy(body);bad['source']='yes24_api'
        with self.assertRaises(ValueError):check_payloads([{'observation':bad,'seller':'SYNTHETIC merchant'}],cfg)

    def test_product_metrics_and_timestamps_survive_restart(self):
        cfg=fixture_config('yes24_api');outbox=Outbox(cfg,self.root/cfg['source'],Mock())
        adapter=Adapter(cfg,SyntheticHTTP(cfg['source']))
        w=Worker(cfg,self.root,adapter=adapter,delivery=outbox)
        for row in fixture_rows(cfg['source']):w.accept(row)
        w.save();r=w.report()
        self.assertEqual((r['products_success'],r['products_held'],r['products_failed']),(2,1,0))
        w2=Worker(cfg,self.root,adapter=adapter,delivery=outbox)
        self.assertEqual(w2.report()['last_collection_at'],r['last_collection_at'])
        self.assertIsNotNone(w2.report()['last_success_at'])

    def test_real_http_exception_text_is_sanitized_in_summary(self):
        adapter=Mock();adapter.search.side_effect=RuntimeError('https://secret.test?api_key=PRIVATE_KEY')
        result=bounded_lookup(adapter,self.cfg)
        self.assertNotIn('PRIVATE_KEY',json.dumps(result));self.assertEqual(result['failed'],1)
