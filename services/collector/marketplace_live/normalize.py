"""Native values only; an incomplete result stays in RAM and is not submitted."""
import hashlib
import json
import re
from decimal import Decimal
from urllib.parse import urlsplit
from services.collector.domeggook_live.domeggook_backend_contract import Observation
from .vendor.yes24_native import native_observation
from .ebay_fields import condition_evidence, availability_evidence

def money(value):
    if isinstance(value,bool) or value is None:raise ValueError('native_price_required')
    result=Decimal(str(value))
    if not result.is_finite() or result<0:raise ValueError('invalid_native_price')
    return str(result)

def validate_body(body,cfg):
    url=urlsplit(body['url'])
    if url.scheme!='https' or url.port not in (None,443):raise ValueError('HTTPS_product_URL_required')
    Observation.model_validate(body,context={'hosts':cfg['allowed_product_hosts'],'currencies':cfg['currencies']})
    if len(json.dumps(body,ensure_ascii=False).encode())>65536:raise ValueError('observation_too_large')
    return body

def finish(source,values,seller,raw_status,at,cfg):
    missing=[k for k in ('source_listing_id','variant_key','name','price','currency','url','condition','availability')
             if values.get(k) is None or values.get(k)=='']
    result={'source':source,'product_number':values.get('source_listing_id'),'name':values.get('name'),
            'price':values.get('price'),'currency':values.get('currency'),'seller':seller,'url':values.get('url'),
            'condition':values.get('condition'),'availability':values.get('availability'),
            'native_status':raw_status,'missing_fields':missing,'observation':None}
    if missing:return result
    body=dict(schema_version=2,source=source,observed_at=at,result='success',selected_domain='product',**values)
    body['field_presence']=sorted(k for k in ('name','price','currency','availability','url') if k in body)
    body['observation_key']=source+':'+hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    result['observation']=validate_body(body,cfg)
    return result

def yes24(item,at,cfg):
    # Reuse the earlier strict v2 normalizer; do not reuse its Product float mapper.
    body,missing=native_observation(item,at)
    result={'source':'yes24_api','product_number':str(item.get('itemId') or ''),'name':item.get('title'),
            'price':money(item['salePrice']) if item.get('salePrice') is not None else None,
            'currency':item.get('currency'),'seller':item.get('seller'),'url':item.get('link'),
            'condition':item.get('condition'),'availability':item.get('availability'),
            'native_status':item.get('itemStatus'),'missing_fields':missing,'observation':None}
    if body:result['observation']=validate_body(body,cfg)
    return result

def ebay(item,at,cfg):
    ident=item.get('itemId','')
    if not isinstance(ident,str) or not re.fullmatch(r'v1\|\d+\|\d+',ident):raise ValueError('native_ebay_item_id_required')
    condition, condition_info = condition_evidence(item)
    state, stock_info = availability_evidence(item,at)
    if 'FIXED_PRICE' not in item.get('buyingOptions',[]):raise ValueError('fixed_price_offer_required')
    price=item.get('price') or {}
    result = finish('ebay_browse',dict(source_listing_id=ident.split('|')[1],variant_key=ident,
        name=item.get('title'),price=money(price['value']) if 'value' in price else None,
        currency=price.get('currency'),url=item.get('itemWebUrl'),condition=condition,availability=state),
        (item.get('seller') or {}).get('username'),item.get('condition'),at,cfg)
    result.update(condition_info)
    result.update(stock_info)
    return result

def shopping(item,at,cfg):
    product=item.get('product_id');seller=item.get('seller');url=item.get('link')
    if product is None or isinstance(product,bool):raise ValueError('google_product_id_required')
    if not isinstance(seller,str) or not seller.strip():raise ValueError('native_merchant_required')
    parsed=urlsplit(url or '')
    if parsed.scheme!='https' or parsed.hostname not in cfg['allowed_product_hosts'] or parsed.username or parsed.password:
        raise ValueError('direct_approved_merchant_URL_required')
    # The Google catalogue ID is not a merchant SKU. Keep offers distinct by
    # merchant + original merchant URL; do not conflate retailers of one product.
    offer=hashlib.sha256(json.dumps([seller,url],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    condition=item.get('condition') if item.get('condition') in ('new','used') else None
    availability=item.get('availability') if item.get('availability') in ('available','out_of_stock','ended') else None
    return finish('searchapi_google_shopping',dict(source_listing_id=str(product),variant_key='merchant-url:'+offer,
        name=item.get('title'),price=money(item['extracted_price']) if item.get('extracted_price') is not None else None,
        currency=item.get('currency'),url=url,condition=condition,availability=availability),seller,
        item.get('condition'),at,cfg)
