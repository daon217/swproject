"""Operator-selected public directories -> DNS-verified candidates, never rights."""
import argparse,json,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
from services.collector.domeggook_live.domeggook_delivery import atomic
from services.collector.domeggook_live.runtime import FileState
from .discovery import MetadataHTTP,wait_fetch
from .bulk import publisher_candidates,candidates
from .parser import document
from .policy import url
from .transport import public_address

def harvest(publishers,root,*,concurrency=3,http_factory=MetadataHTTP,resolver=public_address):
    if not isinstance(publishers,list) or len(publishers)>30 or not 1<=concurrency<=4:raise ValueError('bounded_publishers_and_concurrency_required')
    root=Path(root);locks={};guard=threading.Lock()
    def one(spec):
        http=None;before=0;target='';record={'status':'FAILED','candidate_links':0};found=[]
        try:
            target=url(spec['url']);host=urlsplit(target).hostname;record['url']=target
            if spec.get('metadata_read_approved') is not True:record['status']='ACCESS_REVIEW';return found,record
            with guard:lock=locks.setdefault(host,threading.Lock())
            # Different publisher pages on the same domain share one ledger writer.
            with lock,FileState(root/host/'lock').lock():
                http=http_factory(host,[target],root/host);http.cfg['request_interval_seconds']=max(2,http.cfg['request_interval_seconds']);before=len(http.state['requests'])
                code,text=wait_fetch(http,target)
                if code!=200:raise ValueError('publisher_HTTP_review')
                found=publisher_candidates(text,target,spec['selector'],spec.get('platform','unknown'))
                if spec.get('domain_label_only'):
                    labels=set()
                    for node in document(text).select(spec['selector'])[:2000]:
                        try:
                            h=urlsplit(url(node.get('href',''))).hostname
                            if node.get_text(' ',strip=True).lower() in (h,h.removeprefix('www.')):labels.add(h)
                        except (ValueError,TypeError):continue
                    found=[v for v in found if urlsplit(v['url']).hostname in labels]
                excluded=spec.get('exclude_domains',[])
                found=[v for v in found if not any(urlsplit(v['url']).hostname==d or urlsplit(v['url']).hostname.endswith('.'+d) for d in excluded)]
                record.update(status='READ',candidate_links=len(found))
        except Exception:found=[];record['reason']='publisher_policy_network_or_selector_review'
        finally:
            if http:record['source_requests']=len(http.state['requests'])-before;http.close()
        return found,record
    raw=[];evidence=[]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for found,record in pool.map(one,publishers):raw+=found;evidence.append(record)
    # DNS only; no candidate storefront is fetched during discovery.
    unique={}
    for item in raw:
        host=urlsplit(item['url']).hostname;unique.setdefault(host.removeprefix('www.'),item)
    def verify(item):
        rows,stats=candidates([item],resolver=resolver)
        return rows[0] if rows else None
    rows=[]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for row in pool.map(verify,unique.values()):
            if row:rows.append(row)
    audit={'publisher_results':evidence,'raw_candidate_links':len(raw),'unique_before_DNS':len(unique),'DNS_verified_candidates':len(rows),'storefront_requests':0,'permission_inferred':False}
    return rows,audit

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--publishers',required=True);p.add_argument('--state-dir',required=True);p.add_argument('--output',required=True);p.add_argument('--live',action='store_true');p.add_argument('--concurrency',type=int,default=3);a=p.parse_args(argv)
    specs=json.loads(Path(a.publishers).read_text(encoding='utf-8-sig'))
    if not a.live:print(json.dumps({'publishers':len(specs),'source_requests':0,'permission_inferred':False}));return 0
    with FileState(Path(a.state_dir)/'harvest-lock').lock():
        rows,audit=harvest(specs,a.state_dir,concurrency=a.concurrency);atomic(a.output,rows);atomic(str(a.output)+'.evidence.json',audit)
    print(json.dumps({'candidates':len(rows),'source_requests':sum(x.get('source_requests',0) for x in audit['publisher_results']),'storefront_requests':0}));return 0
if __name__=='__main__':raise SystemExit(main())
