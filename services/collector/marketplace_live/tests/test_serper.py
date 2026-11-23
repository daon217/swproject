"""Offline Serper contract, budget, lookup and retirement regression cases."""
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
from ..config import validate
from ..credentials import load_serper_env
from ..http import ProviderHTTP,Pause,ProviderError
from ..probe import LookupHTTP,bounded_lookup,main as probe,plan
from ..__main__ import main as collect
from ..delivery_probe import main as delivery_probe
from ..serper import SOURCE,ENDPOINT,normalize,price
from ..synthetic import fixture_config,fixture_rows,SyntheticHTTP,run_mock
from ..runner import Worker
from ..delivery import Outbox
from .fixtures import response

PKG=__package__.rsplit('.tests',1)[0]

def config():
    cfg=fixture_config(SOURCE)
    cfg.update(max_units_per_month=20,cost_per_request='0.002',max_cost_per_month='0.04',credits_per_request=2)
    cfg['rights']['expires_at']=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    return cfg

class SerperTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.now=datetime.now(timezone.utc);self.cfg=config()
    def tearDown(self):self.temp.cleanup()
    def adapter(self):return Adapter(self.cfg,SyntheticHTTP(SOURCE),credential_reader=lambda _: 'SYNTHETIC_NOT_REAL')
    def http(self,session):
        h=ProviderHTTP(self.cfg,self.root,clock=lambda:self.now,session=session)
        h.cycle_id='SYNTHETIC_CYCLE';h.task_id='SYNTHETIC_TASK';return h

    def test_exact_POST_endpoint_header_and_JSON_no_SearchAPI_parameters(self):
        http=Mock();http.post_json.return_value={'shopping':fixture_rows(SOURCE)}
        a=Adapter(self.cfg,http,credential_reader=lambda name:'SYNTHETIC_ONLY')
        rows,more=a.search('mechanical keyboard',1)
        self.assertEqual(len(rows),3);self.assertFalse(more)
        call=http.post_json.call_args
        self.assertEqual(call.args,(ENDPOINT,))
        self.assertEqual(call.kwargs['headers'],{'X-API-KEY':'SYNTHETIC_ONLY','Content-Type':'application/json'})
        self.assertEqual(call.kwargs['json'],{'q':'mechanical keyboard','gl':'us','hl':'en'})
        self.assertNotIn('params',call.kwargs);http.get_json.assert_not_called()

    def test_wrong_method_host_redirect_query_or_path_blocked_before_HTTP(self):
        session=Mock();h=self.http(session)
        for method,url in [('GET',ENDPOINT),('POST','https://google.serper.dev/search'),
                           ('POST','https://www.searchapi.io/api/v1/search'),('POST',ENDPOINT+'?key=bad')]:
            with self.subTest(url=url),self.assertRaises(ValueError):h.request(method,url)
        session.request.assert_not_called()

    def test_no_second_page_or_silent_fallback_to_eBay(self):
        a=self.adapter()
        with self.assertRaises(ProviderError):a.search('q',2)
        self.assertEqual(a.http.state['requests'],[])

    def test_response_key_is_shopping_not_shopping_results(self):
        http=Mock();http.post_json.return_value={'shopping_results':[]}
        a=Adapter(self.cfg,http,credential_reader=lambda _: 'SYNTHETIC')
        with self.assertRaises(ProviderError):a.search('q',1)

    def test_native_projection_decimal_seller_identity_and_v2(self):
        row=fixture_rows(SOURCE)[0];row['price']='$1,234.50'
        body=normalize(row,self.now.isoformat(),self.cfg)['observation']
        self.assertEqual(body['source'],SOURCE);self.assertEqual(body['price'],'1234.50')
        self.assertEqual(body['source_listing_id'],row['productId']);self.assertTrue(body['variant_key'].startswith('merchant-url:'))
        self.assertNotIn('seller',body)
        self.assertEqual(normalize(row,self.now.isoformat(),self.cfg)['seller'],row['source'])

    def test_official_basic_shape_is_held_without_inventing_USD_stock_condition(self):
        row={'productId':'12345','title':'SYNTHETIC shoe','source':'SYNTHETIC shop',
             'link':'https://merchant.example.test/a','price':'$104.97','delivery':'Free shipping'}
        result=normalize(row,self.now.isoformat(),self.cfg)
        self.assertEqual(result['price'],'104.97');self.assertIsNone(result['observation'])
        self.assertEqual(set(result['missing_fields']),{'currency','condition','availability'})

    def test_currency_parser_uses_native_units_and_rejects_conflicts_or_ranges(self):
        self.assertEqual(price('$10.25'),('10.25',None))
        self.assertEqual(price('USD 10.25'),('10.25','USD'))
        self.assertEqual(price('US$10.25'),('10.25','USD'))
        self.assertEqual(price('$10 - $20'),(None,None))
        self.assertEqual(price('1.234,50 EUR'),(None,None))
        with self.assertRaises(ValueError):price('EUR 10.00','USD')

    def test_unknown_stock_or_refurbished_or_missing_ID_never_defaulted(self):
        for field,value in [('condition','refurbished'),('availability','unknown'),('productId',None)]:
            row=fixture_rows(SOURCE)[0];row[field]=value
            self.assertIsNone(normalize(row,self.now.isoformat(),self.cfg)['observation'])

    def test_direct_product_host_validation_and_merchant_identity(self):
        row=fixture_rows(SOURCE)[0]
        a=normalize(row,self.now.isoformat(),self.cfg)['observation']
        row['source']='OTHER SYNTHETIC merchant'
        b=normalize(row,self.now.isoformat(),self.cfg)['observation']
        self.assertNotEqual(a['variant_key'],b['variant_key'])
        for url in ('https://www.google.com/goto?url=opaque','http://merchant.example.test/a','https://evil.test/a'):
            row['link']=url
            with self.assertRaises(ValueError):normalize(row,self.now.isoformat(),self.cfg)

    def test_one_search_max_three_no_detail_and_unselected_rows_not_inspected(self):
        class Poison(dict):
            def get(self,*_):raise AssertionError('unselected row inspected')
        a=self.adapter();a.search=Mock(return_value=(fixture_rows(SOURCE)+[Poison() for _ in range(57)],False))
        a.detail=Mock(side_effect=AssertionError('no detail'))
        r=bounded_lookup(a,self.cfg,3)
        self.assertEqual((r['returned_count'],r['selected_count'],r['ignored_count']),(60,3,57))
        a.search.assert_called_once();a.detail.assert_not_called();self.assertEqual((r['success'],r['held']),(2,1))

    def test_two_merchants_one_catalogue_are_both_inspected(self):
        rows=fixture_rows(SOURCE);rows[1]['productId']=rows[0]['productId'];rows[1]['source']='OTHER SYNTHETIC'
        a=self.adapter();a.search=Mock(return_value=(rows,False))
        r=bounded_lookup(a,self.cfg,3)
        self.assertEqual(r['selected_count'],3);self.assertEqual(r['success'],2)

    def test_single_key_env_import_does_not_import_other_keys_or_write_file(self):
        file=self.root/'.env';text='SERPER_API_KEY="SYNTHETIC_PRIVATE"\nYES24_API_KEY=DO_NOT_LOAD\nKKULPICK_BACKEND_TOKEN=DO_NOT_LOAD\n'
        file.write_text(text,encoding='utf-8')
        with patch.dict(os.environ,{},clear=True):
            load_serper_env(file)
            self.assertTrue(os.environ.get('SERPER_API_KEY'));self.assertNotIn('YES24_API_KEY',os.environ)
            self.assertNotIn('KKULPICK_BACKEND_TOKEN',os.environ)
        self.assertEqual(file.read_text(),text)

    def test_duplicate_empty_or_conflicting_keys_fail_without_exposing_values(self):
        file=self.root/'.env'
        for text in ('SERPER_API_KEY=\n','SERPER_API_KEY=SYNTHETIC_PRIVATE\nSERPER_API_KEY=SECOND_SECRET\n'):
            file.write_text(text)
            with patch.dict(os.environ,{},clear=True),self.assertRaises(ValueError) as exc:load_serper_env(file)
            self.assertNotIn('SYNTHETIC_PRIVATE',str(exc.exception))
        file.write_text('SERPER_API_KEY=SYNTHETIC_PRIVATE\n')
        with patch.dict(os.environ,{'SERPER_API_KEY':'OTHER_VALUE'},clear=True),self.assertRaises(ValueError):load_serper_env(file)

    def test_plan_has_request_cost_query_and_no_key_value_or_network(self):
        self.cfg['queries']=['mechanical keyboard']
        with patch.dict(os.environ,{'SERPER_API_KEY':'SYNTHETIC_PRIVATE'}),patch('requests.Session',side_effect=AssertionError('no network')):
            r=plan(self.cfg,3)
        self.assertTrue(r['ready']);self.assertEqual(r['planned_search_requests'],1)
        self.assertEqual(r['max_products_inspected'],3);self.assertEqual(r['credits_reserved_per_request'],2)
        self.assertEqual(r['cost_upper_bound'],'0.002');self.assertEqual(r['query'],'mechanical keyboard')
        self.assertNotIn('SYNTHETIC_PRIVATE',json.dumps(r))

    def test_plan_explicit_env_file_uses_only_key_and_remains_no_HTTP(self):
        cfg=copy.deepcopy(self.cfg);cfg['backend_enabled']=False
        profile=self.root/'config.json';profile.write_text(json.dumps({'sources':[cfg]}))
        envfile=self.root/'.env';envfile.write_text('SERPER_API_KEY=SYNTHETIC_PRIVATE\nYES24_API_KEY=OTHER_PRIVATE\n')
        out=io.StringIO()
        with patch.dict(os.environ,{},clear=True),patch('requests.Session',side_effect=AssertionError('no network')),contextlib.redirect_stdout(out):
            rc=probe(['--source',SOURCE,'--plan','--config',str(profile),'--env-file',str(envfile)])
        self.assertEqual(rc,0);self.assertNotIn('SYNTHETIC_PRIVATE',out.getvalue());self.assertNotIn('OTHER_PRIVATE',out.getvalue())
        self.assertFalse(list(self.root.rglob('request_ledger.json')))

    def test_paid_budget_reserves_configured_credits_and_cost_across_restart(self):
        self.cfg['max_units_per_month']=3
        session=Mock();session.request.return_value=response({'shopping':[]})
        h=self.http(session);h.post_json(ENDPOINT,json={'q':'first'})
        self.assertEqual(h.state['requests'][0]['reserved_units'],2)
        self.now+=timedelta(seconds=11);h=self.http(session)
        with self.assertRaisesRegex(ProviderError,'budget'):h.post_json(ENDPOINT,json={'q':'second'})
        self.assertEqual(session.request.call_count,1);self.assertEqual(h.state['requests'][0]['reserved_cost'],'0.002')

    def test_reported_credit_overrun_keeps_actual_debit_and_holds_future_requests(self):
        session=Mock();session.request.return_value=response({'shopping':[],'credits':3})
        h=self.http(session)
        with self.assertRaisesRegex(ProviderError,'reservation_exceeded'):h.post_json(ENDPOINT,json={'q':'one'})
        self.assertEqual(h.state['requests'][0]['reserved_units'],3)
        self.assertEqual(self.http(session).state['hold'],'provider_credit_cost_review_required')
        self.now+=timedelta(seconds=11)
        with self.assertRaises(ProviderError):h.post_json(ENDPOINT,json={'q':'two'})
        self.assertEqual(session.request.call_count,1)

    def test_POST_fingerprint_tracks_JSON_not_headers_or_token(self):
        session=Mock();session.request.return_value=response({'shopping':[]})
        h=self.http(session);h.post_json(ENDPOINT,json={'q':'one'},headers={'X-API-KEY':'SYNTHETIC_PRIVATE'})
        self.now+=timedelta(seconds=11);h.post_json(ENDPOINT,json={'q':'two'},headers={'X-API-KEY':'SYNTHETIC_PRIVATE'})
        self.assertNotEqual(h.state['requests'][0]['request_hash'],h.state['requests'][1]['request_hash'])
        self.assertNotIn('SYNTHETIC_PRIVATE',h.path.read_text());self.assertNotIn('"q"',h.path.read_text())

    def test_uncertain_POST_no_resend_preserves_credits_and_deadline(self):
        session=Mock();session.request.side_effect=requests.Timeout('SYNTHETIC_PRIVATE')
        h=self.http(session)
        with self.assertRaises(Pause):h.post_json(ENDPOINT,json={'q':'one'})
        h=self.http(session)
        with self.assertRaises(Pause):h.post_json(ENDPOINT,json={'q':'one'})
        self.assertEqual(session.request.call_count,1);self.assertEqual(len(h.state['requests']),1)
        self.assertEqual(h.state['requests'][0]['reserved_units'],2)
        self.assertNotIn('SYNTHETIC_PRIVATE',h.path.read_text())

    def test_retry_after_and_auth_hold_preserved_for_Serper(self):
        session=Mock();session.request.return_value=response({},429,{'Retry-After':'9000'})
        h=self.http(session)
        with self.assertRaises(Pause) as exc:h.post_json(ENDPOINT,json={'q':'one'})
        self.assertEqual((exc.exception.until-self.now).total_seconds(),9000)
        self.assertEqual(self.http(session).state['not_before'],h.state['not_before'])

    def test_worker_cycle_schedule_outbox_duplicate_replay_and_source_isolation(self):
        tx=Mock(return_value=(201,{'state':'applied'}));d=Outbox(self.cfg,self.root/SOURCE,tx,clock=lambda:self.now)
        a=self.adapter();w=Worker(self.cfg,self.root,delivery=d,adapter=a,clock=lambda:self.now)
        w.step();w.step()
        self.assertEqual(w.state['totals']['cycles_completed'],1)
        self.assertEqual(len(a.http.state['requests']),1)
        self.assertEqual((w.report()['products_success'],w.report()['products_held']),(2,1))
        w2=Worker(self.cfg,self.root,delivery=d,adapter=a,clock=lambda:self.now);w2.step()
        self.assertEqual(len(a.http.state['requests']),1)
        self.now+=timedelta(seconds=7201);w2.step();self.assertEqual(len(a.http.state['requests']),2)
        self.assertFalse((self.root/'searchapi_google_shopping').exists())

    def test_missing_budget_or_credit_reservation_does_not_enable_live(self):
        for field,value in [('credits_per_request',0),('cost_per_request','0'),('max_units_per_month',0)]:
            cfg=copy.deepcopy(self.cfg);cfg[field]=value
            with self.assertRaises(ValueError):validate(cfg)

    def test_legacy_live_probe_collection_and_delivery_entrypoints_are_retired(self):
        with patch('requests.Session',side_effect=AssertionError('no network')),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(probe(['--source','searchapi_google_shopping','--live']),2)
            self.assertEqual(collect(['--source','searchapi_google_shopping','--watch']),2)
            self.assertEqual(delivery_probe(['--source','searchapi_google_shopping','--live']),2)

    def test_mock_Serper_zero_real_requests_two_queued_one_held(self):
        with patch.dict(os.environ,{},clear=True),patch('requests.Session',side_effect=AssertionError('no network')):
            r=run_mock(SOURCE,self.root)
        self.assertEqual((r['success'],r['held'],r['queue_pending']),(2,1,2))
        self.assertEqual(r['simulated_provider_actions'],1);self.assertEqual(r['backend_HTTP_requests'],0)
        self.assertEqual(r['provider_HTTP_attempts'],0)
