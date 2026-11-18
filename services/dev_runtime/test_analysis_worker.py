import json
import httpx
import pytest
from services.dev_runtime.analysis_worker import Worker,context_url
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

def test_recommendation_http_auth_domain_and_allergens():
    c=TestClient(app);body={'query':'주전자','selected_domain':'product','offers':[OFFER],
        'profile':{'user_id':'test','allergens':['milk','fragrance']}}
    assert c.post('/internal/process',json=body).status_code==401
    result=c.post('/internal/process',json=body,headers={'Authorization':'Bearer '+TOKEN})
    assert result.status_code==200,result.text
    assert result.json()['offer_ids']==[OFFER['offer_id']]
    assert len(result.json()['warnings'])==2
    body.update(selected_domain='food',ingredients=['대두','우유'])
    body['profile']['allergens']=['soybean','milk']
    result=c.post('/internal/process',json=body,headers={'Authorization':'Bearer '+TOKEN})
    assert result.status_code==200,result.text
    assert result.json()['offer_ids']==[] # Missing catalog ingredients cannot be called safe.
    assert {w['allergen'] for w in result.json()['warnings']}=={'soy','milk'}

def test_product_query_ids_are_not_collapsed():
    assert context_url('https://shop.test/p?id=1')!=context_url('https://shop.test/p?id=2')

@pytest.mark.parametrize('vision', [False,True])
def test_worker_claim_image_8100_rank_complete(vision):
    calls=[]
    def handle(req):
        calls.append(req)
        path=req.url.path
        if path.endswith('/claim'):payload={'analysis_id':'job','lease_token':'lease','page_url':OFFER['current_url'],
            'selected_domain':'product','image_url':'/internal/image' if vision else None,
            'profile':{'user_id':'u','allergens':['milk']}}
        elif path=='/v2/offers':return httpx.Response(200,json={'items':[OFFER] if req.url.params['selected_domain']=='product' else [],'next_cursor':None})
        elif path=='/internal/image':
            assert req.headers['X-Worker-Lease']=='lease';return httpx.Response(200,content=b'image')
        elif path.startswith('/api/v1/vision/'):
            assert req.url.port==8100 and req.headers['Authorization']=='Bearer '+TOKEN
            return httpx.Response(200,json={'status':'success','ingredients':['우유']})
        elif path=='/internal/process':
            body=json.loads(req.content);assert body['profile']['allergens']==['milk']
            return httpx.Response(200,json={'offer_ids':[OFFER['offer_id']],'reasons':{},'ranker':'rule'})
        elif path.endswith('/complete'):
            assert json.loads(req.content)['offer_ids']==[OFFER['offer_id']];payload={'state':'completed'}
        else:raise AssertionError(str(req.url))
        return httpx.Response(200,json={'data':payload})
    assert Worker(httpx.Client(transport=httpx.MockTransport(handle))).once()
    assert calls[-1].url.path.endswith('/complete')
    assert all(r.url.host in {'api','vision-api','recommendation'} for r in calls)

def test_worker_unknown_page_fails_without_arbitrary_fetch():
    paths=[]
    def handle(req):
        paths.append(req.url.path)
        if req.url.path.endswith('/claim'):return httpx.Response(200,json={'data':{'analysis_id':'x','lease_token':'l','page_url':'http://169.254.169.254/latest/','selected_domain':'food'}})
        if req.url.path=='/v2/offers':return httpx.Response(200,json={'items':[],'next_cursor':None})
        assert req.url.path.endswith('/fail') and json.loads(req.content)['code']=='OCR_FAILED'
        return httpx.Response(200,json={'data':{}})
    assert Worker(httpx.Client(transport=httpx.MockTransport(handle))).once()
    assert paths[-1].endswith('/fail')
