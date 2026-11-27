"""Local onboarding regression checks; standard library, also runs on Windows."""
import contextlib
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import workspace


class LocalWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in ('services/api/dev.py', 'infra/db/db.py',
                         'apps/web/.env.example', 'apps/admin/.env.example', 'apps/mobile/.env.example', 'apps/extension/.env.example'):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(workspace.ROOT / relative, target)
        (self.root / 'infra/workspace').mkdir(parents=True)
        self.addCleanup(patch.stopall)
        patch.object(workspace, 'ROOT', self.root).start()
        patch.object(workspace, 'ENV', self.root / 'infra/workspace/.env').start()

    def initialize(self):
        with contextlib.redirect_stdout(io.StringIO()):
            workspace.initialize()

    def test_reinitializing_preserves_credentials_and_personal_settings(self):
        self.initialize()
        web = self.root / 'apps/web/.env.local'
        web.write_text('INTERNAL_API_URL=http://127.0.0.1:8123\n', encoding='utf-8')
        paths = ['infra/db/.env', 'services/api/.env', 'infra/workspace/.env', 'apps/web/.env.local']
        before = {p: (self.root / p).read_bytes() for p in paths}
        self.initialize()
        self.assertEqual(before, {p: (self.root / p).read_bytes() for p in paths})

    def test_fresh_pc_gets_unique_secrets_and_local_client_addresses(self):
        self.initialize()
        first = (self.root / 'infra/db/.env').read_bytes()
        (self.root / 'infra/db/.env').unlink()  # disposable test only; no DB volume exists
        self.initialize()
        self.assertNotEqual(first, (self.root / 'infra/db/.env').read_bytes())
        for app in ('web', 'admin'):
            self.assertIn('INTERNAL_API_URL=http://127.0.0.1:8000',
                          (self.root / f'apps/{app}/.env.local').read_text(encoding='utf-8'))
        self.assertIn('EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000',
                      (self.root / 'apps/mobile/.env.local').read_text(encoding='utf-8'))

    def test_saved_vpn_enrollment_does_not_enable_local_sharing(self):
        self.initialize()
        host = self.root / 'infra/team/local/bind_address'
        host.parent.mkdir(parents=True)
        host.write_text('100.101.102.103')
        with patch.dict(os.environ):
            for scope in ('core', 'full'):
                command = workspace.compose_command(scope)
                self.assertNotIn(str(self.root / 'infra/team/team.compose.yaml'), command)
                self.assertIn(str(self.root / 'infra/workspace/local.compose.yaml'), command)
            self.assertIn(str(self.root / 'infra/team/team.compose.yaml'), workspace.compose_command(shared=True))

    def test_fresh_init_allows_dev_shop_hosts_and_keeps_custom_ones(self):
        # 새로 init한 PC에서도 크롤러 상품 적재·관리자 제휴상품 등록이 되도록 개발용 쇼핑몰 목록을 더한다.
        self.initialize()
        shutil.copyfile(Path(workspace.__file__).resolve().parents[1] / 'infra/workspace/shop_hosts.txt',
                        self.root / 'infra/workspace/shop_hosts.txt')
        api_env = self.root / 'services/api/.env'
        api_env.write_text(api_env.read_text(encoding='utf-8') + 'CATALOG_URL_HOSTS=my.shop.test\n', encoding='utf-8')
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CATALOG_URL_HOSTS', None)
            os.environ.pop('AFFILIATE_URL_HOSTS', None)
            os.environ.pop('BILLING_MODE', None)
            workspace.compose_command('core')
            self.assertNotIn('BILLING_MODE', os.environ)  # 모의 결제는 integrated에서만
            workspace.compose_command('integrated')
            catalog = os.environ['CATALOG_URL_HOSTS'].split(',')
            affiliate = os.environ['AFFILIATE_URL_HOSTS'].split(',')
            self.assertEqual(os.environ['BILLING_MODE'], 'mock')
        self.assertEqual(catalog[0], 'my.shop.test')
        for host in ('www.daisomall.co.kr', 'kurly.com', 'store.example.test'):
            self.assertIn(host, catalog)
            self.assertIn(host, affiliate)

    def test_api_reload_is_opt_in(self):
        # 기본은 자동 반영 꺼짐(쉬는 동안 파일 감시 부하 없음), WORKSPACE_API_RELOAD=on일 때만 켠다.
        self.initialize()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('WORKSPACE_API_RELOAD', None)
            workspace.compose_command('core')
            self.assertEqual(os.environ['API_RELOAD_ARGS'], '')
            os.environ['WORKSPACE_API_RELOAD'] = 'on'
            workspace.compose_command('core')
            self.assertIn('--reload', os.environ['API_RELOAD_ARGS'])

    def test_core_omits_large_stack_and_full_retains_it(self):
        self.initialize()
        file = str(self.root / 'infra/workspace/compose.yaml')
        self.assertNotIn(file, workspace.compose_command('core'))
        self.assertIn(file, workspace.compose_command('full'))

    def test_default_start_is_core_but_stop_still_stops_full_stack(self):
        with patch('sys.argv', ['workspace.py', 'up']), patch.object(workspace, 'compose') as call:
            self.assertEqual(workspace.main(), 0)
            self.assertEqual(call.call_args.kwargs['scope'], 'core')
        with patch('sys.argv', ['workspace.py', 'stop']), patch.object(workspace, 'compose') as call:
            self.assertEqual(workspace.main(), 0)
            self.assertEqual(call.call_args.kwargs['scope'], 'integrated')
        with patch('sys.argv', ['workspace.py', 'up', '--scope', 'full']), patch.object(workspace, 'compose') as call:
            self.assertEqual(workspace.main(), 0)
            self.assertEqual(call.call_args.kwargs['scope'], 'full')

    def test_check_uses_the_same_port_override_as_compose(self):
        self.initialize()
        with patch.dict(os.environ, {'API_PORT': '8123'}):
            self.assertEqual(workspace.api_port(), '8123')
        with patch.dict(os.environ, {'API_PORT': 'bad-port'}):
            with self.assertRaises(ValueError):
                workspace.api_port()


if __name__ == '__main__':
    unittest.main()
