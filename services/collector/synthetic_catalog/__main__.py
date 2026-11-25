import argparse
import json
from .generate import generate


def main(argv=None):
    p=argparse.ArgumentParser(description='Synthetic-only resumable JSONL generator; no HTTP/DB')
    p.add_argument('--output',required=True)
    p.add_argument('--count',type=int,choices=(1000,10000,100000,1000000),required=True)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--batch-size',type=int,default=10000)
    p.add_argument('--max-parts',type=int)
    args=p.parse_args(argv)
    try:
        print(json.dumps(generate(args.output,args.count,args.seed,args.batch_size,args.max_parts)));return 0
    except Exception:
        print(json.dumps({'status':'blocked','reason':'output_settings_or_integrity_requires_review','automatic_reset':False}));return 2


if __name__=='__main__':raise SystemExit(main())
