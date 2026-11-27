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
from .rankers import FALLBACK_MODEL, make_ranker
from .allergens import ALLERGENS,detect,normalize_code


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=1000)
    selected_domain: Literal['product','food']
    ingredients: list[str] = Field(default_factory=list,max_length=100)
    allergens_declared: list[str] = Field(default_factory=list,max_length=32)
    profile: dict = Field(default_factory=lambda: {'user_id':'worker'})
    ai_fallback: bool = False


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
        # OCR 성분 목록에서 '본 제품은 … 사용한 제품과 같은 제조시설에서 제조하고 있습니다' 같은 교차오염 안내 문구는
        # 실제 함유 원재료가 아니므로 제외한다(표시 대상 19종이 모두 적혀 있어 모든 식품에 알레르기 주의가 뜨던 문제).
        ocr_ings=[]
        if food:
            raw_ings=list(body.ingredients)
            skip_until=-1
            import re as _re
            _facility_end=_re.compile(r'(?:같은|동일한?|가은)?\s*제조\s*시설|제조\s*공장|혼입\s*가능|사용한\s*제[품푼]',_re.I)
            _facility_start=_re.compile(r'(?:본|이)\s*제[품푼]은',_re.I)
            for idx_ing,tok in enumerate(raw_ings):
                if idx_ing<=skip_until:
                    continue
                if _facility_end.search(tok):
                    continue
                m=_facility_start.search(tok)
                if m and any(_facility_end.search(nxt) for nxt in raw_ings[idx_ing:idx_ing+6]):
                    prefix=tok[:m.start()].strip()
                    if prefix:
                        ocr_ings.append(prefix)
                    for j in range(idx_ing+1,min(len(raw_ings),idx_ing+6)):
                        if _facility_end.search(raw_ings[j]):
                            skip_until=j
                    continue
                ocr_ings.append(tok)
        # 하단 성분표(body.ingredients)가 아직 화면에 안 보여도 상품명(body.query, 예: '100% 무가당 땅콩버터') 자체에
        # 알레르기 원료가 명시되어 있으면 즉시 감지해 경고한다.
        title_ings=[body.query] if food and body.query else []
        detected=detect(title_ings+ocr_ings+unknown_declared) if food else {}
        warnings=[{'type':'allergy','allergen':a,'evidence':'contains',
            'message':f"판매처 알레르기 표시에 {ALLERGENS[a][0]}이(가) 포함되어 있습니다. 상품 표시를 직접 확인해 주세요."}
            for a in raw['allergens'] if a in declared]
        warnings+=[{'type':'allergy','allergen':a,'evidence':'contains',
            'message':f"상품명 또는 성분 표시에서 {ALLERGENS[a][0]} 관련 표현이 감지되었습니다. 상품 표시를 직접 확인해 주세요."}
            for a in raw['allergens'] if a in detected and a not in declared]
        # 식품이 아닌 상품(노트북·가전 등)에는 알레르기 경고를 붙이지 않는다.
        # 성분표를 아직 읽지 못했다고 해서 사용자의 모든 알레르기 항목에 무조건 '알레르기 주의' 경고를 띄우지 않는다.
        # 실제 성분표나 판매처 표시에서 알레르기 성분이 감지되었을 때만 경고한다.
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
            embedder=config.embedder()
            min_score=float(os.getenv('RECO_MIN_SCORE') or '0')
            margin=float(os.getenv('RECO_SCORE_MARGIN') or '0')
            ranker_kind=os.getenv('RECO_RANKER','rule')
            engine=Recommender(catalog,PgVectorIndex(conn,model_id),
                              embedder,make_ranker(ranker_kind))
            result=engine.recommend(profile,body.query,top_k=8,min_score=min_score,score_margin=margin)  # 프리미엄 5개 + 중고·품절로 빠지는 여유
            # DB에 관련 상품이 전혀 없어 추천 결과가 0건이고, 사용자가 '추천 상품 없을 시 AI 추천(ai_fallback)'을 켠 경우에만
            # 실시간 쇼핑몰 검색으로 상품을 찾아 적재한 뒤 가벼운 폴백 전용 모델(FALLBACK_MODEL)로 다시 추천한다.
            if not result.picks and body.ai_fallback:
                from .live_fallback import discover_and_ingest
                ingested=discover_and_ingest(conn,body.selected_domain,body.query,profile.include_used,
                                             catalog,PgVectorIndex(conn,model_id),embedder)
                if ingested:
                    fb_engine=Recommender(catalog,PgVectorIndex(conn,model_id),
                                          # FALLBACK_MODEL 은 Claude 모델명: local(gemma) 서버에 넘기면 403 -> 규칙 순위로 떨어짐
                                          embedder,make_ranker(ranker_kind,model=FALLBACK_MODEL if ranker_kind in ('claude','auto') else None))
                    result=fb_engine.recommend(profile,body.query,top_k=8,min_score=min_score,score_margin=margin)
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
