"""Shared 15-field validation and seller-specific offer identity."""
import copy
import json
import math
from .runtime import FIELDS,identity,public_url
from .updates import merge_fields,parsed
from .stable_identity import resolve,offer_key,assert_unchanged,IdentityUncertain


def normalize(row,source=None,require_stable_identity=True):
    result=resolve(row,require_complete=require_stable_identity)
    for field in FIELDS:result.setdefault(field,None)
    if source and result.get('source')!=source:raise IdentityUncertain('source_identity_mismatch')
    if not public_url(result.get('product_url')):raise ValueError('purchase_url_invalid')
    if not isinstance(result.get('product_name'),str) or not result['product_name'].strip():raise ValueError('product_name_missing')
    price=result.get('price')
    if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<0:raise ValueError('price_invalid_or_missing')
    currency=result.get('currency')
    if currency is not None and (not isinstance(currency,str) or len(currency)!=3 or not currency.isalpha() or currency!=currency.upper()):raise ValueError('currency_invalid')
    if result['image_url'] is not None and not public_url(result['image_url']):raise ValueError('image_url_invalid')
    if result['seller'] is not None and (not isinstance(result['seller'],str) or not result['seller'].strip()):raise ValueError('seller_invalid')
    evidence=result.get('evidence') or {}
    for field in ('description','specifications'):
        if result.get(field) and not (result.get('field_evidence',{}).get(field) or evidence.get('detail_sha256') or evidence.get('response_sha256')):
            raise ValueError('detail_field_without_response_evidence')
    for field in ('collected_at','updated_at'):
        result.setdefault(field,None)
        if result[field] is not None and not parsed(result[field]):raise ValueError('invalid_observation_time')
    result.setdefault('collection_method','unknown')
    result.setdefault('storage_permission_status','unverified')
    result['detail_status']='complete' if result['description'] and result['specifications'] else 'partial' if result['description'] or result['specifications'] else 'listing_only'
    return result


def merge_offer(previous,incoming):
    incoming=normalize(incoming)
    if previous:
        previous=normalize(previous);assert_unchanged(previous,incoming)
    mutable=('price','currency','description','specifications','image_url','stock_status','availability','in_stock','stock_quantity',
             'description_html','detail_image_urls','detail_image_alt','excluded_detail_images','view_desc_documents')
    merged,operation,changed=merge_fields(previous,incoming,mutable)
    if previous:
        # URL/name/seller labels are observations, never identity keys or merge hints.
        merged['latest_observed_product_url']=incoming.get('product_url')
        merged['latest_observed_product_name']=incoming.get('product_name')
        for field in ('source','product_id','source_listing_id','variant_key'):
            merged[field]=previous[field]
    return merged,operation,changed
