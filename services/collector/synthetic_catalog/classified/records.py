"""Coherent synthetic profiles; original IDs stay stable in the enriched view."""
import hashlib
import re
from decimal import Decimal
from ..generate import encoded

VERSION='synthetic-catalog-classified-v2'


def render(base,leaf_id,taxonomy,ordinal,origin):
    profile=taxonomy.profiles[leaf_id];path=taxonomy.paths[leaf_id]
    number=int.from_bytes(hashlib.sha256(base['record_id'].encode()).digest()[:8],'big')
    brand=profile['brands'][number%len(profile['brands'])]
    model=f'{profile["model_prefix"]}-{ordinal:07d}'
    currency=base['currency'];lo,hi=profile['price_ranges_minor_units'][currency]
    amount=lo+number%(hi-lo+1)
    if base['condition']=='used':
        if not profile['used_allowed']:raise ValueError('used_consumable_not_allowed')
        amount=amount*3//5
    row=dict(base)
    row.update(schema_version=VERSION,name=f'{brand} {model} {path[2]["name"]} {profile["spec_label"]}',
        price=f'{amount//100}.{amount%100:02d}' if currency=='USD' else str(amount),
        category=path[2]['name'],category_path=[n['name'] for n in path],category_ids=[n['id'] for n in path],
        category_status='provisional_pending_team_approval',team_category_id=None,team_domain=path[0]['team_domain'],
        brand=brand,model=model,specifications=dict(profile['specifications']),specification_label=profile['spec_label'],
        origin=origin)
    row.pop('observation_key',None)
    row['observation_key']='SYNTHETIC-CLASSIFIED:'+hashlib.sha256(encoded(row)).hexdigest()
    return row


def added_base(identity,index,profile):
    return {'record_id':identity,'source_listing_id':identity,'variant_key':identity+':variant-0',
        'synthetic':True,'source':'synthetic_catalog','region':'overseas' if index%2 else 'domestic',
        'currency':'USD' if index%2 else 'KRW','condition':'used' if profile['used_allowed'] and index//2%2 else 'new',
        'seller':f'SYNTHETIC_VENDOR_{index%1000:04d}','url':'https://catalog.example.test/synthetic/'+identity,
        'availability':'available','stock_quantity':None,'ingredients':None,'allergens':None,'safe_to_consume':None}


def validate_record(row,taxonomy,ordinal=None):
    if row.get('synthetic') is not True or row.get('schema_version')!=VERSION or row.get('source')!='synthetic_catalog':
        raise ValueError('classified_synthetic_record_required')
    required=('record_id','source_listing_id','variant_key','name','price','currency','seller','url','brand','model',
              'category','category_ids','category_path','specifications','origin')
    if any(row.get(k) in (None,'',{},[]) for k in required):raise ValueError('required_field_missing')
    if any(not isinstance(row[k],list) or len(row[k])!=3 for k in ('category_ids','category_path')):
        raise ValueError('three_category_levels_required')
    if not isinstance(row['origin'],dict) or row['origin'].get('kind') not in ('legacy_enriched','added_balancing'):
        raise ValueError('explicit_synthetic_lineage_required')
    identity=row['record_id']
    if not re.fullmatch(r'SYNTHETIC-(?:ADD-)?[0-9a-f]{16}-[0-9]{7}',identity):raise ValueError('synthetic_ID_required')
    if row['source_listing_id']!=identity or row['variant_key']!=identity+':variant-0':raise ValueError('identity_mismatch')
    if row['url']!='https://catalog.example.test/synthetic/'+identity or not row['seller'].startswith('SYNTHETIC_'):
        raise ValueError('synthetic_provenance_required')
    leaf_id=row['category_ids'][2];profile=taxonomy.profiles.get(leaf_id)
    if profile is None:raise ValueError('unknown_category_leaf')
    path=taxonomy.paths[leaf_id]
    if row['category_ids']!=[n['id'] for n in path] or row['category_path']!=[n['name'] for n in path] or row['category']!=path[2]['name']:
        raise ValueError('category_hierarchy_mismatch')
    if row.get('team_category_id') is not None or row.get('category_status')!='provisional_pending_team_approval' or row.get('team_domain')!=path[0]['team_domain']:
        raise ValueError('official_category_ID_not_assigned')
    if row['brand'] not in profile['brands'] or row['specifications']!=profile['specifications'] or row.get('specification_label')!=profile['spec_label']:
        raise ValueError('brand_or_specification_category_mismatch')
    if not re.fullmatch(re.escape(profile['model_prefix'])+'-[0-9]{7}',row['model']):raise ValueError('category_model_mismatch')
    if ordinal is not None and row['model']!=f'{profile["model_prefix"]}-{ordinal:07d}':raise ValueError('model_sequence_mismatch')
    expected=f'{row["brand"]} {row["model"]} {path[2]["name"]} {profile["spec_label"]}'
    if row['name']!=expected:raise ValueError('product_name_category_mismatch')
    currency=row['currency']
    if (row['region'],currency) not in (('domestic','KRW'),('overseas','USD')):raise ValueError('region_currency_mismatch')
    pattern=r'[0-9]+' if currency=='KRW' else r'[0-9]+\.[0-9]{2}'
    if not isinstance(row['price'],str) or not re.fullmatch(pattern,row['price']):raise ValueError('price_format_invalid')
    lo,hi=profile['price_ranges_minor_units'][currency]
    if row['condition']=='used':
        if not profile['used_allowed']:raise ValueError('used_consumable_not_allowed')
        lo,hi=lo*3//5,hi*3//5
    elif row['condition']!='new':raise ValueError('condition_invalid')
    price=Decimal(row['price'])*(100 if currency=='USD' else 1)
    if not lo<=price<=hi:raise ValueError('price_outside_category_range')
    if row.get('availability')!='available' or any(row.get(k) is not None for k in ('ingredients','allergens','safe_to_consume','stock_quantity')):
        raise ValueError('no_fabricated_food_or_stock_information')
    body={k:v for k,v in row.items() if k!='observation_key'}
    if row.get('observation_key')!='SYNTHETIC-CLASSIFIED:'+hashlib.sha256(encoded(body)).hexdigest():raise ValueError('record_hash_mismatch')
