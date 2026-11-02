#!/usr/bin/env python3
"""Offline metadata catalog and verifiable backups. Python standard library only."""
import argparse
import contextlib
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
ZERO = '0' * 64
TABLES = ('meta', 'tracks', 'events', 'requests', 'legacy_imports', 'receipts')
ARCHIVE_FILES = {'catalog.sqlite3', 'catalog.jsonl', 'catalog.sql'}
SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE tracks(
 id TEXT PRIMARY KEY,artist TEXT NOT NULL,title TEXT NOT NULL,version TEXT NOT NULL,
 composers TEXT NOT NULL,identity_key TEXT UNIQUE NOT NULL,needs_review INTEGER NOT NULL,
 metadata TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE events(
 seq INTEGER PRIMARY KEY,id TEXT UNIQUE NOT NULL,created_at TEXT NOT NULL,
 operation TEXT NOT NULL,request_id TEXT NOT NULL,payload TEXT NOT NULL,
 previous_hash TEXT NOT NULL,hash TEXT UNIQUE NOT NULL);
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN
 SELECT RAISE(ABORT,'audit events are append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN
 SELECT RAISE(ABORT,'audit events are append-only'); END;
CREATE TABLE requests(id TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,result TEXT NOT NULL);
CREATE TABLE legacy_imports(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
CREATE TABLE receipts(
 id TEXT PRIMARY KEY,kind TEXT NOT NULL,target_id TEXT NOT NULL,label TEXT NOT NULL,
 archive_sha256 TEXT NOT NULL,event_seq INTEGER NOT NULL,event_hash TEXT NOT NULL,
 verified_at TEXT NOT NULL,location TEXT NOT NULL);
PRAGMA user_version=1;
"""

def now():
    return datetime.now(timezone.utc).isoformat()

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def sha(value):
    return hashlib.sha256(value).hexdigest()

def folded(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.casefold())
                   if not unicodedata.combining(c))

def identity(artist, title, version=''):
    return encoded([unicodedata.normalize('NFKC', ' '.join(v.split())).casefold()
                    for v in (artist, title, version)])

def directory():
    return Path(os.environ.get('MUSIC_CATALOG_DIR',
        str(Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'playlist-fs/catalog'))).expanduser()

def connect(root, create=False):
    root = Path(root)
    path = root/'catalog.sqlite3'
    if not create and not path.is_file():
        raise ValueError('catalog not found; use catalog init, add, or import-paste first')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or path.is_symlink():
        raise ValueError('catalog directory and database must not be symlinks')
    root.chmod(0o700)
    con = sqlite3.connect(path, timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.execute('PRAGMA synchronous=FULL')
    con.create_function('fold', 1, lambda v: folded(str(v or '')), deterministic=True)
    version = con.execute('PRAGMA user_version').fetchone()[0]
    if version == 0:
        # Recheck after locking: two first-time writers may initialize concurrently.
        try:
            con.execute('BEGIN IMMEDIATE')
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version == 0:
                if con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                    raise ValueError('unrecognized database; refusing to initialize it')
                statement = ''
                for line in SCHEMA.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        con.execute(statement)
                        statement = ''
                con.execute('INSERT INTO meta VALUES (?,?)', ('catalog_id', str(uuid.uuid4())))
            elif version != VERSION:
                raise ValueError('unsupported catalog schema version')
            con.commit()
        except BaseException:
            con.rollback(); con.close(); raise
    elif version != VERSION:
        con.close()
        raise ValueError('unsupported catalog schema version')
    path.chmod(0o600)
    return con

def readonly(path):
    con = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con

@contextlib.contextmanager
def transaction(con):
    con.execute('BEGIN IMMEDIATE')
    try:
        yield
        con.commit()
    except BaseException:
        con.rollback()
        raise

@contextlib.contextmanager
def read_transaction(con):
    owns = not con.in_transaction
    if owns: con.execute('BEGIN')
    try:
        yield
    finally:
        if owns: con.rollback()

def head(con):
    row = con.execute('SELECT seq,hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
    return (row['seq'], row['hash']) if row else (0, ZERO)

def catalog_id(con):
    return con.execute("SELECT value FROM meta WHERE key='catalog_id'").fetchone()[0]

def track(con, track_id):
    row = con.execute('SELECT * FROM tracks WHERE id=?', (track_id,)).fetchone()
    if row is None:
        raise ValueError('track ID not found')
    result = dict(row)
    result['composers'] = json.loads(result['composers'])
    result['metadata'] = json.loads(result['metadata'])
    result['needs_review'] = bool(result['needs_review'])
    return result

def clean(value, name):
    value = value.strip()
    if not value or any(ord(c) < 32 for c in value):
        raise ValueError(name+' must be nonempty text without control characters')
    return value

def upsert_track(con, artist, title, version='', composers=None, needs_review=False,
                 metadata=None, preferred_id=None):
    artist, title = clean(artist, 'artist'), clean(title, 'title')
    version = version.strip()
    composers = [clean(v, 'composer') for v in (composers or [])]
    key = identity(artist, title, version)
    found = con.execute('SELECT id FROM tracks WHERE identity_key=?', (key,)).fetchone()
    if found:
        # A repeated registration adds provenance, never replaces existing metadata.
        existing = track(con, found['id'])
        if composers and existing['composers']!=composers:
            raise ValueError('track already registered with different composers; use edit')
        return existing
    tid = preferred_id or str(uuid.uuid4())
    uuid.UUID(tid)
    timestamp = now()
    con.execute('INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?,?)',
        (tid, artist, title, version, encoded(composers), key, int(needs_review),
         encoded(metadata or {}), timestamp, timestamp))
    return track(con, tid)

def append_event(con, operation, request_id, payload):
    seq, previous = head(con)
    event = dict(seq=seq+1, id=str(uuid.uuid4()), created_at=now(), operation=operation,
                 request_id=request_id, payload=encoded(payload), previous_hash=previous)
    event['hash'] = sha(encoded(event).encode())
    con.execute('INSERT INTO events VALUES (:seq,:id,:created_at,:operation,:request_id,:payload,:previous_hash,:hash)',event)
    return event['seq']

def mutate(con, request_id, command, action):
    request_id = request_id or str(uuid.uuid4())
    command_hash = sha(encoded(command).encode())
    with transaction(con):
        validate(con)
        old = con.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
        if old:
            if old['payload_hash'] != command_hash:
                raise ValueError('request ID already used with different data')
            return dict(json.loads(old['result']), request_replayed=True)
        result, payload = action()
        result['event_seq'] = append_event(con, command['operation'], request_id, payload)
        result['request_id'] = request_id
        con.execute('INSERT INTO requests VALUES (?,?,?)', (request_id,command_hash,encoded(result)))
        return dict(result, request_replayed=False)

def add(con, artist, title, version='', composers=None, source=None, request_id=None):
    command = dict(operation='register', artist=artist, title=title, version=version,
                   composers=composers or [], source=source)
    def action():
        item = upsert_track(con, artist, title, version, composers)
        return {'track_ids':[item['id']]}, {'tracks':[item], 'source':source or {'text':artist+' - '+title}}
    return mutate(con, request_id, command, action)

def edit(con, track_id, changes, request_id=None):
    command = dict(operation='correct', track_id=track_id, changes=changes)
    def action():
        before = track(con, track_id)
        after = dict(before, **changes)
        after['artist'],after['title'] = clean(after['artist'],'artist'),clean(after['title'],'title')
        after['version'] = after['version'].strip()
        after['composers'] = [clean(v,'composer') for v in after['composers']]
        after['identity_key'] = identity(after['artist'],after['title'],after['version'])
        after['updated_at'] = now()
        con.execute('UPDATE tracks SET artist=?,title=?,version=?,composers=?,identity_key=?,needs_review=?,updated_at=? WHERE id=?',
            (after['artist'],after['title'],after['version'],encoded(after['composers']),after['identity_key'],int(after['needs_review']),after['updated_at'],track_id))
        item = track(con, track_id)
        return {'track_ids':[track_id]}, {'tracks':[item], 'before':before}
    return mutate(con, request_id, command, action)

def import_paste(con, raw, source_uri=None, request_id=None):
    command = dict(operation='import-paste', raw=raw, source_uri=source_uri)
    def action():
        tracks, items, unresolved = {}, [], []
        for position, original in enumerate(raw.splitlines(),1):
            line = re.sub(r'^\s*(?:#+\s+|\d+[.)]\s+)', '', html.unescape(original)).strip()
            if not line:
                continue
            parts = re.split(r'\s[-–—]\s', line, maxsplit=1)
            if len(parts)!=2 or not all(p.strip() for p in parts) or parts[1].strip().casefold() in ('xxx','?','tbd','a definir') or 'http://' in line or 'https://' in line:
                unresolved.append({'line':position,'text':original,'reason':'artist/title pair needs review'})
                continue
            item = upsert_track(con,*parts,needs_review='\ufffd' in line)
            tracks[item['id']] = item
            items.append({'line':position,'track_id':item['id'],'text':original})
        result = dict(track_ids=list(tracks), registered_lines=len(items), unresolved=unresolved)
        return result, dict(tracks=list(tracks.values()),items=items,unresolved=unresolved,
                            source={'kind':'paste','text':raw,'uri':source_uri})
    return mutate(con,request_id,command,action)

def import_legacy(con, path):
    legacy_tables = ('songs','sources','entries','links','annotations','recommendations','coverage')
    with contextlib.closing(readonly(path)) as legacy:
        bundle = {name:[dict(r) for r in legacy.execute('SELECT * FROM '+name+' ORDER BY rowid')]
                  for name in legacy_tables}
    payload = encoded(bundle)
    import_id = sha(payload.encode())
    command = dict(operation='import-legacy',payload_sha256=import_id)
    def action():
        tracks, mapping = {}, {}
        for song in bundle['songs']:
            metadata = {k:song.get(k) for k in ('album','release_year','duration_seconds')}
            item = upsert_track(con,song['artist'],song['title'],needs_review=song['status']=='needs_review',
                                metadata=metadata,preferred_id=song['id'])
            tracks[item['id']] = item
            mapping[song['id']] = item['id']
        con.execute('INSERT INTO legacy_imports VALUES (?,?)',(import_id,payload))
        return {'track_ids':list(tracks),'legacy_import_id':import_id}, dict(
            tracks=list(tracks.values()),legacy_import_id=import_id,legacy_track_ids=mapping)
    return mutate(con,'legacy:'+import_id,command,action)

def validate(con):
    with read_transaction(con):
        return validate_snapshot(con)

def validate_snapshot(con):
    if con.execute('PRAGMA user_version').fetchone()[0]!=VERSION:
        raise ValueError('unsupported schema')
    if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or con.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('database integrity check failed')
    previous, states, imports = ZERO, {}, set()
    for expected_seq, row in enumerate(con.execute('SELECT * FROM events ORDER BY seq'),1):
        event = dict(row)
        observed = event.pop('hash')
        if event['seq']!=expected_seq or event['previous_hash']!=previous or sha(encoded(event).encode())!=observed:
            raise ValueError('audit history verification failed')
        previous = observed
        payload = json.loads(event['payload'])
        for item in payload['tracks']:
            states[item['id']] = item
        if 'legacy_import_id' in payload:
            imports.add(payload['legacy_import_id'])
    actual = {r['id']:track(con,r['id']) for r in con.execute('SELECT id FROM tracks')}
    if states!=actual:
        raise ValueError('track state does not match audit history')
    legacy = {r['id']:r['payload'] for r in con.execute('SELECT * FROM legacy_imports')}
    if set(legacy)!=imports or any(sha(v.encode())!=k for k,v in legacy.items()):
        raise ValueError('legacy evidence verification failed')
    return dict(catalog_id=catalog_id(con),event_seq=head(con)[0],event_hash=head(con)[1],tracks=len(actual))

def jsonl(con):
    return ''.join(encoded({'table':name,'row':dict(row)})+'\n'
                   for name in TABLES for row in con.execute('SELECT * FROM '+name+' ORDER BY rowid')).encode()

def fsync_directory(path):
    fd = os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def publish_bytes(path, contents):
    """Publish a complete new file without replacing another file."""
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(contents); out.flush(); os.fsync(out.fileno())
        os.link(name,path)
        fsync_directory(path.parent)
    finally:
        os.unlink(name)

def export(con, root):
    with read_transaction(con):
        return export_snapshot(con,root)

def export_snapshot(con,root):
    validate(con)
    out = Path(root)/('export-'+uuid.uuid4().hex)
    out.mkdir(parents=True,mode=0o700)
    publish_bytes(out/'catalog.jsonl',jsonl(con))
    publish_bytes(out/'catalog.sql', ('\n'.join(con.iterdump())+'\nPRAGMA user_version=1;\n').encode())
    publish_bytes(out/'tracks.jsonl', ''.join(encoded(track(con,r['id']))+'\n' for r in con.execute('SELECT id FROM tracks ORDER BY artist,title')).encode())
    return out

def receipt(con, info, archive_sha, kind, target_id, label, location):
    with transaction(con):
        con.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?)',
            (str(uuid.uuid4()),kind,target_id,label,archive_sha,info['event_seq'],info['event_hash'],now(),location))

def backup(con, root):
    root = Path(root)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.TemporaryDirectory(prefix='.snapshot-',dir=root) as tmp:
        db = Path(tmp)/'catalog.sqlite3'
        with sqlite3.connect(db) as dest:
            con.backup(dest)
        with contextlib.closing(readonly(db)) as snapshot:
            info = validate(snapshot)
            files = {'catalog.sqlite3':db.read_bytes(),'catalog.jsonl':jsonl(snapshot),
                     'catalog.sql':('\n'.join(snapshot.iterdump())+'\nPRAGMA user_version=1;\n').encode()}
        manifest = dict(format=VERSION,**info,files={k:sha(v) for k,v in files.items()})
        staged = Path(tmp)/'snapshot.zip'
        with zipfile.ZipFile(staged,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in files.items():
                archive.writestr(name,data)
            archive.writestr('manifest.json',encoded(manifest))
        verify_backup(staged)
        archive_bytes = staged.read_bytes()
        digest = sha(archive_bytes)
        path = root/('music-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:12]+'.zip')
        publish_bytes(path,archive_bytes)
    receipt(con,info,digest,'local',str(root.resolve()),'local snapshot',str(path.resolve()))
    return path,manifest

def verify_backup(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names)!=len(set(names)) or set(names)!=ARCHIVE_FILES|{'manifest.json'}:
            raise ValueError('unexpected or duplicate archive members')
        # Metadata catalogs are small. Refuse unexpectedly large decompressed archives.
        if sum(i.file_size for i in archive.infolist())>512*1024*1024:
            raise ValueError('archive exceeds metadata recovery limit (512 MiB)')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format')!=VERSION or set(manifest.get('files',{}))!=ARCHIVE_FILES:
            raise ValueError('unsupported or incomplete backup manifest')
        for name in ARCHIVE_FILES:
            if sha(archive.read(name))!=manifest['files'][name]:
                raise ValueError('backup checksum mismatch: '+name)
        with tempfile.TemporaryDirectory(prefix='playlist-fs-verify-') as tmp:
            db = Path(tmp)/'catalog.sqlite3'
            db.write_bytes(archive.read('catalog.sqlite3'))
            with contextlib.closing(readonly(db)) as con:
                info = validate(con)
                if any(manifest[k]!=v for k,v in info.items()) or jsonl(con)!=archive.read('catalog.jsonl'):
                    raise ValueError('backup metadata/export does not match database')
            # Verify the portable SQL recovery route as well as the SQLite snapshot.
            with sqlite3.connect(':memory:') as restored:
                restored.row_factory = sqlite3.Row
                restored.set_authorizer(lambda op,a,b,db,trigger:
                    sqlite3.SQLITE_DENY if op in (sqlite3.SQLITE_ATTACH,sqlite3.SQLITE_DETACH)
                    or (op==sqlite3.SQLITE_FUNCTION and b=='load_extension')
                    or (op==sqlite3.SQLITE_PRAGMA and a!='user_version') else sqlite3.SQLITE_OK)
                restored.executescript(archive.read('catalog.sql').decode())
                restored.set_authorizer(None)
                if validate(restored)!=info or jsonl(restored)!=archive.read('catalog.jsonl'):
                    raise ValueError('SQL recovery does not match snapshot')
    return manifest

def restore(path, destination):
    info = verify_backup(path)
    destination = Path(destination).expanduser()
    # A nonexisting target prevents accidental restoration over a live database or symlink.
    if destination.exists() or destination.is_symlink():
        raise ValueError('restore destination must not exist')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.restore-',dir=destination.parent) as tmp:
        staged = Path(tmp)/'catalog'
        staged.mkdir(mode=0o700)
        with zipfile.ZipFile(path) as archive:
            publish_bytes(staged/'catalog.sqlite3',archive.read('catalog.sqlite3'))
        destination.mkdir(mode=0o700)
        try:
            os.link(staged/'catalog.sqlite3',destination/'catalog.sqlite3')
            fsync_directory(destination)
        except BaseException:
            # Only remove an empty directory reserved by this restoration.
            if not any(destination.iterdir()): destination.rmdir()
            raise
        fsync_directory(destination.parent)
    return info

def restic_command(repository, password_file=None):
    executable = shutil.which(os.environ.get('MUSIC_RESTIC_BIN','restic'))
    if not executable:
        raise ValueError('restic is required for encrypted replicas')
    if not repository:
        raise ValueError('set --repository or MUSIC_CATALOG_RESTIC_REPOSITORY')
    command = [executable,'--repo',repository]
    if password_file:
        command += ['--password-file',password_file]
    elif not any(os.environ.get(k) for k in ('RESTIC_PASSWORD_FILE','RESTIC_PASSWORD','RESTIC_PASSWORD_COMMAND')):
        raise ValueError('configure RESTIC_PASSWORD_FILE for noninteractive backups')
    return command

def run_restic(command, data=None):
    try:
        result = subprocess.run(command,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                timeout=int(os.environ.get('MUSIC_BACKUP_TIMEOUT','120')))
    except subprocess.TimeoutExpired as exc:
        raise ValueError('restic timed out; local data remains saved, retry replication') from exc
    if result.returncode:
        # Do not echo backend URLs, credentials or child-process diagnostics into catalog logs.
        raise ValueError('restic operation failed (exit '+str(result.returncode)+'); no verified receipt recorded')
    return result.stdout

def replicate(con, path, repository, label, password_file=None):
    manifest = verify_backup(path)
    if manifest['catalog_id']!=catalog_id(con):
        raise ValueError('backup belongs to another catalog')
    command = restic_command(repository,password_file)
    contents = Path(path).read_bytes()
    output = run_restic(command+['backup','--stdin','--stdin-filename','playlist-fs/catalog.zip',
        '--tag','playlist-fs','--tag','catalog:'+manifest['catalog_id'],'--json'],contents)
    summaries = [v for line in output.splitlines() if (v:=json.loads(line)).get('message_type')=='summary']
    snapshot_id = summaries[-1].get('snapshot_id') if summaries else None
    if not snapshot_id or not re.fullmatch(r'[0-9a-f]{8,64}',snapshot_id):
        raise ValueError('restic did not confirm a snapshot ID')
    recovered = run_restic(command+['dump',snapshot_id,'/playlist-fs/catalog.zip'])
    if sha(recovered)!=sha(contents):
        raise ValueError('replica readback mismatch; no verified receipt recorded')
    # Identical bytes to a fully restored-and-verified local archive establish the readback.
    receipt(con,manifest,sha(contents),'restic',sha(repository.encode()),label,snapshot_id)
    return dict(label=label,snapshot_id=snapshot_id,archive_sha256=sha(contents),readback_verified=True)

def restore_restic(repository,snapshot_id,destination,password_file=None):
    if not re.fullmatch(r'[0-9a-f]{8,64}',snapshot_id):
        raise ValueError('use an explicit restic snapshot ID, not latest')
    contents = run_restic(restic_command(repository,password_file)+['dump',snapshot_id,'/playlist-fs/catalog.zip'])
    with tempfile.TemporaryDirectory(prefix='playlist-fs-recovery-') as tmp:
        path = Path(tmp)/'snapshot.zip'
        path.write_bytes(contents)
        return restore(path,destination)

def status(con):
    with read_transaction(con):
        return status_snapshot(con)

def status_snapshot(con):
    info = validate(con)
    receipts = []
    for row in con.execute('SELECT * FROM receipts ORDER BY verified_at DESC,rowid DESC'):
        item = dict(row)
        item['covers_current_records'] = (item['event_seq'],item['event_hash'])==(info['event_seq'],info['event_hash'])
        receipts.append(item)
    return dict(info,receipts=receipts,offsite_independence='not_verified',
                automatic_replica_configured=bool(os.environ.get('MUSIC_CATALOG_RESTIC_REPOSITORY')))

def history(con, track_id=None):
    result = []
    for row in con.execute('SELECT * FROM events ORDER BY seq'):
        event = dict(row)
        event['payload'] = json.loads(event['payload'])
        if track_id and not any(t['id']==track_id for t in event['payload']['tracks']):
            continue
        if track_id:
            event['payload']['tracks'] = [t for t in event['payload']['tracks'] if t['id']==track_id]
        result.append(event)
    return result

def pending(con):
    result = []
    for event in history(con):
        result.extend(dict(item,event_seq=event['seq'],source=event['payload'].get('source'))
                      for item in event['payload'].get('unresolved',[]))
    for row in con.execute('SELECT * FROM legacy_imports'):
        data = json.loads(row['payload'])
        result.extend(dict(item,legacy_import_id=row['id']) for item in data['entries']
                      if item.get('kind') in ('needs_review','artist_interest','negative_feedback'))
    return result

def finish_write(con,root,result):
    result = dict(result,local_saved=True)
    try:
        path, _ = backup(con,Path(root)/'backups')
        result['local_backup'] = str(path)
    except (ValueError,OSError,sqlite3.Error,zipfile.BadZipFile) as exc:
        return dict(result,protection='local_saved_backup_pending',error=str(exc)),3
    repository = os.environ.get('MUSIC_CATALOG_RESTIC_REPOSITORY')
    if repository:
        try:
            result['replica'] = replicate(con,path,repository,os.environ.get('MUSIC_CATALOG_RESTIC_LABEL','configured replica'))
        except (ValueError,OSError) as exc:
            return dict(result,protection='local_saved_replica_pending',error=str(exc)),3
        return dict(result,protection='replica_readback_verified'),0
    return dict(result,protection='local_snapshot_only'),0

def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,help='catalog directory (or MUSIC_CATALOG_DIR)')
    s = p.add_subparsers(dest='command',required=True)
    for name in ('init','status','pending'):
        s.add_parser(name)
    h = s.add_parser('history'); h.add_argument('--track-id')
    a = s.add_parser('add'); a.add_argument('--artist',required=True); a.add_argument('--title',required=True)
    a.add_argument('--version',default=''); a.add_argument('--composer',action='append',default=[])
    a.add_argument('--source'); a.add_argument('--source-uri'); a.add_argument('--request-id')
    e = s.add_parser('edit'); e.add_argument('id'); e.add_argument('--artist'); e.add_argument('--title'); e.add_argument('--version')
    e.add_argument('--composer',action='append'); e.add_argument('--clear-composers',action='store_true')
    e.add_argument('--reviewed',action='store_true'); e.add_argument('--request-id')
    g = s.add_parser('get'); g.add_argument('id')
    q = s.add_parser('search'); q.add_argument('query')
    i = s.add_parser('import-paste'); i.add_argument('--file',type=Path); i.add_argument('--source-uri'); i.add_argument('--request-id')
    l = s.add_parser('import-legacy'); l.add_argument('database',type=Path)
    x = s.add_parser('export'); x.add_argument('--to',type=Path,required=True)
    b = s.add_parser('backup'); b.add_argument('--to',type=Path)
    v = s.add_parser('verify'); v.add_argument('archive',type=Path)
    r = s.add_parser('restore'); r.add_argument('archive',type=Path); r.add_argument('--to',type=Path,required=True)
    for name in ('replicate','restore-restic'):
        r = s.add_parser(name); r.add_argument('--repository'); r.add_argument('--password-file')
        if name=='replicate':
            r.add_argument('--label'); r.add_argument('--archive',type=Path)
        else:
            r.add_argument('--snapshot',required=True); r.add_argument('--to',type=Path,required=True)
    return p

def main(argv=None):
    args = parser().parse_args(argv)
    os.umask(0o077)
    root = args.directory or directory()
    code = 0
    if args.command=='verify': result = verify_backup(args.archive)
    elif args.command=='restore': result = restore(args.archive,args.to)
    elif args.command=='restore-restic':
        result = restore_restic(args.repository or os.environ.get('MUSIC_CATALOG_RESTIC_REPOSITORY'),args.snapshot,args.to,args.password_file)
    else:
        with contextlib.closing(connect(root,create=args.command in ('init','add','import-paste','import-legacy'))) as con:
            if args.command=='init': result = validate(con)
            elif args.command=='status': result = status(con)
            elif args.command=='get': result = track(con,args.id)
            elif args.command=='history': result = history(con,args.track_id)
            elif args.command=='pending': result = pending(con)
            elif args.command=='search':
                result = [track(con,r['id']) for r in con.execute("SELECT id FROM tracks WHERE instr(fold(artist||' '||title||' '||version||' '||composers),fold(?))>0 ORDER BY artist,title",(args.query,))]
            elif args.command=='export': result = {'export_directory':str(export(con,args.to))}
            elif args.command=='backup':
                path,manifest = backup(con,args.to or root/'backups'); result = dict(archive=str(path),**manifest)
            elif args.command=='replicate':
                path = args.archive or backup(con,root/'backups')[0]
                result = replicate(con,path,args.repository or os.environ.get('MUSIC_CATALOG_RESTIC_REPOSITORY'),args.label or os.environ.get('MUSIC_CATALOG_RESTIC_LABEL','restic replica'),args.password_file)
            else:
                validate(con)
                if args.command=='add':
                    source = {'kind':'manual','text':args.source or args.artist+' - '+args.title,'uri':args.source_uri}
                    result = add(con,args.artist,args.title,args.version,args.composer,source,args.request_id)
                elif args.command=='edit':
                    changes = {k:getattr(args,k) for k in ('artist','title','version') if getattr(args,k) is not None}
                    if args.composer is not None and args.clear_composers:
                        raise ValueError('--composer and --clear-composers are mutually exclusive')
                    if args.composer is not None or args.clear_composers:
                        changes['composers'] = args.composer or []
                    if args.reviewed: changes['needs_review'] = False
                    if not changes: raise ValueError('provide a correction')
                    result = edit(con,args.id,changes,args.request_id)
                elif args.command=='import-paste':
                    raw = args.file.read_text(encoding='utf-8-sig') if args.file else sys.stdin.read()
                    result = import_paste(con,raw,args.source_uri,args.request_id)
                else: result = import_legacy(con,args.database)
                result,code = finish_write(con,root,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return code

if __name__=='__main__':
    try:
        sys.exit(main())
    except (ValueError,OSError,sqlite3.Error,zipfile.BadZipFile,KeyError) as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
