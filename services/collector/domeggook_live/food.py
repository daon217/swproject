"""Domeggook infoDuty food labels; placeholders never become ingredients."""
import re
from bs4 import BeautifulSoup
from services.collector.unified_live.food import evidence

LABELS={'원재료명 및 함량':'ingredients','원재료명':'ingredients','원재료':'ingredients',
        '알레르기':'allergens','알레르기 정보':'allergens','알레르기 유발물질':'allergens',
        '혼입 가능성':'cross_contact'}
PLACEHOLDER=re.compile(r'^(?:상세\s*(?:정보|페이지|설명|이미지)(?:\s*(?:별도\s*표기|참조|참고|확인))?|상품\s*상세\s*참조|별도\s*표기|[-])$')

def food_evidence(row,ocr_config=None):
    fields={'name':row.get('product_name'),'category':row.get('category'),
            'description':row.get('description') if row.get('detail_content_license_usable') is True else None}
    notices=row.get('product_notices') or {}
    items=notices.get('item',[]) if isinstance(notices,dict) else []
    if isinstance(items,dict):items=[items]
    if not isinstance(items,list):items=[]
    for item in items[:100]:
        if not isinstance(item,dict):continue
        key=LABELS.get(str(item.get('name','')).strip())
        raw=item.get('desc')
        if not key or not isinstance(raw,str) or len(raw)>4000:continue
        value=BeautifulSoup(raw,'html.parser').get_text(' ',strip=True)
        if not value or PLACEHOLDER.fullmatch(value):continue
        fields[key]='\n'.join(filter(None,(fields.get(key),value)))
    # Text evidence always wins; don't download images when the label is in HTML/API text.
    base=evidence(fields,source='domeggook',url=row.get('product_url'),at=row.get('observed_at') or row.get('last_observed_at'))
    from services.collector.food_evidence.ocr import has_allergen_text
    if has_allergen_text(base):
        base.update(ocr_status='skipped_text_available',source_field='detail.infoDuty / licensed desc.contents.item')
        return base
    if row.get('food_ocr') is None and ocr_config:
        from .food_ocr import enrich
        result=enrich(base,row,ocr_config)
        result['source_field']='detail.infoDuty / licensed desc.contents.item; detail_image_ocr'
        return result
    # OCR is explicitly reviewed image evidence, never native API text.
    ocr=row.get('food_ocr');ocr_failure=None
    if ocr is None and ocr_config:
        try:
            from .food_ocr import collect
            ocr=collect(row,ocr_config)
        except (ImportError,OSError,ValueError,RuntimeError,KeyError) as exc:
            ocr_failure=type(exc).__name__
    automatic=isinstance(ocr,dict) and ocr.get('automatic') is True
    accepted_ocr=(isinstance(ocr,dict) and row.get('detail_content_license_usable') is True
        and ocr.get('source_image_url') in (row.get('detail_image_urls') or [])
        and isinstance(ocr.get('image_sha256'),str) and bool(re.fullmatch(r'[0-9a-f]{64}',ocr['image_sha256']))
        and isinstance(ocr.get('raw'),str) and 0<len(ocr['raw'])<=10000
        and (ocr.get('visually_reviewed') is True or automatic))
    if accepted_ocr and automatic:
        from .food_ocr import notices
        # Recompute from literal engine output; manual review fields are ignored.
        automatic_notices=notices(ocr.get('records') or [])
        for source,key in (('automatic_allergen_notice','allergens'),('automatic_cross_contact_notice','cross_contact')):
            value=automatic_notices.get(source)
            if value:fields[key]='\n'.join(filter(None,(fields.get(key),value)))
    if accepted_ocr and not automatic:
        for source,key in (('reviewed_allergen_notice','allergens'),('reviewed_cross_contact_notice','cross_contact')):
            value=ocr.get(source)
            if isinstance(value,str) and value.strip() and len(value)<=500:
                fields[key]='\n'.join(filter(None,(fields.get(key),value)))
    result=evidence(fields,source='domeggook',url=row.get('product_url'),at=row.get('observed_at') or row.get('last_observed_at'))
    if accepted_ocr:
        result.update(ocr_raw=ocr['raw'],source_image_url=ocr['source_image_url'],
            source_image_sha256=ocr['image_sha256'],ocr_engine=ocr.get('engine'),
            ocr_visually_reviewed=not automatic,allergen_status='ocr_unverified',requires_review=True,
            ocr_automatic_extraction_success=automatic and bool(automatic_notices['allergens_declared']),
            ocr_cache_hit=ocr.get('cache_hit',False),ocr_validation_status='ocr_unverified',
            ocr_scan_complete=ocr.get('scan_complete'),ocr_tiles=ocr.get('tiles'))
        if automatic:
            result['allergens_declared']=sorted(set((result.get('allergens_declared') or [])+automatic_notices['allergens_declared'])) or None
            result['allergens_possible_cross_contact']=sorted(set((result.get('allergens_possible_cross_contact') or [])+automatic_notices['allergens_possible_cross_contact'])) or None
        if fields.get('allergens'):
            result['allergen_notice_raw']=(fields['allergens']+'\n[OCR 원문]\n'+ocr['raw'])[:1000]
        elif automatic:
            result['allergen_notice_raw']=('[OCR 원문; 알레르기 자동 미확인]\n'+ocr['raw'])[:1000]
    if ocr_failure:result['ocr_failure']=ocr_failure
    result['source_field']='detail.infoDuty / licensed desc.contents.item'
    return result
