"""Compose-scoped HTTP regressions; only synthetic data, no supplier requests."""
import ipaddress,json,os,socket,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from services.collector.collector_ops import container_route as route
from services.collector.collector_ops.backend_transport import InternalHTTPAdapter,RoutedBackend
from services.collector.collector_ops.internal_network import InternalPolicy,now
from services.collector.unified_live.tests.test_network_separation import BASE,PATH,TOKEN,dns

SUBNET=ipaddress.ip_network('172.30.42.0/24')
ENV={'COLLECTOR_BACKEND_TRANSPORT':'internal_http','COLLECTOR_BACKEND_BASE_URL':BASE,'COLLECTOR_INTERNAL_SUBNET':str(SUBNET),'COLLECTOR_DELIVERY_APPROVED':'yes'}
def attribute(kind,value):
    raw=struct.pack('HH',4+len(value),kind)+value
    return raw+b'\0'*((-len(raw))%4)

class KernelNetworkTests(unittest.TestCase):
    def test_netlink_reads_actual_veth_kind_without_Docker_socket(self):
        attrs=attribute(18,attribute(1,b'veth\0'));body=struct.pack('BBHiII',0,0,0,2,0,0)+attrs
        data=struct.pack('IHHII',16+len(body),16,0,1,0)+body
        fake=Mock();fake.__enter__=Mock(return_value=fake);fake.__exit__=Mock(return_value=False);fake.recv.return_value=data
        with patch.object(socket,'AF_NETLINK',16,create=True),patch.object(socket,'NETLINK_ROUTE',0,create=True),patch('socket.socket',return_value=fake),patch('socket.if_nametoindex',return_value=2):
            self.assertEqual(route.link_kind('eth1'),'veth');self.assertEqual(fake.sendto.call_args.args[1],(0,0))
    def test_malformed_kernel_reply_rejected(self):
        with self.assertRaises(ValueError):list(route.attributes(struct.pack('HH',100,18)+b'bad'))
    def test_onlink_subnet_veth_and_interface_address_agree(self):
        with patch('sys.platform','linux'),patch('pathlib.Path.is_file',return_value=True),patch.object(route,'route_for',return_value=('eth1',SUBNET)),patch.object(route,'link_kind',return_value='veth'),patch.object(route,'interface_ipv4',return_value=ipaddress.ip_interface('172.30.42.3/24')):
            self.assertEqual(route.connected_endpoint('172.30.42.2',SUBNET),('172.30.42.3','eth1'))
    def test_host_physical_bridge_macvlan_and_VPN_paths_rejected(self):
        for driver in ('bridge','macvlan','tun','dummy'):
            with self.subTest(driver=driver),patch('sys.platform','linux'),patch('pathlib.Path.is_file',return_value=True),patch.object(route,'route_for',return_value=('eth1',SUBNET)),patch.object(route,'link_kind',return_value=driver),self.assertRaises(ValueError):route.connected_endpoint('172.30.42.2',SUBNET)
    def test_wrong_network_or_self_destination_rejected(self):
        for value in ('172.31.0.3/24','172.30.42.2/24'):
            with self.subTest(value=value),patch('sys.platform','linux'),patch('pathlib.Path.is_file',return_value=True),patch.object(route,'route_for',return_value=('eth1',SUBNET)),patch.object(route,'link_kind',return_value='veth'),patch.object(route,'interface_ipv4',return_value=ipaddress.ip_interface(value)),self.assertRaises(ValueError):route.connected_endpoint('172.30.42.2',SUBNET)
    def test_default_gateway_and_ambiguous_routes_rejected(self):
        header='Iface Destination Gateway Flags RefCnt Use Metric Mask\n'
        for rows in ('eth0 00000000 01001EAC 0003 0 0 0 00000000\n','eth0 002A1EAC 00000000 0001 0 0 0 00FFFFFF\neth1 002A1EAC 00000000 0001 0 0 0 00FFFFFF\n'):
            with self.subTest(rows=rows),patch('pathlib.Path.read_text',return_value=header+rows),self.assertRaises(ValueError):route.route_for('172.30.42.2')
    def test_kernel_selects_direct_network_instead_of_egress_default(self):
        rows='Iface Destination Gateway Flags RefCnt Use Metric Mask\neth0 00000000 010000AC 0003 0 0 0 00000000\neth1 002A1EAC 00000000 0001 0 0 0 00FFFFFF\n'
        with patch('pathlib.Path.read_text',return_value=rows):self.assertEqual(route.route_for('172.30.42.2'),('eth1',SUBNET))
    def test_only_Docker_embedded_DNS_and_no_extra_hosts(self):
        def read(path,*args,**kwargs):return 'nameserver 127.0.0.11\n' if str(path).endswith('resolv.conf') else '127.0.0.1 localhost\n'
        with patch('pathlib.Path.read_text',autospec=True,side_effect=read):route.docker_dns_service('ingest-api')
        with patch('pathlib.Path.read_text',return_value='nameserver 8.8.8.8\n'),self.assertRaises(ValueError):route.docker_dns_service('ingest-api')
        def override(path,*args,**kwargs):return 'nameserver 127.0.0.11\n' if str(path).endswith('resolv.conf') else '172.30.42.1 ingest-api\n'
        with patch('pathlib.Path.read_text',autospec=True,side_effect=override),self.assertRaises(ValueError):route.docker_dns_service('ingest-api')

class AutomaticDeliveryTests(unittest.TestCase):
    def test_old_approval_files_are_irrelevant(self):
        with patch.dict(os.environ,ENV,clear=True),patch('services.collector.collector_ops.container_route.docker_dns_service'),patch('socket.getaddrinfo',return_value=dns()),patch.object(route,'connected_endpoint',return_value=('172.30.42.3','eth1')):
            self.assertEqual(InternalPolicy(BASE).check(),('172.30.42.2','172.30.42.3'))
    def test_pool_is_cleared_when_service_IP_changes(self):
        p=Mock();p.check.side_effect=[('172.30.42.2','172.30.42.3'),('172.30.42.9','172.30.42.3')]
        adapter=InternalHTTPAdapter(p,BASE);prepared=requests.Request('POST',BASE+PATH,json={}).prepare()
        with patch.object(adapter.poolmanager,'clear') as clear,patch('requests.adapters.HTTPAdapter.send',return_value=Mock()):
            adapter.send(prepared);adapter.send(prepared);clear.assert_called_once()
        adapter.close()
    def test_DNS_not_ready_is_retryable_and_does_not_send_a_token(self):
        with patch.dict(os.environ,ENV,clear=True),patch.object(route,'docker_dns_service'),patch.object(route,'connected_endpoint',return_value=('172.30.42.3','eth1')):
            tx=RoutedBackend(BASE,TOKEN,now)
            try:
                with patch('socket.getaddrinfo',side_effect=socket.gaierror('not ready')),patch.object(tx.session,'post') as post:
                    self.assertEqual(tx(PATH,{}),(503,{}));post.assert_not_called()
                response=Mock(status_code=201);response.json.return_value={'state':'applied','change_kind':'created'}
                with patch('socket.getaddrinfo',return_value=dns()),patch.object(tx.session,'post',return_value=response):self.assertEqual(tx(PATH,{})[0],201)
            finally:tx.close()
