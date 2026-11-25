import base64, glob, os, sys, time, uuid, httpx
H={'Authorization':'Bearer '+os.environ['VISION_SERVICE_TOKEN']}
imgs=[base64.b64encode(open(p,'rb').read()).decode() for p in sorted(glob.glob('/img/*.jpg'))]
c=httpx.Client(base_url='http://vision-api:8000',headers=H,timeout=120)
start,count=int(sys.argv[1]),int(sys.argv[2])
for k in range(start,start+count):
    b=imgs[k%len(imgs)]; sid=uuid.uuid4().hex; t=time.time()
    c.post('/api/v1/vision/init',json={'session_id':sid,'product_name':None,'first_frame_image':b}).raise_for_status()
    c.post('/api/v1/vision/frame',json={'session_id':sid,'frame_index':0,'is_last_frame':True,'image':b}).raise_for_status()
    while True:
        v=c.get(f'/api/v1/vision/status/{sid}').json()
        if v['status']!='processing' or time.time()-t>300: break
        time.sleep(0.3)
    print(f"#{k} img{k%len(imgs)} {v['status']} {time.time()-t:.1f}s ing={len(v.get('ingredients',[]))} name={v.get('product_name')}",flush=True)
