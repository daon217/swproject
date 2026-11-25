"""Domeggook native category/condition/shipping evidence; no title-based guesses.

Backend mapping is limited to existing selected_domain and condition fields.
Category codes, hierarchy and region remain local because v2 has no fields for them.
"""
import copy
import re

REFERENCE='https://docs.channel.io/domeggook_api/ko/articles/933abc24'
# Native code/name pairs observed in the provider response, not new backend codes.
ROOTS={'16_00_00_00_00':('식품','food'),
       '01_00_00_00_00':('패션잡화','product'),
       '02_00_00_00_00':('의류/언더웨어','product'),
       '07_00_00_00_00':('화장품','product'),
       '10_00_00_00_00':('문구','product'),
       '12_00_00_00_00':('생활용품','product'),
       '17_00_00_00_00':('디지털/가전','product')}
CODE=re.compile(r'\d{2}(?:_\d{2}){4}')
CONDITIONS={'신품':'new','새상품':'new','새 상품':'new','중고':'used',
            '리퍼':'unknown','리퍼브':'unknown','리퍼상품':'unknown','재생품':'unknown','RefurbishedCondition':'unknown',
            'NewCondition':'new','UsedCondition':'used','new':'new','used':'used'}


def boolean(value):
    if value is True or value=='true':return True
    if value is False or value=='false':return False
    return None


def category_levels(native):
    if not isinstance(native,dict):return [],['native_category_not_reported']
    parents=native.get('parents') or {}
    items=parents.get('elem',[]) if isinstance(parents,dict) else []
    if isinstance(items,dict):items=[items]
    if not isinstance(items,list):return [],['invalid_native_category_parents']
    nodes=items+[native.get('current')];levels={};errors=[]
    for node in nodes:
        if node is None:continue
        if not isinstance(node,dict):errors.append('invalid_native_category_node');continue
        depth=node.get('depth');code=node.get('code');name=node.get('name')
        if (type(depth) is not int or not 1<=depth<=5 or not isinstance(code,str) or not CODE.fullmatch(code)
            or not isinstance(name,str) or not name.strip()):
            errors.append('invalid_native_category_node');continue
        parts=code.split('_')
        if any(v!='00' for v in parts[depth:]) or parts[depth-1]=='00':
            errors.append('native_category_depth_code_mismatch');continue
        value={'depth':depth,'code':code,'name':name}
        if depth in levels and levels[depth]!=value:errors.append('conflicting_native_category_depth')
        levels[depth]=value
    ordered=[levels[d] for d in sorted(levels)]
    if not ordered or ordered[0]['depth']!=1:errors.append('native_root_category_not_reported')
    for previous,current in zip(ordered,ordered[1:]):
        if current['code'].split('_')[:previous['depth']]!=previous['code'].split('_')[:previous['depth']]:
            errors.append('conflicting_native_category_path')
    return ordered,sorted(set(errors))


def classify(listing,payload):
    native=payload.get('category');levels,errors=category_levels(native)
    domain=None;root=levels[0] if levels and levels[0]['depth']==1 else None
    if root and not errors:
        known=ROOTS.get(root['code'])
        if known and root['name']==known[0]:domain=known[1]
        # Baby categories can include food: only the explicit toy branch is non-food.
        elif root['code']=='09_00_00_00_00' and root['name']=='유아동' and any(
            p['code']=='09_03_00_00_00' and p['name']=='완구/매트' for p in levels):domain='product'
        else:errors.append('unreviewed_native_root_category')
    detail=payload.get('detail') or {};notices=detail.get('infoDuty') or {}
    items=notices.get('item',[]) if isinstance(notices,dict) else []
    if isinstance(items,dict):items=[items]
    condition_evidence=[]
    for index,item in enumerate(items if isinstance(items,list) else []):
        if not isinstance(item,dict) or item.get('name') not in ('상품상태','제품상태','상품 상태','제품 상태'):continue
        value=item.get('desc')
        if isinstance(value,str) and value.strip() in CONDITIONS:
            condition_evidence.append({'path':f'detail.infoDuty.item[{index}].desc','raw':value,'value':CONDITIONS[value.strip()]})
    conditions={e['value'] for e in condition_evidence}
    condition=next(iter(conditions)) if len(conditions)==1 else 'unknown'
    if len(conditions)>1:errors.append('conflicting_native_item_condition')
    if not conditions:errors.append('native_new_used_condition_not_reported')
    delivery=payload.get('deli') or {};list_delivery=listing.get('deli') or {}
    detail_flag=boolean(delivery.get('fromOversea'));list_flag=boolean(list_delivery.get('fromOversea'))
    conflict=detail_flag is not None and list_flag is not None and detail_flag!=list_flag
    shipping=None if conflict else detail_flag if detail_flag is not None else list_flag
    region='overseas' if shipping is True else 'domestic' if shipping is False else 'unknown'
    if conflict:errors.append('conflicting_fromOversea')
    elif shipping is None:errors.append('native_shipping_origin_not_reported')
    shipping_path='deli.fromOversea' if detail_flag is not None else 'getItemList.list.item.deli.fromOversea'
    item_state='refurbished' if any(e['raw'].strip() in ('리퍼','리퍼브','리퍼상품','재생품','RefurbishedCondition') for e in condition_evidence) else condition
    from services.collector.product_evidence.catalog import service_classification
    service=service_classification('domeggook',condition,region)
    return {**service,'is_food':True if domain=='food' else False if domain=='product' else None,
        'selected_domain':domain,'condition':condition,'item_state':item_state,'region':region,
        'category_levels':levels,'native_category':copy.deepcopy(native),
        'origin_country_native':detail.get('country'),
        'export_available_native':detail.get('oversea'),
        'shipping_evidence':{'path':shipping_path,'detail_raw':delivery.get('fromOversea'),
            'listing_raw':list_delivery.get('fromOversea'),'scope':'shipping origin, not manufacturer origin'},
        'condition_evidence':condition_evidence,
        'category_evidence':{'path':'category.parents.elem + category.current','root':root},
        'review_reasons':sorted(set(errors)),'reference':REFERENCE,
        'backend_mapping':{'selected_domain':domain,'condition':condition,'category':'matching_profile.category',
            'category_codes':'local_only_no_backend_field','region':'local_only_no_backend_field'}}
