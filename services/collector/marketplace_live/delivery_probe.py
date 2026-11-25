"""Separate team-API probe. Never queries suppliers; YES24 live POST is forbidden."""
import argparse
import copy
from datetime import datetime,timezone
import json
import os
from pathlib import Path
from services.collector.domeggook_live.runtime import FileState
from .config import SOURCES,load_config,rights
from .normalize import validate_body
from .delivery import Outbox

def check_payloads(payloads,cfg):
    if not isinstance(payloads,list) or not 1<=len(payloads)<=3:raise ValueError('one_to_three_observations_required')
    bodies=[]
    for item in payloads:
        if not isinstance(item,dict) or not isinstance(item.get('seller'),str) or not item['seller'].strip():
            raise ValueError('native_seller_evidence_required')
        body=item.get('observation')
        if not isinstance(body,dict):raise ValueError('observation_object_required')
        if body.get('source')!=cfg['source'] or body.get('result')!='success':raise ValueError('source_or_result_mismatch')
        for field in ('name','price','currency','condition','availability','url','source_listing_id','variant_key'):
            if body.get(field) in (None,''):raise ValueError('incomplete_observation_not_sent')
        validate_body(body,cfg)
        bodies.append(body)
    return bodies

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',choices=SOURCES,required=True)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--plan',action='store_true');mode.add_argument('--live',action='store_true')
    p.add_argument('--config',default=os.environ.get('KKULPICK_MARKETPLACE_CONFIG'))
    p.add_argument('--state-dir',default=os.environ.get('KKULPICK_MARKETPLACE_STATE_DIR'))
    p.add_argument('--payload-file')
    args=p.parse_args(argv)
    try:
        if args.source=='searchapi_google_shopping':
            print(json.dumps({'source':args.source,'status':'retired','reason':'use_serper_google_shopping','backend_HTTP_requests':0}));return 2
        if args.source=='yes24_api':
            print(json.dumps({'source':args.source,'status':'blocked','reason':'YES24_live_DB_ingestion_forbidden',
                              'provider_HTTP_requests':0,'backend_HTTP_requests':0}));return 2
        cfg=next(c for c in load_config(args.config) if c['source']==args.source)
        ready=(cfg['backend_enabled'] and cfg['backend_owner_approved'] and cfg['price_semantics_confirmed'] and
               rights(cfg,datetime.now(timezone.utc),storage=True) and bool(os.environ.get('KKULPICK_BACKEND_TOKEN')))
        if not args.live:
            print(json.dumps({'source':args.source,'mode':'delivery_plan','ready':ready,'provider_HTTP_requests':0,
                              'backend_HTTP_requests':0,'seller_persisted_by_current_contract':False}));return int(not ready)
        if not ready or not args.payload_file or not args.state_dir:raise ValueError('approved_payload_and_delivery_configuration_required')
        path=Path(args.payload_file)
        if path.stat().st_size>200000:raise ValueError('payload_file_too_large')
        payloads=check_payloads(json.loads(path.read_text(encoding='utf-8-sig')),cfg)
        # A dedicated queue cannot flush unrelated pre-existing production work.
        root=Path(args.state_dir).resolve()/args.source/'delivery-probe'
        with FileState(root/'lock').lock():
            outbox=Outbox(cfg,root)
            try:
                for body in payloads:outbox.stage({'observation':body})
                outbox.flush()
                result=outbox.report();result.update(mode='delivery_probe',provider_HTTP_requests=0,
                                                      seller_persisted_by_current_contract=False)
            finally:outbox.close()
        print(json.dumps(result));return int(bool(result['hold']) or result['pending']>0)
    except Exception:
        print(json.dumps({'status':'blocked','reason':'delivery_configuration_or_payload_requires_review'}));return 2

if __name__=='__main__':raise SystemExit(main())
