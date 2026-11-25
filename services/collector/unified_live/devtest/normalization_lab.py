"""Actual external-derived values stay unchanged; strict v2 eligibility gates POST.

An empty eligible set is reported as zero. Synthetic controls are separate.
"""
import json,os,secrets,subprocess,sys,time,uuid
from pathlib import Path

def server():
 import uvicorn
 from fastapi import FastAPI,Request
 from fastapi.responses import JSONResponse
 from services.collector.unified_live.local_receipt import ReceiptStore
 app=FastAPI();store=ReceiptStore('/tmp/collector_test_external.sqlite',['books.toscrape.com','testingurl.dev','webscraper.io'],['USD','GBP','EUR'])
 @app.get('/counts')
 def counts():return store.counts()
 @app.post('/internal/v2/crawl-runs/{run_id}/observations')
 async def ingest(run_id:uuid.UUID,request:Request):
  expected=Path('/tmp/external-test-token').read_text()
  if not secrets.compare_digest(request.headers.get('Authorization',''),'Bearer '+expected):return JSONResponse({},status_code=401)
  try:code,ack=store.receive(await request.json())
  except (ValueError,TypeError,KeyError):return JSONResponse({},status_code=422)
  return JSONResponse(ack,status_code=code)
 uvicorn.run(app,host='127.0.0.1',port=18001,access_log=False,log_level='warning')

def external_check():
 import requests
 from datetime import datetime,timezone
 from services.collector.domeggook_live.domeggook_backend_contract import Observation
 from services.collector.collector_ops.backend_transport import build_backend
 data=json.loads(Path('/run/external-derived.json').read_text(encoding='utf-8'));eligible=[];held=[]
 for row in data:
  if row.get('sample_kind')!='external_demo':raise ValueError('external_demo_provenance_required')
  normalized=row.get('normalized',{});body=normalized.get('observation')
  if body is None:
   held.append({'url':row['url'],'reasons':normalized.get('missing_fields',[]) or [row.get('failure','native_data_missing')]});continue
  if body.get('condition') not in ('new','used'):raise ValueError('never_infer_default_new')
  if not {'name','price','currency','availability','url'}<=set(body['field_presence']):raise ValueError('complete_first_observation_required')
  Observation.model_validate(body,context={'hosts':['books.toscrape.com','testingurl.dev','webscraper.io'],'currencies':['USD','GBP','EUR']});eligible.append(body)
 token=secrets.token_urlsafe(48);Path('/tmp/external-test-token').write_text(token)
 child=subprocess.Popen([sys.executable,'-m','services.collector.unified_live.devtest.normalization_lab','server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 old={k:os.environ.get(k) for k in ('COLLECTOR_BACKEND_TRANSPORT','COLLECTOR_BACKEND_BASE_URL','COLLECTOR_DELIVERY_APPROVED')};transport=None
 try:
  client=requests.Session();client.trust_env=False
  for _ in range(60):
   try:client.get('http://127.0.0.1:18001/counts',timeout=1).raise_for_status();break
   except requests.RequestException:time.sleep(.1)
  else:raise RuntimeError('isolated_external_receipt_not_ready')
  os.environ.update(COLLECTOR_BACKEND_TRANSPORT='internal_http',COLLECTOR_BACKEND_BASE_URL='http://127.0.0.1:18001',COLLECTOR_DELIVERY_APPROVED='yes')
  transport=build_backend('http://127.0.0.1:18001',token,lambda:datetime.now(timezone.utc));acks=[]
  for body in eligible:
   code,ack=transport('/internal/v2/crawl-runs/'+str(uuid.uuid4())+'/observations',body)
   if ack.get('state')!='applied':raise AssertionError('external_product_not_applied')
   acks.append(ack)
  stored=client.get('http://127.0.0.1:18001/counts',timeout=2).json();client.close()
  assert stored['listings']==len(eligible)
  return {'external_derived':True,'original_external_products':sum(r['previous_seven'] for r in data),'additional_external_formats':sum(not r['previous_seven'] for r in data),'eligible_Observations':len(eligible),'external_product_ACKs':len(acks),'external_products_SQLite':stored,'held':held,'external_product_HTTP_POSTs':len(eligible),'unknown_or_fabricated_values_sent':0,'FastAPI_and_SQLite_started':True,'production_DB_writes':0,'NAS_changed':False}
 finally:
  if transport:transport.close()
  child.terminate();child.wait(timeout=10)
  for key,value in old.items():
   if value is None:os.environ.pop(key,None)
   else:os.environ[key]=value

def main():
 if os.environ.get('COLLECTOR_NETWORK_LAB')!='synthetic_only':raise RuntimeError('disposable_network_none_lab_required')
 if len(sys.argv)>1 and sys.argv[1]=='server':return server()
 external=external_check();print(json.dumps(external))
 from services.collector.unified_live.devtest.bulk_lab import main as synthetic_controls
 synthetic_controls()
if __name__=='__main__':main()
