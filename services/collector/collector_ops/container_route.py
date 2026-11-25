"""Read-only Linux network checks; no Docker socket, metadata agent or approval file."""
import ipaddress
import socket
import struct
import sys
from pathlib import Path


def attributes(data):
    offset=0
    while offset+4<=len(data):
        length,kind=struct.unpack_from('HH',data,offset)
        if length<4 or offset+length>len(data):raise ValueError('invalid_kernel_link_metadata')
        yield kind&0x3fff,data[offset+4:offset+length]
        offset+=(length+3)&~3


def link_kind(interface):
    index=socket.if_nametoindex(interface);sequence=1
    body=struct.pack('BBHiII',socket.AF_UNSPEC,0,0,index,0,0)
    request=struct.pack('IHHII',16+len(body),18,1,sequence,0)+body  # RTM_GETLINK
    with socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,socket.NETLINK_ROUTE) as netlink:
        netlink.settimeout(2);netlink.sendto(request,(0,0));data=netlink.recv(65536)
    offset=0
    while offset+16<=len(data):
        length,kind,flags,seq,pid=struct.unpack_from('IHHII',data,offset)
        if length<16 or offset+length>len(data):raise ValueError('invalid_kernel_link_reply')
        if seq==sequence and kind==16 and length>=32:
            for key,value in attributes(data[offset+32:offset+length]):
                if key==18:  # IFLA_LINKINFO / IFLA_INFO_KIND
                    for nested,name in attributes(value):
                        if nested==1:return name.rstrip(b'\0').decode('ascii')
        offset+=(length+3)&~3
    raise ValueError('kernel_link_kind_unavailable')


def interface_ipv4(interface):
    import fcntl
    arg=struct.pack('256s',interface.encode()[:15])
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as control:
        address=socket.inet_ntoa(fcntl.ioctl(control.fileno(),0x8915,arg)[20:24])
        mask=socket.inet_ntoa(fcntl.ioctl(control.fileno(),0x891b,arg)[20:24])
    return ipaddress.ip_interface(address+'/'+mask)


def route_for(destination):
    dest=int(ipaddress.ip_address(destination));routes=[]
    for line in Path('/proc/net/route').read_text().splitlines()[1:]:
        row=line.split()
        if len(row)<8:continue
        network,gateway,mask=(int.from_bytes(bytes.fromhex(row[i]),'little') for i in (1,2,7))
        if int(row[3],16)&1 and dest&mask==network:
            routes.append((mask.bit_count(),int(row[6]),row[0],gateway,network))
    if not routes:raise ValueError('internal_route_missing')
    prefix=max(r[0] for r in routes);metric=min(r[1] for r in routes if r[0]==prefix)
    selected=[r for r in routes if r[0]==prefix and r[1]==metric]
    if len(selected)!=1:raise ValueError('ambiguous_internal_route')
    prefix,metric,interface,gateway,network=selected[0]
    if gateway or prefix==0 or interface=='lo':raise ValueError('routed_or_loopback_HTTP_forbidden')
    return interface,ipaddress.ip_network((network,prefix))


def connected_endpoint(destination,subnet):
    if sys.platform!='linux' or not Path('/.dockerenv').is_file():raise ValueError('Linux_Docker_network_required')
    interface,route_network=route_for(destination)
    if route_network!=subnet:raise ValueError('HTTP_route_not_configured_Docker_subnet')
    if link_kind(interface)!='veth':raise ValueError('Docker_veth_required_no_host_or_physical_LAN_HTTP')
    address=interface_ipv4(interface)
    if address.network!=subnet or address.ip==ipaddress.ip_address(destination):raise ValueError('HTTP_interface_subnet_or_self_destination_mismatch')
    return str(address.ip),interface


def docker_dns_service(host):
    # Use the user-defined Docker network resolver, never an extra_hosts/host-gateway alias.
    resolvers=[line.split()[1] for line in Path('/etc/resolv.conf').read_text().splitlines() if line.split()[:1]==['nameserver']]
    if resolvers!=['127.0.0.11']:raise ValueError('Docker_embedded_DNS_required')
    for line in Path('/etc/hosts').read_text().splitlines():
        values=line.partition('#')[0].split()
        if host in [v.lower() for v in values[1:]]:raise ValueError('hosts_override_not_a_Docker_service')
