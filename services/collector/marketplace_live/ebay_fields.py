"""Browse evidence in RAM; only representable values enter Observation v2.

Reference: eBay Browse OpenAPI v1 / EstimatedAvailability and official condition IDs.
Estimated quantities are never exact stock, nor proof of purchase availability.
"""
import re
from datetime import datetime

# V2 has only new/used. Retain the subtype outside its immutable payload.
CONDITIONS = {
    '1000': ('new', 'new'),
    '1500': (None, 'new_other_open_box'),
    '1750': (None, 'new_with_defects'),
    '2000': (None, 'certified_refurbished'),
    '2010': (None, 'excellent_refurbished'),
    '2020': (None, 'very_good_refurbished'),
    '2030': (None, 'good_refurbished'),
    '2500': (None, 'seller_refurbished'),
    '2750': ('used', 'like_new'),
    '2990': ('used', 'pre_owned_excellent'),
    '3000': ('used', 'used'),
    '3010': ('used', 'pre_owned_fair'),
    '4000': ('used', 'very_good'),
    '5000': ('used', 'good'),
    '6000': ('used', 'acceptable'),
    '7000': (None, 'for_parts_or_not_working'),
}
# Exact US labels only. Never substring-match "new" in "like new" or refurbishments.
LABELS = {
    'new': '1000', 'brand new': '1000', 'new with box': '1000',
    'new with tags': '1000', 'new/factory sealed': '1000', 'digital good': '1000',
    'used': '3000', 'pre-owned': '3000', 'pre-owned - good': '3000',
    'pre-owned- good': '3000', 'open box/used': '3000',
    'like new': '2750', 'pre-owned - excellent': '2990', 'pre-owned - fair': '3010',
    'very good': '4000', 'good': '5000', 'acceptable': '6000',
    'open box': '1500', 'new other (see details)': '1500',
    'new without box': '1500', 'new without tags': '1500',
    'new with defects': '1750', 'certified refurbished': '2000',
    'certified - refurbished': '2000', 'excellent - refurbished': '2010',
    'very good - refurbished': '2020', 'good - refurbished': '2030',
    'seller refurbished': '2500', 'remanufactured': '2500',
    'for parts or not working': '7000',
}


def condition_evidence(item):
    label = item.get('condition')
    text = label.strip().casefold() if isinstance(label, str) else ''
    identity = item.get('conditionId')
    explicit = 'conditionId' in item
    mapped_id = str(identity) if explicit else LABELS.get(text)
    common, subtype = CONDITIONS.get(mapped_id, (None, 'unknown'))
    reason = 'native_condition_id' if explicit else 'exact_US_condition_label'
    # Special categories reuse the IDs for grading rather than wear condition.
    if re.search(r'\b(?:un)?graded\b', text):
        common, subtype, reason = None, text, 'grading_is_not_wear_condition'
    elif mapped_id in ('2750', '3000', '4000') and not text:
        common, subtype, reason = None, 'category_dependent', 'category_condition_requires_label'
    elif mapped_id in CONDITIONS and text in LABELS and LABELS[text] != mapped_id:
        common, reason = None, 'condition_id_label_conflict'
    elif subtype == 'unknown':
        reason = 'unknown_condition'
    elif common is None:
        reason = 'condition_subtype_not_representable_in_v2'
    return common, {'condition_detail': subtype, 'condition_reason': reason,
                    'native_condition_id': identity, 'native_condition_label': label}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp_required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('timezone_required')
    return result


def availability_evidence(item, observed_at):
    evidence = {'stock_quantity': None, 'quantity_kind': 'unknown',
                'quantity_estimates': [], 'purchase_available': None,
                'availability_reason': 'missing_native_availability'}
    rows = item.get('estimatedAvailabilities', [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        evidence['availability_reason'] = 'invalid_native_availability'
        return None, evidence
    # Keep estimates per delivery option. Never sum repeated stock across options.
    fields = ('estimatedAvailableQuantity', 'estimatedRemainingQuantity',
              'availabilityThreshold', 'availabilityThresholdType', 'deliveryOptions')
    invalid_quantity = False
    for row in rows:
        entry = {key: row[key] for key in fields if key in row}
        for key in fields[:3]:
            if key in entry and (type(entry[key]) is not int or entry[key] < 0):
                invalid_quantity = True
        if entry:
            evidence['quantity_estimates'].append(entry)
    if evidence['quantity_estimates']:
        evidence['quantity_kind'] = 'estimated_or_threshold'
    if 'itemEndDate' in item:
        try:
            if timestamp(item['itemEndDate']) <= timestamp(observed_at):
                evidence.update(purchase_available=False, availability_reason='listing_ended')
                return 'ended', evidence
        except (ValueError, TypeError, OverflowError):
            evidence['availability_reason'] = 'invalid_item_end_date'
            return None, evidence
    statuses = {row.get('estimatedAvailabilityStatus') for row in rows
                if isinstance(row.get('estimatedAvailabilityStatus'), str)}
    if invalid_quantity:
        evidence['availability_reason'] = 'invalid_native_quantity'
        return None, evidence
    if not rows:
        return None, evidence
    if (not statuses or any(row.get('estimatedAvailabilityStatus') not in statuses for row in rows)
            or not statuses <= {'IN_STOCK', 'LIMITED_STOCK', 'OUT_OF_STOCK'}):
        evidence['availability_reason'] = 'unknown_or_conflicting_availability'
        return None, evidence
    if 'OUT_OF_STOCK' in statuses and len(statuses) > 1:
        evidence['availability_reason'] = 'unknown_or_conflicting_availability'
        return None, evidence
    status = 'OUT_OF_STOCK' if 'OUT_OF_STOCK' in statuses else 'IN_STOCK'
    for row in rows:
        for key in ('estimatedAvailableQuantity', 'estimatedRemainingQuantity'):
            if key in row and ((status == 'OUT_OF_STOCK' and row[key] > 0)
                               or (status != 'OUT_OF_STOCK' and row[key] == 0)):
                evidence['availability_reason'] = 'availability_quantity_conflict'
                return None, evidence
    available = status != 'OUT_OF_STOCK'
    reason = 'native_' + next(iter(statuses)).lower() if len(statuses) == 1 else 'native_in_stock_or_limited_stock'
    evidence.update(purchase_available=available, availability_reason=reason)
    return ('available' if available else 'out_of_stock'), evidence
