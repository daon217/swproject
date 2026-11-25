"""Official list -> detail -> normalization -> bounded live rechecks.

Product payloads remain in RAM while permanent storage rights are unverified.
Only native IDs, request outcomes, checkpoints and aggregate metrics persist.
"""
import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path
from .runtime import PACKAGE,FIELDS,read,now,public_url,FileState
from .progress import save,update
from .product_contract import normalize
from .updates import merge_fields
from .description import parse_view_desc
from .domeggook_open import OpenClient,SafeAPIError,ROOT,list_items
from urllib.parse import urlsplit,urlunsplit,parse_qs


def purchase_url(value,pid):
    if not isinstance(value,str):return None
    p=urlsplit(value)
    if p.scheme not in ('http','https') or p.hostname not in ('domeggook.com','www.domeggook.com') or p.username or p.password or p.port not in (None,80,443):
        raise SafeAPIError('purchase_URL_host_not_verified')
    matched=p.path.rstrip('/')=='/'+pid or (p.path=='/main/item/itemView.php' and parse_qs(p.query).get('no')==[pid])
    if not matched:raise SafeAPIError('purchase_URL_native_ID_mismatch')
    return urlunsplit(('https',p.hostname,p.path,p.query,''))


def numeric(value):
    if isinstance(value,bool):return None
    value=str(value).replace(',','').strip() if value is not None else ''
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value):return None
    amount=float(value)
    return int(amount) if amount.is_integer() else amount


def flag(value):
    if value is True or value=='true':return True
    if value is False or value=='false':return False
    return None


def price_at_moq(value,moq):
    simple=numeric(value)
    if simple is not None:return simple
    tiers=[]
    if isinstance(value,str):
        for piece in value.split('|'):
            parts=piece.split('+')
            if len(parts)!=2 or numeric(parts[0]) is None or numeric(parts[1]) is None:return None
            tiers.append((numeric(parts[0]),numeric(parts[1])))
    eligible=[(q,p) for q,p in tiers if moq is not None and q<=moq]
    return max(eligible)[1] if eligible else None


def normalize_detail(listing,payload,stamp):
    basis=payload.get('basis',{});pid=str(listing.get('no'))
    if not pid.isdigit() or str(basis.get('no'))!=pid:raise SafeAPIError('native_listing_detail_ID_mismatch')
    row=dict.fromkeys(FIELDS);detail=payload.get('detail') or {};qty=payload.get('qty') or {}
    price=payload.get('price') or {};desc=payload.get('desc') or {};thumb=payload.get('thumb') or {}
    moq=numeric(qty.get('domeMoq'));seller=payload.get('seller') or {};deli=payload.get('deli') or {};shipping=deli.get('dome') or {}
    category=payload.get('category') or {};current=category.get('current') or {}
    row.update(source='domeggook',product_id=pid,source_listing_id=pid,variant_key=None,variant_scope='unknown',
        product_name=basis.get('title') or listing.get('title'),price=price_at_moq(price.get('dome'),moq),
        currency='KRW',seller=seller.get('nick') or seller.get('id'),product_url=purchase_url(listing.get('url'),pid),
        image_url=thumb.get('large') or thumb.get('original') or listing.get('thumb'),
        category=current.get('name') if isinstance(current,dict) else None,
        stock_status=basis.get('status'),stock_quantity=numeric(qty.get('inventory')),
        minimum_order_quantity=moq,purchase_unit=numeric(qty.get('domeUnit')),
        manufacturer=detail.get('manufacturer') or None,model=detail.get('model') or None,
        seller_id=str(seller['id']) if seller.get('id') is not None else None,
        collected_at=stamp,updated_at=stamp,last_observed_at=stamp,collection_method='official_Open_API_HTTP',
        storage_permission_status='ephemeral_only_permanent_storage_unverified',
        price_conditions={'quantity':moq,'native_price':price.get('dome'),'variant_price':'not_selected'},
        shipping_conditions={'pay':deli.get('pay'),'type':shipping.get('type'),'table':shipping.get('tbl')},
        native_category=category,product_notices=detail.get('infoDuty'),
        identity_evidence={'product_id':{'value':pid,'path':'domeggook.basis.no'},
            'source_listing_id':{'value':pid,'path':'domeggook.basis.no'}},
        evidence={'mode':'live','observed_at':stamp,'detail_observed_at':stamp,
            'response_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            'field_paths':{'price':'price.dome at qty.domeMoq','stock_quantity':'qty.inventory','stock_status':'basis.status'},
            'currency_basis':'official domestic API price documented in KRW/won'})
    if row['seller'] is not None:row['seller']=str(row['seller'])
    if deli.get('pay')=='무료배송':row['shipping_fee']=0
    elif shipping.get('type')=='고정배송비':row['shipping_fee']=numeric(shipping.get('fee'))
    specs={k:detail[k] for k in ('manufacturer','model','size','weight','country','itemCustomCode') if detail.get(k) not in (None,'',{},[])}
    row['specifications']=specs or None
    raw_options=payload.get('selectOpt');options=None
    row['native_option_state']=('explicit_null' if 'selectOpt' in payload and raw_options is None else 'provided' if 'selectOpt' in payload else 'absent')
    if isinstance(raw_options,str) and raw_options:
        try:options=json.loads(raw_options)
        except ValueError:options=None
    elif isinstance(raw_options,dict):options=copy.deepcopy(raw_options)
    if row['native_option_state']=='provided' and not isinstance(options,dict):row['native_option_state']='unparseable'
    row['native_options']=options
    # Preserve native option data in RAM. Unknown key semantics are never fabricated as variant IDs.
    row['option_identity_status']='native_option_schema_requires_verified_identifier_mapping'
    permitted=flag((desc.get('license') or {}).get('usable'))
    row.update(detail_content_license_usable=permitted,description_html=None,detail_image_urls=[],detail_image_alt={})
    contents=(desc.get('contents') or {}).get('item')
    row['description_source_html']=contents if permitted is True and isinstance(contents,str) and len(contents.encode())<=4_000_000 else None
    if permitted is True and isinstance(contents,str) and contents.strip():
        cleaned=parse_view_desc('<div class="ifrm_prdc_detail">'+contents+'</div>',row.get('product_url'))
        for field in ('description','description_html','detail_image_urls','detail_image_alt'):row[field]=cleaned[field]
    row['detail_content_status']='withheld_by_license' if permitted is not True else 'text' if row['description'] else 'image_only' if row['detail_image_urls'] else 'empty'
    row['content_persisted']=False
    from .domeggook_options import recalculate_totals
    row['unit_price']=row['price']
    recalculate_totals(row)
    if row.get('minimum_purchase_quantity') is not None:
        row['price']=row['unit_price']=price_at_moq(price.get('dome'),row['minimum_purchase_quantity'])
        row['price_conditions']['quantity']=row['minimum_purchase_quantity']
    row['availability']=('available' if row['stock_status']=='판매중' and row['stock_quantity'] is not None and row['stock_quantity']>0
                         else 'out_of_stock' if row['stock_status']=='판매중' and row['stock_quantity']==0
                         else 'ended' if row['stock_status'] in ('기간종료','판매종료') else None)
    row['shipping_conditions']['regional_surcharges']=copy.deepcopy(deli.get('feeExtra'))
    from .classification import classify
    row['classification']=classify(listing,payload)
    row['category_levels']=copy.deepcopy(row['classification']['category_levels'])
    row['is_food']=row['classification']['is_food']
    row['condition']=row['classification']['condition']
    row['region']=row['classification']['region']
    row['service_type']=row['classification']['service_type']
    row['evidence']['field_paths']['classification']='category.parents.elem/category.current; detail.infoDuty; deli.fromOversea'
    from services.collector.product_evidence.identifiers import extract_identifiers
    duties=detail.get('infoDuty') or {};notice_items=duties.get('item') or []
    if isinstance(notice_items,dict):notice_items=[notice_items]
    api_values={k:(detail[n], 'detail.'+n) for k,n in (('manufacturer','manufacturer'),('model_name','model'),('sku','itemCustomCode'),('size','size'),('brand','brand'),('mpn','mpn'),('gtin','gtin'),('model_number','modelNumber'),('color','color')) if detail.get(n) not in (None,'')}
    identifiers=extract_identifiers(api_values=api_values,notices=notice_items,
        html=contents if isinstance(contents,str) else '',html_allowed=permitted is True,product_url=row['product_url'])
    row['product_identifiers']=identifiers
    row['matching_profile']=copy.deepcopy(identifiers['values'])
    # GTIN/SKU are sent via the already supported identifiers list, never made-up IDs.
    native_ids=[{'type':k,'value':v,'source_field':identifiers['evidence'][k]['sources'][0]['source_field'][:64]} for k,v in identifiers['values'].items() if k in ('gtin','mpn','sku')]
    row['matching_profile'].pop('sku',None);row['matching_profile'].pop('gtin',None)
    if native_ids:row['matching_profile']['identifiers']=native_ids[:8]
    row['field_usage']={field:{'storage':'unverified','reuse':'unverified'} for field in row}
    for field in ('description','description_html','description_source_html','detail_image_urls','detail_image_alt'):
        row['field_usage'][field]={'storage':'unverified','reuse':'permitted_by_desc_license' if permitted is True else 'denied' if permitted is False else 'unverified'}
    recalculate_totals(row)
    row['stock']={'quantity':row['stock_quantity'],'status':row['stock_status'],'availability':row['availability']}
    row['option_values']=copy.deepcopy(row['native_options'])
    row['observed_at']=stamp
    for field in ('stock','option_values','observed_at'):row['field_usage'][field]={'storage':'unverified','reuse':'unverified'}
    return normalize(row,'domeggook',require_stable_identity=False)
