"""Synthetic canonical drafts only. No private endpoint or HTTP transport exists."""
from urllib.parse import urlsplit

from services.collector.marketplace_live.normalize import money

PROVIDERS = ('bunjang', 'joongna')
HOSTS = {'bunjang': 'm.bunjang.co.kr', 'joongna': 'web.joongna.com'}
CONDITIONS = {'new', 'used', 'new_other_open_box', 'new_with_defects',
              'certified_refurbished', 'seller_refurbished', 'for_parts_or_not_working', 'damaged'}


def blocked(provider):
    if provider not in PROVIDERS:
        raise ValueError('unknown_provider')
    return {'provider': provider, 'status': 'blocked',
            'reason': 'partner_access_storage_reuse_grant_and_API_contract_required',
            'HTTP_requests_this_command': 0, 'backend_requests': 0,
            'live_supported': False, 'mock_supported': True}


def normalize_synthetic(provider, item):
    """This is a proposed partner DTO, NOT a claim about either native API."""
    blocked(provider)
    if item.get('synthetic_only') is not True:
        raise ValueError('synthetic_only_input_required')
    identity = item.get('id')
    if not isinstance(identity, str) or not identity.isdigit():
        raise ValueError('synthetic_native_id_required')
    parsed = urlsplit(item.get('url') or '')
    if item.get('url') and (parsed.scheme != 'https' or parsed.hostname != HOSTS[provider] or parsed.port not in (None,443)
            or parsed.username or parsed.password):
        raise ValueError('approved_product_URL_required')
    condition = item.get('condition') if item.get('condition') in CONDITIONS else None
    sale = item.get('sale_status')
    availability = {'active': 'available', 'sold': 'ended', 'deleted': 'ended', 'inactive': 'ended'}.get(sale)
    result = {'provider': provider, 'source_listing_id': identity, 'variant_key': identity,
              'name': item.get('name'), 'price': money(item['price']) if item.get('price') is not None else None,
              'currency': item.get('currency'), 'seller': item.get('seller'), 'url': item.get('url'),
              'condition': condition, 'sale_status': sale, 'availability': availability,
              'stock_quantity': None, 'synthetic_only': True, 'observation': None,
              'API_contract_ready': False}
    result['missing_fields'] = [field for field in ('name','price','currency','seller','url','condition','availability')
                                if result[field] is None or not str(result[field]).strip()]
    if result['currency'] not in ('KRW',):
        result['missing_fields'].append('approved_currency')
    result['draft_ready'] = not result['missing_fields']
    return result


def bunjang_catalog_mock(row):
    """Official catalog field names, synthetic inputs only, no download code.

    Native catalog does not establish currency, display seller or public URL.
    Missing fields stay missing until an approved partner contract supplies them.
    """
    if row.get('synthetic_only') is not True:
        raise ValueError('synthetic_only_input_required')
    conditions = {'NEW':'new','LIKE_NEW':'used','LIGHTLY_USED':'used',
                  'HEAVILY_USED':'used','USED':'used','DAMAGED':'damaged'}
    item = {'synthetic_only':True, 'id':str(row.get('pid','')), 'name':row.get('name'),
            'price':row.get('price'), 'currency':row.get('currency'), 'seller':row.get('seller_display'),
            'url':row.get('public_url'), 'condition':conditions.get(row.get('condition')),
            'sale_status':{'SELLING':'active','DELETED':'deleted'}.get(row.get('saleStatus'))}
    result = normalize_synthetic('bunjang',item)
    result.update(provider_seller_id=row.get('uid'), native_condition=row.get('condition'),
                  reported_quantity=row.get('quantity'))
    if 'quantity' in row and (type(row['quantity']) is not int or row['quantity'] < 0
                             or row['quantity'] == 0 and item['sale_status'] == 'active'):
        result['missing_fields'].append('quantity_status_review')
        result['draft_ready'] = False
    return result


def fixtures(provider):
    blocked(provider)
    for index, state in enumerate(('active','sold','deleted','inactive','reserved','unknown'), 1):
        yield {'synthetic_only': True, 'id': str(990000+index), 'name': 'SYNTHETIC used item',
               'price': '12000', 'currency': 'KRW', 'seller': 'SYNTHETIC display name',
               'condition': 'used', 'sale_status': state,
               'url': f'https://{HOSTS[provider]}/products/{990000+index}'}
