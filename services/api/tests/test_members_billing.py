"""Actual member DB tests: ownership, transactions, session lifecycle and mock billing."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import psycopg
import pytest
from fastapi.testclient import TestClient
from kkulpick.api import app
from kkulpick.db import url

pytestmark = pytest.mark.skipif(os.getenv('CATALOG_INTEGRATION') != '1', reason='requires migrated disposable databases')


def member_db():
    u = url('app','member')
    return psycopg.connect(host=u.host, port=u.port, dbname=u.database, user=u.username, password=u.password, autocommit=True)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('BILLING_MODE','mock')
    monkeypatch.setenv('APP_ENV','development')
    monkeypatch.setenv('AUTH_REQUESTS_PER_MINUTE','10000')
    monkeypatch.setenv('MOCK_PAYMENT_OUTCOME','succeeded')
    monkeypatch.setenv('BILLING_TEST_TOKEN','billing-test-'+'a'*40)
    with TestClient(app) as c:
        yield c


def account(c):
    payload = dict(login_id='u'+uuid4().hex[:12], password='Test-pass-927!', password_confirmation='Test-pass-927!',
                   consent_accepted=True, consent_version='provisional-v1', birth_date='2000-01-01', gender='male', allergies=['milk'])
    r = c.post('/v2/auth/signup',json=payload)
    assert r.status_code == 201, r.text
    login = c.post('/v2/auth/login',json={k:payload[k] for k in ('login_id','password')})
    assert login.status_code == 200, login.text
    return {'Authorization':'Bearer '+login.json()['data']['token']}, payload, r.json()['data']['user_id']


def pay(c, headers, key=None, method='card'):
    return c.post('/v2/me/subscriptions',headers=headers|{'Idempotency-Key':key or uuid4().hex},
                  json={'plan_id':'premium-monthly','payment_method':method})


def test_auth_profile_password_logout(client):
    h,p,uid = account(client)
    assert client.get('/v2/me').status_code == 401
    body = client.get('/v2/me',headers=h).json()['data']
    assert body['profile']['allergies'] == ['milk'] and not body['premium']
    assert client.get('/v2/auth/login-id-availability',params={'login_id':p['login_id'].upper()}).json()['data']['available'] is False
    assert client.post('/v2/auth/signup',json=p|{'login_id':p['login_id'].upper()}).status_code == 409
    patch = client.patch('/v2/me/profile',headers=h,json={'expected_version':1,'birth_date':None})
    assert patch.status_code == 200 and patch.json()['data']['profile']['birth_date'] is None
    assert patch.json()['data']['profile']['allergies'] == ['milk']
    assert client.patch('/v2/me/profile',headers=h,json={'expected_version':1,'gender':'female'}).status_code == 409
    assert client.patch('/v2/me/profile',headers=h,json={'expected_version':2,'ingredient_filter':{'avoid':['milk'],'prefer':[]}}).status_code == 403
    login2=client.post('/v2/auth/login',json={k:p[k] for k in ('login_id','password')}).json()['data']['token']
    change=dict(current_password=p['password'],new_password='Replacement-28!',new_password_confirmation='Replacement-28!')
    assert client.patch('/v2/me/password',headers=h,json=change).status_code == 204
    assert client.get('/v2/me',headers={'Authorization':'Bearer '+login2}).status_code == 401
    assert client.post('/v2/auth/login',json={k:p[k] for k in ('login_id','password')}).status_code == 401
    with member_db() as db:
        encoded=db.execute('SELECT password_hash FROM app.members WHERE user_id=%s',(uid,)).fetchone()[0]
        assert encoded.startswith('scrypt$') and 'Replacement' not in encoded
        token=db.execute('SELECT token_hash FROM app.sessions WHERE user_id=%s',(uid,)).fetchone()[0]
        assert token not in h['Authorization']
    assert client.post('/v2/auth/logout',headers=h).status_code == 204
    assert client.get('/v2/me',headers=h).status_code == 401


@pytest.mark.parametrize('method',['card','bank_transfer','naverpay','kakaopay','tosspay'])
def test_payment_methods_mock_only(client,method):
    h,_,_=account(client)
    r=pay(client,h,method=method)
    assert r.status_code == 201, r.text
    assert r.json()['data']['billing_mode'] == 'mock'
    assert client.get('/v2/me/subscription',headers=h).json()['data']['active']


def test_duplicate_and_concurrent_payment(client):
    h,_,uid=account(client); key=uuid4().hex
    with ThreadPoolExecutor(4) as pool:
        results=list(pool.map(lambda _:pay(client,h,key),range(4)))
    assert sorted(r.status_code for r in results)==[200,200,200,201], [r.text for r in results]
    assert len({r.json()['data']['payment_id'] for r in results})==1
    assert pay(client,h,key,method='tosspay').status_code==409
    assert pay(client,h).status_code==409
    with member_db() as db:
        assert db.execute('SELECT count(*) FROM app.invoices WHERE user_id=%s',(uid,)).fetchone()[0]==1
    assert client.get('/v2/me',headers=h).json()['data']['premium']
    assert client.post('/v2/me/subscription/cancel',headers=h).json()['data']['active']
    assert client.get('/v2/me/subscription',headers=h).json()['data']['cancel_at_period_end']
    with member_db() as db:
        db.execute("UPDATE app.subscriptions SET entitlement_end=now()-interval '1 second' WHERE user_id=%s",(uid,))
    assert not client.get('/v2/me',headers=h).json()['data']['premium']
    assert pay(client,h).status_code==201


def test_failed_payment_persisted_without_entitlement(client,monkeypatch):
    h,_,_=account(client);key=uuid4().hex
    monkeypatch.setenv('MOCK_PAYMENT_OUTCOME','failed')
    assert pay(client,h,key).status_code==402
    monkeypatch.setenv('MOCK_PAYMENT_OUTCOME','succeeded')
    assert pay(client,h,key).status_code==402  # exact retry never changes original outcome
    assert not client.get('/v2/me',headers=h).json()['data']['premium']
    assert len(client.get('/v2/me/payments',headers=h).json()['data'])==1
    assert pay(client,h).status_code==201


def test_pending_reconciliation_auth_and_refund_ownership(client,monkeypatch):
    h,_,_=account(client);other,_,_=account(client); key=uuid4().hex
    monkeypatch.setenv('MOCK_PAYMENT_OUTCOME','pending')
    r=pay(client,h,key); assert r.status_code==202
    pid=r.json()['data']['payment_id']
    assert not client.get('/v2/me',headers=h).json()['data']['premium']
    assert pay(client,h).status_code==409
    target='/internal/v2/mock-payments/'+pid+'/resolve'
    assert client.post(target,headers=h,json={'outcome':'succeeded'}).status_code==401
    admin={'Authorization':'Bearer '+os.environ['BILLING_TEST_TOKEN']}
    assert client.post(target,headers=admin,json={'outcome':'succeeded'}).status_code==200
    end=client.get('/v2/me/subscription',headers=h).json()['data']['entitlement_end']
    assert client.post(target,headers=admin,json={'outcome':'succeeded'}).status_code==200
    assert client.get('/v2/me/subscription',headers=h).json()['data']['entitlement_end']==end
    assert client.post(target,headers=admin,json={'outcome':'failed'}).status_code==409
    refund='/v2/me/payments/'+pid+'/mock-refund'
    assert client.post(refund,headers=other).status_code==404
    assert client.get('/v2/me/payments',headers=other).json()['data']==[]
    assert client.post(refund,headers=h).status_code==200
    assert client.post(refund,headers=h).status_code==200
    assert not client.get('/v2/me',headers=h).json()['data']['premium']
    assert pay(client,h,key).status_code==409


def test_disabled_and_production_mock_guard(client,monkeypatch):
    h,_,_=account(client)
    monkeypatch.setenv('BILLING_MODE','disabled')
    assert pay(client,h).status_code==503
    monkeypatch.setenv('BILLING_MODE','mock'); monkeypatch.setenv('APP_ENV','production')
    assert pay(client,h).status_code==503


def test_invalid_and_private_error_response(client,monkeypatch):
    r=client.post('/v2/auth/signup',json={'password':'do-not-leak-this'})
    assert r.status_code==422 and 'do-not-leak-this' not in r.text
    assert r.json()['error']['code']=='INVALID_INPUT' and r.headers['X-Request-ID']==r.json()['request_id']
    assert r.headers['Cache-Control']=='no-store'
    monkeypatch.setenv('AUTH_REQUESTS_PER_MINUTE','0')
    r=client.post('/v2/auth/login',json={'login_id':'testuser','password':'Secret-7'})
    assert r.status_code==429 and r.headers['Retry-After']=='60'


def test_failed_transaction_rolls_back_invoice(client,monkeypatch):
    h,_,uid=account(client)
    monkeypatch.setenv('MOCK_PAYMENT_OUTCOME','invalid-configuration')
    assert pay(client,h).status_code==503
    with member_db() as db:
        assert db.execute('SELECT count(*) FROM app.invoices WHERE user_id=%s',(uid,)).fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM app.subscriptions WHERE user_id=%s',(uid,)).fetchone()[0]==0


def test_mock_entitlement_disabled_outside_development(client,monkeypatch):
    h,_,_=account(client)
    assert pay(client,h).status_code==201
    monkeypatch.setenv('APP_ENV','production')
    assert not client.get('/v2/me',headers=h).json()['data']['premium']
