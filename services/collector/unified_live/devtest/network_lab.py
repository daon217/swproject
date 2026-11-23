"""Explicit disposable FastAPI/SQLite lab. Never imports a team DB or calls a supplier."""
import json,os,sys
from pathlib import Path

def server():
    import secrets
    import uuid
    import uvicorn
    from fastapi import FastAPI,Request,HTTPException
    from fastapi.responses import JSONResponse
    from services.collector.unified_live.local_receipt import ReceiptStore
    if os.environ.get('COLLECTOR_NETWORK_LAB')!='synthetic_only':raise RuntimeError('isolated_lab_only')
    app=FastAPI();store=ReceiptStore('/tmp/collector_test_network.sqlite',['store.example.test'],['USD'])
    counters={'POST_attempts':0,'forced_503':0,'redirects':0,'auth_rejections':0};failed=False
    def save():Path('/tmp/lab-counters.json').write_text(json.dumps(counters))
    save()
    @app.get('/health')
    def health():return {'status':'synthetic_lab_only'}
    @app.post('/internal/v2/crawl-runs/{run_id}/observations')
    async def ingest(run_id:uuid.UUID,request:Request):
        nonlocal failed
        counters['POST_attempts']+=1;save()
        token=Path('/tmp/lab-secret/token').read_text().strip()
        if not secrets.compare_digest(request.headers.get('Authorization',''),'Bearer '+token):
            counters['auth_rejections']+=1;save();raise HTTPException(401)
        body=await request.json()
        if str(body.get('observation_key','')).endswith(':redirect'):
            counters['redirects']+=1;save();return JSONResponse({},status_code=302,headers={'Location':'http://canary:9000/forbidden'})
        if not failed:
            failed=True;counters['forced_503']+=1;save();return JSONResponse({},status_code=503,headers={'Retry-After':'1'})
        code,ack=store.receive(body);return JSONResponse(ack,status_code=code)
    uvicorn.run(app,host='0.0.0.0',port=8000,access_log=False,log_level='warning')


def client():
    import copy
    from datetime import datetime,timezone,timedelta
    from services.collector.unified_live.mock import fixture_config,product
    from services.collector.unified_live.parser import normalize
    from services.collector.unified_live.backend import ApprovedOutbox
    from services.collector.unified_live.changes import ChangeDelivery
    from services.collector.collector_ops.backend_transport import RoutedBackend
    if os.environ.get('COLLECTOR_NETWORK_LAB')!='synthetic_only':raise RuntimeError('isolated_lab_only')
    path=Path('/tmp/network-review/internal-network-review.json');assert not path.exists()
    os.environ['KKULPICK_BACKEND_TOKEN']=Path('/tmp/lab-secret/token').read_text().strip()
    cfg=fixture_config();cfg['backend_delivery']['base_url']='https://unreachable.example.test'
    clock=[datetime.now(timezone.utc)];body=normalize(product(),cfg['base_url'],clock[0].isoformat(),cfg)
    body['metadata']['synthetic']=True
    box=ApprovedOutbox(cfg,'/tmp/lab-outbox',clock=lambda:clock[0]);gate=ChangeDelivery(box,'/tmp/lab-outbox')
    try:
        staged=gate.stage(body);assert staged['status']=='pending';gate.flush()
        assert next(iter(box.state['entries'].values()))['status']=='retry_wait'
        clock[0]+=timedelta(seconds=10);gate.flush()
        assert next(iter(box.state['entries'].values()))['status']=='delivered'
        route='/internal/v2/crawl-runs/'+box.state['run_id']+'/observations'
        status,ack=box.transport(route,copy.deepcopy(body['observation']));assert status==200
        before=box.state['totals']['HTTP_attempts'];assert gate.stage(body)['status']=='unchanged_skipped';gate.flush()
        assert box.state['totals']['HTTP_attempts']==before
        changed=normalize(product(price='10.00'),cfg['base_url'],clock[0].isoformat(),cfg);changed['metadata']['synthetic']=True
        gate.stage(changed);gate.flush();assert len(box.state['entries'])==2
        assert all(e['status']=='delivered' for e in box.state['entries'].values())
        redirect=copy.deepcopy(changed['observation']);redirect['observation_key']+=':redirect'
        assert box.transport(route,redirect)==(302,{})
        import requests
        direct_redirect_blocked=False
        try:box.transport.session.post(box.transport.base+route,json=redirect,allow_redirects=True,timeout=(5,15))
        except requests.exceptions.InvalidURL:direct_redirect_blocked=True
        assert direct_redirect_blocked

        denied=False
        try:RoutedBackend('http://8.8.8.8:8000',os.environ['KKULPICK_BACKEND_TOKEN'],lambda:clock[0])
        except ValueError:denied=True
        assert denied
        assert not path.exists()  # No approval or topology file was ever injected.
        print(json.dumps({'synthetic_only':True,'real_internal_HTTP_fastapi':True,'first_failure_503_retried':True,
            'new_events':gate.data['totals'].get('new'),'changed_events':gate.data['totals'].get('updated'),
            'unchanged_skipped':gate.data['totals'].get('unchanged'),'queue_HTTP_attempts':box.state['totals']['HTTP_attempts'],
            'direct_idempotent_replay_verified':True,'cross_origin_redirect_blocked_even_if_follow_requested':direct_redirect_blocked,'redirect_not_followed':True,'unconfigured_origin_blocked':denied,
            'approval_file_required':False,'approval_file_present':path.exists(),'supplier_HTTP_requests':0,'production_DB_writes':0,'NAS_changed':False}))
    finally:gate.close()

if __name__=='__main__':
    if len(sys.argv)!=2 or sys.argv[1] not in ('server','client'):raise SystemExit('use server or client in an isolated lab')
    server() if sys.argv[1]=='server' else client()
