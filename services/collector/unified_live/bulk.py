"""Bounded storefront batch, reusing Discovery/Fleet/Registry/Parser transports.

No discovery evidence implies permission. No backend is constructed by validation.
"""
import argparse,copy,csv,hashlib,json,socket,threading,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit,urljoin
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from soupsieve import SelectorSyntaxError
from services.collector.domeggook_live.domeggook_delivery import atomic,load,utcnow
from services.collector.domeggook_live.runtime import FileState
from services.collector.marketplace_live.probe import lookup_permitted
from .policy import url,grant,dedicated,interval
from .transport import SafeHTTP,Wait,public_address
from .parser import document,links,normalize
from .analysis import analyze,value
from .discovery import DiscoveryStore,marketplace_id,select_adapter
from .fleet import registration
from .registry import register

STATES={'DISCOVERED','ACCESS_REVIEW','PERMITTED','PARSER_READY','VERIFIED','ACTIVE','INCOMPLETE','BLOCKED','FAILED'}
COLUMNS=['domain','platform','permission_status','test_status','extracted_product_count','valid_product_count','missing_fields','failure_reason','collection_method','schedule_seconds','sample_kind','reference','robots_status','profile_registered','source_requests','market_kind','country_scope']

def candidates(items,resolver=public_address):
    """Verify public DNS before registering; group www aliases without merging tenants."""
    output={};rejected=[];seen=0
    for item in items:
        seen+=1
        try:
            target=url(item['url']);host=urlsplit(target).hostname;key=host[4:] if host.startswith('www.') else host
            if key in output:
                if item.get('reference') not in output[key]['references']:output[key]['references'].append(item.get('reference'))
                continue
            resolver(host)
            output[key]={**item,'url':target,'domain':host,'references':[item.get('reference')],'dns_public_verified':True}
        except (ValueError,KeyError,TypeError,OSError,Wait):rejected.append({'url':item.get('url'),'reason':'invalid_or_unresolved_or_nonpublic_domain'})
    return list(output.values()),{'input_candidates':seen,'unique_domains':len(output),'rejected':rejected}

def publisher_candidates(html,base,selector,platform='unknown'):
    if not isinstance(selector,str) or len(selector)>200:raise ValueError('bounded_directory_selector_required')
    found=[];host=urlsplit(url(base)).hostname
    for node in document(html).select(selector)[:2000]:
        try:
            target=url(urljoin(base,node.get('href','')))
            if urlsplit(target).hostname==host:continue
            found.append({'url':target,'reference':base,'platform':platform,'sample_kind':'external_commercial_candidate'})
        except ValueError:continue
    return found

class BatchHTTP(SafeHTTP):
    def __init__(self,cfg,root,approval,clock=utcnow):
        self.approval=copy.deepcopy(approval);super().__init__(cfg,root,clock)
    def permitted(self,target):
        # Lookup-only validation never claims a right to persist/reuse products.
        a=self.approval
        return bool(a.get('test_allowed') is True and a.get('allowed_hosts')==[self.host] and a.get('terms_reference') and lookup_permitted({'rights':a},self.clock()))

def fetch_wait(http,target,stop):
    for attempt in range(4):
        try:return http.fetch(target)
        except Wait as exc:
            delay=(exc.until-http.clock()).total_seconds() if exc.until else 999
            allowed=str(exc) in ('rate_wait','robots_crawl_delay','robots_request_rate','retry_after','server_error')
            if exc.hold or not allowed or not 0<=delay<=10 or stop.wait(delay):raise
    raise Wait('batch_retry_exhausted')

def sitemap_links(text,base,host):
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('unsafe_sitemap_XML')
    root=ET.fromstring(text);out=[]
    for n in root.iter():
        if n.tag.rsplit('}',1)[-1]!='loc' or not n.text:continue
        try:target=url(urljoin(base,n.text.strip()),host)
        except ValueError:continue
        if target not in out:out.append(target)
        if len(out)>=100:break
    return out

class Batch:
    def __init__(self,root,*,concurrency=3,http_factory=BatchHTTP,clock=utcnow):
        if type(concurrency) is not int or not 1<=concurrency<=4:raise ValueError('concurrency_1_to_4_required')
        self.root=Path(root);self.concurrency=concurrency;self.factory=http_factory;self.clock=clock;self.stop=threading.Event()
    def validate_one(self,item,approval):
        host=item['domain'];a=copy.deepcopy(approval or {});used=item.get('kind')=='used'
        row=dict.fromkeys(COLUMNS,'');row.update(domain=host,platform=item.get('platform','unknown'),permission_status='unverified',test_status='DISCOVERED',extracted_product_count=0,valid_product_count=0,collection_method='official_API_required' if dedicated(host) else 'HTML_JSONLD_OG_CSS',schedule_seconds=60 if used else 7200,sample_kind=item.get('sample_kind','external_commercial_candidate'),reference=item.get('reference',''),robots_status='not_requested',profile_registered=False,source_requests=0)
        row['market_kind']='used' if used else 'general';row['country_scope']=item.get('country_scope','not_verified');row['history']=['DISCOVERED'];row['products']=[]
        def state(s):row['test_status']=s;row['history'].append(s)
        if a.get('explicitly_prohibited') is True:
            state('BLOCKED');row['failure_reason']='explicit_collection_prohibition';return row
        if not (a.get('test_allowed') is True and a.get('allowed_hosts')==[host] and a.get('terms_reference') and lookup_permitted({'rights':a},self.clock())):
            state('ACCESS_REVIEW');row['failure_reason']='test_storage_reuse_permission_unverified';return row
        row['permission_status']='storage_reuse_confirmed' if grant({'rights':a},self.clock()) else 'lookup_test_only';state('PERMITTED')
        if dedicated(host):
            state('ACCESS_REVIEW');row['failure_reason']='dedicated_official_adapter_entitlement_and_live_budget_required';return row
        cfg={'source':'html_'+hashlib.sha256(host.encode()).hexdigest()[:20],'base_url':'https://'+host+'/',
            'enabled':True,'requests_per_hour':min(30,a.get('requests_per_hour',12)),'requests_per_24h':min(60,a.get('requests_per_24h',24)),
            'request_interval_seconds':max(2,a.get('request_interval_seconds',2)),
            'allowed_product_hosts':[host],'max_products_per_cycle':min(3,a.get('max_products',3)),
            'mode':'used' if used else 'general','selectors':a.get('selectors',{}),'currencies':a.get('currencies',['KRW','USD','GBP','EUR']),
            'rights':a,'country':item.get('country')}
        root=self.root/'domains'/cfg['source'];http=None;before_requests=0;missing=set();failures=[];caps={};starts=[]
        try:
            with FileState(root/'lock').lock():
                http=self.factory(cfg,root,a,self.clock);before_requests=len(http.state['requests'])
                starts=[url(t,host) for t in a.get('start_urls',[item['url']])[:5]]
                queue=[('auto',t) for t in starts];visited=set();details=set();pages=0;render=None
                queue+=[('sitemap',url(t,host)) for t in a.get('sitemap_urls',[])[:2]]
                categories=a.get('category_links_selector')
                while queue and pages<min(10,a.get('max_pages',6)) and len(details)<cfg['max_products_per_cycle']:
                    kind,target=queue.pop(0)
                    if target in visited:continue
                    visited.add(target);pages+=1
                    try:
                        code,text=fetch_wait(http,target,self.stop)
                        row['robots_status']='allowed' if http.robots and http.robots.can_fetch('KkulpickCollector/1.0',target) else 'not_available'
                        if code!=200:failures.append('HTTP_'+str(code));continue
                        if kind=='sitemap':
                            queue.extend(('sitemap' if ET.fromstring(text).tag.rsplit('}',1)[-1]=='sitemapindex' else 'auto',t) for t in sitemap_links(text,target,host)[:10]);continue
                        if a.get('render_javascript') is True:
                            if render is None:
                                from .render import PlaywrightRenderer
                                render=PlaywrightRenderer()
                            text=render.render(target,http);row['collection_method']='HTML_Chromium_JSONLD_CSS'
                        soup=document(text);info=analyze(text,target);selectors=cfg['selectors'];native_price=value(soup,'price',selectors)
                        is_detail=kind=='detail' or info['jsonld_product_count']==1 or info['microdata_product_count']==1 or bool(native_price and value(soup,'name',selectors))
                        if not is_detail:
                            found,nxt=links(text,target,cfg);queue.extend(('detail',t) for t in found)
                            if nxt:queue.append(('auto',nxt))
                            if categories:
                                for node in soup.select(categories)[:10]:
                                    try:queue.append(('auto',url(urljoin(target,node.get('href','')),host)))
                                    except ValueError:continue
                            continue
                        details.add(target);caps.update(info);state('PARSER_READY')
                        extracted=bool(value(soup,'name',selectors) and native_price and value(soup,'image',selectors))
                        try:
                            result=normalize(text,target,self.clock().isoformat(),cfg)
                            extracted=bool(result.get('name') and result.get('price') is not None and result.get('url') and result['metadata'].get('image_url'))
                            absent=list(result['missing_fields'])
                            if not result['metadata'].get('image_url'):absent.append('image_url')
                            valid=result.get('observation') is not None and not absent
                            if valid:row['valid_product_count']+=1
                            row['products'].append({'url':target,'extracted':extracted,'valid':valid,'missing_fields':sorted(set(absent))})
                            missing.update(absent)
                        except (ValueError,TypeError,KeyError,ArithmeticError):
                            valid=False;missing.add('normalization_requires_native_field_review')
                            for field in ('currency','condition','seller'):
                                if not value(soup,field,selectors):missing.add(field)
                            row['products'].append({'url':target,'extracted':extracted,'valid':False,'missing_fields':['normalization_requires_native_field_review']})
                        if extracted:row['extracted_product_count']+=1
                    except Wait as exc:
                        reason=str(exc);failures.append(reason)
                        if 'robots' in reason:row['robots_status']='disallowed_or_limited'
                        if exc.hold:
                            state('BLOCKED' if any(t in reason for t in ('robots','access','challenge','nonpublic','redirect')) else 'FAILED');break
                    except (ValueError,KeyError,TypeError,ArithmeticError,ET.ParseError,SelectorSyntaxError):failures.append('page_parser_or_configuration_error');continue
                if row['test_status'] not in ('BLOCKED','FAILED'):
                    state('VERIFIED' if row['valid_product_count'] else 'INCOMPLETE' if details else 'FAILED')
                row['missing_fields']=';'.join(sorted(missing));row['failure_reason']=';'.join(sorted(set(failures))) or ('required_product_fields_missing' if details and not row['valid_product_count'] else 'no_product_details_discovered' if not details else '')
                # No product bodies/raw HTML in reports or candidate state.
                row['activation_candidate']=dict(cfg=cfg,capabilities=caps,starts=starts) if row['valid_product_count'] else None
        except (ValueError,TypeError,KeyError,OSError,SelectorSyntaxError):state('FAILED');row['failure_reason']='site_configuration_lock_or_state_review'
        finally:
            if http:
                row['source_requests']=len(http.state['requests'])-before_requests;row['lifetime_source_requests']=len(http.state['requests']);http.close()
        return row
    def run(self,items,approvals,*,activate=False):
        # One row/domain and one batch writer; no overlapping network/budget writers.
        with FileState(self.root/'batch-lock').lock():
            unique={item['domain']:item for item in items};rows=[]
            with FileState(self.root/'discovery'/'lock').lock():
                store=DiscoveryStore(self.root/'discovery',self.clock)
                for item in unique.values():
                    try:store.add({'domain':item['domain'],'kind':item.get('kind','general'),'country':item.get('country')},item['reference'])
                    except (ValueError,TypeError,KeyError):pass

            with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
                tasks={pool.submit(self.validate_one,item,approvals.get(host,{})):host for host,item in unique.items()}
                for future in as_completed(tasks):
                    host=tasks[future]
                    try:row=future.result()
                    except Exception:
                        row=dict.fromkeys(COLUMNS,'');row.update(domain=host,test_status='FAILED',extracted_product_count=0,valid_product_count=0,failure_reason='isolated_site_runtime_failure',sample_kind=unique[host].get('sample_kind','external_commercial_candidate'))
                    rows.append(row)
            for row in rows:
                proposal=row.pop('activation_candidate',None)
                if not proposal or not activate:continue
                a=approvals[row['domain']]
                if not (a.get('activation_approved') is True and grant({'rights':a},self.clock()) and row['sample_kind'] in ('external_commercial_candidate','local_fixture')):
                    continue
                try:
                    with FileState(self.root/'discovery'/'lock').lock():
                        store=DiscoveryStore(self.root/'discovery',self.clock);item=unique[row['domain']]
                        ident=store.add({'domain':row['domain'],'kind':item.get('kind','general'),'country':item.get('country')},item['reference'])
                        previous=copy.deepcopy(store.state['sites'][ident]);site=store.state['sites'][ident];site.update(product_quality_verified=True,access_policy='metadata_accessible',capabilities=proposal['capabilities'])
                        if a.get('selectors'):site['capabilities']['css_product_reviewed']=True
                        if a.get('render_javascript'):site['capabilities']['javascript_reviewed']=True
                        site=store.evaluate(ident,a);cfg=registration(site,a)
                        if not cfg:raise ValueError('activation_contract_required')
                        path=self.root/'profiles'/(ident+'.json')
                        if path.exists() and load(path,None)!=cfg:
                            store.state['sites'][ident]=previous;store.save();raise ValueError('active_profile_change_requires_review')
                        try:register(cfg,self.root/'registry')
                        except (ValueError,OSError):
                            store.state['sites'][ident]=previous;store.save();raise
                        atomic(path,cfg)
                        keys={'reference','terms_reference','expires_at','allowed_uses','allowed_hosts','queries','search_url_template','start_urls','backend_enabled','backend_owner_approved','price_semantics_confirmed','backend_delivery','selectors','currencies','category_mapping','requests_per_hour','requests_per_24h','request_interval_seconds','provider_min_interval_seconds','evidence_storage','render_javascript'}
                        fleet_grants=load(self.root/'fleet-grants.json',{})
                        fleet_grants[ident]={k:v for k,v in a.items() if k in keys}
                        atomic(self.root/'fleet-grants.json',fleet_grants);row['profile_registered']=True
                        # ACTIVE means explicit repeat approval + runnable registration, not a DB ACK.
                        row['test_status']='ACTIVE';row['schedule_seconds']=interval(cfg)
                except (ValueError,TypeError,KeyError,OSError):row['failure_reason']='activation_configuration_or_history_review'
            rows.sort(key=lambda r:r['domain']);atomic(self.root/'batch_results.json',{'version':1,'at':self.clock().isoformat(),'rows':rows})
            return rows

def export(rows,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    for name,data in [('korean-mall-candidates.csv',rows),('korean-mall-success.csv',[r for r in rows if r['sample_kind']=='external_commercial_candidate' and r['test_status'] in ('VERIFIED','ACTIVE') and r['valid_product_count']>0]),('korean-mall-blocked.csv',[r for r in rows if r['test_status'] in ('ACCESS_REVIEW','BLOCKED','FAILED','INCOMPLETE')])]:
        with (out/name).open('w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=COLUMNS,extrasaction='ignore');writer.writeheader()
            for row in data:
                # CSV formula injection defence without changing the JSON state.
                writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items() if k in COLUMNS})

    # Required Markdown artifacts are generated by the same batch as the CSVs.
    commercial=[r for r in rows if r.get('sample_kind')=='external_commercial_candidate']
    demos=[r for r in rows if r.get('sample_kind')=='external_demo']
    local=[r for r in rows if r.get('sample_kind')=='local_fixture']
    metric=lambda group,key:sum(int(r.get(key,0) or 0) for r in group)
    report=['# 국내 중심 쇼핑몰 배치 결과','',
        '국내 중심 공개 자료에서 얻은 후보이며 국가 소재지를 별도로 확인한 목록은 아닙니다.',
        '로컬 fixture와 외부 데모, 상용 후보를 합산해 실수집 성공으로 표시하지 않습니다.','',
        '| 구분 | 상용 후보 | 외부 데모 | 로컬 fixture |','|---|---:|---:|---:|',
        f'| 고유 도메인 | {len(commercial)} | {len(demos)} | {len(local)} |',
        f'| 실제 source 요청 | {metric(commercial,"source_requests")} | {metric(demos,"source_requests")} | {metric(local,"source_requests")} |',
        f'| 상품 페이지 추출 | {metric(commercial,"extracted_product_count")} | {metric(demos,"extracted_product_count")} | {metric(local,"extracted_product_count")} |',
        f'| 필수값 통과 | {metric(commercial,"valid_product_count")} | {metric(demos,"valid_product_count")} | {metric(local,"valid_product_count")} |','',
        '권한 확인은 로컬 승인 근거로 판단합니다. robots 허용은 저장·재사용 권한이 아닙니다. ACTIVE는 반복 승인된 실행 프로필 등록이며 DB ACK가 아닙니다.',
        '사이트별 근거/보류/실패는 CSV와 batch_results.json에 기록합니다. 성공 CSV는 실제 검증된 상용 후보만 포함하며 0건이면 헤더만 존재합니다.']
    (out/'korean-mall-bulk-report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    used=[r for r in rows if r.get('market_kind')=='used' or any(d in r.get('domain','') for d in ('ebay','bunjang','joongna','daangn'))]
    lines=['# 중고 플랫폼 배치 결과','', '| domain | state | permission | products | reason |','|---|---|---|---:|---|']
    lines.extend('| '+str(r['domain'])+' | '+str(r['test_status'])+' | '+str(r['permission_status'])+' | '+str(r['valid_product_count'])+' | '+str(r['failure_reason'])+' |' for r in used)
    lines+=['','eBay는 기존 공식 API/공유 account 원장 경로를 사용합니다. 전용 API entitlement와 live 예산이 확인되지 않으면 이 배치가 상품 API를 요청하지 않습니다.',
        '번개장터 파트너 계약/키: https://api.bgzt.guide/ ; 중고나라 사전 승낙/약관: https://common.joongna.com/static/terms/TermsOfService_new.html',
        '60초는 요청 주기이며 권한·제공자 제한·공유 일/시간 예산이 우선합니다. 조회 권한만으로 반복/저장/재사용을 승인하지 않습니다.']
    (out/'used-marketplace-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    guide=['# 배치와 지속 실행 안내','',
        'python -m services.collector.unified_live.bulk --candidates /run/candidates.json --approvals /run/approvals.json --state-dir /state/bulk --output-dir /outputs',
        '기본은 계획만 출력합니다. 명시적으로 허용한 실제 조회는 --live, 검증·반복·저장·재사용 승인이 모두 있는 상용 소스만 등록하려면 --activate를 추가합니다.',
        '배치가 만든 /state/bulk/fleet-grants.json을 기존 Fleet의 --grants로, /state/bulk/discovery를 --discovery-state로 사용합니다. 생성 파일의 부모 디렉터리를 볼륨으로 마운트해야 atomic 교체가 보입니다.',
        'python -m services.collector.unified_live.fleet --state-dir /state/fleet --discovery-state /state/bulk/discovery --grants /state/bulk/fleet-grants.json --watch',
        'COLLECTOR_RUN_APPROVED=yes / COLLECTOR_DELIVERY_APPROVED=yes는 별도입니다. 내부 전송은 COLLECTOR_BACKEND_TRANSPORT=internal_http 및 COLLECTOR_BACKEND_BASE_URL=http://192.168.0.254:8000과 Docker secret token으로 설정합니다.',
        '기존 Compose fleet/discovery 서비스를 재사용하고 상태·원장·Outbox 볼륨을 보존합니다. 일반 최소 7200초, 허용된 중고 최소 60초이며 소스별 더 엄격한 정책을 따릅니다.',
        'eBay 일반/Used는 기존 단일 account 서비스의 공유 예산을 사용합니다. HTML batch가 eBay를 일반 HTML로 우회하지 않습니다.',
        'NAS/운영 PostgreSQL 접속이나 배포는 이 명령의 일부가 아닙니다. 장기 실행/승인 파일 변경은 관리자 책임이며 팀 API 계약은 유지됩니다.']
    (out/'collector-runtime-guide.md').write_text('\n'.join(guide)+'\n',encoding='utf-8')

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--candidates',required=True);p.add_argument('--approvals',required=True);p.add_argument('--state-dir',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--concurrency',type=int,default=3);p.add_argument('--live',action='store_true');p.add_argument('--activate',action='store_true');a=p.parse_args(argv)
    items=json.loads(Path(a.candidates).read_text(encoding='utf-8-sig'));approvals=json.loads(Path(a.approvals).read_text(encoding='utf-8-sig'))
    if not a.live:print(json.dumps({'candidates':len(items),'source_requests':0,'activation':False}));return 0
    rows=Batch(a.state_dir,concurrency=a.concurrency).run(items,approvals,activate=a.activate);export(rows,a.output_dir)
    print(json.dumps({'domains':len(rows),'states':{s:sum(r['test_status']==s for r in rows) for s in sorted(STATES)},'eligible_commercial_domains':sum(r['valid_product_count']>0 and r['sample_kind']=='external_commercial_candidate' for r in rows),'backend_requests':0}));return 0
if __name__=='__main__':raise SystemExit(main())
