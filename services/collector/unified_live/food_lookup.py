"""Exact-GTIN food evidence adapter; community data is never manufacturer certification."""
import argparse
from datetime import timedelta
from decimal import Decimal
import json,os,re
from pathlib import Path
from urllib.parse import urlencode
from services.collector.domeggook_live.domeggook_delivery import utcnow,atomic
from .food import evidence,normalized_terms
from .transport import SafeHTTP,Wait

REFERENCE='https://openfoodfacts.github.io/openfoodfacts-server/api/'
FIELDS='code,product_name,brands,countries_tags,ingredients_text,allergens,allergens_tags,traces,traces_tags,last_modified_t'

def policy_ready(contact,reference,ack):
    return bool(isinstance(contact,str) and len(contact)<=254 and contact.isascii() and
        re.fullmatch(r'[^\s@()]+@[^\s@()]+\.[^\s@()]+',contact) and isinstance(reference,str) and 0<len(reference)<=1024 and ack)

def gtin(value):
    if not isinstance(value,str) or len(value) not in (8,12,13,14) or not value.isascii() or not value.isdigit():raise ValueError('explicit_valid_GTIN_required')
    total=sum(int(c)*(3 if i%2==0 else 1) for i,c in enumerate(reversed(value[:-1])))
    if (10-total%10)%10!=int(value[-1]):raise ValueError('GTIN_check_digit_failed')
    return value.zfill(14)

def record_evidence(record,expected,at):
    if not isinstance(record,dict) or gtin(str(record.get('code','')))!=gtin(expected):raise ValueError('food_GTIN_mismatch')
    raw_allergens=record.get('allergens') if isinstance(record.get('allergens'),str) else None
    raw_traces=record.get('traces') if isinstance(record.get('traces'),str) else None
    def label_text(value):return re.sub(r'\b[a-z]{2}:','',value) if value else None
    fields={'name':record.get('product_name') or '', 'category':'food','ingredients':record.get('ingredients_text'),
        'allergens':label_text(raw_allergens),'cross_contact':label_text(raw_traces),'brand':record.get('brands')}
    source_url='https://world.openfoodfacts.org/product/'+expected
    result=evidence(fields,source='openfoodfacts',url=source_url,at=at)
    result.update(gtin=gtin(expected),requires_review=True,confidence='community_transcription_unverified',
        evidence_kind='community_dataset_not_manufacturer_certification',license='ODbL/DbCL; images_CC_BY_SA_separate',
        policy_reference=REFERENCE,source_last_modified_at=record.get('last_modified_t'),
        allergens_inferred_or_aggregated_tags=record.get('allergens_tags') if isinstance(record.get('allergens_tags'),list) else None,
        cross_contact_unverified_tags=record.get('traces_tags') if isinstance(record.get('traces_tags'),list) else None,
        raw_allergen_label=raw_allergens,raw_cross_contact_label=raw_traces,API_contract_ready=False,is_synthetic=False)
    # Tags may be inferred by the upstream API; they are not promoted to declared-on-label evidence.
    if not raw_allergens:result.update(allergens_declared=None,allergen_status='not_reported')
    return result

def attach(product,record,at):
    # A marketplace listing ID or a similar product name is never a food identity join key.
    expected=product.get('gtin')
    if expected is None:raise ValueError('explicit_product_GTIN_required_no_name_join')
    return record_evidence(record,expected,at)

class FoodHTTP(SafeHTTP):
    def __init__(self,barcode,root,contact,usage_reference,license_acknowledged,clock=utcnow):
        gtin(barcode)
        self.target='https://world.openfoodfacts.org/api/v3.6/product/'+barcode+'.json?'+urlencode({'fields':FIELDS})
        self.contact=contact;self.authorized=policy_ready(contact,usage_reference,license_acknowledged)
        self.expires=clock()+timedelta(minutes=10)
        cfg={'source':'html_food_lookup','base_url':'https://world.openfoodfacts.org/','enabled':True,
            'requests_per_hour':6,'requests_per_24h':12,'request_interval_seconds':5}
        super().__init__(cfg,root,clock)
    def permitted(self,target):return self.authorized and target==self.target and len(self.state['requests'])<1 and self.clock()<self.expires
    def user_agent(self):return 'KkulpickEvidence/1.0 ('+self.contact+')'
    def lookup(self,barcode):
        code,text,_=self._get(self.target)
        if code!=200:raise Wait('food_API_unavailable',hold=True)
        data=json.loads(text,parse_float=Decimal)
        if data.get('status') not in (None,1,'success','success_with_warnings') or not isinstance(data.get('product'),dict):raise ValueError('food_record_not_found')
        return record_evidence(data.get('product'),barcode,self.clock().isoformat())

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--gtin',required=True);p.add_argument('--state-dir',required=True);p.add_argument('--usage-reference')
    p.add_argument('--license-acknowledged',action='store_true');mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--lookup',action='store_true');mode.add_argument('--plan',action='store_true');p.add_argument('--report')
    a=p.parse_args(argv)
    try:
        gtin(a.gtin);contact=os.environ.get('OPENFOODFACTS_CONTACT_EMAIL','')
        ready=policy_ready(contact,a.usage_reference,a.license_acknowledged)
        report={'provider':'openfoodfacts','ready':ready,'policy_reference':REFERENCE,'usage_registration_and_contact_required':True,
            'community_data_not_manufacturer_certification':True,'operational_DB_write_allowed':False,'HTTP_requests_this_command':0}
        if not a.lookup or not ready:print(json.dumps(report));return 0 if ready else 1
        http=FoodHTTP(a.gtin,Path(a.state_dir),contact,a.usage_reference,a.license_acknowledged)
        try:
            result=http.lookup(a.gtin)
            report.update(HTTP_requests_this_command=len(http.state['requests']),ingredients_present=bool(result['ingredients_raw']),
                allergens_declared_count=len(result['allergens_declared'] or []),requires_review=True,safe_to_consume=None,
                raw_evidence_saved=False,status='lookup_completed')
        finally:http.close()
        if a.report:atomic(Path(a.report),report)
        print(json.dumps(report));return 0
    except Exception:
        print(json.dumps({'provider':'openfoodfacts','status':'blocked','reason':'policy_identity_or_API_review_required','raw_evidence_saved':False}));return 2

if __name__=='__main__':raise SystemExit(main())
