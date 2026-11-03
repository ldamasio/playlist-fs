import concurrent.futures
import contextlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('catalog',REPO/'libexec/catalog.py')
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base/'state'
        self.con = catalog.connect(self.root,create=True)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def register(self,artist='Test artist',title='Test title',**kwargs):
        return catalog.add(self.con,artist,title,**kwargs)

    def cli(self,*args,check=True,extra_env=None):
        env = dict(os.environ,MUSIC_CATALOG_DIR=str(self.root))
        env.pop('MUSIC_CATALOG_RESTIC_REPOSITORY',None)
        env.update(extra_env or {})
        run = subprocess.run([str(REPO/'bin/music'),'catalog',*args],env=env,capture_output=True,text=True)
        if check: self.assertEqual(run.returncode,0,run.stderr+run.stdout)
        return run

    def test_correction_keeps_id_history_and_distinct_composers(self):
        result = self.register(artist='Mistyped name',source={'text':'original paste','uri':'chat:1'})
        tid = result['track_ids'][0]
        self.assertEqual(catalog.track(self.con,tid)['composers'],[])
        catalog.edit(self.con,tid,{'artist':'Corrected name','composers':['Composer A','Composer B']})
        item = catalog.track(self.con,tid)
        self.assertEqual(item['artist'],'Corrected name')
        self.assertEqual(item['composers'],['Composer A','Composer B'])
        first = json.loads(self.con.execute('SELECT payload FROM events WHERE seq=1').fetchone()[0])
        self.assertEqual(first['tracks'][0]['artist'],'Mistyped name')
        self.assertEqual(first['source']['text'],'original paste')
        self.assertEqual(catalog.validate(self.con)['tracks'],1)
        self.assertEqual(len(catalog.history(self.con,tid)),2)
        with self.assertRaisesRegex(ValueError,'different composers'):
            self.register(artist='Corrected name',composers=['Unreviewed replacement'])

    def test_idempotent_retry_and_conflicting_request(self):
        first = self.register(request_id='capture-1')
        retry = self.register(request_id='capture-1')
        self.assertTrue(retry['request_replayed'])
        self.assertEqual(first['track_ids'],retry['track_ids'])
        self.assertEqual(catalog.head(self.con)[0],1)
        with self.assertRaisesRegex(ValueError,'different data'):
            self.register(title='Different title',request_id='capture-1')
        self.assertEqual(catalog.head(self.con)[0],1)

    def test_variants_remain_separate_and_names_have_boundaries(self):
        a = self.register(artist='A B',title='C')
        b = self.register(artist='A',title='B C')
        studio = self.register()
        live = self.register(version='Live')
        repeated = self.register(artist='TEST ARTIST',title='Test   title')
        self.assertNotEqual(a['track_ids'],b['track_ids'])
        self.assertNotEqual(studio['track_ids'],live['track_ids'])
        self.assertEqual(studio['track_ids'],repeated['track_ids'])
        self.assertEqual(catalog.validate(self.con)['tracks'],4)

    def test_conflicting_correction_rolls_back_without_audit_gap(self):
        first=self.register(title='One')['track_ids'][0]
        self.register(title='Two')
        before=catalog.head(self.con)
        with self.assertRaises(sqlite3.IntegrityError):
            catalog.edit(self.con,first,{'title':'Two'})
        self.assertEqual(catalog.track(self.con,first)['title'],'One')
        self.assertEqual(catalog.head(self.con),before)
        catalog.validate(self.con)

    def test_paste_preserves_unparsed_source_positions_and_duplicates(self):
        raw='Artist — First\n\nArtist — First\nMoacir Santos - xxx\nTitle · Artist\nCorrupt� - Second'
        result=catalog.import_paste(self.con,raw,'chat:paste','paste-1')
        self.assertEqual(result['registered_lines'],3)
        self.assertEqual(len(result['track_ids']),2)
        self.assertEqual([r['line'] for r in result['unresolved']],[4,5])
        payload=json.loads(self.con.execute('SELECT payload FROM events').fetchone()[0])
        self.assertEqual(payload['source']['text'],raw)
        self.assertEqual([r['line'] for r in payload['items']],[1,3,6])
        self.assertTrue(any(catalog.track(self.con,t)['needs_review'] for t in result['track_ids']))
        self.assertEqual(len(catalog.pending(self.con)),2)

    def test_local_snapshot_sql_and_restore_are_equivalent(self):
        self.register(source={'text':'Private original source'})
        path,info=catalog.backup(self.con,self.root/'backups')
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        self.assertEqual((self.root/'catalog.sqlite3').stat().st_mode & 0o777,0o600)
        self.assertEqual(self.root.stat().st_mode & 0o777,0o700)
        self.assertEqual(catalog.verify_backup(path),info)
        restored=self.base/'restored'
        catalog.restore(path,restored)
        with contextlib.closing(catalog.connect(restored)) as recovered:
            self.assertEqual(catalog.validate(recovered)['event_hash'],info['event_hash'])
            self.assertEqual(catalog.jsonl(recovered),self.archive_bytes(path,'catalog.jsonl'))
        with self.assertRaisesRegex(ValueError,'must not exist'):
            catalog.restore(path,restored)

    def archive_bytes(self,path,name):
        with zipfile.ZipFile(path) as z: return z.read(name)

    def altered_archive(self,path,change):
        output=self.base/'changed.zip'
        with zipfile.ZipFile(path) as z:
            members={name:z.read(name) for name in z.namelist()}
        change(members)
        with zipfile.ZipFile(output,'w') as z:
            for name,data in members.items(): z.writestr(name,data)
        return output

    def test_corruption_and_unexpected_members_are_rejected(self):
        self.register()
        path,_=catalog.backup(self.con,self.root/'backups')
        bad=self.altered_archive(path,lambda m:m.update({'catalog.jsonl':b'corrupt'}))
        with self.assertRaisesRegex(ValueError,'checksum'):
            catalog.verify_backup(bad)
        bad=self.altered_archive(path,lambda m:m.update({'../outside':b'bad'}))
        with self.assertRaisesRegex(ValueError,'unexpected'):
            catalog.restore(bad,self.base/'never-created')
        self.assertFalse((self.base/'never-created').exists())

    def test_sql_recovery_cannot_attach_external_files(self):
        self.register()
        path,_=catalog.backup(self.con,self.root/'backups')
        def malicious(members):
            members['catalog.sql']+=f"ATTACH DATABASE '{self.base/'external.sqlite3'}' AS external;".encode()
            manifest=json.loads(members['manifest.json'])
            manifest['files']['catalog.sql']=catalog.sha(members['catalog.sql'])
            members['manifest.json']=catalog.encoded(manifest).encode()
        bad=self.altered_archive(path,malicious)
        with self.assertRaises(sqlite3.DatabaseError): catalog.verify_backup(bad)
        self.assertFalse((self.base/'external.sqlite3').exists())

    def test_audit_detects_untracked_state_and_protects_events(self):
        tid=self.register()['track_ids'][0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("DELETE FROM events")
        self.con.execute('UPDATE tracks SET title=? WHERE id=?',('Untracked change',tid))
        with self.assertRaisesRegex(ValueError,'audit history'):
            catalog.validate(self.con)
        with self.assertRaises(ValueError): self.register(title='Should not commit')
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM tracks').fetchone()[0],1)

    def test_status_marks_previous_replica_stale_after_new_record(self):
        self.register()
        path,manifest=catalog.backup(self.con,self.root/'backups')
        catalog.receipt(self.con,manifest,catalog.sha(path.read_bytes()),'restic','target','Test replica','deadbeef')
        self.assertTrue(catalog.status(self.con)['receipts'][0]['covers_current_records'])
        self.register(title='Another')
        self.assertTrue(all(not r['covers_current_records'] for r in catalog.status(self.con)['receipts']))
        self.assertEqual(catalog.status(self.con)['offsite_independence'],'not_verified')

    def test_pending_replica_does_not_erase_saved_record(self):
        result=self.cli('add','--artist','Offline','--title','Saved','--request-id','offline-1',check=False,
            extra_env={'MUSIC_CATALOG_RESTIC_REPOSITORY':'/unused','MUSIC_RESTIC_BIN':'missing-restic-binary'})
        self.assertEqual(result.returncode,3,result.stderr)
        payload=json.loads(result.stdout)
        self.assertTrue(payload['local_saved'])
        self.assertEqual(payload['protection'],'local_saved_replica_pending')
        retry=self.cli('add','--artist','Offline','--title','Saved','--request-id','offline-1')
        self.assertTrue(json.loads(retry.stdout)['request_replayed'])
        self.assertEqual(catalog.validate(self.con)['tracks'],1)
        self.assertEqual(catalog.head(self.con)[0],1)

    def test_search_unicode_and_install_symlink_dispatch(self):
        self.cli('add','--artist','Artísta','--title','Canção','--composer','Compositor')
        self.assertEqual(len(json.loads(self.cli('search','CANCAO').stdout)),1)
        installed=self.base/'music-link'
        installed.symlink_to(REPO/'bin/music')
        result=subprocess.run([str(installed),'catalog','status'],env=dict(os.environ,MUSIC_CATALOG_DIR=str(self.root)),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['tracks'],1)

    def test_concurrent_processes_keep_all_records_and_one_retry(self):
        def write(n):
            return self.cli('add','--artist','Concurrent','--title',str(n),'--request-id','request-'+str(n),check=False)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(write,[0,1,2,3,4,5,0,1]))
        self.assertTrue(all(r.returncode==0 for r in results),[r.stderr+r.stdout for r in results if r.returncode])
        self.assertEqual(catalog.validate(self.con)['tracks'],6)
        self.assertEqual(catalog.head(self.con)[0],6)

    def test_unknown_database_is_not_modified(self):
        root=self.base/'unrelated'; root.mkdir()
        with sqlite3.connect(root/'catalog.sqlite3') as other:
            other.execute('CREATE TABLE valuable(data TEXT)')
        before=(root/'catalog.sqlite3').read_bytes()
        with self.assertRaisesRegex(ValueError,'unrecognized'):
            catalog.connect(root,create=True)
        self.assertEqual(before,(root/'catalog.sqlite3').read_bytes())

    def test_legacy_import_preserves_ids_evidence_and_suggestions(self):
        path=self.base/'legacy.sqlite3'
        with sqlite3.connect(path) as old:
            old.executescript('CREATE TABLE songs(id TEXT,artist TEXT,title TEXT,status TEXT,album TEXT,release_year INTEGER,duration_seconds INTEGER);')
            tid='33333333-3333-4333-8333-333333333333'
            old.execute('INSERT INTO songs VALUES (?,?,?,?,?,?,?)',(tid,'Artist','Title','registered','Album',2000,120))
            for name in ('sources','entries','links','annotations','recommendations','coverage'):
                old.execute('CREATE TABLE '+name+'(data TEXT)')
                old.execute('INSERT INTO '+name+' VALUES (?)',('preserved '+name,))
        first=catalog.import_legacy(self.con,path)
        retry=catalog.import_legacy(self.con,path)
        self.assertEqual(first['track_ids'],[tid])
        self.assertTrue(retry['request_replayed'])
        self.assertEqual(catalog.validate(self.con)['tracks'],1)
        evidence=json.loads(self.con.execute('SELECT payload FROM legacy_imports').fetchone()[0])
        self.assertEqual(evidence['recommendations'][0]['data'],'preserved recommendations')
        self.assertEqual(catalog.track(self.con,tid)['composers'],[])

    def test_failed_publish_never_records_a_backup_receipt(self):
        self.register()
        with mock.patch.object(catalog,'publish_bytes',side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError): catalog.backup(self.con,self.root/'backups')
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM receipts').fetchone()[0],0)
        self.assertEqual(catalog.validate(self.con)['tracks'],1)

if __name__=='__main__':
    unittest.main()
