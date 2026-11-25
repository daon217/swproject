"""Full streaming semantic/identity audit; original bytes remain immutable."""
from collections import Counter
import json
from pathlib import Path
from ..generate import rows,sha_file,encoded
from services.collector.domeggook_live.domeggook_delivery import load
from .build import source_fingerprint
from .taxonomy import Taxonomy
from .records import validate_record


def verify(source,output,progress=None,sample_path=None,sample_per_leaf=2):
    source=Path(source);output=Path(output);state=load(output/'manifest.json',{})
    if sample_path and any(Path(sample_path).resolve().is_relative_to(p.resolve()) for p in (source,output)):
        raise ValueError('sample_must_be_outside_source_and_immutable_view')
    allocation=state['allocation'];legacy_count=allocation['legacy_count']
    if state['committed']!=allocation['final_count']:raise ValueError('complete_classified_view_required')
    if source_fingerprint(source)!=state['source_fingerprint']:raise ValueError('original_source_was_changed')
    taxonomy=Taxonomy(output/'taxonomy.snapshot.json')
    if sha_file(taxonomy.path)!=state['settings']['taxonomy_sha256']:raise ValueError('taxonomy_hash_mismatch')
    if type(sample_per_leaf) is not int or not 0<=sample_per_leaf<=10:raise ValueError('bounded_sample_required')
    old_rows=iter(rows(source));major=Counter();middle=Counter();leaf=Counter();region=Counter();condition=Counter()
    lineage=Counter();changes=Counter();samples=[];sample_counts=Counter();count=0
    for part_index,part in enumerate(state['parts']):
        name=f'part-{part_index:05d}.jsonl';path=output/name
        if part['name']!=name or part['start']!=count or path.is_symlink() or sha_file(path)!=part['sha256']:
            raise ValueError('classified_part_identity_or_hash_invalid')
        with path.open('r',encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line);validate_record(row,taxonomy,count)
                origin=row['origin']
                if count<legacy_count:
                    old=next(old_rows)
                    for key in ('record_id','source_listing_id','variant_key','url','seller','region','currency','condition'):
                        if row[key]!=old[key]:raise ValueError('legacy_identity_or_native_context_changed')
                    if origin!={'kind':'legacy_enriched','dataset':state['audit']['dataset'],'record_id':old['record_id'],
                                'category':old['category'],'name':old['name'],'price':old['price'],'observation_key':old['observation_key']}:
                        raise ValueError('legacy_provenance_mismatch')
                    expected=f'SYNTHETIC-{state["audit"]["dataset"]}-{count:07d}'
                    if taxonomy.profiles[row['category_ids'][2]]['legacy_category']!=old['category']:
                        raise ValueError('legacy_category_meaning_changed')
                    changes['names_enriched']+=row['name']!=old['name']
                    changes['prices_adjusted']+=row['price']!=old['price']
                    changes['brands_added']+=old.get('brand') in (None,'')
                    changes['specifications_added']+=old.get('specifications') in (None,{})
                else:
                    addition=count-legacy_count
                    expected=f'SYNTHETIC-ADD-{state["artifact"]}-{addition:07d}'
                    if origin!={'kind':'added_balancing','addition_index':addition}:raise ValueError('addition_sequence_mismatch')
                # Exact sequential namespaces prove uniqueness without a million-ID set.
                if row['record_id']!=expected:raise ValueError('duplicate_or_out_of_order_ID')
                major[row['category_path'][0]]+=1;middle[' > '.join(row['category_path'][:2])]+=1
                leaf[' > '.join(row['category_path'])]+=1;region[row['region']]+=1;condition[row['condition']]+=1
                lineage[origin['kind']]+=1
                key=row['category_ids'][2]
                if sample_counts[key]<sample_per_leaf:samples.append(row);sample_counts[key]+=1
                count+=1
        if count!=part['stop']:raise ValueError('part_row_count_mismatch')
        if progress:progress({'validated':count,'target':allocation['final_count']})
    if count!=allocation['final_count'] or set(major)!={taxonomy.nodes[k]['name'] for k in taxonomy.majors}:
        raise ValueError('final_distribution_missing_category')
    if any(v!=allocation['target_per_major'] for v in major.values()) or any(v!=allocation['target_per_leaf'] for v in leaf.values()):
        raise ValueError('unbalanced_final_distribution')
    if len(leaf)!=len(taxonomy.profiles):raise ValueError('missing_leaf_category')
    if source_fingerprint(source)!=state['source_fingerprint']:raise ValueError('source_changed_during_verification')
    if sample_path:
        sample_path=Path(sample_path);sample_path.parent.mkdir(parents=True,exist_ok=True)
        with sample_path.open('wb') as stream:
            for row in samples:stream.write(encoded(row))
    return {'status':'passed','records':count,'legacy_enriched':lineage['legacy_enriched'],
            'additional_records':lineage['added_balancing'],'major_counts':dict(major),
            'middle_counts':dict(middle),'leaf_counts':dict(leaf),'regions':dict(region),'conditions':dict(condition),
            'legacy_changes_in_separate_view':dict(changes),'original_files_unchanged':True,
            'duplicate_IDs':0,'required_fields_missing':0,'category_semantic_violations':0,
            'all_record_hashes_verified':True,'all_rows_synthetic':True,'team_official_category_IDs_assigned':0,
            'taxonomy_status':'provisional_pending_team_approval','sample_rows':len(samples) if sample_path else 0,
            'API_requests':0,'DB_writes':0}
