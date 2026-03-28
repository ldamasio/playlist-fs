# Linux Mint Quickstart

This guide is for a beginner on Linux Mint who wants to go from zero to playback with the fewest moving parts possible.

## 1. Install dependencies

Open Terminal and run:

```bash
sudo apt update
sudo apt install -y git mpg123
```

`mpg123` is the playback engine. `playlist-fs` does not run a daemon or database.

## 2. Clone the repo and install the command

```bash
cd "$HOME"
git clone https://github.com/ldamasio/playlist-fs.git
cd playlist-fs
./bin/install
```

If `music` is not found after that, run the exact command printed by `./bin/install`.

The usual command is:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
source "$HOME/.bashrc"
```

Confirm the command exists:

```bash
command -v music
```

If that still says the command was not found, close Terminal, open it again, and rerun:

```bash
command -v music
```

To remove the daily-use install later:

```bash
./bin/uninstall
```

## 3. Quick test without installing into PATH

If you want to test playback from the repo itself, without relying on `PATH`, use:

```bash
./bin/music "$HOME/Music/_library"
```

That works once you already have `.mp3` files inside `"$HOME/Music/_library"`.

## 4. Create the filesystem layout

```bash
mkdir -p "$HOME/Music/_library"
mkdir -p "$HOME/Music/Playlists/focus"
```

The rules are simple:

- `_library/` is where the real files live
- `Playlists/<name>/` contains only symlinks to files in `_library`

## 5. Put music into `_library`

Create artist and album folders:

```bash
mkdir -p "$HOME/Music/_library/Artist/Album"
```

Copy one or more `.mp3` files into that album folder:

```bash
cp "/path/to/01 - Track.mp3" "$HOME/Music/_library/Artist/Album/"
cp "/path/to/02 - Track.mp3" "$HOME/Music/_library/Artist/Album/"
```

Replace `/path/to/...` with the real location of your files.

You can inspect what is there with:

```bash
find "$HOME/Music/_library" -type f
```

## 6. Create a playlist by symlinking tracks

Link a real file from `_library` into `Playlists/focus`:

```bash
ln -s \
  "$HOME/Music/_library/Artist/Album/01 - Track.mp3" \
  "$HOME/Music/Playlists/focus/artist-album-track.mp3"
```

Inspect the playlist:

```bash
ls -l "$HOME/Music/Playlists/focus"
readlink -f "$HOME/Music/Playlists/focus/artist-album-track.mp3"
```

The file inside the playlist should be a symlink pointing back to `_library`.

## 7. Start playback

Play the default playlist:

```bash
music
```

That defaults to:

```text
~/Music/Playlists/focus
```

Play a specific playlist:

```bash
music "$HOME/Music/Playlists/focus"
```

Play the entire library:

```bash
music "$HOME/Music/_library"
```

What the command does:

- walks the filesystem with `find -L`
- follows playlist symlinks
- only sends `.mp3` files to `mpg123`
- starts playback in the background

## 8. Stop playback

```bash
pkill -x mpg123
```

There is no internal playback state. Stopping playback means stopping the `mpg123` process.

## 9. Common mistakes

`music: mpg123 not found in PATH`

```bash
sudo apt install -y mpg123
```

`music: no supported audio files under: ...`

- the target folder has no `.mp3` files
- the files may be `.flac` or another unsupported format

`music: path must be ...`

- pass either `"$HOME/Music/_library"` or `"$HOME/Music/Playlists/<name>"`
- do not pass `"$HOME/Music"` or `"$HOME/Music/Playlists"` by itself

## 10. Daily use

Add more real files under `_library`, then symlink the ones you want into playlists:

```bash
mkdir -p "$HOME/Music/Playlists/night"
ln -s \
  "$HOME/Music/_library/Artist/Album/02 - Track.mp3" \
  "$HOME/Music/Playlists/night/artist-album-track-02.mp3"
music "$HOME/Music/Playlists/night"
```
