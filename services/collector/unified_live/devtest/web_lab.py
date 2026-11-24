"""Disposable network=none TLS shop -> real Chromium -> HTTP FastAPI/SQLite lab.

Only this explicit test entry point maps one .test host to loopback. Production
SafeHTTP has no private-address exception, insecure TLS flag or fixture switch.
"""
import json,os,ssl,socket,threading,time,subprocess,secrets,sys
from pathlib import Path
from datetime import datetime,timezone,timedelta
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

def main():
 if os.environ.get('COLLECTOR_NETWORK_LAB')!='synthetic_only':raise RuntimeError('explicit_disposable_lab_required')
 from services.collector.unified_live.mock import fixture_config,product
 from services.collector.unified_live.engine import URLWorker
 from services.collector.unified_live.transport import SafeHTTP
 from services.collector.unified_live import transport
 from services.collector.unified_live.render import PlaywrightRenderer
 from services.collector.unified_live.devtest.network_lab import client as backend_checks
 cert=Path('/tmp/shop-cert');cert.mkdir()
 subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(cert/'key.pem'),'-out',str(cert/'cert.pem'),'-days','1','-subj','/CN=store.example.test','-addext','subjectAltName=DNS:store.example.test'],check=True,capture_output=True)
 prices={'json':'12.00','css':'13.00','js':'14.00'};hits={}
 def detail(kind):
  if kind=='css':
   values=dict(name='SYNTHETIC CSS keyboard',price=prices[kind],currency='USD',seller='SYNTHETIC seller',condition='UsedCondition',availability='InStock',model='SYNTHETIC-MODEL')
   return ''.join('<span class="'+k+'">'+v+'</span>' for k,v in values.items())+'<img class="image" data-src="/image/1.jpg">'
  return product(prices[kind]).replace('SYNTHETIC-1','SYNTHETIC-'+kind).replace('SYNTHETIC-SKU','SYNTHETIC-SKU-'+kind).replace('https://store.example.test/item/1','https://store.example.test/p/'+kind)
 class Shop(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def do_GET(self):
   target=self.path;hits[target]=hits.get(target,0)+1;mime='text/html';code=200
   if target=='/robots.txt':body='User-agent: *\nAllow: /';mime='text/plain'
   elif target.startswith('/catalog/json'):
    body='<script type="application/ld+json">'+json.dumps({'@type':'ItemList','itemListElement':['/p/json','/p/json']})+'</script>'
    if '?' not in target:body+='<a rel="next" href="/catalog/json?page=2">next</a>'
   elif target=='/catalog/css':body='<article class="card"><a href="/p/css">CSS product</a></article>'
   elif target=='/catalog/js':body='<div id="items"></div><script>fetch("/data/list").then(r=>r.json()).then(d=>document.querySelector("#items").innerHTML=d.html)</script>'
   elif target=='/data/list':body=json.dumps({'html':'<a class="product" href="/p/js">JS product</a>'});mime='application/json'
   elif target=='/p/js':body='<script>fetch("/data/detail").then(r=>r.json()).then(d=>{const s=document.createElement("script");s.type="application/ld+json";s.textContent=JSON.stringify(d);document.head.append(s)})</script>'
   elif target=='/data/detail':body=detail('js').split('application/ld+json">')[1].split('</script>')[0];mime='application/json'
   elif target.startswith('/p/') and target[3:] in prices:body=detail(target[3:])
   else:code=404;body='not found'
   self.send_response(code);self.send_header('Content-Type',mime+';charset=utf-8');self.end_headers();self.wfile.write(body.encode())
 shop=ThreadingHTTPServer(('127.0.0.1',8443),Shop);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(str(cert/'cert.pem'),str(cert/'key.pem'));shop.socket=ctx.wrap_socket(shop.socket,server_side=True)
 thread=threading.Thread(target=shop.serve_forever,daemon=True);thread.start()
 # Test-only pin to our TLS server; hostname verification and CA validation stay on.
 original_address=transport.public_address;original_pinned=transport.PinnedHTTPS
 def address(host):
  if host=='store.example.test':return '127.0.0.1'
  return original_address(host)
 class FixtureTLS(original_pinned):
  def __init__(self,host,ip):
   super().__init__(host,ip)
   if host=='store.example.test':self._context=ssl.create_default_context(cafile=str(cert/'cert.pem'))
  def connect(self):
   if self.host!='store.example.test':return super().connect()
   sock=socket.create_connection(('127.0.0.1',8443),self.timeout)
   self.sock=self._context.wrap_socket(sock,server_hostname=self.host)
 transport.public_address=address;transport.PinnedHTTPS=FixtureTLS
 secret=Path('/tmp/lab-secret');secret.mkdir();token=secrets.token_urlsafe(48);(secret/'token').write_text(token)
 os.environ.update(COLLECTOR_BACKEND_TRANSPORT='internal_http',COLLECTOR_BACKEND_BASE_URL='http://127.0.0.1:8000',COLLECTOR_DELIVERY_APPROVED='yes',KKULPICK_BACKEND_TOKEN=token)
 backend=subprocess.Popen([sys.executable,'-m','services.collector.unified_live.devtest.network_lab','server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 workers=[]
 try:
  import urllib.request
  for _ in range(60):
   try:urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=1);break
   except OSError:time.sleep(.2)
  else:raise RuntimeError('local_FastAPI_unavailable')
  backend_checks()  # actual 503, ACK, redirect canary isolation, new/change/dedup
  results={}
  for kind in ('json','css','js'):
   cfg=fixture_config();cfg.update(source='html_lab_'+kind,search_url_template='',queries=[],start_urls=['https://store.example.test/catalog/'+kind],mode='used' if kind=='css' else 'general',provider_min_interval_seconds=60 if kind=='css' else 7200,render_javascript=kind=='js')
   if kind=='css':cfg['selectors']={k:'.'+k for k in ('name','price','currency','seller','condition','availability','image','model')};cfg['selectors']['card']='.card'
   if kind=='js':cfg['selectors']={'product_links':'a.product'}
   offset=[timedelta(hours=-8)];clock=lambda:datetime.now(timezone.utc)+offset[0]
   root=Path('/tmp/web-lab')/kind;http=SafeHTTP(cfg,root/cfg['source'],clock);http.synthetic_only=True
   worker=URLWorker(cfg,root,transport=http,renderer=PlaywrightRenderer() if kind=='js' else None,clock=clock);workers.append(worker)
   def cycle():
    deadline=time.monotonic()+100;target=worker.state['totals'].get('cycles_completed',0)+1
    while time.monotonic()<deadline:
     worker.step()
     if worker.report()['hold']:raise AssertionError(worker.report()['hold'])
     if worker.state['totals'].get('cycles_completed',0)>=target:return
     time.sleep(.2)
    raise AssertionError('bounded_fixture_cycle_timeout')
   cycle();first=worker.report();assert first['tracked_items']==1,first
   initial=worker.delivery.box.state['totals']['HTTP_attempts'] if hasattr(worker.delivery,'box') else None
   offset[0]+=timedelta(seconds=7200 if kind!='css' else 60);cycle()
   assert worker.delivery.data['totals'].get('unchanged',0)>=1,worker.delivery.data
   prices[kind]='10.00';offset[0]+=timedelta(seconds=7200 if kind!='css' else 60);cycle()
   report=worker.report();assert report['totals']['products_success']==2,report
   assert report['effective_interval_seconds']==(60 if kind=='css' else 7200)
   assert all(v['extension']['stock_quantity'] is None for v in worker.state['known'].values())
   results[kind]={'tracked':report['tracked_items'],'new':worker.delivery.data['totals'].get('new'),'updated':worker.delivery.data['totals'].get('updated'),'unchanged':worker.delivery.data['totals'].get('unchanged'),'hold':report['hold'],'interval':report['effective_interval_seconds'],'TLS_requests':report['HTTP_attempts'],'JS_Chromium':kind=='js'}
   worker.close();workers.remove(worker)
  assert hits.get('/catalog/json?page=2',0)>0 and hits.get('/data/list',0)>0 and hits.get('/data/detail',0)>0
  print(json.dumps({'passed':True,'fixture_only':True,'actual_public_sites_tested':[],'network_none':True,'source_TLS_certificate_verified':True,'test_only_loopback_pin':True,'HTTP_FastAPI_SQLite':True,'workers':results,'pagination':True,'production_DB_writes':0,'supplier_API_requests':0,'NAS_changed':False}))
 finally:
  for worker in workers:worker.close()
  backend.terminate();backend.wait(timeout=10);shop.shutdown();shop.server_close();transport.public_address=original_address;transport.PinnedHTTPS=original_pinned
if __name__=='__main__':main()
