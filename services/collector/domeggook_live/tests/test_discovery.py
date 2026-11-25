PKG=__package__.rsplit('.tests',1)[0]
"""Synthetic queue fixtures only. No credentials, real product requests or DB access."""
import copy
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock,patch
from ..domeggook_discovery import *
from ..domeggook_operations import configuration,main as cli
from .fixtures import fixture


class FakeQueueClient(QueueClient):
    def __init__(self,cfg,root):
        self.cfg=cfg;self.root=root;self.state=read(root/'fake_ledger.json',{'requests':[],'hold':None})
        self.legacy=[];self.cycle_start=0;self.calls=[];self.override=None
    def get(self,mode,**params):
        self.admit_request(mode,params)
        entry={'at':now(),'mode':mode,'status':200,'outcome':'success',**self.request_context}
        self.state['requests'].append(entry);save(self.root/'fake_ledger.json',self.state)
        self.calls.append((mode,params))
        if self.override:return self.override(mode,params)
        if mode=='getItemView':return fixture(str(params['no']))[1],now()
        query=params.get('kw',params.get('ca'));page=params['pg']
        ids=({'갤럭시':{1:['90000001','90000002'],2:['90000002','90000003']},
              '아이폰':{1:['90000001','90000004']}}.get(query,{1:['90000005','90000006']})).get(page,[])
        return {'header':{'currentPage':page,'numberOfPages':3},'list':{'item':[fixture(pid)[0] for pid in ids]}},now()


def fixture_config():
    cfg=configuration();cfg['discovery'].update(keywords=['갤럭시','아이폰'],page_size=2,pending_detail_capacity=4)
    return cfg


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        STATE_ROOT.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='dgd_',dir=STATE_ROOT);self.root=Path(self.temp.name)
        self.cfg=fixture_config();self.fake=FakeQueueClient(self.cfg,self.root)
        self.progress=patch(PKG+'.domeggook_discovery.update');self.progress.start()
        self.windows=patch(PKG+'.domeggook_operations.budget_delay',return_value=(0,None));self.windows.start()
    def tearDown(self):self.progress.stop();self.windows.stop();self.temp.cleanup()
    def run_object(self):
        if not (self.root/'discovery_checkpoint.json').exists():
            state=initial_state(self.cfg)
            state['seed_ids']=[str(n) for n in range(88000001,88000006)]
            state['listings']={pid:{'origin':'seed','detail_status':'observed','last_success_at':now(),'attempts':0,'option_codes':[]} for pid in state['seed_ids']}
            save(self.root/'discovery_checkpoint.json',state)
        return DiscoveryRun(self.cfg,self.fake,self.root)
    def test_page_traversal_native_dedup_and_separate_quotas(self):
        run=self.run_object();seeds=list(run.state['seed_ids'])
        for job in run.state['listings'].values():job['last_success_at']='2026-01-01T00:00:00+00:00'
        report=run.cycle('combined')
        self.assertEqual(report['discovered_new_IDs'],3);self.assertEqual(report['new_detail_success_IDs'],2)
        self.assertEqual(report['duplicate_listing_IDs_removed'],1);self.assertEqual(report['cursor']['page'],3)
        self.assertEqual(len(self.fake.state['requests']),6)
        self.assertEqual(sum(e['queue']=='discovery' for e in self.fake.state['requests']),4)
        self.assertEqual(sum(e['queue']=='refresh' for e in self.fake.state['requests']),2)
        self.assertEqual(run.state['seed_ids'],seeds)
    def test_restart_skips_receipted_pages_and_resumes_pending_IDs(self):
        run=self.run_object();run.cycle('discovery');first_calls=len(self.fake.calls)
        resumed=self.run_object();resumed.cycle('discovery')
        later=self.fake.calls[first_calls:]
        self.assertFalse(any(m=='getItemList' and p.get('kw')=='갤럭시' and p['pg'] in (1,2) for m,p in later))
        self.assertEqual(resumed.state['discovery']['last_processed']['query']['value'],'아이폰')
        self.assertEqual(len(resumed.state['listings']),len(set(resumed.state['listings'])))
    def test_empty_results_advance_to_next_keyword(self):
        run=self.run_object()
        self.fake.override=lambda mode,p:({'header':{'numberOfItems':0},'list':None},now())
        run.cycle('discovery')
        self.assertEqual(run.state['discovery']['phase'],'sweep_complete')
        self.assertEqual(len(self.fake.calls),2)
    def test_keyword_duplicates_and_category_validation(self):
        self.cfg['discovery']['keywords']=['갤럭시','갤럭시']
        self.cfg['discovery']['categories']=['01_11_00_00_00']
        self.assertEqual(len(queries(validate_discovery(self.cfg))),2)
        self.cfg['discovery']['categories']=['01_00_00_00_00']
        with self.assertRaises(SafeAPIError):validate_discovery(self.cfg)
    def test_category_request_uses_ca_and_pg(self):
        self.cfg['discovery'].update(keywords=[],categories=['01_11_00_00_00'])
        run=self.run_object();run.cycle('discovery')
        lists=[p for m,p in self.fake.calls if m=='getItemList']
        self.assertEqual(lists[0]['ca'],'01_11_00_00_00');self.assertEqual([p['pg'] for p in lists],[1,2])
    def test_capacity_backpressure_keeps_IDs_and_drains_details(self):
        self.cfg['discovery']['pending_detail_capacity']=2
        run=self.run_object();run.cycle('discovery')
        self.assertLessEqual(len(run.state['pending_ids']),2)
        self.assertEqual(run.state['totals']['new_listing_IDs'],3)
        self.assertEqual(run.state['totals']['new_detail_normalized'],2)
    def test_refresh_only_does_not_discover_or_request_listing(self):
        run=self.run_object();run.cycle('refresh')
        self.assertEqual(len(self.fake.calls),2)
        self.assertTrue(all(mode=='getItemView' for mode,_ in self.fake.calls))
        self.assertEqual(run.report()['discovered_new_IDs'],0)
    def test_discovery_only_cannot_spend_refresh_reservation(self):
        run=self.run_object();run.cycle('discovery')
        self.assertEqual(len(self.fake.calls),4)
        self.assertTrue(all(e['queue']=='discovery' for e in self.fake.state['requests']))
    def test_invalid_quota_cannot_raise_shared_limits(self):
        self.cfg['discovery']['requests_per_cycle']=5
        with self.assertRaises(SafeAPIError):validate_discovery(self.cfg)
    def test_due_refresh_orders_oldest_first(self):
        run=self.run_object();ids=list(run.state['listings'])
        for pid in ids:run.state['listings'][pid]['last_success_at']='2026-01-02T00:00:00+00:00'
        run.state['listings'][ids[-1]]['last_success_at']='2026-01-01T00:00:00+00:00'
        run.cycle('refresh')
        self.assertEqual(self.fake.calls[0][1]['no'],ids[-1])
    def test_failed_refresh_preserves_previous_memory_values(self):
        run=self.run_object();run.cycle('refresh');before=copy.deepcopy(run.store.memory)
        def fail(mode,p):raise SafeAPIError('HTTP_unsuccessful')
        self.fake.override=fail
        with self.assertRaises(SafeAPIError):run.cycle('refresh')
        self.assertEqual(run.store.memory,before)
    def test_restricted_body_and_product_values_never_checkpointed(self):
        run=self.run_object()
        def denied(mode,p):
            if mode=='getItemList':
                return {'header':{'numberOfPages':1},'list':{'item':[fixture('90000001')[0]]}},now()
            listing,payload=fixture(str(p['no']));payload['desc']['license']['usable']=False
            payload['desc']['contents']['item']='<p>RESTRICTED_PAYLOAD_SECRET</p>'
            return payload,now()
        self.fake.override=denied;run.cycle('discovery')
        self.assertIsNone(run.latest_rows['90000001']['description_html'])
        checkpoint=run.path.read_text(encoding='utf-8')
        self.assertNotIn('SYNTHETIC product',checkpoint);self.assertNotIn('RESTRICTED_PAYLOAD_SECRET',checkpoint)
        self.assertFalse((self.root/'permitted_offers.json').exists())
        row=run.latest_rows['90000001']
        for key in ('stock','option_values','observed_at','minimum_product_total','estimated_minimum_checkout_total'):self.assertIn(key,row)
    def test_refresh_replaces_component_notices_and_revoked_image_permissions(self):
        run=self.run_object();pid='90000001';payload=fixture(pid)[1]
        payload['desc']['license']['usable']=True
        payload['detail']['infoDuty']={'item':[{'name':'재질','desc':'PP'}]}
        run.state['listings'][pid]={'origin':'discovery','attempts':0}
        run.state['cycle_refresh_done']=[]
        first=datetime.now(timezone.utc)
        run._detail_result({'pid':pid},payload,first.isoformat(),'discovery')
        self.assertEqual(run.latest_rows[pid]['product_notices']['item'][0]['desc'],'PP')
        newer=copy.deepcopy(payload);newer['detail'].pop('infoDuty');newer['desc']['license']['usable']=False
        run._detail_result({'pid':pid},newer,(first+timedelta(seconds=1)).isoformat(),'refresh')
        row=run.latest_rows[pid]
        self.assertIsNone(row['product_notices']);self.assertIsNone(row['description_html'])
        self.assertEqual(row['detail_image_urls'],[]);self.assertFalse(row['detail_content_license_usable'])

    def test_option_ambiguity_quarantined_without_fabricated_ID(self):
        run=self.run_object()
        payload=fixture('90000001')[1];payload['selectOpt']=None
        run.state['listings']['90000001']={'origin':'discovery','attempts':0};run.state['pending_ids']=['90000001']
        run.state['cycle_refresh_done']=[]
        run._detail_result({'pid':'90000001'},payload,now(),'discovery')
        self.assertEqual(run.state['listings']['90000001']['identity_status'],'quarantine')
        self.assertEqual(run.state['listings']['90000001']['option_codes'],[])
    def test_zero_budget_once_adds_no_HTTP_or_fake_success(self):
        run=self.run_object()
        with patch(PKG+'.domeggook_operations.budget_delay',return_value=(600,'window_budget_wait')):
            result=queue_loop(run,'discovery')
        self.assertEqual(result['status'],'budget_wait');self.assertEqual(self.fake.calls,[])
        self.assertEqual(run.report()['discovered_new_IDs'],0)
    def test_atomic_checkpoint_retries_rename_without_repeating_HTTP(self):
        run=self.run_object();real_replace=os.replace;count=0
        def temporary_failure(source,target):
            nonlocal count
            count+=1
            if count<3:raise PermissionError('SYNTHETIC transient file lock')
            return real_replace(source,target)
        with patch(PKG+'.progress.os.replace',side_effect=temporary_failure),patch(PKG+'.progress.time.sleep'):
            run.checkpoint()
        self.assertEqual(count,3);self.assertEqual(self.fake.calls,[])
        self.assertEqual(read(run.path)['version'],1)
    def test_status_and_dryrun_are_readonly_and_keyless(self):
        with patch(PKG+'.domeggook_open.read_key',side_effect=AssertionError('key read')),patch(PKG+'.domeggook_discovery.save',side_effect=AssertionError('write')):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli(['--status']),0);self.assertEqual(cli(['--discover-once','--dry-run']),0)
    def test_lost_listing_response_is_held_without_resend(self):
        run=self.run_object();run.state['inflight']={'kind':'page','task_id':'page:1:0:1','ledger_start':0}
        self.fake.state['requests']=[{'at':now(),'status':200,'task_id':'page:1:0:1'}];run.checkpoint()
        resumed=self.run_object()
        with self.assertRaises(SafeAPIError):resumed.cycle('discovery')
        self.assertEqual(self.fake.calls,[])
    def test_page_schema_mismatch_cannot_commit_wrong_IDs(self):
        run=self.run_object();task=run._page_task()
        payload={'header':{'currentPage':99},'list':{'item':[fixture('90000001')[0]]}}
        with self.assertRaises(SafeAPIError):run._page_result(task,payload,now())
        self.assertNotIn('90000001',run.state['listings'])
    def test_queue_attempt_limit_blocks_infinite_retries(self):
        run=self.run_object();run.state['discovery']['failures'][run.page_key()]=3
        self.assertIsNone(run._page_task());self.assertEqual(run.state['discovery']['phase'],'task_blocked')
    def test_empty_or_inconsistent_checkpoint_cannot_reset_native_IDs(self):
        save(self.root/'discovery_checkpoint.json',{})
        with self.assertRaises(SafeAPIError):self.run_object()
    def test_retry_cut_by_lane_budget_still_consumes_task_attempt(self):
        run=self.run_object();run.state.update(cycle=1,cycle_requests_start=0)
        task=run._page_task()
        def cut(mode,p):
            self.fake.state['requests'][-1]['status']=503
            raise LaneExhausted('list')
        self.fake.override=cut
        with self.assertRaises(LaneExhausted):run.execute(task,'discovery')
        self.assertEqual(run.state['discovery']['failures'][task['key']],1)
    def test_sweep_wait_then_reopens_pages_for_newly_registered_items(self):
        run=self.run_object();d=run.state['discovery'];d.update(phase='sweep_complete',next_sweep_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
        self.assertIsNone(run._page_task())
        d['next_sweep_at']='2026-01-01T00:00:00+00:00'
        task=run._page_task();self.assertEqual(task['params']['pg'],1);self.assertEqual(d['sweep'],2)
    def test_discovery_is_not_limited_to_old_five(self):
        self.cfg['discovery'].update(page_size=20,pending_detail_capacity=40)
        run=self.run_object()
        def many(mode,p):
            if mode=='getItemView':return fixture(str(p['no']))[1],now()
            start=91000000+(p['pg']-1)*20
            return {'header':{'currentPage':p['pg'],'numberOfPages':100},
                'list':{'item':[fixture(str(i))[0] for i in range(start,start+20)]}},now()
        self.fake.override=many;run.cycle('discovery')
        self.assertEqual(run.report()['discovered_new_IDs'],40)
        self.assertEqual(run.report()['new_detail_success_IDs'],2)
        self.assertEqual(len(run.state['pending_ids']),38)
    def test_separate_process_crash_resume_NO_HTTP(self):
        worker='''
import os,sys
from pathlib import Path
from unittest.mock import patch
from services.collector.domeggook_live.tests.test_discovery import *
root=Path(sys.argv[1]);cfg=fixture_config();fake=FakeQueueClient(cfg,root)
with patch(PKG+'.domeggook_operations.budget_delay',return_value=(0,None)),patch(PKG+'.domeggook_discovery.update'):
    run=DiscoveryRun(cfg,fake,root);original=run.checkpoint
    def checkpoint():
        original()
        if sys.argv[2]=='crash' and len(run.state['discovery']['pages'])==1 and not run.state['inflight']:os._exit(17)
    run.checkpoint=checkpoint
    run.cycle('discovery')
'''
        first=subprocess.run([sys.executable,'-B','-c',worker,str(self.root),'crash'],cwd=Path(__file__).resolve().parents[4],capture_output=True)
        self.assertEqual(first.returncode,17)
        second=subprocess.run([sys.executable,'-B','-c',worker,str(self.root),'resume'],cwd=Path(__file__).resolve().parents[4],capture_output=True)
        self.assertEqual(second.returncode,0,second.stderr.decode(errors='replace'))
        state=read(self.root/'discovery_checkpoint.json');entries=read(self.root/'fake_ledger.json')['requests']
        self.assertEqual(sum(e['task_id']=='page:1:0:1' for e in entries),1)
        self.assertEqual(state['phase'],'cycle_complete');self.assertEqual(len(entries),4)
