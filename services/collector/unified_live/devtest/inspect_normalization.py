"""Explicit authorized lookup -> actual field diagnostics; no backend client.

Input profiles carry existing lookup grants; no grant, default value, or source is
invented by this tool. Raw HTML is never persisted.
"""
import argparse,csv,hashlib,json,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from services.collector.domeggook_live.domeggook_delivery import atomic,utcnow
from services.collector.domeggook_live.runtime import FileState
from services.collector.marketplace_live.probe import lookup_permitted
from services.collector.unified_live.bulk import BatchHTTP,fetch_wait
from services.collector.unified_live.policy import url,dedicated
from services.collector.unified_live.parser import document,normalize
from services.collector.unified_live.analysis import value

def inspect(profiles,root):
 if not isinstance(profiles,list) or len(profiles)>10:raise ValueError('bounded_profiles_required')
 hosts=[p['host'] for p in profiles]
 if len(set(hosts))!=len(hosts):raise ValueError('one_profile_writer_per_host')
 def one(profile):
  host=profile['host'];a=profile['approval'];records=[]
  if dedicated(host):return [{'domain':host,'failure':'dedicated_official_adapter_required','source_requests':0}]
  if a.get('test_allowed') is not True or a.get('allowed_hosts')!=[host] or not a.get('terms_reference') or not lookup_permitted({'rights':a},utcnow()):return [{'domain':host,'failure':'explicit_lookup_grant_required','source_requests':0}]
  source='html_'+hashlib.sha256(host.encode()).hexdigest()[:20]
  cfg={'source':source,'base_url':'https://'+host+'/','enabled':True,'allowed_product_hosts':[host],'currencies':profile['currencies'],'mode':'general','selectors':profile.get('selectors',{}),'requests_per_hour':min(20,a.get('requests_per_hour',12)),'requests_per_24h':min(40,a.get('requests_per_24h',24)),'request_interval_seconds':max(2,a.get('request_interval_seconds',2))}
  if profile.get('storefront_identity'):cfg['storefront_identity']=profile['storefront_identity']
  with FileState(Path(root)/source/'lock').lock():
   http=BatchHTTP(cfg,Path(root)/source,a)
   try:
    for target in profile['urls'][:5]:
     record={'domain':host,'url':target,'sample_kind':profile.get('sample_kind','external_lookup')}
     try:
      target=url(target,host);record['url']=target
      code,text=fetch_wait(http,target,threading.Event());record['HTTP_status']=code
      if code!=200:record['failure']='HTTP_'+str(code)
      else:
       soup=document(text);record['html_sha256']=hashlib.sha256(text.encode()).hexdigest()
       record['native_fields']={f:value(soup,f,cfg['selectors']) for f in ('id','sku','name','price','currency','condition','availability','seller','image','brand','url')}
       record['normalized']=normalize(text,target,utcnow().isoformat(),cfg)
     except Exception:record['failure']='policy_network_or_native_contract_review'
     records.append(record)
   finally:http.close()
  return records
 def safe_one(profile):
  try:return one(profile)
  except Exception:return [{'domain':profile.get('host','invalid_profile'),'failure':'profile_or_lock_review','source_requests':0}]
 results=[]
 with ThreadPoolExecutor(max_workers=3) as pool:
  for rows in pool.map(safe_one,profiles):results.extend(rows)
 return results

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--profiles',required=True);p.add_argument('--state-dir',required=True);p.add_argument('--output',required=True);p.add_argument('--run',action='store_true');a=p.parse_args(argv)
 profiles=json.loads(Path(a.profiles).read_text(encoding='utf-8-sig'))
 if not a.run:print(json.dumps({'profiles':len(profiles),'source_requests':0,'backend_requests':0}));return 0
 results=inspect(profiles,a.state_dir);atomic(a.output,{'records':results,'raw_HTML_persisted':False,'backend_requests':0})
 with Path(str(a.output)+'.csv').open('w',newline='',encoding='utf-8-sig') as f:
  fields=['domain','url','sample_kind','native_fields','missing_fields','normalization_evidence','failure','valid_observation'];writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
  for row in results:
   n=row.get('normalized',{});data={k:row.get(k,'') for k in ('domain','url','sample_kind','failure')};data.update(native_fields=json.dumps(row.get('native_fields',{}),ensure_ascii=False),missing_fields=';'.join(n.get('missing_fields',[])),normalization_evidence=json.dumps(n.get('metadata',{}).get('normalization_evidence',{}),ensure_ascii=False),valid_observation=n.get('observation') is not None);writer.writerow({k:("\'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in data.items()})
 print(json.dumps({'pages':len(results),'valid_Observations':sum(r.get('normalized',{}).get('observation') is not None for r in results),'backend_requests':0}));return 0
if __name__=='__main__':raise SystemExit(main())
