import copy
from contextlib import redirect_stdout
from datetime import datetime,timezone,timedelta
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from services.collector.unified_live.mock import fixture_config,FakeHTTP,product,LIST,run_mock
from services.collector.unified_live.policy import validate,url,interval
from services.collector.unified_live.parser import normalize,links
from services.collector.unified_live.engine import URLWorker
from services.collector.unified_live.transport import SafeHTTP,Wait,public_address
from services.collector.unified_live.changes import ChangeDelivery
from services.collector.unified_live.food import evidence
from services.collector.unified_live.registry import register
from services.collector.unified_live.used import ScheduledWorker,LatestUsedAdapter,used_interval
from services.collector.unified_live.account import AccountWorker
from services.collector.unified_live.backend import ApprovedOutbox
from services.collector.unified_live.__main__ import main
from services.collector.collector_ops.mock import SimulatedDelivery
from services.collector.marketplace_live.synthetic import SyntheticHTTP
from services.collector.marketplace_live.tests.fixtures import config,ebay
from services.collector.domeggook_live.domeggook_delivery import atomic,load

class UnifiedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.cfg=fixture_config();self.now=datetime.now(timezone.utc)
    def tearDown(self):self.tmp.cleanup()
    def box(self,cfg=None,root=None,responses=None):return SimulatedDelivery(cfg or self.cfg,root or self.root/self.cfg['source'],clock=lambda:self.now,responses=responses)
    def worker(self,http=None,box=None,cfg=None):return URLWorker(cfg or self.cfg,self.root,transport=http or FakeHTTP(),delivery=box or self.box(),clock=lambda:self.now)
    def test_URL_pipeline_new_unchanged_and_price_update_ACK(self):
        result=run_mock(self.root)
        self.assertEqual(result['external_HTTP_requests'],0);self.assertEqual(result['DB_writes'],0)
        self.assertEqual(result['simulated_team_API_requests'],2);self.assertTrue(result['unchanged_no_API_write'])
        self.assertEqual(result['content_changes'],{'new':1,'unchanged':1,'updated':1})
    def test_JSONLD_native_fields_unknown_stock_not_invented(self):
        r=normalize(product(),'https://store.example.test/item/1',self.now.isoformat(),self.cfg)
        self.assertEqual((r['condition'],r['availability'],r['currency']),('used','available','USD'))
        self.assertIsNone(r['metadata']['stock_quantity']);self.assertTrue(r['metadata']['purchase_available'])
        self.assertNotIn('seller',r['observation']);self.assertIn('description',r['observation'])
    def test_missing_fields_and_refurbished_held(self):
        for before,after,missing in [('"priceCurrency": "USD"','"priceCurrency": null','currency'),('UsedCondition','RefurbishedCondition','condition'),('"name": "SYNTHETIC seller"','"name": null','seller'),('InStock','PreOrder','availability')]:
            with self.subTest(missing=missing):
                r=normalize(product().replace(before,after),'https://store.example.test/item/1',self.now.isoformat(),self.cfg)
                self.assertIsNone(r['observation']);self.assertIn(missing,r['missing_fields'])
    def test_multiple_offers_and_variants_fail_closed(self):
        html=product().replace('"@type": "Offer"','"@type": "AggregateOffer"')
        with self.assertRaisesRegex(ValueError,'variant'):normalize(html,self.cfg['base_url'],self.now.isoformat(),self.cfg)
    def test_HTML_CSS_adapter_extracts_native_fields(self):
        cfg=copy.deepcopy(self.cfg);cfg['selectors']={k:'#'+k for k in ('id','name','price','currency','seller','condition','availability')}
        html=''.join(f'<span id="{k}">{v}</span>' for k,v in {'id':'SYNTHETIC-1','name':'keyboard','price':'10.25','currency':'USD','seller':'SYNTHETIC seller','condition':'used','availability':'available'}.items())
        r=normalize(html,self.cfg['base_url'],self.now.isoformat(),cfg);self.assertEqual(r['price'],'10.25');self.assertIsNotNone(r['observation'])
    def test_list_dedup_and_same_origin_pagination(self):
        found,more=links(LIST+'<a rel="next" href="/page/2">Next</a>',self.cfg['base_url'],self.cfg)
        self.assertEqual(len(found),1);self.assertEqual(more,'https://store.example.test/page/2')
    def test_URL_credentials_private_addresses_and_cross_origin_rejected(self):
        for u in ('http://store.example.test','https://127.0.0.1','https://user:pass@store.example.test','https://store.example.test/?api_key=secret','https://localhost','https://store.example.test:8443','https://other.example.test'):
            with self.subTest(url=u),self.assertRaises(ValueError):url(u,'store.example.test')
        self.assertEqual(url('https://store.example.test/item?utm_source=a&id=1#x'),'https://store.example.test/item?id=1')
        self.assertEqual(url('https://store.example.test/search?keyword=keyboard'),'https://store.example.test/search?keyword=keyboard')
    def test_DNS_mixed_public_private_rejected(self):
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',443)),(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(Wait):public_address('store.example.test')
    def test_dedicated_adapter_preferred_and_unknown_settings_rejected(self):
        cfg=copy.deepcopy(self.cfg);cfg.update(base_url='https://www.ebay.com/',allowed_product_hosts=['www.ebay.com'])
        with self.assertRaisesRegex(ValueError,'dedicated_adapter'):validate(cfg)
        cfg=copy.deepcopy(self.cfg);cfg['api_key']='SYNTHETIC_SECRET'
        with self.assertRaises(ValueError):validate(cfg)
    def test_registration_idempotent_but_not_silent_overwrite(self):
        register(self.cfg,self.root);register(self.cfg,self.root)
        cfg=copy.deepcopy(self.cfg);cfg['queries']=['other']
        with self.assertRaises(ValueError):register(cfg,self.root)
    def test_robots_disallow_prevents_product_request(self):
        http=SafeHTTP(self.cfg,self.root,clock=lambda:self.now)
        with patch.object(http,'_get',return_value=(200,'User-agent: *\nDisallow: /','text/plain')) as fetch:
            with self.assertRaisesRegex(Wait,'robots_disallowed'):http.fetch('https://store.example.test/item/1')
            self.assertEqual(fetch.call_count,1)
    def test_robots_failure_not_equivalent_to_allow(self):
        http=SafeHTTP(self.cfg,self.root,clock=lambda:self.now)
        with patch.object(http,'_get',return_value=(410,'','text/plain')):
            with self.assertRaises(Wait):http.fetch(self.cfg['base_url'])
    def test_request_budget_and_ledger_restart(self):
        cfg=copy.deepcopy(self.cfg);cfg['requests_per_hour']=1
        http=SafeHTTP(cfg,self.root,clock=lambda:self.now);entry=http.reserve(cfg['base_url']);entry['status']=200;http.save()
        self.now+=timedelta(seconds=2)
        http=SafeHTTP(cfg,self.root,clock=lambda:self.now)
        with self.assertRaisesRegex(Wait,'budget_wait'):http.reserve(cfg['base_url'])
        self.assertEqual(len(http.state['requests']),1)
    def test_interrupted_request_holds_no_replay(self):
        http=SafeHTTP(self.cfg,self.root,clock=lambda:self.now);http.reserve(self.cfg['base_url'])
        restored=SafeHTTP(self.cfg,self.root,clock=lambda:self.now)
        with self.assertRaisesRegex(Wait,'uncertain'):restored.reserve(self.cfg['base_url'])
        self.assertEqual(len(restored.state['requests']),1)
    def test_network_uncertainty_holds_without_raw_exception(self):
        http=SafeHTTP(self.cfg,self.root,clock=lambda:self.now)
        with patch('services.collector.unified_live.transport.public_address',return_value='93.184.216.34'),patch('services.collector.unified_live.transport.PinnedHTTPS',side_effect=OSError('PRIVATE_KEY_VALUE')):
            with self.assertRaises(Wait):http._get(self.cfg['base_url'])
        self.assertNotIn('PRIVATE_KEY_VALUE',http.path.read_text());self.assertIsNotNone(http.state['hold'])
    def test_429_retry_after_and_503_backoff(self):
        for code in (429,503):
            with self.subTest(code=code):
                path=self.root/str(code);http=SafeHTTP(self.cfg,path,clock=lambda:self.now)
                response=Mock(status=code);response.getheader.side_effect=lambda name,default=None:'120' if name=='Retry-After' else default
                connection=Mock();connection.getresponse.return_value=response
                with patch('services.collector.unified_live.transport.public_address',return_value='93.184.216.34'),patch('services.collector.unified_live.transport.PinnedHTTPS',return_value=connection):
                    with self.assertRaises(Wait) as exc:http._get(self.cfg['base_url'])
                self.assertGreaterEqual(exc.exception.until,self.now+timedelta(seconds=120))
    def test_401_403_redirect_require_review(self):
        for code in (401,403,302):
            with self.subTest(code=code):
                http=SafeHTTP(self.cfg,self.root/str(code),clock=lambda:self.now);response=Mock(status=code)
                connection=Mock();connection.getresponse.return_value=response
                with patch('services.collector.unified_live.transport.public_address',return_value='93.184.216.34'),patch('services.collector.unified_live.transport.PinnedHTTPS',return_value=connection):
                    with self.assertRaises(Wait):http._get(self.cfg['base_url'])
                self.assertIsNotNone(http.state['hold'])
    def test_60_and_7200_schedule_and_restart_restore(self):
        for mode,seconds in (('used',60),('general',7200)):
            with self.subTest(mode=mode):
                cfg=copy.deepcopy(self.cfg);cfg['mode']=mode
                root=self.root/mode;box=self.box(cfg,root/cfg['source']);http=FakeHTTP()
                worker=URLWorker(cfg,root,transport=http,delivery=box,clock=lambda:self.now);worker.step();worker.step()
                self.assertEqual(worker.state['next_cycle_at'],(self.now+timedelta(seconds=seconds)).isoformat())
                calls=len(http.state['requests']);worker.close()
                restored=URLWorker(cfg,root,transport=http,delivery=box,clock=lambda:self.now);restored.step()
                self.assertEqual(calls,len(http.state['requests']));restored.close()
    def test_checkpoint_context_change_or_missing_queue_fails_closed(self):
        worker=self.worker();worker.step();worker.step();worker.close()
        cfg=copy.deepcopy(self.cfg);cfg['queries']=['new query']
        with self.assertRaises(ValueError):self.worker(cfg=cfg)
    def test_interrupted_URL_task_does_not_replay(self):
        worker=self.worker();worker.state['inflight']=True;worker.save();worker.close()
        restored=self.worker();restored.step();self.assertIn('interrupted',restored.state['hold']);self.assertEqual(restored.http.state['requests'],[]);restored.close()
    def test_disappearing_search_or_detail_not_sold_automatically(self):
        http=FakeHTTP();worker=self.worker(http);worker.step();worker.step();old=worker.state['known'].copy()
        self.now+=timedelta(seconds=60);http.pages['https://store.example.test/item/1']=(404,'')
        worker.step();worker.step()
        self.assertTrue(worker.state['known']['https://store.example.test/item/1']['verification_required'])
        self.assertEqual(len(worker.delivery.box.fake_API.calls),1);worker.close()
    def test_site_structure_change_is_hold_not_mass_deletion(self):
        http=FakeHTTP();worker=self.worker(http);worker.step();worker.step();self.now+=timedelta(seconds=60)
        for target in list(worker.state['shape']):pass
        http.pages['https://store.example.test/search?page=1&q=keyboard']=(200,'<html><h1>Layout changed</h1></html>')
        worker.step();self.assertIn('structure',worker.state['hold']);self.assertEqual(len(worker.state['known']),1);worker.close()
    def test_unchanged_pending_and_crash_recovery_keep_same_event_key(self):
        box=self.box(responses=[(503,{})]);r=normalize(product(),self.cfg['base_url'],self.now.isoformat(),self.cfg)
        box.stage(r);original=r['observation']['observation_key']
        gate=ChangeDelivery(box,self.root/self.cfg['source']);box.flush();self.now+=timedelta(seconds=6)
        new=normalize(product(),self.cfg['base_url'],self.now.isoformat(),self.cfg)
        self.assertEqual(gate.stage(new)['status'],'unchanged_skipped');box.flush()
        self.assertEqual([call[1]['observation_key'] for call in box.fake_API.calls],[original,original])
    def test_price_and_state_updates_wait_for_prior_ACK(self):
        box=self.box();gate=ChangeDelivery(box,self.root/self.cfg['source'])
        r=normalize(product(),self.cfg['base_url'],self.now.isoformat(),self.cfg);gate.stage(r)
        changed=normalize(product('10.00','SoldOut'),self.cfg['base_url'],self.now.isoformat(),self.cfg)
        self.assertIn('pending',gate.stage(changed)['status']);box.flush();self.assertEqual(gate.stage(changed)['status'],'pending')
    def test_food_raw_normalized_percentage_cross_contact_separate(self):
        fields={'name':'식품 시리얼','category':'food','ingredients':'밀 60%, 설탕','allergens':'밀, 우유','cross_contact':'땅콩','brand':'SYNTHETIC'}
        e=evidence(fields,source='html_synthetic',url=self.cfg['base_url'],at=self.now.isoformat())
        self.assertEqual(e['ingredients_normalized'][0],{'name':'밀','percentage':'60'})
        self.assertIn('wheat',e['allergens_declared']);self.assertIn('peanut',e['allergens_possible_cross_contact'])
        self.assertIsNone(e['safe_to_consume']);self.assertEqual(e['evidence_url'],self.cfg['base_url'])
    def test_food_missing_negative_and_changed_need_review(self):
        for allergens in (None,'없음'):
            with self.subTest(allergens=allergens):
                e=evidence({'name':'식품','category':'food','allergens':allergens},source='html_synthetic',url=self.cfg['base_url'],at=self.now.isoformat(),previous_hash='different')
                self.assertTrue(e['requires_review']);self.assertTrue(e['changed']);self.assertIsNone(e['safe_to_consume'])
    def test_food_held_and_raw_persistence_requires_additional_grant(self):
        cfg=copy.deepcopy(self.cfg);http=FakeHTTP();foodhtml=product().replace('"@type": "Product"','"@type": "Product", "category":"food", "ingredients":"밀 60%", "allergens":"밀"')
        http.pages['https://store.example.test/item/1']=(200,foodhtml)
        worker=self.worker(http,cfg=cfg);worker.step();worker.step()
        self.assertEqual(worker.delivery.pending_count(),0);self.assertFalse((worker.root/'evidence').exists());worker.close()
    def test_optional_JS_renderer_is_used_without_real_browser(self):
        cfg=copy.deepcopy(self.cfg);cfg['render_javascript']=True;renderer=Mock();renderer.render.side_effect=lambda target,http:LIST if '/search?' in target else product()
        worker=URLWorker(cfg,self.root,transport=FakeHTTP(),delivery=self.box(),renderer=renderer,clock=lambda:self.now);worker.step();worker.step()
        self.assertEqual(renderer.render.call_count,2);self.assertEqual(worker.state['totals']['products_success'],1);worker.close()
    def test_challenge_login_page_stops_parser(self):
        for html in ('<title>Just a moment</title>','<input type="password">'):
            with self.subTest(html=html),self.assertRaises(ValueError):normalize(html,self.cfg['base_url'],self.now.isoformat(),self.cfg)
    def test_ebay_latest_used_filter_and_60_schedule_reuse(self):
        cfg=config('ebay_browse');cfg['collection_profile']='ebay_used';cfg['page_size']=3
        http=SyntheticHTTP('ebay_browse')
        http.close=lambda:None
        for row in http.rows:row.update(conditionId='3000',condition='Used',itemOriginDate=self.now.isoformat())
        adapter=LatestUsedAdapter(cfg,http,credential_reader=lambda _: 'SYNTHETIC')
        original=http.get_json;calls=[]
        def capture(target,**kw):calls.append((target,kw));return original(target,**kw)
        http.get_json=capture
        box=self.box(cfg,self.root/'ebay_browse');gate=ChangeDelivery(box,self.root/'ebay_browse')
        worker=ScheduledWorker(cfg,self.root,http=http,adapter=adapter,delivery=gate,clock=lambda:self.now,schedule={'mode':'used','policy_reference':'SYNTHETIC','provider_min_interval_seconds':60})
        for _ in range(4):worker.step()
        params=next(opts['params'] for target,opts in calls if target.endswith('/search'))
        self.assertEqual(params['sort'],'newlyListed');self.assertIn('conditions:{USED}',params['filter'])
        self.assertEqual(worker.state['next_cycle_at'],(self.now+timedelta(seconds=60)).isoformat())
        self.assertTrue(worker.state['latest_listing_watermarks']);worker.close()
    def test_policy_minimum_and_missing_approval_do_not_force_60(self):
        self.assertEqual(used_interval({})[0],7200)
        self.assertEqual(used_interval({'mode':'used','policy_reference':'SYNTHETIC','provider_min_interval_seconds':300})[0],300)
        self.assertEqual(interval(dict(self.cfg,mode='general')),7200)
    def test_account_isolates_one_member_error_and_uses_one_ledger(self):
        general=Mock();used=Mock();http=Mock();http.state={'hold':None,'requests':[{'status':200}]}
        used.step.side_effect=ValueError();used.state={};general.report.return_value={'hold':None};used.report.return_value={'hold':'review'}
        account=AccountWorker(general,used,http);r=account.step()
        general.step.assert_called_once();used.save.assert_called_once();self.assertEqual(r['HTTP_attempts'],1);self.assertTrue(r['shared_ledger_single_writer'])
    def test_backend_send_approval_independent_from_queue(self):
        cfg=self.cfg
        with patch.dict(os.environ,{'COLLECTOR_DELIVERY_APPROVED':'no'}):
            box=ApprovedOutbox(cfg,self.root,transport=Mock(),clock=lambda:self.now)
            box.stage(normalize(product(),self.cfg['base_url'],self.now.isoformat(),self.cfg));box.flush();box.transport.assert_not_called()
    def test_domeggook_native_food_and_permission_gates_reused_with_content_dedup(self):
        from services.collector.unified_live.dome import DomeBridge,DomeContent
        from services.collector.domeggook_live.fixture_data import row,config as dome_config
        calls=[]
        def api(path,body):calls.append(body);return 201,{'state':'applied','change_kind':'created'}
        cfg=dome_config();bridge=DomeBridge(cfg,self.root,transport=api);box=DomeContent(bridge,self.root)
        original=row(stamp=(self.now-timedelta(minutes=2)).isoformat())
        self.assertEqual(box.stage(original)['status'],'pending')
        with patch.dict(os.environ,{'COLLECTOR_DELIVERY_APPROVED':'no'}):box.flush()
        self.assertEqual(len(calls),0)
        with patch.dict(os.environ,{'COLLECTOR_DELIVERY_APPROVED':'yes'}):box.flush()
        another=dict(original,observed_at=(self.now-timedelta(minutes=1)).isoformat())
        result=box.stage(another);self.assertTrue(result['unchanged']);self.assertEqual(len(calls),1)
        self.assertEqual(box.report()['content_changes']['unchanged'],1);box.close()
    def test_compose_isolated_project_persistent_health_and_deny_defaults(self):
        deploy=Path(__file__).parents[1]/'deploy';compose=json.loads((deploy/'compose.yaml').read_text())
        self.assertEqual(compose['name'],'kkulpick-collectors-v2');self.assertNotIn('ebay_used',compose['services'])
        for name,svc in compose['services'].items():
            with self.subTest(service=name):
                self.assertNotIn('container_name',svc);self.assertNotIn('ports',svc);self.assertNotIn('network_mode',svc)
                self.assertEqual(svc['restart'],'unless-stopped');self.assertTrue(svc['read_only']);self.assertTrue(svc['healthcheck'])
                self.assertIn(':-no}',svc['environment']['COLLECTOR_RUN_APPROVED']);self.assertIn(':-no}',svc['environment']['COLLECTOR_DELIVERY_APPROVED'])
                if name!='url':self.assertTrue(any('/state/unified_ops/' in v for v in svc['volumes']))
        self.assertIn('!services/collector/unified_live/*.py',(deploy/'Dockerfile.dockerignore').read_text())
        self.assertEqual(compose['services']['ebay']['command'][4],'ebay_account')
    def test_cli_disabled_watch_health_and_plan_zero_network(self):
        cfg=copy.deepcopy(self.cfg);cfg['enabled']=False;cfg['rights']['reference']='';path=self.root/'cfg.json';path.write_text(json.dumps(cfg))
        args=['--provider','url','--config',str(path),'--state-dir',str(self.root/'state')]
        output=io.StringIO()
        with redirect_stdout(output):self.assertEqual(main(args+['--plan']),1);self.assertEqual(main(args+['--watch','--max-ticks','1']),0)
        self.assertEqual(main(['--provider','url','--health','--state-dir',str(self.root/'state')]),0)
        self.assertFalse((self.root/'state'/cfg['source']).exists());self.assertIn('"HTTP_requests_this_command": 0',output.getvalue())

if __name__=='__main__':unittest.main()
