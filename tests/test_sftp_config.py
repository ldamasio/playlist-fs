"""Parse the real OpenSSH policy, including its effect on unrelated users."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from jinja2 import Template
except ImportError:
    Template = None

REPO = Path(__file__).resolve().parents[1]
SSHD = shutil.which('sshd')


@unittest.skipUnless(SSHD and Template,'install openssh-server and python3-jinja2 for SFTP policy tests')
class SftpPolicyTests(unittest.TestCase):
    def test_scoped_policy_is_valid_and_leaves_administrator_access_identical(self):
        with tempfile.TemporaryDirectory() as task_tmp:
            base=Path(task_tmp)
            subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(base/'host')],check=True)
            policy=Template((REPO/'ops/ansible/templates/backup-sftp.conf.j2').read_text()).render(
                playlist_backup_user='playlist-backup',playlist_backup_jail='/srv/playlist-fs-backup',
                playlist_backup_keys='/etc/ssh/playlist-fs-backup.keys')
            fragment=base/'backup.conf'; fragment.write_text(policy)
            config=base/'sshd_config'
            original=f'HostKey {base}/host\nUsePAM no\nPasswordAuthentication no\n'
            def effective(user):
                return subprocess.run([SSHD,'-T','-f',str(config),'-C',
                    f'user={user},host=localhost,addr=127.0.0.1'],check=True,capture_output=True,text=True).stdout
            config.write_text(original)
            before=effective('root')
            config.write_text(original+f'Include {fragment}\n')
            self.assertEqual(before,effective('root'))
            self.assertEqual(before,effective('unrelated-user'))
            result=effective('playlist-backup').splitlines()
            for setting in ('chrootdirectory /srv/playlist-fs-backup',
                            'forcecommand internal-sftp -d /repository -u 0077',
                            'disableforwarding yes','authenticationmethods publickey','permittty no',
                            'permituserrc no','passwordauthentication no'):
                self.assertIn(setting,result)
            # Inlining a Match block before global directives is invalid; always
            # validate the assembled policy rather than a standalone fragment.
            config.write_text(f'HostKey {base}/host\n'+policy+'\nUsePAM no\n')
            invalid=subprocess.run([SSHD,'-T','-f',str(config)],capture_output=True)
            self.assertNotEqual(invalid.returncode,0)


if __name__=='__main__':
    unittest.main()
