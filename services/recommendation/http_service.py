"""Authenticated, bounded HTTP adapter for the team's recommendation pipeline."""
import os
import secrets
from contextlib import asynccontextmanager
import psycopg
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .adapters.postgres import PgCatalog, PgVectorIndex
from . import embedding_config as config
from .contracts import UserProfile, ContractError
from .pipeline import Recommender
from .rankers import make_ranker
from .allergens import ALLERGENS,detect


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=1000)
    selected_domain: Literal['product','food']
    ingredients: list[str] = Field(default_factory=list,max_length=100)
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
    except (psycopg.Error, ValueError, KeyError, OSError) as error:
        raise HTTPException(503, 'EMBEDDING_DEPENDENCY_UNAVAILABLE') from error
    return {'status':'ok','service':'recommendation','implementation':'team-pipeline',
            'business_ready':os.getenv('RECO_EMBEDDER','st') != 'hash',
            'store':'pg','embedder':os.getenv('RECO_EMBEDDER','st'),
            'ranker':os.getenv('RECO_RANKER','rule')}

@app.post('/internal/dev/probe')
def probe(body:dict,authorization:str=Header(default='')):
    authorize(authorization)
    return body|health()


@app.post('/internal/catalog-context')
def catalog_context(body:CatalogContext,authorization:str=Header(default='')):
    authorize(authorization)
    try:
        with config.connect() as conn:
            row=conn.execute('''SELECT i.name,o.kind FROM app.offers o
                JOIN app.catalog_items i USING(item_id)
                WHERE o.current_url=%s AND (%s::text IS NULL OR o.kind=%s)
                ORDER BY (o.availability='available') DESC,o.offer_id LIMIT 1''',
                (body.page_url,body.selected_domain,body.selected_domain)).fetchone()
        return {'match':{'name':row[0],'kind':row[1]} if row else None}
    except psycopg.Error as error:
        raise HTTPException(503,'CATALOG_UNAVAILABLE') from error

@app.post('/internal/process')
def process(body:Input,authorization:str=Header(default='')):
    authorize(authorization)
    try:
        raw=dict(body.profile)
        requested=raw.get('allergens',[])
        normalized=['soy' if a=='soybean' else a for a in requested]
        unsupported=[a for a in normalized if a not in ALLERGENS]
        raw['allergens']=[a for a in normalized if a in ALLERGENS] if body.selected_domain=='food' else []
        if body.selected_domain!='food':raw['avoid_ingredients']=[]
        profile=UserProfile.from_dict(raw)
        detected=detect(body.ingredients) if body.selected_domain=='food' else {}
        warnings=[{'type':'allergy','allergen':a,'evidence':'contains',
            'message':f"OCR에서 {ALLERGENS[a][0]} 관련 표현이 감지되었습니다. 상품 표시를 직접 확인해 주세요."}
            for a in raw['allergens'] if a in detected]
        # 식품이 아닌 상품(노트북·가전 등)에는 알레르기 경고를 붙이지 않는다.
        # 식품일 때만 자동 검증을 지원하지 않는 항목을 '확인 필요'로 알린다.
        unchecked=unsupported if body.selected_domain=='food' else []
        warnings += [{'type':'allergy','allergen':a,'evidence':'unknown',
            'message':'이 알레르기 항목의 자동 검증은 지원하지 않습니다. 상품 표시를 직접 확인해 주세요.'} for a in unchecked]
        if body.selected_domain=='food' and raw['allergens'] and not body.ingredients:
            warnings += [{'type':'allergy','allergen':a,'evidence':'unknown','message':'페이지 성분을 확인하지 못했습니다.'} for a in raw['allergens']]
        with config.connect() as conn:
            try:
                model_id=config.validate(conn,body.selected_domain)
            except ValueError as error:
                raise HTTPException(503,'EMBEDDING_CONTRACT_UNAVAILABLE') from error
            catalog=PgCatalog(conn,body.selected_domain)
            engine=Recommender(catalog,PgVectorIndex(conn,model_id),
                              config.embedder(),make_ranker(os.getenv('RECO_RANKER','rule')))
            result=engine.recommend(profile,body.query,top_k=6)
            ids=catalog.offer_ids([p.product_id for p in result.picks])
        return {'offer_ids':[ids[p.product_id] for p in result.picks if p.product_id in ids],
                'reasons':{ids[p.product_id]:p.reason for p in result.picks if p.product_id in ids},
                'ranker':result.ranker,'selected_domain':body.selected_domain,'warnings':warnings}
    except (psycopg.Error, KeyError, OSError) as error:
        raise HTTPException(503,'RECOMMENDATION_DEPENDENCY_UNAVAILABLE') from error
    except (ValueError,KeyError,ContractError) as error:
        raise HTTPException(422,'INVALID_RECOMMENDATION_INPUT') from error
