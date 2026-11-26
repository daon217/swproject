"""Disposable real backend -> worker -> recommendation check; optional real OCR fixture.
Run only against your development stack. Creates a uniquely named test member/job.
"""
import argparse,base64,json,secrets,time,sys
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
def settings(path):return dict(l.split('=',1) for l in path.read_text().splitlines() if '=' in l and not l.startswith('#'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--image');p.add_argument('--collector',action='store_true');a=p.parse_args()
    api=settings(ROOT/'services/api/.env');work=settings(ROOT/'infra/workspace/.env')
    base='http://127.0.0.1:'+api.get('API_PORT','8000')
    def call(path,body=None,token=None,server=base):
        req=Request(server+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
        with urlopen(req,timeout=30) as response:return json.load(response)
    uid='it'+secrets.token_hex(5);password=secrets.token_urlsafe(24)
    call('/v2/auth/signup',{'login_id':uid,'password':password,'password_confirmation':password,'consent_version':'v1','consent_accepted':True})
    token=call('/v2/auth/login',{'login_id':uid,'password':password})['data']['token']
    # 중고 상품은 기본 설정(중고 포함 꺼짐)에서 비슷한 상품도 중고뿐이면 추천이 비는 게 정상이고,
    # 관련도 기준·보고 있는 판매처 제외 때문에 비슷한 상품이 없는 상품도 빈 결과가 정상이다.
    # 그래서 새 상품 몇 개를 차례로 분석해 추천이 나오는 경우가 하나라도 있는지 확인한다.
    offers=[o for o in call('/v2/offers?selected_domain=product')['items'] if o.get('condition')!='used'][:5]
    try:
        assert offers,'no new product offers in catalog; run py tools/workspace.py seed'
        for offer in offers:
            job=call('/analyses',{'page_url':offer['current_url'],'page_session_id':'integration','page_revision':1,
                'request_key':secrets.token_hex(16),'selected_domain':'product'},token)['data']['analysis_id']
            for _ in range(90):
                result=call('/analyses/'+job,token=token)['data']
                if result['state'] in ('completed','failed'):break
                time.sleep(1)
            assert result['state']=='completed',result
            if result['sections'][0]['items']:break
        assert result['sections'][0]['items'],result
        assert result['sections'][0]['items'][0]['reason']!='분석 작업자가 선택한 상품'
        print('PASS actual API claim -> catalog -> recommendation -> durable result')
        if a.collector:
            from services.collector.domeggook_live.fixture_data import row,config
            from services.collector.domeggook_live.domeggook_backend import prepare_observation,HTTPBackendTransport
            cfg=config(base);transport=HTTPBackendTransport(base,api['COLLECTOR_TOKEN'],approved_loopback_test=True)
            run=str(uuid4());variant='TEST-'+secrets.token_hex(6);start=datetime.now(timezone.utc)-timedelta(seconds=10)
            def deliver(offset,price,url_suffix='original',quantity=10):
                item=row((start+timedelta(seconds=offset)).isoformat(),price,quantity)
                item['variant_key']=variant;item['identity_evidence']['variant_key']['value']=variant
                item['product_url']='https://store.example.test/TEST-KKULPICK-001/'+url_suffix
                body=prepare_observation(item,cfg,selected_domain='product',condition='new')
                return transport('/internal/v2/crawl-runs/'+run+'/observations',body)
            try:
                status,first=deliver(0,1000);assert status==201 and first['state']=='applied',first
                status,updated=deliver(2,900,'changed');assert status==201 and updated['offer_id']==first['offer_id'],updated
                status,duplicate=deliver(2,900,'changed');assert status==200 and duplicate['observation_id']==updated['observation_id'],duplicate
                _,stale=deliver(1,500);assert stale['change_kind']=='stale',stale
                rows=call('/v2/offers?selected_domain=product&source=domeggook_test&limit=100')['items']
                current=next(o for o in rows if o['offer_id']==first['offer_id'])
                assert float(current['price'])==900 and current['current_url'].endswith('/changed'),current
                _,ended=deliver(3,900,'changed',0);assert ended['offer_id']==first['offer_id'],ended
                rows=call('/v2/offers?selected_domain=product&source=domeggook_test&limit=100')['items']
                assert not any(o['offer_id']==first['offer_id'] for o in rows)
                print('PASS collector mapper -> real DB create, price/URL update, duplicate, stale, out-of-stock hiding')
            finally:transport.close()
        if a.image:
            sid='ci-'+secrets.token_hex(12);frame=base64.b64encode(Path(a.image).read_bytes()).decode()
            def vision(path,body=None):return call('/api/v1/vision/'+path,body,work['WORKSPACE_TOKEN'],'http://127.0.0.1:8100')
            vision('init',{'session_id':sid,'product_name':'성분표 검증용 상품'})
            vision('frame',{'session_id':sid,'frame_index':0,'is_last_frame':True,'image':frame})
            for _ in range(300):
                v=vision('status/'+sid)
                if v['status']!='processing':break
                time.sleep(1)
            assert v['status']=='success' and v['ingredients'],v
            assert any('우유' in i for i in v['ingredients']),v
            print('PASS actual Vision 8100 -> Redis -> PaddleOCR CPU -> Korean ingredients')
    finally:
        call('/v2/me/withdrawal',{'current_password':password},token)

if __name__=='__main__':main()
