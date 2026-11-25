"""Source evidence only; absence or a label claim never establishes food safety."""
import hashlib
import re
import sys
from pathlib import Path


def legacy_refiner():
    # The retained module imports product_refinement as a top-level package.
    # Resolve only the bundled project directory, never a user's external project.
    bundled = Path(__file__).resolve().parents[1]/'real_feed_collectors'
    if str(bundled) not in sys.path:
        sys.path.append(str(bundled))
    from services.collector.real_feed_collectors.detail_enrichment_v1.clean import refine
    return refine


ALIASES = {'우유':'milk','milk':'milk','대두':'soy','soy':'soy','soybean':'soy',
           '밀':'wheat','wheat':'wheat','알류':'egg','계란':'egg','달걀':'egg','egg':'egg','eggs':'egg',
           '땅콩':'peanut','peanut':'peanut','peanuts':'peanut','새우':'shrimp','shrimp':'shrimp',
           '게':'crab','crab':'crab','메밀':'buckwheat','buckwheat':'buckwheat','호두':'walnut','walnut':'walnut',
           '잣':'pine_nut','복숭아':'peach','peach':'peach','토마토':'tomato','tomato':'tomato',
           '오징어':'squid','고등어':'mackerel','조개류':'shellfish','shellfish':'shellfish',
           '돼지고기':'pork','쇠고기':'beef','소고기':'beef','닭고기':'chicken','아황산류':'sulfites'}


from .allergens import find_allergens

# allergens.py 정규 이름 -> 기존 계약 코드(영문). ALIASES는 하위 호환용으로 남긴다.
CODES = {'알류':'egg','우유':'milk','메밀':'buckwheat','땅콩':'peanut','대두':'soy','밀':'wheat',
         '고등어':'mackerel','게':'crab','새우':'shrimp','돼지고기':'pork','복숭아':'peach','토마토':'tomato',
         '아황산류':'sulfites','호두':'walnut','닭고기':'chicken','쇠고기':'beef','오징어':'squid',
         '조개류':'shellfish','잣':'pine_nut','참깨*':'sesame','견과류*':'tree_nut','생선*':'fish'}


def terms(text):
    return [token.strip() for token in re.split(r'[,;、\n]',text) if token.strip()]


def allergen_codes(text):
    """-> (codes, unmapped) 토큰 순서 유지. 한·영·중·일 동의어 사전(allergens.py)으로 대조, 못 찾은 토큰은 버리지 않고 unmapped."""
    codes=[];unmapped=[]
    for token in terms(text or ''):
        contains,trace=find_allergens(token)
        hit=[CODES[c] for c in CODES if c in contains|trace]
        if hit:codes+=hit
        else:unmapped.append(token)
    return list(dict.fromkeys(codes)),list(dict.fromkeys(unmapped))


def extract(text, *, source, source_url, observed_at, name='', category='', source_field='description'):
    if text is not None and (not isinstance(text,str) or len(text.encode('utf-8'))>200000):
        raise ValueError('bounded_text_required')
    raw=text or ''
    result={'source':source,'source_url':source_url,'observed_at':observed_at,'source_field':source_field,
            'raw':None,'raw_sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'ingredients':None,'allergens_declared':None,'may_contain':None,
            'unmapped_allergen_terms':[], 'allergen_status':'not_reported',
            'safe_to_consume':None,'safety_assessment':'not_assessed',
            'API_contract_ready':False,'persisted':False}
    refined=legacy_refiner()(raw,name,category,source_url,source_field)
    if refined['profile']!='food':
        result['status']='not_food';return result
    result.update(status='food_evidence',raw=raw,implementation=refined['shared_implementation'])
    evidence=refined['specifications'] or {}
    def values(key):
        return [re.split(r'[:：]',v,maxsplit=1)[-1].strip() for v in evidence.get(key,[])]
    ingredients=values('ingredients')
    if ingredients:result['ingredients']=list(dict.fromkeys(t for value in ingredients for t in terms(value)))
    labels=values('allergens')
    possible=[]
    for line in refined['plain_text'].splitlines():
        match=re.search(r'(?:may contain|혼입 가능(?:성)?|같은 (?:제조 )?시설)\s*[:：]?\s*(.+)',line,re.I)
        if match:possible.append(match[1].strip())
    if possible:result['may_contain']=list(dict.fromkeys(possible))
    if labels:
        negative=any(re.search(r'없음|해당\s*없|무첨가|미함유|\b(?:none|free[- ]from|no allergens?)\b',v,re.I) for v in labels)
        result['allergen_status']='negative_claim_unverified' if negative else 'reported'
        if not negative:
            declared,unmapped=allergen_codes('\n'.join(labels))
            result['allergens_declared']=declared
            result['unmapped_allergen_terms']=unmapped
    return result
