# Design

## Goal

Keep audio files and playable playlist membership inspectable in the filesystem. Preserve metadata curation separately, including references with no downloaded audio.

- Canonical library: `~/Music/_library`
- Playlists: `~/Music/Playlists/<name>/` as symlink directories
- Staging: `~/Music/_incoming`

This keeps music management:
- local-first
- inspectable with `ls`, `find`, `readlink`
- compatible with any player
- easy to back up

---

## Invariants

1. `_library/` is the source of truth.
2. `Playlists/*` never own files — only symlinks.
3. `_incoming/` is temporary.

---

## Why symlinks (not copies)

- One track can belong to many playlists without duplication
- Removing from a playlist doesn’t delete the track
- Playlists are “views” over the library

---

## Naming and path rules

Canonical path layout:

```text
~/Music/_library/Artist/Album/Track.ext
```

Playlist link destination:

```text
~/Music/Playlists/<playlist>/<Artist - Album - Track.ext>
```

You can override the destination filename with `--name`.

---

## Playback

Playback stays stateless:

- `playlist-fs` owns the filesystem graph
- `music` resolves one path at a time with `find -L`
- `mpg123` is started as a normal background process
- stopping playback is just killing the `mpg123` process

Playback does not query the metadata catalog. The catalog is an optional durable curation record, not an authoritative index of audio files or symlinks. A registered track does not imply an audio file exists. Automatic filesystem projection or server synchronization is a later integration.

## Metadata durability

`music catalog` assigns permanent IDs and records corrections and original sources in one SQLite transaction. A request ID makes a repeated capture idempotent. An append-only audit table stores hashes and previous values; the application verifies both the chain and its agreement with current track state. This detects accidental untracked changes, not an attacker who can rewrite the database and its entire history.

Metadata backups contain a consistent SQLite snapshot, JSONL, and portable SQL. Both SQLite and SQL recovery are checked before publishing a backup. Restic replicas are acknowledged only after a byte-for-byte readback of that verified archive. Failed replication leaves committed local data intact and returns exit status 3. See [the decision](adr/0001-metadata-durability.md).

---

## Portability notes

Some players don’t follow symlinks in every configuration. When that happens:

* you can still open playlist folders directly in players that do
* or generate `.m3u` as a later optional feature (v0.x idea)
