"""Synthetic data only; extra native fields below are NOT live API evidence."""
import copy
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock

def config(source='yes24_api'):
    sources=json.loads((Path(__file__).parents[1]/'config.example.json').read_text(encoding='utf-8'))['sources']
    cfg=next(c for c in sources if c['source']==source)
    cfg.update(enabled=True,backend_enabled=True,backend_owner_approved=True,price_semantics_confirmed=True)
    cfg['rights'].update(reference='SYNTHETIC-provider-grant',expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
                         allowed_uses=['lookup','systematic_collection','storage','reuse'],exception_agreement_reference='SYNTHETIC-contract')
    cfg['backend_delivery']['base_url']='https://team.example.test'
    if source=='searchapi_google_shopping':cfg.update(max_units_per_month=10,cost_per_request='0.001',max_cost_per_month='0.010')
    return cfg

def yes24(complete=True):
    item={'itemId':12345678,'title':'SYNTHETIC book','salePrice':29700,'itemStatus':'판매중',
          'link':'https://www.yes24.com/product/goods/12345678'}
    if complete:item.update(currency='KRW',sku='SYNTHETIC-SKU',condition='new',availability='available',seller='SYNTHETIC seller')
    return item

def ebay():return {'itemId':'v1|123456789|0','title':'SYNTHETIC fixed offer','price':{'value':'12.3400','currency':'USD'},
    'conditionId':'1000','condition':'New','buyingOptions':['FIXED_PRICE'],'itemWebUrl':'https://www.ebay.com/itm/123456789',
    'estimatedAvailabilities':[{'estimatedAvailabilityStatus':'IN_STOCK'}],'seller':{'username':'SYNTHETIC merchant'}}

def shopping(complete=True):
    item={'product_id':'12345','title':'SYNTHETIC shopping offer','price':'$12.34','extracted_price':'12.34',
          'link':'https://merchant.example.test/product/123','seller':'SYNTHETIC merchant'}
    if complete:item.update(currency='USD',condition='new',availability='available')
    return item

def response(body=None,status=200,headers=None):
    r=Mock(status_code=status,headers=headers or {})
    raw=json.dumps(body if body is not None else {}).encode()
    r.iter_content.return_value=[raw]
    return r
