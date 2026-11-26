"""Authenticated, bounded HTTP adapter for the team's recommendation pipeline."""
import os
import secrets
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, urlunsplit
try:
    import psycopg
    PG_ERRORS = (psycopg.Error,)
except ImportError:  # pragma: no cover - per-project unit CI runs without psycopg
    psycopg = None
    PG_ERRORS = ()
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .adapters.postgres import PgCatalog, PgVectorIndex
from . import embedding_config as config
from .contracts import UserProfile, ContractError
from .pipeline import Recommender
from .rankers import make_ranker
from .allergens import ALLERGENS,detect,normalize_code


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=1000)
    selected_domain: Literal['product','food']
    ingredients: list[str] = Field(default_factory=list,max_length=100)
    allergens_declared: list[str] = Field(default_factory=list,max_length=32)
    profile: dict = Field(default_factory=lambda: {'user_id':'worker'})


def authorize(authorization):
    token=os.getenv('WORKSPACE_TOKEN','')
    if len(token)<32 or not secrets.compare_digest(authorization.encode(), ('Bearer '+token).encode()):
        raise HTTPException(401,'SERVICE_AUTH_REQUIRED')


class CatalogContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    page_url: str = Field(min_length=1, max_length=4096)
    selected_domain: Literal['product', 'food'] | None = None


@asynccontextmanager
async def lifespan(app):
    # Load weights once, before accepting traffic. Never substitute hash on model errors.
    config.embedder()
    yield


app=FastAPI(title='꿀픽 추천 연결', lifespan=lifespan)

@app.get('/health')
def health():
    try:
        with config.connect() as conn:
            for kind in ('product', 'food'):
                config.validate(conn, kind)
        config.embedder()
    except PG_ERRORS + (ValueError, KeyError, OSError) as error:
        raise HTTPException(503, 'EMBEDDING_DEPENDENCY_UNAVAILABLE') from error
    return {'status':'ok','service':'recommendation','implementation':'team-pipeline',
            'business_ready':os.getenv('RECO_EMBEDDER','st') != 'hash',
            'store':'pg','embedder':os.getenv('RECO_EMBEDDER','st'),
            'ranker':os.getenv('RECO_RANKER','rule')}

@app.post('/internal/dev/probe')
def probe(body:dict,authorization:str=Header(default='')):
    authorize(authorization)
    return body|health()


def _normalized_url_candidates(raw_url: str) -> tuple[list[str], str, str]:
    """Return index-friendly normalized URL candidates (http/https, lowercase host, no #fragment)
    plus (host, path_and_query) for case-insensitive host fallback."""
    stripped = raw_url.strip()
    u = urlsplit(stripped)
    base_no_frag = urlunsplit((u.scheme, u.netloc, u.path, u.query, ''))
    host = (u.hostname or '').lower()
    if not host:
        return [stripped, base_no_frag], '', ''
    try:
        port = u.port
    except ValueError:
        port = None
    netloc_default = f'{host}:{port}' if port and port not in (80, 443) else host
    path_variants = [u.path] if u.path else ['', '/']
    if u.path and u.path != '/' and u.path.endswith('/'):
        path_variants = [u.path, u.path.rstrip('/')]
    candidates = []
    for candidate in (
        stripped,
        base_no_frag,
        *[
            urlunsplit((scheme, netloc, p, u.query, ''))
            for scheme in ('https', 'http')
            for netloc in ({netloc_default, f'{host}:{port}'} if port else {netloc_default})
            for p in path_variants
        ],
    ):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    suffix = f'{u.path}?{u.query}' if u.query else u.path
    return candidates, host, suffix


def _suffix_variants(suffix: str) -> list[str]:
    """Path/query forms treated as the same page: empty path == '/', optional trailing slash."""
    path, sep, query = suffix.partition('?')
    paths = {path or '/', '' if path in ('', '/') else path}
    if path not in ('', '/'):
        paths.add(path.rstrip('/') if path.endswith('/') else path)
    return sorted({p + sep + query for p in paths})


@app.post('/internal/catalog-context')
def catalog_context(body:CatalogContext,authorization:str=Header(default='')):
    authorize(authorization)
    candidates, host, suffix = _normalized_url_candidates(body.page_url)
    try:
        with config.connect() as conn:
            row=conn.execute('''SELECT i.name,o.kind,f.ingredients,f.ingredients_raw,f.allergens_declared,o.offer_id::text
                FROM app.offers o
                JOIN app.catalog_items i USING(item_id)
                LEFT JOIN app.foods f USING(item_id)
                WHERE o.current_url = ANY(%s) AND (%s::text IS NULL OR o.kind=%s)
                ORDER BY (o.current_url=%s) DESC,(o.availability='available') DESC,o.offer_id LIMIT 1''',
                (candidates,body.selected_domain,body.selected_domain,body.page_url)).fetchone()
            if not row and host:
                # Host-case fallback. The host expression matches the offers_url_host index (0010)
                # and the exact path/query comparison runs in SQL, so a busy host cannot push the
                # matching offer past an arbitrary row limit.
                row=conn.execute('''SELECT i.name,o.kind,f.ingredients,f.ingredients_raw,f.allergens_declared,o.offer_id::text
                    FROM app.offers o
                    JOIN app.catalog_items i USING(item_id)
                    LEFT JOIN app.foods f USING(item_id)
                    WHERE lower(substring(o.current_url from '^[a-zA-Z]+://([^/:?#]+)')) = %s
                      AND coalesce(substring(o.current_url from '^[a-zA-Z]+://[^/?#]+([^#]*)'), '') = ANY(%s)
                      AND (%s::text IS NULL OR o.kind=%s)
                    ORDER BY (o.availability='available') DESC,o.offer_id LIMIT 1''',
                    (host,_suffix_variants(suffix),body.selected_domain,body.selected_domain)).fetchone()
        if not row:
            return {'match':None}
        from .allergens import split_ingredients
        ing=[str(x) for x in (row[2] or []) if str(x).strip()] or split_ingredients(row[3])
        match={'name':row[0],'kind':row[1],'offer_id':row[5]}
        if ing:
            match['ingredients']=ing
        declared=[str(x) for x in (row[4] or []) if str(x).strip()]
        if declared:
            # Structured seller-declared codes travel separately; they are never mixed into OCR text (#59).
            match['allergens_declared']=declared[:32]
        return {'match':match}
    except PG_ERRORS + (KeyError, OSError) as error:
        raise HTTPException(503,'CATALOG_UNAVAILABLE') from error

@app.post('/internal/process')
def process(body:Input,authorization:str=Header(default='')):
    authorize(authorization)
    try:
        raw=dict(body.profile)
        requested=raw.get('allergens',[])
        if not isinstance(requested, (list, tuple)):
            raise ValueError('allergens must be a list')
        normalized=[normalize_code(a) or a for a in requested]
        unsupported=[a for a in normalized if a not in ALLERGENS]
        raw['allergens']=[a for a in normalized if a in ALLERGENS] if body.selected_domain=='food' else []
        if body.selected_domain!='food':raw['avoid_ingredients']=[]
        profile=UserProfile.from_dict(raw)
        food=body.selected_domain=='food'
        declared={normalize_code(x) for x in body.allergens_declared} - {None} if food else set()
        unknown_declared=[x for x in body.allergens_declared if normalize_code(x) is None] if food else []
        detected=detect(list(body.ingredients)+unknown_declared) if food else {}
        warnings=[{'type':'allergy','allergen':a,'evidence':'contains',
            'message':f"판매처 알레르기 표시에 {ALLERGENS[a][0]}이(가) 포함되어 있습니다. 상품 표시를 직접 확인해 주세요."}
            for a in raw['allergens'] if a in declared]
        warnings+=[{'type':'allergy','allergen':a,'evidence':'contains',
            'message':f"OCR에서 {ALLERGENS[a][0]} 관련 표현이 감지되었습니다. 상품 표시를 직접 확인해 주세요."}
            for a in raw['allergens'] if a in detected and a not in declared]
        # 식품이 아닌 상품(노트북·가전 등)에는 알레르기 경고를 붙이지 않는다.
        # 식품일 때만 자동 검증을 지원하지 않는 항목을 '확인 필요'로 알린다.
        unchecked=unsupported if body.selected_domain=='food' else []
        warnings += [{'type':'allergy','allergen':a,'evidence':'unknown',
            'message':'이 알레르기 항목의 자동 검증은 지원하지 않습니다. 상품 표시를 직접 확인해 주세요.'} for a in unchecked]
        if body.selected_domain=='food' and raw['allergens'] and not body.ingredients:
            warnings += [{'type':'allergy','allergen':a,'evidence':'unknown','message':'알레르기 성분표를 인식하지 못했습니다. 구매 전 판매처의 원재료 표시를 직접 확인해 주세요.'}
                         for a in raw['allergens'] if a not in declared and a not in detected]
        # Internal code 'soy' is the clients' 'soybean'; answer in the code the client sent so its label lookup works.
        for w in warnings:
            if w['allergen']=='soy':w['allergen']='soybean'
    except (ValueError,TypeError,KeyError,ContractError) as error:
        raise HTTPException(422,'INVALID_RECOMMENDATION_INPUT') from error
    try:
        with config.connect() as conn:
            try:
                model_id=config.validate(conn,body.selected_domain)
            except ValueError as error:
                raise HTTPException(503,'EMBEDDING_CONTRACT_UNAVAILABLE') from error
            catalog=PgCatalog(conn,body.selected_domain)
            # 관련도 기준점: 엉뚱한 상품명(리뷰 문구 등)에도 가장 가까운 상품을 무조건 보여주지 않도록.
            # 문장 임베딩 모델 기준 0.5(RECO_MIN_SCORE로 조절). 실측(2026-11-27, MiniLM): 관련 상품 0.5~0.86,
            # 리뷰 문구·무관 상품 0.38~0.47. 테스트용 해시 임베딩은 점수 척도가 달라 기본 끔.
            embedder=config.embedder()
            default_min='0' if embedder.name=='hash-ngram-384' else '0.5'
            min_score=float(os.getenv('RECO_MIN_SCORE') or default_min)
            # 가장 비슷한 후보보다 0.25 이상 낮은 후보도 뺀다(RECO_SCORE_MARGIN, 해시 임베딩은 끔)
            margin=float(os.getenv('RECO_SCORE_MARGIN') or ('0' if embedder.name=='hash-ngram-384' else '0.25'))
            engine=Recommender(catalog,PgVectorIndex(conn,model_id),
                              embedder,make_ranker(os.getenv('RECO_RANKER','rule')))
            result=engine.recommend(profile,body.query,top_k=8,min_score=min_score,score_margin=margin)  # 프리미엄 5개 + 중고·품절로 빠지는 여유
            ids=catalog.offer_ids([p.product_id for p in result.picks])
        return {'offer_ids':[ids[p.product_id] for p in result.picks if p.product_id in ids],
                'reasons':{ids[p.product_id]:p.reason for p in result.picks if p.product_id in ids},
                'ranker':result.ranker,'selected_domain':body.selected_domain,'warnings':warnings}
    except HTTPException:
        raise
    except PG_ERRORS + (KeyError, OSError) as error:
        raise HTTPException(503,'RECOMMENDATION_DEPENDENCY_UNAVAILABLE') from error
    except (ValueError,ContractError) as error:
        raise HTTPException(422,'INVALID_RECOMMENDATION_INPUT') from error
