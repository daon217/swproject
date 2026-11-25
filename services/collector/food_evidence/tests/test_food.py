from datetime import datetime,timezone
import hashlib
import unittest
from services.collector.food_evidence.extract import extract
from services.collector.collector_ops.evidence import EvidenceAdapter
from services.collector.marketplace_live.adapters import Adapter
from services.collector.marketplace_live.tests.fixtures import config,ebay


class FoodTests(unittest.TestCase):
    def extract(self,text,**kwargs):
        return extract(text,source='SYNTHETIC',source_url='https://food.example.test/1',
                       observed_at=datetime.now(timezone.utc).isoformat(),category=kwargs.pop('category','food'),**kwargs)
    def test_reuses_retained_refiner_and_separates_native_text_and_terms(self):
        raw='<p>원재료: 밀, 우유, 설탕</p><p>알레르기: 우유, 대두</p>'
        r=self.extract(raw)
        self.assertEqual(r['raw'],raw);self.assertEqual(r['raw_sha256'],hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(r['ingredients'],['밀','우유','설탕'])
        self.assertEqual(r['allergens_declared'],['milk','soy'])
        self.assertIn('original module not patched',r['implementation'])
        self.assertIsNone(r['safe_to_consume']);self.assertFalse(r['persisted'])
    def test_missing_ingredients_and_allergy_stay_unknown_not_safe(self):
        for text in (None,'맛있는 간식','<img src="https://food.example.test/label.jpg">'):
            r=self.extract(text)
            self.assertIsNone(r['ingredients']);self.assertIsNone(r['allergens_declared'])
            self.assertEqual(r['allergen_status'],'not_reported');self.assertIsNone(r['safe_to_consume'])
    def test_negative_claims_never_become_safe(self):
        for text in ('알레르기: 없음','Allergens: none','알레르기: 우유 무첨가'):
            r=self.extract(text);self.assertEqual(r['allergen_status'],'negative_claim_unverified')
            self.assertIsNone(r['safe_to_consume']);self.assertIsNone(r['allergens_declared'])
    def test_possible_cross_contact_not_conflated_with_declared_contents(self):
        r=self.extract('Allergens: milk\nMay contain: peanuts')
        self.assertEqual(r['allergens_declared'],['milk']);self.assertEqual(r['may_contain'],['peanuts'])
    def test_unknown_labels_preserved_without_fabrication(self):
        r=self.extract('알레르기: 조개류, 특수원료ABC')
        self.assertEqual(r['allergens_declared'],['shellfish'])
        self.assertEqual(r['unmapped_allergen_terms'],['특수원료ABC'])
    def test_multilingual_synonyms_and_added_allergens(self):
        r=self.extract('알레르기: 달걀, Sesame, 花生, 탈지분유 함유')
        self.assertEqual(r['allergens_declared'],['egg','sesame','peanut','milk'])
        self.assertEqual(r['unmapped_allergen_terms'],[])
    def test_group_words_stay_as_text_for_specific_backend_codes(self):
        # 백엔드는 아몬드·연어처럼 개별 코드로 판정한다. 'tree_nut'/'fish'로 뭉개면 아몬드 알레르기 경고가 빠진다.
        r=self.extract('알레르기: 우유, 아몬드, 연어 함유')
        self.assertEqual(r['allergens_declared'],['milk'])
        self.assertEqual(r['unmapped_allergen_terms'],['아몬드','연어 함유'])
    def test_cosmetic_ingredients_not_misclassified_as_food(self):
        r=self.extract('전성분: 정제수, 글리세린',category='cosmetics')
        self.assertEqual(r['status'],'not_food');self.assertIsNone(r['raw'])
    def test_evidence_wrapper_preserves_original_v2_body_and_holds_food_contract(self):
        cfg=config('ebay_browse');row=ebay();at=datetime.now(timezone.utc).isoformat()
        a=EvidenceAdapter(Adapter(cfg,None))
        self.assertEqual(a.normalize(row,at)['observation'],a.adapter.normalize(row,at)['observation'])
        row.update(category='food',description='原文\n원재료: 밀, 설탕\n알레르기: 밀')
        result=a.normalize(row,at)
        self.assertIsNone(result['observation']);self.assertIn('food_contract_required',result['missing_fields'])
        cfg['food_policy']='base_product_only'
        result=a.normalize(row,at)
        self.assertNotIn('food_evidence',result['observation']);self.assertNotIn('category',result['observation'])
        self.assertEqual(result['food_evidence']['allergens_declared'],['wheat'])
    def test_source_script_not_used_as_evidence_and_text_bound_enforced(self):
        r=self.extract('<script>알레르기: 우유</script><p>원재료: 쌀</p>')
        self.assertIsNone(r['allergens_declared']);self.assertEqual(r['ingredients'],['쌀'])
        with self.assertRaises(ValueError):self.extract('a'*200001)
