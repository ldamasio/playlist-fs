"""Privileged destructive fixture: run ONLY on an explicitly disposable host.

Exercises the actual Ansible account/SSH policy, encrypted SFTP backup, retries,
and recovery. CI supplies a fresh VM; never run this on a workstation/server.
"""
import json
import os
import pwd
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
JAIL=Path('/srv/playlist-fs-backup')
FRAGMENT=Path('/etc/ssh/playlist-fs-backup.conf')
KEYS=Path('/etc/ssh/playlist-fs-backup.keys')
MAIN=Path('/etc/ssh/sshd_config')


def main():
    if sys.argv[1:]!=['--ephemeral-host'] or os.geteuid()!=0 or os.environ.get('GITHUB_ACTIONS')!='true':
        raise SystemExit('This fixture requires root, GitHub Actions, and --ephemeral-host on a disposable VM.')
    if any(p.exists() for p in (JAIL,FRAGMENT,KEYS)):
        raise SystemExit('Refusing to adopt existing deployment paths in the fixture.')
    try:
        pwd.getpwnam('playlist-backup')
    except KeyError:
        pass
    else:
        raise SystemExit('Refusing to adopt an existing account in the fixture.')
    original=MAIN.read_bytes()
    original_mode=MAIN.stat().st_mode & 0o777
    daemon=None
    with tempfile.TemporaryDirectory(prefix='playlist-fs-sftp-fixture-') as task_tmp:
        base=Path(task_tmp)
        env=dict(os.environ)
        def run(args,**kwargs):
            result=subprocess.run(list(map(str,args)),capture_output=True,env=env,timeout=90,**kwargs)
            if result.returncode:
                raise AssertionError(result.stdout.decode(errors='replace')+'\n'+result.stderr.decode(errors='replace'))
            return result.stdout
        try:
            for name in ('client','host'):
                run(['ssh-keygen','-q','-t','ed25519','-N','','-f',base/name])
            inventory=base/'inventory.yml'
            inventory.write_text('all:\n  children:\n    playlist_backup:\n      hosts:\n        localhost:\n          ansible_connection: local\n')
            deploy=['ansible-playbook','-i',inventory,REPO/'ops/ansible/backup-host.yml',
                    '-e','playlist_backup_public_key_file='+str(base/'client.pub')]
            JAIL.mkdir(mode=0o700)
            unrelated=subprocess.run(list(map(str,deploy)),capture_output=True,env=env,timeout=90)
            assert unrelated.returncode,'An unrelated preexisting directory was unexpectedly adopted'
            assert MAIN.read_bytes()==original and not FRAGMENT.exists() and not KEYS.exists()
            JAIL.rmdir()
            run(deploy)
            again=run(deploy).decode()
            assert re.search(r'changed=0\s+',again),again
            print('Ansible deployment and idempotency passed',flush=True)
            working_main=MAIN.read_bytes(); working_fragment=FRAGMENT.read_bytes()
            invalid_ops=base/'invalid-ops'
            shutil.copytree(REPO/'ops/ansible',invalid_ops)
            bad_template=invalid_ops/'templates/backup-sftp.conf.j2'
            bad_template.write_text(bad_template.read_text()+'\nInvalidSftpFixtureDirective yes\n')
            invalid_deploy=list(deploy); invalid_deploy[3]=invalid_ops/'backup-host.yml'
            rejected=subprocess.run(list(map(str,invalid_deploy)),capture_output=True,env=env,timeout=90)
            assert rejected.returncode,'Invalid SSH policy was unexpectedly accepted'
            assert MAIN.read_bytes()==working_main and FRAGMENT.read_bytes()==working_fragment
            print('Unrelated-path refusal and assembled-policy rollback passed',flush=True)

            with socket.socket() as port_probe:
                port_probe.bind(('127.0.0.1',0)); port=port_probe.getsockname()[1]
            daemon_config=base/'sshd_config'
            daemon_config.write_text(f'Port {port}\nListenAddress 127.0.0.1\nHostKey {base}/host\n'
                f'PidFile {base}/sshd.pid\nUsePAM yes\nPasswordAuthentication no\n'
                f'Subsystem sftp internal-sftp\nInclude {FRAGMENT}\n')
            daemon_log=(base/'sshd.log').open('wb')
            daemon=subprocess.Popen(['/usr/sbin/sshd','-D','-e','-f',str(daemon_config)],stdout=daemon_log,stderr=daemon_log)
            for _ in range(50):
                if daemon.poll() is not None:
                    raise AssertionError((base/'sshd.log').read_text())
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2): break
                except OSError: time.sleep(.1)
            else: raise AssertionError('Test SSH daemon did not become ready')

            host_key=(base/'host.pub').read_text().split()
            known=base/'known_hosts'; known.write_text(f'[127.0.0.1]:{port} {host_key[0]} {host_key[1]}\n')
            client_config=base/'ssh_config'
            client_config.write_text(f'Host playlist-sftp-test\n  HostName 127.0.0.1\n  Port {port}\n'
                f'  User playlist-backup\n  IdentityFile {base}/client\n  IdentitiesOnly yes\n'
                f'  IdentityAgent none\n  BatchMode yes\n  StrictHostKeyChecking yes\n  UserKnownHostsFile {known}\n')
            wrappers=base/'bin'; wrappers.mkdir()
            ssh=wrappers/'ssh'
            ssh.write_text('#!/bin/sh\nexec /usr/bin/ssh -F '+shlex.quote(str(client_config))+' "$@"\n')
            ssh.chmod(0o700)
            password=base/'password'; password.write_text(secrets.token_urlsafe(32)); password.chmod(0o600)
            env.update(PATH=str(wrappers)+os.pathsep+env['PATH'],RESTIC_PASSWORD_FILE=str(password),
                       RESTIC_CACHE_DIR=str(base/'cache'),MUSIC_CATALOG_DIR=str(base/'catalog'),
                       MUSIC_CATALOG_RESTIC_REPOSITORY='sftp:playlist-sftp-test:/repository')
            run(['restic','--repo',env['MUSIC_CATALOG_RESTIC_REPOSITORY'],'init'])
            music=[REPO/'bin/music','catalog']
            saved=json.loads(run(music+['add','--artist','SFTP fixture','--title','Recover me',
                '--source','Evidence surviving a lost device','--request-id','sftp-fixture']))
            assert saved['replica']['readback_verified']
            retry=json.loads(run(music+['add','--artist','SFTP fixture','--title','Recover me',
                '--source','Evidence surviving a lost device','--request-id','sftp-fixture']))
            assert retry['request_replayed']
            assert json.loads(run(music+['doctor','--check-replica','--require-replica']))['ok']
            snapshot=retry['replica']['snapshot_id']
            shutil.rmtree(base/'catalog')
            drill=json.loads(run(music+['drill','--snapshot',snapshot,'--report',base/'drill.json']))
            assert drill['restored_data_equal'] and drill['tracks']==1
            run(music+['restore-restic','--snapshot',snapshot,'--to',base/'recovered'])
            env['MUSIC_CATALOG_DIR']=str(base/'recovered')
            assert json.loads(run(music+['get',saved['track_ids'][0]]))['title']=='Recover me'
            run(['restic','--repo',env['MUSIC_CATALOG_RESTIC_REPOSITORY'],'check','--read-data'])
            print('Encrypted SFTP registration, retry, health, and disaster recovery passed',flush=True)

            escaped=base/'must-not-exist'
            subprocess.run(['ssh','playlist-sftp-test','touch '+str(escaped)],input=b'',capture_output=True,env=env,timeout=10)
            assert not escaped.exists(),'The account unexpectedly executed a shell command'
            outside=base/'outside-passwd'
            denied=subprocess.run(['sftp','-F',str(client_config),'-b','-','playlist-sftp-test'],
                input=f'get /etc/passwd {outside}\n'.encode(),capture_output=True,env=env,timeout=10)
            assert denied.returncode and not outside.exists(),'The account escaped its chroot'
            forwarding=subprocess.run(['ssh','-W','127.0.0.1:22','playlist-sftp-test'],input=b'',capture_output=True,env=env,timeout=10)
            assert forwarding.returncode,'TCP forwarding was unexpectedly allowed'
            print('Shell, forwarding, and filesystem escape restrictions passed',flush=True)
        finally:
            if daemon:
                daemon.terminate(); daemon.wait(timeout=10)
            MAIN.write_bytes(original); MAIN.chmod(original_mode)
            FRAGMENT.unlink(missing_ok=True); KEYS.unlink(missing_ok=True)
            subprocess.run(['/usr/sbin/sshd','-t'],check=True)
            subprocess.run(['systemctl','reload','ssh'],check=True)
            subprocess.run(['userdel','playlist-backup'],check=False,capture_output=True)
            subprocess.run(['groupdel','playlist-backup'],check=False,capture_output=True)
            shutil.rmtree(JAIL,ignore_errors=True)
    print('Disposable-host SFTP deployment acceptance passed')


if __name__=='__main__': main()
