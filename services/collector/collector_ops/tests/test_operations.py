from contextlib import redirect_stdout
from datetime import datetime,timezone,timedelta
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch
from services.collector.collector_ops.__main__ import main,preflight,heartbeat
from services.collector.collector_ops.runtime import OpsWorker,source_status
from services.collector.collector_ops.mock import run_mock,SimulatedDelivery
from services.collector.collector_ops.secrets import load as load_secrets
from services.collector.collector_ops.dome import FoodDelivery
from services.collector.marketplace_live.tests.fixtures import config,ebay
from services.collector.marketplace_live.adapters import Adapter
from services.collector.marketplace_live.delivery import Outbox
from services.collector.domeggook_live.domeggook_delivery import atomic
from services.collector.marketplace_live.http import ProviderError
from services.collector.collector_ops.backup import backup
from services.collector.domeggook_live.runtime import FileState


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.cfg=config('ebay_browse');self.at=datetime.now(timezone.utc)
    def tearDown(self):self.tmp.cleanup()
    def test_all_existing_mock_pipelines_normalize_stage_and_process_API_ACK(self):
        for provider in ('ebay','ebay_used','yes24','serper','domeggook'):
            with self.subTest(provider=provider):
                r=run_mock(provider,self.root)
                self.assertEqual(r['external_HTTP_requests'],0);self.assertEqual(r['DB_writes'],0)
                self.assertTrue(r['synthetic_only']);self.assertGreater(r['simulated_team_API_requests'],0)
                if provider!='domeggook':
                    self.assertEqual((r['products_success'],r['products_held']),(2,1))
                    self.assertEqual(r['API_ack_created'],2)
    def test_sealed_fake_delivery_cannot_accept_real_HTTP_transport(self):
        box=SimulatedDelivery(self.cfg,self.root)
        box.transport=Mock()
        with self.assertRaisesRegex(ValueError,'sealed'):box.flush()
        with self.assertRaises(ValueError):Outbox(self.cfg,self.root,transport=Mock())
    def test_real_outbox_response_algorithm_retries_same_body_and_counts_changes(self):
        box=SimulatedDelivery(self.cfg,self.root,responses=[(503,{}),(200,{'state':'applied','change_kind':'updated'})],clock=lambda:self.at)
        normalized=Adapter(self.cfg,None).normalize(ebay(),self.at.isoformat());box.stage(normalized)
        box.flush();self.assertEqual(box.state['totals']['transient_failures'],1)
        self.at+=timedelta(seconds=6);box.flush()
        self.assertEqual(box.fake_API.calls[0],box.fake_API.calls[1]);self.assertEqual(box.state['totals']['change_updated'],1)
    def test_authentication_failure_holds_delivery_without_auto_retry(self):
        box=SimulatedDelivery(self.cfg,self.root,responses=[(401,{})],clock=lambda:self.at)
        box.stage(Adapter(self.cfg,None).normalize(ebay(),self.at.isoformat()))
        box.flush();box.flush();self.assertEqual(len(box.fake_API.calls),1)
        self.assertIsNotNone(box.state['hold'])
    def test_uncertain_mock_backend_retries_idempotently_with_immutable_payload(self):
        box=SimulatedDelivery(self.cfg,self.root,responses=[(0,{}),(200,{'state':'applied','change_kind':'unchanged'})],clock=lambda:self.at)
        box.stage(Adapter(self.cfg,None).normalize(ebay(),self.at.isoformat()))
        box.flush();self.at+=timedelta(seconds=6);box.flush()
        self.assertEqual(box.fake_API.calls[0][1]['observation_key'],box.fake_API.calls[1][1]['observation_key'])
        self.assertEqual(box.state['totals']['change_unchanged'],1)
    def test_food_is_held_and_raw_evidence_not_persisted_in_checkpoint_or_outbox(self):
        box=SimulatedDelivery(self.cfg,self.root/'ebay_browse')
        worker=OpsWorker(self.cfg,self.root,delivery=box,clock=lambda:self.at)
        row=ebay();row.update(category='food',description='원재료: 밀\n알레르기: 밀\nSENSITIVE FOOD SOURCE')
        worker.accept(row);worker.save()
        self.assertEqual(worker.state['totals']['food_contract_held'],1)
        self.assertEqual(worker.state['totals']['products_held'],1)
        self.assertEqual(box.pending_count(),0)
        text=''.join(p.read_text() for p in self.root.rglob('*.json'))
        self.assertNotIn('SENSITIVE FOOD SOURCE',text)
        worker.close()
    def test_domeggook_license_gate_avoids_extracting_unlicensed_description(self):
        from services.collector.domeggook_live.fixture_data import row,config as dome_config
        cfg=dome_config();box=FoodDelivery(cfg,self.root,transport=Mock())
        data=row();data.update(product_name='SYNTHETIC snack',category='food',description='Allergens: milk',detail_content_license_usable=False)
        self.assertEqual(box.stage(data)['status'],'food_contract_required')
        self.assertEqual(box.state['totals']['food_allergens_not_reported'],1)
        self.assertNotIn('milk',box.path.read_text())
    def test_secret_files_are_explicit_and_transactional_without_logging(self):
        f=self.root/'id';f.write_text('SYNTHETIC_CLIENT_ID')
        s=self.root/'secret';s.write_text('SYNTHETIC_CLIENT_SECRET')
        with patch.dict(os.environ,{'EBAY_CLIENT_ID_FILE':str(f),'EBAY_CLIENT_SECRET_FILE':str(s)},clear=True):
            loaded=load_secrets('ebay');self.assertEqual(loaded,{'EBAY_CLIENT_ID':True,'EBAY_CLIENT_SECRET':True})
            os.environ['EBAY_CLIENT_SECRET']='CONFLICT';os.environ.pop('EBAY_CLIENT_ID')
            with self.assertRaises(ValueError):load_secrets('ebay')
            self.assertNotIn('EBAY_CLIENT_ID',os.environ)
    def test_missing_environment_approval_and_rights_preflight_never_requests(self):
        cfg=config('serper_google_shopping');cfg['enabled']=False;cfg['rights']['allowed_uses']=[]
        with patch.dict(os.environ,{},clear=True),patch('requests.sessions.Session.request',side_effect=AssertionError('network')):
            result=preflight('serper',cfg)
        self.assertFalse(result['ready']);self.assertIn('required_credentials_missing',result['reasons'])
        self.assertIn('systematic_storage_reuse_grants_required',result['reasons'])
    def test_disabled_watch_stays_idle_and_health_without_loading_secrets(self):
        self.cfg['enabled']=False;file=self.root/'config.json';file.write_text(json.dumps({'sources':[self.cfg]}))
        with patch.dict(os.environ,{},clear=True),patch('requests.sessions.Session.request',side_effect=AssertionError('network')):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--provider','ebay','--watch','--config',str(file),'--state-dir',str(self.root),'--max-ticks','1']),0)
        self.assertFalse((self.root/'ebay_browse/request_ledger.json').exists())
        if (self.root/'ops/ebay/heartbeat.json').exists():
            self.assertEqual(main(['--provider','ebay','--health','--state-dir',str(self.root)]),0)
    def test_status_counts_API_ack_changes_separately_from_queue_success(self):
        atomic(self.root/'ebay_browse/checkpoint.json',{'totals':{'products_success':3,'products_held':1},'last_success_at':self.at.isoformat()})
        atomic(self.root/'ebay_browse/backend_outbox.json',{'entries':{},'totals':{'change_created':1,'change_updated':2}})
        result=source_status(self.cfg,self.root,'ebay',clock=lambda:self.at+timedelta(hours=5))
        self.assertEqual((result['DB_ack_created'],result['DB_ack_updated']),(1,2));self.assertTrue(result['stale'])
    def test_unsupported_provider_cannot_activate_by_env_or_watch(self):
        for provider in ('bunjang','joongna','elevenst','searchapi','smartify'):
            with self.subTest(provider=provider),redirect_stdout(io.StringIO()),patch.dict(os.environ,{'COLLECTOR_RUN_APPROVED':'yes'}):
                self.assertEqual(main(['--provider',provider,'--watch']),2)
    def test_health_missing_heartbeat_fails_without_creating_state(self):
        root=self.root/'absent';self.assertEqual(main(['--provider','ebay','--health','--state-dir',str(root)]),1)
        self.assertFalse(root.exists())
    def test_known_items_outside_search_get_bounded_refresh_before_next_cycle(self):
        box=SimulatedDelivery(self.cfg,self.root/'ebay_browse')
        worker=OpsWorker(self.cfg,self.root,delivery=box,clock=lambda:self.at)
        worker.state.update(cycle=1,tasks=[],seen_ids=['v1|123|0'],ops_known_items={
            'v1|123|0':{'last_checked_at':self.at.isoformat()},
            'v1|456|0':{'last_checked_at':(self.at-timedelta(hours=2)).isoformat()},
            'v1|789|0':{'last_checked_at':self.at.isoformat()}})
        worker.complete_if_empty()
        self.assertEqual([t['identity'] for t in worker.state['tasks']],['v1|456|0'])
        worker.state['tasks']=[];worker.complete_if_empty()
        self.assertEqual(worker.state['tasks'],[])
        self.assertEqual(datetime.fromisoformat(worker.state['next_cycle_at'])-self.at,timedelta(seconds=7200))
        worker.close()
    def test_404_requires_verification_without_claiming_deleted_and_403_is_not_swallowed(self):
        box=SimulatedDelivery(self.cfg,self.root/'ebay_browse')
        worker=OpsWorker(self.cfg,self.root,delivery=box,clock=lambda:self.at)
        identity='v1|123|0'
        worker.state['ops_known_items']={identity:{'availability':'available','last_checked_at':self.at.isoformat()}}
        task=worker.task('detail',identity=identity)
        worker.adapter.detail=Mock(side_effect=ProviderError('provider_HTTP_error',404))
        self.assertEqual(worker.execute(task),[])
        known=worker.state['ops_known_items'][identity]
        self.assertTrue(known['verification_required']);self.assertEqual(known['availability'],'available')
        self.assertEqual(worker.state['totals']['products_held'],1)
        worker.adapter.detail.side_effect=ProviderError('provider_access_refused',403)
        with self.assertRaises(ProviderError):worker.execute(task)
        worker.close()
    def test_backup_is_lock_aware_outside_state_and_never_resets_files(self):
        state=self.root/'state';state.mkdir();atomic(state/'checkpoint.json',{'cycle':3})
        archive=self.root/'backup.tar'
        with FileState(state/'source/lock').lock():
            with self.assertRaises(OSError):backup(state,archive)
        self.assertFalse(archive.exists())
        result=backup(state,archive);self.assertFalse(result['state_deleted'])
        import tarfile
        with tarfile.open(archive) as tar:
            self.assertEqual(json.load(tar.extractfile('checkpoint.json')),{'cycle':3})
        with self.assertRaises(ValueError):backup(state,archive)
        with self.assertRaises(ValueError):backup(state,state/'backup.tar')
    def test_refresh_limits_invalid_before_touching_state(self):
        cfg=dict(self.cfg,refresh_items_per_cycle=True)
        with self.assertRaises(ValueError):OpsWorker(cfg,self.root/'unused')
        self.assertFalse((self.root/'unused').exists())
    def test_trusted_CA_is_explicit_and_never_disables_TLS(self):
        from services.collector.collector_ops.backend import configure_CA
        tx=Mock();tx.session.verify=True
        with patch.dict(os.environ,{},clear=True):
            configure_CA(tx);self.assertIs(tx.session.verify,True)
        ca=self.root/'ca.pem';ca.write_text('SYNTHETIC CA placeholder for path validation only')
        with patch.dict(os.environ,{'COLLECTOR_CA_FILE':str(ca)}):
            configure_CA(tx);self.assertEqual(tx.session.verify,str(ca))
        with patch.dict(os.environ,{'COLLECTOR_CA_FILE':str(self.root/'missing')}):
            with self.assertRaises(ValueError):configure_CA(tx)
    def test_used_configuration_cannot_accidentally_run_as_general_ebay(self):
        from services.collector.collector_ops.__main__ import config as load_cfg
        file=self.root/'used.json';cfg=dict(self.cfg,collection_profile='ebay_used')
        file.write_text(json.dumps({'sources':[cfg]}))
        with self.assertRaises(ValueError):load_cfg('ebay',file)
        self.assertEqual(load_cfg('ebay_used',file)['collection_profile'],'ebay_used')
    def test_domeggook_plan_accepts_CLI_string_path_without_reading_keys(self):
        file=self.root/'dome.json';file.write_text(json.dumps({'enabled':False,'backend_profile':{}}))
        with patch.dict(os.environ,{},clear=True),redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(main(['--provider','domeggook','--plan','--config',str(file)]),1)
        result=json.loads(stream.getvalue())
        self.assertFalse(result['ready']);self.assertIn('configuration_disabled',result['reasons'])
        self.assertEqual(result['HTTP_requests_this_command'],0)


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).parents[1]/'deploy'
        self.compose=json.loads((self.root/'compose.yaml').read_text())
    def test_services_have_independent_persistence_secrets_restart_and_health(self):
        for provider in ('domeggook','serper','ebay','ebay_used','yes24'):
            service=self.compose['services'][provider]
            self.assertEqual(service['restart'],'unless-stopped');self.assertTrue(service['read_only'])
            self.assertEqual(service['cap_drop'],['ALL']);self.assertIn('--watch',service['command'])
            self.assertIn('--health',service['healthcheck']['test']);self.assertIn(provider,service['profiles'])
            self.assertNotIn('env_file',service)
            self.assertTrue(all(key.endswith('_FILE') for key in service['environment'] if 'KEY' in key or 'TOKEN' in key or 'SECRET' in key))
        a=self.compose['services']['ebay']['volumes'];b=self.compose['services']['ebay_used']['volumes']
        shared=next(v for v in a if v.endswith(':/state/ebay_browse'))
        self.assertIn(shared,b)
    def test_default_profiles_disabled_food_contract_hold_and_7200_seconds(self):
        for path in (self.root/'config').glob('*.json'):
            data=json.loads(path.read_text());cfg=data['sources'][0] if 'sources' in data else data
            self.assertFalse(cfg['enabled']);self.assertEqual(cfg['food_policy'],'hold_until_contract')
            self.assertGreaterEqual(cfg.get('cycle_interval_seconds',7200),7200)
    def test_runtime_image_excludes_secrets_datasets_DB_drivers_and_tests(self):
        image=(self.root/'Dockerfile').read_text();ignore=(self.root/'Dockerfile.dockerignore').read_text()
        self.assertIn('USER 10001:10001',image);self.assertNotIn('COPY . ',image)
        self.assertTrue(ignore.startswith('**\n'));self.assertNotIn('!.env',ignore)
        lock=(self.root/'requirements.lock').read_text()
        self.assertIn('pydantic==',lock);self.assertNotIn('psycopg',lock)
        for provider in ('synthetic','mock'):
            self.assertEqual(self.compose['services'][provider]['network_mode'],'none')
