"""Domeggook request adapter; recognition/cache live in the shared food module."""
from services.collector.food_evidence.ocr import (
    FoodOCRRequest,collect_images,enrich_evidence,notices,reader,recognize,
)


def build_request(row):
    native=row.get('native_category') or {};parents=(native.get('parents') or {}).get('elem') or []
    if isinstance(parents,dict):parents=[parents]
    food=any(p.get('name')=='식품' for p in parents if isinstance(p,dict)) or row.get('category')=='식품'
    if isinstance(row.get('classification'),dict):food=row['classification'].get('is_food') is True
    return FoodOCRRequest(source=row.get('source') or 'domeggook',product_url=row.get('product_url') or '',
        observed_at=row.get('observed_at') or row.get('last_observed_at') or '',
        is_food=row.get('source')=='domeggook' and food,
        detail_image_urls=tuple(row.get('detail_image_urls') or []),
        image_use_allowed=row.get('detail_content_license_usable') is True)


def collect(row,cfg,evidence=None):
    return collect_images(build_request(row),cfg,existing_evidence=evidence)


def enrich(evidence,row,cfg):
    return enrich_evidence(evidence,build_request(row),cfg)
