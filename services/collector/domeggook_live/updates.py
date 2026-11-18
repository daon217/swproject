"""Field-level observation ordering and paired price/currency preservation."""
import copy
from datetime import datetime,timezone

def parsed(value):
    if not isinstance(value,str):return None
    try:
        stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
    except ValueError:return None

def validate_replacement(name,previous,new,keyer):
    protected=name in ('products_live.json','products_unified.json','products_replayed.json') or name.endswith('_native_live.json')
    if protected and isinstance(previous,list):
        if not isinstance(new,list):raise ValueError('product_array_required')
        oldkeys={keyer(r) for r in previous};newkeys={keyer(r) for r in new}
        if len(newkeys)!=len(new):raise ValueError('duplicate_product_keys_in_replacement')
        if not oldkeys.issubset(newkeys):raise ValueError('product_count_or_identity_regression; existing data preserved')
    if name.endswith('checkpoint.json') and isinstance(previous,dict) and isinstance(new,dict):
        if new.get('total_requests_reserved',0)<previous.get('total_requests_reserved',0):raise ValueError('cumulative_request_budget_reset')
        if len(new.get('requests',[]))<len(previous.get('requests',[])):raise ValueError('persistent_request_ledger_shrank')
        if isinstance(previous.get('records'),dict) and not set(previous['records']).issubset(new.get('records',{})):
            raise ValueError('checkpoint_product_records_lost')

def observed_at(row,field):
    evidence=row.get('evidence') or {}
    return (row.get('field_observed_at',{}).get(field)
            or (evidence.get('detail_observed_at') if field in ('description','specifications','seller') else None)
            or evidence.get('observed_at') or row.get('last_checked_at') or row.get('updated_at') or row.get('collected_at'))

def merge_fields(previous,observed,fields):
    if previous and (previous.get('source'),previous.get('product_id'))!=(observed.get('source'),observed.get('product_id')):
        raise ValueError('observation_identity_changed')
    candidate=copy.deepcopy(previous if previous is not None else observed)
    changed=[];accepted=[]
    candidate.setdefault('field_observed_at',{})
    candidate.setdefault('field_evidence',{})
    partial_price=observed.get('price') is None or observed.get('currency') is None
    old_pair=previous and previous.get('price') is not None and previous.get('currency') is not None
    skip_pair=bool(previous and (partial_price and old_pair or observed.get('price') is None))
    # A pair is accepted/rejected together when the old pair is complete.
    pair_stale=False
    if previous and old_pair:
        for field in ('price','currency'):
            old=parsed(observed_at(previous,field));new=parsed(observed_at(observed,field))
            if old and (not new or new<old):pair_stale=True
    for field in fields:
        value=observed.get(field)
        if value is None or value=='' or value=={} or value==[]:continue
        if field in ('price','currency') and (skip_pair or pair_stale):continue
        if field=='product_url' and previous and previous.get(field):continue
        oldstamp=parsed(observed_at(previous,field)) if previous else None
        stamp=observed_at(observed,field);newstamp=parsed(stamp)
        if previous and previous.get(field) is not None and oldstamp and (not newstamp or newstamp<oldstamp):continue
        if field=='specifications' and isinstance(value,dict) and isinstance(candidate.get(field),dict):
            value={**candidate[field],**value}
        if candidate.get(field)!=value:changed.append(field)
        candidate[field]=copy.deepcopy(value);accepted.append(field)
        if stamp:candidate['field_observed_at'][field]=stamp
        evidence=observed.get('evidence') or {}
        candidate['field_evidence'][field]={'observed_at':stamp,'method':observed.get('collection_method'),
            'response_sha256':evidence.get('detail_sha256') or evidence.get('response_sha256'),
            'native_field':(evidence.get('field_paths') or {}).get(field)}
    if previous is None:
        candidate['collected_at']=observed.get('collected_at')
        candidate['updated_at']=observed.get('updated_at')
        operation='insert'
    else:
        candidate['collected_at']=previous.get('collected_at') or observed.get('collected_at')
        if changed:
            stamps=[datetime.now(timezone.utc),parsed(previous.get('updated_at')),parsed(observed.get('updated_at'))]
            candidate['updated_at']=max(s for s in stamps if s is not None).isoformat()
        else:candidate['updated_at']=previous.get('updated_at')
        operation='update' if changed else 'unchanged'
    if accepted:
        # Keep earlier evidence for retained fields in field_evidence; preserve root facts too.
        candidate['evidence']={**copy.deepcopy(candidate.get('evidence') or {}),**copy.deepcopy(observed.get('evidence') or {})}
        if changed or previous is None:
            for meta in ('source','product_id','collection_method','storage_permission_status'):
                if observed.get(meta) is not None:candidate[meta]=observed[meta]
    candidate['detail_status']=('complete' if candidate.get('description') and candidate.get('specifications')
                                else 'partial' if candidate.get('description') or candidate.get('specifications') else 'listing_only')
    return candidate,operation,changed
