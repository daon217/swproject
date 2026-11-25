"""Explicit backend URL, ordinary HTTP; external collection security is unchanged."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from requests.exceptions import InvalidURL
from services.collector.collector_ops.backend_transport import RoutedBackend,build_backend,InternalHTTPAdapter
from services.collector.collector_ops.backend import configure_CA
from services.collector.unified_live.tests.test_network_separation import BASE,PATH,TOKEN
from services.collector.collector_ops.internal_network import now
from services.collector.unified_live.policy import url

ENV={'COLLECTOR_BACKEND_TRANSPORT':'internal_http','COLLECTOR_BACKEND_BASE_URL':BASE,'COLLECTOR_DELIVERY_APPROVED':'yes'}

class PlainHTTPTests(unittest.TestCase):
    def test_no_Docker_DNS_veth_container_or_file_probes(self):
        with patch.dict(os.environ,ENV,clear=True),patch('socket.getaddrinfo',side_effect=AssertionError('no preflight DNS')),patch('pathlib.Path.read_text',side_effect=AssertionError('no deployment file')):
            tx=RoutedBackend(BASE,TOKEN,now)
            try:
                response=Mock(status_code=201);response.json.return_value={'state':'applied','change_kind':'created'}
                with patch.object(tx.session,'post',return_value=response):self.assertEqual(tx(PATH,{})[0],201)
            finally:tx.close()
    def test_explicit_configured_address_type_is_not_a_topology_gate(self):
        for target in ('http://10.1.2.3:8000','http://nas.internal.test:8000','http://localhost:9000','http://[::1]:8000','http://api'):
            with self.subTest(target=target),patch.dict(os.environ,dict(ENV,COLLECTOR_BACKEND_BASE_URL=target),clear=True):
                tx=build_backend('https://unused.example.test',TOKEN,now);self.assertEqual(tx.base,target);tx.close()
    def test_missing_environment_cannot_create_an_HTTP_sender(self):
        for name in ENV:
            e=dict(ENV);e.pop(name)
            with self.subTest(name=name),patch.dict(os.environ,e,clear=True),self.assertRaises(ValueError):RoutedBackend(BASE,TOKEN,now)
    def test_delivery_switch_removed_after_creation_prevents_send(self):
        with patch.dict(os.environ,ENV,clear=True):
            tx=RoutedBackend(BASE,TOKEN,now)
            try:
                with patch.dict(os.environ,{'COLLECTOR_DELIVERY_APPROVED':'no'}),patch.object(tx.session,'post') as post:
                    self.assertEqual(tx(PATH,{}),(403,{}));post.assert_not_called()
            finally:tx.close()
    def test_changed_origin_after_creation_prevents_send(self):
        with patch.dict(os.environ,ENV,clear=True):
            tx=RoutedBackend(BASE,TOKEN,now)
            try:
                with patch.dict(os.environ,{'COLLECTOR_BACKEND_BASE_URL':'http://other-api:8000'}),patch.object(tx.session,'post') as post:
                    self.assertEqual(tx(PATH,{}),(403,{}));post.assert_not_called()
            finally:tx.close()
    def test_different_host_port_scheme_and_route_blocked_before_network(self):
        with patch.dict(os.environ,ENV,clear=True):
            tx=RoutedBackend(BASE,TOKEN,now)
            try:
                for target in ('http://other-api:8000'+PATH,'http://ingest-api:8001'+PATH,'https://ingest-api:8000'+PATH,BASE+'/wrong-route'):
                    with self.subTest(target=target),self.assertRaises(InvalidURL):tx.session.post(target)
            finally:tx.close()
    def test_backend_HTTP_never_enables_external_product_HTTP_or_private_SSRF(self):
        with patch.dict(os.environ,ENV,clear=True):
            for target in ('http://api:8000/product','http://shop.example.test/product','https://127.0.0.1/product','https://169.254.169.254/latest/meta-data'):
                with self.subTest(target=target),self.assertRaises(ValueError):url(target)
    def test_HTTPS_still_requires_certificate_validation(self):
        with patch.dict(os.environ,{'COLLECTOR_BACKEND_TRANSPORT':'https','COLLECTOR_DELIVERY_APPROVED':'yes'},clear=True):
            tx=RoutedBackend('https://team.example.test',TOKEN,now)
            try:
                self.assertIs(tx.session.verify,True)
                with self.assertRaises(InvalidURL):tx.session.post('https://team.example.test'+PATH,verify=False)
            finally:tx.close()
    def test_HTTP_does_not_require_an_irrelevant_CA_file(self):
        with patch.dict(os.environ,dict(ENV,COLLECTOR_CA_FILE='/definitely-missing-ca.pem'),clear=True):
            tx=RoutedBackend(BASE,TOKEN,now)
            try:self.assertIs(configure_CA(tx),tx)
            finally:tx.close()
    def test_wrong_CA_file_still_rejected_for_HTTPS(self):
        with patch.dict(os.environ,{'COLLECTOR_BACKEND_TRANSPORT':'https','COLLECTOR_DELIVERY_APPROVED':'yes','COLLECTOR_CA_FILE':'/definitely-missing-ca.pem'},clear=True):
            tx=RoutedBackend('https://team.example.test',TOKEN,now)
            try:
                with self.assertRaises(ValueError):configure_CA(tx)
            finally:tx.close()
    def test_proxy_and_implicit_credentials_are_not_inherited(self):
        with patch.dict(os.environ,dict(ENV,HTTP_PROXY='http://untrusted.example.test:8080'),clear=True):
            tx=RoutedBackend(BASE,TOKEN,now)
            try:
                self.assertFalse(tx.session.trust_env)
                request=requests.Request('POST',BASE+PATH,json={}).prepare()
                with self.assertRaises(InvalidURL):tx.session.get_adapter(BASE).send(request,proxies={'http':'http://untrusted.example.test'})
            finally:tx.close()
    def test_HTTP_debug_output_cannot_print_auth_headers(self):
        import http.client
        with patch.dict(os.environ,ENV,clear=True),patch.object(http.client.HTTPConnection,'debuglevel',1):
            tx=RoutedBackend(BASE,TOKEN,now)
            try:
                pool=tx.session.get_adapter(BASE).poolmanager.connection_from_url(BASE)
                self.assertEqual(pool.ConnectionCls('ingest-api',8000).debuglevel,0)
            finally:tx.close()
