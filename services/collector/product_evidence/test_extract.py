"""Synthetic regressions only; real API/OCR counts are verified separately."""
import unittest
from dataclasses import replace
from unittest.mock import patch
from services.collector.product_evidence.extract import ProductEvidenceRequest,extract_text,enrich_product,avoidance_matches,profile_for
from services.collector.product_evidence.catalog import service_classification

def request(**kw):
    defaults=dict(source='domeggook',product_url='https://domeggook.com/123',observed_at='2026-11-25T00:00:00Z',category_levels=({'name':'의류/언더웨어'},),is_food=False)
    defaults.update(kw);return ProductEvidenceRequest(**defaults)

class ProductEvidenceTests(unittest.TestCase):
    def test_service_default_does_not_assert_condition(self):
        for source,value in [('domeggook','general'),('html_artmu','general'),('bestpen','general'),('11st','general'),('joongna','used'),('bunjang','used'),('ebay','overseas')]:
            result=service_classification(source)
            self.assertEqual((result['service_type'],result['condition']),(value,'unknown'))
        self.assertEqual(service_classification('domeggook','used')['service_type'],'used')
        self.assertEqual(service_classification('domeggook',shipping_region='overseas')['service_type'],'overseas')
    def test_categories_and_native_labels_choose_profile(self):
        for name,value in [('화장품','cosmetics'),('어린이식기','baby'),('일반주방세제','chemical'),('건강기능식품','supplement'),('식품','food')]:
            self.assertEqual(profile_for([{'name':name}]),value)
        self.assertEqual(profile_for([]),'other')
    def test_source_materials_have_percent_and_provenance(self):
        result=extract_text(request(api_notices=({'name':'소재','desc':'면 80%, 폴리에스터 20%'},)))
        field=result['fields']['materials'];self.assertEqual(field['status'],'source_reported')
        self.assertEqual([(x['code'],x['percentage']) for x in field['normalized']],[('cotton','80'),('polyester','20')])
        self.assertEqual(field['sources'][0]['source_field'],'detail.infoDuty.item[0].desc')
    def test_placeholder_is_unknown_and_absence_is_never_safe(self):
        result=extract_text(request(api_notices=({'name':'소재','desc':'상세정보 별도표기'},)))
        self.assertEqual(result['fields']['materials']['status'],'not_reported')
        matched=avoidance_matches(result,['cotton']);self.assertFalse(matched['no_match_means_absent']);self.assertIsNone(matched['safe_to_use'])
    def test_unlicensed_text_and_transaction_notice_are_excluded(self):
        result=extract_text(request(description_html='<p>소재: 면100%</p>',text_use_allowed=False,api_notices=({'name':'소재','desc':'면100%','type':'transaction'},)))
        self.assertEqual(result['fields']['materials']['raw'],[])
    def test_full_text_prevents_ocr(self):
        q=request(description_html='<table><tr><th>소재</th><td>면100%</td></tr><tr><th>주의사항</th><td>단독 세탁</td></tr></table>',text_use_allowed=True)
        with patch('services.collector.food_evidence.ocr.collect_detail_images',side_effect=AssertionError('text must win')):
            result=enrich_product(q,{'enabled':True})
        self.assertEqual(result['ocr_status'],'skipped_text_available')
    def test_negative_claim_and_conflict_require_review(self):
        result=extract_text(request(api_notices=({'name':'소재','desc':'니켈 없음'},{'name':'재질','desc':'면100%'})))
        self.assertEqual(result['fields']['materials']['status'],'conflicting')
        self.assertTrue(result['fields']['materials']['normalized'][0]['negative_claim_unverified'])
    def test_ocr_execution_is_not_semantic_success(self):
        q=request(detail_image_urls=('https://example.com/detail.png',),image_use_allowed=True)
        fake={'status':'ocr_executed','records':[{'text':'선물 추천','confidence':.99}],'raw':'선물 추천','source_image_url':q.detail_image_urls[0],'image_sha256':'a'*64,'engine':'synthetic','OCR_performed':True}
        with patch('services.collector.food_evidence.ocr.collect_detail_images',return_value=fake):result=enrich_product(q,{'enabled':True})
        self.assertTrue(result['ocr_call_success']);self.assertFalse(result['ocr_extraction_success'])
    def test_actual_spaced_table_label_is_parsed_without_inventing_value(self):
        q=request(category_levels=({'name':'어린이식기'},),detail_image_urls=('https://example.com/detail.png',),image_use_allowed=True)
        fake={'status':'ocr_executed','records':[{'text':'재 질 PP','confidence':.98}],'raw':'재 질 PP','source_image_url':q.detail_image_urls[0],'image_sha256':'b'*64,'engine':'synthetic','OCR_performed':True}
        with patch('services.collector.food_evidence.ocr.collect_detail_images',return_value=fake):result=enrich_product(q,{'enabled':True})
        self.assertTrue(result['ocr_extraction_success']);self.assertEqual(result['fields']['materials']['raw'],['PP'])
        self.assertEqual(result['fields']['materials']['normalized'][0]['code'],'polypropylene')
        self.assertEqual(result['fields']['materials']['status'],'ocr_unverified')

if __name__=='__main__':unittest.main()
