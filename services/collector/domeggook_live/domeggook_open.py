"""Bounded official Open API GET client. No URLs, secrets or product payloads logged."""
import hashlib
import json
import logging
import time
from pathlib import Path
import requests
from .runtime import PACKAGE,STATE_ROOT,read,now
from .progress import save

ROOT=STATE_ROOT/'domeggook_open'
ENDPOINT='https://domeggook.com/ssl/api/'


class SafeAPIError(RuntimeError):pass


def read_key():
    import os
    key=os.environ.get('DOMEGGOOK_API_KEY')
    if key:
        if any(c.isspace() for c in key):raise SafeAPIError('credential_invalid')
        return key
    path=PACKAGE/'.env'
    try:
        with path.open(encoding='utf-8-sig') as stream:
            values=[]
            for line in stream:
                name,sep,value=line.strip().removeprefix('export ').partition('=')
                if sep and name.strip()=='DOMEGGOOK_API_KEY':
                    value=value.strip()
                    if value[:1] in ('\"',"'") and value[-1:]==value[:1]:value=value[1:-1]
                    else:value=value.split(' #',1)[0].strip()
                    values.append(value)
        if len(values)!=1 or not values[0] or any(c.isspace() for c in values[0]):raise SafeAPIError('credential_missing_or_ambiguous')
        return values[0]
    except OSError:raise SafeAPIError('credential_file_unavailable') from None


class OpenClient:
    def __init__(self,cap=None,interval=3,*,ledger_path=None):
        self.__key=read_key();self.interval=max(3,interval)
        from .network import secure_public_session
        self.session=secure_public_session(requests.Session())
        self.session.headers['User-Agent']='KkulPick-OpenAPI-Verification/1.0'
        self.path=ledger_path or ROOT/'request_ledger.json'
        self.state=read(self.path,{'requests':[],'hold':None,'scope':'getItemList/getItemView; max5 distinct listings; internal cap16'})
        authorized_cap=self.state.get('current_internal_cap',16)
        self.cap=min(cap,authorized_cap) if cap is not None else authorized_cap
        if not self.state.get('hold') and any(entry.get('status')=='reserved' and not entry.get('recovered_at') for entry in self.state['requests']):
            self.state['hold']='interrupted_request_outcome_unknown';save(self.path,self.state)
        logging.getLogger('urllib3').setLevel(logging.CRITICAL)
    def recover_uncertain(self, cooldown=7200, current=None):
        """Release only uncertain public GETs after cooldown; retain every debit.

        No response is invented and this method never performs HTTP. Access,
        schema and circuit holds always require review.
        """
        from datetime import datetime, timezone
        from .updates import parsed
        if self.state.get('hold') not in ('uncertain_request_no_auto_resend','interrupted_request_outcome_unknown'):
            return None
        entries=[e for e in self.state['requests'] if e.get('status') in ('reserved','network_error') and not e.get('recovered_at')]
        if not entries or any(e.get('mode') not in ('getItemList','getItemView') or not parsed(e.get('at')) for e in entries):
            raise SafeAPIError('uncertain_ledger_requires_review')
        current=current or datetime.now(timezone.utc)
        delay=max((parsed(e.get('uncertain_at') or e['at']).timestamp()+max(7200,cooldown)-current.timestamp()) for e in entries)
        if delay>0:return delay
        for entry in entries:
            entry.update(recovered_at=current.isoformat(),outcome='uncertain_counted_no_response')
        self.state['hold']=None
        save(self.path,self.state)
        return 0

    def close(self):self.session.close();self.__key=None
    def get(self,mode,**params):
        if mode not in ('getItemList','getItemView'):raise SafeAPIError('private_or_unknown_API_forbidden')
        if self.state.get('hold'):raise SafeAPIError('persisted_access_or_uncertain_hold')
        for attempt in range(2):
            if hasattr(self,'admit_request'):self.admit_request(mode,params)
            if len(self.state['requests'])>=self.cap:raise SafeAPIError('internal_request_budget_exhausted')
            if self.state['requests']:
                from .updates import parsed
                last=parsed(self.state['requests'][-1]['at'])
                if last:time.sleep(max(0,self.interval-(time.time()-last.timestamp())))
            entry={'mode':mode,'item_no':str(params['no']) if 'no' in params else None,'at':now(),'status':'reserved','attempt':attempt+1}
            entry.update({k:v for k,v in getattr(self,'request_context',{}).items() if k in ('queue','cycle_id','task_id')})
            self.state['requests'].append(entry);save(self.path,self.state)
            query={'ver':'4.1' if mode=='getItemList' else '4.6','mode':mode,'aid':self.__key,'market':'dome','om':'json',**params}
            try:
                response=self.session.get(ENDPOINT,params=query,timeout=(10,30),allow_redirects=False)
                entry['status']=response.status_code
                entry['retry_after_present']=bool(response.headers.get('Retry-After'))
                save(self.path,self.state)
                if response.status_code in (401,403,429) or 300<=response.status_code<400:
                    self.state['hold']='access_refused_or_redirect';save(self.path,self.state);raise SafeAPIError('access_refused_or_redirect')
                if response.status_code in (500,502,503,504) and attempt==0:time.sleep(self.interval*2**attempt);continue
                if response.status_code!=200:raise SafeAPIError('HTTP_unsuccessful')
                if len(response.content)>8_000_000:raise SafeAPIError('response_too_large')
                try:data=response.json()
                except ValueError:
                    self.state['hold']='non_JSON_or_challenge';save(self.path,self.state);raise SafeAPIError('non_JSON_response') from None
                if not isinstance(data,dict) or 'domeggook' not in data:
                    entry['outcome']='API_error'
                    self.state['hold']='API_error_or_schema_changed_requires_review';save(self.path,self.state)
                    raise SafeAPIError('API_error_or_schema_changed')
                payload=data['domeggook']
                if not isinstance(payload,dict):
                    entry['outcome']='API_error'
                    self.state['hold']='API_error_or_schema_changed_requires_review';save(self.path,self.state)
                    raise SafeAPIError('API_error_or_schema_changed')
                if 'error' in payload or 'errors' in payload or 'code' in payload or 'code' in data:
                    entry['outcome']='API_error'
                    self.state['hold']='API_reported_error_requires_review';save(self.path,self.state)
                    raise SafeAPIError('API_reported_error')
                entry['outcome']='success';save(self.path,self.state)
                return payload,entry['at']
            except requests.RequestException:
                entry.update(status='network_error',uncertain_at=now());self.state['hold']='uncertain_request_no_auto_resend';save(self.path,self.state)
                raise SafeAPIError('network_error_request_outcome_uncertain') from None
        raise SafeAPIError('transient_retry_exhausted')


def list_items(payload):
    value=payload.get('list',{}).get('item',[])
    if isinstance(value,dict):value=[value]
    if not isinstance(value,list) or any(not isinstance(r,dict) or not str(r.get('no','')).isdigit() for r in value):raise SafeAPIError('listing_schema_changed')
    return value
