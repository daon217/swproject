"""Idempotent loopback-only synthetic uploader. Uncertain POSTs remain held."""
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import requests
from requests.adapters import HTTPAdapter
from services.collector.domeggook_live.runtime import FileState
from services.collector.domeggook_live.domeggook_delivery import atomic,load
from .generate import rows
from .test_api import validate_record


def target(url,namespace,environment):
    p=urlsplit(url)
    if (environment!='isolated_test' or not re.fullmatch(r'synthetic_[a-z0-9_]+',namespace)
            or p.scheme!='http' or p.hostname!='127.0.0.1' or not p.port or p.port<1024
            or p.path or p.username or p.password or p.query or p.fragment):
        raise ValueError('explicit_isolated_loopback_test_API_required')
    return url


def batches(root,namespace,size=1000):
    if type(size) is not int or not 1<=size<=1000:raise ValueError('bounded_test_batch_required')
    block=[]
    for row in rows(root):
        validate_record(row);block.append(row)
        if len(block)==size:
            yield batch(block,namespace);block=[]
    if block:yield batch(block,namespace)


def batch(block,namespace):
    digest=hashlib.sha256(json.dumps(block,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'batch_key':'SYNTHETIC:'+digest,'namespace':namespace,'records':block}


class LoopbackAPI:
    def __init__(self,url,namespace,environment,token):
        self.url=target(url,namespace,environment)
        if not token or any(not 33<=ord(c)<=126 for c in token):raise ValueError('test_token_required')
        self.session=requests.Session();self.session.trust_env=False
        self.session.mount('http://',HTTPAdapter(max_retries=0))
        self.session.headers['Authorization']='Bearer '+token
    def __call__(self,payload):
        with self.session.post(self.url+'/test/synthetic-import',json=payload,timeout=(3,30),allow_redirects=False) as response:
            if response.status_code!=200:return response.status_code,{}
            return response.status_code,response.json()
    def close(self):self.session.close()


def deliver(root,state_root,url,namespace,environment,api=None):
    target(url,namespace,environment)
    manifest=load(Path(root)/'manifest.json',{})
    if manifest.get('synthetic') is not True or manifest.get('committed')!=manifest.get('settings',{}).get('count'):
        raise ValueError('completed_synthetic_dataset_required')
    state_root=Path(state_root);path=state_root/'test_import_ledger.json'
    identity={'url':url,'namespace':namespace,'dataset':str(Path(root).resolve())}
    with FileState(state_root/'lock').lock():
        ledger=load(path,{'identity':identity,'entries':{}})
        if ledger['identity']!=identity:raise ValueError('test_loader_identity_mismatch_no_reset')
        owned=api is None
        if owned:api=LoopbackAPI(url,namespace,environment,os.environ.get('KKULPICK_SYNTHETIC_TEST_TOKEN'))
        try:
            for payload in batches(root,namespace):
                key=payload['batch_key'];old=ledger['entries'].get(key)
                if old:
                    if old['state']=='acked':continue
                    return {'status':'held','reason':'existing_unacknowledged_batch_requires_receipt_review','batch_key':key}
                entry={'state':'reserved','count':len(payload['records']),'sha256':key.removeprefix('SYNTHETIC:')}
                ledger['entries'][key]=entry;atomic(path,ledger)
                try:code,receipt=api(payload)
                except Exception:
                    entry['state']='uncertain';atomic(path,ledger)
                    return {'status':'held','reason':'request_outcome_uncertain_no_auto_resend','batch_key':key}
                if (code==200 and receipt.get('state') in ('applied','duplicate') and receipt.get('batch_key')==key
                        and receipt.get('sha256')==entry['sha256'] and receipt.get('count')==entry['count']):
                    entry['state']='acked';atomic(path,ledger)
                else:
                    entry.update(state='held',HTTP_status=code);atomic(path,ledger)
                    return {'status':'held','reason':'test_API_ack_required','batch_key':key,'HTTP_status':code}
            return {'status':'complete','synthetic':True,'acked_records':sum(e['count'] for e in ledger['entries'].values() if e['state']=='acked')}
        finally:
            if owned:api.close()


def reconcile(state_root,receipt):
    """Explicit operator-supplied authenticated receipt, no new POST on uncertainty."""
    path=Path(state_root)/'test_import_ledger.json'
    with FileState(Path(state_root)/'lock').lock():
        ledger=load(path,{});entry=ledger['entries'][receipt['batch_key']]
        if (receipt.get('state') not in ('applied','duplicate') or receipt.get('sha256')!=entry['sha256']
                or receipt.get('count')!=entry['count']):raise ValueError('receipt_mismatch')
        entry['state']='acked';atomic(path,ledger)


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',required=True);p.add_argument('--state-dir',required=True)
    p.add_argument('--url',required=True);p.add_argument('--namespace',required=True)
    p.add_argument('--environment',choices=['isolated_test'],required=True)
    p.add_argument('--send',action='store_true')
    p.add_argument('--receipt-file')
    args=p.parse_args()
    try:
        target(args.url,args.namespace,args.environment)
        if args.receipt_file:
            reconcile(args.state_dir,load(args.receipt_file,{}));result={'status':'receipt_reconciled','POST_requests':0}
        elif args.send:result=deliver(args.dataset,args.state_dir,args.url,args.namespace,args.environment)
        else:result={'status':'plan','synthetic':True,'POST_requests':0,'requires_explicit_send':True}
        print(json.dumps(result));return int(result.get('status')=='held')
    except Exception:
        print(json.dumps({'status':'blocked','reason':'isolated_target_dataset_or_receipt_invalid','automatic_reset':False}));return 2


if __name__=='__main__':raise SystemExit(main())
