"""Durable analysis workflow; actual OCR/recommender workers are external adapters."""
import hashlib
import json
import os
import re
import secrets
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID,uuid4
from fastapi import APIRouter,Depends,Header,Query,Request,Response
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from pydantic import Field,HttpUrl,ValidationError,field_validator
from starlette.datastructures import UploadFile
from .freshness import CARD_FRESHNESS, stale_hours
from .access import access
from .images import MAX_IMAGE,image_path,save_image,remove_image
from .extensions import canonical_allergen
from .members import Strict,bearer,member,row,execute,fail,wrap,subscription_status,throttle,me

router=APIRouter()
worker_bearer=HTTPBearer(auto_error=False)

class AnalysisInput(Strict):
    # 선택: 클라이언트는 기본적으로 캡처 이미지만 보낸다. 페이지 URL은 사용자 열람 기록이므로 필수로 받지 않는다.
    page_url:HttpUrl|None=None
    page_title:str|None=Field(default=None,max_length=500)
    page_session_id:str=Field(min_length=1,max_length=180)
    page_revision:int=Field(ge=0)
    request_key:str=Field(min_length=1,max_length=180)
    selected_domain:Literal['product','food']|None=None
    ai_fallback:bool=False

    @field_validator('page_url')
    @classmethod
    def safe_context(cls,value):
        if value is None:return value
        if value.username or value.password or len(str(value))>2048:raise ValueError('invalid page URL')
        return value

class Claim(Strict):
    worker_id:str=Field(min_length=1,max_length=100)

class Lease(Strict):
    lease_token:UUID

class AllergyWarning(Strict):
    type:Literal['allergy']='allergy'
    allergen:str=Field(max_length=100)
    evidence:Literal['contains','may_contain','unknown']
    message:str=Field(max_length=1000)

class AllergyExclusions(Strict):
    """같은 품목 후보 중 알레르기 성분이 있거나(allergen) 성분을 몰라(unknown_ingredients) 뺀 개수."""
    allergen:int=Field(default=0,ge=0,le=10000)
    unknown_ingredients:int=Field(default=0,ge=0,le=10000)

class ResultMetadata(Strict):
    warnings:list[AllergyWarning]=Field(default_factory=list,max_length=100)
    ingredients:list[str]=Field(default_factory=list,max_length=100)
    reasons:dict[str,str]=Field(default_factory=dict,max_length=50)
    ranker:str=Field(default='',max_length=80)
    exclusions:AllergyExclusions|None=None
    @field_validator('ingredients')
    @classmethod
    def bounded_ingredients(cls,values):
        if any(len(v)>500 for v in values):raise ValueError('ingredient too long')
        return values
    @field_validator('reasons')
    @classmethod
    def bounded_reasons(cls,values):
        if any(len(k)>36 or len(v)>1000 for k,v in values.items()):raise ValueError('reason too long')
        return values

class Completion(Lease):
    selected_domain:Literal['product','food']
    offer_ids:list[UUID]=Field(default_factory=list,max_length=50)
    metadata:ResultMetadata=Field(default_factory=ResultMetadata)

class Failure(Lease):
    code:Literal['OCR_FAILED','RECOMMENDATION_FAILED','INPUT_INVALID','DEPENDENCY_UNAVAILABLE','CATALOG_NO_MATCH']
    retryable:bool=False

class HistoryDeletion(Strict):
    scope:Literal['history']


GUEST_KEY=re.compile(r'^[A-Za-z0-9_-]{32,128}$')


async def analysis_owner(req:Request,auth:HTTPAuthorizationCredentials|None=Depends(bearer)):
    """(owner_id, guest). 로그인하면 회원, 아니면 기기별 무작위 키(X-Guest-Key)로 비회원 분석을 허용한다.
    잘못된 로그인 토큰은 비회원으로 바꾸지 않고 401로 알린다(클라이언트가 로그아웃 처리).
    비회원 owner_id는 키에서 만든 값이라 키를 모르면 다른 기기의 분석을 볼 수 없다."""
    if auth:
        return await member(req,auth),False
    key=req.headers.get('x-guest-key','')
    if not GUEST_KEY.match(key):fail(401,'AUTH_REQUIRED')
    return UUID(bytes=hashlib.sha256(b'kkulpick-guest:'+key.encode()).digest()[:16],version=4),True


@asynccontextmanager
async def owner_access(req,uid,guest):
    """회원은 기존 access(세션 잠금·탈퇴 확인), 비회원은 확인할 회원 정보가 없다."""
    if guest:
        yield None
        return
    async with access(req,uid) as m:
        yield m


def worker(auth:HTTPAuthorizationCredentials|None=Depends(worker_bearer)):
    expected=os.getenv('ANALYSIS_WORKER_TOKEN','')
    if len(expected)<32 or not auth or not secrets.compare_digest(expected.encode(),auth.credentials.encode()):
        fail(401,'WORKER_AUTH_REQUIRED')


async def expire(c, *, owner_id=None, analysis_id=None):
    # Public requests only maintain the member/job they access. Workers and the
    # periodic maintenance process still use bounded global batches.
    scope=''
    params={}
    if owner_id is not None:
        scope+=' AND owner_id=:expiry_owner'
        params['expiry_owner']=owner_id
    if analysis_id is not None:
        scope+=' AND analysis_id=:expiry_id'
        params['expiry_id']=analysis_id
    await execute(c,f"""UPDATE app.analyses SET state='failed',error_code='ANALYSIS_TIMEOUT',updated_at=now()
        WHERE analysis_id IN (SELECT analysis_id FROM app.analyses WHERE state IN ('queued','running') AND deadline<=now(){scope} LIMIT 500 FOR UPDATE SKIP LOCKED)""",**params)
    await execute(c,f"""UPDATE app.analyses SET state=CASE WHEN attempt<3 THEN 'queued' ELSE 'failed' END,
        error_code=CASE WHEN attempt<3 THEN NULL ELSE 'WORKER_RETRIES_EXHAUSTED' END,
        lease_token=NULL,worker_id=NULL,lease_until=NULL,updated_at=now()
        WHERE analysis_id IN (SELECT analysis_id FROM app.analyses WHERE state='running' AND lease_until<=now()
        AND deadline>now(){scope} LIMIT 500 FOR UPDATE SKIP LOCKED)""",**params)


async def input_data(req):
    image=None
    content=req.headers.get('content-type','').lower()
    if content.startswith('multipart/form-data'):
        async with req.form(max_files=1,max_fields=8,max_part_size=4096) as form:
            if len(form.multi_items())!=len(form):fail(422,'DUPLICATE_FIELDS')
            raw={k:v for k,v in form.items() if k!='image'}
            upload=form.get('image')
            if upload is not None:
                if not isinstance(upload,UploadFile):fail(422,'INVALID_INPUT')
                image=await upload.read(MAX_IMAGE+1)
                if len(image)>MAX_IMAGE:fail(413,'IMAGE_TOO_LARGE')
    elif content.startswith('application/json'):
        try:raw=await req.json()
        except (ValueError,UnicodeDecodeError):fail(422,'INVALID_INPUT')
    else:fail(415,'CONTENT_TYPE_UNSUPPORTED')
    try:return AnalysisInput.model_validate(raw),image
    except ValidationError:fail(422,'INVALID_INPUT')


@router.post('/analyses',status_code=202)
async def create_analysis(req:Request,response:Response,owner=Depends(analysis_owner)):
    uid,guest=owner
    await throttle(req,'analysis')
    # 비회원은 기기 키를 바꾸면 '진행 중 3건' 한도를 새로 받으므로 접속 주소당 분당 접수 수를 따로 제한한다(#84).
    if guest:await throttle(req,'analysis-guest',int(os.getenv('GUEST_ANALYSES_PER_MINUTE','6')))
    data,image=await input_data(req)
    # 분석 근거가 하나도 없으면 접수하지 않는다(캡처 이미지 또는 페이지 URL 중 하나 필요).
    if image is None and data.page_url is None:fail(422,'INPUT_REQUIRED')
    image_hash=hashlib.sha256(image).hexdigest() if image is not None else None
    digest=hashlib.sha256(json.dumps(data.model_dump(mode='json')|{'image_hash':image_hash},sort_keys=True).encode()).hexdigest()
    image_id=None
    try:
        async with owner_access(req,uid,guest):
            async with req.app.state.engine.begin() as c:
                # Serializes per-member quota and idempotency checks without extra table.
                await execute(c,"SELECT pg_advisory_xact_lock(hashtextextended(:k,0))",k='analysis:'+str(uid))
                await expire(c,owner_id=uid)
                old=await row(c,'SELECT * FROM app.analyses WHERE owner_id=:u AND guest=:g AND request_key=:k',u=uid,g=guest,k=data.request_key)
                if old:
                    if old['request_hash']!=digest:fail(409,'REQUEST_KEY_CONFLICT')
                    response.status_code=200
                    return wrap({'analysis_id':old['analysis_id'],'state':old['state'],'status_url':'/analyses/'+str(old['analysis_id'])},req)
                pending=await row(c,"SELECT count(*) AS n FROM app.analyses WHERE owner_id=:u AND state IN ('queued','running')",u=uid)
                if pending['n']>=3:fail(429,'ANALYSIS_LIMIT')
                if image is not None:image_id=save_image(image)
                # result_metadata는 NOT NULL(기본 {}): 상품명이 없을 때 NULL을 넣으면 접수 전체가 409로 실패한다(#88).
                meta_dict={}
                if data.page_title and data.page_title.strip():meta_dict['page_title']=data.page_title.strip()
                if data.ai_fallback:meta_dict['ai_fallback']=True
                init_meta=json.dumps(meta_dict)
                result=await row(c,'''INSERT INTO app.analyses(owner_id,guest,request_key,request_hash,page_url,page_session_id,page_revision,
                    selected_domain,image_id,image_hash,result_metadata)
                    VALUES(:u,:guest,:k,:h,:url,:session,:revision,:kind,:image,:ih,CAST(:meta AS jsonb))
                    RETURNING analysis_id,state''',u=uid,guest=guest,k=data.request_key,h=digest,url=str(data.page_url) if data.page_url else None,session=data.page_session_id,
                    revision=data.page_revision,kind=data.selected_domain,image=image_id,ih=image_hash,meta=init_meta)
    except BaseException:
        remove_image(image_id)
        raise
    return wrap(dict(result)|{'status_url':'/analyses/'+str(result['analysis_id'])},req)


async def offer_cards(c,ids):
    if not ids:
        return {}
    rows=(await execute(c,f'''SELECT o.offer_id,i.name,o.price::text,o.currency,o.price_observed_at AS observed_at,
        o.availability,o.current_url AS url,o.kind AS image_kind,{CARD_FRESHNESS},
        i.brand,i.image_url,i.category
        FROM app.offers o JOIN app.catalog_items i USING(item_id)
        WHERE o.offer_id=ANY(CAST(:ids AS uuid[])) AND o.availability='available' ''',
        ids=list(set(ids)),stale_hours=stale_hours())).mappings().all()
    return {x['offer_id']:x for x in rows}


# AI 추천 공개 개수. 무료 회원 3개, 프리미엄 5개. 무료 회원에게는 나머지를 잠긴 개수로만 알린다.
FREE_AI_ITEMS=3
PREMIUM_AI_ITEMS=5
# 중고·해외 추천 구역 최대 개수(설정 화면 안내 '중고 상품을 3개까지')
USED_ITEMS=3
OVERSEAS_ITEMS=3


def card_subtitle(card):
    """해외 판매처(원화가 아닌 가격)는 카드에 표시한다. 해외 상품 포함 설정이 결과에 보이도록."""
    return f"해외 판매처 · {card['currency']}" if card.get('currency') and card['currency']!='KRW' else ''


# 캡처 없이 페이지 주소만 왔는데 카탈로그에 없는 상품(#26): 다시 시도해도 같으므로 재시도 불가로 안내한다.
ERROR_MESSAGES={'CATALOG_NO_MATCH':'아직 수집되지 않은 상품이에요. 화면 캡처와 함께 다시 분석해 주세요.'}


def warnings_for_domain(warnings,domain):
    """식품 결과에는 식품 알레르기만, 일반 상품 결과에는 식품이 아닌(피부 등) 알레르기만 남긴다.
    예외(#83): 일반 상품 결과라도 식품 알레르기의 '확인 못 함'(evidence=unknown) 경고는 남긴다. 작업자는 식품인지
    확인하지 못해 상품으로 처리했을 때만 이 경고를 붙이므로, 숨기면 실제 식품에서 알레르기 안내가 사라진다.
    종류를 모르면 경고를 내보내지 않는다. 클라이언트(allergens.ts warningsForDomain)도 같은 규칙으로 거른다."""
    if domain not in ('food','product'):return []
    def keep(w):
        food=canonical_allergen(str(w.get('allergen',''))) is not None
        return food if domain=='food' else (not food or w.get('evidence')=='unknown')
    return [w for w in warnings if keep(w)]


def is_overseas(card):
    return bool(card.get('currency')) and card['currency']!='KRW'


async def public_result(c,r,premium,by_id=None,include_used=False,include_overseas=False,allow_overseas=True):
    """AI 추천(국내 새 상품)·해외 추천·중고 추천을 나눈다. 해외·중고는 AI 공개 개수에 넣지 않고 각자 구역에 따로 보여준다.
    include_used / include_overseas: 회원이 설정을 켰는지. 켰는데 고른 상품이 없으면 빈 구역('없음' 안내)을 보여준다.
    allow_overseas=False(비회원): 해외 상품은 어느 구역에도 넣지 않는다(예전에 해외 포함으로 분석된 결과 포함)."""
    metadata=r.get('result_metadata') or {}
    ingredients=metadata.get('ingredients',[])
    cards=[]
    if r['state']=='completed' and r['offer_ids']:
        if by_id is None:
            by_id=await offer_cards(c,r['offer_ids'])
        cards=[dict(by_id[ident])|{'subtitle':card_subtitle(by_id[ident]),'reason':metadata.get('reasons',{}).get(str(ident),'분석 작업자가 선택한 상품'),'affiliate':False}
               for ident in r['offer_ids'] if ident in by_id and by_id[ident]['image_kind']==r['selected_domain']]
    used=[x for x in cards if x.get('condition')=='used'][:USED_ITEMS]
    overseas=[x for x in cards if x.get('condition')!='used' and is_overseas(x)][:OVERSEAS_ITEMS] if allow_overseas else []
    cards=[x for x in cards if x.get('condition')!='used' and not is_overseas(x)][:PREMIUM_AI_ITEMS]
    cap=PREMIUM_AI_ITEMS if premium else FREE_AI_ITEMS
    result_kind=('recommendation' if cards or used or overseas else 'empty') if r['state']=='completed' else None
    # 추천이 비었고 같은 품목 후보가 알레르기로 빠졌을 때만: 화면이 '비슷한 상품 없음' 대신 이유를 안내한다.
    excl=metadata.get('exclusions') or {}
    allergy_excluded=(excl if result_kind=='empty' and r['selected_domain']=='food'
                      and (excl.get('allergen',0) or excl.get('unknown_ingredients',0)) else None)
    state='ready' if r['state']=='completed' else 'loading' if r['state'] in {'queued','running'} else 'failed'
    extra=lambda kind,items:{'kind':kind,'state':state,'items':items,'locked_count':0,'lock_reason':None,'footnote':None}
    used_section=([extra('overseas',overseas)] if overseas or include_overseas else [])+(
        [extra('used',used)] if (used or include_used) and r['selected_domain']!='food' else [])
    return {'analysis_id':r['analysis_id'],'state':r['state'],'result_kind':result_kind,
        'allergy_excluded':allergy_excluded,
        'ingredient_status':('partial' if ingredients else 'not_found') if r['selected_domain']=='food' else 'not_applicable',
        'page_session_id':r['page_session_id'],'page_revision':r['page_revision'],'selected_domain':r['selected_domain'],
        'source_summary':{'vision':'success' if ingredients else 'empty'},'warnings':warnings_for_domain(metadata.get('warnings',[]),r['selected_domain']), 'premium':premium,'applied_filter':None,
        'sections':[{'kind':'ai','state':state,
                     'items':cards[:cap],'locked_count':max(0,len(cards)-cap),
                     'lock_reason':'premium_required' if len(cards)>cap else None,'footnote':('OCR 추출 성분은 상품 표시와 대조해 주세요. 안전을 보증하지 않습니다.' if ingredients else '성분을 확인하지 못했습니다. 상품 표시를 직접 확인해 주세요.') if r['selected_domain']=='food' else None}]+used_section,
        'error':{'code':r['error_code'],'message':ERROR_MESSAGES.get(r['error_code'],'분석을 완료하지 못했습니다.'),
                 'retryable':r['error_code'] not in {'INPUT_INVALID','CATALOG_NO_MATCH'}} if r['error_code'] else None}


@router.get('/analyses/{analysis_id}')
async def get_analysis(analysis_id:UUID,req:Request,owner=Depends(analysis_owner)):
    uid,guest=owner
    async with owner_access(req,uid,guest) as m:
        premium=False if guest else (await subscription_status(m,uid))['active']
        settings=None if guest else await row(m,'SELECT include_used,include_overseas FROM app.members WHERE user_id=:u',u=uid)
        include_used=bool(settings and settings['include_used'])
        include_overseas=bool(settings and settings['include_overseas'])
        async with req.app.state.engine.begin() as c:
            await expire(c,owner_id=uid,analysis_id=analysis_id)
            r=await row(c,'SELECT * FROM app.analyses WHERE analysis_id=:id AND owner_id=:u AND guest=:g',id=analysis_id,u=uid,g=guest)
            if not r:fail(404,'ANALYSIS_NOT_FOUND')
            result=await public_result(c,r,premium,include_used=include_used,include_overseas=include_overseas,allow_overseas=not guest)
    return wrap(result,req)


@router.post('/analyses/{analysis_id}/cancel')
async def cancel(analysis_id:UUID,req:Request,owner=Depends(analysis_owner)):
    uid,guest=owner
    async with owner_access(req,uid,guest):
        async with req.app.state.engine.begin() as c:
            r=await row(c,'SELECT * FROM app.analyses WHERE analysis_id=:id AND owner_id=:u AND guest=:g FOR UPDATE',id=analysis_id,u=uid,g=guest)
            if not r:fail(404,'ANALYSIS_NOT_FOUND')
            if r['state'] in {'queued','running'}:
                await execute(c,"UPDATE app.analyses SET state='cancelled',lease_token=NULL,updated_at=now() WHERE analysis_id=:id",id=analysis_id)
                state='cancelled'
            elif r['state']=='cancelled':state='cancelled'
            else:fail(409,'ANALYSIS_ALREADY_FINISHED')
        remove_image(r['image_id'])
    return wrap({'analysis_id':analysis_id,'state':state},req)


@router.get('/v2/me/analyses')
async def history(req:Request,limit:int=Query(20,ge=1,le=100),uid=Depends(member)):
    async with access(req,uid) as m:
        premium=(await subscription_status(m,uid))['active']
        async with req.app.state.engine.connect() as c:
            rows=(await execute(c,"SELECT * FROM app.analyses WHERE owner_id=:u AND state='completed' ORDER BY created_at DESC,analysis_id DESC LIMIT :n",u=uid,n=limit)).mappings().all()
            by_id=await offer_cards(c,[ident for r in rows for ident in r['offer_ids']])
            items=[]
            for r in rows:
                result=await public_result(c,r,premium,by_id)
                if result['sections'][0]['items']:
                    items.append({'analysis_id':r['analysis_id'],'created_at':r['created_at'],'card':result['sections'][0]['items'][0]})
    return wrap(items,req)


@router.post('/v2/me/data-deletions')
async def delete_history(data:HistoryDeletion,req:Request,uid=Depends(member)):
    async with access(req,uid):
        async with req.app.state.engine.begin() as c:
            await execute(c,"SELECT pg_advisory_xact_lock(hashtextextended(:k,0))",k='analysis:'+str(uid))
            rows=(await execute(c,'DELETE FROM app.analyses WHERE owner_id=:u RETURNING image_id',u=uid)).mappings().all()
        for r in rows:remove_image(r['image_id'])
    return wrap({'request_id':uuid4(),'state':'completed'},req)


@router.post('/internal/v2/analyses/claim',dependencies=[Depends(worker)])
async def claim(data:Claim,req:Request):
    async with req.app.state.engine.begin() as c:
        await expire(c)
        # 재시도는 바로 다시 가져가지 않는다(#25): 5초, 20초 … 지수 대기(마감 시각 안에서만). 첫 시도(attempt=0)는 즉시.
        r=await row(c,"""SELECT * FROM app.analyses WHERE state='queued' AND deadline>now() AND attempt<3
            AND (attempt=0 OR updated_at<=now()-make_interval(secs=>CAST(:base AS float)*power(4,attempt-1)))
            ORDER BY created_at,analysis_id FOR UPDATE SKIP LOCKED LIMIT 1""",base=float(os.getenv('ANALYSIS_RETRY_BASE_SECONDS','5')))
        if not r:return wrap(None,req)
        lease=uuid4()
        result=await row(c,"""UPDATE app.analyses SET state='running',attempt=attempt+1,worker_id=:w,lease_token=:lease,
            lease_until=least(deadline,now()+interval '2 minutes'),updated_at=now() WHERE analysis_id=:id
            RETURNING analysis_id,owner_id,guest,page_url,page_session_id,selected_domain,lease_token,lease_until,attempt,image_id,result_metadata""",w=data.worker_id,lease=lease,id=r['analysis_id'])
    meta_obj=result.get('result_metadata') if isinstance(result.get('result_metadata'),dict) else {}
    page_title=meta_obj.get('page_title')
    ai_fallback=bool(meta_obj.get('ai_fallback'))
    # Release the catalog connection before taking a member connection: public
    # routes use member -> catalog order, so nesting here could exhaust both pools.
    if result['guest']:
        # 비회원: 회원 DB를 조회하지 않고 기본 설정으로 추천한다(알레르기 없음, 중고·해외 제외, 무료 개수).
        # 설정 화면의 중고·해외 스위치가 비회원에게 꺼짐으로 보이므로 그와 같게 둔다.
        return wrap({k:v for k,v in result.items() if k not in {'image_id','owner_id','guest','result_metadata'}}|
                    {'page_title':page_title,'ai_fallback':ai_fallback,'profile':{'user_id':'guest','allergens':[],'include_used':False,'include_overseas':False,
                        'avoid_ingredients':[],'preferences':''},
                     'image_url':'/internal/v2/analyses/'+str(result['analysis_id'])+'/image' if result['image_id'] else None},req)
    async with req.app.state.member_engine.connect() as m:
        owner=await row(m,'SELECT user_id FROM app.members WHERE user_id=:u AND deleted_at IS NULL',u=result['owner_id'])
        profile=(await me(m,result['owner_id'])) if owner else None
    if not owner:
        async with req.app.state.engine.begin() as c:
            await execute(c,"UPDATE app.analyses SET state='cancelled',lease_token=NULL,updated_at=now() WHERE analysis_id=:id AND lease_token=:lease",id=result['analysis_id'],lease=lease)
        return wrap(None,req)
    return wrap({k:v for k,v in result.items() if k not in {'image_id','owner_id','guest','result_metadata'}}|
                {'page_title':page_title,'ai_fallback':ai_fallback,'profile':{'user_id':str(result['owner_id']),'allergens':profile['profile']['allergies'],
                    'include_used':profile['profile']['include_used'],
                    'include_overseas':profile['profile']['include_overseas'],
                    'avoid_ingredients':profile['profile']['ingredient_filter']['avoid'] if profile['premium'] else [],
                    'preferences':' '.join(profile['profile']['ingredient_filter']['prefer']) if profile['premium'] else ''},
                 'image_url':'/internal/v2/analyses/'+str(result['analysis_id'])+'/image' if result['image_id'] else None},req)


async def leased(c,ident,token):
    r=await row(c,'''SELECT *,lease_until>now() AND deadline>now() AS lease_valid FROM app.analyses
        WHERE analysis_id=:id FOR UPDATE''',id=ident)
    if not r:fail(404,'ANALYSIS_NOT_FOUND')
    if r['state']!='running' or r['lease_token']!=token or not r['lease_valid']:
        fail(409,'WORKER_LEASE_CONFLICT')
    return r


@router.post('/internal/v2/analyses/{analysis_id}/heartbeat',dependencies=[Depends(worker)])
async def heartbeat(analysis_id:UUID,data:Lease,req:Request):
    async with req.app.state.engine.begin() as c:
        await leased(c,analysis_id,data.lease_token)
        r=await row(c,"UPDATE app.analyses SET lease_until=least(deadline,now()+interval '2 minutes') WHERE analysis_id=:id RETURNING lease_until",id=analysis_id)
    return wrap(dict(r),req)


@router.get('/internal/v2/analyses/{analysis_id}/image',dependencies=[Depends(worker)])
async def read_image(analysis_id:UUID,req:Request,lease_token:UUID=Header(alias="X-Worker-Lease")):
    async with req.app.state.engine.begin() as c:
        r=await leased(c,analysis_id,lease_token)
        if not r['image_id']:fail(404,'IMAGE_NOT_FOUND')
        path=image_path(r['image_id'])
        try:content=path.read_bytes()
        except FileNotFoundError:fail(410,'IMAGE_EXPIRED')
    return Response(content,media_type='application/octet-stream',headers={'Cache-Control':'no-store'})


@router.post('/internal/v2/analyses/{analysis_id}/complete',dependencies=[Depends(worker)])
async def complete(analysis_id:UUID,data:Completion,req:Request):
    if len(set(data.offer_ids))!=len(data.offer_ids):fail(422,'DUPLICATE_OFFERS')
    async with req.app.state.engine.begin() as c:
        old=await row(c,'SELECT * FROM app.analyses WHERE analysis_id=:id FOR UPDATE',id=analysis_id)
        if not old:fail(404,'ANALYSIS_NOT_FOUND')
        if old['state']=='completed' and old['lease_token']==data.lease_token:
            if old['selected_domain']!=data.selected_domain or list(old['offer_ids'])!=data.offer_ids or (old.get('result_metadata') or {})!=data.metadata.model_dump():fail(409,'RESULT_CONFLICT')
            return wrap({'analysis_id':analysis_id,'state':'completed'},req)
        r=await leased(c,analysis_id,data.lease_token)
        if r['selected_domain'] and r['selected_domain']!=data.selected_domain:fail(409,'DOMAIN_CONFLICT')
        count=await row(c,"SELECT count(*) AS n FROM app.offers WHERE offer_id=ANY(CAST(:ids AS uuid[])) AND kind=:k AND availability='available'",ids=data.offer_ids,k=data.selected_domain)
        if count['n']!=len(data.offer_ids):fail(422,'INVALID_RESULT_OFFERS')
        await execute(c,"""UPDATE app.analyses SET state='completed',selected_domain=:k,offer_ids=CAST(:ids AS uuid[]),
            result_metadata=CAST(:metadata AS jsonb),error_code=NULL,updated_at=now() WHERE analysis_id=:id""",id=analysis_id,k=data.selected_domain,ids=data.offer_ids,metadata=data.metadata.model_dump_json())
    remove_image(r['image_id'])
    return wrap({'analysis_id':analysis_id,'state':'completed'},req)


@router.post('/internal/v2/analyses/{analysis_id}/fail',dependencies=[Depends(worker)])
async def failed(analysis_id:UUID,data:Failure,req:Request):
    async with req.app.state.engine.begin() as c:
        r=await leased(c,analysis_id,data.lease_token)
        state='queued' if data.retryable and r['attempt']<3 else 'failed'
        await execute(c,'UPDATE app.analyses SET state=:s,error_code=:e,lease_token=NULL,lease_until=NULL,worker_id=NULL,updated_at=now() WHERE analysis_id=:id',
                      id=analysis_id,s=state,e=None if state=='queued' else data.code)
    if state=='failed':remove_image(r['image_id'])
    return wrap({'analysis_id':analysis_id,'state':state},req)
