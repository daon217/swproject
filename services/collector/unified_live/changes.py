"""Content dedup survives restart; pending/uncertain events keep their original key."""
import copy
import hashlib
import json
from pathlib import Path
from services.collector.domeggook_live.domeggook_delivery import atomic,load

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
def rekey(body):
    body.pop('observation_key',None)
    body['observation_key']=body['source']+':'+digest(body)

class ChangeDelivery:
    def __init__(self,box,root):
        self.box=box;self.path=Path(root)/'content_checkpoint.json'
        self.data=load(self.path,{'version':1,'source':box.source,'items':{},'totals':{}})
        if self.data.get('version')!=1 or self.data.get('source')!=box.source:raise ValueError('content_checkpoint_mismatch')
        if any(v.get('key') not in box.state['entries'] for v in self.data['items'].values()):raise ValueError('missing_content_outbox_history_no_reset')
        # Reconcile staged bodies before the worker's first flush can ACK/remove them.
        recovered=False
        for key,entry in box.state['entries'].items():
            body=entry.get('body')
            if not body:continue
            identity=digest([body['source'],body.get('source_listing_id'),body.get('variant_key')])
            if identity not in self.data['items']:
                content={k:v for k,v in body.items() if k not in ('observed_at','observation_key')}
                self.data['items'][identity]={'signature':digest(content),'key':key,'first_seen_at':body['observed_at'],'last_checked_at':body['observed_at']};recovered=True
        if recovered:atomic(self.path,self.data)
    def __getattr__(self,name):return getattr(self.box,name)
    def count(self,k):self.data['totals'][k]=self.data['totals'].get(k,0)+1
    def stage(self,normalized):
        result=self._stage(normalized)
        if result['status'] in ('pending','delivered','unchanged_skipped') and (normalized.get('metadata') or {}).get('matching_profile'):
            from .matching import MatchingStore
            MatchingStore(self.path.parent,self.box.source).record(normalized,getattr(self.box,'cfg',{}))
        return result
    def _stage(self,normalized):
        body=normalized.get('observation')
        if not body:return {'status':'incomplete_native_fields'}
        identity=digest([body['source'],body['source_listing_id'],body['variant_key']])
        content={k:v for k,v in body.items() if k not in ('observed_at','observation_key')}
        signature=digest(content);old=self.data['items'].get(identity)
        entries=self.box.state['entries']
        if old:
            queued=entries.get(old['key'])
            if queued is None:raise ValueError('missing_content_outbox_history_no_reset')
            if queued['status'] in ('quarantine','revoked','held','exhausted','rejected'):return {'status':'previous_event_requires_review'}
            if old['signature']==signature:
                old['last_checked_at']=body['observed_at'];self.count('unchanged');atomic(self.path,self.data)
                return {'status':'unchanged_skipped','observation_key':old['key']}
            if queued['status']!='delivered':return {'status':'prior_event_pending_reobserve_after_ack'}
        # Recover crash between box.stage and saving this checkpoint, preserving event timestamp/key.
        for key,entry in entries.items():
            saved=entry.get('body')
            if saved and digest([saved['source'],saved.get('source_listing_id'),saved.get('variant_key')])==identity:
                previous={k:v for k,v in saved.items() if k not in ('observed_at','observation_key')}
                if digest(previous)==signature and entry['status'] in ('pending','sending','retry_wait','delivered'):
                    normalized=copy.deepcopy(normalized);normalized['observation']=copy.deepcopy(saved);break
        result=self.box.stage(normalized)
        if result['status'] in ('pending','delivered'):
            key=normalized['observation']['observation_key']
            self.data['items'][identity]={'signature':signature,'key':key,'first_seen_at':old['first_seen_at'] if old else body['observed_at'],'last_checked_at':body['observed_at']}
            self.count('updated' if old else 'new');atomic(self.path,self.data)
        return result
