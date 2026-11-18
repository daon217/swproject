"""Strict field validation added around the original JSON extractor."""
import re
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qs, unquote

PRODUCT_HOSTS = frozenset({'www.11st.co.kr', 'm.11st.co.kr'})
IMAGE_HOSTS = frozenset({'cdn.011st.com', 'image.11st.co.kr'})


def price(value):
    # Do not strip arbitrary characters, truncate floats, or coerce booleans.
    if type(value) is int:
        return value if value >= 0 else None
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not re.fullmatch(r'(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)', value):
        return None
    try:
        return int(value.replace(',', ''))
    except ValueError:
        return None


def native_id(value):
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise ValueError('invalid_native_identifier')
    return value


def safe_url(value, *, image=False, listing_id=None):
    if not isinstance(value, str) or not value or any(ord(c) <= 32 for c in value) or '\\' in value:
        raise ValueError('invalid_url')
    value = urljoin('https://www.11st.co.kr', value)
    try:
        parsed = urlsplit(value)
        allowed = IMAGE_HOSTS if image else PRODUCT_HOSTS
        if (parsed.scheme != 'https' or parsed.hostname not in allowed or
                parsed.username is not None or parsed.password is not None or
                parsed.port not in (None, 443)):
            raise ValueError('unapproved_url_origin')
        if not parsed.path or parsed.path == '/':
            raise ValueError('missing_url_path')
        if not image:
            match = re.fullmatch(r'/products/([A-Za-z0-9_-]+)/?', parsed.path)
            if match:
                found = match.group(1)
            elif parsed.path == '/product/SellerProductDetail.tmall':
                ids = parse_qs(parsed.query).get('prdNo', [])
                if len(ids) != 1:
                    raise ValueError('ambiguous_url_identifier')
                found = ids[0]
            else:
                raise ValueError('unapproved_product_path')
            if listing_id is not None and found != listing_id:
                raise ValueError('url_native_identifier_mismatch')
        # Preserve native option query parameters; strip fragments only.
        if any(ord(c) < 32 for c in unquote(value)):
            raise ValueError('encoded_control_in_url')
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ''))
    except (ValueError, UnicodeError):
        raise ValueError('invalid_or_unapproved_url') from None
