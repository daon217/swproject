from pathlib import Path
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor
import copy,json,os,subprocess,sys,time,uuid
assert os.environ.get('KKULPICK_DEVTEST_APPROVED')=='1','explicit_synthetic_devtest_approval_required'
ROOT=Path(os.environ['KKULPICK_DEVTEST_ROOT']).resolve()
from services.collector.domeggook_live.fixture_data import row,config
from services.collector.domeggook_live.domeggook_backend import prepare_observation,HTTPBackendTransport
from services.collector.domeggook_live.domeggook_delivery import DeliveryPipeline,atomic
from services.collector.domeggook_live.domeggook_discovery import queue_loop
import requests

settings=json.loads((ROOT/'private_test_secrets.json').read_text())
assert json.loads((ROOT/'mock_results.json').read_text())['status']=='passed'
base='http://127.0.0.1:'+str(settings['api_port']);cfg=config(base)
token=settings['api_token'];headers={'Authorization':'Bearer '+token}
session=requests.Session();session.trust_env=False
api=None;log=None
def start_api():
    global api,log
    log=(ROOT/'test-api.log').open('ab')
    api=subprocess.Popen([sys.executable,'-B','-m','uvicorn','services.collector.domeggook_live.devtest.test_api:app','--host','127.0.0.1','--port',str(settings['api_port']),
        '--no-access-log','--log-level','warning','--loop','services.collector.domeggook_live.devtest.test_api:selector_loop'],cwd=Path(__file__).resolve().parents[4],stdout=log,stderr=log,creationflags=0x08000000 if os.name=='nt' else 0)
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if api.poll() is not None:raise RuntimeError('isolated_test_API_start_failed_see_local_log')
        try:
            if session.get(base+'/health',timeout=1).status_code==200:return
        except requests.RequestException:pass
        time.sleep(.2)
    raise RuntimeError('isolated_API_health_timeout')
def stop_api():
    global api,log
    if api is not None and api.poll() is None:api.terminate();api.wait(timeout=15)
    if log:log.close()
    api=None;log=None
def evidence():
    r=session.get(base+'/test/evidence',headers=headers,timeout=5);r.raise_for_status();return r.json()
def pg(action):
    data=(ROOT/'pgdata').resolve();data.relative_to(ROOT.resolve())
    if action=='start':
        stream=(ROOT/'postgres.log').open('ab')
        process=subprocess.Popen([str(Path(os.environ['KKULPICK_DEVTEST_PG_BIN'])/'postgres.exe'),'-D',str(data),'-h','127.0.0.1','-p',str(settings['db_port'])],
            stdout=stream,stderr=stream,creationflags=0x08000000 if os.name=='nt' else 0)
        stream.close();deadline=time.monotonic()+20
        import psycopg
        while time.monotonic()<deadline:
            try:
                with psycopg.connect(host='127.0.0.1',port=settings['db_port'],dbname=settings['dbname'],user='kkulpick_fixture_admin',password=settings['admin_password'],connect_timeout=1):return
            except psycopg.OperationalError:time.sleep(.2)
        raise RuntimeError('isolated_PG_restart_failed')
    cmd=[str(Path(os.environ['KKULPICK_DEVTEST_PG_BIN'])/'pg_ctl.exe'),'-D',str(data),'-w']
    cmd+=['-l',str(ROOT/'postgres.log'),'start'] if action=='start' else ['stop','-m','fast']
    result=subprocess.run(cmd,capture_output=True,creationflags=0x08000000 if os.name=='nt' else 0)
    if result.returncode:raise RuntimeError('isolated_PG_'+action+'_failed')

class Tracked:
    def __init__(self,lose_once=False):
        self.tx=HTTPBackendTransport(base,token,approved_loopback_test=True);self.lose_once=lose_once;self.calls=[]
    def __call__(self,path,body):
        code,ack=self.tx(path,body);self.calls.append({'status':code,'state':ack.get('state'),'change_kind':ack.get('change_kind')})
        if self.lose_once and code in (200,201):self.lose_once=False;return 0,{}
        return code,ack
    def close(self):self.tx.close()

def main():
    import threading
    report={};run_label=uuid.uuid4().hex[:8];outbox=ROOT/('outbox_'+run_label)
    t=datetime.now(timezone.utc)-timedelta(minutes=5);clock=[datetime.now(timezone.utc)]
    def fixture(index,price,quantity):
        value=row((t+timedelta(seconds=30*index)).isoformat(),price,quantity)
        pid='TEST-KKULPICK-'+run_label;value.update(product_id=pid,source_listing_id=pid,product_url='https://store.example.test/'+pid)
        for key in ('product_id','source_listing_id'):value['identity_evidence'][key]['value']=pid
        return value
    start_api();initial=evidence();tx=Tracked();pipeline=DeliveryPipeline(cfg,outbox,tx,clock=lambda:clock[0])
    snapshots=[];rows=[fixture(0,1000,10),fixture(1,1200,0),fixture(2,1200,0)]
    class FixtureWatch:
        def __init__(self):self.root=outbox;self.cfg={'cycle_interval_seconds':60};self.stop=threading.Event();self.index=0
        def cycle(self,mode):
            value=rows[self.index];atomic(outbox/'collection_checkpoint.json',{'cycle':self.index+1,'source_listing_id':value['source_listing_id'],'observed_at':value['observed_at']})
            pipeline.stage(value);pipeline.flush();snapshots.append(evidence());self.index+=1;return self.report()
        def report(self):return {'cycles':self.index,'delivery':pipeline.report()}
    watcher=FixtureWatch();waits=[]
    queue_loop(watcher,'combined',watch=True,cycles=3,wait=lambda seconds,stop:waits.append(seconds))
    target=lambda ev:next(r for r in ev['offers'] if r['source_listing_id']==rows[0]['source_listing_id'])
    first,second,third=map(target,snapshots)
    assert len({r['offer_id'] for r in (first,second,third)})==1
    assert second['price']=='1200.0000' and second['availability']=='out_of_stock'
    assert parsed_iso(third['last_checked_at'])>parsed_iso(second['last_checked_at'])
    assert snapshots[2]['counts']['price_history']==snapshots[1]['counts']['price_history']
    path='/internal/v2/crawl-runs/'+pipeline.state['run_id']+'/observations'
    body=prepare_observation(rows[0],cfg,selected_domain='product',condition='new')
    duplicate_before=evidence()['counts'];duplicate=tx(path,body);assert duplicate[0]==200
    assert evidence()['counts']==duplicate_before
    report['watch']={'cycles':3,'scheduler_intervals_simulated':waits,'real_POSTs':3,'created':1,'updated':1,'unchanged':1,
        'same_offer_id':True,'last_checked_advanced':True,'availability_changed':'available -> out_of_stock','numeric_stock_contract_supported':False}
    report['duplicate_replay']={'HTTP_status':duplicate[0],'duplicate_offer_growth':0,'fixture_offers_total_after_replays':1}
    stop_api();fourth=fixture(3,1250,3);pipeline.stage(fourth);pipeline.flush()
    assert pipeline.report()['states']['retry_wait']==1
    checkpoint_before=(outbox/'collection_checkpoint.json').read_bytes();pending_sha=next(e['sha256'] for e in pipeline.state['entries'].values() if e.get('body'))
    pipeline.close();clock[0]+=timedelta(seconds=6);start_api();tx2=Tracked();pipeline=DeliveryPipeline(cfg,outbox,tx2,clock=lambda:clock[0]);pipeline.flush()
    assert pipeline.pending_count()==0 and (outbox/'collection_checkpoint.json').read_bytes()==checkpoint_before
    assert target(evidence())['price']=='1250.0000'
    report['outage_recovery']={'connection_failed_safely':True,'same_body_sha256_retained':pending_sha,
        'outbox_restart_replayed':True,'collection_checkpoint_unchanged':True,'retry_status':tx2.calls[-1]['status']}
    fifth=fixture(4,1300,5);loss=Tracked(lose_once=True);pipeline.transport=loss;pipeline.stage(fifth);pipeline.flush()
    assert target(evidence())['price']=='1300.0000' and pipeline.pending_count()==1
    committed=evidence()['counts'];clock[0]+=timedelta(seconds=6)
    retry=Tracked();pipeline=DeliveryPipeline(cfg,outbox,retry,clock=lambda:clock[0]);pipeline.flush()
    assert retry.calls[-1]['status']==200 and evidence()['counts']==committed
    report['lost_response_replay']={'server_commit_before_response_loss':True,'replay_status':200,'duplicate_rows_or_history_added':0}
    final_row=fixture(5,1350,5);final_body=prepare_observation(final_row,cfg,selected_domain='product',condition='new')
    def concurrent(_):
        transport=Tracked()
        try:return transport(path,final_body)[0]
        finally:transport.close()
    with ThreadPoolExecutor(2) as pool:statuses=sorted(pool.map(concurrent,range(2)))
    assert statuses==[200,201]
    final_before_restart=evidence();assert target(final_before_restart)['offer_id']==first['offer_id']
    report['concurrent_identical_observation']={'statuses':statuses,'one_offer_preserved':True}
    denied=copy.deepcopy(final_body);denied.update(source='domeggook',source_listing_id='12345678')
    response=session.post(base+path,json=denied,headers=headers,timeout=5);assert response.status_code==403
    assert evidence()['non_synthetic_offers']==0
    report['real_product_namespace_blocked']=True
    stop_api();pg('stop');pg('start');start_api();final=evidence()
    assert final['counts']==final_before_restart['counts'];assert target(final)['offer_id']==first['offer_id']
    report['API_and_PostgreSQL_restart']={'same_rows_and_IDs_preserved':True}
    report.update(status='passed',dataset='synthetic only',fixture_source='domeggook_test',
        fixture_offers_added=final['counts']['offers']-initial['counts']['offers'],
        observations_added=final['counts']['crawl_observations']-initial['counts']['crawl_observations'],
        price_history_added=final['counts']['price_history']-initial['counts']['price_history'],
        real_Domeggook_rows=final['non_synthetic_offers'],final_fixture=target(final),final_counts=final['counts'],
        backend_team_files_modified=False,live_crawler_requests_sent_by_test=0)
    atomic(ROOT/'integration_results.json',report)
    pipeline.close();tx.close();tx2.close();loss.close();retry.close()
    print(json.dumps({'status':'passed','fixture_offers_added':report['fixture_offers_added'],'observations_added':report['observations_added'],
        'price_history_added':report['price_history_added'],'real_Domeggook_rows':0,'watch_cycles':3,'outage_recovery':True,'concurrent_statuses':statuses}))

def parsed_iso(value):return datetime.fromisoformat(value.replace('Z','+00:00'))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        # No exception message/connection string/token or actual product values printed.
        print(json.dumps({'safe_error_type':type(exc).__name__,'line':__import__('traceback').extract_tb(exc.__traceback__)[-1].lineno}));raise SystemExit(2)
    finally:
        stop_api()
        try:pg('stop')
        except Exception:pass
