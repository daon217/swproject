"""Local-only FastAPI/SQLite receipt lab. Synthetic HTML, no external/production DB.
Uses the collector's real worker, HTTP routing, durable queues and ACK handling.
"""
import copy,json,os,socket,tempfile,threading,time,sqlite3
from pathlib import Path
from datetime import datetime,timezone,timedelta
from fastapi import FastAPI,HTTPException,Request
import uvicorn
from services.collector.unified_live.mock import fixture_config,product,FakeHTTP
from services.collector.unified_live.engine import URLWorker
from services.collector.unified_live.backend import ApprovedOutbox
from services.collector.unified_live.local_receipt import ReceiptStore
from services.collector.collector_ops.delivery_contract import ListingExtension
from services.collector.domeggook_live.domeggook_backend import safe_ack

class Shop(FakeHTTP):
    def __init__(self):super().__init__();self.price='12.00'
    def fetch(self,url):
        code,html=super().fetch(url)
        html=html.replace('UsedCondition','NewCondition').replace('SYNTHETIC clean keyboard','원재료명: 우유, 밀\\n알레르기: 우유, 밀').replace('"@type": "Product"','"@type": "Product", "category":"food"')
        return code,html

def run():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);now=[datetime.now(timezone.utc)];cfg=fixture_config();cfg['mode']='general';cfg['evidence_storage']=True;cfg['rights']['allowed_uses'].append('evidence_storage')
        store=ReceiptStore(root/'collector_test_obs.sqlite',cfg['allowed_product_hosts'],cfg['currencies'])
        c=sqlite3.connect(root/'collector_test_extensions.sqlite',check_same_thread=False)
        c.execute('CREATE TABLE extensions (event_key TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL)');c.commit()
        app=FastAPI();stats={'observations':0,'extensions':0,'checks':0,'auth':0,'pending':0};fault={'observation':1,'extension':1,'mismatch':False}
        @app.middleware('http')
        async def auth(req,call_next):
            if req.headers.get('Authorization')!='Bearer '+'SYNTHETIC_TEST_ONLY_'*2:raise HTTPException(401)
            stats['auth']+=1;return await call_next(req)
        @app.post('/internal/v2/crawl-runs/{run_id}/observations')
        async def obs(run_id:str,request:Request):
            from fastapi.responses import JSONResponse
            stats['observations']+=1
            if fault['observation']:fault['observation']-=1;return JSONResponse(status_code=503,content={'error':{'code':'DATABASE_UNAVAILABLE'}})
            payload=await request.json();code,ack=store.receive(payload);stats['latest_price']=payload.get('price');return JSONResponse(status_code=code,content=ack)
        @app.post('/internal/v2/crawl-runs/{run_id}/extensions')
        async def ext(run_id:str,body:ListingExtension):
            from fastapi.responses import JSONResponse
            stats['extensions']+=1;p=body.model_dump(mode='json',exclude_unset=True);raw=json.dumps(p,sort_keys=True)
            old=c.execute('SELECT payload,state FROM extensions WHERE event_key=?',(body.observation_key,)).fetchone()
            if old and old[0]!=raw:raise HTTPException(409,'EXTENSION_PAYLOAD_CONFLICT')
            if fault['extension']:fault['extension']-=1;state='pending';stats['pending']+=1
            else:state='applied'
            c.execute('INSERT INTO extensions VALUES(?,?,?) ON CONFLICT(event_key) DO UPDATE SET state=excluded.state',(body.observation_key,raw,state));c.commit()
            return JSONResponse(status_code=202 if state=='pending' else 201,content={'state':state,'change_kind':'pending' if state=='pending' else 'updated','error_code':'OFFER_NOT_YET_OBSERVED' if state=='pending' else None})
        @app.post('/internal/v2/listing-checks')
        async def checks(request:Request):
            stats['checks']+=1;b=await request.json();ids=[{k:x[k] for k in ('source_listing_id','variant_key')} for x in b['items']]
            return {'confirmed':0 if fault['mismatch'] else len(ids),'mismatch':ids if fault['mismatch'] else [],'unknown':[],'rejected':[]}
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False));thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
        for _ in range(500):
            if server.started:break
            time.sleep(.01)
        assert server.started
        oldenv={k:os.environ.get(k) for k in ('COLLECTOR_BACKEND_TRANSPORT','COLLECTOR_BACKEND_BASE_URL','COLLECTOR_DELIVERY_APPROVED','KKULPICK_BACKEND_TOKEN')}
        os.environ.update(COLLECTOR_BACKEND_TRANSPORT='internal_http',COLLECTOR_BACKEND_BASE_URL='http://127.0.0.1:'+str(port),COLLECTOR_DELIVERY_APPROVED='yes',KKULPICK_BACKEND_TOKEN='SYNTHETIC_TEST_ONLY_'*2)
        box=ApprovedOutbox(cfg,root/cfg['source'],clock=lambda:now[0]);worker=URLWorker(cfg,root,transport=Shop(),delivery=box,clock=lambda:now[0])
        try:
            task={'kind':'detail','url':'https://store.example.test/item/1'};worker.page(task);worker.delivery.flush()
            assert box.report()['states']['retry_wait']==1
            now[0]+=timedelta(seconds=60);worker.delivery.flush();assert worker.delivery.extras.report()['extension_states']['retry_wait']==1
            # Restart queues between pending extension and its terminal ACK.
            from services.collector.unified_live.changes import ChangeDelivery
            worker.delivery=ChangeDelivery(box,root/cfg['source']);now[0]+=timedelta(seconds=60);worker.delivery.flush()
            assert worker.delivery.extras.report()['extension_states']['delivered']==1
            worker.page(task);worker.delivery.flush();assert stats['checks']==1
            now[0]+=timedelta(seconds=60);fault['mismatch']=True;worker.page(task);worker.delivery.flush();worker.delivery.flush();assert len(box.state['entries'])==2
            now[0]+=timedelta(seconds=60);worker.http.price='11.00';worker.page(task);worker.delivery.flush()
            assert store.counts()['listings']==1
            assert stats['latest_price']=='11.00' and box.state['totals'].get('change_updated',0)>=1
            rows=c.execute('SELECT payload,state FROM extensions').fetchall();assert all(x[1]=='applied' for x in rows)
            evidence=json.loads(rows[0][0])['food_evidence'];assert '우유' in evidence['ingredients_raw'];assert '우유' in evidence['allergen_notice_raw'];assert 'safe_to_consume' not in evidence
            out={'passed':True,'local_synthetic_HTML_food_products':1,'real_external_food_products':0,'native_ingredient_extraction':1,'extension_ACKs':len(rows),'SQLite_listings':store.counts()['listings'],'price_updated':True,'unchanged_check_in':True,'mismatch_reobserved':True,'restart_pending_recovered':True,'HTTP_requests':stats,'NAS_accessed':False,'production_DB_writes':0,'external_requests':0,'actual_backend_SQL_executed':False}
            print(json.dumps(out,ensure_ascii=False));return out
        finally:
            worker.close();server.should_exit=True;thread.join(10);c.close()
            for k,v in oldenv.items():
                if v is None:os.environ.pop(k,None)
                else:os.environ[k]=v
if __name__=='__main__':run()
