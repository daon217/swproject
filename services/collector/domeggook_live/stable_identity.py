"""Native identity is immutable. No title/URL/price hash or default option IDs."""
import copy
import hashlib
import json
from functools import lru_cache
from urllib.parse import urlsplit,parse_qs
from .runtime import PACKAGE,STATE_ROOT,read,identity,now
from .progress import save

D=STATE_ROOT
MANIFEST=D/'native_identity_manifest.json'
FROZEN=('source','product_id','source_listing_id','variant_key','source_product_id','seller_product_id','seller_id','option_id','item_id')


class IdentityUncertain(ValueError):pass


def legacy_key(row):
    source=row.get('source');pid=row.get('product_id')
    if not isinstance(source,str) or not source or not isinstance(pid,str) or not pid:
        raise IdentityUncertain('native_source_or_existing_product_id_missing')
    return json.dumps([source,pid],ensure_ascii=False,separators=(',',':'))


def ensure_manifest():
    # Optional local-only legacy bindings; never invent or upload a product dataset.
    if MANIFEST.exists():return read(MANIFEST)
    return {'bindings':{},'original_count':0}


def proof(row,field,value):
    entry=(row.get('identity_evidence') or {}).get(field)
    return isinstance(entry,dict) and entry.get('value')==value and isinstance(entry.get('path'),str) and bool(entry['path'])


def resolve(row,require_complete=True):
    result=copy.deepcopy(row);key=legacy_key(result);binding=ensure_manifest()['bindings'].get(key)
    if binding:
        for field,value in binding['native_fields'].items():
            if field in result and result[field]!=value:raise IdentityUncertain('existing_native_identifier_changed:'+field)
        for field in ('source_listing_id','variant_key'):
            previous=binding[field]
            if field in result and result[field]!=previous:raise IdentityUncertain('original_native_tuple_not_confirmed_or_changed:'+field)
            result.setdefault(field,previous)
        verified=binding['status']=='verified_native_tuple'
    else:
        sid=result.get('source_listing_id');variant=result.get('variant_key')
        verified=isinstance(sid,str) and bool(sid) and proof(result,'source_listing_id',sid) and proof(result,'product_id',result['product_id'])
        if variant is None:
            # Native absence can be represented by null only with explicit evidence;
            # lack of an option field is not evidence that a product has no variants.
            variants=(result.get('identity_evidence') or {}).get('variants')
            verified=verified and result.get('variant_scope')=='confirmed_none' and isinstance(variants,dict) and variants.get('value')==[] and bool(variants.get('path'))
        else:verified=verified and isinstance(variant,str) and bool(variant) and proof(result,'variant_key',variant)
    if require_complete and not verified:raise IdentityUncertain('native_listing_or_variant_identity_unconfirmed')
    result['identity_status']='verified_native_tuple' if verified else 'quarantine_required'
    return result


def native_tuple(row):
    resolved=resolve(row)
    return resolved['source'],resolved['source_listing_id'],resolved.get('variant_key')


def offer_key(row):return json.dumps(native_tuple(row),ensure_ascii=False,separators=(',',':'))


def original_for(row):
    resolved=resolve(row);binding=ensure_manifest()['bindings'].get(legacy_key(resolved))
    if binding and binding['status']=='verified_native_tuple':return resolve(binding['original_record'])
    return None


def assert_unchanged(previous,incoming):
    if native_tuple(previous)!=native_tuple(incoming):raise IdentityUncertain('native_tuple_changed')
    for field in FROZEN:
        if field in previous and field in incoming and previous[field]!=incoming[field]:raise IdentityUncertain('immutable_native_identifier_changed:'+field)


def carry_identity(previous,incoming):
    result=copy.deepcopy(incoming)
    for field in FROZEN:
        if field not in previous:continue
        if field in result and result[field]!=previous[field]:raise IdentityUncertain('detail_native_identifier_changed:'+field)
        result[field]=copy.deepcopy(previous[field])
    for field in ('identity_evidence','variant_scope'):
        if field in previous:result.setdefault(field,copy.deepcopy(previous[field]))
    assert_unchanged(previous,result)
    return result
