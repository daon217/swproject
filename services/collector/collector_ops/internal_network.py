"""Compose-scoped internal HTTP policy. Legacy review CLI is optional and not used by delivery."""
import argparse
from datetime import datetime,timezone,timedelta
import ipaddress,json,os,re,socket,stat,struct,sys,tempfile
from pathlib import Path

RFC1918=tuple(ipaddress.ip_network(s) for s in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
def now():return datetime.now(timezone.utc)
def stamp(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('aware_network_review_time_required')
    return result
def private4(value):
    ip=ipaddress.ip_address(value)
    if not any(ip in net for net in RFC1918):raise ValueError('RFC1918_endpoint_required')
    return str(ip)
def ident(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('full_Docker_identity_required')
    return value


def issue_review(network,collector,backend,*,trusted_ids,service,port,reference,admin_confirmed=False,current=None):
    """Pure validation of host-side inspect snapshots; does not change Docker or grant API rights."""
    current=current or now()
    if not admin_confirmed or not reference or len(reference)>1024:raise ValueError('independent_admin_review_required')
    if network.get('Internal') is not True or network.get('Driver')!='bridge' or network.get('Scope')!='local' or network.get('Ingress') or network.get('EnableIPv6'):
        raise ValueError('isolated_IPv4_internal_bridge_required')
    nid=ident(network.get('Id'));cid=ident(collector.get('Id'));bid=ident(backend.get('Id'))
    trusted=set(map(ident,trusted_ids));members=network.get('Containers',{})
    if set(members)!=trusted or not {cid,bid}<=trusted or cid==bid:raise ValueError('network_membership_not_exactly_trusted')
    if not re.fullmatch('[a-z][a-z0-9-]{1,62}',service) or service in ('localhost','host-docker-internal') or type(port) is not int or not 1<=port<=65535:
        raise ValueError('approved_service_and_port_required')
    configs=network.get('IPAM',{}).get('Config',[])
    if len(configs)!=1:raise ValueError('one_reviewed_subnet_required')
    subnet=ipaddress.ip_network(configs[0]['Subnet']);private4(str(subnet.network_address));private4(str(subnet.broadcast_address))
    for item in (collector,backend):
        host=item.get('HostConfig',{})
        if host.get('Privileged') or host.get('NetworkMode') in ('host','none') or host.get('NetworkMode','').startswith('container:'):
            raise ValueError('isolated_nonprivileged_container_required')
        if 'ALL' not in (host.get('CapDrop') or []) or host.get('CapAdd') or item.get('State',{}).get('Running') is not True:
            raise ValueError('running_capability_restricted_container_required')
        if any(v for v in item.get('NetworkSettings',{}).get('Ports',{}).values()):raise ValueError('published_ports_forbidden')
        if any('docker.sock' in m.get('Destination','') or 'docker_engine' in m.get('Destination','') for m in item.get('Mounts',[])):
            raise ValueError('worker_Docker_socket_forbidden')
    def endpoint(item):
        entries=[e for e in item['NetworkSettings']['Networks'].values() if e.get('NetworkID')==nid]
        if len(entries)!=1:raise ValueError('reviewed_endpoint_missing')
        ip=private4(entries[0]['IPAddress'])
        if ipaddress.ip_address(ip) not in subnet or ip!=str(ipaddress.ip_interface(members[item['Id']]['IPv4Address']).ip):
            raise ValueError('inspect_endpoint_mismatch')
        return entries[0],ip
    be,bip=endpoint(backend);ce,cip=endpoint(collector)
    if len(backend['NetworkSettings']['Networks'])!=1:raise ValueError('ingest_service_must_be_internal_only')
    if service not in (be.get('Aliases') or []):raise ValueError('approved_DNS_alias_missing')
    return {'version':1,'approved':True,'review_reference':reference,'issued_at':current.isoformat(),
        'expires_at':(current+timedelta(minutes=5)).isoformat(),'network_id':nid,'network_name':network['Name'],
        'subnet':str(subnet),'collector_id':cid,'backend_id':bid,'collector_hostname':collector['Config']['Hostname'],
        'collector_ip':cip,'backend_ip':bip,'service':service,'port':port,'trusted_container_ids':sorted(trusted),
        'internal':True,'driver':'bridge','backend_internal_only':True,'published_ports':False}


def direct_route(destination,source):
    """Linux LPM route must be on-link via the interface owning the attested source address."""
    if sys.platform!='linux':raise ValueError('Linux_route_proof_required')
    import fcntl
    dst=int(ipaddress.ip_address(destination));routes=[]
    for line in Path('/proc/net/route').read_text().splitlines()[1:]:
        row=line.split()
        if len(row)<8:continue
        net,gw,flags,mask=(int.from_bytes(bytes.fromhex(row[i]),'little') for i in (1,2,3,7))
        # Flags are host-order hex, unlike addresses.
        flags=int(row[3],16)
        if flags&1 and dst&mask==net:routes.append((mask.bit_count(),int(row[6]),row[0],gw))
    if not routes:raise ValueError('no_direct_route')
    best=max(x[0] for x in routes);metric=min(x[1] for x in routes if x[0]==best)
    winners=[x for x in routes if x[0]==best and x[1]==metric]
    if len(winners)!=1 or winners[0][3]!=0 or best==0:raise ValueError('gateway_or_ambiguous_route_forbidden')
    iface=winners[0][2]
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        address=socket.inet_ntoa(fcntl.ioctl(s.fileno(),0x8915,struct.pack('256s',iface.encode()[:15]))[20:24])
    if address!=source:raise ValueError('route_source_interface_mismatch')
    return iface


class InternalPolicy:
    """Explicit Compose origin + subnet; Docker enforces isolation, kernel checks the actual path."""
    def __init__(self,base_url):
        from urllib.parse import urlsplit
        p=urlsplit(base_url)
        if p.scheme!='http' or not p.hostname or not re.fullmatch('[a-z][a-z0-9_-]{1,62}',p.hostname) or p.path not in ('','/') or p.username or p.password or p.query or p.fragment or p.port is None:
            raise ValueError('explicit_internal_service_origin_required')
        if p.hostname in ('localhost','host_docker_internal','host-docker-internal'):raise ValueError('Docker_service_required')
        self.host=p.hostname;self.port=p.port
        self.subnet=self.settings()
    def settings(self):
        from urllib.parse import urlsplit
        if os.environ.get('COLLECTOR_BACKEND_TRANSPORT','https')!='internal_http' or os.environ.get('COLLECTOR_DELIVERY_APPROVED')!='yes':
            raise ValueError('internal_HTTP_not_configured_for_delivery')
        target=urlsplit(os.environ.get('COLLECTOR_BACKEND_BASE_URL',''))
        if target.scheme!='http' or target.hostname!=self.host or target.port!=self.port or target.path not in ('','/') or target.username or target.password or target.query or target.fragment:
            raise ValueError('only_explicit_Compose_service_and_port_allowed')
        subnet=ipaddress.ip_network(os.environ.get('COLLECTOR_INTERNAL_SUBNET',''),strict=True)
        if subnet.version!=4 or not 16<=subnet.prefixlen<=30:raise ValueError('bounded_Docker_IPv4_subnet_required')
        private4(str(subnet.network_address));private4(str(subnet.broadcast_address))
        if hasattr(self,'subnet') and subnet!=self.subnet:raise ValueError('restart_after_network_configuration_change')
        return subnet
    def check(self):
        from .container_route import connected_endpoint,docker_dns_service
        subnet=self.settings();docker_dns_service(self.host)
        addresses={r[4][0] for r in socket.getaddrinfo(self.host,self.port,type=socket.SOCK_STREAM)}
        if not addresses:raise socket.gaierror('Docker_service_not_ready')
        if len(addresses)!=1:raise ValueError('single_Docker_service_IP_required')
        destination=private4(next(iter(addresses)))
        if ipaddress.ip_address(destination) not in subnet or ipaddress.ip_address(destination) in (subnet.network_address,subnet.broadcast_address):
            raise ValueError('HTTP_destination_outside_configured_Docker_network')
        source,interface=connected_endpoint(destination,subnet)
        return destination,source


def save_review(path,data):
    # Set permissions BEFORE atomic replacement: no root-only inode visibility window.
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(data,stream);stream.flush();os.fsync(stream.fileno())
        os.chmod(temp,0o644);os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def main():
    p=argparse.ArgumentParser();p.add_argument('--network-inspect',required=True);p.add_argument('--collector-inspect',required=True);p.add_argument('--backend-inspect',required=True)
    p.add_argument('--trusted-container-id',action='append',required=True);p.add_argument('--service',required=True);p.add_argument('--port',type=int,required=True)
    p.add_argument('--review-reference',required=True);p.add_argument('--admin-network-review-confirmed',action='store_true');p.add_argument('--output',required=True)
    a=p.parse_args()
    def read(path):
        d=json.loads(Path(path).read_text(encoding='utf-8'));return d[0] if isinstance(d,list) and len(d)==1 else d
    try:
        review=issue_review(read(a.network_inspect),read(a.collector_inspect),read(a.backend_inspect),trusted_ids=a.trusted_container_id,service=a.service,port=a.port,reference=a.review_reference,admin_confirmed=a.admin_network_review_confirmed)
        save_review(Path(a.output),review);print(json.dumps({'network_review_created':True,'expires_at':review['expires_at'],'production_deployment_performed':False}));return 0
    except Exception:
        # A failed refresh revokes any previous approval; never keep stale positive evidence.
        save_review(Path(a.output),{'version':1,'approved':False});print(json.dumps({'network_review_created':False,'revoked':True}));return 2

if __name__=='__main__':raise SystemExit(main())
