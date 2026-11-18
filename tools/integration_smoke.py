"""Disposable real backend -> worker -> recommendation check; optional real OCR fixture.
Run only against your development stack. Creates a uniquely named test member/job.
"""
import argparse,base64,json,secrets,time
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
def settings(path):return dict(l.split('=',1) for l in path.read_text().splitlines() if '=' in l and not l.startswith('#'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--image');a=p.parse_args()
    api=settings(ROOT/'services/api/.env');work=settings(ROOT/'infra/workspace/.env')
    base='http://127.0.0.1:'+api.get('API_PORT','8000')
    def call(path,body=None,token=None,server=base):
        req=Request(server+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
        with urlopen(req,timeout=30) as response:return json.load(response)
    uid='it'+secrets.token_hex(5);password=secrets.token_urlsafe(24)
    call('/v2/auth/signup',{'login_id':uid,'password':password,'password_confirmation':password,'consent_version':'v1','consent_accepted':True})
    token=call('/v2/auth/login',{'login_id':uid,'password':password})['data']['token']
    offer=call('/v2/offers?selected_domain=product')['items'][0]
    job=call('/analyses',{'page_url':offer['current_url'],'page_session_id':'integration','page_revision':1,
        'request_key':secrets.token_hex(16),'selected_domain':'product'},token)['data']['analysis_id']
    try:
        for _ in range(90):
            result=call('/analyses/'+job,token=token)['data']
            if result['state'] in ('completed','failed'):break
            time.sleep(1)
        assert result['state']=='completed',result
        assert result['sections'][0]['items'],result
        assert result['sections'][0]['items'][0]['reason']!='분석 작업자가 선택한 상품'
        print('PASS actual API claim -> catalog -> recommendation -> durable result')
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
