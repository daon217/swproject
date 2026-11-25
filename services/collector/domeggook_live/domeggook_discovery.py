"""Resumable discovery/detail and refresh queues sharing the existing HTTP ledger.

Only query cursors, native IDs, timestamps and outcomes persist. Product values stay in RAM.
"""
import copy
import json
import re
import threading
import os
import uuid
from datetime import datetime,timezone,timedelta
from collections import OrderedDict
from .runtime import PACKAGE,STATE_ROOT,read,now,FileState
from .progress import save,update,replace_with_retry
from .updates import parsed,merge_fields
from .domeggook_open import SafeAPIError,list_items
from .domeggook_operations import (ROOT,OperationsClient,PermittedStore,BudgetWait,budget_delay,interruptible_wait)
from .domeggook_options import option_offers


class LaneExhausted(RuntimeError):pass


def validate_discovery(cfg):
    d=cfg.get('discovery',{});r=cfg.get('refresh',{})
    for obj,keys in ((d,('page_size','max_pages_per_query','requests_per_cycle','list_requests_per_cycle',
                       'pending_detail_capacity','sweep_interval_seconds','max_task_attempts','memory_listing_limit','memory_offer_limit')),
                     (r,('requests_per_cycle','interval_seconds'))):
        if any(type(obj.get(k)) is not int or obj[k]<1 for k in keys):raise SafeAPIError('invalid_queue_configuration')
    if not 1<=d['page_size']<=200 or d['pending_detail_capacity']<d['page_size']:
        raise SafeAPIError('invalid_discovery_page_or_capacity')
    if d['requests_per_cycle']+r['requests_per_cycle']>cfg['requests_per_cycle'] or d['list_requests_per_cycle']>d['requests_per_cycle']:
        raise SafeAPIError('queue_quotas_exceed_shared_cycle_budget')
    if d['sweep_interval_seconds']<3600 or r['interval_seconds']<60 or d['max_task_attempts']>3:
        raise SafeAPIError('queue_retry_or_schedule_outside_reviewed_limits')
    if not isinstance(d.get('keywords'),list) or any(not isinstance(x,str) or not x.strip() for x in d['keywords']):raise SafeAPIError('invalid_keywords')
    if not isinstance(d.get('categories'),list):raise SafeAPIError('invalid_categories')
    for category in d['categories']:
        if not isinstance(category,str) or not re.fullmatch(r'[0-9]{2}(?:_[0-9]{2}){4}',category) or '00' in category.split('_')[:2]:
            raise SafeAPIError('category_requires_documented_middle_or_deeper_code')
    if not d['keywords'] and not d['categories']:raise SafeAPIError('discovery_query_required')
    return cfg


def queries(cfg):
    result=[];seen=set()
    for kind,values in (('kw',cfg['discovery']['keywords']),('ca',cfg['discovery']['categories'])):
        for value in values:
            value=value.strip();key=json.dumps([kind,value],ensure_ascii=False,separators=(',',':'))
            if key not in seen:result.append({'kind':kind,'value':value});seen.add(key)
    return result


class QueueClient(OperationsClient):
    def task(self,lane,cycle,task_id):self.request_context={'queue':lane,'cycle_id':cycle,'task_id':task_id}
    def admit_request(self,mode,params):
        lane=self.request_context['queue'];entries=self.state['requests'][self.cycle_start:]
        if sum(e.get('queue')==lane for e in entries)>=self.cfg[lane]['requests_per_cycle']:raise LaneExhausted(lane)
        if mode=='getItemList' and sum(e.get('task_id','').startswith('page:') for e in entries)>=self.cfg['discovery']['list_requests_per_cycle']:
            raise LaneExhausted('list')
        super().admit_request(mode,params)


def initial_state(cfg):
    previous=read(ROOT/'checkpoint.json',{});original=read(STATE_ROOT/'domeggook_open/checkpoint.json',{})
    ids=list(dict.fromkeys(previous.get('native_ids',[])+original.get('native_ids',[])))
    control={}
    for pid in ids:
        old=previous.get('jobs',{}).get(pid,{})
        control[pid]={'origin':'seed','detail_status':'observed','last_success_at':old.get('last_success_at'),
            'option_codes':old.get('option_codes',[]),'identity_status':old.get('identity_status','quarantine'),
            'first_seen_at':previous.get('listing_observed_at'),'attempts':0}
    return {'version':1,'phase':'idle','cycle':0,'cycle_requests_start':0,'inflight':None,'totals':{},
        'seed_ids':ids,'listings':control,'pending_ids':[],
        'discovery':{'queries':queries(cfg),'query_index':0,'page':1,'sweep':1,'pages':{},'failures':{},
                     'phase':'ready','next_sweep_at':None,'next_kind':'list','last_processed':None}}


def load_state(cfg,path):
    state=read(path,None)
    if state is None:return initial_state(cfg)
    if not isinstance(state,dict) or state.get('version')!=1 or not all(k in state for k in ('listings','pending_ids','discovery','seed_ids','cycle','phase')):
        raise SafeAPIError('invalid_discovery_checkpoint_no_reset')
    if len(state['pending_ids'])!=len(set(state['pending_ids'])) or not set(state['pending_ids']).issubset(state['listings']) or not set(state['seed_ids']).issubset(state['listings']):
        raise SafeAPIError('checkpoint_native_ID_integrity_invalid')
    return state


class DiscoveryRun:
    def __init__(self,cfg,client,root=ROOT):
        self.cfg=validate_discovery(cfg);self.client=client;self.root=root;self.path=root/'discovery_checkpoint.json'
        self.state=load_state(cfg,self.path)
        if self.state['discovery']['queries']!=queries(cfg):raise SafeAPIError('query_plan_changed_keep_checkpoint_or_finish_existing_plan')
        self.stop=threading.Event();self.store=PermittedStore(root,cfg);self.latest_rows=OrderedDict();self.listing_ram={}
        self.recover_inflight()
    def checkpoint(self):
        # One atomic current receipt, not an ever-growing full history per discovered ID.
        self.path.resolve().relative_to(STATE_ROOT)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(self.state,stream,ensure_ascii=False,allow_nan=False);stream.flush();os.fsync(stream.fileno())
        replace_with_retry(temporary,self.path)
    def count(self,key,n=1):self.state['totals'][key]=self.state['totals'].get(key,0)+n
    def recover_inflight(self):
        task=self.state.get('inflight')
        if not task:return
        entries=[e for e in self.client.state['requests'][task['ledger_start']:] if e.get('task_id')==task['task_id']]
        uncertain=[e for e in entries if e.get('status') in ('reserved','network_error')]
        if uncertain:
            if any(not e.get('recovered_at') for e in uncertain):
                if self.client.state.get('hold') in ('uncertain_request_no_auto_resend','interrupted_request_outcome_unknown'):return
                raise SafeAPIError('queue_inflight_request_outcome_unknown')
            if not task.get('failure_recorded'):self._record_failure(task)
            self.count('uncertain_requests_deferred')
        if entries and any(e.get('status')==200 for e in entries):
            if task['kind']=='page':
                # No response payload persisted: do not pretend IDs were checkpointed or resend automatically.
                self.state['recovery_hold']='listing_response_lost_before_ID_checkpoint'
            else:
                job=self.state['listings'][task['pid']]
                job.update(detail_status='response_lost',next_attempt_at=(datetime.now(timezone.utc)+timedelta(seconds=self.cfg['refresh']['interval_seconds'])).isoformat())
                self.count('responses_lost_deferred')
        self.state['inflight']=None;self.checkpoint()
    def page_key(self):
        d=self.state['discovery'];return f"{d['sweep']}:{d['query_index']}:{d['page']}"
    def _page_task(self):
        d=self.state['discovery']
        if d['phase']=='sweep_complete':
            if parsed(d['next_sweep_at'])>datetime.now(timezone.utc):return None
            d.update(query_index=0,page=1,sweep=d['sweep']+1,phase='ready',next_sweep_at=None)
            # Previous sweeps are summarized; current sweep page receipts prevent replay.
            d['pages']={};d['failures']={};self.checkpoint()
        key=self.page_key()
        while key in d['pages']:
            self._advance(d['pages'][key]['terminal']);key=self.page_key()
            if d['phase']=='sweep_complete':return None
        if d['failures'].get(key,0)>=self.cfg['discovery']['max_task_attempts']:
            d['phase']='task_blocked';return None
        query=d['queries'][d['query_index']]
        return {'kind':'page','task_id':'page:'+key,'key':key,
            'params':{query['kind']:query['value'],'sz':self.cfg['discovery']['page_size'],'pg':d['page'],'so':'da'}}
    def _advance(self,terminal):
        d=self.state['discovery']
        if terminal or d['page']>=self.cfg['discovery']['max_pages_per_query']:
            d['query_index']+=1;d['page']=1
        else:d['page']+=1
        if d['query_index']>=len(d['queries']):
            d.update(phase='sweep_complete',next_sweep_at=(datetime.now(timezone.utc)+timedelta(seconds=self.cfg['discovery']['sweep_interval_seconds'])).isoformat())
    def _pending(self):
        current=datetime.now(timezone.utc)
        for pid in self.state['pending_ids']:
            job=self.state['listings'][pid];due=parsed(job.get('next_attempt_at'))
            if job.get('attempts',0)<self.cfg['discovery']['max_task_attempts'] and (not due or due<=current):
                return {'kind':'detail','task_id':'new:'+pid,'pid':pid}
        return None
    def next_discovery(self):
        pending=self._pending();d=self.state['discovery'];entries=self.client.state['requests'][self.state['cycle_requests_start']:]
        list_count=sum(e.get('task_id','').startswith('page:') for e in entries)
        can_list=(list_count<self.cfg['discovery']['list_requests_per_cycle'] and
                  len(self.state['pending_ids'])+self.cfg['discovery']['page_size']<=self.cfg['discovery']['pending_detail_capacity'])
        if d['next_kind']=='list' and can_list:
            page=self._page_task()
            if page:return page
        if pending:return pending
        return self._page_task() if can_list else None
    def next_refresh(self,force=False):
        current=datetime.now(timezone.utc);candidates=[]
        for pid,job in self.state['listings'].items():
            if pid in self.state['pending_ids'] or pid in self.state.get('cycle_refresh_done',[]):continue
            if job.get('attempts',0)>=self.cfg['discovery']['max_task_attempts']:continue
            due=parsed(job.get('next_attempt_at'));last=parsed(job.get('last_success_at'))
            if due and due>current:continue
            if force or not last or current-last>=timedelta(seconds=self.cfg['refresh']['interval_seconds']):
                candidates.append((job.get('last_success_at') or '',pid))
        if not candidates:return None
        pid=min(candidates)[1];return {'kind':'detail','task_id':'refresh:'+pid,'pid':pid}
    def _page_result(self,task,payload,stamp):
        header=payload.get('header') or {}
        if not payload.get('list') and str(header.get('numberOfItems'))=='0':items=[]
        else:items=list_items(payload)
        if len(items)>self.cfg['discovery']['page_size']:raise SafeAPIError('listing_page_larger_than_requested')
        current_page=header.get('currentPage')
        if current_page is not None and str(current_page)!=str(task['params']['pg']):raise SafeAPIError('listing_response_page_mismatch')
        self.count('list_HTTP_success');new=0
        for item in items:
            pid=str(item['no'])
            if pid in self.state['listings']:
                # A repeated listing is not a new product, but its latest list data
                # can help normalize the next scheduled detail refresh. Keep it bounded.
                self.count('duplicate_listing_IDs_removed')
                if pid in self.latest_rows or pid in self.state['pending_ids']:
                    self.listing_ram[pid]=item
                continue
            self.state['listings'][pid]={'origin':'discovery','first_seen_at':stamp,'found_page':task['key'],
                'detail_status':'pending','attempts':0,'option_codes':[],'identity_status':'unconfirmed'}
            self.state['pending_ids'].append(pid);self.listing_ram[pid]=item;new+=1
        self.count('new_listing_IDs',new);self.count('listing_rows_seen',len(items))
        total_pages=header.get('numberOfPages')
        terminal=not items or len(items)<self.cfg['discovery']['page_size']
        if total_pages is not None and str(total_pages).isdigit():terminal=terminal or task['params']['pg']>=int(total_pages)
        d=self.state['discovery'];d['pages'][task['key']]={'observed_at':stamp,'new_IDs':new,'rows':len(items),'terminal':terminal}
        d['last_processed']={'query':copy.deepcopy(d['queries'][d['query_index']]),'page':task['params']['pg'],'observed_at':stamp}
        d['next_kind']='detail';self._advance(terminal)
    def _detail_result(self,task,payload,stamp,lane):
        from .domeggook_pipeline import normalize_detail
        pid=task['pid'];job=self.state['listings'][pid]
        self.count('detail_HTTP_success');self.count(lane+'_detail_HTTP_success')
        try:
            row=normalize_detail(self.listing_ram.get(pid,{'no':pid,'url':'https://domeggook.com/'+pid}),payload,stamp)
            # Manual collection uses an UPSERT on repeated IDs. The live collector
            # instead merges newly observed fields with the current in-memory row,
            # preserving fields absent from a partial refresh and rejecting stale data.
            previous=self.latest_rows.get(pid)
            row,operation,changed=merge_fields(previous,row,(
                'product_name','price','currency','seller','product_url','image_url',
                'category','brand','description','specifications','rating',
                'rating_scale','review_count','condition','shipping_fee',
                'stock_status','stock_quantity','minimum_order_quantity',
                'purchase_unit','availability','unit_price','stock',
            ))
            offers,reasons=option_offers(row)
            for candidate in offers:self.store.put(candidate)
            self.latest_rows[pid]=row;self.latest_rows.move_to_end(pid)
            if operation=='update':self.count('refreshed_product_changes')
            elif operation=='unchanged':self.count('refreshed_product_unchanged')
            while len(self.latest_rows)>self.cfg['discovery']['memory_listing_limit']:self.latest_rows.popitem(last=False)
            while len(self.store.memory)>self.cfg['discovery']['memory_offer_limit']:self.store.memory.pop(next(iter(self.store.memory)))
            self.listing_ram.pop(pid,None)
            if job.get('last_success_at'):self.count('price_stock_requery_success')
            self.count('normalized_observations');self.count('option_identified_observations',len(offers))
            job.update(detail_status='success',last_success_at=stamp,attempts=0,next_attempt_at=None,
                option_codes=[o['variant_key'] for o in offers],identity_status='verified' if offers and not reasons else 'quarantine',
                quarantine_reasons=reasons,has_specifications=bool(row.get('specifications')),
                has_description=bool(row.get('description')),detail_license_usable=row.get('detail_content_license_usable'),
                data_usage_status='memory_only_pending_field_rights')
            if lane=='discovery':self.count('new_detail_normalized')
        except (ValueError,TypeError,KeyError,OverflowError,SafeAPIError):
            job.update(detail_status='quarantine',identity_status='quarantine',quarantine_reasons=['detail_normalization_failed'],last_failure_at=stamp,
                attempts=job.get('attempts',0)+1,next_attempt_at=(datetime.now(timezone.utc)+timedelta(seconds=self.cfg['refresh']['interval_seconds'])).isoformat())
            self.count('normalization_failures')
        if pid in self.state['pending_ids']:self.state['pending_ids'].remove(pid)
        self.listing_ram.pop(pid,None)
        if lane=='refresh':self.state['cycle_refresh_done'].append(pid)
        self.state['discovery']['next_kind']='list'
    def _record_failure(self,task):
        if task['kind']=='page':
            d=self.state['discovery'];d['failures'][task['key']]=d['failures'].get(task['key'],0)+1
        else:
            job=self.state['listings'][task['pid']];job.update(attempts=job.get('attempts',0)+1,detail_status='failed',last_failure_at=now(),
                next_attempt_at=(datetime.now(timezone.utc)+timedelta(seconds=self.cfg['refresh']['interval_seconds'])).isoformat())
        self.count('request_failures')
    def execute(self,task,lane):
        self.client.task(lane,self.state['cycle'],task['task_id'])
        active={**task,'lane':lane,'ledger_start':len(self.client.state['requests'])}
        self.state['inflight']=active;self.checkpoint()
        try:
            payload,stamp=self.client.get('getItemList',**task['params']) if task['kind']=='page' else self.client.get('getItemView',no=task['pid'])
        except (BudgetWait,LaneExhausted):
            sent=self.client.state['requests'][active['ledger_start']:]
            if sent and any(e.get('status')!=200 or e.get('outcome')=='API_error' for e in sent):self._record_failure(task)
            self.state['inflight']=None;self.checkpoint();raise
        except SafeAPIError:
            self._record_failure(task)
            if self.client.state.get('hold') in ('uncertain_request_no_auto_resend','interrupted_request_outcome_unknown'):
                active['failure_recorded']=True
            else:self.state['inflight']=None
            self.checkpoint();raise
        if task['kind']=='page':self._page_result(task,payload,stamp)
        else:self._detail_result(task,payload,stamp,lane)
        # The ID receipt, next cursor, pending IDs and inflight completion commit together.
        self.state['inflight']=None;self.checkpoint()
    def cycle(self,mode='combined'):
        delay=self.client.recover_uncertain(self.cfg['cycle_interval_seconds'])
        if delay:raise BudgetWait(delay,'uncertain_request_cooldown')
        self.recover_inflight()
        if self.state.get('recovery_hold'):raise SafeAPIError('discovery_recovery_hold_response_unavailable')
        if self.state['phase'] in ('idle','cycle_complete'):
            self.state.update(phase='active',cycle=self.state['cycle']+1,cycle_requests_start=len(self.client.state['requests']),cycle_refresh_done=[])
            self.checkpoint()
        self.client.begin_cycle(self.state['cycle_requests_start'])
        for lane in (('discovery',) if mode=='discovery' else ('refresh',) if mode=='refresh' else ('discovery','refresh')):
            while True:
                if self.stop.is_set():return self.report()
                entries=self.client.state['requests'][self.state['cycle_requests_start']:]
                if sum(e.get('queue')==lane for e in entries)>=self.cfg[lane]['requests_per_cycle']:break
                task=self.next_discovery() if lane=='discovery' else self.next_refresh(force=mode=='refresh')
                if not task:break
                try:self.execute(task,lane)
                except LaneExhausted:break
        self.state['phase']='cycle_complete';self.count('cycles_completed')
        self.state['next_cycle_at']=(datetime.now(timezone.utc)+timedelta(seconds=self.cfg['cycle_interval_seconds'])).isoformat();self.checkpoint()
        report=self.report();save(self.root/'discovery_last_run.json',report)
        update('도매꾹 발견/갱신 큐 주기 완료·상품값은 RAM·원장/ID 체크포인트 저장',
            next_action='Start-Domeggook.ps1 -Status 또는 -Watch; 예산 소진 시 다음 허용 시각까지 대기',
            active_phase='domeggook_discovery',domeggook_discovery_metrics=report)
        return report
    def report(self):return status(self.cfg,self.state,self.client.state)


def status(cfg,state=None,ledger=None):
    state=state if state is not None else load_state(cfg,ROOT/'discovery_checkpoint.json')
    ledger=ledger or read(ROOT/'request_ledger.json',{'requests':[]})
    delay,reason=budget_delay(ledger['requests'],cfg,legacy=read(STATE_ROOT/'domeggook_open/request_ledger.json',{'requests':[]})['requests'])
    d=state['discovery'];jobs=state['listings'];cursor=None
    current=datetime.now(timezone.utc)
    due=sum(pid not in state['pending_ids'] and j.get('attempts',0)<cfg['discovery']['max_task_attempts'] and
        (not parsed(j.get('next_attempt_at')) or parsed(j['next_attempt_at'])<=current) and
        (not parsed(j.get('last_success_at')) or current-parsed(j['last_success_at'])>=timedelta(seconds=cfg['refresh']['interval_seconds']))
        for pid,j in jobs.items())
    if d['query_index']<len(d['queries']):cursor={'query':d['queries'][d['query_index']],'page':d['page'],'sweep':d['sweep']}
    return {'at':now(),'source':'domeggook','mode':'LIVE_EPHEMERAL_QUEUES','phase':state['phase'],'cycle':state['cycle'],
        **state['totals'],'HTTP_requests_cumulative_operating':len(ledger['requests']),
        'discovered_new_IDs':sum(j['origin']=='discovery' for j in jobs.values()),'known_IDs_including_seed':len(jobs),
        'new_detail_success_IDs':sum(j['origin']=='discovery' and j.get('last_success_at') is not None for j in jobs.values()),
        'identified_option_tuples':sum(len(j.get('option_codes',[])) for j in jobs.values()),
        'identity_quarantined_products':sum(j.get('identity_status')=='quarantine' for j in jobs.values()),
        'pending_new_details':len(state['pending_ids']),'completed_pages_current_sweep':len(d['pages']),
        'refresh_due_products':due,'pending_detail_capacity':cfg['discovery']['pending_detail_capacity'],
        'cursor':cursor,'last_processed':d.get('last_processed'),'discovery_phase':d['phase'],
        'queue_budgets':{'discovery':cfg['discovery']['requests_per_cycle'],'refresh':cfg['refresh']['requests_per_cycle'],
                        'shared_cycle':cfg['requests_per_cycle'],'shared_hour':cfg['requests_per_hour'],'shared_day':cfg['requests_per_kst_day']},
        'budget_wait_seconds':delay,'next_budget_at':(datetime.now(timezone.utc)+timedelta(seconds=delay)).isoformat(),
        'wait_reason':reason,'provider_hold':ledger.get('hold'),'recovery_hold':state.get('recovery_hold'),
        'next_cycle_at':state.get('next_cycle_at'),
        'permanent_product_storage':False,'backend_enabled':False,'private_API_used':False}


def queue_loop(run,mode,watch=False,cycles=None,wait=interruptible_wait):
    completed=0
    wait=getattr(run,'wait',wait)
    while not run.stop.is_set() and (cycles is None or completed<cycles):
        due=parsed(run.state.get('next_cycle_at'))
        delay=(due-datetime.now(timezone.utc)).total_seconds() if due else 0
        if watch and delay>0:
            wait(delay,run.stop)
            if run.stop.is_set():break
        try:run.cycle(mode);completed+=1
        except BudgetWait as exc:
            save(run.root/'discovery_wait_status.json',{'at':now(),'reason':str(exc),'seconds':exc.seconds,
                'next_allowed_at':(datetime.now(timezone.utc)+timedelta(seconds=exc.seconds)).isoformat()})
            if not watch:return {'status':'budget_wait','completed':completed,'report':run.report()}
            if str(exc)=='cycle_budget_wait':run.state['phase']='cycle_complete';run.checkpoint()
            wait(exc.seconds,run.stop);continue
        except SafeAPIError as exc:
            if not watch:raise
            if run.client.state.get('hold') in ('uncertain_request_no_auto_resend','interrupted_request_outcome_unknown'):
                delay=run.client.recover_uncertain(run.cfg['cycle_interval_seconds'])
                wait(delay or 1,run.stop);continue
            if not run.client.state.get('hold') and str(exc) in ('HTTP_unsuccessful','transient_retry_exhausted'):
                run.state.update(phase='cycle_complete',next_cycle_at=(datetime.now(timezone.utc)+timedelta(seconds=run.cfg['cycle_interval_seconds'])).isoformat())
                run.checkpoint();continue
            raise
        if not watch or cycles is not None and completed>=cycles:break
    return {'status':'stopped' if run.stop.is_set() else 'completed','completed':completed,'report':run.report()}


def dispatch(args,cfg):
    if args.limit is not None:cfg['refresh']['requests_per_cycle']=min(cfg['refresh']['requests_per_cycle'],args.limit)
    cfg=validate_discovery(cfg)
    mode='discovery' if args.discover_once or args.discover_watch else 'combined' if args.watch else 'refresh'
    if args.status or args.dry_run:
        result=status(cfg);result.update(command_mode=mode,HTTP_requests=0,writes=False,key_read=False)
        if cfg.get('backend_enabled') is True:
            outbox=read(ROOT/'backend_delivery/backend_outbox.json',{'entries':{},'hold':None})
            result['backend_enabled']=True
            result['backend_delivery']={'hold':outbox.get('hold'),'states':{}}
            for entry in outbox['entries'].values():
                states=result['backend_delivery']['states'];name=entry['status'];states[name]=states.get(name,0)+1
        if args.dry_run:result['dry_run']=True
        print(json.dumps(result,ensure_ascii=True));return 0
    with FileState(ROOT/'state').lock():
        client=QueueClient(cfg);run=None
        try:
            from .domeggook_watch_delivery import DeliveryDiscoveryRun
            run=DeliveryDiscoveryRun(cfg,client)
            import signal
            previous={}
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGTERM,signal.SIGINT):
                    previous[sig]=signal.signal(sig,lambda *_:run.stop.set())
            try:result=queue_loop(run,mode,args.watch or args.discover_watch,args.cycles)
            except KeyboardInterrupt:
                run.stop.set();run.checkpoint();result={'status':'user_stopped','report':run.report()}
            finally:
                for sig,handler in previous.items():signal.signal(sig,handler)
            print(json.dumps(result,ensure_ascii=True));return 0
        except SafeAPIError as exc:
            save(ROOT/'discovery_safe_failure.json',{'at':now(),'error_code':str(exc),'report':run.report() if run else None})
            print(json.dumps({'safe_error':str(exc)},ensure_ascii=True));return 2
        finally:
            client.close()
            if run and hasattr(run,'delivery'):run.delivery.close()
