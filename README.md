# playlist-fs

**Playlists as filesystem projections over a canonical music library.**

`playlist-fs` is a local-first toolkit where playlists are symlinked filesystem views over a canonical audio library. An optional `music catalog` command preserves track names, performers, composers, original pasted sources, and corrections even before an audio file exists.

Playback uses files, symlinks, shell, and `mpg123`. The metadata catalog uses Python 3 and SQLite, without a daemon, account, or network dependency. Optional encrypted backup replicas use Restic and a repository you configure.

---

## Philosophy

- Your music lives in one place: `~/Music/_library/Artist/Album/Track`
- Playlists are views: `~/Music/Playlists/<name>/` containing symlinks to tracks in `_library`
- New downloads go to `_incoming/` until you curate them

---

## Daily Use Setup

Install the `music` command into `~/.local/bin` for normal day-to-day use.

On Linux Mint:

```bash
sudo apt update
sudo apt install -y git mpg123 python3
git clone https://github.com/ldamasio/playlist-fs.git
cd playlist-fs
./bin/install
```

If `~/.local/bin` is not already in your `PATH`, `./bin/install` prints the exact command to add it.

To remove the daily-use install later:

```bash
./bin/uninstall
```

For the full beginner flow on Linux Mint, see [docs/linux-mint.md](docs/linux-mint.md).

## Register and recover music metadata

```bash
music catalog add --artist "Example performer" --title "Example title" --request-id capture-001
music catalog search "Example"
music catalog status
music catalog pending
music catalog backup
```

Use a unique request ID for each capture and reuse it when retrying that capture. Corrections use `music catalog edit <track-id>` and keep the same permanent track ID. `--composer` is repeatable and remains distinct from `--artist` (performer). Unknown composers stay unknown.

Paste playlists into `music catalog import-paste`, then end standard input with Ctrl+D. Every original line is kept; ambiguous lines appear under `pending`. See [catalog commands](docs/catalog.md), [backup and disaster recovery](docs/recovery.md), and the [architecture decision](docs/adr/0001-metadata-durability.md).

`MUSIC_CATALOG_DIR` selects an explicit local catalog; the default is `${XDG_DATA_HOME:-~/.local/share}/playlist-fs/catalog`. Personal data stays outside this public source repository. `music catalog` works without `mpg123` installed.

## Quick Test

If you just want to test the repo before installing anything into your shell, run the script directly:

```bash
./bin/music "$HOME/Music/_library"
./bin/music "$HOME/Music/Playlists/focus"
```

## Quick Start

Create the canonical library and one playlist:

```bash
mkdir -p "$HOME/Music/_library/Artist/Album"
mkdir -p "$HOME/Music/Playlists/focus"
```

Put `.mp3` files into `_library`:

```bash
cp "/path/to/01 - Track.mp3" "$HOME/Music/_library/Artist/Album/"
```

Link one track into the playlist:

```bash
ln -s \
  "$HOME/Music/_library/Artist/Album/01 - Track.mp3" \
  "$HOME/Music/Playlists/focus/artist-album-track.mp3"
```

## Playback

`music` is a stateless wrapper around `mpg123`.

- It reads the filesystem at launch time.
- It follows playlist symlinks with `find -L`.
- It only passes `.mp3` files to `mpg123`.
- It backgrounds playback and leaves process control to the shell.

Examples:

```bash
music
music "$HOME/Music/Playlists/focus"
music "$HOME/Music/_library"
pkill -x mpg123
```

## Docs

- Linux Mint quickstart: [docs/linux-mint.md](docs/linux-mint.md)
- Examples: [docs/examples.md](docs/examples.md)
- Design: [docs/design.md](docs/design.md)
- Metadata catalog: [docs/catalog.md](docs/catalog.md)
- Recovery: [docs/recovery.md](docs/recovery.md)

## Tests

```bash
bash tests/smoke.sh
```

Install `restic` to include real encrypted-repository recovery tests (`sudo apt install restic`). Without it, those integration tests are explicitly skipped. CI requires them. Test data is synthetic; CI never connects to personal servers or reads a real catalog.
