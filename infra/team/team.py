"""Private team access to the existing Docker development catalog. Requires Python 3.10+."""
import argparse
import base64
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import subprocess
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
LOCAL=HERE/"local"
KEYS=LOCAL/"authorized_keys"
HOST=LOCAL/"bind_address"
NETWORKS=[ipaddress.ip_network(n) for n in ("127.0.0.0/8","10.0.0.0/8","172.16.0.0/12",
                                              "192.168.0.0/16","100.64.0.0/10")]


def address(s):
    ip=ipaddress.ip_address(s)
    if not any(ip in n for n in NETWORKS):
        raise ValueError("use a specific private IPv4 address assigned to this host")
    return str(ip)


def atomic(path,data):
    temp=path.with_suffix(".tmp")
    temp.write_text(data,encoding="ascii")
    temp.replace(path)


def enroll(label,public):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}",label):
        raise ValueError("use a short ASCII label (for example junseo)")
    words=Path(public).read_text(encoding="utf-8-sig").strip().split()
    if len(words)<2 or words[0]!="ssh-ed25519":
        raise ValueError("expected an OpenSSH Ed25519 .pub file")
    data=base64.b64decode(words[1],validate=True)
    if len(data)!=51 or data[:19]!=b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20":
        raise ValueError("invalid Ed25519 public key")
    rows=(KEYS.read_text().splitlines() if KEYS.exists() else [])
    for row in rows:
        parts=row.split()
        if parts[1]==words[1] and parts[2]!=label:
            raise ValueError("key already assigned to another label")
    rows=[r for r in rows if r.split()[2]!=label]
    atomic(KEYS,"\n".join(rows+["ssh-ed25519 "+words[1]+" "+label])+"\n")
    print("Enrolled",label,"SHA256:"+base64.b64encode(hashlib.sha256(data).digest()).decode().rstrip("="))
    print("Run 'up' to apply changes and close old tunnels.")


def compose(ip,*args):
    envs=[ROOT/"infra/db/.env",ROOT/"services/api/.env"]
    workspace=ROOT/"infra/workspace/.env"
    if workspace.is_file(): envs.append(workspace)
    if not all(p.is_file() for p in envs):
        raise ValueError("initialize the API first: python services/api/dev.py init")
    cmd=["docker","compose"]
    for p in envs: cmd+=["--env-file",str(p)]
    files=[ROOT/"infra/db/compose.yaml",ROOT/"infra/db/api.compose.yaml"]
    if workspace.is_file(): files.append(ROOT/"infra/workspace/compose.yaml")
    files.append(HERE/"team.compose.yaml")
    for p in files:
        cmd+=["-f",str(p)]
    subprocess.run(cmd+list(args),env=os.environ|{"TEAM_BIND_IP":address(ip)},check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="action",required=True)
    e=sub.add_parser("enroll");e.add_argument("label");e.add_argument("pub")
    u=sub.add_parser("up");u.add_argument("ip",nargs="?")
    sub.add_parser("home");sub.add_parser("stop");sub.add_parser("fingerprint")
    d=sub.add_parser("revoke");d.add_argument("label")
    args=p.parse_args()
    LOCAL.mkdir(exist_ok=True)
    if args.action=="enroll":
        enroll(args.label,args.pub);return
    if args.action=="revoke":
        rows=KEYS.read_text().splitlines()
        keep=[r for r in rows if r.split()[2]!=args.label]
        if len(keep)==len(rows): raise ValueError("unknown label")
        if HOST.exists(): compose(HOST.read_text().strip(),"stop","gateway")
        atomic(KEYS,"".join(r+"\n" for r in keep))
        print("Removed key; gateway stopped. Run up again for remaining users.");return
    if args.action=="home":
        exe=shutil.which("tailscale") or str(Path(os.getenv("ProgramFiles","C:/Program Files"))/"Tailscale"/"tailscale.exe")
        if not Path(exe).is_file(): raise ValueError("install Tailscale and sign in on the host first")
        ips=subprocess.check_output([exe,"ip","-4"],text=True).split()
        if len(ips)!=1 or ipaddress.ip_address(ips[0]) not in ipaddress.ip_network("100.64.0.0/10"):
            raise ValueError("no connected Tailscale IPv4 address; check tailscale status")
        args.action="up";args.ip=ips[0]
        print("Host VPN IP:",args.ip,flush=True)
    ip=getattr(args,"ip",None) or (HOST.read_text().strip() if HOST.exists() else None)
    if not ip: raise ValueError("first start: up <host private IPv4 address>")
    ip=address(ip)
    if args.action=="up":
        if not KEYS.is_file() or not KEYS.read_text().strip(): raise ValueError("enroll a teammate public key first")
        compose(ip,"up","-d","--build","api")
        compose(ip,"up","-d","--build","--no-deps","--force-recreate","gateway")
        atomic(HOST,ip+"\n")
    if args.action=="stop": compose(ip,"stop","gateway");return
    compose(ip,"exec","-T","gateway","ssh-keygen","-lf","/var/lib/team-ssh/ssh_host_ed25519_key.pub")


if __name__=="__main__":
    try: main()
    except (ValueError,OSError,subprocess.CalledProcessError) as exc: raise SystemExit(str(exc))
