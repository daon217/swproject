"""Authenticated, bounded HTTP adapter for the team's recommendation pipeline."""
import os
import secrets
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .adapters.local import InMemoryVectorIndex
from .adapters.offers_api import offer_to_product
from .contracts import UserProfile, ContractError
from .embedders import make_embedder
from .pipeline import Recommender
from .rankers import make_ranker
from .allergens import ALLERGENS,detect


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')
    query: str = Field(min_length=1, max_length=1000)
    selected_domain: Literal['product','food']
    offers: list[dict] = Field(max_length=1000)
    ingredients: list[str] = Field(default_factory=list,max_length=100)
    profile: dict = Field(default_factory=lambda: {'user_id':'worker'})


def authorize(authorization):
    token=os.getenv('WORKSPACE_TOKEN','')
    if len(token)<32 or not secrets.compare_digest(authorization.encode(), ('Bearer '+token).encode()):
        raise HTTPException(401,'SERVICE_AUTH_REQUIRED')


class Catalog:
    def __init__(self,products):self.products={p.product_id:p for p in products}
    def all_ids(self):return list(self.products)
    def get_many(self,ids):return {i:self.products[i] for i in ids if i in self.products}


app=FastAPI(title='꿀픽 추천 연결')

@app.get('/health')
def health():
    return {'status':'ok','service':'recommendation','implementation':'team-pipeline',
            'business_ready':True,'embedder':os.getenv('RECO_EMBEDDER','hash'),
            'ranker':os.getenv('RECO_RANKER','rule')}

@app.post('/internal/dev/probe')
def probe(body:dict,authorization:str=Header(default='')):
    authorize(authorization)
    return body|health()

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
        # Never include unavailable offers, including suspect status.
        offers=[o for o in body.offers if o.get('availability')=='available']
        products=[offer_to_product(o,body.selected_domain) for o in offers]
        ids={p.product_id:o['offer_id'] for p,o in zip(products,offers)}
        embedder=make_embedder(os.getenv('RECO_EMBEDDER','hash'))
        engine=Recommender(Catalog(products),InMemoryVectorIndex(None,embedder.name),
                           embedder,make_ranker(os.getenv('RECO_RANKER','rule')))
        engine.reindex()
        result=engine.recommend(profile,body.query,top_k=6)
        return {'offer_ids':[ids[p.product_id] for p in result.picks],
                'reasons':{ids[p.product_id]:p.reason for p in result.picks},
                'ranker':result.ranker,'selected_domain':body.selected_domain,'warnings':warnings}
    except (ValueError,KeyError,ContractError) as error:
        raise HTTPException(422,'INVALID_RECOMMENDATION_INPUT') from error
