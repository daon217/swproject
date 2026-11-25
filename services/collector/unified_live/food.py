"""Food evidence extension; never an allergy safety classifier."""
import hashlib
import re
from decimal import Decimal
from services.collector.food_evidence.extract import extract,terms,allergen_codes

def normalized_terms(text):
    known,unknown=allergen_codes(text)
    return sorted(known),sorted(unknown)

def evidence(fields,*,source,url,at,previous_hash=None):
    lines=[fields.get('description') or '']
    for key,label in (('ingredients','원재료'),('allergens','알레르기'),('cross_contact','혼입 가능성')):
        value=fields.get(key)
        if isinstance(value,str):lines.append(label+': '+value)
    text='\n'.join(lines)
    explicit_food=any(isinstance(fields.get(k),str) and fields[k].strip() for k in ('ingredients','allergens','cross_contact'))
    category='food' if explicit_food else fields.get('category') or ''
    old=extract(text,source=source,source_url=url,observed_at=at,name=fields.get('name') or '',category=category)
    declared=old.get('allergens_declared');possible=[];unmapped=[]
    for value in old.get('may_contain') or []:
        # Do not treat facility wording as direct contains; exact aliases only.
        codes,unknown=normalized_terms(value);possible+=codes;unmapped+=unknown
    def raw_label(pattern):
        match=re.search(r'(?:'+pattern+r')\s*[:：]\s*(.+?)(?=\s*(?:원재료(?:명)?|ingredients|알레르기|allergens?|혼입 가능(?:성)?|may contain)\s*[:：]|$)',text,re.I|re.S)
        return match.group(1).strip() if match else None
    raw_allergens=fields.get('allergens') or raw_label(r'알레르기|allergens?')
    raw_cross=fields.get('cross_contact') or raw_label(r'혼입 가능(?:성)?|may contain')
    raw_ingredients=fields.get('ingredients') or raw_label(r'원재료(?:명)?|ingredients')
    raw_ingredients=raw_ingredients or next((m.group(1).strip() for line in text.splitlines() if (m:=re.match(r'\s*(?:원재료(?:명)?|ingredients)\s*[:：]\s*(.+)',line,re.I))),None)
    ingredients=[]
    invalid_percentage=False
    for token in terms(raw_ingredients or ''):
        m=re.fullmatch(r'(.+?)\s*(\d+(?:\.\d+)?)\s*%',token)
        ingredient_name=m.group(1).strip() if m else token
        ingredients.append({'name':re.sub(r'\s+',' ',ingredient_name),'percentage':m.group(2) if m else None})
        if m and Decimal(m.group(2))>100:invalid_percentage=True
    signature=hashlib.sha256(text.encode()).hexdigest()
    return {'schema_version':'food-evidence-v1','food_detected':explicit_food or old.get('status')=='food_evidence','ingredients_raw':raw_ingredients,'allergen_notice_raw':raw_allergens,'ingredients_normalized':ingredients or None,
        'allergens_declared':declared,'allergens_possible_cross_contact':sorted(set(possible)) or None,
        'cross_contact_raw':raw_cross,'allergen_status':old['allergen_status'],
        'evidence_source':source,'evidence_url':url,'verified_at':at,'raw_sha256':signature,'raw':text,
        'requires_review':invalid_percentage or old['allergen_status']!='reported' or bool(old['unmapped_allergen_terms'] or unmapped) or previous_hash not in (None,signature),
        'unmapped_terms':old['unmapped_allergen_terms']+unmapped,'confidence':'source_text_unverified',
        'changed':None if previous_hash is None else previous_hash!=signature,'safe_to_consume':None,
        'manufacturer':fields.get('manufacturer'),'brand':fields.get('brand'),'API_contract_ready':False}
