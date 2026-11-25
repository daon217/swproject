"""서지웅 브랜치(2026-11-26) 백엔드 변경 검증: 비회원 분석(X-Guest-Key), 결과 구역(AI·해외·중고), 경고 구역 필터, 회원 설정 칸."""
import os
from uuid import uuid4

import pytest

from test_contract import fixture
from test_independent_features import claim, db, job, worker_headers  # noqa: F401  (fixture)
from test_members_billing import account, client  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(os.getenv('CATALOG_INTEGRATION') != '1', reason='requires disposable migrated databases')


def offer(client, **patch):
    item = fixture() | dict(source='sections_' + uuid4().hex[:12], source_listing_id=uuid4().hex,
                            observation_key=uuid4().hex) | patch
    r = client.post('/internal/v2/crawl-runs/' + str(uuid4()) + '/observations', json=item,
                    headers={'Authorization': 'Bearer ' + os.environ['COLLECTOR_TOKEN']})
    assert r.status_code == 201, r.text
    return r.json()['offer_id']


def guest(key=None):
    return {'X-Guest-Key': key or uuid4().hex + uuid4().hex}


def complete(client, wh, task, offer_ids, domain='product', warnings=()):
    body = {'lease_token': task['lease_token'], 'selected_domain': domain, 'offer_ids': offer_ids,
            'metadata': {'warnings': list(warnings)}}
    r = client.post('/internal/v2/analyses/' + task['analysis_id'] + '/complete', headers=wh, json=body)
    assert r.status_code == 200, r.text


def test_guest_analysis_is_isolated_by_device_key(client, worker_headers):
    assert job(client, {}).status_code == 401                       # 로그인도 기기 키도 없음
    assert job(client, {'X-Guest-Key': 'short'}).status_code == 401  # 형식이 틀린 키
    me = guest()
    created = job(client, me)
    assert created.status_code == 202, created.text
    ident = created.json()['data']['analysis_id']
    assert client.get('/analyses/' + ident, headers=me).status_code == 200
    assert client.get('/analyses/' + ident, headers=guest()).status_code == 404   # 다른 기기
    h, _, _ = account(client)
    assert client.get('/analyses/' + ident, headers=h).status_code == 404        # 회원도 못 봄
    # 잘못된 로그인 토큰은 비회원으로 바뀌지 않는다
    assert client.get('/analyses/' + ident, headers=me | {'Authorization': 'Bearer nope'}).status_code == 401
    task = claim(client, worker_headers)
    assert task['analysis_id'] == ident
    assert task['profile'] == {'user_id': 'guest', 'allergens': [], 'include_used': False, 'include_overseas': False,
                               'avoid_ingredients': [], 'preferences': ''}
    assert 'guest' not in task and 'owner_id' not in task
    domestic, overseas = offer(client), offer(client, currency='USD', price='19.9900')
    complete(client, worker_headers, task, [domestic, overseas])
    result = client.get('/analyses/' + ident, headers=me).json()['data']
    assert [s['kind'] for s in result['sections']] == ['ai']                   # 비회원: 해외 구역 없음
    assert [c['offer_id'] for c in result['sections'][0]['items']] == [domestic]
    assert client.post('/analyses/' + ident + '/cancel', headers=guest()).status_code == 404


def test_member_sections_split_used_and_overseas_and_filter_warnings(client, worker_headers):
    h, _, _ = account(client)
    version = client.get('/v2/me', headers=h).json()['data']['profile']['version']
    r = client.patch('/v2/me/profile', headers=h, json={'expected_version': version, 'include_used': True,
                                                        'height_cm': 172.5, 'foot_mm': 265})
    assert r.status_code == 200, r.text
    profile = client.get('/v2/me', headers=h).json()['data']['profile']
    assert profile['include_overseas'] is True and profile['height_cm'] == 172.5 and profile['foot_mm'] == 265
    ids = [offer(client), offer(client), offer(client, currency='USD', price='9.5000'), offer(client, condition='used')]
    ident = job(client, h).json()['data']['analysis_id']
    task = claim(client, worker_headers)
    assert task['profile']['include_used'] is True and task['profile']['include_overseas'] is True
    complete(client, worker_headers, task, ids, warnings=[
        {'allergen': 'milk', 'evidence': 'unknown', 'message': '식품 알레르기'},
        {'allergen': 'nickel', 'evidence': 'unknown', 'message': '피부'}])
    result = client.get('/analyses/' + ident, headers=h).json()['data']
    sections = {s['kind']: [c['offer_id'] for c in s['items']] for s in result['sections']}
    assert sections == {'ai': ids[:2], 'overseas': [ids[2]], 'used': [ids[3]]}
    overseas_card = result['sections'][1]['items'][0]
    assert overseas_card['condition'] == 'new' and overseas_card['subtitle'] == '해외 판매처 · USD'
    # 일반 상품 결과에는 식품 알레르기 경고를 싣지 않는다(식품 결과에는 식품 경고만)
    assert [w['allergen'] for w in result['warnings']] == ['nickel']


def test_withdrawal_clears_body_sizes(client):
    h, _, uid = account(client)
    version = client.get('/v2/me', headers=h).json()['data']['profile']['version']
    assert client.patch('/v2/me/profile', headers=h, json={'expected_version': version, 'weight_kg': 60,
                                                           'include_overseas': False}).status_code == 200
    assert client.post('/v2/me/withdrawal', headers=h, json={'current_password': 'Test-pass-927!'}).status_code == 202
    with db('member', 'owner') as c:
        row = c.execute('SELECT height_cm,weight_kg,foot_mm,include_overseas FROM app.members WHERE user_id=%s',
                        (uid,)).fetchone()
    assert row == (None, None, None, True)
