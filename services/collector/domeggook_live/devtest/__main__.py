"""Explicitly approved disposable PostgreSQL test; never uses a team DB or real products."""
import argparse,json,os,subprocess,sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--approve-synthetic',action='store_true',required=True)
    p.add_argument('--work-dir',type=Path,required=True)
    p.add_argument('--backend-dir',type=Path,required=True,help='Read-only services/api directory with kkulpick/ and migrations/')
    p.add_argument('--pg-bin',type=Path,required=True,help='PostgreSQL bin directory; binaries are never downloaded implicitly')
    a=p.parse_args();root=a.work_dir.resolve();backend=a.backend_dir.resolve();binary=a.pg_bin.resolve()
    if not (backend/'kkulpick/models.py').is_file() or not (backend/'kkulpick/ingest.py').is_file() or not (backend/'migrations/versions/catalog.sql').is_file():p.error('backend model/ingest/catalog SQL required')
    if not (binary/'postgres.exe').is_file():p.error('this optional harness requires approved Windows PostgreSQL binaries')
    if root==backend or root==binary or root in (backend.parents[0],binary.parents[0]):p.error('use a separate disposable work directory')
    if (root/'pgdata/PG_VERSION').exists() and not (root/'approval_manifest.json').exists():p.error('unrecognized existing DB directory; refusing to initialize')
    root.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,KKULPICK_DEVTEST_APPROVED='1',KKULPICK_DEVTEST_ROOT=str(root),KKULPICK_DEVTEST_BACKEND=str(backend),
        KKULPICK_DEVTEST_PG_BIN=str(binary),KKULPICK_STATE_DIR=str(root/'collector_state'),PYTHONUTF8='1')
    repo=Path(__file__).resolve().parents[4];package='services.collector.domeggook_live'
    result=subprocess.run([sys.executable,'-B','-m','pytest','-q',str(Path(__file__).resolve().parents[1]/'tests')],cwd=repo,env=env)
    (root/'mock_results.json').write_text(json.dumps({'status':'passed' if result.returncode==0 else 'failed','HTTP_provider':0,'synthetic_only':True}),encoding='utf-8')
    if result.returncode:return result.returncode
    for module in ('setup_pg','run_integration'):
        result=subprocess.run([sys.executable,'-B','-m',package+'.devtest.'+module],cwd=repo,env=env)
        if result.returncode:return result.returncode
    return 0

if __name__=='__main__':raise SystemExit(main())
