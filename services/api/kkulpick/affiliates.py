"""Affiliate metadata is attached to an existing offer, never a duplicate product."""
import os
from uuid import UUID
from fastapi import APIRouter,Depends,Query,Request
from pydantic import AwareDatetime,Field,HttpUrl,model_validator
from .access import access, admin_member
from .members import Strict,row,execute,fail,wrap
from .freshness import CARD_FRESHNESS, stale_hours

router=APIRouter()

class Affiliate(Strict):
    partner_name:str=Field(min_length=1,max_length=100)
    affiliate_url:HttpUrl
    starts_at:AwareDatetime
    ends_at:AwareDatetime|None=None
    enabled:bool=True
    expected_version:int=Field(ge=0)

    @model_validator(mode='after')
    def valid(self):
        if not self.partner_name.strip() or (self.ends_at and self.ends_at<=self.starts_at):raise ValueError('invalid period or partner')
        u=self.affiliate_url
        if u.scheme!='https' or u.username or u.password or u.host not in os.getenv('AFFILIATE_URL_HOSTS','store.example.test').split(','):
            raise ValueError('affiliate destination must be explicitly allowed HTTPS')
        return self


@router.put('/v2/admin/affiliate-offers/{offer_id}')
async def save(offer_id:UUID,data:Affiliate,req:Request,uid=Depends(admin_member)):
    async with access(req,uid,{'admin'}):
        async with req.app.state.engine.begin() as c:
            offer=await row(c,'SELECT offer_id FROM app.offers WHERE offer_id=:id FOR UPDATE',id=offer_id)
            if not offer:fail(404,'OFFER_NOT_FOUND')
            old=await row(c,'SELECT version FROM app.affiliate_offers WHERE offer_id=:id',id=offer_id)
            if (old['version'] if old else 0)!=data.expected_version:fail(409,'VERSION_CONFLICT')
            r=await row(c,'''INSERT INTO app.affiliate_offers(offer_id,partner_name,affiliate_url,starts_at,ends_at,enabled,updated_by)
                VALUES(:id,:name,:url,:start,:end,:enabled,:u) ON CONFLICT(offer_id) DO UPDATE SET
                partner_name=:name,affiliate_url=:url,starts_at=:start,ends_at=:end,enabled=:enabled,
                updated_by=:u,version=app.affiliate_offers.version+1,updated_at=now() RETURNING *''',
                id=offer_id,name=data.partner_name,url=str(data.affiliate_url),start=data.starts_at,end=data.ends_at,enabled=data.enabled,u=uid)
            await execute(c,"INSERT INTO app.catalog_admin_audit(actor_id,offer_id,action) VALUES(:u,:id,'affiliate.save')",u=uid,id=offer_id)
    return wrap(dict(r),req)


@router.delete('/v2/admin/affiliate-offers/{offer_id}')
async def disable(offer_id:UUID,req:Request,expected_version:int=Query(ge=1),uid=Depends(admin_member)):
    async with access(req,uid,{'admin'}):
        async with req.app.state.engine.begin() as c:
            old=await row(c,'SELECT * FROM app.affiliate_offers WHERE offer_id=:id FOR UPDATE',id=offer_id)
            if not old:fail(404,'AFFILIATE_NOT_FOUND')
            if old['version']!=expected_version:fail(409,'VERSION_CONFLICT')
            await execute(c,'UPDATE app.affiliate_offers SET enabled=false,version=version+1,updated_by=:u,updated_at=now() WHERE offer_id=:id',id=offer_id,u=uid)
            await execute(c,"INSERT INTO app.catalog_admin_audit(actor_id,offer_id,action) VALUES(:u,:id,'affiliate.disable')",u=uid,id=offer_id)
    return wrap({'offer_id':offer_id,'enabled':False,'version':expected_version+1},req)


@router.get('/v2/recommendations/featured')
async def featured(req:Request,limit:int=Query(10,ge=1,le=100),selected_domain:str=Query('product',pattern='^(product|food)$'),after:UUID|None=None):
    async with req.app.state.engine.connect() as c:
        rows=(await execute(c,f'''SELECT o.offer_id,i.name,o.price::text,o.currency,o.price_observed_at AS observed_at,
            o.availability,a.affiliate_url AS url,a.partner_name AS subtitle,o.kind AS image_kind,{CARD_FRESHNESS}
            FROM app.affiliate_offers a JOIN app.offers o USING(offer_id) JOIN app.catalog_items i USING(item_id)
            WHERE a.enabled AND a.starts_at<=now() AND (a.ends_at IS NULL OR a.ends_at>now())
            AND o.availability='available' AND o.kind=:k
            AND (CAST(:after AS uuid) IS NULL OR o.offer_id>CAST(:after AS uuid))
            ORDER BY o.offer_id LIMIT :n''',k=selected_domain,after=after,n=limit,stale_hours=stale_hours())).mappings().all()
    return wrap([dict(r)|{'affiliate':True,'reason':'제휴 상품'} for r in rows],req)


@router.get('/v2/admin/affiliate-offers')
async def admin_list(req:Request,limit:int=Query(20,ge=1,le=100),after:UUID|None=None,uid=Depends(admin_member)):
    async with access(req,uid,{'admin'}):
        async with req.app.state.engine.connect() as c:
            rows=(await execute(c,'''SELECT a.*,i.name,o.price::text FROM app.affiliate_offers a JOIN app.offers o USING(offer_id) JOIN app.catalog_items i USING(item_id)
                WHERE CAST(:a AS uuid) IS NULL OR a.offer_id>CAST(:a AS uuid)
                ORDER BY a.offer_id LIMIT :n''',a=after,n=limit)).mappings().all()
    return wrap([dict(r) for r in rows],req)


@router.get('/v2/recommendations/basic')
async def basic(req:Request,limit:int=Query(10,ge=1,le=30),
                selected_domain:str=Query('product',pattern='^(product|food)$')):
    """Public catalog browsing, not personalized AI or an analysis/history write."""
    async with req.app.state.engine.connect() as c:
        rows=(await execute(c,f'''SELECT o.offer_id,i.name,o.price::text,o.currency,
            o.price_observed_at AS observed_at,o.availability,{CARD_FRESHNESS},
            COALESCE(a.affiliate_url,o.current_url) AS url,
            COALESCE(a.partner_name,o.source) AS subtitle,o.kind AS image_kind,
            (a.offer_id IS NOT NULL) AS affiliate
            FROM app.offers o JOIN app.catalog_items i USING(item_id)
            LEFT JOIN app.affiliate_offers a ON a.offer_id=o.offer_id
              AND a.enabled AND a.starts_at<=now() AND (a.ends_at IS NULL OR a.ends_at>now())
            WHERE o.availability='available' AND o.condition='new' AND o.kind=:k
            ORDER BY o.last_seen_at DESC,o.offer_id LIMIT :n''',
            k=selected_domain,n=limit,stale_hours=stale_hours())).mappings().all()
    return wrap([dict(r)|{'reason':'최근 판매가 확인된 상품 · 개인 맞춤 분석 아님'} for r in rows],req)
