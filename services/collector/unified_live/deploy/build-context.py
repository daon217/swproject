"""Export exactly Dockerfile COPY inputs; never send .env/Git/cache/data to a builder."""
import argparse,glob,hashlib,json,shutil
from pathlib import Path

def export(repo,destination):
    repo=Path(repo).resolve();destination=Path(destination).resolve()
    if destination==repo or repo in destination.parents:raise ValueError('build_context_must_be_outside_repository')
    if destination.exists():raise ValueError('new_build_context_required_no_overwrite')
    docker=repo/'services/collector/unified_live/deploy/Dockerfile'
    inputs=[]
    for line in docker.read_text(encoding='utf-8').splitlines():
        if not line.startswith('COPY '):continue
        pattern=line.split()[1]
        if pattern.startswith('/') or '..' in Path(pattern).parts:raise ValueError('relative_reviewed_COPY_required')
        matched=glob.glob(str(repo/pattern))
        if not matched:raise ValueError('Docker_COPY_input_missing')
        for item in matched:
            p=Path(item)
            if p.is_symlink() or not p.is_file():raise ValueError('ordinary_source_files_only')
            p.resolve().relative_to(repo);inputs.append(p)
    destination.mkdir(parents=True)
    manifest=[]
    for p in sorted(set(inputs)):
        relative=p.relative_to(repo);out=destination/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,out)
        manifest.append({'path':relative.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    shutil.copyfile(docker,destination/'Dockerfile')
    (destination/'.dockerignore').write_text('**\n!Dockerfile\n!services/\n!services/**\n',encoding='utf-8')
    (destination/'build-inputs.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return {'context':str(destination),'input_files':len(manifest),'Git_secrets_caches_datasets_included':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(export(a.repo,a.output)))
