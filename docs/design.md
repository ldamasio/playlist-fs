# Design

## Goal

Make playlists a filesystem concern, not a database concern.

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

This avoids duplicating `_library` and `Playlists` in a second index or daemon.

---

## Portability notes

Some players don’t follow symlinks in every configuration. When that happens:

* you can still open playlist folders directly in players that do
* or generate `.m3u` as a later optional feature (v0.x idea)
