"""Loopback-only harness around the team's UNCHANGED model and ingestion function."""
import importlib.util,json,os,secrets
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from uuid import UUID
from urllib.parse import urlsplit
from fastapi import FastAPI,HTTPException,Header,Response
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import URL,text

assert os.environ.get('KKULPICK_DEVTEST_APPROVED')=='1','explicit_synthetic_devtest_approval_required'
ROOT=Path(os.environ['KKULPICK_DEVTEST_ROOT']).resolve()
settings=json.loads((ROOT/'private_test_secrets.json').read_text(encoding='utf-8'))
team=Path(os.environ['KKULPICK_DEVTEST_BACKEND'])/'kkulpick'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
Observation=module('team_model_readonly',team/'models.py').Observation
accept=module('team_ingest_readonly',team/'ingest.py').accept
os.environ['CATALOG_URL_HOSTS']='store.example.test'
url=URL.create('postgresql+psycopg',username='kkulpick_fixture_api',password=settings['app_password'],
    host='127.0.0.1',port=settings['db_port'],database=settings['dbname'])
@asynccontextmanager
async def lifespan(app):
    app.state.engine=create_async_engine(url,hide_parameters=True,pool_pre_ping=True)
    yield
    await app.state.engine.dispose()
app=FastAPI(lifespan=lifespan)
def selector_loop():return asyncio.SelectorEventLoop()

@app.get('/health')
async def health():
    async with app.state.engine.connect() as c:await c.execute(text('SELECT 1'))
    return {'status':'ok','synthetic_only':True}

@app.post('/internal/v2/crawl-runs/{run_id}/observations')
async def observation(run_id:UUID,obs:Observation,response:Response,authorization:str=Header(default='')):
    if not secrets.compare_digest(authorization,'Bearer '+settings['api_token']):raise HTTPException(401,'TEST_TOKEN_REQUIRED')
    if obs.source!='domeggook_test' or not (obs.source_listing_id or '').startswith('TEST-') or obs.url and obs.url.host!='store.example.test':
        raise HTTPException(403,'SYNTHETIC_NAMESPACE_ONLY')
    async with app.state.engine.begin() as connection:result,created=await accept(connection,run_id,obs)
    response.status_code=201 if created else 200
    return result

@app.get('/test/evidence')
async def evidence(authorization:str=Header(default='')):
    if not secrets.compare_digest(authorization,'Bearer '+settings['api_token']):raise HTTPException(401)
    async with app.state.engine.connect() as c:
        counts={table:(await c.execute(text('SELECT count(*) FROM app.'+table))).scalar_one() for table in
            ('offers','catalog_items','crawl_observations','price_history','offer_changes','offer_url_history')}
        rows=(await c.execute(text('SELECT offer_id,source,source_listing_id,variant_key,price::text,currency,availability,last_seen_at,last_checked_at FROM app.offers'))).mappings().all()
        real=(await c.execute(text("SELECT count(*) FROM app.offers WHERE source<>'domeggook_test'"))).scalar_one()
    return {'counts':counts,'offers':[dict(r) for r in rows],'non_synthetic_offers':real}
