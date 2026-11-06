"""From repo root: python services/api/dev.py init|up|seed|down."""
import argparse
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.request import Request, urlopen
from uuid import uuid4

HERE=Path(__file__).resolve().parent
DB=HERE.parents[1]/"infra"/"db"
ENV=DB/".env"
LOCAL=HERE/".env"


def config(path):
    return dict(line.strip().split("=",1) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#"))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["init","up","down","seed"])
    a=p.parse_args().action
    if a=="init":
        subprocess.run([sys.executable,str(DB/"db.py"),"init"],check=True)
        if not LOCAL.exists():
            fd=os.open(LOCAL,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,"w",encoding="utf8") as f:
                f.write("COLLECTOR_TOKEN="+secrets.token_hex(32)+"\nAPI_PORT=8000\n")
        return
    if not ENV.exists() or not LOCAL.exists():
        p.error("run init first")
    if a in ("up","down"):
        compose=["docker","compose","--env-file",str(ENV),"--env-file",str(LOCAL),"-f",str(DB/"compose.yaml"),
                 "-f",str(DB/"api.compose.yaml")]
        subprocess.run(compose+(["up","-d","--build","--wait","--wait-timeout","240"] if a=="up" else ["down"]),check=True)
        return
    cfg=config(LOCAL)
    base="http://127.0.0.1:"+os.environ.get("API_PORT",cfg.get("API_PORT","8000"))
    run_id=uuid4()
    url=f"{base}/internal/v2/crawl-runs/{run_id}/observations"
    data=json.loads((HERE/"fixtures"/"offer.json").read_text(encoding="utf8"))
    start=datetime.now(UTC)-timedelta(seconds=2)
    for i,(price,suffix) in enumerate([("12000.0000","original"),("11500.0000","updated")]):
        data.update(price=price,url="https://store.example.test/p/"+suffix,observation_key=f"{run_id}:{i}",
                    observed_at=(start+timedelta(seconds=i)).isoformat())
        req=Request(url,data=json.dumps(data).encode(),headers={"Content-Type":"application/json",
                    "Authorization":"Bearer "+cfg["COLLECTOR_TOKEN"]})
        with urlopen(req, timeout=15) as resp:
            print(resp.status,json.load(resp))
    with urlopen(base+"/v2/offers?selected_domain=product",timeout=15) as resp:
        print(json.dumps(json.load(resp),ensure_ascii=False))


if __name__=="__main__":
    main()
