"""Source-labelled product components, materials and cautions. No absence/safety inference."""
import copy
import hashlib
import json
import re
from dataclasses import dataclass,replace
from decimal import Decimal
from requests.exceptions import RequestException
from bs4 import BeautifulSoup

FIELDS={
 'food':('ingredients','allergens','cross_contact','nutrition','cautions'),
 'cosmetics':('ingredients','cautions'),
 'apparel':('materials','cautions'),
 'household':('materials','ingredients','cautions'),
 'chemical':('ingredients','safety','cautions'),
 'baby':('materials','age_restriction','safety','cautions'),
 'accessories':('materials','cautions'),
 'supplement':('ingredients','functional_ingredients','nutrition','cautions'),
 'other':('materials','ingredients','cautions','safety')}
LABELS={
 'ingredients':('원재료명 및 함량','원재료명','원재료','원료명 및 함량','원료','전성분','성분','구성 성분','주요 성분','주요물질','사용물질','표시성분','ingredients'),
 'materials':('소재','제품소재','제품 소재','주요 소재','소재 및 혼용률','섬유혼용률','섬유 혼용률','재질','구성재질','주요소재','섬유의 조성 또는 혼용률','혼용률','금속소재','가죽종류','material','materials','composition'),
 'allergens':('알레르기','알레르기 유발물질','알레르기 정보','allergens','contains'),
 'cross_contact':('혼입 가능성','교차 오염','may contain'),
 'nutrition':('영양정보','영양성분','영양성분표','nutrition'),
 'cautions':('주의사항','사용할 때 주의사항','사용할 때의 주의사항','사용 시 주의사항','사용시 주의사항','사용상 주의사항','세탁방법 및 취급시 주의사항','취급시 주의사항','소비자안전을 위한 주의사항','섭취 시 주의사항','섭취량, 섭취방법 및 섭취시 주의사항','cautions','precautions'),
 'safety':('안전정보','안전확인 신고번호','KC인증정보','안전인증','유해위험성','응급처치','취급방법 및 취급시 주의사항, 안전표시','safety information'),
 'age_restriction':('사용연령','권장사용연령','사용연령 또는 권장사용연령','최소연령','age limit'),
 'functional_ingredients':('기능성 원료','기능성 성분','기능성 내용')}
MATERIALS={'면':'cotton','cotton':'cotton','폴리에스터':'polyester','polyester':'polyester',
 '실리콘':'silicone','silicone':'silicone','pp':'polypropylene','폴리프로필렌':'polypropylene',
 'pe':'polyethylene','폴리에틸렌':'polyethylene','abs':'abs','스테인리스':'stainless_steel',
 'stainless steel':'stainless_steel','소가죽':'cow_leather','천연가죽':'leather','가죽':'leather','leather':'leather',
 '니켈':'nickel','nickel':'nickel','알루미늄':'aluminium','울':'wool','양모':'wool','나일론':'nylon'}


def label_key(value):return re.sub(r'[^a-z0-9가-힣]','',str(value).casefold())
LABEL_INDEX={label_key(label):key for key,labels in LABELS.items() for label in labels}


def labelled_field(label):
    key=label_key(label)
    if '화장품법' in key and '모든성분' in key:return 'ingredients'
    return LABEL_INDEX.get(key)



def labelled_value(text):
    if labelled_field(text):return None
    match=re.match(r'^\s*([^:：]{1,100})\s*[:：]\s*(.+)$',text)
    if match and labelled_field(match.group(1)):return match.group(1),match.group(2)
    # Korean table labels often contain inter-character spacing ("재 질 PP").
    for label in sorted((x for labels in LABELS.values() for x in labels),key=len,reverse=True):
        letters=re.sub(r'\s+','',label)
        pattern=r'^\s*'+r'\s*'.join(map(re.escape,letters))+r'(?:\s*[:：]\s*|\s+)(\S.*)$'
        found=re.match(pattern,text,re.I)
        if found:return label,found.group(1)
    return None

def profile_for(category_levels,notice_type=''):
    names=[str(x.get('name','')) for x in category_levels if isinstance(x,dict)]
    text=' '.join(names+[notice_type])
    for pattern,profile in [(r'건강기능|기능성식품','supplement'),(r'화장품|미용','cosmetics'),
       (r'세제|세정제|화학제품','chemical'),(r'유아|어린이|아동용','baby'),
       (r'의류|언더웨어','apparel'),(r'패션잡화|가방|액세서리','accessories'),
       (r'식품|과자|음료','food'),(r'생활용품|주방용품','household')]:
        if re.search(pattern,text):return profile
    return 'other'


def plain(value):return BeautifulSoup(value,'html.parser').get_text(' ',strip=True) if isinstance(value,str) else ''


def placeholder(value):
    compact=re.sub(r'\s+','',plain(value))
    return not compact or bool(re.fullmatch(r'(?:상세(?:정보|페이지|설명|이미지)(?:별도표기|참조|참고|확인)?|상품상세(?:참조|설명참조)|별도표기|이미지참조|사진참조|[-.])',compact))


def split_terms(raw):
    raw=re.sub(r'(?<=[%％])\s+(?=[a-zA-Z가-힣])','; ',raw)
    tokens=[];part=[];depth=0
    for char in raw:
        if char in '([{':depth+=1
        elif char in ')]}':depth=max(0,depth-1)
        if char in ',;\n、/' and depth==0:
            if ''.join(part).strip():tokens.append(''.join(part).strip())
            part=[]
        else:part.append(char)
    if ''.join(part).strip():tokens.append(''.join(part).strip())
    return tokens


def normalized(raw,kind):
    if kind not in ('materials','ingredients','functional_ingredients','allergens','cross_contact'):return []
    result=[]
    for token in split_terms(raw):
        match=re.fullmatch(r'(.+?)\s*(\d+(?:\.\d+)?)\s*[%％]',token)
        name=(match.group(1) if match else token).strip();percentage=match.group(2) if match else None
        review=False
        if percentage and Decimal(percentage)>100:review=True
        negative=bool(re.search(r'없음|무첨가|미함유|\b(?:none|free from)\b',name,re.I))
        code=MATERIALS.get(name.casefold()) if kind not in ('allergens','cross_contact') and not negative else None
        if kind in ('allergens','cross_contact') and not negative:
            from services.collector.food_evidence.extract import ALIASES
            code=ALIASES.get(name.casefold())
            code={'soy':'soybean','sulfites':'sulfite'}.get(code,code)
        result.append({'name':name,'code':code,
            'percentage':percentage,'requires_review':review or negative,'negative_claim_unverified':negative})
    return result


@dataclass(frozen=True)
class ProductEvidenceRequest:
    source: str
    product_url: str
    observed_at: str
    category_levels: tuple
    is_food: bool|None
    condition: str='unknown'
    service_type: str='unknown'
    notice_type: str=''
    api_notices: tuple=()
    description_html: str=''
    description_text: str=''
    text_use_allowed: bool=False
    detail_image_urls: tuple=()
    image_use_allowed: bool=False


def extract_text(request):
    profile=profile_for(request.category_levels,request.notice_type);wanted=FIELDS[profile]
    output={'schema_version':'product-detail-evidence-v1','source':request.source,'source_url':request.product_url,
        'observed_at':request.observed_at,'category_levels':copy.deepcopy(request.category_levels),
        'category_profile':profile,'service_type':request.service_type,'condition':request.condition,'is_food':request.is_food,
        'fields':{k:{'raw':[],'normalized':[],'sources':[],'status':'not_reported'} for k in wanted},
        'source_references':[],'ocr_call_success':False,'OCR_performed':False,'ocr_extraction_success':False,
        'safe_to_use':None,'completeness':'partial','backend_status':'structured_nonfood_fields_pending_contract'}
    def add(label,value,method,path,confidence=None):
        key=labelled_field(label)
        if key not in wanted or not isinstance(value,str) or len(value)>12000 or placeholder(value):return
        raw=plain(value)
        if raw in output['fields'][key]['raw']:return
        field=output['fields'][key];field['raw'].append(raw);field['normalized'].extend(normalized(raw,key))
        field['sources'].append({'source_url':request.product_url,'source_field':path,'label':label,'method':method,'confidence':confidence,'raw':raw})
        field['status']='source_reported' if len(field['raw'])==1 else 'conflicting'
    for index,item in enumerate(request.api_notices):
        if isinstance(item,dict) and item.get('type','item')=='item':add(item.get('name',''),item.get('desc'),'api_text',f'detail.infoDuty.item[{index}].desc')
    if request.text_use_allowed:
        soup=BeautifulSoup(request.description_html or '', 'html.parser')
        products=[]
        def product_nodes(node):
            if isinstance(node,list):
                for child in node:product_nodes(child)
            elif isinstance(node,dict):
                types=node.get('@type',[]);types=[types] if isinstance(types,str) else types
                if 'Product' in types:products.append(node)
                if '@graph' in node:product_nodes(node['@graph'])
        for script in soup.select('script[type="application/ld+json"]')[:12]:
            try:product_nodes(json.loads(script.string or script.get_text()))
            except (ValueError,TypeError):continue
        selected=products if len(products)==1 else [x for x in products if x.get('url')==request.product_url]
        for node in selected[:1]:
            for key,label in (('material','materials'),('ingredients','ingredients')):
                value=node.get(key)
                if isinstance(value,list):value=', '.join(x for x in value if isinstance(x,str))
                add(label,value,'jsonld',f'jsonld.Product.{key}')
            props=node.get('additionalProperty') or []
            if isinstance(props,dict):props=[props]
            for index,prop in enumerate(props[:100]):
                if isinstance(prop,dict):add(prop.get('name',''),prop.get('value'),'jsonld',f'jsonld.Product.additionalProperty[{index}]')
        for node in soup.select('script,style,nav,footer,aside,iframe'):node.decompose()
        for index,tr in enumerate(soup.select('tr')[:200]):
            cells=tr.find_all(['th','td'],recursive=False)
            if len(cells)%2==0:
                for pair in range(0,len(cells),2):add(cells[pair].get_text(' ',strip=True),cells[pair+1].get_text(' ',strip=True),'html_text',f'description.tr[{index}].cells[{pair}:{pair+2}]')
        for index,dt in enumerate(soup.select('dt')[:100]):
            dd=dt.find_next_sibling('dd')
            if dd:add(dt.get_text(' ',strip=True),dd.get_text(' ',strip=True),'html_text',f'description.dt[{index}]')
        text=(soup.get_text('\n',strip=True)+'\n'+(request.description_text or ''))[:200000]
        lines=[line.strip() for line in text.splitlines() if line.strip()]
        for index,line in enumerate(lines):
            match=labelled_value(line)
            if match:add(match[0],match[1],'html_text',f'description.line[{index}]')
            elif labelled_field(line) and index+1<len(lines) and not labelled_field(lines[index+1]):
                add(line,lines[index+1],'html_text',f'description.lines[{index}:{index+2}]')
    output['missing_fields']=[key for key,field in output['fields'].items() if field['status']=='not_reported']
    output['components']=component_list(output)
    return output


def _enrich_one(request,cfg=None):
    output=extract_text(request)
    if not output['missing_fields']:
        output['ocr_status']='skipped_text_available';return output
    if not cfg or cfg.get('enabled') is not True:
        output['ocr_status']='disabled';return output
    from services.collector.food_evidence.ocr import DetailOCRRequest,collect_detail_images
    image_request=DetailOCRRequest(request.source,request.product_url,request.observed_at,request.detail_image_urls,
        request.image_use_allowed,tuple(output['missing_fields']))
    try:ocr=collect_detail_images(image_request,cfg)
    except (ImportError,OSError,ValueError,RuntimeError,KeyError,RequestException) as exc:
        output.update(ocr_status='failed',ocr_failure_reason=str(exc) if isinstance(exc,ValueError) else type(exc).__name__);return output
    output.update(ocr_status=ocr.get('status'),OCR_performed=ocr.get('OCR_performed',False),
        ocr_cache_hit=ocr.get('cache_hit',False),ocr_raw=ocr.get('raw',''),ocr_records=ocr.get('records',[]),
        ocr_failure_reason=ocr.get('failure_reason'),ocr_call_success='records' in ocr)
    if ocr.get('source_image_url'):
        output['source_references'].append({'image_url':ocr['source_image_url'],'image_sha256':ocr['image_sha256'],
            'engine':ocr.get('engine'),'validation_status':'ocr_unverified','scan_complete':ocr.get('scan_complete',False)})
    for index,record in enumerate(ocr.get('records',[])):
        if record.get('confidence',0)<0.5:continue
        match=labelled_value(record.get('text',''))
        if not match:continue
        label,value=match
        key=labelled_field(label)
        if key not in output['missing_fields'] or placeholder(value):continue
        field=output['fields'][key];raw=value.strip()
        if raw in field['raw']:continue
        field['raw'].append(raw);field['normalized'].extend(normalized(raw,key));field['status']='ocr_unverified' if len(field['raw'])==1 else 'conflicting'
        field['sources'].append({'source_url':ocr['source_image_url'],'source_field':f'OCR.records[{index}]','method':'ocr','confidence':record['confidence'],'label':label,'raw':raw,'image_sha256':ocr['image_sha256']})
        output['ocr_extraction_success']=True
    output['missing_fields']=[key for key,field in output['fields'].items() if field['status']=='not_reported']
    if output['ocr_call_success'] and not output['ocr_extraction_success']:
        output['ocr_failure_reason']='no_supported_field_label_and_value_in_OCR'
    output['components']=component_list(output)
    return output



def enrich_product(request,cfg=None):
    """At most two allowed detail images; text first, shared pixel/model cache."""
    urls=list(dict.fromkeys(request.detail_image_urls))
    limit=min(2,max(1,int((cfg or {}).get('max_detail_images',2))))
    selected=urls[:1]+(urls[-1:] if len(urls)>1 and limit==2 else [])
    output=None;attempts=[];images=[]
    for image_index,url in enumerate(selected or [None]):
        item=_enrich_one(replace(request,detail_image_urls=(url,) if url else ()),cfg)
        images.append({'image_url':url,'raw':item.get('ocr_raw',''),'records':copy.deepcopy(item.get('ocr_records',[])),
            'image_sha256':next((r['image_sha256'] for r in item['source_references']),None)})
        for field in item['fields'].values():
            for source in field['sources']:
                if source['method']=='ocr':source['source_field']=source['source_field'].replace('OCR.records[',f'OCR.images[{image_index}].records[')
        attempts.append({'image_url':url,'status':item.get('ocr_status'),
            'failure_reason':item.get('ocr_failure_reason'),'OCR_performed':item.get('OCR_performed',False),
            'cache_hit':item.get('ocr_cache_hit',False),'character_records':len(item.get('ocr_records',[])),
            'field_extraction_success':item.get('ocr_extraction_success',False)})
        if output is None:output=item
        else:
            for key,field in item['fields'].items():
                current=output['fields'][key]
                if current['status']=='source_reported':continue
                for raw in field['raw']:
                    if raw not in current['raw']:
                        current['raw'].append(raw);current['normalized'].extend(normalized(raw,key))
                        current['sources'].extend(x for x in field['sources'] if x['raw']==raw)
                if current['raw']:current['status']='ocr_unverified' if len(current['raw'])==1 else 'conflicting'
            output['source_references'].extend(x for x in item['source_references'] if x not in output['source_references'])
            output['ocr_raw']='\n'.join(x for x in (output.get('ocr_raw'),item.get('ocr_raw')) if x)
            output.setdefault('ocr_records',[]).extend(item.get('ocr_records',[]))
            for flag in ('ocr_call_success','OCR_performed','ocr_extraction_success'):output[flag]=output.get(flag,False) or item.get(flag,False)
        if item.get('ocr_status') in ('skipped_text_available','disabled','image_permission_required'):break
    output['ocr_attempts']=attempts
    output['ocr_images']=images
    if output.get('ocr_extraction_success'):
        output['ocr_status']='extracted_unverified';output['ocr_failure_reason']=None
    elif output.get('ocr_call_success'):
        output['ocr_status']='ocr_executed_no_supported_fields'
        output['ocr_failure_reason']='no_supported_field_label_and_value_in_OCR'
    output['ocr_cache_hit']=all(a['cache_hit'] for a in attempts if a['character_records']) if any(a['character_records'] for a in attempts) else False
    output['missing_fields']=[key for key,value in output['fields'].items() if value['status']=='not_reported']
    output['components']=component_list(output)
    return output

def component_list(evidence):
    result=[]
    for key,field in evidence.get('fields',{}).items():
        if key not in ('materials','ingredients','functional_ingredients'):continue
        for value in field['normalized']:
            result.append({**copy.deepcopy(value),'field_kind':key,'raw':list(field['raw']),
                'sources':copy.deepcopy(field['sources']),'status':field['status'],
                'requires_review':value['requires_review'] or field['status']!='source_reported'})
    return result


def merge_food_evidence(existing,product_evidence):
    """Map the same component fields into the existing food Extension contract.

    Ingredients never become an explicit allergen declaration. Cross-contact
    codes remain separate and its raw notice fits the existing backend field.
    """
    output=copy.deepcopy(existing);fields=product_evidence.get('fields',{})
    ingredients=fields.get('ingredients') or {}
    if ingredients.get('raw'):
        output['ingredients_raw']='\n'.join(ingredients['raw'])[:4000]
        output['ingredients_normalized']=[{'name':x['name'][:200],'percentage':x.get('percentage')} for x in ingredients.get('normalized',[])][:120]
    for key,target in (('allergens','allergen_notice_raw'),('cross_contact','cross_contact_raw')):
        field=fields.get(key) or {}
        if field.get('raw'):output[target]='\n'.join(field['raw'])[:1000]
        codes=[x['code'] for x in field.get('normalized',[]) if x.get('code') and not x.get('negative_claim_unverified')]
        if codes:
            dest='allergens_declared' if key=='allergens' else 'allergens_possible_cross_contact'
            output[dest]=sorted(set((output.get(dest) or [])+codes))
    statuses={field['status'] for key,field in fields.items() if key in ('ingredients','allergens','cross_contact') and field['raw']}
    if 'conflicting' in statuses:output['allergen_status']='conflicting'
    elif 'ocr_unverified' in statuses:output['allergen_status']='ocr_unverified'
    elif any(v.get('negative_claim_unverified') for v in (fields.get('allergens') or {}).get('normalized',[])) or output.get('allergen_status')=='negative_claim_unverified':output['allergen_status']='negative_claim_unverified'
    elif (fields.get('allergens') or {}).get('raw'):output['allergen_status']='reported'
    output['safe_to_consume']=None
    return output


def avoidance_matches(evidence,terms):
    """Candidate matches for future search integration; missing information is unknown."""
    wanted={str(x).strip().casefold() for x in terms};matches=[]
    wanted.update(MATERIALS.get(x,x) for x in list(wanted))
    from services.collector.food_evidence.extract import ALIASES
    wanted.update(ALIASES.get(x,x) for x in list(wanted))
    for key,field in evidence.get('fields',{}).items():
        for value in field.get('normalized',[]):
            if value['name'].casefold() in wanted or (value.get('code') or '').casefold() in wanted or ALIASES.get(value['name'].casefold()) in wanted:
                matches.append({'field':key,'source_term':value['name'],'status':field['status'],'requires_review':field['status']!='source_reported' or value['requires_review']})
    return {'matches':matches,'no_match_means_absent':False,'safe_to_use':None,'missing_fields':evidence.get('missing_fields',[])}
