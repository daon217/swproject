"""Native evidence helpers. Unknown never becomes new/available/zero stock."""
import re
from urllib.parse import urlsplit
from services.collector.marketplace_live.config import stamp
from .policy import url

def price_evidence(raw,currency,currencies,parse):
    code=currency.strip().upper() if isinstance(currency,str) else None
    code=code if code in currencies else None
    info={'raw':raw,'currency_raw':currency,'currency_status':'native_ISO' if code else 'unknown','symbol':None,'errors':[]}
    text=raw.strip() if isinstance(raw,str) else raw
    # Only an explicitly printed ISO code can resolve an otherwise absent code.
    if code is None and isinstance(text,str):
        match=re.fullmatch(r'([A-Z]{3})\s+([0-9][0-9,.]*)|([0-9][0-9,.]*)\s+([A-Z]{3})',text)
        if match:
            iso=match.group(1) or match.group(4)
            if iso in currencies:code=iso;info['currency_status']='native_price_ISO'
    try:amount=parse(raw,code) if raw is not None else None
    except (ValueError,TypeError,ArithmeticError):
        amount=None
        # Preserve a printed amount for diagnostics without assigning a currency.
        match=re.fullmatch(r'([£$€¥₩])\s*([0-9][0-9,.]*)',text) if isinstance(text,str) else None
        if match and code is None:
            info['symbol']=match.group(1)
            try:amount=parse(match.group(2),None)
            except (ValueError,ArithmeticError):pass
        if amount is None:info['errors'].append('invalid_native_price')
    if raw is not None and code is None:info['errors'].append('currency_evidence_required')
    return amount,code,info

def stock_evidence(native,inventory):
    quantity=None;kind='unknown'
    if isinstance(inventory,dict) and type(inventory.get('value')) is int and inventory['value']>=0:
        quantity=inventory['value'];kind='native_inventoryLevel'
    match=re.fullmatch(r'In stock\s*\(\s*(\d+)\s+available\s*\)',str(native),re.I)
    if match:
        stated=int(match.group(1))
        if stated==0:return None,'conflicting_native_stock',None
        if quantity is None:quantity=stated;kind='native_stock_label'
        elif quantity!=stated:return None,'conflicting_native_stock',None
        return quantity,kind,'available' if stated>0 else 'out_of_stock'
    if quantity==0 and str(native).rsplit('/',1)[-1] in ('InStock','LimitedAvailability','available','in stock'):return None,'conflicting_native_stock',None
    return quantity,kind,None

def storefront_evidence(cfg,at):
    host=cfg['allowed_product_hosts'][0]
    base={'kind':'source_origin','domain':host,'legal_seller_verified':False,'accepted_as_seller_identity':False}
    proof=cfg.get('storefront_identity')
    if not proof:return base
    try:
        valid=(proof.get('single_merchant') is True and proof.get('domain')==host and
            urlsplit(url(proof['reference'],host)).hostname==host and stamp(proof['expires_at'])>stamp(at))
    except (ValueError,TypeError,KeyError,AttributeError):valid=False
    if valid:base.update(kind='reviewed_single_merchant_origin',accepted_as_seller_identity=True,reference=proof['reference'])
    return base
