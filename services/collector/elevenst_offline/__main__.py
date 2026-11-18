"""Counts-only offline CLI. Never prints product data, input URLs or secrets."""
import argparse
import json
import sys
from pathlib import Path
from .collector import OfflineCollector
from .parser import MAX_BYTES
from .live import require_live_transport


def main(argv=None):
    parser = argparse.ArgumentParser(description='11st saved JSON replay; no HTTP or DB writes')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--format', choices=('listing', 'snapshot'), default='listing')
    parser.add_argument('--state-dir', type=Path, default=Path(__file__).parent / 'data')
    parser.add_argument('--observed-at', help='Original response timestamp with timezone; never replay time')
    parser.add_argument('--max-items', type=int)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args(argv)
    collector = OfflineCollector(args.state_dir)
    try:
        if args.live:
            require_live_transport()
        if args.status:
            result = collector.status()
        else:
            if not args.input:
                parser.error('--input is required unless --status')
            if args.input.stat().st_size > MAX_BYTES:
                raise ValueError('response_size_limit')
            if args.format == 'snapshot' and args.observed_at:
                parser.error('--observed-at cannot override original snapshot timestamps')
            result = collector.replay(args.input.read_text(encoding='utf-8-sig'),
                                      snapshot=args.format == 'snapshot', observed_at=args.observed_at,
                                      max_items=args.max_items, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, RecursionError):
        # Do not leak paths, arbitrary JSON or secrets via exception messages.
        print(json.dumps({'status': 'failed', 'reason': 'input_or_checkpoint_invalid_or_unavailable'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
