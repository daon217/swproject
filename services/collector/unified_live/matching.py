"""Native product matching evidence, separate from Observation v2 and embeddings."""
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from services.collector.domeggook_live.domeggook_delivery import atomic,load
from .policy import url
from .food_lookup import gtin


def text(value,limit=500):
    if isinstance(value,dict):value=value.get('name') or value.get('value')
    if not isinstance(value,str):return None
    value=unicodedata.normalize('NFKC',BeautifulSoup(value,'html.parser').get_text(' ',strip=True))
    value=' '.join(value.split())
    return value[:limit] or None


def canonical(value):
    value=text(value)
    return value.casefold() if value else None


ALIASES={'brand':'brand','브랜드':'brand','manufacturer':'manufacturer','제조사':'manufacturer',
    'model':'model_name','모델명':'model_name','model name':'model_name','model number':'model_number',
    'model no.':'model_number','모델번호':'model_number','mpn':'mpn','manufacturer part number':'mpn',
    'color':'color','colour':'color','색상':'color','size':'size','사이즈':'size',
    'storage capacity':'storage_capacity','저장용량':'storage_capacity','capacity':'capacity',
    'memory':'memory','voltage':'voltage','pack quantity':'pack_quantity','gtin':'gtin','ean':'gtin','upc':'gtin'}
DIMENSIONS=('color','size','storage_capacity','capacity','memory','voltage','pack_quantity')


def profile(native,base,*,origin):
    """Project bounded explicit fields. No title-derived brand/model or image inference."""
    if not isinstance(native,dict):raise ValueError('native_product_object_required')
    fields={};provenance={};review=[]
    def add(key,value,path):
        if isinstance(value,list):
            for v in value[:16]:add(key,v,path)
            return
        val=text(value,300)
        if val:
            fields.setdefault(key,[])
            if val not in fields[key]:fields[key].append(val)
            provenance.setdefault(key,[])
            if path not in provenance[key]:provenance[key].append(path)
    for key in ('name','brand','manufacturer','mpn','color','size','category'):
        add(key,native.get(key),key)
    add('model_name',native.get('model'),'model');add('model_number',native.get('modelNumber'),'modelNumber')
    properties=native.get('additionalProperty') or []
    if isinstance(properties,dict):properties=[properties]
    if isinstance(properties,list):
        for prop in properties[:64]:
            if not isinstance(prop,dict):continue
            key=ALIASES.get(canonical(prop.get('name')))
            if key:add(key,prop.get('value'),'additionalProperty.'+key)
    for key,values in fields.items():
        if len({canonical(v) for v in values})>1:review.append('conflicting_native_'+key)
    def one(key):
        values=fields.get(key,[])
        return values[0] if len({canonical(v) for v in values})==1 else None
    identifiers=[]
    for key in ('gtin','gtin8','gtin12','gtin13','gtin14'):
        raw=native.get(key);raw=raw if isinstance(raw,list) else [raw]
        if key=='gtin':raw=raw+fields.get('gtin',[])
        for candidate in raw[:8]:
            if candidate is None:continue
            try:val=gtin(candidate)  # Numeric GTINs can have lost leading zeroes; do not repair them.
            except (ValueError,TypeError):review.append('invalid_native_'+key);continue
            if val not in [i['value'] for i in identifiers]:identifiers.append({'type':'gtin','value':val,'source_field':key})
    if len(identifiers)>1:review.append('multiple_GTINs_variant_review')
    images=[]
    raw_images=native.get('image') or [];raw_images=raw_images if isinstance(raw_images,list) else [raw_images]
    for image in raw_images[:16]:
        if isinstance(image,dict):image=image.get('contentUrl') or image.get('url')
        if not isinstance(image,str):continue
        try:image=url(urljoin(base,image))
        except ValueError:review.append('image_URL_rejected');continue
        if image not in images:images.append(image)
        if len(images)>=8:break
    attributes={k:one(k) for k in DIMENSIONS if one(k) is not None}
    signature=hashlib.sha256(json.dumps({k:canonical(v) for k,v in attributes.items()},sort_keys=True).encode()).hexdigest() if attributes else None
    return {'schema_version':'product-match-v1','product_name':one('name'),'brand':one('brand'),
        'manufacturer':one('manufacturer'),'model_name':one('model_name'),'model_number':one('model_number'),
        'mpn':one('mpn'),'identifiers':identifiers,'image_urls':images,'image_url':images[0] if images else None,
        'color':one('color'),'size':one('size'),'options':attributes,'variant_signature':signature,
        'category':one('category'),'description':text(native.get('description'),4000),
        'evidence_origin':origin,'source_fields':provenance,'review_reasons':sorted(set(review)),
        'exact_match_confirmed':False,'image_similarity_is_identity':False}


def provider_profile(row,source,base):
    """Use only documented native projections; IDs/SKUs never become global identifiers."""
    p={k:row.get(k) for k in ('brand','manufacturer','mpn','model','modelNumber','gtin','gtin8','gtin12','gtin13','gtin14','color','size','category','description','additionalProperty')}
    p['name']=row.get('title') or row.get('name') or row.get('product_name')
    if source=='ebay_browse':
        images=[row.get('image')]+(row.get('additionalImages') if isinstance(row.get('additionalImages'),list) else [])
        p['image']=[i.get('imageUrl') if isinstance(i,dict) else i for i in images]
        props=list(p.get('additionalProperty') or []) if isinstance(p.get('additionalProperty'),list) else []
        aspects=row.get('localizedAspects') or []
        for aspect in (aspects[:64] if isinstance(aspects,list) else []):
            if isinstance(aspect,dict):props.append({'name':aspect.get('name'),'value':aspect.get('value')})
        p['additionalProperty']=props
        p['description']=row.get('shortDescription') or row.get('description')
    elif source=='serper_google_shopping':p['image']=row.get('imageUrl')
    elif source=='yes24_api':p['image']=row.get('cover')
    elif source=='domeggook':p['image']=row.get('image_url');p['name']=row.get('product_name')
    else:
        p['image']=[row.get('image_link')]+(row.get('additional_image_link') if isinstance(row.get('additional_image_link'),list) else [])
        p['name']=row.get('title') or row.get('name');p['gtin']=row.get('gtin');p['description']=row.get('description')
        if isinstance(row.get('product_type'),str):p['category']=row['product_type']
    return profile(p,base,origin=source)


def compare(left,right):
    """Generate conservative candidates, never confirm identity or collapse offers."""
    conflicts=[];basis=[]
    for key in ('brand','model_number','mpn'):
        a,b=canonical(left.get(key)),canonical(right.get(key))
        if a and b and a!=b:conflicts.append(key)
    lg={x['value'] for x in left.get('identifiers',[]) if x.get('type')=='gtin'}
    rg={x['value'] for x in right.get('identifiers',[]) if x.get('type')=='gtin'}
    if lg and rg and not lg&rg:conflicts.append('gtin')
    options_a=left.get('options',{});options_b=right.get('options',{})
    for key in set(options_a)&set(options_b):
        if canonical(options_a[key])!=canonical(options_b[key]):conflicts.append('option.'+key)
    if lg&rg:basis.append('native_gtin')
    brand=canonical(left.get('brand'))
    if brand and brand==canonical(right.get('brand')):
        for key in ('mpn','model_number'):
            if canonical(left.get(key)) and canonical(left.get(key))==canonical(right.get(key)):basis.append('brand+'+key)
    uncertain=bool(left.get('review_reasons') or right.get('review_reasons'))
    kind='identity_conflict' if conflicts else 'same_product_candidate' if basis and not uncertain else 'similar_candidate'
    variants='conflict' if any(k.startswith('option.') for k in conflicts) else 'partially_specified' if not options_a or not options_b or set(options_a)!=set(options_b) else 'observed_options_agree'
    return {'match_type':kind,'identity_basis':basis,'conflicts':sorted(conflicts),'variant_status':variants,
        'requires_review':True,'exact_match_confirmed':False,'image_similarity_is_identity':False}


class MatchingStore:
    """Local extension only; never sends to the v2 backend or fetches an image."""
    def __init__(self,root,source):
        self.path=Path(root)/'matching_checkpoint.json';self.source=source
        self.data=load(self.path,{'version':1,'source':source,'items':{}})
        if self.data.get('version')!=1 or self.data.get('source')!=source:raise ValueError('matching_checkpoint_mismatch_no_reset')
    def record(self,normalized,cfg):
        from .changes import digest
        body=normalized.get('observation');mp=(normalized.get('metadata') or {}).get('matching_profile')
        if not body or not mp or not {'storage','reuse'}<=set(cfg.get('rights',{}).get('allowed_uses',[])):return
        from services.collector.domeggook_live.domeggook_delivery import utcnow
        from services.collector.marketplace_live.config import rights,SOURCES
        from .policy import grant
        if cfg.get('source')!=self.source:return
        permitted=rights(cfg,utcnow(),storage=True) if self.source in SOURCES else grant(cfg,utcnow())
        if not permitted:return
        mp=dict(mp)
        if 'description_storage' not in cfg['rights']['allowed_uses']:mp['description']=None
        key=digest([body['source'],body['source_listing_id'],body['variant_key']]);old=self.data['items'].get(key,{})
        maximum=min(cfg.get('max_tracked_items',10000),100000)
        if not old and len(self.data['items'])>=maximum:return
        signature=digest(mp);at=body['observed_at']
        content=digest([mp,body.get('price'),body.get('currency'),body['condition'],body.get('availability'),body['url'],normalized.get('seller')])
        self.data['items'][key]={'source':body['source'],'source_listing_id':body['source_listing_id'],'variant_key':body['variant_key'],
            'product_url':body['url'],'condition':body['condition'],'availability':body.get('availability'),
            'price':body.get('price'),'currency':body.get('currency'),'seller':normalized.get('seller'),
            'profile':mp,'profile_sha256':signature,'content_sha256':content,'collected_at':old.get('collected_at',at),'last_checked_at':at,
            'last_changed_at':at if content!=old.get('content_sha256') else old.get('last_changed_at',at),
            'is_synthetic':(normalized.get('metadata') or {}).get('synthetic',False),
            'backend_contract_ready':False}
        atomic(self.path,self.data)
