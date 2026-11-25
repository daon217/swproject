"""Test-only child process: exact TLS fixture pin, then the production watch CLI."""
import os,ssl,socket,sys
from pathlib import Path
def main():
 if os.environ.get('COLLECTOR_NETWORK_LAB')!='synthetic_only':raise RuntimeError('lab_only')
 from services.collector.unified_live import transport,engine
 original=transport.PinnedHTTPS;original_address=transport.public_address
 class TLS(original):
  def __init__(self,host,ip):
   super().__init__(host,ip)
   if host=='store.example.test':self._context=ssl.create_default_context(cafile='/tmp/shop-cert/cert.pem')
  def connect(self):
   if self.host!='store.example.test':return super().connect()
   self.sock=self._context.wrap_socket(socket.create_connection(('127.0.0.1',8443),self.timeout),server_hostname=self.host)
 transport.PinnedHTTPS=TLS
 transport.public_address=lambda h:'127.0.0.1' if h=='store.example.test' else original_address(h)
 original_worker=engine.URLWorker
 class Worker(original_worker):
  def __init__(self,cfg,root,**kwargs):
   http=transport.SafeHTTP(cfg,Path(root)/cfg['source']);http.synthetic_only=True
   super().__init__(cfg,root,transport=http,**kwargs)
 engine.URLWorker=Worker
 from services.collector.unified_live.__main__ import main as watch
 return watch(sys.argv[1:])
if __name__=='__main__':raise SystemExit(main())
