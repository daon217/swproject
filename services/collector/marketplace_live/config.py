import json
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

SOURCES=('yes24_api','searchapi_google_shopping','ebay_browse','serper_google_shopping')
PAID_SHOPPING=('searchapi_google_shopping','serper_google_shopping')

def stamp(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('aware_timestamp_required')
    return parsed.astimezone(timezone.utc)

def rights(cfg,current,storage=False):
    grant=cfg.get('rights',{})
    uses={'lookup','systematic_collection'}|({'storage','reuse'} if storage else set())
    try:
        okay=bool(grant.get('reference') and uses<=set(grant.get('allowed_uses',[])) and
                  stamp(grant['expires_at'])>current)
    except (KeyError,ValueError,TypeError,AttributeError):return False
    # Public YES24 terms do not authorize building a separate catalogue database.
    if cfg['source']=='yes24_api' and not grant.get('exception_agreement_reference'):return False
    return okay

def validate(cfg):
    if cfg.get('source') not in SOURCES:raise ValueError('unknown_source')
    for key in ('enabled','backend_enabled','backend_owner_approved','price_semantics_confirmed'):
        if type(cfg.get(key)) is not bool:raise ValueError('explicit_boolean_required')
    for key,maximum in (('requests_per_cycle',100),('requests_per_hour',1000),
                        ('requests_per_24h',5000),('max_units_per_month',100000),
                        ('page_size',20),('max_pages_per_cycle',10),('max_task_attempts',3)):
        value=cfg.get(key)
        minimum=0 if key=='max_units_per_month' else 1
        if type(value) is not int or not minimum<=value<=maximum:raise ValueError('invalid_'+key)
    for key,floor in (('request_interval_seconds',1),('cycle_interval_seconds',7200)):
        value=cfg.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<floor:
            raise ValueError('invalid_'+key)
    for key in ('cost_per_request','max_cost_per_month'):
        try:
            value=Decimal(cfg[key])
            if not isinstance(cfg[key],str) or not value.is_finite() or value<0:raise ValueError()
        except (KeyError,InvalidOperation,TypeError,ValueError):raise ValueError('invalid_'+key) from None
    if cfg['source'] in PAID_SHOPPING and cfg['enabled'] and (
        cfg['max_units_per_month']<1 or Decimal(cfg['cost_per_request'])<=0 or Decimal(cfg['max_cost_per_month'])<=0):
        raise ValueError('explicit_paid_shopping_credit_and_cost_budget_required')
    if cfg['source']=='serper_google_shopping' and cfg['enabled'] and (
        type(cfg.get('credits_per_request')) is not int or not 1<=cfg['credits_per_request']<=100):
        raise ValueError('explicit_Serper_credit_reservation_required')
    if cfg['source']=='serper_google_shopping' and cfg['enabled']:
        unit=cfg.get('cost_currency')
        if not isinstance(unit,str) or len(unit)!=3 or not unit.isascii() or not unit.isalpha() or not unit.isupper():
            raise ValueError('explicit_Serper_cost_currency_required')
    if not isinstance(cfg.get('queries'),list) or not cfg['queries'] or any(not isinstance(q,str) or not q.strip() for q in cfg['queries']):
        raise ValueError('queries_required')
    if len(cfg['queries'])>20:raise ValueError('too_many_queries')
    if not isinstance(cfg.get('allowed_product_hosts'),list) or not cfg['allowed_product_hosts'] or any(
        not isinstance(h,str) or not h or any(c in h for c in '/:*@?#') for h in cfg['allowed_product_hosts']):
        raise ValueError('explicit_product_hosts_required')
    if not isinstance(cfg.get('currencies'),list) or not cfg['currencies']:raise ValueError('currencies_required')
    settings=cfg.get('backend_delivery',{})
    for key,default,maximum in (('max_attempts',5,5),('max_requests_per_flush',1,10),('max_pending',100,5000),('retry_base_seconds',5,300)):
        v=settings.get(key,default)
        if type(v) is not int or not 1<=v<=maximum:raise ValueError('invalid_backend_'+key)
    return cfg

def load_config(path):
    data=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    configs=[validate(c) for c in data['sources']]
    if len({c['source'] for c in configs})!=len(configs):raise ValueError('duplicate_source')
    return configs
