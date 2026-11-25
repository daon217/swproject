import argparse
import json
from pathlib import Path
from .taxonomy import Taxonomy
from .build import audit_source,plan,build
from .verify import verify


def main(argv=None):
    p=argparse.ArgumentParser(description='Preserve v1 samples; classify/enrich a separate synthetic view')
    p.add_argument('--source',required=True);p.add_argument('--output')
    p.add_argument('--taxonomy');p.add_argument('--minimum-total',type=int,default=1000000)
    modes=p.add_mutually_exclusive_group();modes.add_argument('--plan',action='store_true');modes.add_argument('--verify',action='store_true')
    p.add_argument('--batch-size',type=int,default=10000);p.add_argument('--max-parts',type=int)
    p.add_argument('--report');p.add_argument('--sample')
    args=p.parse_args(argv)
    def progress(data):
        current=data.get('committed',data.get('validated',0))
        if current%100000==0 or current==data['target']:print(json.dumps({'progress':data}),flush=True)
    try:
        for target in (args.report,args.sample):
            if target and any(Path(target).resolve().is_relative_to(Path(p).resolve()) for p in (args.source,args.output) if p):
                raise ValueError('reports_must_be_outside_source_and_immutable_view')
        if args.plan:
            tax=Taxonomy(args.taxonomy) if args.taxonomy else Taxonomy()
            audit=audit_source(args.source,tax);result={'audit':audit,'plan':plan(audit,tax,args.minimum_total),'API_requests':0,'DB_writes':0}
        elif args.verify:
            if not args.output:raise ValueError('output_required')
            result=verify(args.source,args.output,progress=progress,sample_path=args.sample)
        else:
            if not args.output:raise ValueError('output_required')
            result=build(args.source,args.output,args.taxonomy,args.minimum_total,args.batch_size,args.max_parts,progress)
        if args.report:
            path=Path(args.report);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=True));return 0
    except Exception as exc:
        print(json.dumps({'status':'blocked','reason':'classification_integrity_or_configuration_requires_review',
                          'exception_type':type(exc).__name__,'source_overwritten':False}));return 2


if __name__=='__main__':raise SystemExit(main())
