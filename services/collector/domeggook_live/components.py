"""Domeggook adapter for shared, provenance-labelled component evidence.

Non-food structured evidence stays local until the team backend adds a contract.
Only licensed, explicitly storage/reuse-granted detail text can enter description.
"""
import copy
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from services.collector.product_evidence.extract import ProductEvidenceRequest,enrich_product


def build_request(row):
    classification=row.get('classification') or {}
    notices=row.get('product_notices') or {}
    items=notices.get('item') or []
    if isinstance(items,dict):items=[items]
    # Exclude seller banners; use actual detail images, never representative images.
    urls=[]
    for url in row.get('detail_image_urls') or []:
        path=urlsplit(url).path.lower()
        if re.search(r'(?:^|/)(?:notice|banner|delivery|shipping|info)(?:[./_-]|$)',path):continue
        urls.append(url)
    return ProductEvidenceRequest(source='domeggook',product_url=row.get('product_url') or '',
        observed_at=row.get('observed_at') or row.get('last_observed_at') or '',
        category_levels=tuple(classification.get('category_levels') or row.get('category_levels') or []),
        is_food=classification.get('is_food'),condition=classification.get('condition','unknown'),
        service_type=classification.get('service_type','unknown'),notice_type=notices.get('type',''),
        api_notices=tuple(items),description_html=row.get('description_source_html') or row.get('description_html') or '',
        description_text=row.get('description') or '',text_use_allowed=row.get('detail_content_license_usable') is True,
        detail_image_urls=tuple(urls),image_use_allowed=row.get('detail_content_license_usable') is True)


def collect(row,cfg):
    return enrich_product(build_request(row),cfg)


def source_description(row,evidence,cfg):
    """Existing description field; OCR is explicitly labelled unverified, never fact-checked."""
    from .domeggook_operations import grant_valid
    grants=cfg.get('storage_grants',{})
    if row.get('detail_content_license_usable') is not True or not grant_valid(grants,'description') or grants['description'].get('reuse') is not True:return row
    lines=[]
    for field in evidence['fields'].values():
        if field['status'] not in ('source_reported','ocr_unverified'):continue
        for source in field['sources']:
            if source['method'] in ('api_text','html_text','jsonld'):lines.append(source['label']+': '+source['raw'])
            elif source['method']=='ocr':
                lines.append('[OCR 미검증; 안전 여부 미확인] '+source['label']+': '+source['raw']+' | confidence='+str(source['confidence'])+' | image='+source['source_url'])
    if not lines:return row
    output=copy.deepcopy(row);original=output.get('description') or ''
    additions=[line for line in lines if line not in original]
    output['description']=(original+'\n'+'\n'.join(additions)).strip()[:4000]
    return output


def persist(root,row,evidence,observation_key):
    from .domeggook_delivery import atomic
    identity={'source':'domeggook','source_listing_id':row['source_listing_id'],
        'variant_key':row['variant_key'],'observed_at':row['observed_at'],'observation_key':observation_key}
    payload={'identity':identity,'evidence':evidence,'classification':copy.deepcopy(row.get('classification')),
        'native_category':copy.deepcopy(row.get('native_category')),'backend_status':'local_evidence_pending_structured_contract'}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:32]
    path=Path(root)/'product_evidence'/(key+'.json');path.parent.mkdir(parents=True,exist_ok=True)
    atomic(path,payload)
    return path
