import asyncio
import os
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from kkulpick.db import url
from kkulpick.maintenance import cleanup, Policy
from test_arrival_updates import catalog

pytestmark = pytest.mark.skipif(os.getenv('CATALOG_INTEGRATION') != '1', reason='requires disposable database')


def maintain(apply):
    async def task():
        engine=create_async_engine(url('app'))
        try:
            async with engine.begin() as c:
                return await cleanup(c,apply=apply)
        finally:
            await engine.dispose()
    return asyncio.run(task())


def test_purge_dry_run_stale_replay_and_restock(catalog):
    api,post,current,count,source,db,base,start,path,headers=catalog
    created=post(0,dict(availability='out_of_stock'),key='initial').json()
    item=db.execute('SELECT item_id FROM app.offers WHERE offer_id=%s',(created['offer_id'],)).fetchone()[0]
    assert maintain(False)['offers']>=1
    assert current() is not None
    assert maintain(True)['offers_deleted']>=1
    assert current() is None
    assert db.execute('SELECT count(*) FROM app.catalog_items WHERE item_id=%s',(item,)).fetchone()[0]==0
    for table in ['offer_changes','price_history','offer_url_history']:
        assert count(table)==0
    assert post(-10).json()['error_code']=='DELETED_STALE_OBSERVATION'
    assert current() is None
    # A replay is acknowledged without restoring the deleted offer.
    assert post(0,dict(availability='out_of_stock'),key='initial').status_code==200
    assert current() is None
    assert post(10).json()['change_kind']=='created'
    assert current()['availability']=='available'
    maintain(True)
    assert current() is not None


def test_payload_trim_replay_hash_and_unavailable_recovery(catalog):
    _,post,current,_,source,db,*_=catalog
    post(0,key='keep')
    db.execute("UPDATE app.crawl_observations SET received_at=now()-interval '8 days' WHERE source=%s",(source,))
    maintain(True)
    assert db.execute('SELECT normalized_payload FROM app.crawl_observations WHERE source=%s',(source,)).fetchone()[0]=={}
    assert post(0,key='keep').status_code==200
    assert post(1,dict(price='1'),key='keep').status_code==409
    assert current()['availability']=='available'


def test_too_old_observation_rejected_after_retention(catalog):
    api,post,current,_,_,_,base,start,path,headers=catalog
    data=base|dict(observation_key=uuid4().hex,observed_at=(start-timedelta(days=40)).isoformat())
    r=api.post(path,json=data,headers=headers)
    assert r.status_code==201 and r.json()['error_code']=='OBSERVATION_TOO_OLD'
    assert current() is None


def test_retention_policy_minimum():
    with pytest.raises(ValueError):
        Policy(tombstone_days=1)
