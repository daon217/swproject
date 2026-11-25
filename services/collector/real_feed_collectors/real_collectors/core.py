"""Small portable extraction layer adapted from the retained working feed collectors.

Native merchant fields only. Missing/ambiguous sale units are rejected, never filled.
"""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from urllib.parse import urlsplit

SOURCES = {
    'smartify': ('https://smartify.in/product-feed.xml', {'smartify.in'}, 'https://smartify.in/developers/'),
    'perfume_registry': ('https://perfumeregistry.com/feed.xml', {'perfumeregistry.com', 'www.perfumeregistry.com'}, 'https://perfumeregistry.com/ai'),
    'yappy_kids': ('https://www.yappykids.com/fb.php?lang=en', {'www.yappykids.com'}, 'https://www.yappykids.com/agents'),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def rows(data):
    # Reject external entities/DTD rather than accepting arbitrary XML extensions.
    if re.search(br'<!\s*(DOCTYPE|ENTITY)', data, re.I):
        raise ValueError('DTD/entity XML is unsupported')
    root = ET.fromstring(data)
    for node in root.iter('item'):
        row = {}
        for child in node:
            key = child.tag.split('}')[-1]
            value = child.text or ''
            if key == 'additional_image_link':
                row.setdefault(key, []).append(value)
            elif key in row:
                raise ValueError('Ambiguous repeated feed field: ' + key)
            else:
                row[key] = value
        yield row


def http_url(value):
    if not isinstance(value, str):
        return False
    u = urlsplit(value)
    return u.scheme in ('http', 'https') and bool(u.hostname) and not u.username and not u.password


def details(o, raw=None):
    raw = raw or {}
    image = raw.get('image_link')
    images = ([image] if http_url(image) else []) + [x for x in raw.get('additional_image_link', []) if http_url(x)]
    # Spnid feed brand can identify a private seller. This adapter does not support Spnid.
    return dict(source=o['source'], source_listing_id=o['source_listing_id'],
                observation_key=o['observation_key'], name=o['name'], price=o['price'],
                currency=o['currency'], seller_source=o['source'], url=o['url'],
                image_urls=list(dict.fromkeys(images)), description=raw.get('description') or None,
                category=raw.get('product_type') or raw.get('google_product_category') or None,
                brand=raw.get('brand') or None, variant_key=o['variant_key'],
                options={k: raw[k] for k in ('color', 'size', 'material', 'pattern', 'item_group_id') if raw.get(k)},
                condition=o['condition'], availability=o['availability'], observed_at=o['observed_at'])


def convert(source, row, observed_at):
    if source not in SOURCES:
        raise ValueError('Unsupported source')
    for field in ('id', 'title', 'link', 'price', 'condition', 'availability'):
        if not row.get(field):
            raise ValueError('missing_' + field)
    if not http_url(row['link']) or urlsplit(row['link']).hostname not in SOURCES[source][1]:
        raise ValueError('unexpected_product_host')
    if row['condition'] not in ('new', 'used'):
        raise ValueError('unsupported_condition')
    if row['condition'] == 'new' and re.search(r'\b(unboxed|tester|open[- ]?box|refurbished|renewed|pre[- ]?owned|showroom|ex[- ]display|as[- ]is|used)\b', row['title'], re.I):
        raise ValueError('condition_exception_title')
    state = {'in_stock': 'available', 'in stock': 'available',
             'out_of_stock': 'out_of_stock', 'out of stock': 'out_of_stock'}.get(row['availability'])
    if state is None:
        raise ValueError('unsupported_availability')
    if row.get('item_group_id'):
        raise ValueError('variant_offer_requires_detail')
    if row.get('sale_price_effective_date'):
        raise ValueError('sale_window_requires_review')
    m = re.fullmatch(r'(\d+(?:\.\d+)?) ([A-Z]{3})', row.get('sale_price') or row['price'])
    if not m:
        raise ValueError('invalid_price_currency')
    price, currency = m.groups()
    if not Decimal(price).is_finite():
        raise ValueError('nonfinite_price')
    if source == 'perfume_registry':
        # This feed's item ID is the native SKU, verified by the original sample.
        sku = row['id']
        listing = urlsplit(row['link']).path.rstrip('/').split('/')[-1]
        prefix = 'merchant-feed:'
    else:
        sku, listing = row.get('mpn'), row['id']
        prefix = 'native-feed:' if source == 'smartify' else 'merchant-feed:'
    if not sku:
        raise ValueError('missing_native_unit_identifier')
    o = dict(schema_version=2, source=source, observed_at=observed_at, result='success',
             selected_domain='product', source_listing_id=listing, variant_key=sku,
             condition=row['condition'], name=row['title'], price=price, currency=currency,
             availability=state, url=row['link'],
             field_presence=['name', 'price', 'currency', 'availability', 'url'])
    o['observation_key'] = prefix + digest(json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
    return o


def model_from_file(path):
    # Explicit local model supplied by operator; no imports of backend services/DB.
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location('_collector_contract', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.Observation
