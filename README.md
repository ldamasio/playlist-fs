# playlist-fs

**Playlists as filesystem projections over a canonical music library.**

`playlist-fs` is a local-first, file-based toolkit where playlists are just symlinked filesystem views over a canonical music library.

No daemon.  
No cloud.  
No login.  
Just files + symlinks + shell.

---

## Philosophy

- Your music lives in one place: `~/Music/_library/Artist/Album/Track`
- Playlists are views: `~/Music/Playlists/<name>/` containing symlinks to tracks in `_library`
- New downloads go to `_incoming/` until you curate them

---

## Install

This repo currently ships one playback command: `music`.

On Linux Mint:

```bash
sudo apt update
sudo apt install -y git mpg123
git clone https://github.com/ldamasio/playlist-fs.git
cd playlist-fs
mkdir -p ~/.local/bin
ln -sf "$PWD/bin/music"         ~/.local/bin/music
```

If `~/.local/bin` is not already in your `PATH`:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

For a full beginner walkthrough, see [docs/linux-mint.md](/home/psyctl/apps/playlist-fs/docs/linux-mint.md).

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

- Linux Mint quickstart: [docs/linux-mint.md](/home/psyctl/apps/playlist-fs/docs/linux-mint.md)
- Examples: [docs/examples.md](/home/psyctl/apps/playlist-fs/docs/examples.md)
- Design: [docs/design.md](/home/psyctl/apps/playlist-fs/docs/design.md)
