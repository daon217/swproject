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
        {'allergen': 'milk', 'evidence': 'unknown', 'message': '성분표를 인식하지 못함(식품 확인 실패)'},
        {'allergen': 'egg', 'evidence': 'contains', 'message': '식품 함유'},
        {'allergen': 'nickel', 'evidence': 'unknown', 'message': '피부'}])
    result = client.get('/analyses/' + ident, headers=h).json()['data']
    sections = {s['kind']: [c['offer_id'] for c in s['items']] for s in result['sections']}
    assert sections == {'ai': ids[:2], 'overseas': [ids[2]], 'used': [ids[3]]}
    overseas_card = result['sections'][1]['items'][0]
    assert overseas_card['condition'] == 'new' and overseas_card['subtitle'] == '해외 판매처 · USD'
    # 일반 상품 결과: 식품 '함유' 경고는 싣지 않지만, 식품 확인 실패(unknown) 경고는 남긴다(#83)
    assert [w['allergen'] for w in result['warnings']] == ['milk', 'nickel']


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


def test_analysis_without_page_title_is_accepted_and_title_reaches_worker(client, worker_headers):
    # #88: 상품명이 없으면 result_metadata에 NULL을 넣어 409로 실패하던 문제
    h, _, _ = account(client)
    assert job(client, h).status_code == 202
    titled = job(client, h, page_title='  꿀픽 땅콩 쿠키 ')
    assert titled.status_code == 202, titled.text
    tasks = [claim(client, worker_headers), claim(client, worker_headers)]
    assert {t.get('page_title') for t in tasks} == {None, '꿀픽 땅콩 쿠키'}


def test_retry_waits_before_the_next_claim(client, worker_headers, monkeypatch):
    # #25: 재시도 가능한 실패는 바로 다시 가져가지 않는다
    monkeypatch.setenv('ANALYSIS_RETRY_BASE_SECONDS', '30')
    h, _, _ = account(client)
    ident = job(client, h).json()['data']['analysis_id']
    task = claim(client, worker_headers)
    r = client.post('/internal/v2/analyses/' + ident + '/fail', headers=worker_headers,
                    json={'lease_token': task['lease_token'], 'code': 'DEPENDENCY_UNAVAILABLE', 'retryable': True})
    assert r.json()['data']['state'] == 'queued'
    assert client.post('/internal/v2/analyses/claim', headers=worker_headers, json={'worker_id': 'w'}).json()['data'] is None
    with db('catalog') as c:
        c.execute("UPDATE app.analyses SET updated_at=now()-interval '31 seconds' WHERE analysis_id=%s", (ident,))
    assert claim(client, worker_headers)['analysis_id'] == ident


def test_unknown_allergy_codes_are_rejected_and_labels_normalized(client):
    # #79: 앱이 고르는 코드만 저장(식품 이름·별칭은 코드로)
    h, _, _ = account(client)
    version = client.get('/v2/me', headers=h).json()['data']['profile']['version']
    bad = client.patch('/v2/me/profile', headers=h, json={'expected_version': version, 'allergies': ['꽃가루']})
    assert bad.status_code == 422
    ok = client.patch('/v2/me/profile', headers=h, json={'expected_version': version,
                                                         'allergies': ['우유', 'soy', 'nickel', 'milk']})
    assert ok.status_code == 200, ok.text
    assert sorted(ok.json()['data']['profile']['allergies']) == ['milk', 'nickel', 'soybean']


def test_guest_analyses_have_their_own_rate_limit(client, worker_headers, monkeypatch):
    # #84: 기기 키를 바꿔도 접속 주소당 분당 접수 수가 제한된다
    monkeypatch.setenv('GUEST_ANALYSES_PER_MINUTE', '2')
    with db('member', 'owner') as c:
        c.execute('DELETE FROM app.auth_attempts')
    codes = [job(client, guest()).status_code for _ in range(3)]
    assert codes == [202, 202, 429]


def test_admin_signup_can_be_rejected_and_reapplied(client):
    # #60: 관리자 가입 신청 거절(대기 신청만 삭제, 감사 기록), 같은 아이디로 다시 신청 가능
    from test_independent_features import grant
    login_id = 'r' + uuid4().hex[:12]
    application = {'login_id': login_id, 'password': 'Test-pass-427!', 'password_confirmation': 'Test-pass-427!',
                   'consent_version': 'provisional-v1', 'consent_accepted': True}
    path = '/v2/admin/auth'
    user_id = client.post(path + '/signup', json=application).json()['data']['user_id']
    reviewer, _, reviewer_id = account(client)
    assert client.post(f'{path}/requests/{user_id}/reject', headers=reviewer).status_code == 403
    grant(reviewer_id)
    assert client.post(f'{path}/requests/{user_id}/reject', headers=reviewer).status_code == 200
    assert client.post(f'{path}/requests/{user_id}/reject', headers=reviewer).status_code == 404
    with db('member') as c:
        audit = c.execute('SELECT actor_id,action FROM app.admin_audit WHERE target_id=%s', (user_id,)).fetchall()
    assert [(str(a), b) for a, b in audit] == [(reviewer_id, 'reject')]
    assert client.post(path + '/signup', json=application).status_code == 201
