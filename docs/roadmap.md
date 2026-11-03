# Roadmap

Updated 2026-11-03. Completion means demonstrated behavior, not just an implemented command.

| Stage | State | Exit criteria |
| --- | --- | --- |
| 1. Durable local registrations | Delivered in PR #1 | Stable IDs, provenance, corrections, idempotent captures, serialized transactions, complete exports, verified local backup/recovery, unchanged filesystem playback. |
| 2. Operational recovery checks | Implemented on this branch; deployment pending | `doctor` detects missing, corrupt, stale, or mismatched copies; `drill` restores without the live catalog. Deployments must pass the external-copy criteria below. |
| 3. Complete the collection | Partial; historical pasted playlists still need locating | Import the original message content with provenance, preserve order/duplicates, resolve ambiguous pairs and damaged spelling from evidence, demonstrate coverage without declaring unseen history recovered. |
| 4. Filesystem integration | Planned | Associate stable track IDs with existing audio files; produce symlink playlists only for resolved files, preserve ordering, report missing audio, and rebuild without changing the catalog authority. |
| 5. Optional desktop | Proposed after operational acceptance | Search, register, correct, and show protection state through the same domain commands. Pass Linux Mint resource and recovery gates in [ADR 0002](adr/0002-optional-desktop.md). |
| 6. Analytics and optional server | Later, driven by actual need | Reproducible read-only analysis of provenance/coverage; a server only with an explicit authority/conflict model. Keep restoration independent of k3s. |

## Current priority: protection outside the primary device

The code supports Restic; this does not establish a deployed remote backup. Before marking stage 2 operationally complete:

1. Select a dedicated backup account/path on Jaguar with verified SSH host identity, capacity, and permissions. Keep the catalog on the local filesystem; send immutable encrypted snapshots rather than a live SQLite file.
2. Select a second destination with independent provider/account or offline custody. This choice is still open. The GitHub source repository is not a backup of private catalog records.
3. Establish independently recoverable repository passwords and access credentials. Create each dedicated repository explicitly, then replicate and validate exact-snapshot readback.
4. Restore each destination on another machine and compare catalog identity, audit head, IDs, and source evidence. Keep private drill reports and record credential recovery without the original device.
5. Enable bounded scheduled retries, define a maximum acceptable copy age, demonstrate visible failure, and choose retention/capacity monitoring before pruning anything.

No accounts, remote repositories, production infrastructure, or systemd timers are created by this branch. Health/drill commands run only when invoked and leave no resident process. Storage destinations and production activation are deployment decisions; no provider independence or recovery-time objective is inferred from local tests.

## Next desktop experiment

A GUI is optional and shares the CLI's authority. First measure a release-build vertical slice (search plus one idempotent capture and protection display) on the target Mint machine. Build that slice after external-copy acceptance, rather than coupling reliable capture to a webview. Use the performance gates in ADR 0002 to decide whether the GUI earns its ongoing maintenance and resource cost. The CLI remains usable with the GUI closed or absent.
