"""Clearly synthetic observations; never derives values from live crawler rows."""
from datetime import datetime,timezone,timedelta
import copy

def row(stamp=None,price=1000,quantity=10):
    stamp=stamp or (datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
    pid='TEST-KKULPICK-001';variant='TEST-OPT-00'
    return {'source':'domeggook_test','product_id':pid,'source_listing_id':pid,'variant_key':variant,
        'variant_scope':'native_option','test_data':True,'product_name':'SYNTHETIC 꿀픽 테스트 상품',
        'product_url':'https://store.example.test/TEST-KKULPICK-001','unit_price':price,'price':price,'currency':'KRW',
        'availability':'available' if quantity else 'out_of_stock','stock_quantity':quantity,
        'stock':{'quantity':quantity,'availability':'available' if quantity else 'out_of_stock'},
        'minimum_order_quantity':2,'minimum_product_total':price*2,'estimated_minimum_checkout_total':price*2+3000,
        'shipping_fee':3000,'detail_content_license_usable':False,'description':None,
        'observed_at':stamp,'last_observed_at':stamp,'collected_at':stamp,'updated_at':stamp,
        'collection_method':'synthetic_fixture','evidence':{'mode':'synthetic'},
        'identity_evidence':{key:{'value':value,'path':'SYNTHETIC.fixture.'+key} for key,value in
            [('product_id',pid),('source_listing_id',pid),('variant_key',variant)]}}

def config(base_url='http://127.0.0.1:18765'):
    return {'backend_enabled':True,'backend_owner_approved':True,'price_semantics_confirmed':False,'storage_grants':{},
        'backend_delivery':{'mode':'synthetic_test','synthetic_test_approved':True,'base_url':base_url,
            'selected_domain':'product','condition':'new','allowed_product_hosts':['store.example.test'],
            'max_requests_per_flush':10,'max_attempts':5,'retry_base_seconds':5,'max_pending':5000}}
