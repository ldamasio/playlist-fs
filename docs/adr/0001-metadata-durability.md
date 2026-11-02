# ADR 0001: Durable local metadata with independently recoverable backups

Status: accepted for this implementation, 2026-11-02.

## Problem and behavior

Track references collected in chats must survive corrections, device loss, and unavailable infrastructure. They may have no audio file yet. The existing filesystem library and symlink playlists remain the playback authority.

## Decision

Add an optional Python-standard-library SQLite metadata catalog behind `music catalog`. Keep one writable catalog; replicas are immutable backup snapshots, not writable synchronized databases. Use stable UUIDs, exact normalized identities, explicit performer/composer fields, original paste evidence, transactional audit history, and caller-supplied idempotency keys. The same ID survives a corrected name. Do not infer composers, popularity, likes, or existing audio from a capture.

After committing a mutation, create a consistent local snapshot and validate both SQLite and SQL restoration. Optionally send snapshots through a configured Restic backend and verify readback before acknowledging a replica. A failed copy reports committed local data with pending protection. JSONL and SQL provide portable exits from the implementation.

Jaguar can be a dedicated remote-copy destination after access, capacity, and restoration have been validated. It is not automatically an independent off-site copy. Another provider/account or offline custody supplies an independent failure domain. k3s can host a future API or jobs; metadata recovery must remain possible without the cluster. No server resources, accounts, schedules, or remote repositories are provisioned by this change.

## Limits and later integration

Audit hashes detect accidental drift; someone able to rewrite the entire database can rewrite its hashes. Receipts prove past readback, not current remote health or independence. The catalog is single-writer-in-authority, with serialized concurrent local transactions. Two offline writable copies need an explicit synchronization/conflict protocol before they can be combined. Do not share a live SQLite file over a network filesystem.

A later API can expose this domain model, with an explicit authority migration if a server becomes primary. A future filesystem adapter can associate track IDs with existing audio files and generate playlists only for resolved files. Neither feature requires changing existing stateless playback now.
