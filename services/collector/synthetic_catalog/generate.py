"""Deterministic streaming JSONL parts; crash-safe manifests, never live products."""
import hashlib
import json
import os
from pathlib import Path
import uuid
from services.collector.domeggook_live.runtime import FileState
from services.collector.domeggook_live.domeggook_delivery import atomic,load

VERSION='synthetic-catalog-v1'
# Native currency ranges for synthetic examples, not exchange-rate conversions.
CATEGORIES=[('laptop',(300000,3000000),(25000,250000)),('phone',(100000,1800000),(10000,150000)),
            ('food',(1500,80000),(300,8000)),('book',(8000,60000),(700,6000)),
            ('clothing',(5000,250000),(500,25000)),('furniture',(30000,1500000),(3000,150000)),
            ('cosmetics',(3000,150000),(500,15000)),('toys',(3000,200000),(300,20000))]


def encoded(row):return (json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')


def record(index,seed,dataset):
    category,won,cents=CATEGORIES[(index//4)%len(CATEGORIES)]
    overseas=bool(index%2);used=bool((index//2)%2) and category not in ('food','cosmetics')
    number=int.from_bytes(hashlib.sha256(f'{seed}:{index}'.encode()).digest()[:8],'big')
    lo,hi=cents if overseas else won
    amount=lo+number%(hi-lo+1)
    if used:amount=max(1,amount*55//100)
    price=f'{amount//100}.{amount%100:02d}' if overseas else str(amount)
    identity=f'SYNTHETIC-{dataset}-{index:07d}'
    row={'schema_version':VERSION,'synthetic':True,'source':'synthetic_catalog',
         'record_id':identity,'source_listing_id':identity,'variant_key':identity+':variant-0',
         'name':f'SYNTHETIC {category} {index:07d}','category':category,
         'region':'overseas' if overseas else 'domestic','condition':'used' if used else 'new',
         'price':price,'currency':'USD' if overseas else 'KRW','seller':f'SYNTHETIC_VENDOR_{number%1000:04d}',
         'url':'https://catalog.example.test/synthetic/'+identity,'availability':'available',
         'stock_quantity':None,'ingredients':None,'allergens':None,'safe_to_consume':None}
    row['observation_key']='SYNTHETIC:'+hashlib.sha256(encoded(row)).hexdigest()
    return row


def sha_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):digest.update(block)
    return digest.hexdigest()


def generate(root,count,seed=42,batch_size=10000,max_parts=None):
    if type(count) is not int or not 1<=count<=1000000 or type(seed) is not int:
        raise ValueError('bounded_integer_count_and_seed_required')
    if type(batch_size) is not int or not 1<=batch_size<=10000:raise ValueError('bounded_batch_required')
    if max_parts is not None and (type(max_parts) is not int or max_parts<1):raise ValueError('positive_max_parts_required')
    root=Path(root)
    if root.is_symlink():raise ValueError('symlink_output_forbidden')
    root=root.resolve()
    root.mkdir(parents=True,exist_ok=True)
    settings={'version':VERSION,'count':count,'seed':seed,'batch_size':batch_size}
    dataset=uuid.uuid5(uuid.NAMESPACE_URL,json.dumps(settings,sort_keys=True)).hex[:16]
    with FileState(root/'lock').lock():
        path=root/'manifest.json'
        if not path.exists() and any(p.name!='lock' for p in root.iterdir()):
            raise ValueError('unowned_output_directory_no_overwrite')
        manifest=load(path,{'settings':settings,'dataset':dataset,'synthetic':True,'parts':[],'committed':0})
        if manifest['settings']!=settings or manifest['dataset']!=dataset or manifest.get('synthetic') is not True:
            raise ValueError('resume_settings_mismatch_no_reset')
        committed=0
        for index,part in enumerate(manifest['parts']):
            expected_name=f'part-{index:05d}.jsonl'
            expected_stop=min(count,committed+batch_size)
            file=root/expected_name
            if (part['name']!=expected_name or part['start']!=committed or part['stop']!=expected_stop
                    or file.is_symlink() or not file.is_file() or sha_file(file)!=part['sha256']):
                raise ValueError('committed_part_corruption_no_reset')
            committed=part['stop']
        if committed!=manifest['committed']:raise ValueError('manifest_progress_mismatch')
        allowed={'manifest.json','lock'}|{p['name'] for p in manifest['parts']}
        # One orphaned complete/partial part can remain after an abrupt exit.
        current=f'part-{len(manifest["parts"]):05d}.jsonl'
        allowed|={current,current+'.partial'}
        if any(p.name not in allowed for p in root.iterdir()):raise ValueError('unrecognized_output_files_no_reset')
        if not path.exists():atomic(path,manifest)
        created=0
        while committed<count and (max_parts is None or created<max_parts):
            index=len(manifest['parts']);name=f'part-{index:05d}.jsonl';file=root/name;partial=root/(name+'.partial')
            if file.is_symlink() or partial.is_symlink():raise ValueError('symlink_part_forbidden')
            stop=min(count,committed+batch_size);digest=hashlib.sha256()
            if file.exists():
                # Adopt only a deterministic complete part, never blindly append/re-send.
                for i in range(committed,stop):digest.update(encoded(record(i,seed,dataset)))
                if sha_file(file)!=digest.hexdigest():raise ValueError('orphan_part_mismatch_no_overwrite')
            else:
                with partial.open('wb') as stream:
                    for i in range(committed,stop):
                        data=encoded(record(i,seed,dataset));stream.write(data);digest.update(data)
                    stream.flush();os.fsync(stream.fileno())
                os.replace(partial,file)
            manifest['parts'].append({'name':name,'start':committed,'stop':stop,'sha256':digest.hexdigest()})
            manifest['committed']=stop;atomic(path,manifest)
            committed=stop;created+=1
        return {'synthetic':True,'dataset':dataset,'committed':committed,'target':count,
                'complete':committed==count,'parts':len(manifest['parts']),'batch_size':batch_size,
                'HTTP_requests':0,'DB_writes':0}


def rows(root):
    root=Path(root);manifest=load(root/'manifest.json',{})
    if manifest.get('synthetic') is not True:raise ValueError('synthetic_manifest_required')
    for index,part in enumerate(manifest['parts']):
        if part['name']!=f'part-{index:05d}.jsonl':raise ValueError('manifest_path_invalid')
        file=root/part['name']
        if file.is_symlink() or sha_file(file)!=part['sha256']:raise ValueError('part_hash_mismatch')
        with file.open('r',encoding='utf-8') as stream:
            for line in stream:yield json.loads(line)
