"""Operational failure boundaries; standard library, Windows and Linux."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import operations as ops
import team_dev


def configuration():
    pg={'POSTGRES_PASSWORD':'master-'+'x'*40}
    api={'COLLECTOR_TOKEN':'collector-'+'x'*40}
    for domain in ops.DOMAINS:
        pg[domain.upper()+'_OWNER_PASSWORD']=domain+'-owner-'+'x'*40
        pg[domain.upper()+'_APP_PASSWORD']=domain+'-app-'+'x'*40
        api[domain.upper()+'_PASSWORD']=pg[domain.upper()+'_APP_PASSWORD']
    return {'services':{'postgres':{'environment':pg},'api':{'environment':api},'maintenance':{},'migrate':{}}}


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        patch.object(ops,'BACKUPS',self.root).start()

    def archive(self):
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        directory=self.root/(stamp+'-fixture');directory.mkdir(exist_ok=True)
        entries=[]
        for domain in ops.DOMAINS:
            data=('archive-'+domain).encode();name='kkulpick_'+domain
            (directory/(name+'.dump')).write_bytes(data)
            entries.append({'database':name,'file':name+'.dump','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        manifest={'created_utc':stamp,'databases':entries}
        (directory/'manifest.json').write_text(json.dumps(manifest))
        return directory,manifest

    def test_config_errors_do_not_expose_secrets(self):
        good=configuration();self.assertTrue(all(c['ok'] for c in ops.config_checks(good,'core')))
        bad=deepcopy(good);env=bad['services']['api']['environment']
        env.update(BILLING_MODE='mock',APP_ENV='production',ANALYSIS_WORKER_TOKEN=env['COLLECTOR_TOKEN'])
        bad['services']['postgres']['ports']=[{'published':'5433','host_ip':'0.0.0.0'}]
        checks=ops.config_checks(bad,'core')
        self.assertGreaterEqual(sum(not c['ok'] for c in checks),3)
        self.assertNotIn(env['COLLECTOR_TOKEN'],json.dumps(checks))

    def test_effective_compose_failure_hides_stderr(self):
        with patch.object(ops.workspace,'compose_command',return_value=['docker']),patch.object(ops,'captured',side_effect=subprocess.CalledProcessError(1,['docker'],stderr=b'password-secret')):
            report=ops.validate()
        self.assertFalse(report['ok']);self.assertNotIn('password-secret',json.dumps(report))

    def test_complete_backup_and_same_size_corruption(self):
        folder,_=self.archive();ops.verify_backup(folder)
        file=folder/'kkulpick_catalog.dump';data=file.read_bytes();file.write_bytes(b'X'+data[1:])
        with self.assertRaisesRegex(ValueError,'CHECKSUM'):ops.verify_backup(folder)

    def test_incomplete_duplicate_and_path_escape_rejected(self):
        folder,manifest=self.archive()
        for entries in (manifest['databases'][:2],[manifest['databases'][0]]*3,
                        [manifest['databases'][0]|{'file':'../secret'},*manifest['databases'][1:]]):
            (folder/'manifest.json').write_text(json.dumps(manifest|{'databases':entries}))
            with self.assertRaises(ValueError):ops.verify_backup(folder)

    def test_symbolic_link_rejected(self):
        folder,_=self.archive();p=folder/'kkulpick_member.dump';data=p.read_bytes();p.unlink()
        outside=self.root/'outside';outside.write_bytes(data)
        try:p.symlink_to(outside)
        except OSError:self.skipTest('OS does not permit symlink creation')
        with self.assertRaises(ValueError):ops.verify_backup(folder)

    def test_scheduler_restart_uses_existing_completed_backup(self):
        self.archive()
        with patch.object(team_dev,'backup') as backup:
            self.assertEqual(ops.backup_due()['state'],'not_due')
            self.assertEqual(ops.backup_due()['state'],'not_due')
            backup.assert_not_called()

    def test_scheduler_creates_when_only_partial_backup_exists(self):
        partial=self.root/'incomplete';partial.mkdir();(partial/'member.partial').write_bytes(b'x')
        def make(**kwargs):return self.archive()[0]
        with patch.object(team_dev,'backup',side_effect=make) as backup:
            self.assertEqual(ops.backup_due()['state'],'created');backup.assert_called_once()

    def test_second_scheduler_cannot_take_same_lock(self):
        with ops.backup_lock():
            with self.assertRaises(OSError):
                with ops.backup_lock():pass

    def test_failed_dump_never_publishes_complete_manifest(self):
        with patch.object(team_dev,'ROOT',self.root),patch.object(team_dev,'db_command',return_value=['docker']),patch.object(team_dev,'run',side_effect=subprocess.CalledProcessError(1,['docker'])):
            with self.assertRaises(subprocess.CalledProcessError):team_dev.backup()
        self.assertFalse(list(self.root.rglob('manifest.json')))
        self.assertTrue(list(self.root.rglob('*.partial')))

    def test_restore_failure_cleans_only_generated_databases(self):
        folder,_=self.archive();commands=[]
        def fake(command,**kwargs):
            commands.append(command)
            if 'pg_restore' in command:raise subprocess.CalledProcessError(1,command)
            return b''
        with patch.object(team_dev,'db_command',side_effect=lambda *args:list(args)),patch.object(ops,'captured',side_effect=fake):
            with self.assertRaises(subprocess.CalledProcessError):ops.restore_check(folder)
        creates=[x[-1] for x in commands if 'createdb' in x];drops=[x[-1] for x in commands if 'dropdb' in x]
        self.assertEqual(creates,drops);self.assertEqual(len(drops),1)
        self.assertTrue(drops[0].startswith('kkulpick_verify_'))
        self.assertNotIn('kkulpick_catalog',drops)


if __name__=='__main__':unittest.main()
