"""Native option codes only. Display names and content hashes never identify offers."""
import copy
import json
import math
import re
from decimal import Decimal, InvalidOperation
from .stable_identity import resolve


def signed_number(value):
    if isinstance(value,bool) or value is None:return None
    try:
        number=Decimal(str(value).replace(',',''))
        if not number.is_finite():return None
        return int(number) if number==int(number) else float(number)
    except (ValueError,InvalidOperation):return None


def decode_options(value):
    if isinstance(value,str):
        try:return json.loads(value)
        except ValueError:return None
    return copy.deepcopy(value) if isinstance(value,dict) else None


def option_offers(row):
    options=row.get('native_options')
    # Missing/empty options are not proof of option absence.
    if not isinstance(options,dict) or options.get('type')!='combination' or not isinstance(options.get('data'),dict) or not options['data']:
        return [],['unconfirmed_option_structure']
    accepted=[];reasons=[]
    for code,option in options['data'].items():
        # Codes are keys returned by API, including leading zeros. No enumeration.
        if not isinstance(code,str) or not re.fullmatch(r'[0-9A-Za-z_:-]{1,120}',code) or not isinstance(option,dict):
            reasons.append('invalid_native_option_code');continue
        delta=signed_number(option.get('domPrice'));stock=signed_number(option.get('qty'))
        if delta is None or stock is None or stock<0 or stock!=int(stock) or str(option.get('dom')) not in ('0','1') or str(option.get('hid')) not in ('0','1','2'):
            reasons.append('incomplete_option_price_stock_or_state');continue
        candidate=copy.deepcopy(row)
        # product_id stays the original listing no; native tuple differentiates options.
        candidate.update(variant_key=code,variant_scope='native_option',option_id=code,
            option_name=option.get('name'),option_price_delta=delta,stock_quantity=int(stock),
            native_option_status={'dom':option['dom'],'hid':option['hid']},
            price=row['price']+delta,unit_price=row['price']+delta)
        candidate['price_conditions'].update(variant_price='selected_native_option',variant_key=code,option_price_delta=delta)
        if candidate['price']<0:
            reasons.append('negative_option_price');continue
        candidate['availability']=('ended' if str(option['hid'])!='0' or str(option['dom'])=='0' or row.get('availability')=='ended'
                                   else 'out_of_stock' if stock==0 else row.get('availability'))
        candidate['stock']={'quantity':int(stock),'status':row.get('stock_status'),'availability':candidate['availability']}
        candidate['option_values']={'native_code':code,'name':option.get('name')}
        path='domeggook.selectOpt(JSON).data['+json.dumps(code)+']'
        candidate['identity_evidence']['variant_key']={'value':code,'path':path,'basis':'native option code; provider option-update arrays use same codes'}
        candidate['evidence']['field_paths'].update(price=path+'.domPrice + price.dome at MOQ',stock_quantity=path+'.qty')
        candidate['native_options']=None
        recalculate_totals(candidate)
        accepted.append(resolve(candidate))
    return accepted,reasons


def recalculate_totals(row):
    price=row.get('unit_price',row.get('price'));moq=row.get('minimum_order_quantity');unit=row.get('purchase_unit')
    quantity=None
    if isinstance(moq,(int,float)) and moq>0 and moq==int(moq):
        quantity=int(moq)
        if isinstance(unit,(int,float)) and unit>0 and unit==int(unit):quantity=math.ceil(quantity/unit)*int(unit)
    row['minimum_purchase_quantity']=quantity
    row['minimum_product_total']=price*quantity if price is not None and quantity is not None else None
    shipping=row.get('shipping_fee');subtotal=row['minimum_product_total']
    row['estimated_minimum_checkout_total']=subtotal+shipping if subtotal is not None and shipping is not None else None
    row['checkout_total_is_exact']=False
    row['checkout_total_basis']='estimate at minimum valid quantity; options, region and delivery conditions apply'
    return row
