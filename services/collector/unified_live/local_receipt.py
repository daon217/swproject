"""Disposable loopback-only HTTP/SQLite contract lab, never a production DB client."""
from contextlib import contextmanager,closing
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import uuid
from services.collector.domeggook_live.domeggook_backend_contract import Observation

class ReceiptStore:
    def __init__(self,path,hosts,currencies):
        self.path=Path(path)
        if not self.path.name.startswith('collector_test_'):raise ValueError('isolated_test_namespace_required')
        self.hosts=hosts;self.currencies=currencies;self.calls=0;self.fail_next=False
        with closing(sqlite3.connect(self.path)) as c:
            c.executescript('CREATE TABLE IF NOT EXISTS observations(source TEXT,event_key TEXT,hash TEXT,ack TEXT,PRIMARY KEY(source,event_key)); CREATE TABLE IF NOT EXISTS listings(source TEXT,id TEXT,variant TEXT,hash TEXT,PRIMARY KEY(source,id,variant));')
            c.commit()
    def receive(self,body):
        Observation.model_validate(body,context={'hosts':self.hosts,'currencies':self.currencies})
        if not all(body.get(k) for k in ('source_listing_id','variant_key','observation_key')):return 422,{}
        self.calls+=1
        if self.fail_next:self.fail_next=False;return 503,{}
        raw=json.dumps(body,sort_keys=True,ensure_ascii=False,separators=(',',':'));sha=hashlib.sha256(raw.encode()).hexdigest()
        identity=(body['source'],body['source_listing_id'],body['variant_key']);event=(body['source'],body['observation_key'])
        semantic=hashlib.sha256(json.dumps({k:v for k,v in body.items() if k not in ('observed_at','observation_key')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with closing(sqlite3.connect(self.path)) as c:
            old=c.execute('SELECT hash,ack FROM observations WHERE source=? AND event_key=?',event).fetchone()
            if old:return (200,json.loads(old[1])) if old[0]==sha else (409,{})
            item=c.execute('SELECT hash FROM listings WHERE source=? AND id=? AND variant=?',identity).fetchone()
            if item is None and not {'price','currency','availability','url','name'}<=set(body.get('field_presence',[])):
                ack={'state':'quarantine','change_kind':'quarantined','reason':'INCOMPLETE_FIRST_OBSERVATION'}
                c.execute('INSERT INTO observations VALUES(?,?,?,?)',(*event,sha,json.dumps(ack)));c.commit()
                return 201,ack
            kind='created' if item is None else 'unchanged' if item[0]==semantic else 'updated'
            ack={'state':'applied','change_kind':kind}
            c.execute('INSERT INTO listings VALUES(?,?,?,?) ON CONFLICT(source,id,variant) DO UPDATE SET hash=excluded.hash',(*identity,semantic))
            c.execute('INSERT INTO observations VALUES(?,?,?,?)',(*event,sha,json.dumps(ack)))
            c.commit()
        return 201,ack
    def counts(self):
        with closing(sqlite3.connect(self.path)) as c:return {'observations':c.execute('SELECT COUNT(*) FROM observations').fetchone()[0],
            'listings':c.execute('SELECT COUNT(*) FROM listings').fetchone()[0],'HTTP_calls':self.calls}

@contextmanager
def server(hosts,currencies):
    with tempfile.TemporaryDirectory(prefix='collector_contract_lab_') as temp:
        store=ReceiptStore(Path(temp)/'collector_test_receipts.sqlite',hosts,currencies);token='LOCAL_TEST_ONLY_'+uuid.uuid4().hex
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_POST(self):
                if self.headers.get('Authorization')!='Bearer '+token:self.send_error(401);return
                if not re.fullmatch(r'/internal/v2/crawl-runs/[a-f0-9-]{36}/observations',self.path):self.send_error(404);return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=65536:raise ValueError()
                    body=json.loads(self.rfile.read(size));code,ack=store.receive(body)
                except (ValueError,TypeError,KeyError):code,ack=422,{}
                data=json.dumps(ack).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        http=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:yield 'http://127.0.0.1:'+str(http.server_port),token,store
        finally:http.shutdown();http.server_close();thread.join(timeout=5)
