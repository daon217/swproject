"""Claim -> catalog or Vision(8100) -> recommender -> backend result.

No arbitrary page URL is fetched. Only configured internal services receive requests.
Jobs, image access and completion all use the backend's authenticated lease protocol.
Concurrent worker pool prevents a slow OCR job from blocking other queued analyses.
"""
import base64
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import logging
import os
import re
import time
from urllib.parse import urlsplit
import httpx

log=logging.getLogger('analysis-worker')

def context_url(value):
    u=urlsplit(value)
    return (u.hostname or '').lower(),u.path,u.query

# 식품 판별 신호. Vision이 원재료명·영양정보 아래에서 성분을 읽었거나, 상품명이 식품일 때 food로 본다.
# 카탈로그에 식품이 없어도 판별되도록 카탈로그 겹침보다 먼저 확인한다.
FOOD_TITLE=re.compile(r'라면|과자|스낵|쿠키|비스킷|초콜릿|초코|젤리|사탕|캔디|껌|아이스크림|빵|케이크|떡|만두|국수|파스타|우동|냉면|짜장|짬뽕|'
    r'즉석밥|햇반|도시락|밀키트|반찬|김치|소스|양념|간장|된장|고추장|케첩|마요네즈|드레싱|식용유|참기름|'
    r'우유|두유|요거트|요구르트|치즈|버터|분유|커피|음료|주스|탄산|생수|녹차|홍차|'
    r'견과|땅콩|아몬드|호두|캐슈|시리얼|그래놀라|오트밀|햄|소시지|베이컨|참치|어묵|두부|계란|달걀|'
    r'정육|한우|돼지고기|닭가슴살|닭고기|소고기|쌀|현미|잡곡|과일|사과|딸기|복숭아|오징어|새우|멸치|'
    r'식품|간식|과자류|영양제|홍삼|단백질\s*쉐이크|프로틴')
# 화장품·생활용품 성분표는 식품 성분표로 보지 않는다(전성분에 '크림'·'우유' 같은 말이 섞여도 식품 아님).
NON_FOOD=re.compile(r'화장품|스킨|토너|로션|에센스|세럼|앰플|선크림|썬크림|클렌징|폼클렌저|샴푸|린스|컨디셔너|트리트먼트|바디워시|'
    r'핸드크림|립밤|립스틱|파운데이션|쿠션|마스크팩|향수|세제|섬유유연제|치약|'
    r'글리세린|부틸렌글라이콜|페녹시에탄올|나이아신아마이드|다이메티콘|카보머|토코페릴아세테이트|소듐하이알루로네이트|'
    # 식품 이름이 들어간 가전·주방용품·반려동물 용품
    r'커피머신|커피메이커|커피포트|에스프레소머신|믹서기|블렌더|착즙기|원액기|그라인더|우유거품기|에어프라이어|전자레인지|'
    r'냉장고|토스터기|전기밥솥|밥솥|보관용기|밀폐용기|텀블러|프라이팬|냄비|햄스터')
# 성분표에서 식품으로 볼 만한 말(알레르기 유발 원료·식품 첨가물)
FOOD_INGREDIENT=re.compile(r'밀가루|소맥분|전분|설탕|백설탕|액상과당|물엿|올리고당|포도당|정제소금|식염|대두유|팜유|'
    r'우유|탈지분유|유청|버터|계란|난백|땅콩|대두|간장|향미증진제|L-글루탐산나트륨|산도조절제|유화제|팽창제|'
    r'돼지고기|닭고기|쇠고기|새우|오징어|고등어|토마토|복숭아|호두|메밀|잣')

def food_evidence(title,ingredients):
    """식품으로 볼 근거를 돌려준다(없으면 None). 화장품 신호가 있으면 식품으로 보지 않는다."""
    text=' '.join([title or '',*[str(i) for i in (ingredients or [])]])
    if NON_FOOD.search(text):return None
    if ingredients and FOOD_INGREDIENT.search(' '.join(str(i) for i in ingredients)):return 'vision_ingredients'
    if FOOD_TITLE.search(title or ''):return 'title_keyword'
    return None

class Worker:
    def __init__(self,client=None,*,worker_id='team-integration',max_concurrency=None,poll_interval=0.5):
        self.http=client or httpx.Client(timeout=20,follow_redirects=False,trust_env=False)
        self.api=os.getenv('API_INTERNAL_URL','http://api:8000').rstrip('/')
        self.vision=os.getenv('VISION_INTERNAL_URL','http://vision-api:8100').rstrip('/')
        self.reco=os.getenv('RECOMMENDATION_INTERNAL_URL','http://recommendation:8000').rstrip('/')
        self.auth={'Authorization':'Bearer '+os.environ['ANALYSIS_WORKER_TOKEN']}
        self.service_auth={'Authorization':'Bearer '+os.environ['WORKSPACE_TOKEN']}
        self.worker_id=worker_id
        self.max_concurrency=max(1,int(max_concurrency or os.getenv('ANALYSIS_WORKER_CONCURRENCY','4')))
        self.poll_interval=float(poll_interval)

    def request(self,method,path,**kwargs):
        r=self.http.request(method,self.api+path,headers=self.auth,**kwargs)
        r.raise_for_status()
        return r.json().get('data')

    def claim_job(self):
        return self.request('POST','/internal/v2/analyses/claim',json={'worker_id':self.worker_id})

    def process_job(self,job):
        if not job:return False
        path='/internal/v2/analyses/'+job['analysis_id'];lease={'lease_token':job['lease_token']}
        try:
            # 캡처 전용 분석은 page_url이 없다. 그때는 클라이언트가 보낸 selected_domain과 OCR 상품명만 사용한다.
            page=job.get('page_url')
            match=None
            if page:
                r=self.http.post(self.reco+'/internal/catalog-context',headers=self.service_auth,
                    json={'page_url':page,'selected_domain':job.get('selected_domain')})
                r.raise_for_status();match=r.json()['match']
            log.info('analysis %s: page_url=%s selected_domain=%s catalog_match=%s',
                     job['analysis_id'],'yes' if page else 'none',job.get('selected_domain'),bool(match))
            kind=job.get('selected_domain') or (match['kind'] if match else None)
            title=match['name'] if match else None
            catalog_ingredients=list(match.get('ingredients') or []) if match else []
            ingredients=[]
            if job.get('image_url'):
                image=self.http.get(self.api+job['image_url'],headers=self.auth|{'X-Worker-Lease':job['lease_token']})
                image.raise_for_status()
                frame=base64.b64encode(image.content).decode()
                sid=job['analysis_id']+'-'+job['lease_token']
                try:
                    r=self.http.post(self.vision+'/api/v1/vision/init',headers=self.service_auth,json={
                        'session_id':sid,'product_name':title,'first_frame_image':frame})
                    r.raise_for_status()
                    r=self.http.post(self.vision+'/api/v1/vision/frame',headers=self.service_auth,json={
                        'session_id':sid,'frame_index':0,'is_last_frame':True,'image':frame})
                    r.raise_for_status()
                    start=time.monotonic();heartbeat=start
                    while time.monotonic()-start<90:
                        if time.monotonic()-heartbeat>15:
                            self.request('POST',path+'/heartbeat',json=lease);heartbeat=time.monotonic()
                        r=self.http.get(self.vision+'/api/v1/vision/status/'+sid,headers=self.service_auth);r.raise_for_status();v=r.json()
                        if v['status']!='processing':
                            title=title or v.get('product_name');ingredients=v.get('ingredients',[]);break
                        time.sleep(self.poll_interval)
                except httpx.HTTPError:
                    if not title:raise
                    # A catalog match can still be ranked; never pretend OCR succeeded.
            if not ingredients and catalog_ingredients:
                ingredients=catalog_ingredients
            if not title:
                self.request('POST',path+'/fail',json=lease|{'code':'OCR_FAILED','retryable':False});return True
            # A generic cosmetics ingredient list must not automatically classify a page as food.
            inferred=not kind
            if not kind:
                # Vision 성분표·상품명으로 판별. 전체 카탈로그를 매번 내려받지 않는다.
                evidence=food_evidence(title,ingredients)
                kind='food' if evidence else 'product'
                log.info('analysis %s: selected_domain 미지정 → 자동 판단 %s (근거=%s, vision 성분 %d개)',
                         job['analysis_id'],kind,evidence or 'default_product',len(ingredients))
            r=self.http.post(self.reco+'/internal/process',headers=self.service_auth,json={
                'query':title[:1000],'selected_domain':kind,
                'ingredients':[str(i)[:500] for i in ingredients[:100]],
                'profile':job.get('profile',{'user_id':'worker'})})
            r.raise_for_status();result=r.json()
            warnings=list(result.get('warnings',[]))
            allergens=(job.get('profile') or {}).get('allergens') or []
            if inferred and kind=='product' and allergens:
                # 식품 근거를 찾지 못해 상품으로 처리했다. 실제 식품이면 알레르기 검사가 빠졌으므로 숨기지 않고 알린다.
                warnings+=[{'type':'allergy','allergen':str(a)[:100],'evidence':'unknown',
                    'message':'식품인지 확인하지 못해 알레르기 성분을 검사하지 않았습니다. 식품이라면 상품 표시를 직접 확인해 주세요.'}
                    for a in allergens[:50]]
            self.request('POST',path+'/complete',json=lease|{
                'selected_domain':kind,'offer_ids':result['offer_ids'],
                'metadata':{'ingredients':[str(i)[:500] for i in ingredients[:100]] if kind=='food' else [],
                    'reasons':result.get('reasons',{}),'ranker':result.get('ranker',''),'warnings':warnings}})
            return True
        except httpx.HTTPStatusError as error:
            status=error.response.status_code
            # Backend 404/409 means the lease is gone (cancelled, expired, already completed): nothing to report.
            # A 404 from Vision (session evicted) or the recommender is a dependency failure and must be reported.
            lease_gone=status in (404,409) and str(error.request.url).startswith(self.api)
            if not lease_gone:
                self.fail(path,lease,retryable=status==429 or status>=500)
            return True
        except httpx.TransportError as error:
            # Timeouts and refused connections are transient; the backend caps retries at 3 attempts.
            log.warning('analysis %s: dependency unreachable (%s)',job['analysis_id'],type(error).__name__)
            self.fail(path,lease,retryable=True);return True
        except Exception as error:
            # Malformed dependency payloads or bugs: fail now instead of holding the lease until it expires.
            log.exception('analysis %s: unexpected worker error (%s)',job['analysis_id'],type(error).__name__)
            self.fail(path,lease,code='RECOMMENDATION_FAILED');return True

    def once(self):
        job=self.claim_job()
        if not job:return False
        return self.process_job(job)

    def drain_concurrent(self,max_workers=None):
        """Claim and execute up to max_workers jobs concurrently until the queue is empty."""
        workers=max(1,int(max_workers or self.max_concurrency))
        completed=0
        active=set()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            while True:
                while len(active)<workers:
                    job=self.claim_job()
                    if not job:
                        break
                    active.add(pool.submit(self.process_job,job))
                if not active:
                    break
                done,active=wait(active,return_when=FIRST_COMPLETED)
                for fut in done:
                    if fut.result():
                        completed+=1
        return completed

    def fail(self,path,lease,*,retryable=False,code='DEPENDENCY_UNAVAILABLE'):
        try:self.request('POST',path+'/fail',json=lease|{'code':code,'retryable':retryable})
        except httpx.HTTPError as error:
            # The lease expires on its own and the backend requeues or fails the job.
            log.warning('could not report analysis failure (%s)',type(error).__name__)

def main():
    logging.basicConfig(level=logging.INFO)
    worker=Worker()
    active=set()
    with ThreadPoolExecutor(max_workers=worker.max_concurrency) as pool:
        while True:
            try:
                claimed=False
                while len(active)<worker.max_concurrency:
                    job=worker.claim_job()
                    if not job:
                        break
                    claimed=True
                    active.add(pool.submit(worker.process_job,job))
                if active:
                    done,active=wait(active,timeout=0.2 if claimed else 1.0,return_when=FIRST_COMPLETED)
                    for fut in done:
                        try:fut.result()
                        except Exception as exc:log.warning('Worker task error (%s)',type(exc).__name__)
                elif not claimed:
                    time.sleep(2)
            except httpx.HTTPError:
                log.warning('Backend unavailable; retrying in 5 seconds');time.sleep(5)

if __name__=='__main__':main()
