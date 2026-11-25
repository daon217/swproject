"""Bounded documented endpoints. Pagination never follows provider-supplied URLs."""
import os
import re
from urllib.parse import quote
from .http import ProviderError
from .vendor.ebay_oauth import EbayOAuth
from . import normalize
from . import serper

YES24='https://apis.yes24.com/v1/goods/'
SHOPPING='https://www.searchapi.io/api/v1/search'
EBAY='https://api.ebay.com/buy/browse/v1/'

def credential(name):
    value=os.environ.get(name,'')
    if not value or any(ord(c)<33 or ord(c)>126 for c in value):raise ProviderError('credentials_missing_or_invalid')
    return value

def objects(value,maximum):
    if not isinstance(value,list) or len(value)>maximum or any(not isinstance(v,dict) for v in value):
        raise ProviderError('provider_rows_schema_invalid')
    return value

class Adapter:
    def __init__(self,cfg,http,credential_reader=credential,*,retry_auth=True):
        self.cfg=cfg;self.http=http;self.oauth=None;self.credential=credential_reader
        self.retry_auth=retry_auth

    def ebay_get(self,url,params=None):
        rejected=sum(e.get('status')==401 and e.get('task_id')==self.http.task_id
                     for e in self.http.state.get('requests',[]))
        if rejected>=2:
            self.http.state['hold']='repeated_401_review_required';self.http.save()
            raise ProviderError('provider_access_refused',401)
        if self.oauth is None:self.oauth=EbayOAuth(self.credential('EBAY_CLIENT_ID'),self.credential('EBAY_CLIENT_SECRET'),self.http)
        token=self.oauth._get_access_token()
        for attempt in range(2):
            try:
                return self.http.get_json(url,params=params or {},headers={'Authorization':'Bearer '+token,
                    'X-EBAY-C-MARKETPLACE-ID':self.cfg.get('marketplace_id','EBAY_US')})
            except ProviderError as exc:
                if exc.http_status!=401:raise
                if not self.retry_auth:raise
                self.oauth._invalidate_token(token)
                rejected+=1
                if attempt or rejected>=2:
                    self.http.state['hold']='repeated_401_review_required';self.http.save();raise
                token=self.oauth._get_access_token()

    def search(self,query,page):
        source=self.cfg['source'];size=self.cfg['page_size']
        if source==serper.SOURCE:
            if page!=1:raise ProviderError('Serper_probe_one_page_only')
            body=self.http.post_json(serper.ENDPOINT,
                headers={'X-API-KEY':self.credential('SERPER_API_KEY'),'Content-Type':'application/json'},
                json={'q':query,'gl':self.cfg.get('gl','us'),'hl':self.cfg.get('hl','en')})
            if 'shopping' not in body:raise ProviderError('Serper_response_schema_invalid')
            return objects(body['shopping'],1000),False
        if source=='yes24_api':
            body=self.http.get_json(YES24+'itemList',headers={'X-Api-Key':self.credential('YES24_API_KEY')},
                                    params={'query':query,'page':page,'pageSize':size})
            if body.get('success') is not True or not isinstance(body.get('data'),dict):raise ProviderError('YES24_response_invalid')
            data=body['data'];rows=objects(data.get('items'),size)
            if data.get('currentPage') is not None and data['currentPage']!=page:raise ProviderError('YES24_page_mismatch')
            return rows,len(rows)==size
        if source=='searchapi_google_shopping':
            body=self.http.get_json(SHOPPING,headers={'Authorization':'Bearer '+self.credential('SEARCHAPI_API_KEY')},
                                    params={'engine':'google_shopping','q':query,'page':page,
                                            'gl':self.cfg.get('gl','us'),'hl':self.cfg.get('hl','en')})
            rows=objects(body.get('shopping_results',[]),1000)
            # Google Shopping has no documented page-size control. Normalize all
            # returned rows in RAM; do not invent a num= parameter or count ads.
            if 'shopping_results' not in body and not body.get('search_information',{}).get('organic_results_state'):
                raise ProviderError('Shopping_response_schema_invalid')
            return rows,bool(body.get('pagination',{}).get('next'))
        offset=(page-1)*size
        if offset>=10000:raise ProviderError('eBay_result_window_exceeded')
        body=self.ebay_get(EBAY+'item_summary/search',{'q':query,'limit':size,'offset':offset,'filter':'buyingOptions:{FIXED_PRICE}'})
        rows=objects(body.get('itemSummaries',[]),size)
        if 'itemSummaries' not in body and body.get('total')!=0:raise ProviderError('eBay_response_schema_invalid')
        return rows,offset+len(rows)<body.get('total',0) and bool(rows)

    def detail(self,identity):
        if self.cfg['source']=='yes24_api':
            body=self.http.get_json(YES24+'itemDetail',headers={'X-Api-Key':self.credential('YES24_API_KEY')},
                                    params={'searchType':'ItemId','query':identity,'detail':'N'})
            if body.get('success') is not True or not isinstance(body.get('data'),dict):raise ProviderError('YES24_detail_schema_invalid')
            rows=objects(body['data'].get('items'),1)
            if len(rows)!=1 or str(rows[0].get('itemId'))!=identity:raise ProviderError('detail_identity_mismatch')
            return rows[0]
        # Retrieve fresh price, condition and estimated availability together.
        # Never merge old search stock into an incomplete detail response.
        if not isinstance(identity,str) or not re.fullmatch(r'v1\|\d+\|\d+',identity):
            raise ProviderError('native_identity_invalid')
        body=self.ebay_get(EBAY+'item/'+quote(identity,safe=''))
        if body.get('itemId')!=identity:raise ProviderError('detail_identity_mismatch')
        return body

    def normalize(self,row,at):
        return {'yes24_api':normalize.yes24,'ebay_browse':normalize.ebay,
                'searchapi_google_shopping':normalize.shopping,'serper_google_shopping':serper.normalize}[self.cfg['source']](row,at,self.cfg)
