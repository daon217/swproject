"""Offline queue recovery; stop only this collector first. Default is read-only plan."""
import argparse,copy
from pathlib import Path
from services.collector.domeggook_live.domeggook_delivery import load,atomic,digest,utcnow
from .delivery_contract import catalog_review

def recover(path,cfg,apply=False):
    path=Path(path);state=load(path,None)
    if not isinstance(state,dict) or not state.get('entries'):raise ValueError('existing_outbox_required')
    restored=[]
    for key,e in state['entries'].items():
        fields=e.get('error_fields') or []
        native={x[-1] for x in fields if isinstance(x,list) and x}
        # A 422 is not assumed to be a catalog error: only explicit URL/currency locations qualify.
        if e.get('last_status')!=422 or e.get('status')!='rejected' or not native or not native<={'url','currency'} or 'body' not in e:continue
        body=e['body']
        if digest(body)!=e['sha256']:raise ValueError('immutable_body_integrity_review_required')
        if not cfg.get('backend_catalog') or catalog_review(body,cfg) is not None:continue
        if body['source']!=cfg['source']:raise ValueError('outbox_source_mismatch')
        restored.append(key)
        if apply:e.update(status='pending',attempts=0);e.pop('next_attempt_at',None)
    if apply and restored:
        backup=path.with_name(path.name+'.before-catalog-recovery-'+utcnow().strftime('%Y%m%dT%H%M%S%f')+'.json')
        if backup.exists():raise ValueError('backup_collision')
        atomic(backup,load(path,None));atomic(path,state)
    return {'mode':'apply' if apply else 'plan','restorable_catalog_events':len(restored),'HTTP_requests':0,'DB_writes':0,'integrity_holds_unchanged':True}

def main():
    import json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outbox',required=True);p.add_argument('--config',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    cfg=json.loads(Path(a.config).read_text(encoding='utf-8-sig'));print(json.dumps(recover(a.outbox,cfg,a.apply)))
if __name__=='__main__':main()
