"""Query count, scoped expiration and rollback-only index plans on disposable DBs."""
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event
from test_members_billing import client, account
from test_independent_features import db, job, new_offer, worker_headers

pytestmark = pytest.mark.skipif(os.getenv('CATALOG_INTEGRATION') != '1', reason='requires disposable databases')


def test_history_batch_query_preserves_current_values_and_order(client, worker_headers):
    headers, _, uid = account(client)
    first, second, unavailable = [new_offer(client) for _ in range(3)]
    ids = [uuid4() for _ in range(100)]
    with db('catalog') as c:
        for number, ident in enumerate(ids):
            c.execute('''INSERT INTO app.analyses(analysis_id,owner_id,request_key,request_hash,page_url,
                page_session_id,page_revision,selected_domain,state,offer_ids,created_at)
                VALUES(%s,%s,%s,'test','https://store.example.test/','p',1,'product','completed',CAST(%s AS uuid[]),
                now()-(%s * interval '1 second'))''',
                (ident,uid,str(ident),[unavailable, first, second],number))
        c.execute("UPDATE app.offers SET availability='ended' WHERE offer_id=%s",(unavailable,))
        c.execute("UPDATE app.offers SET price=4321,current_url='https://store.example.test/latest' WHERE offer_id=%s",(first,))
    queries=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        queries.append(statement)
    engine=client.app.state.engine.sync_engine
    event.listen(engine,'before_cursor_execute',capture)
    try:
        r=client.get('/v2/me/analyses?limit=100',headers=headers)
    finally:
        event.remove(engine,'before_cursor_execute',capture)
    assert r.status_code==200,r.text
    items=r.json()['data']
    assert [x['analysis_id'] for x in items]==[str(i) for i in ids]
    assert all(x['card']['offer_id']==first and x['card']['price']=='4321.0000'
               and x['card']['url']=='https://store.example.test/latest' for x in items)
    assert second not in r.text and unavailable not in r.text
    # Catalog SQL stays at 2 for 100 histories: one page + one batched offer read.
    assert len(queries)==2,queries
    assert sum('FROM app.offers' in sql for sql in queries)==1


def test_public_poll_expires_only_its_own_job(client,worker_headers):
    h,_,uid=account(client);other,_,other_uid=account(client)
    target=job(client,h).json()['data']['analysis_id']
    unrelated=job(client,other).json()['data']['analysis_id']
    with db('catalog') as c:
        c.execute("UPDATE app.analyses SET deadline=now()-interval '1 second' WHERE owner_id IN (%s,%s)",(uid,other_uid))
    assert client.get('/analyses/'+unrelated,headers=h).status_code==404
    with db('catalog') as c:
        assert c.execute('SELECT state FROM app.analyses WHERE analysis_id=%s',(unrelated,)).fetchone()[0]=='queued'
    assert client.get('/analyses/'+target,headers=h).json()['data']['error']['code']=='ANALYSIS_TIMEOUT'
    assert job(client,h).status_code==202
    with db('catalog') as c:
        assert c.execute('SELECT state FROM app.analyses WHERE analysis_id=%s',(unrelated,)).fetchone()[0]=='queued'
    assert client.get('/analyses/'+unrelated,headers=other).json()['data']['state']=='failed'


def test_retention_and_fk_query_plans(client):
    """10k synthetic rows/table; savepoint DROP INDEX compares the same snapshot.

    The outer transaction ALWAYS rolls back fixtures, DDL and ANALYZE changes.
    Timing is evidence, not a fragile millisecond assertion; index selection and
    result equivalence are asserted. Never execute this on a shared/live DB.
    """
    source='plan_'+uuid4().hex
    run_id,item_id,offer_id=uuid4(),uuid4(),uuid4()
    reports=[]
    with db('catalog','owner') as c, c.transaction(force_rollback=True):
        c.execute("INSERT INTO app.catalog_items(item_id,kind,name) VALUES(%s,'product','plan fixture')",(item_id,))
        c.execute('INSERT INTO app.products(item_id) VALUES(%s)',(item_id,))
        c.execute('INSERT INTO app.crawl_runs(run_id,source) VALUES(%s,%s)',(run_id,source))
        c.execute('''INSERT INTO app.offers(offer_id,item_id,kind,source,source_listing_id,variant_key,condition,
            price,currency,current_url,availability,price_observed_at,status_observed_at,url_observed_at,
            content_observed_at,last_seen_at,last_checked_at,condition_observed_at,last_changed_at)
            SELECT CASE WHEN g=1 THEN %s ELSE gen_random_uuid() END,%s,'product',%s,g::text,'v','new',1,'KRW',
            'https://store.example.test/','available',now(),now(),now(),now(),now(),now(),now(),now()
            FROM generate_series(1,10000) g''',(offer_id,item_id,source))
        c.execute('''INSERT INTO app.crawl_observations(run_id,source,observation_key,payload_hash,observed_at,
            received_at,normalized_payload,state,offer_id)
            SELECT %s,%s,g::text,'hash',now(),now()-interval '8 days',
            CASE WHEN g<=10 THEN '{"name":"fixture"}'::jsonb ELSE '{}'::jsonb END,'applied',%s
            FROM generate_series(1,10000) g''',(run_id,source,offer_id))
        c.execute('''INSERT INTO app.offer_url_history(offer_id,url,valid_from,valid_to)
            SELECT %s,'https://store.example.test/',now()-interval '2 days',now()-interval '1 day'
            FROM generate_series(1,10000)''',(offer_id,))
        c.execute('''INSERT INTO app.price_history(offer_id,observation_id,price,currency,observed_at)
            SELECT %s,observation_id,1,'KRW',CASE WHEN observation_key::int<=10 THEN now()-interval '100 days' ELSE now() END
            FROM app.crawl_observations WHERE source=%s''',(offer_id,source))
        c.execute('''INSERT INTO app.offer_changes(offer_id,observation_id,observed_at,before_data,after_data)
            SELECT %s,observation_id,CASE WHEN observation_key::int<=10 THEN now()-interval '100 days' ELSE now() END,'{}','{}'
            FROM app.crawl_observations WHERE source=%s''',(offer_id,source))
        for table in ('offers','offer_url_history','crawl_observations','price_history','offer_changes'):
            c.execute('ANALYZE app.'+table)
        cases=[
            ('offers_by_item','SELECT offer_id FROM app.offers WHERE item_id=%s',(uuid4(),)),
            ('urls_by_offer','SELECT url_history_id FROM app.offer_url_history WHERE offer_id=%s',(uuid4(),)),
            ('observations_payload_cleanup',"SELECT observation_id FROM app.crawl_observations WHERE received_at<now()-interval '7 days' AND normalized_payload<>'{}'::jsonb ORDER BY received_at LIMIT 500",()),
            ('prices_expiry',"SELECT price_history_id FROM app.price_history WHERE observed_at<now()-interval '90 days' LIMIT 500",()),
            ('changes_expiry',"SELECT change_id FROM app.offer_changes WHERE observed_at<now()-interval '90 days' LIMIT 500",()),
        ]
        def explain(query,params):
            return c.execute('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+query,params).fetchone()[0][0]
        for index,query,params in cases:
            after=explain(query,params)
            with c.transaction(force_rollback=True):
                c.execute('DROP INDEX app.'+index)
                before=explain(query,params)
            assert index in json.dumps(after),after
            assert after['Plan']['Actual Rows']==before['Plan']['Actual Rows']
            def summary(plan):
                return {'ms':plan['Execution Time'],'rows':plan['Plan']['Actual Rows'],
                        'shared_blocks':plan['Plan'].get('Shared Hit Blocks',0)+plan['Plan'].get('Shared Read Blocks',0)}
            reports.append({'index':index,'without_index':summary(before),'with_index':summary(after)})
        index_bytes=c.execute("SELECT sum(pg_relation_size(indexrelid)) FROM pg_index WHERE indexrelid::regclass::text=ANY(%s)",
            (['app.'+case[0] for case in cases],)).fetchone()[0]
    result={'fixture_rows_per_table':10000,'fixture_cleanup':'transaction rolled back',
            'new_index_bytes_in_fixture':int(index_bytes),'plans':reports}
    if path:=os.getenv('EFFICIENCY_REPORT'):
        target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
