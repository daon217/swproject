"""Synthetic native fixtures; no provider calls, vision model, LLM, or DB needed."""
import copy
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import tempfile
import unittest
from services.collector.unified_live.matching import profile,provider_profile,compare,MatchingStore
from services.collector.unified_live.parser import normalize
from services.collector.unified_live.policy import validate
from services.collector.unified_live.mock import product,fixture_config,run_mock
from services.collector.unified_live.used import FullAdapter,LatestUsedAdapter,used_interval
from services.collector.unified_live.changes import ChangeDelivery
from services.collector.collector_ops.mock import SimulatedDelivery
from services.collector.marketplace_live.tests.fixtures import ebay,config
from services.collector.marketplace_live.normalize import validate_body

BASE='https://store.example.test/item/1'
def native(**updates):
    p={'name':'SYNTHETIC keyboard','brand':{'name':'SYNTHETIC Brand'},'modelNumber':'KB-01',
       'mpn':'KB-01-RED','color':'Red','size':'L','image':['/image/a.jpg','https://cdn.example.test/b.jpg'],
       'description':'SYNTHETIC public description','category':'Keyboards'}
    p.update(updates);return p
def mp(**updates):return profile(native(**updates),BASE,origin='SYNTHETIC')
def observation(at=None):
    return normalize(product(),BASE,at or datetime.now(timezone.utc).isoformat(),fixture_config())

class MatchingTests(unittest.TestCase):
    def test_native_fields_and_image_list(self):
        p=mp(manufacturer={'name':'SYNTHETIC Manufacturer'},model='Keyboard Series')
        self.assertEqual(p['brand'],'SYNTHETIC Brand');self.assertEqual(p['model_number'],'KB-01')
        self.assertEqual(p['manufacturer'],'SYNTHETIC Manufacturer');self.assertEqual(p['model_name'],'Keyboard Series')
        self.assertEqual(p['image_urls'],['https://store.example.test/image/a.jpg','https://cdn.example.test/b.jpg'])
        self.assertEqual(p['source_fields']['model_number'],['modelNumber'])
    def test_invalid_images_not_fetched_or_retained(self):
        p=mp(image=['http://example.test/a','data:image/png,abc','https://127.0.0.1/a','https://u:p@example.test/a','https://cdn.example.test/a?token=private'])
        self.assertEqual(p['image_urls'],[]);self.assertIn('image_URL_rejected',p['review_reasons'])
    def test_image_object_and_dedup(self):
        p=mp(image=[{'contentUrl':'/a.jpg'},'/a.jpg',{'url':'/b.jpg'}])
        self.assertEqual(len(p['image_urls']),2)
    def test_valid_GTIN_preserves_canonical_identity(self):
        p=mp(gtin13='3017620422003',gtin14='03017620422003')
        self.assertEqual([i['value'] for i in p['identifiers']],['03017620422003'])
    def test_invalid_or_numeric_GTIN_not_repaired(self):
        p=mp(gtin13=3017620422003,gtin='3017620422004')
        self.assertEqual(p['identifiers'],[]);self.assertIn('invalid_native_gtin',p['review_reasons'])
    def test_no_brand_model_or_GTIN_inferred_from_title_SKU(self):
        p=profile({'name':'FamousBrand KB-01 red XL','sku':'3017620422003'},BASE,origin='SYNTHETIC')
        self.assertIsNone(p['brand']);self.assertIsNone(p['model_number']);self.assertIsNone(p['color']);self.assertEqual(p['identifiers'],[])
    def test_options_native_and_conflicts(self):
        p=mp(additionalProperty=[{'name':'Storage Capacity','value':'256 GB'},{'name':'Color','value':'Blue'}])
        self.assertEqual(p['options']['storage_capacity'],'256 GB');self.assertIsNone(p['color'])
        self.assertIn('conflicting_native_color',p['review_reasons'])
    def test_model_punctuation_not_erased(self):
        r=compare(mp(modelNumber='AB-12',mpn=None),mp(modelNumber='AB12',mpn=None))
        self.assertEqual(r['match_type'],'identity_conflict')
    def test_brand_model_pair_is_candidate_never_confirmation(self):
        r=compare(mp(),mp())
        self.assertEqual(r['match_type'],'same_product_candidate');self.assertFalse(r['exact_match_confirmed'])
    def test_same_image_without_identifiers_only_similarity(self):
        p=profile({'image':'/same.jpg'},BASE,origin='SYNTHETIC')
        self.assertEqual(compare(p,p)['match_type'],'similar_candidate')
    def test_different_colors_sizes_capacity_do_not_merge(self):
        for key in ('color','size'):
            with self.subTest(key=key):
                r=compare(mp(),mp(**{key:'different'}));self.assertEqual(r['match_type'],'identity_conflict')
        a=mp(additionalProperty=[{'name':'Storage Capacity','value':'128 GB'}]);b=mp(additionalProperty=[{'name':'Storage Capacity','value':'256 GB'}])
        self.assertEqual(compare(a,b)['match_type'],'identity_conflict')
    def test_GTIN_conflict_wins_over_same_brand_model(self):
        self.assertEqual(compare(mp(gtin='3017620422003'),mp(gtin='4006381333931'))['match_type'],'identity_conflict')
    def test_missing_options_not_equal_by_default(self):
        self.assertEqual(compare(mp(),mp(color=None,size=None))['variant_status'],'partially_specified')
    def test_manufacturer_alone_never_identity(self):
        a=profile({'manufacturer':'SYNTHETIC Corp'},BASE,origin='SYNTHETIC')
        self.assertEqual(compare(a,a)['match_type'],'similar_candidate')
    def test_jsonld_profile_keeps_v2_body_and_offer_keys(self):
        cfg=fixture_config();at=datetime.now(timezone.utc).isoformat();original=normalize(product(),BASE,at,cfg)
        html=product().replace('"sku": "SYNTHETIC-SKU"','"sku": "SYNTHETIC-SKU", "mpn":"KB-01", "modelNumber":"MODEL-1", "color":"red"')
        result=normalize(html,BASE,at,cfg)
        self.assertEqual(original['observation'],result['observation']);self.assertEqual(result['metadata']['matching_profile']['mpn'],'KB-01')
        validate_body(result['observation'],cfg)
    def test_microdata_profile_and_reviewed_selectors(self):
        cfg=fixture_config();cfg['selectors'].update(model_number='#model',color='#color')
        validate(cfg)
        html=product().replace('<script type="application/ld+json">','<span id="model">MODEL-1</span><span id="color">red</span><script type="application/ld+json">')
        # JSON-LD remains authoritative; it is never silently replaced by CSS.
        result=normalize(html,BASE,datetime.now(timezone.utc).isoformat(),cfg)
        self.assertIsNone(result['metadata']['matching_profile']['model_number'])
        css='<meta itemprop="model" content="Series"><meta itemprop="mpn" content="MPN-1"><span id="model">MODEL-1</span><span id="color">red</span>'
        result=normalize(css,BASE,datetime.now(timezone.utc).isoformat(),cfg)
        self.assertEqual(result['metadata']['matching_profile']['model_number'],'MODEL-1')
        self.assertEqual(result['metadata']['matching_profile']['color'],'red');self.assertIsNone(result['observation'])
    def test_ebay_native_details_and_localized_aspects(self):
        row=ebay();row.update(image={'imageUrl':'https://i.ebayimg.com/a.jpg'},additionalImages=[{'imageUrl':'https://i.ebayimg.com/b.jpg'}],
            localizedAspects=[{'name':'Brand','value':'SYNTHETIC Brand'},{'name':'MPN','value':'MPN-1'},{'name':'Color','value':'Red'},{'name':'UPC','value':'3017620422003'}])
        result=FullAdapter(config('ebay_browse'),None).normalize(row,datetime.now(timezone.utc).isoformat())
        p=result['metadata']['matching_profile'];self.assertEqual(p['mpn'],'MPN-1');self.assertEqual(len(p['image_urls']),2)
        self.assertEqual(len(p['identifiers']),1);self.assertNotIn('matching_profile',result['observation'])
    def test_used_condition_kept_separate_from_product_identity(self):
        row=ebay();row['conditionId']='3000';row['condition']='Used'
        result=LatestUsedAdapter(config('ebay_browse'),None).normalize(row,datetime.now(timezone.utc).isoformat())
        self.assertEqual(result['condition'],'used');self.assertIsNone(result['metadata']['matching_profile']['model_number'])
    def test_serper_missing_identifiers_stay_missing(self):
        p=provider_profile({'productId':'123','title':'SYNTHETIC','imageUrl':'/image.jpg'},'serper_google_shopping',BASE)
        self.assertEqual(p['identifiers'],[]);self.assertEqual(p['image_url'],'https://store.example.test/image.jpg')
    def test_yes24_dome_and_feed_projections(self):
        for source,row in [('yes24_api',{'cover':'/cover.jpg','title':'SYNTHETIC'}),('domeggook',{'image_url':'/image.jpg','product_name':'SYNTHETIC'}),('yappy_kids',{'image_link':'/feed.jpg','title':'SYNTHETIC','mpn':'MPN-1'})]:
            with self.subTest(source=source):
                p=provider_profile(row,source,BASE);self.assertIsNotNone(p['image_url']);self.assertEqual(p['product_name'],'SYNTHETIC')
    def test_matching_sidecar_storage_and_description_grants(self):
        cfg=fixture_config();r=observation();r['metadata']['matching_profile']=mp()
        with tempfile.TemporaryDirectory() as d:
            s=MatchingStore(d,cfg['source']);s.record(r,cfg);saved=next(iter(s.data['items'].values()))
            self.assertIsNone(saved['profile']['description']);self.assertFalse(saved['backend_contract_ready'])
            cfg['rights']['allowed_uses'].append('description_storage');s.record(r,cfg)
            self.assertEqual(next(iter(s.data['items'].values()))['profile']['description'],'SYNTHETIC public description')
    def test_matching_sidecar_not_written_without_storage_permission(self):
        cfg=fixture_config();cfg['rights']['allowed_uses']=['lookup'];r=observation();r['metadata']['matching_profile']=mp()
        with tempfile.TemporaryDirectory() as d:
            MatchingStore(d,cfg['source']).record(r,cfg);self.assertFalse((Path(d)/'matching_checkpoint.json').exists())
    def test_sidecar_restart_and_change_timestamps(self):
        cfg=fixture_config();now=datetime.now(timezone.utc);r=observation(now.isoformat());r['metadata']['matching_profile']=mp()
        with tempfile.TemporaryDirectory() as d:
            MatchingStore(d,cfg['source']).record(r,cfg)
            r['observation']['observed_at']=(now+timedelta(seconds=60)).isoformat();s=MatchingStore(d,cfg['source']);s.record(r,cfg)
            saved=next(iter(s.data['items'].values()));self.assertEqual(saved['last_changed_at'],now.isoformat());self.assertNotEqual(saved['last_checked_at'],now.isoformat())
            r['observation']['price']='99';s.record(r,cfg)
            self.assertEqual(next(iter(s.data['items'].values()))['last_changed_at'],r['observation']['observed_at'])
    def test_matching_sidecar_rechecks_expiry_and_revocation(self):
        r=observation();r['metadata']['matching_profile']=mp()
        for mode in ('expired','reference_removed','terms_removed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                cfg=fixture_config()
                if mode=='expired':cfg['rights']['expires_at']='2000-01-01T00:00:00+00:00'
                elif mode=='reference_removed':cfg['rights']['reference']=''
                else:cfg['rights']['terms_reference']=''
                MatchingStore(d,cfg['source']).record(r,cfg)
                self.assertFalse((Path(d)/'matching_checkpoint.json').exists())
    def test_yes24_sidecar_requires_storage_exception(self):
        cfg=config('yes24_api');cfg['rights']['exception_agreement_reference']=''
        r=observation();r['observation']['source']='yes24_api';r['metadata']['matching_profile']=mp()
        with tempfile.TemporaryDirectory() as d:
            MatchingStore(d,'yes24_api').record(r,cfg);self.assertFalse((Path(d)/'matching_checkpoint.json').exists())
    def test_matching_change_does_not_resend_unchanged_v2(self):
        cfg=fixture_config();r=observation();r['metadata']['matching_profile']=mp()
        with tempfile.TemporaryDirectory() as d:
            box=SimulatedDelivery(cfg,Path(d));gate=ChangeDelivery(box,d)
            try:
                gate.stage(r);r['metadata']['matching_profile']=mp(color='blue');self.assertEqual(gate.stage(r)['status'],'unchanged_skipped')
                saved=next(iter(MatchingStore(d,cfg['source']).data['items'].values()));self.assertEqual(saved['profile']['color'],'blue')
                self.assertEqual(len(box.state['entries']),1)
            finally:gate.close()
    def test_schedule_and_content_dedup_regression(self):
        self.assertEqual(used_interval({})[0],7200)
        self.assertEqual(used_interval({'mode':'used','policy_reference':'SYNTHETIC','provider_min_interval_seconds':60})[0],60)
        with tempfile.TemporaryDirectory() as d:
            result=run_mock(d);self.assertTrue(result['unchanged_no_API_write']);self.assertEqual(result['external_HTTP_requests'],0)
    def test_corrupt_sidecar_never_reset(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'matching_checkpoint.json').write_text('{"version":99,"source":"other"}')
            with self.assertRaises(ValueError):MatchingStore(d,'html_test')
    def test_optional_fields_and_bounds(self):
        p=profile({'name':'x'*1000,'image':['/'+str(i)+'.jpg' for i in range(100)]},BASE,origin='SYNTHETIC')
        self.assertLessEqual(len(p['product_name']),300);self.assertLessEqual(len(p['image_urls']),8)
        self.assertEqual(p['options'],{});self.assertIsNone(p['variant_signature'])
