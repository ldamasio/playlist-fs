# Backup and recovery

## Local snapshots

Every metadata mutation attempts a local snapshot after its transaction commits. Backup failure does not undo the saved registration. An explicit snapshot is also available:

```bash
music catalog backup
music catalog backup --to /path/private-backups
music catalog verify /path/snapshot.zip
music catalog restore /path/snapshot.zip --to /path/new-catalog
MUSIC_CATALOG_DIR=/path/new-catalog music catalog status
```

Restore requires a destination that does not exist and never replaces a live catalog. Archives include a consistent SQLite copy, complete JSONL, SQL, and SHA-256 manifest. Validation checks database integrity, current-state/audit agreement, all member hashes, and equivalence of both recovery formats. Recovery rejects unexpected archive members and decompressed metadata larger than 512 MiB. Backup files are published atomically after validation. The app keeps local directories private and creates data files with mode 600.

Local ZIP files are plaintext, not encrypted. Filesystem permissions are not disk encryption. Local snapshots on the same disk do not protect against disk loss. Audio files and filesystem playlists are not included in these metadata snapshots; back them up separately.

## Encrypted replicas using Restic

Use an existing, independently recoverable Restic repository, or explicitly initialize a dedicated one. Restic is optional, installed separately; version 0.16.4 or later is tested. The app never initializes a remote repository or creates credentials implicitly.

For a local test repository or an external drive:

```bash
export RESTIC_PASSWORD_FILE=/path/private/repository-password
restic --repo /path/backup-repository init
music catalog replicate --repository /path/backup-repository --label external-drive
```

The password file should be private (600). Keep an independently recoverable copy of the password and access credentials. Losing the repository password makes the encrypted backups unusable. Do not put passwords into Git, command-line arguments, or a service environment file; reference a password file or your existing credential mechanism.

For a dedicated SFTP directory, after the server, user, pinned SSH host key, and access have been provisioned:

```bash
restic --repo sftp:backup-user@backup-host:/srv/backups/personal-music init
music catalog replicate \
  --repository sftp:backup-user@backup-host:/srv/backups/personal-music --label jaguar
```

These hostnames and paths are placeholders, not infrastructure setup commands for a real server. Use a dedicated backup account and directory; never reuse a shared production database directory. Preserve SSH host verification. SFTP requires an SSH/SFTP server; Restic itself runs on the client.

The app verifies a local archive, uploads it through Restic, then reads the exact snapshot back and checks its SHA-256 before recording a receipt. Repository/storage errors, wrong keys, and timeouts leave the local capture saved and report a pending replica. No successful receipt is fabricated. A lost acknowledgement can create another Restic snapshot on retry; content is deduplicated by Restic and track captures remain idempotent.

## Automatic copies after each mutation

Only the catalog-specific opt-in enables automatic network/storage access:

```bash
export MUSIC_CATALOG_RESTIC_REPOSITORY=sftp:backup-user@backup-host:/srv/backups/personal-music
export MUSIC_CATALOG_RESTIC_LABEL=jaguar
export RESTIC_PASSWORD_FILE=/path/private/repository-password
music catalog add --artist "Example performer" --title "Example title" --request-id capture-001
```

`RESTIC_REPOSITORY` alone does not opt a catalog into automatic copying. `MUSIC_BACKUP_TIMEOUT` sets a timeout in seconds for each Restic subprocess (default 120). Successful readback only acknowledges the snapshot's audit head; simultaneous new captures can make it stale immediately. Consult `status` for current coverage.

For periodic retries, [systemd user service/timer examples](../examples/systemd) run `music catalog replicate` hourly and after missed runs. Configure their private environment file and review the destination before enabling them. They are templates, not enabled by installation. Failures appear in the user journal and service status. No external notification service is configured.

## Disaster recovery without the original computer

Install Python 3, this repository, and Restic on a recovery machine. Retrieve the repository credentials/password from independent custody. Find the desired explicit snapshot ID:

```bash
restic --repo <repository> snapshots --tag playlist-fs
music catalog restore-restic --repository <repository> \
  --snapshot <snapshot-id> --to /path/recovered-catalog
MUSIC_CATALOG_DIR=/path/recovered-catalog music catalog status
MUSIC_CATALOG_DIR=/path/recovered-catalog music catalog search "known title"
```

The app recovers `/playlist-fs/catalog.zip` from the chosen snapshot and performs the same verification as local recovery. It does not need the old catalog, old computer, receipt table, k3s, or a working database server. A password available only inside the lost infrastructure does not meet this requirement.

## Retention and operational acceptance

Local snapshots and Restic snapshots are retained until explicitly managed. Automatic pruning is intentionally absent. Choose a retention window that can recover older accidental changes, monitor capacity, and use Restic's documented retention commands on this dedicated repository.

For a reliable deployment, demonstrate: registration without internet; current verified copy on another machine; another encrypted copy with independent provider/account or offline custody; restore on a clean machine; failed-copy visibility; and recovery of credentials without the primary infrastructure. Re-run restore drills periodically and after upgrades. A second copy on Jaguar alone cannot prove provider/account independence. No RPO/RTO or off-site availability is promised by source code or a local test.

## Operational checks and recovery drills

Run these checks on demand or from an explicitly configured scheduler:

```bash
music catalog doctor
music catalog doctor --max-age-hours 48
music catalog doctor --check-replica --require-replica --repository <repository>
music catalog drill /path/snapshot.zip --report /path/private/drill-unique.json
music catalog drill --repository <repository> --snapshot <explicit-snapshot-id> \
  --report /path/private/remote-drill-unique.json
```

`doctor` reads the database without modifying it and validates the actual local archive bytes, their receipt hash, catalog identity, audit head, and full SQLite/JSONL/SQL agreement. It accepts another valid current local copy if a newer receipt points to a missing or corrupt file. Its default policy requires a snapshot verified within 24 hours, even when the records have not changed; refresh with `backup` or change the policy deliberately. Timestamps over five minutes in the future are invalid. Age limits must be positive and finite.

Remote I/O requires `--check-replica`; merely configuring a repository never causes a network read in `doctor`. That flag requires a matching receipt for the selected repository and reads its exact Restic snapshot back, verifying the receipt hash and the full archive again. The password options/environment are the same as `replicate`. Without the flag, remote health is `not_checked`. `--require-replica` alone reports pending protection until the remote check is explicitly requested. A remote check does not create a snapshot, repair a failure, or write a new receipt. Refresh a stale copy with `replicate`.

An `ok: true` result means only that the listed requirements passed at check time. The command rechecks the live catalog head after file/network reads; if a concurrent registration changed it, the result is pending and can be retried. Exit `0` means the requested protection checks passed, `3` means incomplete protection, and `1` means input/catalog validation failed. Remote account/provider/physical independence remains unverified. Credentials, repository URLs, and Restic child diagnostics are not included in the doctor result.

`drill` restores a supplied local archive or explicit Restic snapshot into a fresh temporary directory, validates the recovered database, and compares every exported table with the snapshot. It needs no live catalog, receipt table, k3s, or database server, and leaves the authoritative catalog untouched. The temporary copy is removed before success is reported. Optional report files are private, published atomically, and never overwrite existing evidence. No success report is written after a failed restoration. Reports describe the chosen snapshot; they do not certify that it is the latest capture or an independent off-site copy. A temporary-directory drill on the original computer is preparation for a separate clean-machine drill, not proof of recovery after device loss.

After configuring a real destination, retain a private report for each destination and demonstrate a second-machine restoration with credentials retrieved independently. Configure scheduled checks and failure notification only after the destination and credential custody are established. The existing systemd templates are opt-in and remain inactive until installed and enabled.

References: [Restic repository preparation](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html), [Restic scripting](https://restic.readthedocs.io/en/stable/075_scripting.html), [SQLite network-file caveats](https://www.sqlite.org/useovernet.html).
