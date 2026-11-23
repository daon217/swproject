"""Lock-aware state snapshots. Never delete/reset state or overwrite an archive."""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tarfile
from services.collector.domeggook_live.runtime import FileState


def backup(root,archive):
    root=Path(root).resolve();archive=Path(archive).resolve()
    if not root.is_dir() or archive.exists() or archive.is_relative_to(root):
        raise ValueError('existing_state_and_new_external_archive_required')
    if any(p.is_symlink() for p in root.rglob('*')):raise ValueError('review_symlink_state_before_backup')
    archive.parent.mkdir(parents=True,exist_ok=True)
    partial=archive.with_name(archive.name+'.partial')
    if partial.exists():raise ValueError('unfinished_archive_requires_review')
    with ExitStack() as stack:
        for lock in sorted(root.rglob('writer.lock')):
            stack.enter_context(FileState(lock.parent).lock())
        with tarfile.open(partial,'x') as tar:
            # Heartbeats are live diagnostics, not checkpoints or request history.
            for p in sorted(root.rglob('*')):
                rel=p.relative_to(root)
                if 'ops' in rel.parts or p.name=='writer.lock':continue
                if p.is_file():tar.add(p,arcname=rel.as_posix(),recursive=False)
        with partial.open('rb+') as stream:os.fsync(stream.fileno())
        os.replace(partial,archive)
    digest=hashlib.sha256()
    with archive.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):digest.update(block)
    return {'archive':str(archive),'sha256':digest.hexdigest(),'state_deleted':False,'HTTP_requests':0}


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state-root',required=True);p.add_argument('--archive',required=True)
    args=p.parse_args()
    try:print(json.dumps(backup(args.state_root,args.archive)));return 0
    except Exception:
        print(json.dumps({'status':'blocked','reason':'stop_all_state_writers_or_review_archive_paths','state_deleted':False}));return 2


if __name__=='__main__':raise SystemExit(main())
