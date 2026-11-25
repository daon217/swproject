"""Backend-test contract  b51ffdc (extensions/freshness); no backend imports or SQL."""
import re
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime
from typing import Literal

class MatchingProfile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    brand: str|None=Field(default=None,min_length=1,max_length=200)
    manufacturer: str|None=Field(default=None,min_length=1,max_length=200)
    model_name: str|None=Field(default=None,min_length=1,max_length=200)
    model_number: str|None=Field(default=None,min_length=1,max_length=200)
    mpn: str|None=Field(default=None,min_length=1,max_length=200)
    identifiers: list[dict]=Field(default_factory=list,max_length=8)
    image_url: str|None=None
    image_urls: list[str]=Field(default_factory=list,max_length=8)
    color: str|None=Field(default=None,min_length=1,max_length=100)
    size: str|None=Field(default=None,min_length=1,max_length=100)
    options: dict[str,str|None]=Field(default_factory=dict)
    category: str|None=Field(default=None,min_length=1,max_length=200)
    seller_id: str|None=Field(default=None,min_length=1,max_length=120)
    seller_name: str|None=Field(default=None,min_length=1,max_length=200)
    exact_match_confirmed: Literal[False]=False

class FoodEvidence(BaseModel):
    model_config=ConfigDict(extra='forbid')
    ingredients_raw: str|None=Field(default=None,min_length=1,max_length=4000)
    ingredients: list[str]=Field(default_factory=list,max_length=120)
    allergen_notice_raw: str|None=Field(default=None,min_length=1,max_length=1000)
    cross_contact_raw: str|None=Field(default=None,min_length=1,max_length=1000)
    allergens_declared: list[str]=Field(default_factory=list,max_length=32)
    evidence_status: Literal['not_reported','reported','negative_claim_unverified','conflicting','image_only','ocr_unverified']='reported'

class ListingExtension(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version: Literal['listing-extension-v1']='listing-extension-v1'
    source: str=Field(pattern=r'^[a-z][a-z0-9_-]{0,63}$')
    source_listing_id: str=Field(min_length=1,max_length=180)
    variant_key: str=Field(min_length=1,max_length=180)
    observation_key: str=Field(min_length=1,max_length=180)
    observed_at: AwareDatetime
    product_url: str|None=None
    is_synthetic: bool=False
    matching_profile: MatchingProfile|None=None
    food_evidence: FoodEvidence|None=None

ERROR=re.compile(r'[A-Z0-9_]{1,80}')
def safe_error(value):
    if not isinstance(value,dict):return {}
    code=(value.get('error') or {}).get('code') if isinstance(value.get('error'),dict) else None
    code=code or value.get('error_code') or value.get('detail')
    out={'error_code':code} if isinstance(code,str) and ERROR.fullmatch(code) else {}
    fields=value.get('fields')
    if isinstance(fields,list):
        out['fields']=[x for x in fields[:32] if isinstance(x,list) and len(x)<=8 and all(isinstance(k,(str,int)) and len(str(k))<=80 for k in x)]
    return out

def safe_checks(value,body):
    if not isinstance(value,dict) or type(value.get('confirmed')) is not int:return {}
    if not 0<=value['confirmed']<=len(body['items']):return {}
    allowed={(x['source_listing_id'],x['variant_key']) for x in body['items']}
    out={'confirmed':value['confirmed']}
    for k in ('mismatch','unknown','rejected'):
        if not isinstance(value.get(k),list):return {}
        out[k]=[]
        for x in value[k]:
            if not isinstance(x,dict) or (x.get('source_listing_id'),x.get('variant_key')) not in allowed:return {}
            y={p:x[p] for p in ('source_listing_id','variant_key')}
            if k=='rejected':
                if x.get('reason')!='OBSERVED_AT_OUT_OF_RANGE':return {}
                y['reason']=x['reason']
            out[k].append(y)
    identities=[(x['source_listing_id'],x['variant_key']) for k in ('mismatch','unknown','rejected') for x in out[k]]
    if len(set(identities))!=len(identities) or out['confirmed']+len(identities)!=len(allowed):return {}
    return out

def catalog_review(body,cfg):
    """An operator-supplied copy of the backend allowlist, never an automatic grant."""
    import os
    policy=cfg.get('backend_catalog')
    if os.environ.get('COLLECTOR_BACKEND_CATALOG_HOSTS') or os.environ.get('COLLECTOR_BACKEND_CATALOG_CURRENCIES'):
        policy={'url_hosts':os.environ.get('COLLECTOR_BACKEND_CATALOG_HOSTS','').split(','),'currencies':os.environ.get('COLLECTOR_BACKEND_CATALOG_CURRENCIES','').split(',')}
    if policy is None:return None
    host=urlsplit(body.get('url','')).hostname
    missing=[]
    if host not in policy.get('url_hosts',[]):missing.append('url')
    if body.get('currency') not in policy.get('currencies',[]):missing.append('currency')
    if missing:return {'status':'backend_catalog_approval_required','missing_fields':missing,'required_host':host,'required_currency':body.get('currency')}
    return None
