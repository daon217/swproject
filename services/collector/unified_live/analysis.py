"""Bounded, evidence-based page analysis. Suggestions never grant collection rights."""
import json
import re
from urllib.parse import urljoin,urlsplit,urlunsplit,parse_qsl,urlencode
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from .policy import url

PROPERTIES={
    'id':'[itemprop="productID"],meta[property="product:retailer_item_id"]',
    'name':'[itemprop="name"],meta[property="og:title"]',
    'price':'[itemprop="price"],meta[property="product:price:amount"],meta[property="og:price:amount"],meta[property="og:price"]',
    'currency':'[itemprop="priceCurrency"],meta[property="product:price:currency"],meta[property="og:price:currency"],meta[property="og:currency"]',
    'seller':'[itemprop="seller"] [itemprop="name"],[itemprop="seller"]',
    'condition':'[itemprop="itemCondition"],meta[property="product:condition"],meta[property="og:condition"]',
    'availability':'[itemprop="availability"],meta[property="product:availability"],meta[property="og:availability"]',
    'image':'[itemprop="image"],meta[property="og:image"]',
    'description':'[itemprop="description"],meta[property="og:description"],meta[name="description"]',
    'category':'[itemprop="category"],meta[property="product:category"]',
    'brand':'[itemprop="brand"] [itemprop="name"],[itemprop="brand"],meta[property="product:brand"]',
    'manufacturer':'[itemprop="manufacturer"] [itemprop="name"],[itemprop="manufacturer"]',
    'model':'[itemprop="model"]','model_number':'[itemprop="modelNumber"]','mpn':'[itemprop="mpn"]',
    'gtin':'[itemprop="gtin"],[itemprop="gtin13"],[itemprop="gtin14"]',
    'color':'[itemprop="color"]','size':'[itemprop="size"]',
    'sku':'[itemprop="sku"]','url':'[itemprop="url"],meta[property="og:url"]',
}

def node_value(node):
    if node is None:return None
    return node.get('content') or node.get('href') or node.get('data-src') or node.get('src') or node.get_text(' ',strip=True)

def value(soup,field,selectors=None):
    selector=(selectors or {}).get(field) or PROPERTIES.get(field)
    if not selector:return None
    nodes=soup.select(selector)
    if not (selectors or {}).get(field):
        # Native product Microdata outranks page-level OG/social share metadata.
        native=','.join(part for part in selector.split(',') if '[itemprop=' in part)
        native_nodes=soup.select(native) if native else []
        if field=='name':
            native_nodes=[n for n in native_nodes if n.find_parent(attrs={'itemprop':re.compile(r'^(seller|brand|manufacturer)$')}) is None]
        if native_nodes:nodes=native_nodes
        elif field in ('name','image','description','url'):
            # A single explicit product OG block can follow generic website OG tags.
            tags=list(soup.select('meta[property]'))
            boundaries=[i for i,n in enumerate(tags) if n.get('property')=='og:type' and n.get('content')=='product']
            if len(boundaries)==1:
                begin=boundaries[0];end=next((i for i in range(begin+1,len(tags)) if tags[i].get('property')=='og:type'),len(tags))
                block={id(n) for n in tags[begin:end]};nodes=[n for n in nodes if id(n) in block]
    if not (selectors or {}).get(field) and field in ('seller','brand','manufacturer'):
        inner=soup.select(f'[itemprop="{field}"] [itemprop="name"]')
        if inner:nodes=inner
    if not (selectors or {}).get(field) and field=='name':
        nodes=[n for n in nodes if n.find_parent(attrs={'itemprop':re.compile(r'^(seller|brand|manufacturer)$')}) is None]
    values=list(dict.fromkeys(v for n in nodes[:20] if (v:=node_value(n))))
    # Overlapping seller/name selectors can yield the same text; conflicting prices are held.
    if not values and not (selectors or {}).get(field):
        labels={'condition':{'condition','상품상태','상품 상태'},'currency':{'currency','통화'},'availability':{'availability','stock status','재고 상태'},'seller':{'seller','판매처'},'model_number':{'model number','모델번호'}}
        native=[]
        for label in soup.select('th,dt')[:300]:
            if label.get_text(' ',strip=True).strip(' :：').casefold() not in labels.get(field,set()):continue
            sibling=label.find_next_sibling(['td','dd'])
            if sibling:
                v=sibling.get_text(' ',strip=True)
                if v and v not in native:native.append(v)
        values=native
    return values[0] if len(values)==1 else None

def product_graph(soup):
    documents=[];nodes={};products=[]
    def visit(v,depth=0):
        if depth>16:raise ValueError('JSONLD_depth_exceeded')
        if isinstance(v,list):
            for x in v:visit(x,depth+1)
        elif isinstance(v,dict):
            if isinstance(v.get('@id'),str) and len(v)>1:
                if v['@id'] in nodes and nodes[v['@id']]!=v:raise ValueError('conflicting_JSONLD_ID')
                nodes[v['@id']]=v
            types=v.get('@type',[]);types=[types] if isinstance(types,str) else types
            if any(str(t).rstrip('/').rsplit('/',1)[-1]=='Product' for t in types):products.append(v)
            for k in ('@graph','itemListElement','item','offers','seller','brand','manufacturer'):
                if k in v:visit(v[k],depth+1)
    for script in soup.select('script[type="application/ld+json"]')[:100]:
        try:doc=json.loads(script.string or script.get_text())
        except json.JSONDecodeError:continue
        documents.append(doc);visit(doc)
    def resolve(v,trail=(),depth=0):
        if depth>16:raise ValueError('JSONLD_reference_depth_exceeded')
        if isinstance(v,list):return [resolve(x,trail,depth+1) for x in v]
        if not isinstance(v,dict):return v
        ident=v.get('@id')
        if ident in nodes and ident not in trail:
            target=dict(nodes[ident]);target.update(v);v=target;trail=trail+(ident,)
        return {k:resolve(x,trail,depth+1) if k in ('offers','seller','brand','manufacturer','image') else x for k,x in v.items()}
    output=[];fingerprints=set()
    for p in products:
        item=resolve(p);key=json.dumps(item,sort_keys=True,ensure_ascii=False)
        if key not in fingerprints:output.append(item);fingerprints.add(key)
    return output

def labeled_food(soup):
    labels={'원재료명':'ingredients','원재료':'ingredients','원재료명 및 함량':'ingredients','ingredients':'ingredients',
        '알레르기':'allergens','알레르기 유발물질':'allergens','allergens':'allergens',
        '혼입 가능성':'cross_contact','동일 시설':'cross_contact','may contain':'cross_contact',
        '제조사':'manufacturer','제조원':'manufacturer','manufacturer':'manufacturer'}
    output={}
    for label in soup.select('th,dt,label')[:300]:
        text=label.get_text(' ',strip=True).strip(' :：').casefold()
        field=labels.get(text)
        if not field:continue
        sibling=label.find_next_sibling(['td','dd','span'])
        if sibling:
            raw=sibling.get_text(' ',strip=True)[:4000]
            if field in output and output[field]!=raw:raise ValueError('conflicting_food_labels')
            output[field]=raw
    return output

def search_template(soup,base):
    host=urlsplit(base).hostname
    for form in soup.select('form')[:30]:
        if str(form.get('method','get')).lower()!='get' or form.select_one('input[type="password"]'):continue
        query=form.select_one('input[name="q"],input[name="query"],input[name="keyword"],input[name="search"],input[name="s"]')
        if query is None:continue
        try:target=url(urljoin(base,form.get('action') or base),host)
        except ValueError:continue
        p=urlsplit(target);pairs=parse_qsl(p.query,keep_blank_values=True)
        pairs=[(k,v) for k,v in pairs if k!=query['name']]+[(query['name'],'KKULPICKQUERYMARKER')]
        result=urlunsplit((p.scheme,p.netloc,p.path,urlencode(pairs),''))
        return result.replace('KKULPICKQUERYMARKER','{query}')
    return None

def opensearch_template(text,base):
    if len(text.encode())>65536 or re.search(r'<!\s*(?:DOCTYPE|ENTITY)',text,re.I):raise ValueError('bounded_plain_OpenSearch_required')
    root=ET.fromstring(text)
    for node in root.iter():
        if node.tag.rsplit('}',1)[-1]!='Url' or node.attrib.get('type')!='text/html':continue
        target=node.attrib.get('template','')
        if target.count('{searchTerms}')!=1:continue
        target=target.replace('{searchTerms}','{query}').replace('{startPage?}','{page}').replace('{startPage}','{page}')
        remaining=target.replace('{query}','test').replace('{page}','1')
        if '{' in remaining or '}' in remaining:continue
        checked=url(urljoin(base,remaining),urlsplit(base).hostname)
        # Return the original placeholders only after the concrete URL passed origin/credential checks.
        raw=urljoin(base,target)
        url(raw.replace('{query}','test').replace('{page}','1'),urlsplit(base).hostname)
        return raw
    return None

def analyze(html,base):
    if len(html.encode())>2_000_000:raise ValueError('bounded_analysis_required')
    soup=BeautifulSoup(html,'html.parser');products=product_graph(soup)
    candidates={}
    for field,selector in PROPERTIES.items():
        for candidate in selector.split(','):
            if len(soup.select(candidate))==1:candidates[field]=candidate;break
    api_links=[];opensearch=[]
    for n in soup.select('link[href],a[href]')[:1000]:
        href=n.get('href');rel=n.get('rel',[])
        if isinstance(rel,str):rel=rel.split()
        try:target=url(urljoin(base,href),urlsplit(base).hostname)
        except ValueError:continue
        if 'service-desc' in rel or 'api-catalog' in rel:api_links.append(target)
        if 'search' in rel and n.get('type')=='application/opensearchdescription+xml':opensearch.append(target)
    return {'jsonld_product_count':len(products),'open_graph':soup.select_one('meta[property="og:type"][content="product"]') is not None,
        'microdata_product_count':len(soup.select('[itemtype$="/Product"]')),'selector_candidates':candidates,
        'search_url_template':search_template(soup,base),'opensearch_descriptions':list(dict.fromkeys(opensearch)),
        'published_API_links':list(dict.fromkeys(api_links)),
        'supports_pagination':bool(soup.select_one('a[rel~="next"]')),
        'supports_product_detail':bool(products or soup.select_one('[itemtype$="/Product"]')),
        'supports_price':bool(value(soup,'price') or any(isinstance(p.get('offers'),dict) and p['offers'].get('price') is not None for p in products)),
        'supports_stock_status':bool(value(soup,'availability') or any(isinstance(p.get('offers'),dict) and p['offers'].get('availability') for p in products)),
        'supports_used_products':any('UsedCondition' in str(p.get('itemCondition','')) for p in products),
        'permission_inferred':False,'auto_selector_activation':False}
