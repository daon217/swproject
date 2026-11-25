"""Synthetic classification contract regressions; never counted as actual API products."""
import copy
import unittest
from datetime import datetime,timezone
from ..classification import classify
from ..domeggook_pipeline import normalize_detail
from ..domeggook_options import option_offers
from .fixtures import fixture


def response(root='16',name='식품',condition=None,foreign='false'):
    listing,payload=fixture()
    payload['category']={'parents':{'elem':[{'name':name,'code':root+'_00_00_00_00','depth':1},
        {'name':'중분류','code':root+'_03_00_00_00','depth':2}]},
        'current':{'name':'소분류','code':root+'_03_12_00_00','depth':3}}
    payload['deli']['fromOversea']=foreign
    payload['detail'].update(country='수입산_중국',oversea='true')
    if condition is not None:payload['detail']['infoDuty']={'item':[{'name':'상품상태','desc':condition}]}
    return listing,payload


class ClassificationTests(unittest.TestCase):
    def test_food_condition_and_shipping_are_independent(self):
        listing,payload=response('17','디지털/가전','중고','true')
        result=classify(listing,payload)
        self.assertIs(result['is_food'],False)
        self.assertEqual((result['condition'],result['region']),('used','overseas'))
        listing,payload=response('16','식품','새상품','true')
        result=classify(listing,payload)
        self.assertIs(result['is_food'],True)
        self.assertEqual((result['condition'],result['region']),('new','overseas'))

    def test_imported_origin_and_export_permission_do_not_mean_overseas_shipping(self):
        listing,payload=response();original=copy.deepcopy(payload)
        result=classify(listing,payload)
        self.assertEqual(result['region'],'domestic')
        self.assertEqual(result['condition'],'unknown')
        self.assertEqual(result['native_category'],original['category'])
        self.assertEqual([x['depth'] for x in result['category_levels']],[1,2,3])
        self.assertEqual(payload,original)
        payload['deli'].pop('fromOversea')
        self.assertEqual(classify(listing,payload)['region'],'unknown')

    def test_missing_unreviewed_and_conflicting_categories_are_held(self):
        listing,payload=response();payload.pop('category')
        payload['basis']['title']='과자 새상품 해외 중고'
        self.assertIsNone(classify(listing,payload)['selected_domain'])
        self.assertEqual(classify(listing,payload)['condition'],'unknown')
        listing,payload=response('99','새 분류')
        self.assertIsNone(classify(listing,payload)['selected_domain'])
        listing,payload=response();payload['category']['current']['code']='17_03_12_00_00'
        self.assertIsNone(classify(listing,payload)['selected_domain'])

    def test_food_words_in_nonfood_titles_and_ambiguous_baby_root(self):
        listing,payload=response('12','생활용품');payload['basis']['title']='과자 포장'
        self.assertIs(classify(listing,payload)['is_food'],False)
        listing,payload=response('09','유아동')
        self.assertIsNone(classify(listing,payload)['is_food'])

    def test_conflicting_shipping_flags_are_unknown(self):
        listing,payload=response();listing['deli']={'fromOversea':'true'}
        self.assertEqual(classify(listing,payload)['region'],'unknown')

    def test_only_explicit_null_uses_backend_listing_default(self):
        listing,payload=response();payload['selectOpt']=None
        row=normalize_detail(listing,payload,datetime.now(timezone.utc).isoformat())
        offers,reasons=option_offers(row)
        self.assertFalse(reasons);self.assertEqual(offers[0]['variant_key'],'default')
        self.assertNotIn('option_id',offers[0]);self.assertIsNone(row['variant_key'])
        for mode in ('missing','malformed'):
            candidate=copy.deepcopy(payload)
            if mode=='missing':candidate.pop('selectOpt')
            else:candidate['selectOpt']='{broken'
            row=normalize_detail(listing,candidate,datetime.now(timezone.utc).isoformat())
            self.assertFalse(option_offers(row)[0])
