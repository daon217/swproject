"""Optional isolated SQLite test API. No team app imports or PostgreSQL driver."""
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3
from contextlib import contextmanager
from urllib.parse import urlsplit
from decimal import Decimal
from .generate import VERSION,encoded,CATEGORIES


def validate_record(row):
    if not isinstance(row,dict) or row.get('synthetic') is not True or row.get('schema_version')!=VERSION or row.get('source')!='synthetic_catalog':
        raise ValueError('synthetic_record_required')
    fields={'schema_version','synthetic','source','record_id','source_listing_id','variant_key','name',
            'category','region','condition','price','currency','seller','url','availability',
            'stock_quantity','ingredients','allergens','safe_to_consume','observation_key'}
    if set(row)!=fields or row.get('availability')!='available' or any(row.get(k) is not None for k in ('stock_quantity','ingredients','allergens','safe_to_consume')):
        raise ValueError('exact_synthetic_schema_required')
    if (row.get('region'),row.get('currency')) not in (('domestic','KRW'),('overseas','USD')):
        raise ValueError('synthetic_region_currency_mismatch')
    identity=row.get('record_id','')
    if not re.fullmatch(r'SYNTHETIC-[0-9a-f]{16}-\d{7}',identity):raise ValueError('synthetic_identity_required')
    if row.get('source_listing_id')!=identity or row.get('variant_key')!=identity+':variant-0':raise ValueError('synthetic_identity_mismatch')
    parsed=urlsplit(row.get('url',''))
    if parsed.scheme!='https' or parsed.netloc!='catalog.example.test' or parsed.path!='/synthetic/'+identity or parsed.query or parsed.fragment:
        raise ValueError('synthetic_URL_required')
    if (not str(row.get('name','')).startswith('SYNTHETIC ') or not str(row.get('seller','')).startswith('SYNTHETIC_VENDOR_')
            or row.get('currency') not in ('KRW','USD') or row.get('condition') not in ('new','used')
            or row.get('category') not in {c[0] for c in CATEGORIES} or row.get('safe_to_consume') is not None):
        raise ValueError('synthetic_fields_required')
    price=row.get('price')
    if not isinstance(price,str) or not re.fullmatch(r'\d+(?:\.\d{1,2})?',price) or not Decimal(price).is_finite() or Decimal(price)<0:
        raise ValueError('synthetic_price_invalid')
    body={k:v for k,v in row.items() if k!='observation_key'}
    if row.get('observation_key')!='SYNTHETIC:'+hashlib.sha256(encoded(body)).hexdigest():raise ValueError('synthetic_hash_mismatch')


class TestStore:
    __test__=False
    def __init__(self,path,namespace):
        self.path=Path(path)
        if self.path.is_symlink():raise ValueError('symlink_test_DB_forbidden')
        if (not self.path.name.startswith('synthetic_') or self.path.suffix!='.sqlite3'
                or not re.fullmatch(r'synthetic_[a-z0-9_]+',namespace)):
            raise ValueError('isolated_synthetic_SQLite_namespace_required')
        self.namespace=namespace
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'") if not r[0].startswith('sqlite_')}
            if not tables<={'synthetic_products','synthetic_receipts'}:
                raise ValueError('non_synthetic_SQLite_DB_forbidden')
            db.execute('CREATE TABLE IF NOT EXISTS synthetic_products (namespace TEXT, id TEXT, payload TEXT, PRIMARY KEY(namespace,id))')
            db.execute('CREATE TABLE IF NOT EXISTS synthetic_receipts (namespace TEXT, key TEXT, hash TEXT, count INTEGER, PRIMARY KEY(namespace,key))')
    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path)
        try:
            with db:yield db
        finally:db.close()
    def ingest(self,batch):
        rows=batch.get('records');key=batch.get('batch_key')
        if batch.get('namespace')!=self.namespace or not isinstance(rows,list) or not 1<=len(rows)<=1000 or not isinstance(key,str) or not key.startswith('SYNTHETIC:'):
            raise ValueError('bounded_synthetic_batch_required')
        for row in rows:validate_record(row)
        digest=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with self.connection() as db:
            receipt=db.execute('SELECT hash,count FROM synthetic_receipts WHERE namespace=? AND key=?',(self.namespace,key)).fetchone()
            if receipt:
                if receipt[0]!=digest:raise ValueError('immutable_batch_conflict')
                return {'batch_key':key,'sha256':digest,'count':receipt[1],'state':'duplicate'}
            for row in rows:
                payload=json.dumps(row,sort_keys=True,separators=(',',':'))
                old=db.execute('SELECT payload FROM synthetic_products WHERE namespace=? AND id=?',(self.namespace,row['record_id'])).fetchone()
                if old and old[0]!=payload:raise ValueError('immutable_record_conflict')
                db.execute('INSERT OR IGNORE INTO synthetic_products VALUES (?,?,?)',(self.namespace,row['record_id'],payload))
            db.execute('INSERT INTO synthetic_receipts VALUES (?,?,?,?)',(self.namespace,key,digest,len(rows)))
        return {'batch_key':key,'sha256':digest,'count':len(rows),'state':'applied'}
    def receipt(self,key):
        with self.connection() as db:
            row=db.execute('SELECT hash,count FROM synthetic_receipts WHERE namespace=? AND key=?',(self.namespace,key)).fetchone()
        return {'batch_key':key,'sha256':row[0],'count':row[1],'state':'applied'} if row else None


def create_server(path,namespace,token,port=18779):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from urllib.parse import parse_qs
    if not isinstance(token,str) or len(token)<16:raise ValueError('explicit_test_token_required')
    store=TestStore(path,namespace)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,body):
            data=json.dumps(body).encode()
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def authorized(self):
            return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token)
        def do_POST(self):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=2000000:raise ValueError('bounded_body_required')
                # Drain the bounded body before sending 401/404; otherwise closing
                # while a client is uploading can reset TCP and hide the status.
                body=self.rfile.read(length)
                if not self.authorized():self.reply(401,{'error':'test_auth_required'});return
                if self.path!='/test/synthetic-import':self.reply(404,{});return
                result=store.ingest(json.loads(body))
                self.reply(200,result)
            except (ValueError,KeyError,TypeError):self.reply(409,{'error':'synthetic_batch_or_identity_rejected'})
        def do_GET(self):
            if not self.authorized():self.reply(401,{'error':'test_auth_required'});return
            parsed=urlsplit(self.path)
            if parsed.path!='/test/synthetic-receipt':self.reply(404,{});return
            key=parse_qs(parsed.query).get('batch_key',[''])[0]
            result=store.receipt(key)
            self.reply(200,result) if result else self.reply(404,{})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    return server


def main():
    import argparse,os
    p=argparse.ArgumentParser(description='Isolated synthetic SQLite API, bound to loopback only')
    p.add_argument('--db',required=True);p.add_argument('--namespace',required=True)
    p.add_argument('--port',type=int,default=18779)
    args=p.parse_args()
    server=create_server(args.db,args.namespace,os.environ.get('KKULPICK_SYNTHETIC_TEST_TOKEN'),args.port)
    try:server.serve_forever()
    finally:server.server_close()


if __name__=='__main__':main()
