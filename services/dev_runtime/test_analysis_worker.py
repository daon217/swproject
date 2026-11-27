import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import httpx
import pytest
from services.dev_runtime.analysis_worker import Worker
from services.recommendation.http_service import app
from fastapi.testclient import TestClient

TOKEN='t'*64
OFFER={'offer_id':'11111111-1111-1111-1111-111111111111','source':'demo','source_listing_id':'kettle',
 'variant_key':'blue','name':'주전자','price':'10000','currency':'KRW','condition':'new','availability':'available',
 'current_url':'https://store.example.test/p?id=1'}

@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv('WORKSPACE_TOKEN',TOKEN);monkeypatch.setenv('ANALYSIS_WORKER_TOKEN',TOKEN)
    monkeypatch.setenv('RECO_EMBEDDER','hash');monkeypatch.setenv('RECO_RANKER','rule')
    # HTTP/profile unit tests use a pre-built index. The real PostgreSQL path has separate integration tests.
    from contextlib import nullcontext
    from services.recommendation import http_service as service
    from services.recommendation.adapters.offers_api import offer_to_product
    from services.recommendation.adapters.local import InMemoryVectorIndex
    from services.recommendation.embedders import HashEmbedder
    encoder=HashEmbedder()
    index=InMemoryVectorIndex(None,encoder.name)
    class Catalog:
        def __init__(self,conn,kind):self.product=offer_to_product(OFFER,kind)
        def get_many(self,ids):return {self.product.product_id:self.product} if self.product.product_id in ids else {}
        def offer_ids(self,ids):return {p:OFFER['offer_id'] for p in ids}
    product=offer_to_product(OFFER,'product')
    index.upsert([(product.product_id,encoder.embed_query('주전자'))])
    monkeypatch.setattr(service.config,'connect',lambda: nullcontext(None))
    monkeypatch.setattr(service.config,'validate',lambda conn,kind: 'unit-test')
    monkeypatch.setattr(service.config,'embedder',lambda:encoder)
    monkeypatch.setattr(service,'PgCatalog',Catalog)
    monkeypatch.setattr(service,'PgVectorIndex',lambda conn,model:index)

def test_recommendation_http_auth_domain_and_allergens():
    c=TestClient(app);body={'query':'주전자','selected_domain':'product',
        'profile':{'user_id':'test','allergens':['milk','fragrance']}}
    assert c.post('/internal/process',json=body).status_code==401
    result=c.post('/internal/process',json=body,headers={'Authorization':'Bearer '+TOKEN})
    assert result.status_code==200,result.text
    assert result.json()['offer_ids']==[OFFER['offer_id']]
    assert result.json()['warnings']==[] # 식품이 아닌 상품에는 알레르기 경고를 붙이지 않는다.
    body.update(selected_domain='food',ingredients=['대두','우유'])
    body['profile']['allergens']=['soybean','milk']
    result=c.post('/internal/process',json=body,headers={'Authorization':'Bearer '+TOKEN})
    assert result.status_code==200,result.text
    assert result.json()['offer_ids']==[] # Missing catalog ingredients cannot be called safe.
    # Clients send and label 'soybean'; the internal 'soy' code must not leak back.
    assert {w['allergen'] for w in result.json()['warnings']}=={'soybean','milk'}
    # #59: seller-declared codes from the catalog are judged as codes (shellfish/pine_nut are not text-matchable).
    body.update(ingredients=['밀가루'],allergens_declared=['shellfish','pine_nut','Soybean'])
    body['profile']['allergens']=['shellfish','pine_nut','soybean','wheat','milk']
    warnings=c.post('/internal/process',json=body,headers={'Authorization':'Bearer '+TOKEN}).json()['warnings']
    assert {w['allergen']:w['evidence'] for w in warnings}=={'shellfish':'contains','pine_nut':'contains',
        'soybean':'contains','wheat':'contains'} # milk: ingredients were read and do not contain it



def test_normalized_url_candidates_and_process_422_vs_503(monkeypatch):
    from services.recommendation import http_service as service
    candidates, host, suffix = service._normalized_url_candidates('http://WWW.11st.co.kr:80/products/12345?opt=1#review')
    assert host == 'www.11st.co.kr'
    assert suffix == '/products/12345?opt=1'
    assert 'https://www.11st.co.kr/products/12345?opt=1' in candidates
    assert 'http://www.11st.co.kr/products/12345?opt=1' in candidates

    c = TestClient(app)
    # Invalid profile inputs (empty user_id, non-list allergens, unknown profile fields) must return 422, not 503
    for bad_profile in (
        {'user_id': ''},
        {'user_id': 'u', 'allergens': 'milk'},
        {'user_id': 'u', 'unknown_field': 123},
    ):
        resp = c.post('/internal/process', headers={'Authorization': 'Bearer ' + TOKEN}, json={
            'query': '주전자',
            'selected_domain': 'product',
            'profile': bad_profile,
        })
        assert resp.status_code == 422, (bad_profile, resp.status_code, resp.text)

    # If UserProfile.from_dict or downstream input validation raises KeyError, it must still return 422
    with monkeypatch.context() as m:
        m.setattr(service.UserProfile, 'from_dict', staticmethod(lambda _: (_ for _ in ()).throw(KeyError('missing_key'))))
        resp_key = c.post('/internal/process', headers={'Authorization': 'Bearer ' + TOKEN}, json={
            'query': '주전자',
            'selected_domain': 'product',
        })
        assert resp_key.status_code == 422

    # Dependency failure (e.g. DB connection OSError) must return 503
    with monkeypatch.context() as m:
        m.setattr(service.config, 'connect', lambda: (_ for _ in ()).throw(OSError('db down')))
        resp_dep = c.post('/internal/process', headers={'Authorization': 'Bearer ' + TOKEN}, json={
            'query': '주전자',
            'selected_domain': 'product',
        })
        assert resp_dep.status_code == 503

@pytest.mark.parametrize('vision', [False,True])
def test_worker_claim_image_8100_rank_complete(vision):
    calls=[]
    def handle(req):
        calls.append(req)
        path=req.url.path
        if path.endswith('/claim'):payload={'analysis_id':'job','lease_token':'lease','page_url':OFFER['current_url'],
            'selected_domain':'product','image_url':'/internal/image' if vision else None,
            'profile':{'user_id':'u','allergens':['milk']}}
        elif path=='/internal/catalog-context':return httpx.Response(200,json={'match':{'kind':'product','name':OFFER['name'],
            'allergens_declared':['shellfish']}})
        elif path=='/internal/image':
            assert req.headers['X-Worker-Lease']=='lease';return httpx.Response(200,content=b'image')
        elif path.startswith('/api/v1/vision/'):
            assert req.url.port==8100 and req.headers['Authorization']=='Bearer '+TOKEN
            return httpx.Response(200,json={'status':'success','ingredients':['우유']})
        elif path=='/internal/process':
            body=json.loads(req.content);assert body['profile']['allergens']==['milk'];assert 'offers' not in body
            assert body['allergens_declared']==['shellfish'] # catalog codes are forwarded as codes, not mixed into OCR text
            return httpx.Response(200,json={'offer_ids':[OFFER['offer_id']],'reasons':{},'ranker':'rule'})
        elif path.endswith('/complete'):
            assert json.loads(req.content)['offer_ids']==[OFFER['offer_id']];payload={'state':'completed'}
        else:raise AssertionError(str(req.url))
        return httpx.Response(200,json={'data':payload})
    assert Worker(httpx.Client(transport=httpx.MockTransport(handle))).once()
    assert calls[-1].url.path.endswith('/complete')
    assert not any(r.url.path=='/v2/offers' for r in calls)
    assert all(r.url.host in {'api','vision-api','recommendation'} for r in calls)

def test_worker_unknown_page_fails_without_arbitrary_fetch():
    paths=[]
    def handle(req):
        paths.append(req.url.path)
        if req.url.path.endswith('/claim'):return httpx.Response(200,json={'data':{'analysis_id':'x','lease_token':'l','page_url':'http://169.254.169.254/latest/','selected_domain':'food'}})
        if req.url.path=='/internal/catalog-context':return httpx.Response(200,json={'match':None})
        assert req.url.path.endswith('/fail') and json.loads(req.content)['code']=='CATALOG_NO_MATCH'  # 캡처 없음 + 카탈로그 없음(#26)
        return httpx.Response(200,json={'data':{}})
    assert Worker(httpx.Client(transport=httpx.MockTransport(handle))).once()
    assert paths[-1].endswith('/fail')


def test_worker_capture_only_job_uses_ocr_title_and_client_domain():
    """page_url 없이 캡처만 접수된 작업: URL 매칭 없이 OCR 상품명 + 클라이언트 selected_domain으로 추천한다."""
    calls=[]
    def handle(req):
        calls.append(req);path=req.url.path
        if path.endswith('/claim'):payload={'analysis_id':'cap','lease_token':'lease','page_url':None,
            'selected_domain':'product','image_url':'/internal/image','profile':{'user_id':'u','allergens':[]}}
        elif path=='/internal/catalog-context':return httpx.Response(200,json={'match':{'kind':'product','name':OFFER['name']}})
        elif path=='/internal/image':return httpx.Response(200,content=b'image')
        elif path.startswith('/api/v1/vision/'):
            if path.endswith('/init'):assert json.loads(req.content)['product_name'] is None # URL 매칭이 없으니 OCR에 맡긴다
            return httpx.Response(200,json={'status':'success','product_name':'주전자','ingredients':[]})
        elif path=='/internal/process':
            assert json.loads(req.content)['query']=='주전자'
            assert 'allergens_declared' not in json.loads(req.content) # no catalog match -> field omitted
            return httpx.Response(200,json={'offer_ids':[OFFER['offer_id']],'reasons':{},'ranker':'rule'})
        elif path.endswith('/complete'):
            body=json.loads(req.content);assert body['selected_domain']=='product' and body['offer_ids']==[OFFER['offer_id']];payload={'state':'completed'}
        else:raise AssertionError(str(req.url))
        return httpx.Response(200,json={'data':payload})
    assert Worker(httpx.Client(transport=httpx.MockTransport(handle))).once()
    assert calls[-1].url.path.endswith('/complete')
    assert not any(r.url.path=='/v2/offers' for r in calls)


def test_food_avoid_filter_does_not_assume_missing_ingredients_safe():
    c=TestClient(app)
    r=c.post('/internal/process',headers={'Authorization':'Bearer '+TOKEN},json={
        'query':'간식','selected_domain':'food',
        'profile':{'user_id':'u','avoid_ingredients':['설탕']}})
    assert r.status_code==200 and r.json()['offer_ids']==[]


@pytest.mark.parametrize('title,ingredients,expected',[
    # 식품: 상품명 또는 Vision이 읽은 성분표로 판별(카탈로그에 식품이 없어도)
    ('오뚜기 진라면 매운맛 5개입',[],'title_keyword'),
    ('[더블적립] 삼양식품 프리미엄 짜장라면 짜르르 12입',[],'title_keyword'),
    ('정화 오징어는땅콩을좋아해 40g',[],'title_keyword'),
    ('[소반옥] 왕갈비탕 600g',[],'title_keyword'),
    ('[차려낸] 햄 가득 송탄식 부대찌개',[],'title_keyword'),
    ('[KF365] 에어프라이어용 생선까스',[],'title_keyword'),
    ('필립스 에어프라이어 4.1L',[],None),
    ('브랜드명 없는 상품',['밀가루(밀:미국산)','설탕','대두유','정제소금'],'vision_ingredients'),
    # 일반 상품
    ('베이직스 노트북 16인치 사무용 8GB 256GB',[],None),
    ('스테인리스 전기 주전자 1.7L',[],None),
    # 식품 단어가 들어간 가전·화장품은 식품이 아님
    ('드롱기 전자동 커피머신',[],None),
    ('쿠쿠 전기밥솥 6인용',[],None),
    ('시어버터 핸드크림 50ml',['정제수','글리세린','부틸렌글라이콜','쉐어버터'],None),
    ('수분 크림',['정제수','글리세린','우유추출물','페녹시에탄올'],None),
])
def test_food_evidence_from_title_and_vision(title,ingredients,expected):
    """클라이언트가 종류를 보내지 않으면 Vision 성분표와 상품명으로 식품을 먼저 판별한다."""
    from services.dev_runtime.analysis_worker import food_evidence
    assert food_evidence(title,ingredients)==expected


def test_worker_concurrent_pool_processes_multiple_jobs_without_blocking():
    """앞선 작업이 Vision OCR을 폴링하는 동안에도 뒤 작업들을 동시에 가져와 병렬 완료한다."""
    import threading
    lock=threading.Lock()
    queue=[
        {'analysis_id':'job-1','lease_token':'lease-1','page_url':None,'selected_domain':'product','image_url':'/internal/image','profile':{'user_id':'u1','allergens':[]}},
        {'analysis_id':'job-2','lease_token':'lease-2','page_url':OFFER['current_url'],'selected_domain':'food','image_url':None,'profile':{'user_id':'u2','allergens':['milk']}},
        {'analysis_id':'job-3','lease_token':'lease-3','page_url':OFFER['current_url'],'selected_domain':'product','image_url':None,'profile':{'user_id':'u3','allergens':[]}},
    ]
    polls={'job-1-lease-1':0}
    completed_order=[]

    def handle(req):
        path=req.url.path
        if path.endswith('/claim'):
            with lock:
                payload=queue.pop(0) if queue else None
            return httpx.Response(200,json={'data':payload})
        if path=='/internal/catalog-context':
            return httpx.Response(200,json={'match':{'kind':'food','name':'우유 과자','ingredients':['우유','밀가루']}})
        if path=='/internal/image':
            return httpx.Response(200,content=b'image')
        if path.startswith('/api/v1/vision/status/'):
            sid=path.rsplit('/',1)[-1]
            with lock:
                polls[sid]=polls.get(sid,0)+1
                count=polls[sid]
            if count<3:
                return httpx.Response(200,json={'status':'processing'})
            return httpx.Response(200,json={'status':'success','product_name':'주전자','ingredients':[]})
        if path.startswith('/api/v1/vision/'):
            return httpx.Response(200,json={'status':'processing'})
        if path=='/internal/process':
            body=json.loads(req.content)
            return httpx.Response(200,json={'offer_ids':[OFFER['offer_id']],'reasons':{},'ranker':'rule','warnings':[{'type':'allergy','allergen':'milk','evidence':'contains','message':'우유 감지'}] if '우유' in body.get('ingredients',[]) else []})
        if path.endswith('/complete'):
            job_id=path.split('/')[-2]
            with lock:
                completed_order.append(job_id)
            return httpx.Response(200,json={'data':{'state':'completed'}})
        raise AssertionError(str(req.url))

    worker=Worker(httpx.Client(transport=httpx.MockTransport(handle)),max_concurrency=3,poll_interval=0.05)
    assert worker.drain_concurrent(max_workers=3)==3
    assert set(completed_order)=={'job-1','job-2','job-3'}
    # job-2 and job-3 finish while job-1 is still polling Vision OCR
    assert completed_order[-1]=='job-1'


def test_elevenst_offline_backend_adapter_observation_and_extension():
    from unittest.mock import Mock
    from services.collector.elevenst_offline.backend_adapter import (
        ElevenstBackendAdapter,
        prepare_elevenst_extension,
        prepare_elevenst_observation,
    )
    from services.collector.elevenst_offline.parser import parse_listing

    raw=json.dumps({
        'data':{
            'products':[{
                'id':'fixture-1',
                'optionId':'OPT-1',
                'title':'Synthetic test product',
                'finalPrc':'1,234',
                'linkUrl':'https://m.11st.co.kr/products/fixture-1',
                'imageUrl':'https://cdn.011st.com/image/synthetic.jpg',
                'currency':'KRW',
                'sellerName':'Synthetic shop',
                'categoryName':'Test category',
                'brandName':'11번가브랜드',
            }],
            'pagination':{'pageNo':1,'hasMore':False,'nextPageNo':None},
        }
    })
    row=parse_listing(raw,'2026-11-18T00:00:00+00:00')[0][0]
    row.update(
        source='elevenst_test',
        product_url='https://store.example.test/products/fixture-1',
        image_url='https://store.example.test/images/fixture-1.jpg',
    )
    cfg={
        'backend_enabled':True,
        'backend_owner_approved':True,
        'price_semantics_confirmed':True,
        'backend_delivery':{
            'mode':'synthetic_test',
            'allowed_product_hosts':['store.example.test'],
            'currencies':['KRW'],
        },
    }
    obs=prepare_elevenst_observation(row,cfg,selected_domain='product',condition='new')
    assert obs['schema_version']==2 and obs['price']=='1234'
    ext=prepare_elevenst_extension(row,cfg,matching_profile={'model_number':'11ST-M1','gtin':'8801043014809'})
    assert ext['matching_profile']['brand']=='11번가브랜드' and ext['matching_profile']['model_number']=='11ST-M1'
    tx=Mock(side_effect=[
        (201,{'state':'applied','change_kind':'created','offer_id':'00000000-0000-0000-0000-000000000011'}),
        (201,{'state':'applied','change_kind':'updated','extension_id':'00000000-0000-0000-0000-000000000022'}),
    ])
    res=ElevenstBackendAdapter(cfg,tx).send('00000000-0000-0000-0000-000000000001',row)
    assert res['applied'] is True and res['extension_applied'] is True


def _worker_with(vision_status=None, process=None, page_url=None, domain=None, allergens=(), ingredients=()):
    """Mock backend/vision/recommender; returns (worker, captured fail/complete bodies)."""
    sent={}
    def handle(req):
        path=req.url.path
        if path.endswith('/claim'):
            return httpx.Response(200,json={'data':{'analysis_id':'a1','lease_token':'lease','page_url':page_url,
                'selected_domain':domain,'image_url':'/internal/image','profile':{'user_id':'u','allergens':list(allergens)}}})
        if path=='/internal/image':return httpx.Response(200,content=b'image')
        if path.startswith('/api/v1/vision/'):
            if vision_status and path.startswith('/api/v1/vision/status'):return vision_status(req)
            return httpx.Response(200,json={'status':'success','product_name':'무지 상품','ingredients':list(ingredients)})
        if path=='/internal/process':
            return process(req) if process else httpx.Response(200,json={'offer_ids':[],'reasons':{},'ranker':'rule','warnings':[]})
        if path.endswith(('/fail','/complete')):
            sent[path.rsplit('/',1)[1]]=json.loads(req.content);return httpx.Response(200,json={'data':{}})
        raise AssertionError(str(req.url))
    return Worker(httpx.Client(transport=httpx.MockTransport(handle))),sent


def test_vision_404_is_reported_not_mistaken_for_lost_lease():
    worker,sent=_worker_with(vision_status=lambda req:httpx.Response(404,json={'detail':'session gone'}))
    assert worker.once()
    assert sent['fail']=={'lease_token':'lease','code':'DEPENDENCY_UNAVAILABLE','retryable':False}
    assert 'complete' not in sent


def test_transient_dependency_errors_are_retryable():
    def down(req):raise httpx.ConnectError('refused',request=req)
    worker,sent=_worker_with(process=down)
    assert worker.once()
    assert sent['fail']=={'lease_token':'lease','code':'DEPENDENCY_UNAVAILABLE','retryable':True}
    worker,sent=_worker_with(process=lambda req:httpx.Response(503))
    assert worker.once() and sent['fail']['retryable'] is True
    worker,sent=_worker_with(process=lambda req:httpx.Response(422))
    assert worker.once() and sent['fail']['retryable'] is False


def test_malformed_dependency_payload_fails_job_immediately():
    worker,sent=_worker_with(process=lambda req:httpx.Response(200,json={'unexpected':True}))
    assert worker.once()
    assert sent['fail']['code']=='RECOMMENDATION_FAILED' and sent['fail']['retryable'] is False


def test_inferred_product_with_allergy_profile_does_not_emit_false_unknown_warnings():
    # 성분표가 아직 읽히지 않았거나 알레르기 성분이 감지되지 않은 경우에는 무조건 '알레르기 주의'(unknown)를 띄우지 않는다
    worker,sent=_worker_with(allergens=['milk','peanut','nickel'],ingredients=['귀리','꿀'])
    assert worker.once()
    warnings=sent['complete']['metadata']['warnings']
    assert sent['complete']['selected_domain']=='product'
    assert warnings==[]
    # 성분 글자가 전혀 없는 일반 상품: 경고를 붙이지 않는다(모든 상품 페이지에 '알레르기 주의'가 뜨던 문제)
    worker,sent=_worker_with(allergens=['milk','peanut'])
    assert worker.once() and sent['complete']['metadata']['warnings']==[]
    # The client explicitly chose product: no extra warning.
    worker,sent=_worker_with(allergens=['milk'],domain='product')
    assert worker.once() and sent['complete']['metadata']['warnings']==[]



def test_page_own_offer_is_not_recommended():
    # 사료 페이지에서 바로 그 사료를 추천하던 문제: 매칭된 판매처 상품 자신은 뺀다
    own, other = 'own-offer', 'other-offer'
    sent = {}
    def handle(req):
        path = req.url.path
        if path.endswith('/claim'):
            return httpx.Response(200, json={'data': {'analysis_id': 'a1', 'lease_token': 'l', 'page_url': 'https://shop.example.test/p/1',
                'selected_domain': None, 'image_url': None, 'profile': {'user_id': 'u', 'allergens': []}}})
        if path == '/internal/catalog-context':
            return httpx.Response(200, json={'match': {'kind': 'product', 'name': '퓨리나 사료', 'offer_id': own}})
        if path == '/internal/process':
            return httpx.Response(200, json={'offer_ids': [own, other], 'reasons': {}, 'ranker': 'rule', 'warnings': []})
        if path.endswith('/complete'):
            sent['complete'] = json.loads(req.content)
            return httpx.Response(200, json={'data': {'state': 'completed'}})
        raise AssertionError(path)
    assert Worker(httpx.Client(transport=httpx.MockTransport(handle))).once()
    assert sent['complete']['offer_ids'] == [other]


def test_worker_reuses_completed_vision_scroll_session_without_re_ocr():
    # 스크롤 중 Vision이 page_session_id로 성분표를 이미 찾은 경우(status=success + ingredients),
    # 이미지를 다시 다운로드해 /vision/init·/frame으로 재실행하지 않고 GET /vision/status/{page_session_id}의 성분을 바로 쓴다.
    calls = []
    sent = {}
    def handle(req):
        path = req.url.path
        calls.append(path)
        if path.endswith('/claim'):
            return httpx.Response(200, json={'data': {
                'analysis_id': 'a1', 'lease_token': 'l', 'page_url': None,
                'page_session_id': 'scroll-session-1', 'page_title': '한방선생 볶은 메밀',
                'selected_domain': 'food', 'image_url': '/internal/image',
                'profile': {'user_id': 'u', 'allergens': ['buckwheat', 'wheat']},
            }})
        if path == '/api/v1/vision/status/scroll-session-1':
            return httpx.Response(200, json={
                'session_id': 'scroll-session-1',
                'status': 'success',
                'product_name': '한방선생 볶은 메밀',
                'product_category': 'food_health',
                'ingredients': ['메밀 100%', '밀 함유'],
            })
        if path == '/internal/process':
            body = json.loads(req.content)
            sent['process'] = body
            return httpx.Response(200, json={
                'offer_ids': [], 'reasons': {}, 'ranker': 'rule',
                'warnings': [{'type': 'allergy', 'allergen': 'buckwheat', 'evidence': 'contains', 'message': '메밀 함유'}],
            })
        if path.endswith('/complete'):
            sent['complete'] = json.loads(req.content)
            return httpx.Response(200, json={'data': {'state': 'completed'}})
        raise AssertionError(f'Unexpected call: {path}')
    assert Worker(httpx.Client(transport=httpx.MockTransport(handle))).once()
    assert '/internal/image' not in calls
    assert '/api/v1/vision/init' not in calls
    assert sent['process']['ingredients'] == ['메밀 100%', '밀 함유']
    assert sent['complete']['metadata']['ingredients'] == ['메밀 100%', '밀 함유']
    assert sent['complete']['metadata']['warnings'][0]['allergen'] == 'buckwheat'

