"""Bounded lookup only. No backend client, outbox or product export in live mode."""
import argparse
import copy
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import time
import uuid
from decimal import Decimal
from services.collector.domeggook_live.runtime import FileState
from services.collector.domeggook_live.domeggook_delivery import atomic,load
from .config import SOURCES,load_config,stamp,validate
from .adapters import Adapter,credential
from .http import ProviderHTTP,ProviderError,Pause

KEYS={'yes24_api':['YES24_API_KEY'],'searchapi_google_shopping':['SEARCHAPI_API_KEY'],
      'ebay_browse':['EBAY_CLIENT_ID','EBAY_CLIENT_SECRET'],'serper_google_shopping':['SERPER_API_KEY']}
FIELDS=('name','price','currency','condition','availability','seller','url')

def lookup_permitted(cfg,current):
    grant=cfg.get('rights',{})
    try:
        return bool(grant.get('reference') and 'lookup' in grant.get('allowed_uses',[]) and stamp(grant['expires_at'])>current)
    except (KeyError,TypeError,ValueError,AttributeError):return False

class LookupHTTP(ProviderHTTP):
    def permitted(self):return self.cfg['enabled'] and lookup_permitted(self.cfg,self.clock())

def safe_reason(exc):
    # Never echo an exception containing request URLs, response bodies or keys.
    known={'credentials_missing_or_invalid','provider_permission_required','provider_hold_requires_review',
        'provider_access_refused','provider_HTTP_error','provider_invalid_JSON','provider_error_or_schema',
        'provider_response_too_large','provider_credit_or_cost_budget_exhausted','detail_identity_mismatch',
        'YES24_response_invalid','YES24_detail_schema_invalid','YES24_page_mismatch',
        'Shopping_response_schema_invalid','eBay_response_schema_invalid','native_identity_invalid',
        'Serper_response_schema_invalid','Serper_probe_one_page_only','provider_credit_reservation_exceeded'}
    text=str(exc)
    return text if text in known else 'provider_lookup_or_schema_failed'

def inspect_item(adapter,raw):
    try:normalized=adapter.normalize(raw,datetime.now(timezone.utc).isoformat())
    except (ValueError,TypeError,KeyError,ArithmeticError,AttributeError):
        return {'status':'held','checks':{f:False for f in FIELDS},'reasons':['normalization_rejected'],'observation_ready':False},None
    checks={f:normalized.get(f) is not None and normalized.get(f)!='' for f in FIELDS}
    checks['condition']=normalized.get('condition') in ('new','used')
    checks['availability']=normalized.get('availability') in ('available','out_of_stock','ended')
    checks['seller']=isinstance(normalized.get('seller'),str) and bool(normalized['seller'].strip())
    missing=list(normalized.get('missing_fields',[]))
    missing.extend(f for f,okay in checks.items() if not okay)
    reasons=['missing_'+f for f in sorted(set(missing))]
    if normalized.get('observation') is None and not reasons:reasons=['incomplete_observation']
    if normalized.get('source')=='ebay_browse':
        if not checks['condition']:reasons.append(normalized['condition_reason'])
        if not checks['availability']:reasons.append(normalized['availability_reason'])
    result = {'status':'held' if reasons else 'success','checks':checks,'reasons':reasons,
            'observation_ready':normalized.get('observation') is not None}
    if normalized.get('source')=='ebay_browse':
        # Fixed enums and booleans only: no product data or credentials in summaries.
        result['evidence']={k:normalized[k] for k in ('condition_detail','condition_reason',
            'quantity_kind','purchase_available','availability_reason')}
        result['evidence']['exact_stock_known']=False
    return result,normalized

def bounded_lookup(adapter,cfg,maximum=3,wait=None,on_result=None):
    if type(maximum) is not int or not 1<=maximum<=3:raise ValueError('max_products_1_to_3_required')
    summary={'source':cfg['source'],'mode':'lookup_only','max_products':maximum,'provider_search_calls':0,
             'provider_detail_calls':0,'returned_count':0,'selected_count':0,'ignored_count':0,'success':0,'failed':0,'held':0,
             'products':[],'hold_reasons':{},'backend_HTTP_requests':0,'products_persisted':False,
             'last_collection_at':None,'last_success_at':None,'last_failure_at':None}
    def call(function,*args):
        # Waiting for a local request interval is not a resend. A failed HTTP
        # request, provider Retry-After or uncertain outcome ends this probe.
        for _ in range(8):
            try:return function(*args)
            except Pause as exc:
                seconds=(exc.until-datetime.now(timezone.utc)).total_seconds()
                if str(exc)!='request_interval_wait' or wait is None or not 0<seconds<=60:raise
                wait(seconds)
        raise ProviderError('probe_interval_wait_exhausted')
    try:
        summary['provider_search_calls']=1
        rows,_=call(adapter.search,cfg['queries'][0],1)
    except Pause as exc:
        summary.update(failed=1,status='deferred',hold_reasons={str(exc):1},next_allowed_at=exc.until.isoformat(),
                       last_failure_at=datetime.now(timezone.utc).isoformat())
        return summary
    except Exception as exc:
        summary.update(failed=1,status='failed',hold_reasons={safe_reason(exc):1},last_failure_at=datetime.now(timezone.utc).isoformat())
        return summary
    summary['returned_count']=len(rows)
    selected=[];seen=set()
    # Slice before examining row contents: unselected SearchAPI rows are not
    # normalized, followed, exported or placed in an outbox.
    for row in rows[:maximum]:
        if cfg['source']=='serper_google_shopping':
            # A catalogue ID can have multiple merchants; missing IDs are held
            # individually rather than silently dropped by deduplication.
            identity=(row.get('productId'),row.get('source'),row.get('link'))
            if identity==(None,None,None):identity=('missing',len(selected))
        else:identity=str(row.get('itemId')) if cfg['source']!='searchapi_google_shopping' else str(row.get('product_id'))
        if identity in seen:continue
        seen.add(identity);selected.append((identity,row))
    summary['selected_count']=len(selected);summary['ignored_count']=len(rows)-len(selected)
    if not selected:summary['hold_reasons']['no_products_returned']=1
    for index,(identity,row) in enumerate(selected,1):
        try:
            if cfg['source']=='yes24_api':
                if not identity.isdigit():raise ProviderError('native_identity_invalid')
                row=call(adapter.detail,identity)
            elif cfg['source']=='ebay_browse':
                if not re.fullmatch(r'v1\|\d+\|\d+',identity):raise ProviderError('native_identity_invalid')
                summary['provider_detail_calls']+=1
                row=call(adapter.detail,identity)
            result,normalized=inspect_item(adapter,row)
        except Pause as exc:
            summary['failed']+=1;summary['hold_reasons'][str(exc)]=summary['hold_reasons'].get(str(exc),0)+1
            summary['next_allowed_at']=exc.until.isoformat()
            summary['last_failure_at']=datetime.now(timezone.utc).isoformat()
            # Never attempt more products after quota/refusal/uncertainty.
            remaining=len(selected)-index
            summary['held']+=remaining
            if remaining:summary['hold_reasons']['unqueried_after_provider_stop']=remaining
            break
        except Exception as exc:
            reason=safe_reason(exc);summary['failed']+=1
            summary['hold_reasons'][reason]=summary['hold_reasons'].get(reason,0)+1
            summary['last_failure_at']=datetime.now(timezone.utc).isoformat()
            summary['held']+=len(selected)-index
            if len(selected)>index:summary['hold_reasons']['unqueried_after_provider_stop']=len(selected)-index
            break
        result['index']=index;summary['products'].append(result)
        summary[result['status']]+=1;summary['last_collection_at']=datetime.now(timezone.utc).isoformat()
        if result['status']=='success':summary['last_success_at']=summary['last_collection_at']
        else:
            for reason in result['reasons']:summary['hold_reasons'][reason]=summary['hold_reasons'].get(reason,0)+1
        if on_result is not None:on_result(result,normalized)
    summary['status']='passed' if summary['success'] and not summary['failed'] and not summary['held'] else 'review_required'
    return summary

def plan(cfg,maximum):
    live=copy.deepcopy(cfg);live['enabled']=True;live['page_size']=maximum
    reasons=[]
    try:validate(live)
    except ValueError:reasons.append('invalid_live_budget_or_configuration')
    if not lookup_permitted(live,datetime.now(timezone.utc)):reasons.append('lookup_grant_required')
    presence={name:bool(os.environ.get(name)) for name in KEYS[cfg['source']]}
    if not all(presence.values()):reasons.append('environment_credentials_missing')
    result={'source':cfg['source'],'mode':'plan','ready':not reasons,'reasons':reasons,'credentials_present':presence,
            'max_products_inspected':maximum,'provider_HTTP_requests':0,'backend_HTTP_requests':0,
            'sample_policy':'one_search_first_three_only' if cfg['source'] in ('searchapi_google_shopping','serper_google_shopping') else 'bounded_search_and_detail',
            'YES24_DB_allowed':False}
    if cfg['source']=='ebay_browse':
        result.update(environment='Production',endpoint='https://api.ebay.com/buy/browse/v1/',
            marketplace=cfg.get('marketplace_id','EBAY_US'),planned_oauth_requests_max=1,
            planned_search_requests=1,planned_detail_requests_max=maximum,
            planned_HTTP_requests_max=maximum+2,query=cfg['queries'][0],retries=0,
            cost_per_request_configured=cfg['cost_per_request'],cost_currency=cfg.get('cost_currency'),
            cost_note='configured_budget_not_provider_billing_confirmation')
        if any(os.environ.get(name) and os.environ[name] in result['query'] for name in KEYS['ebay_browse']):
            result['query']='[withheld_possible_credential]'
        if cfg['requests_per_cycle'] < maximum+2:result['ready']=False;result['reasons'].append('lookup_request_budget_too_small')
    if cfg['source']=='serper_google_shopping':
        query=cfg['queries'][0];key=os.environ.get('SERPER_API_KEY','')
        if key and key in query:query='[withheld_possible_credential]'
        cost=Decimal(cfg['cost_per_request'])
        result.update(endpoint='https://google.serper.dev/shopping',method='POST',auth_header='X-API-KEY',
                      planned_search_requests=1,query=query,cost_upper_bound=str(cost) if cost>0 else None,
                      credits_reserved_per_request=cfg.get('credits_per_request'),
                      cost_currency=cfg.get('cost_currency'),product_currencies=cfg['currencies'],
                      additional_pages=0,detail_requests=0)
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',choices=SOURCES,required=True)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--plan',action='store_true')
    mode.add_argument('--mock',action='store_true');mode.add_argument('--live',action='store_true')
    parser.add_argument('--max-products',type=int,choices=(1,2,3),default=3)
    parser.add_argument('--config',default=os.environ.get('KKULPICK_MARKETPLACE_CONFIG'))
    parser.add_argument('--state-dir',default=os.environ.get('KKULPICK_MARKETPLACE_STATE_DIR'))
    parser.add_argument('--env-file',help='Explicit dotenv file; reads only credentials for Serper or eBay')
    args=parser.parse_args(argv)
    try:
        if args.mock:
            from .synthetic import run_mock
            if not args.state_dir:raise ValueError('mock_state_directory_required')
            result=run_mock(args.source,args.state_dir,args.max_products)
            print(json.dumps(result,ensure_ascii=True));return 0
        if args.source=='searchapi_google_shopping':
            print(json.dumps({'source':args.source,'ready':False,'status':'retired','reason':'use_serper_google_shopping',
                              'provider_HTTP_requests':0,'backend_HTTP_requests':0}));return 2
        if args.env_file:
            if args.source=='ebay_browse':
                from .ebay_credentials import load_ebay_env
                load_ebay_env(args.env_file)
            elif args.source=='serper_google_shopping':
                from .credentials import load_serper_env
                load_serper_env(args.env_file)
            else:raise ValueError('env_file_unsupported_source')
        if not args.config:raise ValueError('configuration_required')
        configs=load_config(args.config);cfg=next(c for c in configs if c['source']==args.source)
        result=plan(cfg,args.max_products)
        if not args.live:print(json.dumps(result));return int(not result['ready'])
        if not args.state_dir or not result['ready']:
            result['mode']='live_preflight_blocked';print(json.dumps(result));return 2
        live=copy.deepcopy(cfg);live['enabled']=True;live['page_size']=args.max_products
        # Explicitly ignore all backend settings; no Outbox is instantiated.
        live['backend_enabled']=False;live['backend_owner_approved']=False
        root=Path(args.state_dir).resolve()/args.source
        with FileState(root/'lock').lock():
            http=LookupHTTP(live,root)
            http.cycle_id='lookup:'+str(uuid.uuid4());http.task_id=http.cycle_id
            try:
                before=len(http.state['requests'])
                result=bounded_lookup(Adapter(live,http,retry_auth=args.source!='ebay_browse'),live,args.max_products,wait=time.sleep)
                result['provider_HTTP_attempts']=len(http.state['requests'])-before
                result['provider_HTTP_attempts_cumulative']=len(http.state['requests'])
                # Summary contains field checks and counts only, never values.
                atomic(root/'last_lookup_summary.json',result)
            finally:http.close()
        print(json.dumps(result,ensure_ascii=True));return int(result['status']!='passed')
    except Exception:
        print(json.dumps({'status':'blocked','reason':'probe_configuration_or_state_requires_review','request_history_preserved_in_provider_ledger':True}));return 2

if __name__=='__main__':raise SystemExit(main())
