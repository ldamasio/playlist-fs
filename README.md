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

Clone and put scripts in your PATH.

Option A (recommended): symlink scripts into `~/.local/bin`:

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/bin/music-init.sh" ~/.local/bin/music-init.sh
ln -sf "$PWD/bin/music-link"    ~/.local/bin/music-link
ln -sf "$PWD/bin/music"         ~/.local/bin/music
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
