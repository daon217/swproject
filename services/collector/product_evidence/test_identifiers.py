"""Synthetic regression fixtures; not counted as actual extracted products."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from services.collector.product_evidence.identifiers import extract_identifiers
from services.collector.product_evidence.extract import ProductEvidenceRequest,enrich_product,avoidance_matches
from services.collector.domeggook_live.fixture_data import row,config
from services.collector.collector_ops.dome import FoodDelivery

class IdentityComponentTests(unittest.TestCase):
    def test_jsonld_identifiers_use_only_explicit_product_values(self):
        html='<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'Title MPN-FAKE','gtin13':'4006381333931','mpn':'PART-01','sku':'SELLER-01','brand':{'name':'Example'},'model':'Explicit model'})+'</script>'
        r=extract_identifiers(html=html,html_allowed=True,product_url='https://example.com/p')
        self.assertEqual(r['values']['gtin'],'04006381333931');self.assertEqual(r['values']['mpn'],'PART-01')
        self.assertEqual(r['values']['sku'],'SELLER-01');self.assertNotIn('model_number',r['values'])
        self.assertEqual(extract_identifiers(html=html,html_allowed=False)['values'],{})
    def test_bad_gtin_and_placeholder_do_not_become_identifiers(self):
        r=extract_identifiers(api_values={'gtin':('4006381333932','detail.gtin'),'model_name':('해당없음','detail.model')})
        self.assertEqual(r['values'],{});self.assertEqual(r['rejected'][0]['reason'],'invalid_gtin')
    def test_conflicting_mpn_not_sent_and_multiple_products_not_misattributed(self):
        r=extract_identifiers(api_values={'mpn':('ONE','detail.mpn')},notices=({'name':'MPN','desc':'TWO'},))
        self.assertNotIn('mpn',r['values']);self.assertEqual(r['evidence']['mpn']['status'],'conflicting')
        html='<script type="application/ld+json">'+json.dumps([{'@type':'Product','mpn':'A'},{'@type':'Product','mpn':'B'}])+'</script>'
        self.assertEqual(extract_identifiers(html=html,html_allowed=True)['values'],{})
    def test_unified_components_do_not_include_declared_allergens(self):
        q=ProductEvidenceRequest('domeggook','https://example.com/p','2026-11-25T00:00:00Z',({'name':'식품'},),True,api_notices=({'name':'원재료명','desc':'설탕 40%, 밀가루 60%'},{'name':'알레르기','desc':'밀'}))
        r=enrich_product(q);self.assertEqual(len(r['components']),2)
        self.assertEqual(r['fields']['allergens']['normalized'][0]['code'],'wheat')
        self.assertNotIn('allergens',{x['field_kind'] for x in r['components']})
        self.assertIsNone(avoidance_matches(r,['milk'])['safe_to_use'])
    def test_materials_tables_percentage_and_jsonld_share_component_list(self):
        html='<table><tr><th>소재 및 혼용률</th><td>면80% 폴리에스터20%</td><th>주의사항</th><td>단독 세탁</td></tr></table>'
        q=ProductEvidenceRequest('example','https://example.com/p','2026-11-25T00:00:00Z',({'name':'의류'},),False,description_html=html,text_use_allowed=True)
        r=enrich_product(q);self.assertEqual([(x['code'],x['percentage']) for x in r['components']],[('cotton','80'),('polyester','20')])
        self.assertTrue(avoidance_matches(r,['면'])['matches'])
    def test_domeggook_preserves_allowed_jsonld_for_common_components(self):
        from services.collector.domeggook_live.tests.fixtures import fixture
        from services.collector.domeggook_live.domeggook_pipeline import normalize_detail
        from services.collector.domeggook_live.components import build_request
        listing,payload=fixture();payload['desc']['contents']['item']='<script type="application/ld+json">'+json.dumps({'@type':'Product','material':'면100%'})+'</script>'
        r=normalize_detail(listing,payload,'2026-11-25T00:00:00Z');e=enrich_product(build_request(r))
        self.assertEqual(e['components'][0]['code'],'cotton')
        payload['desc']['license']['usable']=False
        r=normalize_detail(listing,payload,'2026-11-25T00:00:00Z');self.assertIsNone(r['description_source_html'])
    def test_food_contract_keeps_ingredients_and_declarations_separate(self):
        from services.collector.product_evidence.extract import merge_food_evidence
        q=ProductEvidenceRequest('example','https://example.com/p','2026-11-25T00:00:00Z',({'name':'식품'},),True,api_notices=({'name':'원재료명','desc':'우유20%, 설탕80%'},))
        merged=merge_food_evidence({'allergen_status':'not_reported'},enrich_product(q))
        self.assertEqual(merged['ingredients_normalized'][0]['name'],'우유');self.assertFalse(merged.get('allergens_declared'))
        q=ProductEvidenceRequest('example','https://example.com/p','2026-11-25T00:00:00Z',({'name':'식품'},),True,api_notices=({'name':'알레르기','desc':'우유 없음'},))
        self.assertEqual(merge_food_evidence({},enrich_product(q))['allergen_status'],'negative_claim_unverified')

    def test_avoidance_alias_match_does_not_create_allergen_declaration(self):
        q=ProductEvidenceRequest('example','https://example.com/p','2026-11-25T00:00:00Z',({'name':'식품'},),True,api_notices=({'name':'원재료명','desc':'우유20%, 설탕80%'},))
        e=enrich_product(q);match=avoidance_matches(e,['milk'])
        self.assertEqual(match['matches'][0]['field'],'ingredients')
        self.assertEqual(e['fields']['allergens']['status'],'not_reported');self.assertIsNone(match['safe_to_use'])

    def test_optional_evidence_permission_does_not_block_food_core(self):
        r=row();r['classification']={'selected_domain':'food','is_food':True,'condition':'new'}
        cfg=config();cfg.update(food_policy='extension_v1',evidence_storage=False)
        with tempfile.TemporaryDirectory() as temp:
            p=FoodDelivery(cfg,Path(temp),transport=Mock())
            self.assertEqual(p.stage(r)['status'],'pending');self.assertEqual(p.pending_count(),1)
    def test_optional_ocr_failure_does_not_block_core(self):
        r=row();cfg=config();cfg.update(food_policy='extension_v1',evidence_storage=True,rights={'allowed_uses':['evidence_storage']})
        with tempfile.TemporaryDirectory() as temp,patch('services.collector.domeggook_live.components.collect',side_effect=RuntimeError('synthetic OCR failure')):
            p=FoodDelivery(cfg,Path(temp),transport=Mock())
            self.assertEqual(p.stage(r)['status'],'pending');self.assertEqual(p.state['totals']['optional_component_extraction_failed'],1)

if __name__=='__main__':unittest.main()
