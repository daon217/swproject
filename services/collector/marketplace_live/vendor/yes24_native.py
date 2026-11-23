"""Reused native_observation, unchanged; see PROVENANCE.json."""
from decimal import Decimal, InvalidOperation
import hashlib,json
from urllib.parse import urlsplit

def native_observation(row, observed_at):
    """Strict v2 gate: existing generic Product defaults are deliberately bypassed.

    YES24 title/salePrice/link/itemId map from official search fields. Native
    currency/sku/condition/availability must exist in the supplied evidence;
    an actual search response may legitimately fail this gate.
    """
    missing = []
    identity = str(row.get('itemId') or '').strip()
    name = row.get('title')
    url = row.get('link')
    variant = row.get('sku')
    condition = row.get('condition')
    stock = row.get('availability')
    currency = row.get('currency')
    if not identity or len(identity) > 180: missing.append('source_listing_id')
    if not isinstance(name, str) or not name.strip(): missing.append('name')
    if not isinstance(variant, str) or not variant.strip() or len(variant) > 180: missing.append('variant_key')
    if condition not in ('new', 'used'): missing.append('condition')
    if stock not in ('available', 'out_of_stock', 'ended'): missing.append('availability')
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isascii() or not currency.isupper() or not currency.isalpha(): missing.append('currency')
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        if not parsed or parsed.scheme != 'https' or parsed.hostname != 'www.yes24.com' or parsed.username or parsed.password or parsed.port not in (None,443): missing.append('url')
    except ValueError:
        missing.append('url')
    price = row.get('salePrice')
    try:
        if isinstance(price, bool) or not isinstance(price, (str, int)):
            raise ValueError('Avoid binary float or missing money')
        money = Decimal(str(price))
        if not money.is_finite() or money < 0: raise ValueError('Invalid price')
        _, digits, exponent = money.as_tuple()
        if max(-exponent,0)>4 or max(len(digits)+exponent,len(digits))>20: raise ValueError('Money exceeds model bounds')
    except (ValueError, InvalidOperation):
        missing.append('price')
    if missing: return None, sorted(set(missing))
    body = dict(schema_version=2, source='yes24_api', observed_at=observed_at,
                result='success', selected_domain='product', source_listing_id=identity,
                variant_key=variant, condition=condition, name=name, price=str(price),
                currency=currency, availability=stock, url=url,
                field_presence=['name','price','currency','availability','url'])
    body['observation_key'] = 'native:' + hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return body, []
