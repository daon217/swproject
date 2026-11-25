"""Native evidence and truthful v2 compatibility. All test fixtures are local."""
import copy,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from services.collector.unified_live.mock import fixture_config,product,FakeHTTP
from services.collector.unified_live.parser import normalize
from services.collector.unified_live.analysis import value
from services.collector.unified_live.policy import validate
from services.collector.unified_live.engine import URLWorker
from services.collector.unified_live.changes import ChangeDelivery
from services.collector.collector_ops.mock import SimulatedDelivery
from services.collector.domeggook_live.domeggook_backend_contract import Observation
from bs4 import BeautifulSoup

class NormalizationEvidence(unittest.TestCase):
 def setUp(self):self.cfg=fixture_config();self.at=datetime.now(timezone.utc).isoformat()
 def norm(self,html,cfg=None,**kwargs):return normalize(html,'https://store.example.test/item/1',self.at,cfg or self.cfg,**kwargs)
 def test_microdata_wins_over_generic_OG_page_title_and_image(self):
  html='<meta property="og:title" content="Website page"><meta property="og:image" content="/banner.png"><div itemtype="https://schema.org/Product" itemscope><h1 itemprop="name">Native product</h1><img itemprop="image" src="/product.png"></div>'
  soup=BeautifulSoup(html,'html.parser');self.assertEqual(value(soup,'name'),'Native product');self.assertEqual(value(soup,'image'),'/product.png')
 def test_explicit_product_OG_block_wins_over_website_OG(self):
  html='<meta property="og:type" content="website"><meta property="og:title" content="page"><meta property="og:image" content="/banner.png"><meta property="og:type" content="product"><meta property="og:title" content="Native product"><meta property="og:image" content="/product.png">'
  soup=BeautifulSoup(html,'html.parser');self.assertEqual(value(soup,'name'),'Native product');self.assertEqual(value(soup,'image'),'/product.png')
 def test_conflicting_native_prices_stay_unknown(self):
  soup=BeautifulSoup('<meta itemprop="price" content="10"><meta itemprop="price" content="20"><meta property="product:price:amount" content="10">','html.parser');self.assertIsNone(value(soup,'price'))
 def test_symbol_price_preserves_amount_without_guessing_currency(self):
  html=product().replace('"price": "12.00"','"price": "£51.77"').replace('"priceCurrency": "USD"','"priceCurrency": null')
  r=self.norm(html);self.assertEqual(r['price'],'51.77');self.assertIsNone(r['currency']);self.assertIsNone(r['observation']);self.assertIn('currency',r['missing_fields']);self.assertEqual(r['metadata']['normalization_evidence']['price']['symbol'],'£')
 def test_ambiguous_dollar_does_not_become_USD(self):
  html=product().replace('"price": "12.00"','"price": "$12.00"').replace('"priceCurrency": "USD"','"priceCurrency": null');r=self.norm(html);self.assertIsNone(r['currency']);self.assertIsNone(r['observation'])
 def test_printed_ISO_currency_is_usable(self):
  html=product().replace('"price": "12.00"','"price": "USD 12.00"').replace('"priceCurrency": "USD"','"priceCurrency": null');r=self.norm(html);self.assertEqual(r['currency'],'USD');self.assertIsNotNone(r['observation'])
 def test_missing_condition_unknown_is_never_omitted_to_default_new(self):
  r=self.norm(product().replace('https://schema.org/UsedCondition',''))
  self.assertIsNone(r['observation']);self.assertEqual(r['metadata']['normalization_evidence']['condition'],'unknown');self.assertIn('condition_unknown_contract_required',r['missing_fields'])
 def test_absent_availability_can_be_omitted_under_existing_contract(self):
  r=self.norm(product().replace('https://schema.org/InStock',''),allow_partial_update=True);body=r['observation'];self.assertIsNotNone(body);self.assertNotIn('availability',body);self.assertNotIn('availability',body['field_presence']);self.assertEqual(r['metadata']['normalization_evidence']['availability'],'unknown');self.assertIsNone(r['metadata']['stock_quantity']);self.assertIsNone(r['metadata']['purchase_available']);Observation.model_validate(body,context={'hosts':self.cfg['allowed_product_hosts'],'currencies':self.cfg['currencies']})
 def test_unrepresentable_preorder_stays_held(self):
  r=self.norm(product().replace('InStock','PreOrder'));self.assertIsNone(r['observation']);self.assertIn('availability',r['missing_fields'])
 def test_native_stock_label_is_not_lost(self):
  r=self.norm(product().replace('https://schema.org/InStock','In stock (22 available)'));self.assertEqual(r['availability'],'available');self.assertEqual(r['metadata']['stock_quantity'],22)
 def test_conflicting_stock_is_held(self):
  html=product().replace('"@type": "Offer"','"@type": "Offer", "inventoryLevel":{"value":0}')
  r=self.norm(html);self.assertIsNone(r['observation']);self.assertIsNone(r['metadata']['stock_quantity']);self.assertEqual(r['metadata']['normalization_evidence']['quantity_kind'],'conflicting_native_stock')
 def test_storefront_domain_identity_does_not_invent_seller_name(self):
  cfg=self.cfg;cfg['storefront_identity']={'domain':'store.example.test','single_merchant':True,'reference':'https://store.example.test/about','expires_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()};validate(cfg)
  r=self.norm(product().replace('"name": "SYNTHETIC seller"','"name": null'));self.assertIsNotNone(r['observation']);self.assertIsNone(r['seller']);self.assertNotIn('seller',r['observation']);self.assertFalse(r['metadata']['normalization_evidence']['storefront_identity']['legal_seller_verified'])
 def test_expired_identity_does_not_bypass_native_seller_hold(self):
  self.cfg['storefront_identity']={'domain':'store.example.test','single_merchant':True,'reference':'https://store.example.test/about','expires_at':'2000-01-01T00:00:00+00:00'}
  r=self.norm(product().replace('"name": "SYNTHETIC seller"','"name": null'));self.assertIsNone(r['observation']);self.assertIn('seller',r['missing_fields'])
 def test_cross_domain_storefront_proof_rejected(self):
  self.cfg['storefront_identity']={'domain':'evil.example.test','single_merchant':True,'reference':'https://evil.example.test/','expires_at':'2030-01-01T00:00:00+00:00'}
  with self.assertRaises(ValueError):validate(self.cfg)
 def test_missing_options_are_explicit_not_exposed(self):
  r=self.norm(product());self.assertEqual(r['metadata']['normalization_evidence']['options_status'],'not_exposed');self.assertEqual(r['metadata']['normalization_evidence']['variant_key_kind'],'native_sku')
 def test_new_microdata_sku_does_not_silently_change_legacy_variant(self):
  html='<h1 itemprop="name">Native product</h1><span itemprop="sku">SKU-1</span><meta itemprop="price" content="12"><meta itemprop="priceCurrency" content="USD"><link itemprop="itemCondition" href="https://schema.org/UsedCondition"><link itemprop="availability" href="https://schema.org/InStock"><span itemprop="seller">SYNTHETIC seller</span>'
  r=self.norm(html);self.assertEqual(r['observation']['variant_key'],r['product_number']);self.assertEqual(r['metadata']['normalization_evidence']['native_sku'],'SKU-1')
 def test_URL_tracking_removed_and_native_options_not_collapsed(self):
  red=self.norm(product().replace('/item/1','/item/1?color=red&utm_source=x'));blue=self.norm(product().replace('/item/1','/item/1?color=blue'));self.assertIn('color=red',red['url']);self.assertNotIn('utm_',red['url']);self.assertNotEqual(red['url'],blue['url'])
 def test_optional_availability_body_deduplicates_and_ACKs(self):
  r=self.norm(product().replace('https://schema.org/InStock',''),allow_partial_update=True)
  with tempfile.TemporaryDirectory() as d:
   box=SimulatedDelivery(self.cfg,Path(d));gate=ChangeDelivery(box,Path(d));gate.stage(self.norm(product()));gate.flush();gate.stage(r);gate.flush();self.assertEqual(len(box.fake_API.calls),2);self.assertEqual(gate.stage(r)['status'],'unchanged_skipped');gate.close()
 def test_unknown_availability_new_listing_is_held(self):
  r=self.norm(product().replace('https://schema.org/InStock',''));self.assertIsNone(r['observation']);self.assertIn('availability',r['missing_fields']);self.assertEqual(r['metadata']['normalization_evidence']['availability'],'unknown')
 def test_test_backend_mirrors_incomplete_first_observation_quarantine(self):
  from services.collector.unified_live.local_receipt import ReceiptStore
  body=self.norm(product().replace('https://schema.org/InStock',''),allow_partial_update=True)['observation']
  with tempfile.TemporaryDirectory() as d:
   store=ReceiptStore(Path(d)/'collector_test_first.sqlite',self.cfg['allowed_product_hosts'],self.cfg['currencies']);code,ack=store.receive(body)
   self.assertEqual(code,201);self.assertEqual(ack['state'],'quarantine');self.assertEqual(ack['reason'],'INCOMPLETE_FIRST_OBSERVATION');self.assertEqual(store.counts()['listings'],0)
 def test_inspector_plan_has_zero_source_and_backend_requests(self):
  from contextlib import redirect_stdout
  import io
  from services.collector.unified_live.devtest.inspect_normalization import main
  with tempfile.TemporaryDirectory() as d:
   profile=Path(d)/'profiles.json';profile.write_text('[]');out=io.StringIO()
   with redirect_stdout(out):code=main(['--profiles',str(profile),'--state-dir',d,'--output',str(Path(d)/'out.json')])
   self.assertEqual(code,0);self.assertEqual(json.loads(out.getvalue())['source_requests'],0)
 def test_inspector_missing_grant_never_creates_HTTP(self):
  from unittest.mock import patch
  from services.collector.unified_live.devtest.inspect_normalization import inspect
  with tempfile.TemporaryDirectory() as d,patch('services.collector.unified_live.devtest.inspect_normalization.BatchHTTP',side_effect=AssertionError('no network')):
   rows=inspect([{'host':'store.example.test','approval':{}}],d)
  self.assertEqual(rows[0]['failure'],'explicit_lookup_grant_required')
 def test_inspector_profile_failure_is_isolated(self):
  from services.collector.unified_live.devtest.inspect_normalization import inspect
  with tempfile.TemporaryDirectory() as d:
   rows=inspect([{'host':'bad.example.test'},{'host':'store.example.test','approval':{}}],d)
  self.assertEqual(len(rows),2);self.assertEqual(rows[0]['failure'],'profile_or_lock_review');self.assertEqual(rows[1]['failure'],'explicit_lookup_grant_required')
 def test_inspector_keeps_official_API_platform_on_dedicated_path(self):
  from services.collector.unified_live.devtest.inspect_normalization import inspect
  with tempfile.TemporaryDirectory() as d:rows=inspect([{'host':'www.ebay.com','approval':{}}],d)
  self.assertEqual(rows[0]['failure'],'dedicated_official_adapter_required');self.assertEqual(rows[0]['source_requests'],0)
 def test_JSONLD_offer_URL_is_not_replaced_by_page_OG_URL(self):
  html=product().replace('"url": "https://store.example.test/item/1",','')
  p=json.loads(html.split('application/ld+json">')[1].split('</script>')[0]);p['offers']['url']='https://store.example.test/native-product'
  html='<meta property="og:url" content="https://store.example.test/format-page"><script type="application/ld+json">'+json.dumps(p)+'</script>'
  r=self.norm(html);self.assertEqual(r['url'],'https://store.example.test/native-product')
 def test_JSONLD_missing_SKU_does_not_adopt_new_Microdata_variant(self):
  html=product().replace('"sku": "SYNTHETIC-SKU",','')+'<span itemprop="sku">NEW-DOM-SKU</span>'
  r=self.norm(html);self.assertEqual(r['observation']['variant_key'],r['product_number'])
if __name__=='__main__':unittest.main()
