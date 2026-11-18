"""Metadata-only atomic checkpoint; normalized product contents stay in memory."""
import copy
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .parser import parse_listing, parse_snapshot


def now():
    return datetime.now(timezone.utc).isoformat()


def key(row):
    return json.dumps([row['source'], row['source_listing_id'], row['variant_key']], separators=(',', ':'), ensure_ascii=False)


@contextmanager
def writer_lock(directory):
    # OS advisory lock is released after a crash; no stale PID/lock deletion.
    fd = os.open(directory / 'writer.lock', os.O_CREAT | os.O_RDWR)
    locked = False
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b'0')
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield
    finally:
        if locked:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == 'nt':
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _blank():
    return dict(version=1, source='elevenst', listings={}, offers={}, archives={}, last_processed_at=None)


class OfflineCollector:
    def __init__(self, state_dir):
        self.directory = Path(state_dir).resolve()
        self.path = self.directory / 'checkpoint.json'
        self.records = {}  # ephemeral; no product DB/export side effects

    def _read(self):
        if not self.path.exists():
            return _blank()
        state = json.loads(self.path.read_text(encoding='utf-8'))
        if state.get('version') != 1 or state.get('source') != 'elevenst':
            raise ValueError('checkpoint_schema_mismatch')
        for field in ('listings', 'offers', 'archives'):
            if not isinstance(state.get(field), dict):
                raise ValueError('checkpoint_schema_mismatch')
        return state

    def status(self):
        state = self._read()
        return dict(source='elevenst', mode='OFFLINE', live_enabled=False, backend_enabled=False,
                    product_storage_enabled=False, unique_listing_ids=len(state['listings']),
                    verified_offers=sum(v['identity_status'] == 'verified_native_tuple' for v in state['offers'].values()),
                    quarantined_identities=sum(v['identity_status'] == 'quarantine_required' for v in state['offers'].values()),
                    completed_archives=sum(a['complete'] for a in state['archives'].values()),
                    last_processed_at=state['last_processed_at'])

    def _save(self, state):
        fd, filename = tempfile.mkstemp(prefix='checkpoint-', suffix='.tmp', dir=self.directory)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump(state, output, ensure_ascii=False, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(filename, self.path)
        finally:
            if os.path.exists(filename):
                os.unlink(filename)

    def replay(self, body, *, snapshot=False, observed_at=None, max_items=None, dry_run=False):
        if max_items is not None and (type(max_items) is not int or max_items < 1):
            raise ValueError('max_items_must_be_positive')
        rows, meta = parse_snapshot(body) if snapshot else parse_listing(body, observed_at)
        # Content hash includes replay mode and source observation time; not a product identity.
        archive = hashlib.sha256(json.dumps([snapshot, observed_at, body], ensure_ascii=False).encode()).hexdigest()
        if dry_run:
            return self._apply(self._read(), rows, meta, archive, max_items, persist=False)
        self.directory.mkdir(parents=True, exist_ok=True)
        with writer_lock(self.directory):
            return self._apply(self._read(), rows, meta, archive, max_items, persist=True)

    def _apply(self, state, rows, meta, archive, max_items, persist):
        resume = state['archives'].get(archive, {'cursor': 0, 'complete': False})
        start = resume['cursor']
        if type(start) is not int or not 0 <= start <= len(rows):
            raise ValueError('checkpoint_cursor_invalid')
        end = min(len(rows), start + max_items) if max_items else len(rows)
        counts = dict(processed=0, new_listing_ids=0, new_offers=0, known_offers=0, quarantined=0,
                      stale_observations=0, duplicate_items=meta['duplicate_items'], rejected=len(meta['rejected']))
        memory = copy.deepcopy(self.records)
        for row in rows[start:end]:
            pid, ident = row['source_listing_id'], key(row)
            counts['processed'] += 1
            counts['new_listing_ids'] += pid not in state['listings']
            counts['known_offers' if ident in state['offers'] else 'new_offers'] += 1
            counts['quarantined'] += row['identity_status'] == 'quarantine_required'
            previous = state['offers'].get(ident)
            stamp = row['observed_at']
            last = previous.get('last_observed_at') if previous else None
            # Unknown replay timestamps cannot advance or replace dated observations.
            fresh = not previous or not last or (stamp is not None and datetime.fromisoformat(stamp.replace('Z', '+00:00')) > datetime.fromisoformat(last.replace('Z', '+00:00')))
            if fresh:
                memory[ident] = copy.deepcopy(row)
                state['offers'][ident] = dict(source='elevenst', source_listing_id=pid, variant_key=row['variant_key'],
                                             identity_status=row['identity_status'], last_observed_at=stamp)
            else:
                counts['stale_observations'] += 1
            state['listings'].setdefault(pid, {'first_processed_at': now()})
        state['archives'][archive] = dict(cursor=end, complete=end == len(rows),
                                          native_page=meta['native_page'], next_page=meta['next_page'])
        state['last_processed_at'] = now()
        if persist:
            self._save(state)
            self.records = memory  # do not publish partial state on disk failure
        return dict(**counts, cursor=end, complete=end == len(rows), resumed_from=start,
                    unique_listing_ids=len(state['listings']), next_page=meta['next_page'],
                    actual_http_requests=0, backend_requests=0, product_storage_enabled=False,
                    dry_run=not persist)
