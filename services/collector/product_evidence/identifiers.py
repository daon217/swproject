"""Explicit API, labelled HTML and Product JSON-LD identifiers; no title guessing."""
import ipaddress
import json
import re
from urllib.parse import urlsplit
from bs4 import BeautifulSoup

LABELS={'브랜드':'brand','brand':'brand','제조사':'manufacturer','manufacturer':'manufacturer',
 '모델명':'model_name','model':'model_name','modelname':'model_name','모델번호':'model_number','modelnumber':'model_number',
 'mpn':'mpn','제조사부품번호':'mpn','gtin':'gtin','gtin8':'gtin','gtin12':'gtin','gtin13':'gtin','gtin14':'gtin','ean':'gtin','upc':'gtin','바코드':'gtin',
 'sku':'sku','판매자상품코드':'sku','색상':'color','color':'color','사이즈':'size','size':'size'}

def clean(value):
    if isinstance(value,dict):value=value.get('name')
    if not isinstance(value,(str,int)) or isinstance(value,bool):return None
    text=BeautifulSoup(str(value),'html.parser').get_text(' ',strip=True)
    if not text or re.fullmatch(r'해당\s*없음|없음|기타|[-.]|상세(?:정보|설명|페이지)(?:\s*(?:별도표기|참조|참고))?',text):return None
    return text

def gtin(value):
    if not value.isascii() or not value.isdigit() or len(value) not in (8,12,13,14):return None
    padded=value.zfill(14)
    check=(10-sum(int(c)*(3 if i%2==0 else 1) for i,c in enumerate(padded[:13]))%10)%10
    return padded if check==int(padded[-1]) else None

def public_image(value):
    if not isinstance(value,str):return False
    try:
        p=urlsplit(value)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443) or p.hostname.lower()=='localhost':return False
        try:return ipaddress.ip_address(p.hostname).is_global
        except ValueError:return not p.hostname.lower().endswith(('.local','.internal'))
    except ValueError:return False

def extract_identifiers(*,api_values=None,notices=(),html='',html_allowed=False,product_url=''):
    candidates={};rejected=[]
    def add(key,value,path,method):
        value=clean(value)
        if not value:return
        raw=value
        if key=='gtin':
            value=gtin(value)
            if value is None:rejected.append({'field':key,'raw':raw,'source_field':path,'reason':'invalid_gtin'});return
        limit=100 if key in ('color','size') else 128 if key=='sku' else 200
        if len(value)>limit:rejected.append({'field':key,'raw':raw,'source_field':path,'reason':'length_limit'});return
        candidates.setdefault(key,[]).append({'value':value,'raw':raw,'source_field':path,'method':method,'source_url':product_url})
    for key,entry in (api_values or {}).items():
        if entry and isinstance(entry,tuple):add(key,entry[0],entry[1],'api_text')
    for i,item in enumerate(notices):
        if isinstance(item,dict) and item.get('type','item')=='item':
            key=LABELS.get(re.sub(r'[\s_\-]','',str(item.get('name',''))).casefold())
            if key:add(key,item.get('desc'),f'detail.infoDuty.item[{i}].desc','api_text')
    if html_allowed:
        soup=BeautifulSoup(html or '', 'html.parser')
        products=[]
        def walk(node):
            if isinstance(node,list):
                for x in node:walk(x)
            elif isinstance(node,dict):
                types=node.get('@type',[]);types=[types] if isinstance(types,str) else types
                if 'Product' in types:products.append(node)
                if '@graph' in node:walk(node['@graph'])
        for script in soup.select('script[type="application/ld+json"]')[:12]:
            try:walk(json.loads(script.string or script.get_text()))
            except (ValueError,TypeError):continue
        selected=products if len(products)==1 else [p for p in products if p.get('url')==product_url]
        for index,node in enumerate(selected[:1]):
            for label,key in LABELS.items():
                if label in node:add(key,node[label],f'jsonld.Product[{index}].{label}','jsonld')
            for i,prop in enumerate(node.get('additionalProperty') or []):
                if not isinstance(prop,dict):continue
                key=LABELS.get(re.sub(r'[\s_\-]','',str(prop.get('name',''))).casefold())
                if key:add(key,prop.get('value'),f'jsonld.additionalProperty[{i}]','jsonld')
        for node in soup.select('script,style,nav,footer,aside'):node.decompose()
        pairs=[]
        for tr in soup.select('tr')[:200]:
            cells=tr.find_all(['th','td'],recursive=False)
            if len(cells)%2==0:pairs.extend((cells[i].get_text(' ',strip=True),cells[i+1].get_text(' ',strip=True)) for i in range(0,len(cells),2))
        for dt in soup.select('dt')[:100]:
            dd=dt.find_next_sibling('dd')
            if dd:pairs.append((dt.get_text(' ',strip=True),dd.get_text(' ',strip=True)))
        for line in soup.get_text('\n',strip=True).splitlines()[:2000]:
            if ':' in line:pairs.append(tuple(line.split(':',1)))
        for i,(label,value) in enumerate(pairs):
            key=LABELS.get(re.sub(r'[\s_\-]','',label).casefold())
            if key:add(key,value,f'html.label[{i}]','html_text')
    values={};evidence={}
    for key,entries in candidates.items():
        unique={x['value'] for x in entries};status='source_reported' if len(unique)==1 else 'conflicting'
        evidence[key]={'status':status,'sources':entries}
        if status=='source_reported':values[key]=entries[0]['value']
    return {'values':values,'evidence':evidence,'rejected':rejected,'status':'source_reported' if values else 'not_reported'}
