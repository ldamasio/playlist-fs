# Examples

## Create the base layout

```bash
mkdir -p "$HOME/Music/_library"
mkdir -p "$HOME/Music/Playlists/focus"
```

## Add music to the canonical library

```bash
mkdir -p "$HOME/Music/_library/Tycho/Awake"
cp "/path/to/01 - Awake.mp3" "$HOME/Music/_library/Tycho/Awake/"
```

## Link a track into a playlist

```bash
ln -s \
  "$HOME/Music/_library/Tycho/Awake/01 - Awake.mp3" \
  "$HOME/Music/Playlists/focus/tycho-awake.mp3"
```

## Link another track into another playlist

```bash
mkdir -p "$HOME/Music/Playlists/sleep"
ln -s \
  "$HOME/Music/_library/Nils Frahm/Spaces/01 - An Aborted Beginning.mp3" \
  "$HOME/Music/Playlists/sleep/nils-frahm-aborted-beginning.mp3"
```

## Inspect links

```bash
ls -la "$HOME/Music/Playlists/focus"
readlink -f "$HOME/Music/Playlists/focus/tycho-awake.mp3"
```

## Broken links (cleanup idea)

```bash
find "$HOME/Music/Playlists" -type l ! -exec test -e {} \; -print
```

## List only playable `.mp3` files from a playlist

```bash
find -L "$HOME/Music/Playlists/focus" -type f -iname '*.mp3'
```

## Playback

Default playlist:

```bash
music
```

Specific playlist:

```bash
music "$HOME/Music/Playlists/focus"
```

Entire library:

```bash
music "$HOME/Music/_library"
```

Stop playback:

```bash
pkill -x mpg123
```

## Linux Mint tutorial

For a full step-by-step guide, see [docs/linux-mint.md](/home/psyctl/apps/playlist-fs/docs/linux-mint.md).
