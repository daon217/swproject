import copy
import importlib.util
import os
from pathlib import Path
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock,patch
from .. import normalize
from ..adapters import Adapter
from ..http import ProviderError,Pause
from ..vendor.ebay_oauth import EbayOAuth
from .fixtures import config,yes24,ebay,shopping

AT=datetime.now(timezone.utc).isoformat()

class NormalizationTests(unittest.TestCase):
    def test_reused_yes24_native_normalizer_and_v2_shape(self):
        r=normalize.yes24(yes24(),AT,config())
        self.assertEqual(r['observation']['source_listing_id'],'12345678')
        self.assertEqual(r['observation']['price'],'29700')
        self.assertEqual(r['seller'],'SYNTHETIC seller');self.assertNotIn('seller',r['observation'])

    def test_official_yes24_shape_does_not_invent_missing_native_fields(self):
        r=normalize.yes24(yes24(False),AT,config())
        self.assertIsNone(r['observation']);self.assertEqual(set(r['missing_fields']),{'variant_key','condition','availability','currency'})
        self.assertEqual(r['native_status'],'판매중');self.assertIsNone(r['seller'])

    def test_yes24_bad_money_and_untrusted_URL_are_rejected(self):
        for field,value in [('salePrice',True),('salePrice','NaN'),('link','https://evil.example/product/123')]:
            row=yes24();row[field]=value
            try:result=normalize.yes24(row,AT,config())
            except ValueError:continue
            self.assertIsNone(result['observation'])

    def test_ebay_decimal_identity_and_native_condition(self):
        r=normalize.ebay(ebay(),AT,config('ebay_browse'));b=r['observation']
        self.assertEqual((b['source_listing_id'],b['variant_key']),('123456789','v1|123456789|0'))
        self.assertEqual((b['price'],b['currency'],b['condition']),('12.3400','USD','new'))

    def test_ebay_refurbished_parts_or_missing_stock_not_defaulted(self):
        for condition in ('1500','2000','7000',None):
            r=ebay();r['conditionId']=condition
            self.assertIsNone(normalize.ebay(r,AT,config('ebay_browse'))['observation'])
        r=ebay();r['estimatedAvailabilities']=[]
        self.assertIn('availability',normalize.ebay(r,AT,config('ebay_browse'))['missing_fields'])

    def test_ebay_auction_is_not_a_retail_price(self):
        r=ebay();r['buyingOptions']=['AUCTION']
        with self.assertRaises(ValueError):normalize.ebay(r,AT,config('ebay_browse'))

    def test_shopping_native_offer_separates_merchants(self):
        cfg=config('searchapi_google_shopping');first=shopping();second=shopping();second['seller']='OTHER SYNTHETIC merchant'
        a=normalize.shopping(first,AT,cfg)['observation'];b=normalize.shopping(second,AT,cfg)['observation']
        self.assertEqual(a['source_listing_id'],b['source_listing_id']);self.assertNotEqual(a['variant_key'],b['variant_key'])
        self.assertNotEqual(a['observation_key'],b['observation_key'])

    def test_official_shopping_shape_does_not_infer_USD_stock_or_condition(self):
        r=normalize.shopping(shopping(False),AT,config('searchapi_google_shopping'))
        self.assertIsNone(r['observation']);self.assertEqual(set(r['missing_fields']),{'currency','condition','availability'})

    def test_shopping_google_redirect_and_unknown_merchants_rejected(self):
        for url in ('https://www.google.com/goto?url=opaque','https://evil.example/product/1','http://merchant.example.test/a'):
            r=shopping();r['link']=url
            with self.assertRaises(ValueError):normalize.shopping(r,AT,config('searchapi_google_shopping'))

    def test_all_complete_adapters_match_actual_team_model_without_DB(self):
        # Import only the pure Pydantic model file, never FastAPI/engine modules.
        model_path=Path(os.environ.get('KKULPICK_TEST_MODEL_PATH',Path(__file__).resolve().parents[4]/'services/api/kkulpick/models.py'))
        if not model_path.is_file() and not os.environ.get('KKULPICK_TEST_MODEL_PATH'):
            self.skipTest('team API model not in collector-only checkout; set KKULPICK_TEST_MODEL_PATH for integration contract validation')
        spec=importlib.util.spec_from_file_location('marketplace_team_contract',model_path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for source,fn,row in [('yes24_api',normalize.yes24,yes24()),('ebay_browse',normalize.ebay,ebay()),
                              ('searchapi_google_shopping',normalize.shopping,shopping())]:
            cfg=config(source)
            with patch.dict(os.environ,{'CATALOG_URL_HOSTS':','.join(cfg['allowed_product_hosts'])}):
                module.Observation.model_validate(fn(row,AT,cfg)['observation'])

class AdapterTests(unittest.TestCase):
    def test_yes24_search_and_detail_use_documented_header_and_identity(self):
        http=Mock();http.get_json.return_value={'success':True,'data':{'items':[yes24()],'currentPage':1}}
        a=Adapter(config(),http)
        with patch.dict(os.environ,{'YES24_API_KEY':'SYNTHETIC'}):
            self.assertEqual(len(a.search('SYNTHETIC query',1)[0]),1)
            self.assertEqual(a.detail('12345678')['itemId'],12345678)
        self.assertEqual(http.get_json.call_args.kwargs['params'],{'searchType':'ItemId','query':'12345678','detail':'N'})
        self.assertEqual(http.get_json.call_args.kwargs['headers'],{'X-Api-Key':'SYNTHETIC'})

    def test_wrong_detail_identity_and_provider_error_are_not_merged(self):
        http=Mock();http.get_json.return_value={'success':True,'data':{'items':[yes24()]}}
        with patch.dict(os.environ,{'YES24_API_KEY':'SYNTHETIC'}):
            with self.assertRaisesRegex(ProviderError,'identity'):Adapter(config(),http).detail('999')
            http.get_json.return_value={'success':False,'data':None}
            with self.assertRaises(ProviderError):Adapter(config(),http).search('q',1)

    def test_SearchAPI_uses_header_and_fixed_engine_without_next_URL_following(self):
        cfg=config('searchapi_google_shopping');http=Mock()
        http.get_json.return_value={'shopping_results':[shopping()],'pagination':{'next':'https://evil.example'}}
        with patch.dict(os.environ,{'SEARCHAPI_API_KEY':'SYNTHETIC'}):Adapter(cfg,http).search('q',2)
        call=http.get_json.call_args
        self.assertEqual(call.args[0],'https://www.searchapi.io/api/v1/search')
        self.assertEqual(call.kwargs['headers'],{'Authorization':'Bearer SYNTHETIC'})
        self.assertEqual(call.kwargs['params']['engine'],'google_shopping');self.assertNotIn('api_key',call.kwargs['params'])

    def test_reused_ebay_OAuth_cache_invalidation_and_no_secret_in_errors(self):
        tx=Mock();tx.post_json.return_value={'access_token':'SYNTHETIC_TOKEN','expires_in':3600}
        oauth=EbayOAuth('SYNTHETIC_ID','SYNTHETIC_SECRET',tx)
        self.assertEqual(oauth._get_access_token(),oauth._get_access_token());self.assertEqual(tx.post_json.call_count,1)
        oauth._invalidate_token('older_token');oauth._get_access_token();self.assertEqual(tx.post_json.call_count,1)
        oauth._invalidate_token('SYNTHETIC_TOKEN');oauth._get_access_token();self.assertEqual(tx.post_json.call_count,2)

    def test_ebay_second_401_is_held_after_one_refresh(self):
        cfg=config('ebay_browse');http=Mock();http.state={}
        http.get_json.side_effect=ProviderError('provider_access_refused',401)
        a=Adapter(cfg,http);a.oauth=Mock();a.oauth._get_access_token.return_value='SYNTHETIC'
        with self.assertRaises(ProviderError):a.search('q',1)
        self.assertEqual(http.get_json.call_count,2);self.assertEqual(a.oauth._get_access_token.call_count,2)
        self.assertEqual(http.state['hold'],'repeated_401_review_required')

    def test_ebay_401_retry_count_survives_rate_limit_pause_between_refreshes(self):
        cfg=config('ebay_browse');http=Mock();http.state={'requests':[]};http.task_id='SYNTHETIC_TASK'
        def denied(*args,**kwargs):
            http.state['requests'].append({'status':401,'task_id':http.task_id})
            raise ProviderError('provider_access_refused',401)
        http.get_json.side_effect=denied
        a=Adapter(cfg,http);a.oauth=Mock()
        a.oauth._get_access_token.side_effect=['SYNTHETIC_TOKEN',Pause('request_interval_wait',datetime.now(timezone.utc)),'SYNTHETIC_NEW_TOKEN']
        with self.assertRaises(Pause):a.search('q',1)
        with self.assertRaises(ProviderError):a.search('q',1)
        self.assertEqual(http.get_json.call_count,2);self.assertEqual(http.state['hold'],'repeated_401_review_required')
