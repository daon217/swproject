"""Policy-budgeted Open API loop. Checkpoints contain control metadata, never raw products."""
import argparse
import copy
import hashlib
import json
import math
import os
import threading
import time
import uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .runtime import PACKAGE,STATE_ROOT,read,now,FileState
from .progress import save,update
from .updates import parsed
from .domeggook_open import OpenClient,SafeAPIError,list_items
from .domeggook_options import option_offers
from .product_contract import normalize,merge_offer,offer_key

ROOT=STATE_ROOT/'domeggook_ops'
CONFIG=PACKAGE/'config.json'
KST=timezone(timedelta(hours=9))
CONTENT=('description','description_html','detail_image_urls','detail_image_alt')
CORE=('product_name','price','currency','product_url')
SAFE_FIELDS=CORE+('image_url','seller','manufacturer','model','category','specifications','stock_quantity','stock_status','availability',
    'unit_price','minimum_order_quantity','minimum_purchase_quantity','minimum_product_total','shipping_fee','shipping_conditions',
    'estimated_minimum_checkout_total','checkout_total_is_exact','checkout_total_basis','purchase_unit',
    'option_name','option_price_delta','native_option_status','stock','option_values','observed_at')+CONTENT


def configuration(path=CONFIG):
    cfg=read(path)
    for key in ('limit','requests_per_cycle','requests_per_hour','requests_per_kst_day'):
        if type(cfg.get(key)) is not int or cfg[key]<1:raise SafeAPIError('invalid_operating_budget')
    if cfg['limit']>5 or cfg['requests_per_cycle']>12 or cfg['requests_per_hour']>12 or cfg['requests_per_kst_day']>120:
        raise SafeAPIError('operating_scope_exceeds_reviewed_envelope')
    for key,floor in (('request_interval_seconds',10),('cycle_interval_seconds',60)):
        value=cfg.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<floor:raise SafeAPIError('invalid_operating_interval')
    if not 0<cfg.get('failure_rate_stop',0)<=1 or type(cfg.get('failure_rate_min_requests')) is not int or cfg['failure_rate_min_requests']<1:
        raise SafeAPIError('invalid_failure_policy')
    return cfg


class BudgetWait(SafeAPIError):
    def __init__(self,seconds,reason):super().__init__(reason);self.seconds=max(1,seconds)


def budget_delay(entries,cfg,current=None,legacy=()):
    current=current or datetime.now(timezone.utc);stamps=[parsed(e.get('at')) for e in entries]
    stamps=[s for s in stamps if s is not None]
    all_stamps=stamps+[s for e in legacy if (s:=parsed(e.get('at'))) is not None]
    today=current.astimezone(KST).date()
    if sum(current-s<timedelta(seconds=60) for s in all_stamps)>=180:
        return 60,'provider_minute_budget_wait'
    if sum(s.astimezone(KST).date()==today for s in all_stamps)>=15000:
        midnight=datetime.combine(today+timedelta(days=1),datetime.min.time(),tzinfo=KST)
        return max(1,(midnight-current).total_seconds()),'provider_daily_budget_wait'
    for seconds,cap in ((60,min(180,max(1,int(60/cfg['request_interval_seconds'])))),(3600,cfg['requests_per_hour'])):
        recent=sorted(s for s in stamps if current-s<timedelta(seconds=seconds))
        if len(recent)>=cap:return max(1,(recent[-cap]+timedelta(seconds=seconds)-current).total_seconds()),'window_budget_wait'
    if sum(s.astimezone(KST).date()==today for s in stamps)>=cfg['requests_per_kst_day']:
        midnight=datetime.combine(today+timedelta(days=1),datetime.min.time(),tzinfo=KST)
        return max(1,(midnight-current).total_seconds()),'daily_budget_wait'
    return 0,None


class OperationsClient(OpenClient):
    def __init__(self,cfg,root=ROOT):
        super().__init__(interval=cfg['request_interval_seconds'],ledger_path=root/'request_ledger.json')
        self.cfg=cfg;self.cycle_start=len(self.state['requests'])
        self.legacy=read(STATE_ROOT/'domeggook_open/request_ledger.json',{'requests':[]})['requests']
        if 'current_internal_cap' in self.state:
            self.state['bootstrap_verification_cap']=self.state.pop('current_internal_cap')
        self.state['scope']=cfg['scope']
        self.state['budget_policy']={k:cfg[k] for k in ('requests_per_cycle','requests_per_hour','requests_per_kst_day','request_interval_seconds')}
        save(self.path,self.state)
    def begin_cycle(self,start):self.cycle_start=start
    def admit_request(self,mode,params):
        delay,reason=budget_delay(self.state['requests'],self.cfg,legacy=self.legacy)
        if delay:raise BudgetWait(delay,reason)
        if len(self.state['requests'])-self.cycle_start>=self.cfg['requests_per_cycle']:
            raise BudgetWait(self.cfg['cycle_interval_seconds'],'cycle_budget_wait')
        # Base client still applies its cap; only this one reservation is admitted.
        self.cap=len(self.state['requests'])+1
    def get(self,mode,**params):
        try:return super().get(mode,**params)
        except BudgetWait:raise
        except SafeAPIError:
            entries=self.state['requests'][self.cycle_start:]
            failures=sum(e.get('status')!=200 or e.get('outcome')=='API_error' for e in entries)
            if len(entries)>=self.cfg['failure_rate_min_requests'] and failures/len(entries)>=self.cfg['failure_rate_stop']:
                self.state['hold']='failure_rate_circuit_open';save(self.path,self.state)
            raise


def grant_valid(grants,field,current=None):
    grant=grants.get(field,{})
    return bool(grant.get('storage') is True and grant.get('reference') and parsed(grant.get('expires_at')) and
                parsed(grant['expires_at'])>(current or datetime.now(timezone.utc)))


class PermittedStore:
    """Separate store; never touches original294. No payload history or raw responses."""
    def __init__(self,root,cfg):
        self.path=root/'permitted_offers.json';self.cfg=cfg
        self.memory={k:v for k,r in read(self.path,{'records':{}})['records'].items() if (v:=self.project(r)) is not None}
        if self.path.exists():self._save({'records':self.memory})
    def project(self,row):
        grants=self.cfg.get('storage_grants',{})
        if not all(grant_valid(grants,f) for f in CORE):return None
        result={k:copy.deepcopy(row[k]) for k in ('source','product_id','source_listing_id','variant_key','variant_scope',
            'identity_evidence','evidence','collected_at','updated_at','last_observed_at','field_usage') if k in row}
        # Do not persist a denied body even if a config grant is supplied.
        for field in SAFE_FIELDS:
            if grant_valid(grants,field) and (field not in CONTENT or row.get('detail_content_license_usable') is True):
                result[field]=copy.deepcopy(row.get(field))
        result.update(storage_permission_status='granted',collection_method=row['collection_method'],
            detail_content_license_usable=row.get('detail_content_license_usable'))
        return normalize(result,'domeggook')
    def put(self,row):
        row=normalize(row,'domeggook');key=offer_key(row);previous=self.memory.get(key)
        # Reuse the existing ordering/empty-field guard for mutable fields.
        merged,operation,_=merge_offer(previous,row)
        if not previous or parsed(row['last_observed_at'])>=parsed(previous['last_observed_at']):
            for field in SAFE_FIELDS+('last_observed_at','field_usage','detail_content_license_usable'):
                if row.get(field) not in (None,'',{},[]):merged[field]=copy.deepcopy(row[field])
            if row.get('detail_content_license_usable') is not True:
                for field in CONTENT:merged[field]=[] if field=='detail_image_urls' else {} if field=='detail_image_alt' else None
        self.memory[key]=merged
        projected=self.project(merged)
        state=read(self.path,{'records':{}})
        # Re-evaluate expiry/revocation on every write. Never archive restricted content.
        state['records']={k:v for k,r in state['records'].items() if (v:=self.project(r)) is not None}
        if projected:state['records'][key]=projected
        if projected or self.path.exists():self._save(state)
        return operation,projected is not None
    def _save(self,state):
        self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        with temp.open('x',encoding='utf-8') as stream:json.dump(state,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,self.path)

def interruptible_wait(seconds,stop):
    import time
    deadline=time.monotonic()+seconds
    while not stop.is_set() and time.monotonic()<deadline:
        stop.wait(min(30,max(0,deadline-time.monotonic())))

def integrity(root=ROOT):
    from .domeggook_discovery import validate_discovery,load_state
    validate_discovery(configuration())
    load_state(configuration(),root/'discovery_checkpoint.json')
    ledger=read(root/'request_ledger.json',{'requests':[],'hold':None})
    if not isinstance(ledger.get('requests'),list):raise SafeAPIError('invalid_request_ledger')
    return {'status':'passed','scope':'configuration/checkpoint schema; no product or DB requests',
            'HTTP_requests':0,'key_read':False,'writes':False,'hold':ledger.get('hold')}

def main(argv=None):
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--once',action='store_true');mode.add_argument('--watch',action='store_true');mode.add_argument('--verify',action='store_true')
    mode.add_argument('--discover-once',action='store_true');mode.add_argument('--discover-watch',action='store_true')
    mode.add_argument('--refresh-once',action='store_true');mode.add_argument('--status',action='store_true')
    parser.add_argument('--source',choices=['domeggook'],default='domeggook');parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--detail',action='store_true');parser.add_argument('--interval',type=float)
    parser.add_argument('--cycles',type=int);parser.add_argument('--limit',type=int);parser.add_argument('--backend-config',default=os.environ.get('KKULPICK_BACKEND_CONFIG'));args=parser.parse_args(argv)
    try:
        cfg=configuration()
        if args.backend_config:
            profile=json.loads(Path(args.backend_config).read_text(encoding='utf-8-sig'))
            allowed={'backend_enabled','backend_owner_approved','price_semantics_confirmed','storage_grants','backend_delivery'}
            if not isinstance(profile,dict) or set(profile)-allowed:raise SafeAPIError('backend_profile_cannot_override_collection_budgets')
            cfg.update(profile)
        if args.verify and args.dry_run:raise SafeAPIError('verify_and_dry_run_are_separate_modes')
        if args.limit is not None:
            if not 1<=args.limit<=cfg['limit']:raise SafeAPIError('limit_exceeds_operating_scope')
            cfg['limit']=args.limit
        if args.interval is not None:
            if not math.isfinite(args.interval) or args.interval<60:raise SafeAPIError('cycle_interval_minimum_60_seconds')
            cfg['cycle_interval_seconds']=args.interval
        if args.cycles is not None and args.cycles<1:raise SafeAPIError('positive_cycles_required')
        if not args.verify:
            from .domeggook_discovery import dispatch
            return dispatch(args,cfg)
        result=integrity();print(json.dumps(result,ensure_ascii=True));return int(result['status']!='passed')
    except SafeAPIError as exc:
        print(json.dumps({'safe_error':str(exc)},ensure_ascii=True));return 2
    except Exception:
        print(json.dumps({'safe_error':'operation_failed_no_sensitive_traceback'}));return 2
