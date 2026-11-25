"""Small anonymous official read-only probes. No operational persistence or backend send."""
import argparse
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import threading
from decimal import Decimal
from services.collector.domeggook_live.domeggook_delivery import utcnow,atomic
from services.collector.marketplace_live.normalize import finish,money,validate_body
from services.collector.real_feed_collectors.real_collectors.core import SOURCES,rows,convert
from .transport import SafeHTTP,Wait

POLICIES={
    'smartify':{'host':'smartify.in','feed':'https://smartify.in/product-feed.xml','reference':'https://smartify.in/developers/',
        'limits':'ordinary_fair_use; local_probe_max6','storage':'cache_and_cite_with_attribution; no_wholesale_competing_republication'},
    'yappy_kids':{'host':'www.yappykids.com','feed':'https://www.yappykids.com/fb.php?lang=en','api':'https://www.yappykids.com/api/mcp',
        'reference':'https://www.yappykids.com/agents','limits':'60/minute; 3000/day/IP; local_probe_max6','storage':'product_comparison_use; systematic_DB_reuse_pending'},
    'perfume_registry':{'host':'perfumeregistry.com','feed':'https://perfumeregistry.com/feed.xml',
        'reference':'https://perfumeregistry.com/ai','limits':'not_specified; local_probe_max6','storage':'systematic_DB_reuse_pending'}}

class PublicReader(SafeHTTP):
    def __init__(self,provider,root,*,maximum=6,clock=utcnow):
        if provider not in POLICIES or not 1<=maximum<=6:raise ValueError('bounded_public_provider_required')
        self.provider=provider;self.policy=POLICIES[provider];self.maximum=maximum;self.expires=clock()+timedelta(minutes=20)
        self.allowed={self.policy['feed'],'https://'+self.policy['host']+'/robots.txt'}
        if 'api' in self.policy:self.allowed.add(self.policy['api'])
        cfg={'source':'html_public_lookup_'+provider,'base_url':'https://'+self.policy['host']+'/',
            'enabled':True,'requests_per_hour':12,'requests_per_24h':40,'request_interval_seconds':1}
        super().__init__(cfg,root,clock)
    def permitted(self,target):
        return target in self.allowed and len(self.state['requests'])<self.maximum and self.clock()<self.expires
    def method_permitted(self,method,target,body):
        if method=='GET':return target in self.allowed
        if method!='POST' or target!=self.policy.get('api'):return False
        try:data=json.loads(body)
        except (TypeError,ValueError):return False
        if not isinstance(data,dict) or not isinstance(data.get('params'),dict):return False
        return (data.get('jsonrpc')=='2.0' and data.get('method')=='tools/call' and
            data.get('params',{}).get('name') in ('search_products','get_product','get_store_info'))
    def tool(self,name,arguments):
        if self.provider!='yappy_kids' or name not in ('search_products','get_product','get_store_info'):raise ValueError('read_only_official_tools_required')
        if name=='search_products':
            if set(arguments)-{'query','lang','limit','page'} or not 1<=arguments.get('limit',0)<=3 or arguments.get('page',0)!=0:raise ValueError('small_search_only')
            if not isinstance(arguments.get('query'),str) or len(arguments['query'])>100:raise ValueError('bounded_query')
        elif name=='get_product' and (set(arguments)-{'id','lang'} or type(arguments.get('id')) is not int):raise ValueError('native_product_ID_required')
        body={'jsonrpc':'2.0','id':len(self.state['requests'])+1,'method':'tools/call','params':{'name':name,'arguments':arguments}}
        code,text,_=self._request('POST',self.policy['api'],json.dumps(body,separators=(',',':')).encode())
        if code!=200:raise Wait('public_API_not_200',hold=True)
        response=json.loads(text,parse_float=Decimal)
        if response.get('error') or not isinstance(response.get('result'),dict) or response['result'].get('isError'):raise Wait('public_API_error',hold=True)
        result=response['result']
        if isinstance(result.get('structuredContent'),dict):return result['structuredContent']
        texts=[c['text'] for c in result.get('content',[]) if c.get('type')=='text' and isinstance(c.get('text'),str)]
        if len(texts)!=1:raise Wait('public_API_structure_review',hold=True)
        return json.loads(texts[0],parse_float=Decimal)

def permitted_wait(reader,action,stop=None):
    stop=stop or threading.Event()
    for _ in range(3):
        try:return action()
        except Wait as exc:
            delay=(exc.until-reader.clock()).total_seconds() if exc.until else 999
            if exc.hold or str(exc) not in ('rate_wait','robots_crawl_delay','robots_request_rate') or not 0<=delay<=10:raise
            if stop.wait(delay):raise Wait('probe_stopping',hold=True)
    raise Wait('public_probe_rate_review',hold=True)

def summarize_body(body):
    return {'status':'valid_observation','native_fields_present':sorted(k for k in ('name','price','currency','url','condition','availability') if body.get(k) is not None),
        'stock_quantity':None,'actual_quantity_not_inferred':True,'is_synthetic':False}

def feed_probe(reader,maximum,on_valid=None):
    code,text=permitted_wait(reader,lambda:reader.fetch(reader.policy['feed']))
    if code!=200:raise Wait('public_feed_not_found',hold=True)
    count=0;valid=0;held=0;checks=[]
    for raw in rows(text.encode()):
        if count>=maximum:break
        count+=1
        try:
            body=convert(reader.provider,raw,reader.clock().isoformat())
            validate_body(body,{'allowed_product_hosts':list(SOURCES[reader.provider][1]),
                'currencies':{'smartify':['INR'],'perfume_registry':['USD'],'yappy_kids':['EUR','PLN']}[reader.provider]})
        except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
            held+=1
            reason=str(exc)
            allowed=('missing_','unsupported_','condition_exception_title','variant_offer_requires_detail','sale_window_requires_review','invalid_price_currency','unexpected_product_host','nonfinite_price')
            checks.append({'status':'held','reason':reason if reason.startswith(allowed) and len(reason)<100 else 'native_schema_review_required','is_synthetic':False})
        else:
            valid+=1;checks.append(summarize_body(body))
            if on_valid:on_valid(body)
    return {'inspected_products':count,'valid_products':valid,'held_products':held,'products':checks}

def mcp_probe(reader,maximum,query,on_valid=None):
    data=permitted_wait(reader,lambda:reader.tool('search_products',{'query':query,'lang':'en','limit':maximum,'page':0}))
    candidates=data.get('products',data.get('items')) if isinstance(data,dict) else data
    if not isinstance(candidates,list):raise Wait('public_search_structure_review',hold=True)
    checks=[];valid=held=0;details=0;detail_fields=set()
    cfg={'allowed_product_hosts':[reader.policy['host']],'currencies':['EUR','PLN']}
    for item in candidates[:maximum]:
        if not isinstance(item,dict):raise Wait('public_product_structure_review',hold=True)
        ident=item.get('id')
        if type(ident) is int:
            detail=permitted_wait(reader,lambda:reader.tool('get_product',{'id':ident,'lang':'en'}));details+=1
            if isinstance(detail,dict) and isinstance(detail.get('product'),dict):detail=detail['product']
            if not isinstance(detail,dict) or detail.get('id')!=ident:raise Wait('public_detail_identity_review',hold=True)
            detail_fields.update(detail);item=detail
        # Use only explicit native condition/currency; do not derive them from the store's line of business.
        native_price=item.get('price');native_price=native_price.get('value') if isinstance(native_price,dict) else native_price
        condition=item.get('condition') if item.get('condition') in ('new','used') else None
        availability={'in_stock':'available','low_stock':'available','out_of_stock':'out_of_stock','sold':'ended'}.get(item.get('availability'))
        identity=item.get('id');seller=item.get('seller')
        seller=seller.get('name') if isinstance(seller,dict) else seller
        try:
            result=finish('yappy_kids',dict(source_listing_id=str(identity) if identity is not None else None,
                variant_key=str(item.get('sku') or identity) if identity is not None else None,
                name=item.get('name'),price=money(native_price) if native_price is not None else None,
                currency=item.get('currency'),url=item.get('url'),condition=condition,availability=availability),seller,item.get('availability'),reader.clock().isoformat(),cfg)
            if not seller:result['observation']=None;result['missing_fields'].append('seller')
        except (ValueError,TypeError,KeyError,ArithmeticError):result={'observation':None,'missing_fields':['native_schema_review_required']}
        if result['observation']:
            valid+=1;checks.append(summarize_body(result['observation']))
            if on_valid:on_valid(result['observation'])
        else:held+=1;checks.append({'status':'held','reasons':result['missing_fields'],'is_synthetic':False})
    return {'inspected_products':len(checks),'valid_products':valid,'held_products':held,'products':checks,
        'detail_requests_this_probe':details,'native_detail_fields':sorted(detail_fields),
        'native_response_fields':sorted(set(k for item in candidates[:maximum] if isinstance(item,dict) for k in item))}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--provider',choices=tuple(POLICIES),required=True);p.add_argument('--state-dir',required=True)
    p.add_argument('--max-products',type=int,default=3);p.add_argument('--mcp',action='store_true');p.add_argument('--query',default='Yappy')
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--plan',action='store_true');mode.add_argument('--lookup',action='store_true')
    p.add_argument('--report');a=p.parse_args(argv)
    if not 1<=a.max_products<=3:raise SystemExit('maximum_three_products')
    report={'provider':a.provider,'mode':'public_read_only_lookup' if a.lookup else 'plan','maximum_products':a.max_products,
        'maximum_HTTP_requests':6,'policy_reference':POLICIES[a.provider]['reference'],'storage_permission':POLICIES[a.provider]['storage'],
        'operational_backend_requests':0,'production_DB_writes':0,'raw_products_exported':False,'is_synthetic':False}
    if a.plan:report.update(HTTP_requests_this_command=0);print(json.dumps(report));return 0
    from services.collector.domeggook_live.runtime import FileState
    root=Path(a.state_dir)
    with FileState(root/'lock').lock():
        reader=PublicReader(a.provider,root)
        try:
            report.update(mcp_probe(reader,a.max_products,a.query) if a.mcp else feed_probe(reader,a.max_products));report['status']='completed'
        except (Wait,ValueError,TypeError,KeyError,ArithmeticError):report.update(status='blocked_or_failed',reason='policy_transport_or_native_schema_review_required')
        finally:
            report['HTTP_attempts']=len(reader.state['requests']);report['request_statuses']=[e['status'] for e in reader.state['requests']];reader.close()
    if a.report:atomic(Path(a.report),report)
    print(json.dumps(report));return 0 if report['status']=='completed' else 2

if __name__=='__main__':raise SystemExit(main())
