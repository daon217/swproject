"""Portable adaptation of domestic23.elevenst_parser, using the original extractor."""
import json
from datetime import datetime
from .extractor import _product_items, _candidate_from_item, _first_text, _first_value
from .validation import native_id, safe_url, price

MAX_BYTES = 4_000_000
ID_FIELDS = ('id', 'productNo', 'productId', 'prdNo', 'goodsNo', 'itemId')
OPTION_FIELDS = ('optionId', 'optionNo', 'variantId')


class SchemaChanged(ValueError):
    pass


def _payload(body):
    if not isinstance(body, str) or len(body.encode('utf-8')) > MAX_BYTES:
        raise SchemaChanged('response_size_limit')
    try:
        return json.loads(body)
    except (ValueError, RecursionError):
        raise SchemaChanged('expected_JSON_not_HTML') from None


def _stamp(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('invalid_observation_time')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError()
    except ValueError:
        raise ValueError('invalid_observation_time') from None
    return value


def _one_id(native, fields, required=True):
    values = [(key, native_id(native[key])) for key in fields if native.get(key) not in (None, '')]
    if not values:
        if required:
            raise ValueError('native_identifier_missing')
        return None, None
    if len({value for _, value in values}) != 1:
        raise ValueError('conflicting_native_identifiers')
    return values[0]


def _normalize(native, path, observed_at=None, *, archive=False):
    field, pid = _one_id(native, ID_FIELDS)
    option_field, option = _one_id(native, OPTION_FIELDS, required=False)
    candidate = _candidate_from_item(native, pid)
    if not candidate.product_name or candidate.price is None or candidate.price <= 0:
        raise ValueError('required_name_or_positive_price_missing')
    proof = {f: {'value': pid, 'path': path + '.' + field} for f in ('product_id', 'source_listing_id')}
    scope = 'unknown'
    if option is not None:
        proof['variant_key'] = {'value': option, 'path': path + '.' + option_field}
        scope = 'confirmed_option'
    elif not archive and (native.get('hasOptions') is False or native.get('optionYn') == 'N') and native.get('options') == []:
        scope = 'confirmed_none'
        proof['variants'] = {'value': [], 'path': path + '.options'}
    # Missing/unknown currency stays unknown. KRW is never inferred from a hostname.
    currency = _first_text(native, 'currency')
    if currency is not None and currency not in ('KRW', 'USD', 'JPY', 'EUR'):
        raise ValueError('currency_invalid')
    row = dict(
        source='elevenst', product_id=pid, source_listing_id=pid, variant_key=option,
        variant_scope=scope, identity_evidence=proof,
        identity_status='quarantine_required' if scope == 'unknown' else 'verified_native_tuple',
        product_name=candidate.product_name, price=candidate.price, unit_price=candidate.price,
        currency=currency,
        product_url=safe_url(candidate.product_url, listing_id=pid),
        image_url=safe_url(candidate.image_url, image=True),
        seller=_first_text(native, 'seller', 'sellerName', 'storeName', 'mallName'),
        category=_first_text(native, 'categoryName', 'category'),
        brand=_first_text(native, 'brandName'), description=None, specifications=None,
        rating=None, rating_scale=None, review_count=None, condition=None, shipping_fee=None,
        observed_at=_stamp(observed_at), collected_at=observed_at, updated_at=observed_at,
        collection_method='archived_extracted_listing' if archive else 'elevenst_JSON_offline',
        storage_permission_status='unverified', reuse_permission_status='unverified',
        collection_status='offline_replay', detail_status='listing_only',
    )
    row['price_field'] = next(k for k in ('finalPrc', 'salePrice', 'price', 'finalPrice', 'displayPrice', 'selPrc')
                              if (price(_first_value(native, k)) or 0) > 0)
    row['price_conditions'] = 'Final price eligibility/discount conditions are unverified; checkout total is unknown.'
    row['evidence'] = {'mode': 'archive', 'observed_at': observed_at,
                       'field_paths': {'price': path + '.' + row['price_field']},
                       'raw_internal_response_available': not archive}
    return row


def _parse_items(items, observed_at=None, *, archive=False):
    rows, rejected, seen = [], [], set()
    duplicates = 0
    for index, native in enumerate(items):
        try:
            if not isinstance(native, dict):
                raise ValueError('invalid_item_shape')
            row = _normalize(native, f'items[{index}]', observed_at if not archive else native.get('_observed_at'), archive=archive)
        except ValueError as error:
            # No product content or input URL in errors/logs/checkpoints.
            rejected.append({'index': index, 'reason': str(error)})
            continue
        key = (row['source_listing_id'], row['variant_key'])
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        rows.append(row)
    return rows, {'rejected': rejected, 'duplicate_items': duplicates}


def parse_listing(body, observed_at=None):
    payload = _payload(body)
    if not isinstance(payload, dict):
        raise SchemaChanged('unexpected_root_shape')
    _stamp(observed_at)
    try:
        items = _product_items(payload)
    except RecursionError:
        raise SchemaChanged('JSON_nesting_limit') from None
    if not items:
        # Traverse only containers to distinguish a legitimate empty result from schema drift.
        def empty(node):
            if isinstance(node, dict):
                return any(k in ('products', 'items') and v == [] or empty(v) for k, v in node.items())
            if isinstance(node, list):
                return any(empty(v) for v in node)
            return False
        if not empty(payload):
            raise SchemaChanged('product_array_structure_changed')
    rows, meta = _parse_items(items, observed_at)
    container = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    pagination = container.get('pagination', {})
    if not isinstance(pagination, dict):
        raise SchemaChanged('pagination_shape_changed')
    next_page = pagination.get('nextPageNo')
    page = pagination.get('pageNo')
    if any(v is not None and (type(v) is not int or v < 1) for v in (page, next_page)):
        raise SchemaChanged('invalid_page_number')
    if pagination.get('hasMore') is True and (next_page is None or page is not None and next_page <= page):
        raise SchemaChanged('non_advancing_pagination')
    meta.update(native_page=page, next_page=next_page if pagination.get('hasMore') is True else None)
    return rows, meta


def parse_snapshot(body):
    """Replay extracted local records; never claim they are saved internal API JSON."""
    payload = _payload(body)
    rows = payload if isinstance(payload, list) else payload.get('products') if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise SchemaChanged('archived_record_array_changed')
    items = []
    for row in rows:
        if not isinstance(row, dict) or row.get('source') != 'elevenst':
            continue
        item = dict(id=row.get('source_listing_id') or row.get('product_id'), title=row.get('product_name'),
                    price=row.get('price'), linkUrl=row.get('product_url'), imageUrl=row.get('image_url'),
                    seller=row.get('seller'), categoryName=row.get('category'), currency=row.get('currency'),
                    _observed_at=row.get('observed_at') or row.get('collected_at'))
        if row.get('product_id') is not None and row.get('source_listing_id') is not None and str(row['product_id']) != str(row['source_listing_id']):
            item['productId'] = row['product_id']
        proof = (row.get('identity_evidence') or {}).get('variant_key') or {}
        variant = row.get('variant_key')
        if variant is not None and proof.get('value') == variant and proof.get('path'):
            item['optionId'] = variant
        items.append(item)
    result, meta = _parse_items(items, archive=True)
    meta.update(native_page=None, next_page=None, snapshot_elevenst_rows=len(items))
    return result, meta
