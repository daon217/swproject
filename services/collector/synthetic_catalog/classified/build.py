"""Read-only legacy audit + resumable materialized classified view and additions."""
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import uuid
from ..generate import rows,encoded,sha_file
from ..test_api import validate_record as validate_legacy
from services.collector.domeggook_live.runtime import FileState
from services.collector.domeggook_live.domeggook_delivery import atomic,load
from .taxonomy import Taxonomy
from .records import render,added_base,VERSION


def source_fingerprint(root):
    root=Path(root)
    return {p.relative_to(root).as_posix():sha_file(p) for p in sorted(root.rglob('*')) if p.is_file()}


def audit_source(root,taxonomy):
    root=Path(root);manifest=load(root/'manifest.json',{})
    if manifest.get('committed')!=manifest.get('settings',{}).get('count'):raise ValueError('complete_legacy_source_required')
    counts=Counter();majors=Counter();leaves=Counter();missing=Counter();regions=Counter();conditions=Counter()
    for index,row in enumerate(rows(root)):
        validate_legacy(row)
        expected=f'SYNTHETIC-{manifest["dataset"]}-{index:07d}'
        if row['record_id']!=expected:raise ValueError('legacy_ID_sequence_invalid')
        # The source is the retained v1 synthetic generator, never live products.
        if row.get('synthetic') is not True or row.get('source')!='synthetic_catalog':raise ValueError('synthetic_source_required')
        category=row['category'];rank=counts[category]
        leaf=taxonomy.select_legacy(category,rank)
        counts[category]+=1;leaves[leaf]+=1;majors[taxonomy.paths[leaf][0]['id']]+=1
        regions[row['region']]+=1;conditions[row['condition']]+=1
        for key in ('brand','specifications','category_path'):
            if row.get(key) in (None,'',{},[]):missing[key]+=1
        if row['name'].startswith('SYNTHETIC '+category+' '):missing['generic_name']+=1
    count=sum(counts.values())
    if count!=manifest['committed']:raise ValueError('legacy_count_mismatch')
    return {'count':count,'dataset':manifest['dataset'],'categories':dict(counts),'majors':dict(majors),
            'leaves':dict(leaves),'missing_fields':dict(missing),'regions':dict(regions),'conditions':dict(conditions),
            'source_manifest_sha256':sha_file(root/'manifest.json')}


def plan(audit,taxonomy,minimum_total=1000000):
    if type(minimum_total) is not int or not 0<=minimum_total<=10000000:raise ValueError('bounded_minimum_total_required')
    # Equal major totals; each major currently has four leaf profiles.
    leaves_by_major={m:[k for k in taxonomy.profiles if taxonomy.paths[k][0]['id']==m] for m in taxonomy.majors}
    sizes={len(v) for v in leaves_by_major.values()}
    if len(sizes)!=1:raise ValueError('equal_leaf_profile_counts_required_for_balanced_plan')
    leaf_count=next(iter(sizes))
    minimum=max(max(audit['majors'].values(),default=0),math.ceil(minimum_total/len(taxonomy.majors)))
    target=math.ceil(minimum/leaf_count)*leaf_count
    # Protect existing leaves too; never downsample or silently reassign a row.
    target=max(target,max(audit['leaves'].values(),default=0)*leaf_count)
    quota={key:target//leaf_count-audit['leaves'].get(key,0) for key in taxonomy.profiles}
    total=target*len(taxonomy.majors)
    if total>10000000:raise ValueError('planned_data_exceeds_local_generation_cap')
    return {'legacy_count':audit['count'],'target_per_major':target,'target_per_leaf':target//leaf_count,
            'additional_by_leaf':quota,'additional_count':sum(quota.values()),'final_count':total,
            'major_count':len(taxonomy.majors),'leaf_count':len(taxonomy.profiles)}


def iter_records(source,taxonomy,audit,allocation,artifact):
    ranks=Counter()
    for index,old in enumerate(rows(source)):
        category=old['category'];leaf=taxonomy.select_legacy(category,ranks[category]);ranks[category]+=1
        origin={'kind':'legacy_enriched','dataset':audit['dataset'],'record_id':old['record_id'],
                'category':category,'name':old['name'],'price':old['price'],'observation_key':old['observation_key']}
        yield render(old,leaf,taxonomy,index,origin)
    addition=0
    for leaf,count in allocation['additional_by_leaf'].items():
        for local in range(count):
            identity=f'SYNTHETIC-ADD-{artifact}-{addition:07d}'
            base=added_base(identity,local,taxonomy.profiles[leaf])
            yield render(base,leaf,taxonomy,audit['count']+addition,{'kind':'added_balancing','addition_index':addition})
            addition+=1


def build(source,output,taxonomy_path=None,minimum_total=1000000,batch_size=10000,max_parts=None,progress=None):
    source=Path(source).resolve();output=Path(output)
    if output.is_symlink():raise ValueError('symlink_output_forbidden')
    output=output.resolve()
    if source.is_relative_to(output) or output.is_relative_to(source):raise ValueError('source_and_view_must_be_separate')
    if any((p/'.git').exists() for p in (output,*output.parents)):raise ValueError('dataset_output_must_be_outside_Git')
    if type(batch_size) is not int or not 1<=batch_size<=10000:raise ValueError('bounded_batch_required')
    if max_parts is not None and (type(max_parts) is not int or max_parts<1):raise ValueError('positive_max_parts_required')
    taxonomy=Taxonomy(taxonomy_path) if taxonomy_path else Taxonomy()
    fingerprint=source_fingerprint(source);audit=audit_source(source,taxonomy);allocation=plan(audit,taxonomy,minimum_total)
    if progress:progress({'phase':'planned','audit':audit,'allocation':allocation})
    settings={'schema_version':VERSION,'source_manifest_sha256':audit['source_manifest_sha256'],
              'taxonomy_sha256':sha_file(taxonomy.path),'minimum_total':minimum_total,'batch_size':batch_size}
    artifact=uuid.uuid5(uuid.NAMESPACE_URL,json.dumps(settings,sort_keys=True)).hex[:16]
    output.mkdir(parents=True,exist_ok=True)
    with FileState(output/'lock').lock():
        path=output/'manifest.json'
        if not path.exists() and any(p.name!='lock' for p in output.iterdir()):raise ValueError('unowned_output_no_overwrite')
        state=load(path,{'settings':settings,'artifact':artifact,'synthetic':True,'audit':audit,'allocation':allocation,
                         'source_fingerprint':fingerprint,'parts':[],'committed':0})
        if state['settings']!=settings or state['artifact']!=artifact or state['source_fingerprint']!=fingerprint:
            raise ValueError('resume_context_or_source_changed_no_reset')
        committed=0
        for index,part in enumerate(state['parts']):
            name=f'part-{index:05d}.jsonl';file=output/name
            if (part['name']!=name or part['start']!=committed or part['stop']!=min(committed+batch_size,allocation['final_count'])
                    or file.is_symlink() or sha_file(file)!=part['sha256']):raise ValueError('classified_part_corruption')
            committed=part['stop']
        if committed!=state['committed']:raise ValueError('classified_manifest_corruption')
        current=f'part-{len(state["parts"]):05d}.jsonl'
        allowed={'lock','manifest.json','taxonomy.snapshot.json',current,current+'.partial'}|{p['name'] for p in state['parts']}
        if any(p.name not in allowed for p in output.iterdir()):raise ValueError('unrecognized_classified_files')
        if not path.exists():
            atomic(path,state);shutil.copyfile(taxonomy.path,output/'taxonomy.snapshot.json')
        elif not (output/'taxonomy.snapshot.json').exists():
            # The manifest pins this public taxonomy if initialization was interrupted.
            shutil.copyfile(taxonomy.path,output/'taxonomy.snapshot.json')
        if sha_file(output/'taxonomy.snapshot.json')!=settings['taxonomy_sha256']:raise ValueError('taxonomy_snapshot_changed')
        stream=iter_records(source,taxonomy,audit,allocation,artifact)
        # Skip deterministic already-committed records without buffering them.
        for _ in range(committed):next(stream)
        written=0
        while committed<allocation['final_count'] and (max_parts is None or written<max_parts):
            name=f'part-{len(state["parts"]):05d}.jsonl';file=output/name;partial=output/(name+'.partial')
            if file.is_symlink() or partial.is_symlink():raise ValueError('symlink_part_forbidden')
            stop=min(committed+batch_size,allocation['final_count']);digest=hashlib.sha256()
            if file.exists():
                for _ in range(committed,stop):digest.update(encoded(next(stream)))
                if sha_file(file)!=digest.hexdigest():raise ValueError('orphan_classified_part_mismatch')
            else:
                with partial.open('wb') as handle:
                    for _ in range(committed,stop):
                        data=encoded(next(stream));handle.write(data);digest.update(data)
                    handle.flush();os.fsync(handle.fileno())
                os.replace(partial,file)
            state['parts'].append({'name':name,'start':committed,'stop':stop,'sha256':digest.hexdigest()})
            state['committed']=stop;atomic(path,state);committed=stop;written+=1
            if progress:progress({'committed':committed,'target':allocation['final_count']})
        if source_fingerprint(source)!=fingerprint:raise ValueError('legacy_source_changed_during_build')
        return {'synthetic':True,'complete':committed==allocation['final_count'],'committed':committed,
                **allocation,'original_files_unchanged':True,'API_requests':0,'DB_writes':0}
