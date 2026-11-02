"""Real encrypted repository round trip; CI installs the distribution restic package."""
import contextlib
import importlib.util
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('restic_catalog',REPO/'libexec/catalog.py')
catalog=importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)
RESTIC=shutil.which(os.environ.get('MUSIC_RESTIC_BIN','restic'))

@unittest.skipUnless(RESTIC,'install restic to run encrypted backup integration tests')
class ResticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.root=self.base/'catalog'
        self.repo=self.base/'encrypted-repository'
        self.password=self.base/'password'
        self.password.write_text(secrets.token_urlsafe(32))
        self.password.chmod(0o600)
        self.env=mock.patch.dict(os.environ,{'MUSIC_RESTIC_BIN':RESTIC,
            'RESTIC_PASSWORD_FILE':str(self.password),'RESTIC_CACHE_DIR':str(self.base/'cache')})
        self.env.start()
        subprocess.run([RESTIC,'--repo',str(self.repo),'init'],check=True,capture_output=True)
        self.con=catalog.connect(self.root,create=True)

    def tearDown(self):
        self.con.close(); self.env.stop(); self.tmp.cleanup()

    def test_encrypted_repository_readback_and_disaster_recovery(self):
        result=catalog.add(self.con,'Artist','Recorded without audio',composers=['Composer'],
                           source={'text':'Original source that must survive recovery'})
        tid=result['track_ids'][0]
        archive,manifest=catalog.backup(self.con,self.root/'backups')
        replica=catalog.replicate(self.con,archive,str(self.repo),'Integration test')
        self.assertTrue(replica['readback_verified'])
        state=catalog.status(self.con)
        self.assertTrue(state['receipts'][0]['covers_current_records'])
        # Recovery uses only the encrypted repository and its key, with no live DB.
        recovered=self.base/'recovered'
        info=catalog.restore_restic(str(self.repo),replica['snapshot_id'],recovered)
        with contextlib.closing(catalog.connect(recovered)) as con:
            self.assertEqual(catalog.track(con,tid)['composers'],['Composer'])
            self.assertEqual(catalog.validate(con)['event_hash'],manifest['event_hash'])
            self.assertIn('Original source',con.execute('SELECT payload FROM events').fetchone()[0])
        self.assertEqual(info['tracks'],1)
        subprocess.run([RESTIC,'--repo',str(self.repo),'check','--read-data'],check=True,capture_output=True)

    def test_wrong_key_leaves_a_saved_record_and_pending_copy(self):
        wrong=self.base/'wrong-password'; wrong.write_text(secrets.token_urlsafe(32))
        env=dict(os.environ,MUSIC_CATALOG_DIR=str(self.root),RESTIC_PASSWORD_FILE=str(wrong),
                 MUSIC_CATALOG_RESTIC_REPOSITORY=str(self.repo))
        args=[str(REPO/'bin/music'),'catalog','add','--artist','Offline','--title','Keep me','--request-id','retryable']
        failed=subprocess.run(args,env=env,capture_output=True,text=True)
        self.assertEqual(failed.returncode,3,failed.stderr)
        self.assertTrue(json.loads(failed.stdout)['local_saved'])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM receipts WHERE kind='restic'").fetchone()[0],0)
        env['RESTIC_PASSWORD_FILE']=str(self.password)
        retry=subprocess.run(args,env=env,capture_output=True,text=True)
        self.assertEqual(retry.returncode,0,retry.stdout+retry.stderr)
        self.assertTrue(json.loads(retry.stdout)['request_replayed'])
        self.assertEqual(catalog.validate(self.con)['tracks'],1)
        self.assertEqual(catalog.head(self.con)[0],1)
        self.assertTrue(catalog.status(self.con)['receipts'][0]['covers_current_records'])

if __name__=='__main__':
    unittest.main()
