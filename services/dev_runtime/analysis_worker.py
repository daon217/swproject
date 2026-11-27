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
import httpx

log=logging.getLogger('analysis-worker')

# 식품 판별 신호. Vision이 원재료명·영양정보 아래에서 성분을 읽었거나, 상품명이 식품일 때 food로 본다.
# 다른 말에 섞이기 쉬운 한 글자(빵·떡·껌·햄·쌀)는 쓰지 않는다. 틀리면 일반 상품에 식품 알레르기가 뜬다.
# 카탈로그에 식품이 없어도 판별되도록 카탈로그 겹침보다 먼저 확인한다.
FOOD_TITLE=re.compile(r'라면|과자|스낵|쿠키|비스킷|초콜릿|초코|젤리|사탕|캔디|아이스크림|케이크|만두|국수|파스타|우동|냉면|짜장|짬뽕|'
    r'즉석밥|햇반|도시락|밀키트|반찬|김치|소스|양념|간장|된장|고추장|케첩|마요네즈|드레싱|식용유|참기름|'
    r'우유|두유|요거트|요구르트|치즈|버터|분유|커피|음료|주스|탄산|생수|녹차|홍차|'
    r'견과|땅콩|아몬드|호두|캐슈|시리얼|그래놀라|오트밀|소시지|베이컨|참치|어묵|두부|계란|달걀|'
    r'정육|한우|돼지고기|닭가슴살|닭고기|소고기|현미|잡곡|메밀|보리|귀리|오트|대두|과일|사과|딸기|복숭아|오징어|새우|멸치|'
    r'찌개|갈비탕|곰탕|설렁탕|삼계탕|감자탕|육개장|국밥|떡볶이|돈까스|돈가스|치킨까스|생선까스|볶음밥|잼|스프레드|땅콩버터|피넛버터|'
    r'식품|간식|과자류|영양제|홍삼|단백질\s*쉐이크|프로틴')
# 화장품·생활용품 성분표는 식품 성분표로 보지 않는다(전성분에 '크림'·'우유' 같은 말이 섞여도 식품 아님).
NON_FOOD=re.compile(r'화장품|스킨|토너|로션|에센스|세럼|앰플|선크림|썬크림|클렌징|폼클렌저|샴푸|린스|컨디셔너|트리트먼트|바디워시|'
    r'핸드크림|립밤|립스틱|파운데이션|쿠션|마스크팩|향수|세제|섬유유연제|치약|'
    r'글리세린|부틸렌글라이콜|페녹시에탄올|나이아신아마이드|다이메티콘|카보머|토코페릴아세테이트|소듐하이알루로네이트|'
    # 식품 이름이 들어간 가전·주방용품·반려동물 용품('에어프라이어용 생선까스'처럼 '…용' 식품은 제외)
    r'커피머신|커피메이커|커피포트|에스프레소머신|믹서기|블렌더|착즙기|원액기|그라인더|우유거품기|에어프라이어(?!용)|전자레인지(?!용)|'
    r'냉장고|토스터기|전기밥솥|밥솥|보관용기|밀폐용기|텀블러|프라이팬|냄비|햄스터|'
    # '오픈소스'의 '소스'처럼 식품 단어가 섞인 말, 전자·패션 상품(확장·모바일 pageProduct와 같은 기준)
    r'오픈소스|소스코드|리소스|아두이노|라즈베리|개발보드|노트북|컴퓨터|그래픽카드|메인보드|프로세서|CPU|SSD|HDD|키보드|마우스|모니터|프린터|'
    r'케이블|충전기|이어폰|헤드폰|스피커|스마트폰|태블릿|패딩|자켓|재킷|티셔츠|바지|신발|운동화|가방|의류')
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
        # OCR은 한 번에 하나씩 처리하므로 동시 작업을 너무 많이 잡으면 뒤쪽 작업이 Vision 대기 시간을 넘긴다(#18).
        self.max_concurrency=max(1,int(max_concurrency or os.getenv('ANALYSIS_WORKER_CONCURRENCY','2')))
        self.vision_wait=float(os.getenv('ANALYSIS_VISION_WAIT_SECONDS','150'))
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
            title=(match['name'] if match else None) or job.get('page_title')
            catalog_ingredients=list(match.get('ingredients') or []) if match else []
            declared=[str(a)[:64] for a in (match.get('allergens_declared') or [])[:32]] if match else []
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
                    while time.monotonic()-start<self.vision_wait:
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
                # 캡처가 없으면 OCR 실패가 아니라 카탈로그에 없는 상품이다(#26).
                code='OCR_FAILED' if job.get('image_url') else 'CATALOG_NO_MATCH'
                self.request('POST',path+'/fail',json=lease|{'code':code,'retryable':False});return True
            # A generic cosmetics ingredient list must not automatically classify a page as food.
            if not kind:
                # Vision 성분표·상품명으로 판별. 전체 카탈로그를 매번 내려받지 않는다.
                evidence=food_evidence(title,ingredients)
                kind='food' if evidence else 'product'
                log.info('analysis %s: selected_domain 미지정 → 자동 판단 %s (근거=%s, vision 성분 %d개)',
                         job['analysis_id'],kind,evidence or 'default_product',len(ingredients))
            query_text=title
            if page:
                from urllib.parse import parse_qs, urlsplit
                qs=parse_qs(urlsplit(page).query)
                for qk in ('q','query','keyword','searchKeyword'):
                    qv=' '.join(qs.get(qk,())).strip()
                    if qv and qv not in query_text:
                        query_text=f'{query_text} {qv}'
                        break
            r=self.http.post(self.reco+'/internal/process',headers=self.service_auth,json={
                'query':query_text[:1000],'selected_domain':kind,
                'ingredients':[str(i)[:500] for i in ingredients[:100]],
                **({'allergens_declared':declared} if declared else {}),
                **({'ai_fallback':True} if job.get('ai_fallback') else {}),
                'profile':job.get('profile',{'user_id':'worker'})})
            r.raise_for_status();result=r.json()
            warnings=list(result.get('warnings',[]))
            # 지금 보고 있는 그 판매처 상품은 추천하지 않는다(같은 상품의 다른 판매처는 가격 비교로 남긴다).
            own=match.get('offer_id') if match else None
            offer_ids=[o for o in result['offer_ids'] if o!=own]
            self.request('POST',path+'/complete',json=lease|{
                'selected_domain':kind,'offer_ids':offer_ids,
                'metadata':{'ingredients':[str(i)[:500] for i in ingredients[:100]] if kind=='food' else [],
                    'reasons':result.get('reasons',{}),'ranker':result.get('ranker',''),'warnings':warnings,
                    **({'exclusions':result['exclusions']} if kind=='food' and result.get('exclusions') else {})}})
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
