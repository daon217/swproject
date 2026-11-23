"""No external requests. Runtime Docker/FastAPI tests are an independent opt-in lab."""
import copy,io,json,os,socket,tempfile,unittest,uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from requests.exceptions import InvalidURL
from urllib3.exceptions import NewConnectionError
from services.collector.domeggook_live.network import public_ips,PublicHTTPSConnection,PublicHTTPSAdapter,secure_public_session
from services.collector.collector_ops.internal_network import issue_review,InternalPolicy,now
from services.collector.collector_ops.backend_transport import RoutedBackend,build_backend,InternalHTTPAdapter
from services.collector.unified_live.policy import url
from services.collector.unified_live.transport import SafeHTTP,Wait
from services.collector.unified_live.mock import fixture_config,product
from services.collector.unified_live.parser import normalize
from services.collector.unified_live.backend import ApprovedOutbox
from services.collector.unified_live.changes import ChangeDelivery

NID='a'*64;CID='b'*64;BID='c'*64;TOKEN='SYNTHETIC_INTERNAL_TOKEN_'+('x'*40)
BASE='http://ingest-api:8000';PATH='/internal/v2/crawl-runs/'+str(uuid.uuid4())+'/observations'
def snapshots():
    def container(cid,ip,aliases):return {'Id':cid,'Config':{'Hostname':cid[:12]},'HostConfig':{'NetworkMode':'isolated','CapDrop':['ALL'],'Privileged':False},'State':{'Running':True},'Mounts':[],
        'NetworkSettings':{'Ports':{'8000/tcp':None},'Networks':{'isolated':{'NetworkID':NID,'IPAddress':ip,'Aliases':aliases}}}}
    c=container(CID,'172.30.42.3',['collector']);b=container(BID,'172.30.42.2',['ingest-api'])
    n={'Id':NID,'Name':'SYNTHETIC-isolated','Scope':'local','Driver':'bridge','Internal':True,'EnableIPv6':False,
        'IPAM':{'Config':[{'Subnet':'172.30.42.0/24'}]},'Containers':{CID:{'IPv4Address':'172.30.42.3/24'},BID:{'IPv4Address':'172.30.42.2/24'}}}
    return n,c,b
def review(n=None,c=None,b=None,**kwargs):
    defaults=snapshots();return issue_review(n or defaults[0],c or defaults[1],b or defaults[2],trusted_ids=[CID,BID],service='ingest-api',port=8000,reference='SYNTHETIC independent admin verification',admin_confirmed=True,**kwargs)
def dns(address='172.30.42.2'):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,8000))]

class NetworkPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.file=self.root/'review.json'
        self.env={'COLLECTOR_BACKEND_TRANSPORT':'internal_http','COLLECTOR_BACKEND_BASE_URL':BASE,
            'COLLECTOR_INTERNAL_SUBNET':'172.30.42.0/24','COLLECTOR_DELIVERY_APPROVED':'yes','KKULPICK_BACKEND_TOKEN':TOKEN}
        self.stack=__import__('contextlib').ExitStack();self.stack.enter_context(patch.dict(os.environ,self.env,clear=True))
        self.stack.enter_context(patch('services.collector.collector_ops.internal_network.socket.getaddrinfo',return_value=dns()))
        self.stack.enter_context(patch('services.collector.collector_ops.container_route.docker_dns_service'))
        self.route=self.stack.enter_context(patch('services.collector.collector_ops.container_route.connected_endpoint',return_value=('172.30.42.3','eth1')))
    def tearDown(self):self.stack.close();self.temp.cleanup()
    def test_explicit_Compose_internal_origin_allowed_without_review_file(self):
        p=InternalPolicy(BASE);self.assertEqual(p.check(),('172.30.42.2','172.30.42.3'));self.route.assert_called();self.assertFalse(self.file.exists())
    def test_explicit_origin_subnet_and_existing_delivery_activation_required(self):
        for name in ('COLLECTOR_BACKEND_TRANSPORT','COLLECTOR_BACKEND_BASE_URL','COLLECTOR_INTERNAL_SUBNET','COLLECTOR_DELIVERY_APPROVED'):
            with self.subTest(name=name),patch.dict(os.environ,{name:''}),self.assertRaises(ValueError):InternalPolicy(BASE)
    def test_private_IP_loopback_public_IP_and_other_service_not_automatically_allowed(self):
        for base in ('http://172.30.42.2:8000','http://127.0.0.1:8000','http://localhost:8000','http://8.8.8.8:8000','http://other-api:8000','http://ingest-api:80','http://ingest-api','http://user:pass@ingest-api:8000','http://ingest-api:8000/?token=secret'):
            with self.subTest(base=base),self.assertRaises(ValueError):InternalPolicy(base)
    def test_obsolete_approval_variables_are_not_read_or_required(self):
        with patch.dict(os.environ,{'COLLECTOR_INTERNAL_HTTP_APPROVED':'no','COLLECTOR_INTERNAL_NETWORK_ID':'old-id','COLLECTOR_INTERNAL_NETWORK_REVIEW_FILE':str(self.file)}),patch('pathlib.Path.read_text',side_effect=AssertionError('approval files forbidden')):
            self.assertEqual(InternalPolicy(BASE).check(),('172.30.42.2','172.30.42.3'))
    def test_unbounded_or_public_subnet_rejected(self):
        for subnet in ('0.0.0.0/0','10.0.0.0/8','8.8.8.0/24','127.0.0.0/24','169.254.0.0/16','172.30.42.1/24','::/64'):
            with self.subTest(subnet=subnet),patch.dict(os.environ,{'COLLECTOR_INTERNAL_SUBNET':subnet}),self.assertRaises(ValueError):InternalPolicy(BASE)
    def test_DNS_public_outside_subnet_and_mixed_answers_rejected(self):
        p=InternalPolicy(BASE)
        for answers in (dns('8.8.8.8'),dns('127.0.0.1'),dns('169.254.169.254'),dns('172.31.0.2'),dns()+dns('172.30.42.9')):
            with self.subTest(answers=answers),patch('socket.getaddrinfo',return_value=answers),self.assertRaises(ValueError):p.check()
    def test_gateway_route_is_not_accepted(self):
        self.route.side_effect=ValueError('gateway_route')
        with self.assertRaises(ValueError):InternalPolicy(BASE).check()
    def test_recreated_service_IP_in_same_network_needs_no_manual_approval(self):
        p=InternalPolicy(BASE);p.check()
        with patch('socket.getaddrinfo',return_value=dns('172.30.42.9')):self.assertEqual(p.check(),('172.30.42.9','172.30.42.3'))
    def test_origin_and_route_cannot_leak_backend_token(self):
        tx=RoutedBackend(BASE,TOKEN,now)
        try:
            with self.assertRaises(InvalidURL):tx.session.post('http://other-api:8000'+PATH)
            with self.assertRaises(InvalidURL):tx.session.post('https://public.example.test'+PATH)
            with self.assertRaises(InvalidURL):tx.session.post(BASE+'/other-route')
        finally:tx.close()
        self.assertNotIn('Authorization',tx.session.headers)
    def test_configuration_violation_returns_hold_without_connect_or_sensitive_output(self):
        tx=RoutedBackend(BASE,TOKEN,now)
        try:
            with patch.dict(os.environ,{'COLLECTOR_INTERNAL_SUBNET':'172.31.0.0/24'}),patch.object(tx.session,'post') as send:
                result=tx(PATH,{});self.assertEqual(result,(403,{}));send.assert_not_called();self.assertNotIn(TOKEN,str(result))
        finally:tx.close()
    def test_retries_after_same_body_and_ACK_sanitization(self):
        tx=RoutedBackend(BASE,TOKEN,now);response=Mock(status_code=201)
        response.json.return_value={'state':'applied','change_kind':'created','token':TOKEN,'offer_id':str(uuid.uuid4())}
        try:
            with patch.object(tx.session,'post',return_value=response) as send:
                code,ack=tx(PATH,{'schema_version':2});self.assertEqual(code,201);self.assertNotIn('token',ack)
                self.assertFalse(send.call_args.kwargs['allow_redirects']);self.assertNotIn(TOKEN,json.dumps(ack))
        finally:tx.close()
    def test_redirect_not_followed_and_no_second_host_token(self):
        tx=RoutedBackend(BASE,TOKEN,now);response=Mock(status_code=302,headers={'Location':'http://public.example.test/'})
        try:
            with patch.object(tx.session,'post',return_value=response) as send:
                self.assertEqual(tx(PATH,{}),(302,{}));self.assertEqual(send.call_count,1);self.assertFalse(send.call_args.kwargs['allow_redirects'])
        finally:tx.close()
    def test_factory_env_overrides_only_backend_URL(self):
        tx=build_backend('https://team.example.test',TOKEN,now)
        try:self.assertEqual(tx.base,BASE);self.assertEqual(fixture_config()['base_url'],'https://store.example.test/')
        finally:tx.close()
    def test_outbox_default_disabled_preserves_payload(self):
        cfg=fixture_config();r=normalize(product(),cfg['base_url'],now().isoformat(),cfg)
        with patch.dict(os.environ,{'COLLECTOR_DELIVERY_APPROVED':'no'}):
            box=ApprovedOutbox(cfg,self.root/'queue',clock=now)
            try:
                staged=box.stage(r);box.flush();self.assertEqual(staged['status'],'pending')
                self.assertIsNone(box.transport);self.assertIn('body',next(iter(box.state['entries'].values())))
            finally:box.close()
    def test_outbox_retry_dedup_and_payload_unchanged(self):
        cfg=fixture_config();clock=[now()];tx=Mock();tx.retry_not_before=None;tx.side_effect=[(503,{}),(201,{'state':'applied','change_kind':'created'})]
        raw=normalize(product(),cfg['base_url'],clock[0].isoformat(),cfg)
        box=ApprovedOutbox(cfg,self.root/'retry',transport=tx,clock=lambda:clock[0]);gate=ChangeDelivery(box,self.root/'retry')
        try:
            gate.stage(raw);gate.flush();self.assertEqual(next(iter(box.state['entries'].values()))['status'],'retry_wait')
            clock[0]+=timedelta(seconds=10);gate.flush();self.assertEqual(next(iter(box.state['entries'].values()))['status'],'delivered')
            self.assertEqual(tx.call_args_list[0].args,tx.call_args_list[1].args);self.assertEqual(gate.stage(raw)['status'],'unchanged_skipped')
        finally:gate.close()

class TopologyTests(unittest.TestCase):
    def test_inspect_snapshot_issues_only_short_admin_review(self):
        d=review();self.assertEqual(stamp_duration(d),300)
    def test_noninternal_network_and_extra_members_rejected(self):
        for key,value in (('Internal',False),('Driver','host'),('EnableIPv6',True)):
            n,c,b=snapshots();n[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):review(n,c,b)
        n,c,b=snapshots();n['Containers']['d'*64]={}
        with self.assertRaises(ValueError):review(n,c,b)
    def test_public_endpoint_published_port_or_multihomed_backend_rejected(self):
        n,c,b=snapshots();b['NetworkSettings']['Ports']['8000/tcp']=[{'HostPort':'8000'}]
        with self.assertRaises(ValueError):review(n,c,b)
        n,c,b=snapshots();b['NetworkSettings']['Networks']['public']={'NetworkID':'d'*64}
        with self.assertRaises(ValueError):review(n,c,b)
    def test_privileged_or_host_network_container_rejected(self):
        for key,value in (('Privileged',True),('CapAdd',['NET_ADMIN']),('NetworkMode','host')):
            n,c,b=snapshots();c['HostConfig'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):review(n,c,b)
    def test_missing_admin_confirmation_is_not_an_approval(self):
        n,c,b=snapshots()
        with self.assertRaises(ValueError):issue_review(n,c,b,trusted_ids=[CID,BID],service='ingest-api',port=8000,reference='SYNTHETIC')

def stamp_duration(d):return (datetime.fromisoformat(d['expires_at'])-datetime.fromisoformat(d['issued_at'])).total_seconds()

class ExternalHTTPSRegression(unittest.TestCase):
    def test_external_HTTP_private_and_credential_URLs_remain_blocked(self):
        for target in ('http://store.example.test/a','https://127.0.0.1/a','https://169.254.169.254/a','https://user:pass@store.example.test/a'):
            with self.subTest(target=target),self.assertRaises(ValueError):url(target)
    def test_public_DNS_mixed_private_answers_blocked(self):
        for answers in (dns('127.0.0.1'),dns('169.254.169.254'),dns('93.184.216.34')+dns('10.0.0.1')):
            with self.subTest(answers=answers),patch('socket.getaddrinfo',return_value=answers),self.assertRaises(OSError):public_ips('api.example.test')
    def test_public_connection_is_pinned_and_TLS_host_remains_original(self):
        sock=Mock();sock.getpeername.return_value=('93.184.216.34',443)
        with patch('socket.getaddrinfo',return_value=dns('93.184.216.34')),patch('services.collector.domeggook_live.network.create_connection',return_value=sock) as connect:
            conn=PublicHTTPSConnection('api.example.test',443);self.assertIs(conn._new_conn(),sock)
            self.assertEqual(connect.call_args.args[0],('93.184.216.34',443));self.assertEqual(conn.host,'api.example.test')
    def test_HTTP_and_verify_false_rejected_before_socket(self):
        session=secure_public_session(requests.Session())
        try:
            with self.assertRaises(InvalidURL):session.get('http://api.example.test/')
            with self.assertRaises(InvalidURL):session.get('https://api.example.test/',verify=False)
        finally:session.close()
    def test_external_HTTPS_mock_success_and_downgrade_redirect_hold(self):
        cfg=fixture_config()
        with tempfile.TemporaryDirectory() as root:
            tx=SafeHTTP(cfg,root);conn=Mock();response=Mock(status=200)
            response.getheader.side_effect=lambda k,default=None:{'Content-Type':'text/html'}.get(k,default);response.read.side_effect=[b'<html>native product</html>',b''];conn.getresponse.return_value=response
            with patch('services.collector.unified_live.transport.public_address',return_value='93.184.216.34'),patch('services.collector.unified_live.transport.PinnedHTTPS',return_value=conn):
                code,text,_=tx._get(cfg['base_url']);self.assertEqual(code,200);self.assertIn('native product',text)
        with tempfile.TemporaryDirectory() as root:
            tx=SafeHTTP(cfg,root);response.status=301;response.getheader.side_effect=lambda k,default=None:'http://evil.example.test/' if k=='Location' else default
            with patch('services.collector.unified_live.transport.public_address',return_value='93.184.216.34'),patch('services.collector.unified_live.transport.PinnedHTTPS',return_value=conn),self.assertRaises(Wait):tx._get(cfg['base_url'])
            self.assertEqual(tx.state['hold'],'access_or_redirect_review_required')


class ReviewPersistenceTests(unittest.TestCase):
    def test_review_permissions_set_before_atomic_replace_and_revocation(self):
        from services.collector.collector_ops.internal_network import save_review
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'policy.json';real=os.replace;observed=[]
            def replace(source,target):
                self.assertTrue(Path(source).is_file())
                if os.name=='posix':self.assertEqual(Path(source).stat().st_mode&0o777,0o644)
                observed.append(True);return real(source,target)
            with patch('services.collector.collector_ops.internal_network.os.replace',side_effect=replace):
                save_review(path,{'approved':True});save_review(path,{'approved':False})
            self.assertEqual(json.loads(path.read_text()),{'approved':False});self.assertEqual(len(observed),2)
            self.assertEqual(len(list(Path(root).iterdir())),1)
    def test_failed_snapshot_refresh_revokes_old_positive_review(self):
        from services.collector.collector_ops.internal_network import main
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'policy.json';path.write_text('{"version":1,"approved":true}')
            argv=['internal_network','--network-inspect',root+'/missing.json','--collector-inspect',root+'/c.json','--backend-inspect',root+'/b.json',
                '--trusted-container-id',CID,'--trusted-container-id',BID,'--service','ingest-api','--port','8000','--review-reference','SYNTHETIC','--admin-network-review-confirmed','--output',str(path)]
            with patch('sys.argv',argv),redirect_stdout(io.StringIO()):self.assertEqual(main(),2)
            self.assertFalse(json.loads(path.read_text())['approved'])
    def test_public_TLS_pool_keeps_certificate_verification(self):
        from services.collector.domeggook_live.network import PublicHTTPSPool
        session=secure_public_session(requests.Session())
        try:
            prepared=requests.Request('GET','https://api.example.test/').prepare()
            pool=session.get_adapter(prepared.url).get_connection_with_tls_context(prepared,verify=True,proxies={})
            self.assertIsInstance(pool,PublicHTTPSPool);self.assertEqual(pool.cert_reqs,'CERT_REQUIRED')
            self.assertIs(pool.ConnectionCls,PublicHTTPSConnection)
        finally:session.close()


class DisabledDeliveryRevocationTests(unittest.TestCase):
    def test_no_delivery_approval_does_not_disable_storage_revocation(self):
        from services.collector.collector_ops.backend import OpsOutbox
        cfg=fixture_config();r=normalize(product(),cfg['base_url'],now().isoformat(),cfg)
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'COLLECTOR_DELIVERY_APPROVED':'no'}):
            box=OpsOutbox(cfg,root)
            try:
                self.assertEqual(box.stage(r)['status'],'pending')
                box.cfg['rights']['expires_at']='2000-01-01T00:00:00+00:00';box.flush()
                entry=next(iter(box.state['entries'].values()));self.assertEqual(entry['status'],'revoked');self.assertNotIn('body',entry)
                self.assertIsNone(box.transport)
            finally:box.close()
