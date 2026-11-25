"""Serper Shopping native projection; no inference of stock or condition."""
import hashlib
import json
import re
from urllib.parse import urlsplit
from .normalize import finish,money

SOURCE='serper_google_shopping'
ENDPOINT='https://google.serper.dev/shopping'

def price(value,currency=None):
    if value is None or isinstance(value,bool):return None,currency
    if not isinstance(value,str):return money(value),currency
    text=value.strip()
    if not text:return None,currency
    unit=re.match(r'^(USD|EUR|GBP|KRW|JPY|AUD|CAD|CNY)\s*',text)
    if unit:
        if currency and currency!=unit[1]:raise ValueError('conflicting_price_currency')
        currency=unit[1];text=text[unit.end():]
    else:
        for mark,code in (('US$','USD'),('A$','AUD'),('C$','CAD'),('€','EUR'),('£','GBP'),('₩','KRW')):
            if text.startswith(mark):
                if currency and currency!=code:raise ValueError('conflicting_price_currency')
                currency=code;text=text[len(mark):].strip();break
        if text.startswith('$'):
            if currency and currency not in ('USD','AUD','CAD','NZD'):raise ValueError('conflicting_price_currency')
            text=text[1:].strip()  # '$' alone does not establish USD.
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,4})?',text):return None,currency
    return money(text.replace(',','')),currency

def normalize(row,at,cfg):
    ident=row.get('productId');seller=row.get('source');url=row.get('link')
    parsed=urlsplit(url or '')
    if parsed.scheme!='https' or parsed.hostname not in cfg['allowed_product_hosts'] or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('direct_approved_merchant_URL_required')
    amount,currency=price(row.get('price'),row.get('currency'))
    if currency not in cfg['currencies']:currency=None
    condition=row.get('condition')
    condition=condition.lower() if isinstance(condition,str) else None
    if condition not in ('new','used'):condition=None
    availability={'available':'available','in_stock':'available','In stock':'available',
                  'out_of_stock':'out_of_stock','Out of stock':'out_of_stock','ended':'ended'}.get(row.get('availability'))
    # Google productId identifies the catalogue, not the seller's SKU.
    variant=None
    if isinstance(seller,str) and seller.strip() and isinstance(url,str) and url:
        variant='merchant-url:'+hashlib.sha256(json.dumps([seller,url],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    if ident is not None and (isinstance(ident,bool) or not isinstance(ident,(int,str)) or not str(ident).strip()):ident=None
    return finish(SOURCE,dict(source_listing_id=str(ident) if ident is not None else None,variant_key=variant,
        name=row.get('title'),price=amount,currency=currency,url=url,condition=condition,availability=availability),
        seller,row.get('condition'),at,cfg)
