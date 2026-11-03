# Deploy a dedicated SFTP backup destination

This is an explicit deployment procedure for an existing SSH host, separate from installing the CLI. It provisions a small account and directory; Restic encryption/compression runs on the client. No k3s workload or database service is needed. Apply it only to a reviewed host with production authorization and a verified host key.

## Server scope

The opt-in [Ansible playbook](../ops/ansible/backup-host.yml) uses only built-in Ansible modules. It manages exactly:

- System account/group `playlist-backup`, password locked, no login shell, no supplementary groups.
- Root-owned chroot `/srv/playlist-fs-backup` and user-owned mode-700 subdirectory `repository`.
- A dedicated public key in `/etc/ssh/playlist-fs-backup.keys`; it is public material, root-owned and readable by SSH authentication.
- Scoped policy `/etc/ssh/playlist-fs-backup.conf`, included at the end of `/etc/ssh/sshd_config`.

The account is forced into `internal-sftp`, confined to its chroot, and denied shell, forwarding, TTY, and user startup scripts. Repository path `/repository` on the client is `/srv/playlist-fs-backup/repository` on the server. The SFTP account can modify/delete its own encrypted repository: this is not an append-only or independently immutable copy.

The playbook refuses an unrelated existing account, directory, or managed-file path, and refuses symlinks. It validates the assembled SSH configuration and checks that the effective root administrator policy is identical before reloading SSH. A validation/reload failure restores the previous main configuration and fragment, then reloads the restored policy. Account/repository data is retained for inspection; rollback never deletes backup data. Review a failure before retrying. No packages, new listener ports, firewall rules, Kubernetes resources, or database settings are changed on the server.

## Review and apply

Install Ansible on the control machine and verify administrative SSH access with strict host-key verification. Copy [inventory.example.yml](../ops/ansible/inventory.example.yml) to a private location and replace its documentation address. Use a dedicated Ed25519 key, not a reused administrative identity. Keep private keys out of the repository and public PRs.

```bash
ansible-playbook --syntax-check -i /private/inventory.yml ops/ansible/backup-host.yml
# After the reviewed production operation is authorized:
ansible-playbook -i /private/inventory.yml ops/ansible/backup-host.yml \
  --limit backup-host -e playlist_backup_public_key_file=/private/client_ed25519.pub
```

Syntax/check-mode output is not deployment acceptance. The CI disposable-host fixture exercises an actual account, assembled-policy rollback, idempotent application, encrypted SFTP capture/retry/readback, recovery after deleting the original catalog, and shell/forwarding/chroot restrictions. Never run `tests/sftp_deployment.py` on a workstation or production host; it deliberately mutates a disposable VM's account and SSH configuration and is gated to GitHub Actions.

## Configure the client and credential custody

Install Restic from the distribution packages. Place a dedicated client alias in a private SSH configuration file, and include it at the **start** of the normal `~/.ssh/config` so it is outside other `Host` sections:

```sshconfig
Host playlist-backup-destination
    HostName <reviewed-host-address>
    User playlist-backup
    IdentityFile /absolute/private/client_ed25519
    IdentitiesOnly yes
    BatchMode yes
    StrictHostKeyChecking yes
    UserKnownHostsFile /absolute/private/known_hosts
    ServerAliveInterval 30
    ServerAliveCountMax 2
```

Pin the host key from the already trusted administrative connection or an independent verified fingerprint. Do not bootstrap trust by disabling verification. Protect private files/directories with 600/700 permissions. Generate a separate high-entropy Restic password directly into a private file without printing it or placing it in command arguments. Establish a recovery copy outside the primary computer; a password stored only on the lost device makes remote ciphertext unusable. No custody/independence claim follows from creating a local password file.

Initialize only the dedicated repository, then capture/read back and drill it:

```bash
export RESTIC_PASSWORD_FILE=/absolute/private/restic-password
export MUSIC_CATALOG_RESTIC_REPOSITORY=sftp:playlist-backup-destination:/repository
export MUSIC_CATALOG_RESTIC_LABEL=dedicated-sftp
restic --repo "$MUSIC_CATALOG_RESTIC_REPOSITORY" init
music catalog replicate
music catalog doctor --check-replica --require-replica
music catalog drill --snapshot <returned-snapshot-id> --report /private/drill-unique.json
```

Also demonstrate restoration on another machine with independently recovered credentials. The temporary local drill is useful acceptance evidence but not proof of surviving device loss. A copy on a shared host/provider remains a correlated copy; add the separate destination selected in the roadmap.

## Scheduling and retention

After verified readback/restoration, the [systemd user service/timer](../examples/systemd) can retry hourly. Put the reviewed repository/label/password-file path into `~/.config/playlist-fs/backup.env` (mode 600, absolute paths). Saving this environment file affects the service only; interactive captures need the explicit exports above for immediate replication. Otherwise they retain local snapshots and the timer sends the next copy.

```bash
install -d -m 700 ~/.config/playlist-fs ~/.config/systemd/user
install -m 644 examples/systemd/playlist-fs-backup.service ~/.config/systemd/user/
install -m 644 examples/systemd/playlist-fs-backup.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now playlist-fs-backup.timer
systemctl --user start playlist-fs-backup.service
systemctl --user status playlist-fs-backup.service
journalctl --user -u playlist-fs-backup.service
```

The timer runs while the user manager is available; `Persistent=true` retries missed calendar runs when that manager starts. It does not wake a powered-off computer or promise unattended operation after logout. No lingering or external notification channel is enabled by these templates. Failure is visible through the service journal and `doctor`; configure notification if unattended detection is required. Choose retention/capacity policy explicitly; the application never prunes automatically.

For rollback, disable the user timer first and preserve repository/password evidence. Restoring SSH configuration or revoking the dedicated key can stop access without deleting ciphertext. Never recursively remove the production repository as a routine rollback.

References: [OpenSSH chroot and forced commands](https://man.openbsd.org/sshd_config), [Restic SFTP repositories](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html#sftp).
