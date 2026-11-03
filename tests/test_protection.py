"""Operational recovery must work even when receipts or the live database do not."""
import contextlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('protection_catalog',REPO/'libexec/catalog.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class ProtectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base/'catalog'
        self.con = catalog.connect(self.root,create=True)
        catalog.add(self.con,'Example artist','Saved title',source={'text':'Original evidence'})
        self.archive,self.manifest = catalog.backup(self.con,self.base/'backups')

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def cli(self,*args):
        env = dict(os.environ,MUSIC_CATALOG_DIR=str(self.root))
        env.pop('MUSIC_CATALOG_RESTIC_REPOSITORY',None)
        return subprocess.run([str(REPO/'bin/music'),'catalog',*map(str,args)],
                              env=env,capture_output=True,text=True)

    def test_local_health_requires_readable_valid_backup_without_changing_database(self):
        before = (self.root/'catalog.sqlite3').read_bytes()
        run = self.cli('doctor')
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertTrue(json.loads(run.stdout)['ok'])
        self.assertEqual(before,(self.root/'catalog.sqlite3').read_bytes())
        self.archive.unlink()
        run = self.cli('doctor')
        self.assertEqual(run.returncode,3,run.stderr)
        self.assertFalse(json.loads(run.stdout)['ok'])
        self.assertEqual(catalog.validate(self.con)['tracks'],1)

    def test_receipt_alone_cannot_hide_corrupt_archive(self):
        self.archive.write_bytes(b'not a ZIP')
        self.con.execute('UPDATE receipts SET archive_sha256=?',(catalog.sha(self.archive.read_bytes()),))
        result = catalog.doctor(self.con)
        self.assertFalse(result['ok'])
        self.assertEqual(result['local']['attempts'][0]['state'],'unavailable_or_invalid')

    def test_another_valid_current_backup_survives_one_missing_copy(self):
        newer,_ = catalog.backup(self.con,self.base/'another-location')
        newer.unlink()
        self.assertTrue(catalog.doctor(self.con)['ok'])

    def test_new_capture_and_expired_or_future_receipts_are_not_healthy(self):
        catalog.add(self.con,'Example artist','Not backed up')
        self.assertFalse(catalog.doctor(self.con)['ok'])
        catalog.backup(self.con,self.base/'backups')
        self.con.execute("UPDATE receipts SET verified_at='2000-01-01T00:00:00+00:00'")
        self.assertFalse(catalog.doctor(self.con)['ok'])
        self.con.execute("UPDATE receipts SET verified_at='2999-01-01T00:00:00+00:00'")
        self.assertFalse(catalog.doctor(self.con)['ok'])

    def test_snapshot_from_another_catalog_is_rejected_even_with_matching_checksum(self):
        with contextlib.closing(catalog.connect(self.base/'other',create=True)) as other:
            catalog.add(other,'Other artist','Other song')
            archive,_ = catalog.backup(other,self.base/'other-backups')
        self.con.execute('UPDATE receipts SET location=?,archive_sha256=?',
                         (str(archive),catalog.sha(archive.read_bytes())))
        self.assertFalse(catalog.doctor(self.con)['ok'])

    def test_no_implicit_network_and_explicit_replica_requirement(self):
        with mock.patch.object(catalog,'read_restic_archive',side_effect=AssertionError('unexpected network')):
            result = catalog.doctor(self.con,repository='sftp:example:/backup')
            self.assertTrue(result['ok'])
            self.assertEqual(result['replica']['state'],'not_checked')
            result = catalog.doctor(self.con,require_replica=True)
            self.assertFalse(result['ok'])
            self.assertEqual(result['replica']['state'],'not_configured')
        run = self.cli('doctor','--require-replica')
        self.assertEqual(run.returncode,3,run.stderr)

    def test_configured_repository_needs_its_own_fresh_verified_receipt(self):
        repository = 'sftp:example:/private-backup'
        catalog.receipt(self.con,self.manifest,catalog.sha(self.archive.read_bytes()),'restic',
                        catalog.sha(repository.encode()),'Test destination','deadbeef')
        contents = self.archive.read_bytes()
        with mock.patch.object(catalog,'read_restic_archive',return_value=contents):
            result = catalog.doctor(self.con,repository=repository,check_replica=True)
            self.assertTrue(result['ok'])
            self.assertTrue(result['replica']['checked'])
            self.assertFalse(catalog.doctor(self.con,repository='different',check_replica=True)['ok'])
        with mock.patch.object(catalog,'read_restic_archive',side_effect=ValueError('unavailable')):
            result = catalog.doctor(self.con,repository=repository,check_replica=True)
            self.assertFalse(result['ok'])
            self.assertEqual(result['replica']['state'],'unavailable_or_invalid')
        with mock.patch.object(catalog,'read_restic_archive',return_value=b'corrupt remote copy'):
            self.assertFalse(catalog.doctor(self.con,repository=repository,check_replica=True)['ok'])

    def test_capture_during_remote_check_invalidates_old_proof(self):
        repository = '/test/repository'
        catalog.receipt(self.con,self.manifest,catalog.sha(self.archive.read_bytes()),'restic',
                        catalog.sha(repository.encode()),'Test destination','deadbeef')
        def concurrent_capture(*args):
            catalog.add(self.con,'Concurrent artist','Arrived during verification')
            return self.archive.read_bytes()
        with mock.patch.object(catalog,'read_restic_archive',side_effect=concurrent_capture):
            result = catalog.doctor(self.con,repository=repository,check_replica=True)
        self.assertFalse(result['ok'])
        self.assertTrue(result['catalog_changed_during_check'])

    def test_drill_uses_no_live_catalog_and_publishes_private_report_without_overwrite(self):
        expected = catalog.validate(self.con)
        self.con.close()
        (self.root/'catalog.sqlite3').unlink()
        report = self.base/'reports/drill.json'
        run = self.cli('drill',self.archive,'--report',report)
        self.assertEqual(run.returncode,0,run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['event_hash'],expected['event_hash'])
        self.assertEqual(result['tracks'],1)
        self.assertTrue(result['restored_data_equal'])
        self.assertFalse(result['original_catalog_required'])
        self.assertEqual(result,json.loads(report.read_text()))
        self.assertEqual(report.stat().st_mode & 0o777,0o600)
        self.assertFalse((self.root/'catalog.sqlite3').exists())
        before = report.read_bytes()
        self.assertEqual(self.cli('drill',self.archive,'--report',report).returncode,1)
        self.assertEqual(report.read_bytes(),before)

    def test_failed_drill_never_writes_success_report_and_requires_explicit_source(self):
        report = self.base/'failed.json'
        self.archive.write_bytes(b'corrupt')
        self.assertEqual(self.cli('drill',self.archive,'--report',report).returncode,1)
        self.assertFalse(report.exists())
        self.assertEqual(self.cli('drill').returncode,1)
        self.assertEqual(self.cli('drill',self.archive,'--snapshot','deadbeef').returncode,1)
        self.assertEqual(self.cli('drill','--snapshot','latest').returncode,1)

    def test_health_policy_rejects_invalid_age_limits(self):
        for value in ('0','-1','nan','inf'):
            with self.subTest(value=value):
                self.assertEqual(self.cli('doctor','--max-age-hours',value).returncode,1)


if __name__=='__main__':
    unittest.main()
