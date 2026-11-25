"""Reproducible local HTTP/DB smoke benchmark; no external services or paid APIs.

From repository root: python tools/performance.py --allow-write --rows 1000
Synthetic rows use a unique perf_* source. A local owner can remove these with
--cleanup, which only deletes rows from this run. Never load tests against live data.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
import math
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def config(relative):
    p=ROOT/relative
    if not p.exists(): return {}
    return dict(line.strip().split('=',1) for line in p.read_text(encoding='utf-8').splitlines()
                if line.strip() and not line.lstrip().startswith('#'))


def request(base,path,payload=None,token=None):
    start=time.perf_counter()
    headers={'Content-Type':'application/json'}
    if token: headers['Authorization']='Bearer '+token
    data=json.dumps(payload).encode() if payload is not None else None
    try:
        with urlopen(Request(base+path,data=data,headers=headers),timeout=15) as response:
            return response.status,json.load(response),(time.perf_counter()-start)*1000
    except HTTPError as exc:
        return exc.code,{},(time.perf_counter()-start)*1000
    except (URLError,TimeoutError):
        return 0,{},(time.perf_counter()-start)*1000


def measure(name,items,fn,workers,expected,validate=None):
    start=time.perf_counter()
    with ThreadPoolExecutor(workers) as pool:
        results=list(pool.map(fn,items))
    elapsed=time.perf_counter()-start
    timings=sorted(r[2] for r in results)
    percentile=lambda p:round(timings[max(0,math.ceil(len(timings)*p)-1)],2)
    return {'phase':name,'requests':len(results),'errors':sum(r[0] not in expected or
            (validate is not None and not validate(r[1])) for r in results),
            'seconds':round(elapsed,3),'rps':round(len(results)/elapsed,2),
            'p50_ms':percentile(.5),'p95_ms':percentile(.95),'p99_ms':percentile(.99)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-write',action='store_true')
    parser.add_argument('--rows',type=int,default=1000)
    parser.add_argument('--requests',type=int,default=500)
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--base-url')
    parser.add_argument('--output',default='data/benchmarks/latest.json')
    parser.add_argument('--read-p95-ms',type=float,default=1000)
    parser.add_argument('--write-p95-ms',type=float,default=1500)
    parser.add_argument('--cleanup',action='store_true')
    args=parser.parse_args()
    if not args.allow_write: parser.error('--allow-write is required for synthetic data insertion')
    if not 1<=args.rows<=100000 or not 1<=args.requests<=100000 or not 1<=args.workers<=32:
        parser.error('rows/requests must be 1..100000 and workers 1..32')
    cfg=config('services/api/.env')
    base=(args.base_url or 'http://127.0.0.1:'+os.getenv('API_PORT',cfg.get('API_PORT','8000'))).rstrip('/')
    parsed=urlsplit(base)
    if parsed.scheme!='http' or parsed.hostname not in {'localhost','127.0.0.1','::1'} or parsed.username or parsed.password or parsed.path:
        parser.error('benchmark is restricted to a local HTTP development server')
    token=os.getenv('COLLECTOR_TOKEN',cfg.get('COLLECTOR_TOKEN',''))
    if len(token)<32: parser.error('collector token missing; initialize the workspace first')
    source='perf_'+uuid4().hex
    path=f'/internal/v2/crawl-runs/{uuid4()}/observations'
    stamp=datetime.now(UTC)-timedelta(seconds=10)
    def payload(i,update=False):
        return {'schema_version':2,'source':source,'observation_key':f'{i}:{int(update)}',
                'observed_at':(stamp+timedelta(seconds=int(update))).isoformat(),'result':'success',
                'selected_domain':'product','source_listing_id':f'item-{i}','variant_key':'default','condition':'new',
                'name':f'Performance sample {i}','price':'12.50' if update else '10.00','currency':'USD',
                'availability':'available','url':f'https://store.example.test/perf/{source}/{i}',
                'field_presence':['name','price','currency','availability','url']}
    metrics=[]
    applied=lambda body:body.get('state')=='applied' and body.get('error_code') is None
    metrics.append(measure('insert',range(args.rows),lambda i:request(base,path,payload(i),token),args.workers,{201},applied))
    count=min(100,args.rows)
    metrics.append(measure('update',range(count),lambda i:request(base,path,payload(i,True),token),args.workers,{201},applied))
    metrics.append(measure('duplicate',range(count),lambda i:request(base,path,payload(i,True),token),args.workers,{200},applied))
    query='/v2/offers?'+urlencode({'selected_domain':'product','source':source,'limit':20})
    # Warm the read path; network and JSON overhead are deliberately included.
    request(base,query)
    metrics.append(measure('read',range(args.requests),lambda _:request(base,query),args.workers,{200}))
    ids=set(); cursor=None; errors=0
    while True:
        q={'selected_domain':'product','source':source,'limit':100}
        if cursor:q['after']=cursor
        status,body,_=request(base,'/v2/offers?'+urlencode(q))
        if status!=200: errors+=1; break
        incoming={r['offer_id'] for r in body['items']}
        for item in body['items']:
            index=int(item['source_listing_id'].removeprefix('item-'))
            expected_price='12.5000' if index<count else '10.0000'
            if item['price']!=expected_price or item['current_url']!=payload(index)['url']:
                errors+=1
        if ids & incoming:errors+=1;break
        ids.update(incoming)
        cursor=body['next_cursor']
        if cursor is None:break
    passed=not errors and len(ids)==args.rows and all(m['errors']==0 and m['p95_ms']<=(args.read_p95_ms if m['phase']=='read' else args.write_p95_ms) for m in metrics)
    report={'source':source,'created_at':datetime.now(UTC).isoformat(),'rows':args.rows,'workers':args.workers,
            'unique_rows_read':len(ids),'verification_errors':errors,'passed':passed,'metrics':metrics,
            'scope':'local HTTP + PostgreSQL; no OCR, embeddings, payment provider or production sizing',
            'temporary_gates':{'read_p95_ms':args.read_p95_ms,'write_p95_ms':args.write_p95_ms}}
    if args.cleanup:
        # Optional extra: API dev requirements supply psycopg. Scope every deletion
        # to the unique source generated above; never reset databases or other data.
        import psycopg
        dbcfg=config('infra/db/.env')
        with psycopg.connect(host='127.0.0.1',port=int(os.getenv('DB_PORT',dbcfg.get('DB_PORT','5433'))),
             dbname='kkulpick_catalog',user='kkulpick_catalog_app',
             password=os.getenv('CATALOG_APP_PASSWORD',dbcfg.get('CATALOG_APP_PASSWORD',''))) as db:
            report['database_bytes']=db.execute('SELECT pg_database_size(current_database())').fetchone()[0]
            items=[r[0] for r in db.execute('SELECT item_id FROM app.offers WHERE source=%s',(source,))]
            for table in ['offer_changes','price_history','offer_url_history']:
                db.execute(f'DELETE FROM app.{table} WHERE offer_id IN (SELECT offer_id FROM app.offers WHERE source=%s)',(source,))
            db.execute('DELETE FROM app.crawl_observations WHERE source=%s',(source,))
            db.execute('DELETE FROM app.offers WHERE source=%s',(source,))
            db.execute('DELETE FROM app.catalog_items WHERE item_id=ANY(%s)',(items,))
            db.execute('DELETE FROM app.crawl_runs WHERE source=%s',(source,))
            report['cleanup']='removed only this run'
    output=ROOT/args.output
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if summary:=os.getenv('GITHUB_STEP_SUMMARY'):
        with open(summary,'a',encoding='utf-8') as out:
            out.write('\n### Local HTTP/DB smoke benchmark\n\n| Phase | Requests | Errors | p95 ms | RPS |\n|---|---:|---:|---:|---:|\n')
            for m in metrics:out.write(f"| {m['phase']} | {m['requests']} | {m['errors']} | {m['p95_ms']} | {m['rps']} |\n")
            out.write('\nScope: '+report['scope']+'\n')
    return 0 if passed else 1

if __name__=='__main__':
    raise SystemExit(main())
