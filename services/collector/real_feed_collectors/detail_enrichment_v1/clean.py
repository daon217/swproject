"""Incremental cleanup adapter; delegates HTML parsing and common rules to the team."""
import hashlib,re
from product_refinement import clean as base

EXTRA_RULES={'model': '(?:모델명|model(?: number)?)\\s*[:：]\\s*[^\\n.!?]+', 'processor': '\\b(?:Intel\\s+(?:Core\\s+)?(?:i[3579][ -]?\\w+|Ultra\\s+\\d+[\\w -]*)|AMD\\s+Ryzen\\s+[\\w -]+|ARM\\s+Cortex[- ]\\w+)\\b', 'screen': '\\b\\d+(?:\\.\\d+)?[- ]?(?:inch|inches)\\s+(?:display|screen)\\b|\\d+(?:\\.\\d+)?\\s*인치', 'battery': '\\b\\d+(?:\\.\\d+)?\\s*(?:mAh|Wh)\\b', 'size': '\\b(?:size|사이즈)\\s*[:：]\\s*(?:XXS|XS|S|M|L|XL|XXL|\\d+(?:[./-]\\d+)?)\\b', 'care': '(?:세탁|washing|wash care)\\s*[:：]\\s*[^\\n.!?]+', 'ingredients': '(?:원재료|전성분|주요 성분|ingredients)\\s*[:：]\\s*[^\\n.!?]+', 'allergens': '(?:알레르기|allergens?)\\s*[:：]\\s*[^\\n.!?]+', 'expiry': '(?:소비기한|사용기한|유통기한|expiry|expiration)\\s*[:：]\\s*[^\\n.!?]+', 'storage_conditions': '(?:보관(?: 조건| 방법)?|storage(?: conditions)?)\\s*[:：]\\s*[^\\n.!?]+', 'skin_type': '(?:피부 타입|skin type)\\s*[:：]\\s*[^\\n.!?]+', 'used_condition': '(?:사용 상태|상태|condition)\\s*[:：]\\s*[^\\n.!?]+', 'defects': '(?:하자|defects?|scratches)\\s*[:：]\\s*[^\\n.!?]+', 'repair_history': '(?:수리 이력|repair history)\\s*[:：]\\s*[^\\n.!?]+', 'usage_duration': '(?:사용 기간|usage duration|used for)\\s*[:：]?\\s*[^\\n.!?]+'}
EXTRA_PROFILES={
    'electronics':{'model','processor','screen','battery'},
    'fashion':{'size','care'},
    'food':{'ingredients','allergens','volume','weight','expiry','storage_conditions'},
    'cosmetics':{'ingredients','volume','expiry','storage_conditions','skin_type'},
}
USED={'used_condition','defects','repair_history','usage_duration'}
EXTRA_RULES.update({
    'ram': r'\b(?:RAM|memory)\s*[:：]?\s*\d+\s*(?:GB|MB)\b|\b\d+\s*(?:GB|MB)\s+RAM\b',
    'storage': r'\b(?:SSD|HDD|storage)\s*[:：]?\s*\d+(?:\.\d+)?\s*(?:GB|TB)\b|\b\d+(?:\.\d+)?\s*(?:GB|TB)\s+(?:SSD|HDD)\b',
    'resolution': r'\b\d{3,5}\s*[x×]\s*\d{3,5}\s*(?:pixels?|px)?\b',
    'contents': r'(?:구성품|contents|included accessories)\s*[:：]\s*[^\n]+',
    'origin': r'(?:원산지|country of origin)\s*[:：]\s*[^\n]+',
    'usage': r'(?:사용 방법|directions|how to use)\s*[:：]\s*[^\n]+',
    'cautions': r'(?:주의사항|precautions|cautions)\s*[:：]\s*[^\n]+'
})
EXTRA_PROFILES['electronics'].update({'ram','storage','resolution','contents'})
EXTRA_PROFILES['fashion'].add('contents')
EXTRA_PROFILES['food'].add('origin')
EXTRA_PROFILES['cosmetics'].update({'usage','cautions'})
USED.add('contents')
def profile(category,name):
    text=str(category or '')+' '+str(name or '')
    if re.search(r'식품|음료|과자|\b(?:food|snack|beverage|juice|cereal)\b',text,re.I):return 'food'
    if re.search(r'화장품|크림|보습|\b(?:cosmetic|cream|moisturizer|skin care|skincare)\b',text,re.I):return 'cosmetics'
    return base.profile(category,name)

def refine(text,name,category,base_url='',source_field='description',condition=None):
    original=text or '';privacy=[]
    def redact(m):
        privacy.append({'reason':'contact_removed','sha256':hashlib.sha256(m.group().encode()).hexdigest()});return '[contact removed]'
    processed=original
    for pattern in (r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',r'(?<!\w)(?:\+\d[\d ()-]{8,}\d|0\d{1,2}[- ]\d{3,4}[- ]\d{4})(?!\w)',r'https?://(?:t\.me|wa\.me)/[^\s<]+'):
        processed=re.sub(pattern,redact,processed)
    def template(m):
        privacy.append({'reason':'unfilled_seller_template_removed','sha256':hashlib.sha256(m.group().encode()).hexdigest()});return ''
    processed=re.sub(r'(?:\bcondition\s*[:：]?\s*)?\[[^\]\n]*Ekhane[^\]\n]*\]',template,processed,flags=re.I)
    # Preserve the native URL, while mapping Cafe24 lazy attributes for the shared parser.
    processed=re.sub(r'\b(?:ec-data-src|data-original)(?=\s*=)','data-src',processed,flags=re.I)
    # Remove irrelevant plain URLs, preserving linked anchor text and image attributes.
    processed=re.sub(r'(?<!["\'=])https?://[^\s<>"\']+', '', processed) if '<' not in processed else processed
    r=base.refine(processed,name,category,base_url,source_field)
    target=profile(category,name);r['profile']=target
    allowed=(set(base.PROFILES.get(target,set()))|EXTRA_PROFILES.get(target,set())|(USED if condition=='used' else set()))
    if target in ('food','cosmetics'):allowed=EXTRA_PROFILES[target]|(USED if condition=='used' else set())
    specs={k:list(v) for k,v in (r['specifications'] or {}).items() if k in allowed or k.startswith('label:')}
    evidence=[e for e in r['specification_evidence'] if e['attribute'] in specs]
    for field,content in [('product_name',name or ''),(source_field,r['plain_text'])]:
        for key in sorted(allowed & EXTRA_RULES.keys()):
            for m in re.finditer(EXTRA_RULES[key],content,re.I):
                line=content[:m.start()].rsplit('\n',1)[-1]+content[m.start():].split('\n',1)[0]
                if re.search(r'compare|comparison|versus|비교표|모델별',line,re.I):continue
                value=m.group()
                if value not in specs.setdefault(key,[]):
                    specs[key].append(value);evidence.append({'attribute':key,'value':value,'source_field':field,'text':value,'start':m.start(),'end':m.end(),'offset_basis':'preprocessed HTML-stripped text' if field==source_field else 'original field'})
    extra_purchase=re.compile(r'\b(?:allergens?|expiry|expiration|storage|ingredients|wash|repair|defect|scratches|measurement)\b|알레르기|소비기한|보관|세탁|수리|하자',re.I)
    for line in r['plain_text'].splitlines():
        if extra_purchase.search(line) and line and not any(p['text']==line for p in r['purchase_information']):
            r['purchase_information'].append({'text':line,'source_field':source_field})
    kept=[]
    for line in (r['clean_description'] or '').splitlines():
        if re.match(r'^(?:grab (?:it|yours)|get yours|shop now|buy now|subscribe|follow us)\b',line,re.I) and not(base.TECHNICAL_FACT.search(line) or base.PURCHASE.search(line) or extra_purchase.search(line)):
            r['removed'].append({'text':line,'reason':'standalone_advertising'});continue
        if re.search(r'세심한 디자인과 편의성을 제공하여 일상을|경험을 혁신하는 테크 브랜드|합리적인 가격과 귀여운 디자인으로 일상을',line):
            r['removed'].append({'text':line,'reason':'generic_lifestyle_advertising'});continue
        kept.append(line)
    for img in r['description_images']:
        marker=img.get('alt') or '';both=marker+' '+img['url']
        if base.PROMO.search(marker) or re.search(r'banner|advert|coupon|event|/promotion/|/campaign/',both,re.I):img['role']='advertisement'
        elif re.search(r'youtube|youtu\.be|video',both,re.I):img['role']='video_thumbnail'
    r.update(clean_description='\n'.join(kept) or None,specifications=specs or None,specification_evidence=evidence,
             privacy_redactions=privacy,source_text_sha256=hashlib.sha256(original.encode()).hexdigest(),
             preprocessing_sha256=hashlib.sha256(processed.encode()).hexdigest(),
             shared_implementation='product_refinement.clean.refine; original module not patched')
    return r
