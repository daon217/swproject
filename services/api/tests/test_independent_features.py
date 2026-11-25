"""Real three-DB tests without OCR, recommendation, crawler or frontend code."""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC,datetime,timedelta
import os
from uuid import uuid4
import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from kkulpick.accounts import process_deletions
from kkulpick.admin_cli import change_access
from kkulpick.db import url
from kkulpick.images import image_path
from test_members_billing import client,account,pay
from test_contract import fixture

pytestmark=pytest.mark.skipif(os.getenv('CATALOG_INTEGRATION')!='1',reason='requires disposable migrated databases')


def db(domain,role='app'):
    u=url(role,domain)
    # Tests use the explicit per-role credentials, independent of API override.
    return psycopg.connect(host=u.host,port=u.port,dbname=u.database,user=u.username,
        password=os.environ[domain.upper()+'_'+role.upper()+'_PASSWORD'],autocommit=True)


def grant(uid,role='admin'):
    with db('member','owner') as c:
        c.execute('INSERT INTO app.admin_accounts(user_id,role) VALUES(%s,%s)',(uid,role))


def new_offer(client):
    item=fixture()|dict(source='feature_'+uuid4().hex,source_listing_id=uuid4().hex,observation_key=uuid4().hex)
    r=client.post('/internal/v2/crawl-runs/'+str(uuid4())+'/observations',json=item,
        headers={'Authorization':'Bearer '+os.environ['COLLECTOR_TOKEN']})
    assert r.status_code==201,r.text
    return r.json()['offer_id']


def job(client,h,**patch):
    data=dict(page_url='https://store.example.test/product',page_session_id='page-one',page_revision=1,
              request_key=uuid4().hex,selected_domain='product')|patch
    return client.post('/analyses',headers=h,json=data)


@pytest.fixture
def worker_headers(monkeypatch,tmp_path):
    monkeypatch.setenv('ANALYSIS_WORKER_TOKEN','worker-secret-'+'x'*40)
    monkeypatch.setenv('ANALYSIS_IMAGE_DIR',str(tmp_path))
    # Each worker test is isolated from intentionally queued cases in prior tests.
    with db('catalog') as c:
        c.execute("UPDATE app.analyses SET state='cancelled' WHERE state IN ('queued','running')")
    return {'Authorization':'Bearer '+os.environ['ANALYSIS_WORKER_TOKEN']}


def claim(client,wh):
    r=client.post('/internal/v2/analyses/claim',headers=wh,json={'worker_id':'fixture-worker'})
    assert r.status_code==200,r.text
    return r.json()['data']


def test_support_ownership_idempotency_and_sequence(client):
    h,_,_=account(client);other,_,_=account(client)
    created=client.post('/v2/support/conversations',headers=h)
    assert created.status_code==201,created.text
    cid=created.json()['data']['conversation_id']
    assert client.post('/v2/support/conversations',headers=h).json()['data']['conversation_id']==cid
    path=f'/v2/support/conversations/{cid}/messages'
    assert client.get(path,headers=other).status_code==404
    body={'body':'문의입니다','client_message_id':str(uuid4())}
    with ThreadPoolExecutor(4) as pool:
        responses=list(pool.map(lambda _:client.post(path,headers=h,json=body),range(4)))
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    assert len({r.json()['data']['message_id'] for r in responses})==1
    assert client.post(path,headers=h,json=body|{'body':'다른 내용'}).status_code==409
    assert client.post(path,headers=other,json=body).status_code==404
    for i in range(3):
        assert client.post(path,headers=h,json={'body':str(i),'client_message_id':str(uuid4())}).status_code==200
    assert [m['sequence_no'] for m in client.get(path,headers=h).json()['data']]==[1,2,3,4]
    assert [m['sequence_no'] for m in client.get(path+'?after_sequence=2',headers=h).json()['data']]==[3,4]


def test_admin_signup_requires_approval_and_stays_out_of_members(client):
    login_id = 'a' + uuid4().hex[:12]
    password = 'Test-pass-427!'
    credentials = {'login_id': login_id, 'password': password}
    application = credentials | {
        'password_confirmation': password, 'consent_version': 'provisional-v1', 'consent_accepted': True,
    }
    path = '/v2/admin/auth'
    assert client.post(path+'/signup', json=application|{'role':'admin'}).status_code==422
    response = client.post(path+'/signup', json=application)
    assert response.status_code == 201, response.text
    assert response.json()['data']['status'] == 'pending_approval'
    user_id = response.json()['data']['user_id']
    requests_path = path+'/requests'
    approve_path = f'{requests_path}/{user_id}/approve'
    assert client.post(path+'/signup', json=application).status_code==409
    with db('member') as conn:
        assert conn.execute('SELECT count(*) FROM app.members WHERE login_id=%s',(login_id,)).fetchone()[0]==0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("UPDATE app.admin_identities SET role='admin',enabled=true WHERE login_id=%s",(login_id,))
    pending=client.post(path+'/login', json=credentials)
    assert pending.status_code==403 and pending.json()['error']['code']=='ADMIN_APPROVAL_REQUIRED'
    assert client.post('/v2/auth/login',json=credentials).status_code==401

    reviewer,_,reviewer_id=account(client)
    ordinary,_,ordinary_id=account(client)
    assert client.get(requests_path).status_code==401
    assert client.get(requests_path,headers=reviewer).status_code==403
    assert client.post(approve_path,headers=ordinary,json={'role':'admin'}).status_code==403
    grant(ordinary_id,'support')
    assert client.post(approve_path,headers=ordinary,json={'role':'admin'}).status_code==403
    grant(reviewer_id)
    listed=client.get(requests_path,headers=reviewer)
    assert listed.status_code==200,listed.text
    request=next(item for item in listed.json()['data'] if item['user_id']==user_id)
    assert request['login_id']==login_id and set(request)=={'user_id','login_id','created_at'}
    assert client.post(approve_path,headers=reviewer,json={'role':'owner'}).status_code==422
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:client.post(approve_path,headers=reviewer,json={'role':'support'}), range(2)))
    assert sorted(result.status_code for result in results)==[200,409], [result.text for result in results]
    assert all(item['user_id']!=user_id for item in client.get(requests_path,headers=reviewer).json()['data'])
    with db('member') as conn:
        audit=conn.execute('SELECT actor_id,action FROM app.admin_audit WHERE target_id=%s',(user_id,)).fetchall()
        assert [(str(actor),action) for actor,action in audit]==[(reviewer_id,'approve:support')]

    engine=create_engine(url('owner','member'),hide_parameters=True)
    try:
        active=client.post(path+'/login',json=credentials)
        assert active.status_code==200,active.text
        token=active.json()['data']['token']
        h={'Authorization':'Bearer '+token}
        assert client.get('/v2/admin/me',headers=h).json()['data']['role']=='support'
        customer,_,_=account(client)
        conversation=client.post('/v2/support/conversations',headers=customer)
        assert conversation.status_code==201,conversation.text
        cid=conversation.json()['data']['conversation_id']
        reply=client.post(f'/v2/admin/support/conversations/{cid}/messages',headers=h,
                          json={'body':'답변입니다','client_message_id':str(uuid4())})
        assert reply.status_code==200,reply.text
        conversations=client.get('/v2/admin/support/conversations?limit=100',headers=h)
        assert conversations.status_code==200,conversations.text
        assert any(item['conversation_id']==cid and item['agent_name']==login_id
                   for item in conversations.json()['data'])
        assert client.get('/v2/admin/members',headers=h).status_code==403
        assert client.get('/v2/me',headers=h).status_code==401

        with engine.begin() as conn:
            change_access(conn,'revoke',login_id,'support')
            change_access(conn,'grant',login_id,'admin')
        assert client.get('/v2/admin/me',headers=h).status_code==401
        approved=client.post(path+'/login',json=credentials)
        assert approved.status_code==200,approved.text
        h={'Authorization':'Bearer '+approved.json()['data']['token']}
        assert client.get('/v2/admin/members',headers=h).status_code==200
        another=client.post(path+'/signup',json=application|{'login_id':'b'+uuid4().hex[:12]})
        nested_path=f"{requests_path}/{another.json()['data']['user_id']}/approve"
        assert client.post(nested_path,headers=h,json={'role':'support'}).status_code==200
        assert client.post(path+'/logout',headers=h).status_code==204
        assert client.get('/v2/admin/me',headers=h).status_code==401
    finally:
        engine.dispose()


def test_admin_conversation_list_carries_customer_summary_for_support_staff(client):
    """#72: support staff cannot read the admin-only member list (and it stops at 100 members), so the
    conversation list itself must name the customer and carry the summary shown in the console."""
    customer,customer_profile,customer_uid=account(client)
    support,support_profile,support_uid=account(client)
    admin,_,admin_uid=account(client)
    grant(support_uid,'support'); grant(admin_uid)
    cid=client.post('/v2/support/conversations',headers=customer).json()['data']['conversation_id']
    assert client.get('/v2/admin/members',headers=support).status_code==403

    def find(headers):
        after=None
        while True:
            q='/v2/admin/support/conversations?limit=100'+(f'&after={after}' if after else '')
            page=client.get(q,headers=headers)
            assert page.status_code==200,page.text
            rows=page.json()['data']
            hit=next((c for c in rows if c['conversation_id']==cid),None)
            if hit or len(rows)<100: return hit
            after=rows[-1]['conversation_id']

    for headers in (support,admin):
        row=find(headers)
        assert row['owner_id']==customer_uid and row['owner_login_id']==customer_profile['login_id']
        assert row['owner']=={'login_id':customer_profile['login_id'],'gender':'male','age_decade':20,
                              'subscribed':False,'subscription_started_at':None}


def test_support_admin_reply_close_and_revocation(client):
    h,_,_=account(client);admin,profile,uid=account(client)
    other_admin,other_profile,other_uid=account(client)
    grant(uid,'support')
    grant(other_uid)
    legacy=client.post('/v2/admin/auth/login',json={k:profile[k] for k in ('login_id','password')})
    assert legacy.status_code==200,legacy.text
    legacy_headers={'Authorization':'Bearer '+legacy.json()['data']['token']}
    assert client.get('/v2/admin/me',headers=legacy_headers).json()['data']['role']=='support'
    assert client.post('/v2/admin/auth/logout',headers=legacy_headers).status_code==204
    cid=client.post('/v2/support/conversations',headers=h).json()['data']['conversation_id']
    path=f'/v2/admin/support/conversations/{cid}'
    assert client.get('/v2/admin/members',headers=admin).status_code==403
    assert client.get('/v2/admin/support/conversations',headers=h).status_code==403

    def displayed_agent():
        result=client.get('/v2/admin/support/conversations?limit=100',headers=admin)
        assert result.status_code==200
        return next(c['agent_name'] for c in result.json()['data'] if c['conversation_id']==cid)

    assert displayed_agent() is None
    r=client.post(path+'/messages',headers=admin,json={'body':'답변입니다','client_message_id':str(uuid4())})
    assert r.status_code==200 and r.json()['data']['sender']=='agent'
    assert displayed_agent()==profile['login_id']
    r=client.post(path+'/messages',headers=other_admin,json={'body':'후속 답변','client_message_id':str(uuid4())})
    assert r.status_code==200
    assert displayed_agent()==other_profile['login_id']
    public=client.get('/v2/support/conversations',headers=h)
    assert next(c['agent_name'] for c in public.json()['data'] if c['conversation_id']==cid) is None
    r=client.patch(path,headers=admin,json={'expected_version':1,'status':'closed'})
    assert r.status_code==409
    r=client.patch(path,headers=admin,json={'expected_version':3,'status':'closed'})
    assert r.status_code==200,r.text
    assert client.post(f'/v2/support/conversations/{cid}/messages',headers=h,json={'body':'추가','client_message_id':str(uuid4())}).status_code==409
    with db('member','owner') as c:c.execute('UPDATE app.admin_accounts SET enabled=false WHERE user_id=%s',(uid,))
    assert client.get(path+'/messages',headers=admin).status_code==403
    with db('member') as c:
        with pytest.raises(psycopg.Error):c.execute("UPDATE app.admin_accounts SET enabled=true WHERE user_id=%s",(uid,))


def test_affiliate_admin_only_periods_version_and_stock(client):
    h,_,uid=account(client);ordinary,_,_=account(client);grant(uid)
    offer=new_offer(client);path='/v2/admin/affiliate-offers/'+offer
    data=dict(partner_name='테스트 제휴',affiliate_url='https://store.example.test/affiliate',
              starts_at=(datetime.now(UTC)-timedelta(hours=1)).isoformat(),ends_at=None,enabled=True,expected_version=0)
    assert client.put(path,headers=ordinary,json=data).status_code==403
    assert client.put(path,headers=h,json=data|{'affiliate_url':'https://evil.example/'}).status_code==422
    r=client.put(path,headers=h,json=data);assert r.status_code==200,r.text
    assert client.put(path,headers=h,json=data).status_code==409
    cards=client.get('/v2/recommendations/featured?limit=100').json()['data']
    card=next(c for c in cards if c['offer_id']==offer)
    assert card['affiliate'] and card['url']==data['affiliate_url']
    with db('catalog') as c:c.execute("UPDATE app.offers SET availability='out_of_stock' WHERE offer_id=%s",(offer,))
    assert all(c['offer_id']!=offer for c in client.get('/v2/recommendations/featured?limit=100').json()['data'])
    assert client.delete(path+'?expected_version=1',headers=h).status_code==200
    assert client.delete(path+'?expected_version=1',headers=h).status_code==409
    assert client.put(path,headers=h,json=data|{'expected_version':2,'starts_at':(datetime.now(UTC)+timedelta(days=1)).isoformat()}).status_code==200
    with db('catalog') as c:c.execute("UPDATE app.offers SET availability='available' WHERE offer_id=%s",(offer,))
    assert all(c['offer_id']!=offer for c in client.get('/v2/recommendations/featured?limit=100').json()['data'])


def test_admin_deletes_only_selected_unlinked_offers(client):
    admin,_,admin_id=account(client);grant(admin_id)
    support,_,support_id=account(client);grant(support_id,'support')
    source='deleted_'+uuid4().hex
    payload=fixture()|dict(source=source,source_listing_id=uuid4().hex,observation_key=uuid4().hex)
    ingest_path='/internal/v2/crawl-runs/'+str(uuid4())+'/observations'
    collector={'Authorization':'Bearer '+os.environ['COLLECTOR_TOKEN']}
    created=client.post(ingest_path,headers=collector,json=payload)
    assert created.status_code==201,created.text
    selected=created.json()['offer_id']
    other_selected,linked,unselected=new_offer(client),new_offer(client),new_offer(client)
    r=client.put('/v2/admin/affiliate-offers/'+linked,headers=admin,json={
        'partner_name':'제휴 테스트','affiliate_url':'https://store.example.test/affiliate',
        'starts_at':datetime.now(UTC).isoformat(),'expected_version':0,
    })
    assert r.status_code==200,r.text

    path='/v2/admin/catalog/offers/delete'
    request={'offer_ids':[selected,linked,other_selected,selected]}
    assert client.post(path,headers=support,json=request).status_code==403
    assert client.post(path,headers=admin,json={'offer_ids':[]}).status_code==422
    r=client.post(path,headers=admin,json=request)
    assert r.status_code==200,r.text
    result=r.json()['data']
    assert set(result['deleted_offer_ids'])=={selected,other_selected}
    assert result['protected_offer_ids']==[linked] and result['missing_offer_ids']==[]
    assert client.post(path,headers=admin,json=request).json()['data']['missing_offer_ids']==[selected,other_selected]
    with db('catalog') as conn:
        ids=conn.execute('SELECT offer_id FROM app.offers WHERE offer_id=ANY(%s::uuid[])',
                         ([selected,other_selected,linked,unselected],)).fetchall()
        assert {str(item[0]) for item in ids}=={linked,unselected}
        assert conn.execute('SELECT offer_id FROM app.crawl_observations WHERE source=%s',(source,)).fetchone()==(None,)
        audit=conn.execute('SELECT actor_id,action FROM app.catalog_admin_audit WHERE offer_id=%s',(selected,)).fetchone()
        assert (str(audit[0]),audit[1])==(admin_id,'catalog.offer.delete')
    stale=client.post(ingest_path,headers=collector,json=payload|{'observation_key':uuid4().hex})
    assert stale.status_code==201 and stale.json()['error_code']=='DELETED_STALE_OBSERVATION'


def test_analysis_idempotency_limit_cancel_and_bola(client,worker_headers):
    h,_,_=account(client);other,_,_=account(client);key=uuid4().hex
    r=job(client,h,request_key=key);assert r.status_code==202,r.text
    ident=r.json()['data']['analysis_id'];path='/analyses/'+ident
    assert job(client,h,request_key=key).status_code==200
    assert job(client,h,request_key=key,page_revision=2).status_code==409
    assert client.get(path,headers=other).status_code==404
    assert client.post(path+'/cancel',headers=other).status_code==404
    assert job(client,h).status_code==202
    assert job(client,h).status_code==202
    assert job(client,h).status_code==429
    assert client.post(path+'/cancel',headers=h).json()['data']['state']=='cancelled'
    assert client.post(path+'/cancel',headers=h).status_code==200
    assert job(client,h).status_code==202
    assert client.post('/internal/v2/analyses/claim',headers=h,json={'worker_id':'bad'}).status_code==401


def test_worker_result_subscription_gate_and_history(client,worker_headers):
    h,_,_=account(client)
    offers=[new_offer(client) for _ in range(3)]
    ident=job(client,h).json()['data']['analysis_id']
    task=claim(client,worker_headers);assert task['analysis_id']==ident
    data={'lease_token':task['lease_token'],'selected_domain':'product','offer_ids':offers}
    path='/internal/v2/analyses/'+ident
    assert client.post(path+'/complete',headers=worker_headers,json=data|{'lease_token':str(uuid4())}).status_code==409
    assert client.post(path+'/complete',headers=worker_headers,json=data|{'offer_ids':[str(uuid4())]}).status_code==422
    assert client.post(path+'/heartbeat',headers=worker_headers,json={'lease_token':task['lease_token']}).status_code==200
    assert client.post(path+'/complete',headers=worker_headers,json=data).status_code==200
    assert client.post(path+'/complete',headers=worker_headers,json=data).status_code==200
    assert client.post(path+'/complete',headers=worker_headers,json=data|{'offer_ids':[]}).status_code==409
    result=client.get('/analyses/'+ident,headers=h).json()['data']
    assert len(result['sections'][0]['items'])==1 and result['sections'][0]['locked_count']==2
    assert offers[1] not in str(result) and task['lease_token'] not in str(result)
    assert pay(client,h).status_code==201
    result=client.get('/analyses/'+ident,headers=h).json()['data']
    assert len(result['sections'][0]['items'])==3
    assert len(client.get('/v2/me/analyses',headers=h).json()['data'])==1
    assert client.post('/v2/me/data-deletions',headers=h,json={'scope':'history'}).status_code==200
    assert client.get('/analyses/'+ident,headers=h).status_code==404
    assert client.post(path+'/complete',headers=worker_headers,json=data).status_code==404


def test_worker_expiry_retry_and_late_result(client,worker_headers):
    h,_,_=account(client);ident=job(client,h).json()['data']['analysis_id']
    first=claim(client,worker_headers)
    with db('catalog') as c:c.execute("UPDATE app.analyses SET lease_until=now()-interval '1 second' WHERE analysis_id=%s",(ident,))
    second=claim(client,worker_headers)
    assert second['attempt']==2 and second['lease_token']!=first['lease_token']
    path='/internal/v2/analyses/'+ident
    assert client.post(path+'/complete',headers=worker_headers,json={'lease_token':first['lease_token'],'selected_domain':'product','offer_ids':[]}).status_code==409
    fail={'lease_token':second['lease_token'],'code':'DEPENDENCY_UNAVAILABLE','retryable':True}
    assert client.post(path+'/fail',headers=worker_headers,json=fail).json()['data']['state']=='queued'
    third=claim(client,worker_headers);assert third['attempt']==3
    assert client.post(path+'/fail',headers=worker_headers,json=fail|{'lease_token':third['lease_token']}).json()['data']['state']=='failed'
    assert client.get('/analyses/'+ident,headers=h).json()['data']['state']=='failed'
    nextid=job(client,h).json()['data']['analysis_id']
    with db('catalog') as c:c.execute("UPDATE app.analyses SET deadline=now()-interval '1 second' WHERE analysis_id=%s",(nextid,))
    assert client.get('/analyses/'+nextid,headers=h).json()['data']['error']['code']=='ANALYSIS_TIMEOUT'


def test_cancel_running_job_rejects_late_callback(client,worker_headers):
    h,_,_=account(client);ident=job(client,h).json()['data']['analysis_id'];task=claim(client,worker_headers)
    assert client.post('/analyses/'+ident+'/cancel',headers=h).status_code==200
    r=client.post('/internal/v2/analyses/'+ident+'/complete',headers=worker_headers,json={'lease_token':task['lease_token'],'selected_domain':'product','offer_ids':[]})
    assert r.status_code==409


def test_upload_private_size_format_and_completion_cleanup(client,worker_headers):
    h,_,_=account(client)
    data=dict(page_url='https://store.example.test/p',page_session_id='p1',page_revision='1',request_key=uuid4().hex)
    assert client.post('/analyses',headers=h,data=data,files={'image':('bad.html',b'<script>x</script>','image/png')}).status_code==415
    assert client.post('/analyses',headers=h,data=data,files={'image':('big.png',b'x'*(2*1024*1024+1),'image/png')}).status_code==413
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ0kAAAAASUVORK5CYII=')
    r=client.post('/analyses',headers=h,data=data,files={'image':('test.png',png,'image/png')});assert r.status_code==202,r.text
    ident=r.json()['data']['analysis_id'];task=claim(client,worker_headers)
    path=task['image_url']
    assert client.get(path,headers=h|{'X-Worker-Lease':task['lease_token']}).status_code==401
    r=client.get(path,headers=worker_headers|{'X-Worker-Lease':task['lease_token']})
    assert r.status_code==200 and r.content==png
    with db('catalog') as c:img=c.execute('SELECT image_id FROM app.analyses WHERE analysis_id=%s',(ident,)).fetchone()[0]
    assert image_path(img).is_file()
    assert client.post('/internal/v2/analyses/'+ident+'/complete',headers=worker_headers,
        json={'lease_token':task['lease_token'],'selected_domain':'product','offer_ids':[]}).status_code==200
    assert not image_path(img).exists()


def test_capture_only_analysis_without_page_url(client,worker_headers):
    h,_,_=account(client)
    data=dict(page_session_id='cap',page_revision='1',request_key=uuid4().hex,selected_domain='product')
    # 이미지도 URL도 없으면 분석 근거가 없으므로 거부한다.
    r=client.post('/analyses',headers=h,data=data|{'request_key':uuid4().hex},files={})
    assert r.status_code in (415,422),r.text
    assert client.post('/analyses',headers=h,json=data).json()['error']['code']=='INPUT_REQUIRED'
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZ0kAAAAASUVORK5CYII=')
    r=client.post('/analyses',headers=h,data=data,files={'image':('c.png',png,'image/png')});assert r.status_code==202,r.text
    task=claim(client,worker_headers)
    assert task['page_url'] is None and task['selected_domain']=='product' and task['image_url']
    with db('catalog') as c:
        assert c.execute('SELECT page_url FROM app.analyses WHERE analysis_id=%s',(r.json()['data']['analysis_id'],)).fetchone()[0] is None


def run_deletions():
    async def work():
        engines=[create_async_engine(url('app',d)) for d in ('member','catalog','support')]
        try:return await process_deletions(*engines)
        finally:
            for e in engines:await e.dispose()
    return asyncio.run(work())


def test_withdrawal_immediate_revoke_and_cross_db_cleanup(client,worker_headers):
    h,credentials,uid=account(client)
    cid=client.post('/v2/support/conversations',headers=h).json()['data']['conversation_id']
    client.post('/v2/support/conversations/'+cid+'/messages',headers=h,json={'body':'삭제할 문의','client_message_id':str(uuid4())})
    ident=job(client,h).json()['data']['analysis_id']
    assert client.post('/v2/me/withdrawal',headers=h,json={'current_password':'wrong-pass'}).status_code==422
    assert pay(client,h).status_code==201
    result=client.post('/v2/me/withdrawal',headers=h,json={'current_password':credentials['password']})
    assert result.status_code==202,result.text
    assert client.get('/v2/me',headers=h).status_code==401
    assert client.post('/v2/auth/login',json={'login_id':credentials['login_id'],'password':credentials['password']}).status_code==401
    assert run_deletions()>=1
    assert run_deletions()==0
    with db('support') as c:assert c.execute('SELECT count(*) FROM app.conversations WHERE owner_id=%s',(uid,)).fetchone()[0]==0
    with db('catalog') as c:assert c.execute('SELECT count(*) FROM app.analyses WHERE analysis_id=%s',(ident,)).fetchone()[0]==0
    with db('member') as c:
        r=c.execute('SELECT login_id,gender,birth_date,deleted_at FROM app.members WHERE user_id=%s',(uid,)).fetchone()
        assert r[0]!=credentials['login_id'] and r[1:3]==(None,None) and r[3] is not None
        assert c.execute('SELECT count(*) FROM app.invoices WHERE user_id=%s',(uid,)).fetchone()[0]==1
        assert c.execute('SELECT state FROM app.account_deletions WHERE user_id=%s',(uid,)).fetchone()[0]=='completed'


def test_withdrawal_pending_payment_guard(client,monkeypatch):
    h,p,_=account(client);monkeypatch.setenv('MOCK_PAYMENT_OUTCOME','pending')
    assert pay(client,h).status_code==202
    assert client.post('/v2/me/withdrawal',headers=h,json={'current_password':p['password']}).status_code==409
    assert client.get('/v2/me',headers=h).status_code==200


def test_parallel_worker_claims_are_unique(client,worker_headers):
    h,_,_=account(client)
    ids={job(client,h).json()['data']['analysis_id'] for _ in range(3)}
    with ThreadPoolExecutor(4) as pool:
        tasks=list(pool.map(lambda _:claim(client,worker_headers),range(4)))
    received=[t['analysis_id'] for t in tasks if t]
    assert len(received)==len(set(received))==3 and set(received)==ids


def test_deletion_retries_after_partial_cross_database_failure(client,worker_headers):
    h,p,uid=account(client)
    cid=client.post('/v2/support/conversations',headers=h).json()['data']['conversation_id']
    job(client,h)
    assert client.post('/v2/me/withdrawal',headers=h,json={'current_password':p['password']}).status_code==202
    async def fail_once():
        class Offline:
            def begin(self):raise RuntimeError('temporary catalog outage')
        m=create_async_engine(url('app','member'));s=create_async_engine(url('app','support'))
        try:
            with pytest.raises(RuntimeError):await process_deletions(m,Offline(),s)
        finally:
            await m.dispose();await s.dispose()
    asyncio.run(fail_once())
    with db('support') as c:assert c.execute('SELECT count(*) FROM app.conversations WHERE conversation_id=%s',(cid,)).fetchone()[0]==0
    with db('member') as c:assert c.execute('SELECT state FROM app.account_deletions WHERE user_id=%s',(uid,)).fetchone()[0]=='pending'
    assert run_deletions()>=1
    with db('catalog') as c:assert c.execute('SELECT count(*) FROM app.analyses WHERE owner_id=%s',(uid,)).fetchone()[0]==0


def test_console_aggregates_settings_and_public_basic(client):
    ordinary,_,_=account(client)
    admin,_,uid=account(client);grant(uid)
    assert client.get('/v2/admin/overview',headers=ordinary).status_code==403
    r=client.get('/v2/admin/overview',headers=admin)
    assert r.status_code==200,r.text
    baseline=r.json()['data']
    assert baseline['members']>=2
    older,_,_=account(client)
    older_payment=pay(client,older)
    assert older_payment.status_code==201,older_payment.text
    with db('member') as c:
        c.execute('''UPDATE app.invoices SET period_start=
            date_trunc('day', now() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul' - interval '1 microsecond'
            WHERE invoice_id=%s''',(older_payment.json()['data']['invoice_id'],))
    payment=pay(client,ordinary)
    assert payment.status_code==201,payment.text
    r=client.get('/v2/admin/overview',headers=admin)
    assert r.status_code==200,r.text
    assert r.json()['data']['today_subscribers']==baseline['today_subscribers']+1
    # Today's mock revenue is a real server total (both payments were made today), not an estimate.
    with db('member') as c:
        paid_today=c.execute('SELECT coalesce(sum(amount),0) FROM app.invoices WHERE invoice_id=ANY(%s::uuid[])',
            ([older_payment.json()['data']['invoice_id'],payment.json()['data']['invoice_id']],)).fetchone()[0]
    from decimal import Decimal
    assert Decimal(r.json()['data']['today_mock_revenue_krw'])-Decimal(baseline['today_mock_revenue_krw'])==paid_today
    path='/v2/admin/support/settings'
    r=client.get(path,headers=admin);assert r.status_code==200,r.text
    v=r.json()['data']['version']
    data={'days':'월요일 ~ 금요일','startTime':'10:00','endTime':'19:00','awayMessage':'운영시간 안내','expected_version':v}
    assert client.put(path,headers=ordinary,json=data).status_code==403
    assert client.put(path,headers=admin,json=data).status_code==200
    assert client.put(path,headers=admin,json=data).status_code==409
    assert client.get(path,headers=admin).json()['data']['startTime']=='10:00'
    assert client.get('/v2/recommendations/basic').status_code==200
    assert client.get('/v2/recommendations/basic?selected_domain=invalid').status_code==422


def test_member_and_staff_share_one_login_namespace(client):
    password = 'Test-pass-427!'
    staff_id = 's' + uuid4().hex[:12]
    staff = {'login_id': staff_id, 'password': password, 'password_confirmation': password,
             'consent_version': 'provisional-v1', 'consent_accepted': True}
    assert client.post('/v2/admin/auth/signup', json=staff).status_code == 201
    member = dict(login_id=staff_id.upper(), password=password, password_confirmation=password,
                  consent_accepted=True, consent_version='provisional-v1', birth_date='2000-01-01', gender='male')
    taken = client.post('/v2/auth/signup', json=member)
    assert taken.status_code == 409 and taken.json()['error']['code'] == 'LOGIN_ID_TAKEN'
    assert client.get('/v2/auth/login-id-availability', params={'login_id': staff_id}).json()['data']['available'] is False
    # And the other direction: an existing member ID cannot become a staff ID.
    _, payload, _ = account(client)
    assert client.post('/v2/admin/auth/signup', json=staff | {'login_id': payload['login_id']}).status_code == 409
