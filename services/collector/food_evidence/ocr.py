"""Shared, opt-in product-detail OCR. Original text wins; OCR never assesses safety."""

import hashlib

import io

import json

import re

import time

from functools import lru_cache

from pathlib import Path

from services.collector.domeggook_live.domeggook_delivery import atomic,load

from services.collector.food_evidence.extract import ALIASES

VERSION='product-easyocr-v6-table-cells'

TERMS=sorted((k for k in ALIASES if re.search('[가-힣]',k)),key=len,reverse=True)

CONTAINS=re.compile(r'(?<![가-힣])('+ '|'.join(map(re.escape,TERMS))+r')\s*(?:함유|포함)')

CROSS=re.compile(r'혼입|교차\s*오염|같은.*(?:시설|제조)|동일.*(?:시설|제조)|may\s+contain|same facility|facility.*(?:handles|processes)',re.I)

NEGATIVE=re.compile(r'미함유|불포함|함유하지|해당\s*없|알레르기.*없음|\b(?:free[- ]from|does not contain|no allergens?|contains? no)\b',re.I)

def _english_codes(text):
    return [code for term,code in ALIASES.items() if term.isascii() and
            re.search(r'(?<![a-z])'+re.escape(term)+r'(?![a-z])',text,re.I)]

def notices(records):

    direct=[];cross=[];codes=[];possible=[]

    for record in records:

        text=record['text'].strip()

        if record.get('confidence',0)<0.5 or NEGATIVE.search(text):continue

        if CROSS.search(text):

            found=[ALIASES[k] for k in TERMS if re.search(r'(?<![가-힣])'+re.escape(k)+r'(?:을|를|이|가|와|과)?(?=[^가-힣]|$)',text)]

            found.extend(_english_codes(text))
            if found:cross.append(text);possible.extend(found)

            continue

        found=[ALIASES[m.group(1)] for m in CONTAINS.finditer(text)]

        if re.search(r'알레르기(?:\s*유발물질)?\s*[:：]',text):

            value=re.split(r'[:：]',text,maxsplit=1)[-1]

            found.extend(ALIASES[token.strip()] for token in re.split(r'[,、/]',value) if token.strip() in ALIASES)

        english=re.search(r'\b(?:contains?|allergens?)(?:\s*[:：]\s*|\s+)(.+)',text,re.I)
        if english:found.extend(_english_codes(english.group(1)))
        if found:direct.append(text);codes.extend(found)

    return {'automatic_allergen_notice':'\n'.join(dict.fromkeys(direct)) or None,

            'automatic_cross_contact_notice':'\n'.join(dict.fromkeys(cross)) or None,

            'allergens_declared':sorted(set(codes)),

            'allergens_possible_cross_contact':sorted(set(possible))}

@lru_cache(maxsize=1)

def reader(model_dir,download=False):

    import torch,easyocr

    torch.set_num_threads(2)

    return easyocr.Reader(['ko','en'],gpu=False,detector=False,model_storage_directory=model_dir,

        user_network_directory=str(Path(model_dir)/'network'),download_enabled=download,verbose=False)

def recognize(image_path,model_dir):

    import numpy as np

    import cv2

    from PIL import Image,ImageOps,ImageEnhance

    image=Image.open(image_path)

    if image.width>4096 or image.height>12000 or image.width*image.height>16000000:

        raise ValueError('bounded_food_image_required')

    image.load();cv2.setNumThreads(1)
    image=image.convert('L');array=np.asarray(image)

    # Find small reversed-text panels by geometry, without product coordinates.

    mask=(array<90).astype(np.uint8)*255

    lines=(cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((1,60),np.uint8)) |

           cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((35,1),np.uint8)))

    _,_,stats,_=cv2.connectedComponentsWithStats(cv2.subtract(mask,lines))

    boxes=[]

    for x,y,w,h,area in stats[1:]:

        if 20<=w<=400 and 8<=h<=80 and 1.5<=w/h<=15 and area>=180 and area/(w*h)>=0.42:

            boxes.append(tuple(map(int,(x,y,w,h))))

    reverse_boxes=set(boxes)
    # Ruled specification tables provide stable line/cell regions independently
    # of product IDs, coordinates or expected ingredient/material values.
    grid_mask=(array<235).astype(np.uint8)*255
    horizontal=cv2.morphologyEx(grid_mask,cv2.MORPH_OPEN,np.ones((1,60),np.uint8))
    vertical=cv2.morphologyEx(grid_mask,cv2.MORPH_OPEN,np.ones((25,1),np.uint8))
    grid=cv2.dilate(horizontal | vertical,np.ones((3,3),np.uint8))
    contours,_=cv2.findContours(grid,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    table_boxes=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour)
        if 120<=w<=1200 and 20<=h<=90 and 3<=w/h<=45:
            table_boxes.append((x+2,y+2,w-4,h-4))
    joined=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((2,7),np.uint8))
    _,_,normal_stats,_=cv2.connectedComponentsWithStats(joined)
    for x,y,w,h,area in normal_stats[1:]:
        if 30<=w<=1000 and 12<=h<=80 and 2<=w/h<=25 and 0.12<=area/(w*h)<=0.7:
            boxes.append(tuple(map(int,(x,y,w,h))))
    table_boxes=sorted(set(table_boxes),key=lambda box:-box[1])[:12]
    boxes=(table_boxes+sorted(set(boxes)-set(table_boxes),key=lambda box:-box[1]))[:20]
    low_resolution=[]

    records=[];engine=reader(str(Path(model_dir).resolve()));deadline=time.monotonic()+45

    for x,y,w,h in boxes:

        base=image.crop((x,y,x+w,y+h))
        interior=np.asarray(base)[3:-3,3:-3]
        ink=interior>130 if (x,y,w,h) in reverse_boxes else interior<130
        rows=np.flatnonzero(ink.sum(axis=1)>=4)
        text_height=int(rows[-1]-rows[0]+1) if len(rows) else 0
        if text_height<10:
            low_resolution.append({'box':[x,y,w,h],'text_height_pixels':text_height})
            continue

        for border in (0,1,3):

            if time.monotonic()>deadline:break

            crop=base.crop((border,border,w-border,h-border))

            if (x,y,w,h) in reverse_boxes:crop=ImageOps.invert(crop)
            crop=ImageOps.autocontrast(crop).resize((crop.width*4,crop.height*4),Image.Resampling.LANCZOS)

            crop=ImageOps.expand(crop,10,fill=255)

            found=engine.recognize(np.asarray(crop),horizontal_list=[[0,crop.width,0,crop.height]],

                free_list=[],batch_size=1,workers=0,detail=1,paragraph=False)

            for _,text,confidence in found:

                records.append({'text':text,'confidence':float(confidence),'box':[x,y,w,h],'border':border,'region':'table_cell' if (x,y,w,h) in table_boxes else 'text_candidate'})

            if time.monotonic()>deadline:break

        if time.monotonic()>deadline:break

    result=notices(records)

    support=(result['automatic_allergen_notice'] or '')+'\n'+(result['automatic_cross_contact_notice'] or '')

    raw='\n'.join(dict.fromkeys(support.splitlines()+[r['text'] for r in records])).strip()[:10000]

    return dict(result,raw=raw,records=records,engine='easyocr_cpu_ko_en',automatic=True,

        automatic_extraction_success=bool(result['allergens_declared'] or result['allergens_possible_cross_contact']),visually_reviewed=False,

        validation_status='ocr_unverified',image_size=list(image.size),panels=len(boxes),

        scan_complete=False,coverage='bounded table cells and normal/reversed text candidates; not all image text',

        failure_reason=None if result['allergens_declared'] or result['allergens_possible_cross_contact'] else 'low_resolution_text_candidates' if low_resolution else 'no_literal_allergen_notice',
        low_resolution_candidates=low_resolution)

from dataclasses import dataclass
from copy import deepcopy

@dataclass(frozen=True)
class FoodOCRRequest:
    """Caller supplies reviewed detail URLs and its existing image-use permission.

    Representative images are deliberately excluded. Only confirmed food pages
    with no existing allergen text reach image download/recognition.
    """
    source: str
    product_url: str
    observed_at: str
    is_food: bool
    detail_image_urls: tuple[str,...]
    image_use_allowed: bool=False

def has_allergen_text(evidence):
    if evidence.get('allergen_status') in ('ocr_unverified','image_only'):return False
    if evidence.get('allergens_declared'):return True
    for key in ('allergen_notice_raw','cross_contact_raw'):
        value=evidence.get(key)
        if isinstance(value,str) and value.strip() and not re.fullmatch(
            r'\s*(?:상세\s*(?:정보|페이지|설명)(?:\s*(?:별도\s*표기|참조|참고))?|별도\s*표기)\s*',value):return True
    return evidence.get('allergen_status') in ('negative_claim_unverified','conflicting')

@dataclass(frozen=True)
class DetailOCRRequest:
    """Category-independent, explicitly allowed product-description image input."""
    source: str
    product_url: str
    observed_at: str
    detail_image_urls: tuple[str,...]
    image_use_allowed: bool=False
    requested_fields: tuple[str,...]=()


def collect_images(request,cfg,existing_evidence=None):
    # Backward-compatible food adapter; generic callers have no food restriction.
    if has_allergen_text(existing_evidence or {}):return {'status':'skipped_text_available','OCR_performed':False}
    if request.is_food is not True:return {'status':'skipped_not_food','OCR_performed':False}
    result=collect_detail_images(DetailOCRRequest(request.source,request.product_url,request.observed_at,
        request.detail_image_urls,request.image_use_allowed,('allergens',)),cfg)
    if 'records' in result:
        result['status']='extracted_unverified' if result['automatic_extraction_success'] else 'not_recognized'
    return result


def collect_detail_images(request,cfg):
    """Shared image transport/cache/CPU OCR; raw OCR is not semantic extraction."""
    if not isinstance(cfg,dict) or cfg.get('enabled') is not True or cfg.get('local_ocr_approved') is not True:
        return {'status':'disabled','OCR_performed':False}
    if request.image_use_allowed is not True:return {'status':'image_permission_required','OCR_performed':False}
    if not request.detail_image_urls:return {'status':'detail_images_not_reported','OCR_performed':False}
    from services.collector.domeggook_live.network import secure_public_session
    from urllib.parse import urlsplit,parse_qsl
    import requests
    target=request.detail_image_urls[0];p=urlsplit(target)
    if (p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443)
        or any(re.search(r'token|secret|password|signature|session|auth|credential|api[-_]?key',k,re.I) for k,_ in parse_qsl(p.query))):
        raise ValueError('public_credential_free_HTTPS_detail_required')
    root=Path(cfg['cache_dir']);root.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(target.encode()).hexdigest();image_path=root/(key+'.image');index=root/(key+'.json')
    previous=load(index,{})
    fresh=(time.time()-previous.get('downloaded_at',0)<3600 and image_path.exists()
        and image_path.stat().st_size<=10000000 and hashlib.sha256(image_path.read_bytes()).hexdigest()==previous.get('image_sha256'))
    if not fresh:
        session=secure_public_session(requests.Session())
        try:
            with session.get(target,timeout=(10,30),allow_redirects=False,stream=True) as response:
                if response.status_code!=200 or not response.headers.get('Content-Type','').startswith('image/'):
                    raise ValueError('detail_image_access_failed_no_redirect')
                data=bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data)>10000000:raise ValueError('bounded_food_image_required')
            image_path.write_bytes(data)
        finally:session.close()
        previous={'downloaded_at':time.time(),'image_sha256':hashlib.sha256(data).hexdigest()}
        atomic(index,previous)
    model_stamp=[(p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in sorted(Path(cfg['model_dir']).glob('*.pth'))]
    fingerprint=hashlib.sha256(json.dumps([VERSION,str(Path(cfg['model_dir']).resolve()),model_stamp]).encode()).hexdigest()
    # A second provider/URL serving the same pixels reuses OCR, not its provenance.
    content_key=hashlib.sha256((previous['image_sha256']+fingerprint).encode()).hexdigest()[:32]
    content_cache=root/(content_key+'.ocr.json')
    saved=load(content_cache,{})
    if saved.get('fingerprint')==fingerprint and saved.get('image_sha256')==previous['image_sha256'] and saved.get('result'):
        result=deepcopy(saved['result']);hit=True
    else:
        result=recognize(image_path,cfg['model_dir']);hit=False
        atomic(content_cache,{'fingerprint':fingerprint,'image_sha256':previous['image_sha256'],'result':result})
    return dict(result,status='ocr_executed',
        source_image_url=target,image_sha256=previous['image_sha256'],cache_hit=hit,
        image_cache_hit=fresh,OCR_performed=not hit)

def enrich_evidence(evidence,request,cfg):
    """Shared entry point. Existing text is preserved and no OCR fact is verified."""
    output=deepcopy(evidence)
    try:ocr=collect_images(request,cfg,existing_evidence=evidence)
    except (ImportError,OSError,ValueError,RuntimeError,KeyError) as exc:
        output.update(ocr_status='failed',ocr_failure_reason=type(exc).__name__,ocr_automatic_extraction_success=False)
        return output
    output['ocr_status']=ocr['status']
    if 'records' not in ocr:return output
    found=notices(ocr['records'])
    success=bool(found['allergens_declared'] or found['allergens_possible_cross_contact'])
    output.update(ocr_raw=ocr['raw'],ocr_records=ocr['records'],source_image_url=ocr['source_image_url'],
        source_image_sha256=ocr['image_sha256'],ocr_engine=ocr['engine'],ocr_visually_reviewed=False,
        ocr_automatic_extraction_success=success,ocr_cache_hit=ocr['cache_hit'],ocr_performed=ocr['OCR_performed'],
        ocr_scan_complete=ocr.get('scan_complete',False),ocr_failure_reason=ocr.get('failure_reason'),
        ocr_low_resolution_candidates=ocr.get('low_resolution_candidates',[]),
        ocr_validation_status='ocr_unverified',allergen_status='ocr_unverified',requires_review=True,safe_to_consume=None)
    output['allergens_declared']=sorted(set((output.get('allergens_declared') or [])+found['allergens_declared'])) or None
    output['allergens_possible_cross_contact']=sorted(set((output.get('allergens_possible_cross_contact') or [])+found['allergens_possible_cross_contact'])) or None
    direct=found['automatic_allergen_notice']
    if direct:output['allergen_notice_raw']=(direct+'\n[OCR 원문]\n'+ocr['raw'])[:1000]
    elif ocr['raw']:output['allergen_notice_raw']=('[OCR 원문; 알레르기 자동 미확인]\n'+ocr['raw'])[:1000]
    if found['automatic_cross_contact_notice']:output['cross_contact_raw']=found['automatic_cross_contact_notice'][:1000]
    raw=(output.get('raw') or '')+'\n[OCR]\n'+ocr['raw']
    output['raw']=raw;output['raw_sha256']=hashlib.sha256(raw.encode()).hexdigest()
    return output

def attach_to_normalized(normalized,request,cfg):
    """Homepage integration: call after text extraction, before delivery.stage()."""
    output=deepcopy(normalized)
    output['food_evidence']=enrich_evidence(output.get('food_evidence') or {},request,cfg)
    image=output['food_evidence'].get('source_image_url')
    if image and request.image_use_allowed is True and image in request.detail_image_urls:
        metadata=output.get('metadata') or {}
        output['metadata']=metadata
        profile=metadata.get('matching_profile') or {}
        metadata['matching_profile']=profile
        profile['image_urls']=list(dict.fromkeys([image]+(profile.get('image_urls') or [])))[:8]
    return output
