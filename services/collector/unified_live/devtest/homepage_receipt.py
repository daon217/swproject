"""Disposable synthetic FastAPI/SQLite receipt fixture, not the team backend SQL."""
import json,os,sqlite3,uuid
from pathlib import Path

def server():
 import uvicorn
 from fastapi import FastAPI,Request,HTTPException
 from fastapi.responses import JSONResponse
 from services.collector.unified_live.local_receipt import ReceiptStore
 from services.collector.collector_ops.delivery_contract import ListingExtension
 if os.environ.get('COLLECTOR_NETWORK_LAB')!='synthetic_only':raise RuntimeError('isolated_lab_only')
 app=FastAPI();store=ReceiptStore('/tmp/collector_test_homepage.sqlite',['store.example.test'],['USD'])
 path='/tmp/collector_test_homepage_extensions.sqlite'
 with sqlite3.connect(path) as c:
  c.execute('CREATE TABLE extensions (event TEXT PRIMARY KEY,payload TEXT,state TEXT)');c.execute('CREATE TABLE catalog (identity TEXT PRIMARY KEY,body TEXT)');c.commit()
 failed=False
 def identity(b):return json.dumps([b['source'],b['source_listing_id'],b['variant_key']])
 async def auth(request):
  import secrets
  if not secrets.compare_digest(request.headers.get('Authorization',''),'Bearer '+Path('/tmp/lab-secret/token').read_text()):raise HTTPException(401,'COLLECTOR_AUTH_REQUIRED')
 @app.get('/health')
 async def health():return {'test_fixture':True}
 @app.get('/counts')
 async def counts():
  with sqlite3.connect(path) as c:e=c.execute("SELECT count(*) FROM extensions WHERE state='applied'").fetchone()[0]
  return dict(store.counts(),extension_ACKs=e)
 @app.post('/internal/v2/crawl-runs/{run_id}/observations')
 async def obs(run_id:str,request:Request):
  nonlocal failed
  await auth(request)
  if not failed:failed=True;return JSONResponse(status_code=503,content={'detail':'DATABASE_UNAVAILABLE'},headers={'Retry-After':'1'})
  body=await request.json();code,ack=store.receive(body)
  if ack.get('state')=='applied':
   with sqlite3.connect(path) as c:c.execute('INSERT INTO catalog VALUES(?,?) ON CONFLICT(identity) DO UPDATE SET body=excluded.body',(identity(body),json.dumps(body)));c.commit()
  return JSONResponse(status_code=code,content=ack)
 @app.post('/internal/v2/crawl-runs/{run_id}/extensions')
 async def ext(run_id:str,body:ListingExtension,request:Request):
  await auth(request);b=body.model_dump(mode='json',exclude_unset=True);raw=json.dumps(b,sort_keys=True)
  with sqlite3.connect(path) as c:
   old=c.execute('SELECT payload,state FROM extensions WHERE event=?',(b['observation_key'],)).fetchone()
   if old and old[0]!=raw:raise HTTPException(409,'EXTENSION_PAYLOAD_CONFLICT')
   known=c.execute('SELECT body FROM catalog WHERE identity=?',(identity(b),)).fetchone();state='applied' if known else 'pending'
   c.execute('INSERT INTO extensions VALUES(?,?,?) ON CONFLICT(event) DO UPDATE SET state=excluded.state',(b['observation_key'],raw,state));c.commit()
  return JSONResponse(status_code=202 if state=='pending' else 200 if old else 201,content={'state':state,'change_kind':'updated' if known else 'pending','extension_id':str(uuid.uuid5(uuid.NAMESPACE_DNS,b['observation_key'])),'error_code':None if known else 'OFFER_NOT_YET_OBSERVED'})
 @app.post('/internal/v2/listing-checks')
 async def checks(request:Request):
  await auth(request);b=await request.json();result={'confirmed':0,'mismatch':[],'unknown':[],'rejected':[]}
  if not isinstance(b.get('items'),list) or not 1<=len(b['items'])<=500:raise HTTPException(422,'INVALID_INPUT')
  with sqlite3.connect(path) as c:
   for x in b['items']:
    ident={k:x[k] for k in ('source_listing_id','variant_key')};old=c.execute('SELECT body FROM catalog WHERE identity=?',(identity(dict(x,source=b['source'])),)).fetchone()
    if not old:result['unknown'].append(ident)
    elif any(json.loads(old[0]).get(k)!=x[k] for k in ('price','currency','availability')):result['mismatch'].append(ident)
    else:result['confirmed']+=1
  return result
 uvicorn.run(app,host='127.0.0.1',port=8000,access_log=False,log_level='critical')
if __name__=='__main__':server()
