"""Reused safe description parser; only called when desc license permits."""
import hashlib,re
from urllib.parse import urlsplit,urljoin
from bs4 import BeautifulSoup
from .runtime import public_url
ALLOWED_TAGS={'div','section','article','p','span','br','hr','img','ul','ol','li','table','thead','tbody','tfoot','tr','th','td','caption','strong','b','em','i','u','h1','h2','h3','h4','h5','h6','a'}
DROP_TAGS={'script','style','iframe','object','embed','svg','math','form','input','button','textarea','select','link','meta','base','template','noscript','video','audio','source'}
EXTENSIONS=('description_html','detail_image_urls','detail_image_alt','excluded_detail_images','view_desc_documents')

def safe_url(value,base=None):
    if not isinstance(value,str) or not value.strip():return None
    value=value.strip()
    if any(ord(c)<32 for c in value):return None
    value=urljoin(base,value) if base else value
    try:p=urlsplit(value)
    except ValueError:return None
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:return None
    return value if public_url(value) else None


def parse_view_desc(body,base_url=None):
    if not isinstance(body,str) or len(body.encode())>4_000_000:raise ValueError('description_response_size_or_type_invalid')
    soup=BeautifulSoup(body,'html.parser');blocks=soup.select('.ifrm_prdc_detail')
    if not blocks:raise ValueError('view_desc_container_missing')
    # Nested matching regions must not duplicate images/text/markup.
    blocks=[block for block in blocks if not any('ifrm_prdc_detail' in p.get('class',[]) for p in block.parents if getattr(p,'attrs',None))]
    texts=[];urls=[];alts={};excluded=[];html=[];specs={};conflicts=set()
    for block in blocks:
        for bad in list(block.find_all(DROP_TAGS)):bad.decompose()
        for node in list(block.find_all(True)):
            if node.name not in ALLOWED_TAGS:node.unwrap();continue
            old=dict(node.attrs);node.attrs={}
            if node.name=='img':
                raw=old.get('src') or old.get('data-src');url=safe_url(raw,base_url)
                marker=' '.join([str(old.get('id','')),str(old.get('class','')),str(old.get('alt','')),urlsplit(url or '').path])
                reason=None
                if not url:reason='empty_or_unsafe_or_unresolved_URL'
                elif str(old.get('width','')) in ('1','2') and str(old.get('height','')) in ('1','2'):reason='tracking_pixel_dimensions'
                elif re.search(r'(^|[\W_])(logo|tracking|pixel|advertisement|adbanner)([\W_]|$)',marker,re.I):reason='explicit_logo_ad_or_tracker_marker'
                if reason:
                    excluded.append({'raw_src':raw,'url':url,'reason':reason});node.decompose();continue
                alt=old.get('alt');alt=alt if isinstance(alt,str) else None
                node['src']=url
                if alt is not None:node['alt']=alt
                if url not in urls:urls.append(url)
                alts.setdefault(url,[])
                if alt and alt not in alts[url]:alts[url].append(alt)
            elif node.name=='a':
                target=safe_url(old.get('href'),base_url)
                if target:node['href']=target;node['rel']='noopener noreferrer'
            elif node.name in ('th','td'):
                for key in ('colspan','rowspan'):
                    if str(old.get(key,'')).isdigit() and 0<int(old[key])<=100:node[key]=str(old[key])
        block.attrs={'class':['ifrm_prdc_detail']}
        for tr in block.select('table tr'):
            cells=tr.find_all(['th','td'],recursive=False)
            if len(cells)!=2:continue
            label,value=(cell.get_text(' ',strip=True) for cell in cells)
            if label and value:
                if label in specs and specs[label]!=value:conflicts.add(label)
                else:specs[label]=value
        # Table contents are structured facts, not an invented prose description.
        prose=BeautifulSoup(str(block),'html.parser')
        for table in prose.select('table'):table.decompose()
        value=prose.get_text(' ',strip=True)
        if value and value not in texts:texts.append(value)
        html.append(str(block))
    for label in conflicts:specs.pop(label,None)
    return {'description': '\n'.join(texts) or None,'specifications':specs or None,
        'description_html':'\n'.join(html),'detail_image_urls':urls,'detail_image_alt':alts,
        'excluded_detail_images':excluded,'description_content_status':'text' if texts else 'image_only_no_OCR' if urls else 'no_text_or_detail_images',
        'raw_response_sha256':hashlib.sha256(body.encode()).hexdigest(),'OCR_performed':False}
