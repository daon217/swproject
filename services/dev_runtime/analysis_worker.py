"""Claim -> catalog or Vision(8100) -> recommender -> backend result.

No arbitrary page URL is fetched. Only configured internal services receive requests.
Jobs, image access and completion all use the backend's authenticated lease protocol.
"""
import base64
import logging
import os
import time
from urllib.parse import urlsplit
import httpx

log=logging.getLogger('analysis-worker')

def context_url(value):
    u=urlsplit(value)
    return (u.hostname or '').lower(),u.path,u.query

class Worker:
    def __init__(self,client=None):
        self.http=client or httpx.Client(timeout=20,follow_redirects=False,trust_env=False)
        self.api=os.getenv('API_INTERNAL_URL','http://api:8000').rstrip('/')
        self.vision=os.getenv('VISION_INTERNAL_URL','http://vision-api:8100').rstrip('/')
        self.reco=os.getenv('RECOMMENDATION_INTERNAL_URL','http://recommendation:8000').rstrip('/')
        self.auth={'Authorization':'Bearer '+os.environ['ANALYSIS_WORKER_TOKEN']}
        self.service_auth={'Authorization':'Bearer '+os.environ['WORKSPACE_TOKEN']}

    def request(self,method,path,**kwargs):
        r=self.http.request(method,self.api+path,headers=self.auth,**kwargs)
        r.raise_for_status()
        return r.json().get('data')

    def offers(self,kind):
        rows=[];after=None
        for _ in range(10):
            params={'selected_domain':kind,'limit':100,'condition':'all','availability':'available'}
            if after:params['after']=after
            r=self.http.get(self.api+'/v2/offers',params=params);r.raise_for_status()
            page=r.json();rows.extend(page['items']);after=page.get('next_cursor')
            if not after:break
        return rows

    def once(self):
        job=self.request('POST','/internal/v2/analyses/claim',json={'worker_id':'team-integration'})
        if not job:return False
        path='/internal/v2/analyses/'+job['analysis_id'];lease={'lease_token':job['lease_token']}
        try:
            groups={kind:self.offers(kind) for kind in ('product','food')}
            matches=[(kind,o) for kind,rows in groups.items() for o in rows
                     if context_url(o['current_url'])==context_url(job['page_url'])]
            kind=job.get('selected_domain') or (matches[0][0] if matches else None)
            title=matches[0][1]['name'] if matches else None
            ingredients=[]
            if job.get('image_url'):
                image=self.http.get(self.api+job['image_url'],headers=self.auth|{'X-Worker-Lease':job['lease_token']})
                image.raise_for_status()
                frame=base64.b64encode(image.content).decode()
                sid=job['analysis_id']+'-'+job['lease_token']
                try:
                    r=self.http.post(self.vision+'/api/v1/vision/init',headers=self.service_auth,json={
                        'session_id':sid,'product_name':title,'first_frame_image':frame})
                    r.raise_for_status()
                    r=self.http.post(self.vision+'/api/v1/vision/frame',headers=self.service_auth,json={
                        'session_id':sid,'frame_index':0,'is_last_frame':True,'image':frame})
                    r.raise_for_status()
                    start=time.monotonic();heartbeat=start
                    while time.monotonic()-start<90:
                        if time.monotonic()-heartbeat>15:
                            self.request('POST',path+'/heartbeat',json=lease);heartbeat=time.monotonic()
                        r=self.http.get(self.vision+'/api/v1/vision/status/'+sid,headers=self.service_auth);r.raise_for_status();v=r.json()
                        if v['status']!='processing':
                            title=title or v.get('product_name');ingredients=v.get('ingredients',[]);break
                        time.sleep(.5)
                except httpx.HTTPError:
                    if not title:raise
                    # A catalog match can still be ranked; never pretend OCR succeeded.
            if not title:
                self.request('POST',path+'/fail',json=lease|{'code':'OCR_FAILED','retryable':False});return True
            # A generic cosmetics ingredient list must not automatically classify a page as food.
            if not kind:
                self.request('POST',path+'/fail',json=lease|{'code':'INPUT_INVALID','retryable':False});return True
            r=self.http.post(self.reco+'/internal/process',headers=self.service_auth,json={
                'query':title[:1000],'selected_domain':kind,'offers':groups[kind],
                'ingredients':[str(i)[:500] for i in ingredients[:100]],
                'profile':job.get('profile',{'user_id':'worker'})})
            r.raise_for_status();result=r.json()
            self.request('POST',path+'/complete',json=lease|{
                'selected_domain':kind,'offer_ids':result['offer_ids'],
                'metadata':{'ingredients':[str(i)[:500] for i in ingredients[:100]] if kind=='food' else [],
                    'reasons':result.get('reasons',{}),'ranker':result.get('ranker',''),'warnings':result.get('warnings',[])}})
            return True
        except httpx.HTTPStatusError as error:
            if error.response.status_code not in (404,409):
                self.fail(path,lease)
            return True
        except (httpx.HTTPError,KeyError,ValueError):
            self.fail(path,lease);return True

    def fail(self,path,lease):
        try:self.request('POST',path+'/fail',json=lease|{'code':'DEPENDENCY_UNAVAILABLE','retryable':False})
        except httpx.HTTPError:pass

def main():
    logging.basicConfig(level=logging.INFO)
    worker=Worker()
    while True:
        try:
            if not worker.once():time.sleep(2)
        except httpx.HTTPError:
            log.warning('Backend unavailable; retrying in 5 seconds');time.sleep(5)

if __name__=='__main__':main()
