# Metadata catalog

The catalog stores names and provenance; `_library` remains the audio-file authority. Commands emit JSON for shell integrations and do not play or download audio.

## Storage and registration

The default directory is `${XDG_DATA_HOME:-~/.local/share}/playlist-fs/catalog`. Override with `MUSIC_CATALOG_DIR` or `music catalog --directory /absolute/path <command>`. Use a local filesystem. Do not open the SQLite file over NFS, synchronize a live database through a folder-sync tool, or run independent writable copies as if they were replicas.

```bash
music catalog init
music catalog add --artist "Example performer" --title "Example title" \
  --composer "Example composer" --request-id source-unique-001
music catalog search "example"
music catalog get <track-id>
music catalog edit <track-id> --title "Corrected title" --request-id correction-unique-001
music catalog edit <track-id> --composer "First writer" --composer "Second writer"
music catalog edit <track-id> --clear-composers
music catalog edit <track-id> --reviewed
music catalog history --track-id <track-id>
music catalog status
music catalog doctor
```

Performer and composer are different fields; the application never infers authorship from the performer. `--version` distinguishes versions such as live recordings and remixes. Exact normalized identities deduplicate registrations; fuzzy matching never silently merges them. Correcting an identity to one already registered fails atomically and requires human reconciliation. Supplying different composers on a repeated `add` requires an explicit `edit`.

Track IDs persist through corrections. `--request-id` identifies an operation, not a song: reuse the same key and identical input for a retry, and use another key for a new capture or correction. Reusing a key with different input is rejected. Without a supplied key, the command generates one and returns it. Repeating a song with a fresh key preserves another source observation without duplicating the track.

`--source` preserves original text; `--source-uri` can identify a chat or another provenance location. Local saved data and its audit event commit together before backup is attempted. Original information stays in the event even after a correction.

## Pasted playlists

```bash
music catalog import-paste --source-uri "chat:playlist-reference" --request-id playlist-capture-001
# Paste lines, then Ctrl+D
```

One `Artist - Title`, `Artist — Title`, or `Artist – Title` per line is recognized. Blank lines, original text, ordering, repeated entries, and unresolved lines are retained. Unknown titles such as `xxx` and link-only lines remain pending. UTF-8 files are an optional input:

```bash
music catalog import-paste --file /path/pasted-playlist.txt --request-id playlist-capture-002
music catalog pending
```

The parser is deliberately conservative. Ambiguous performer/title order, multi-artist credits, and other paste formats need review. `pending` currently presents unresolved evidence; it is not a full resolution workflow.

## Import the earlier Music catalog

```bash
music catalog import-legacy /path/to/music.sqlite3
```

The adapter reads the earlier schema (`songs`, `sources`, `entries`, `links`, `annotations`, `recommendations`, `coverage`) read-only. It preserves existing track IDs and the full seven-table payload as hashed legacy evidence. Suggestions stay outside the registered tracks. Performer labels with review flags remain flagged. Unknown composers remain empty. Reimporting an identical payload is idempotent. Existing identity/ID conflicts fail without partial import.

The adapter preserves source rows already present in that database, not files or chat messages that were never recovered into it. The old database and source files should be retained as migration evidence. This is an explicit, one-time migration; the two applications do not synchronize their databases.

## Exports and exit status

```bash
music catalog export --to /path/private-exports
```

A new export directory contains `tracks.jsonl`, complete `catalog.jsonl` (all tables), and `catalog.sql`. SQLite, SQL, and full JSONL are compared during backup validation. Audit hashes support integrity checking; they are not digital signatures or independent proof of authenticity.

- `0`: requested operation completed. A successful registration can still have `protection: local_snapshot_only` when no replica is configured.
- `1`: validation, input, or explicitly requested operation failed. Inspect the JSON error.
- `3`: a registration/correction/import committed locally, but its backup or configured replica is pending. Inspect `local_saved` and retry with the same request ID. For `doctor`, the requested protection checks are not satisfied; this read-only command does not register or retry a capture.

`status` lists the last verified snapshot copies and whether each covers the current audit head. A later registration makes old receipts stale. A receipt is historical evidence of successful verification, not continuous remote monitoring. Physical/provider/account independence is always reported as unverified by this application.

`doctor` opens the catalog read-only and checks that at least one actual local archive matches its receipt, passes full backup validation, covers the current records, and is within the age policy (24 hours by default). It makes no network calls by default, even with a configured repository. Its `ok` applies only to the explicit `requirements` in the result; local success does not certify an external copy. See [operational checks and recovery drills](recovery.md#operational-checks-and-recovery-drills).
