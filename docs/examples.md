# Examples

## Initialize structure

```bash
music-init.sh
```

## Custom base directory

```bash
music-init.sh "$HOME/Music"
# or
MUSIC_DIR="$HOME/Music" music-link "Artist/Album/Track.mp3" focus
```

## Link by relative path (recommended)

```bash
music-link "Tycho/Awake/01 - Awake.mp3" focus
music-link "Nils Frahm/Spaces/01 - An Aborted Beginning.flac" sleep
```

## Link by absolute path

```bash
music-link "$HOME/Music/_library/Tycho/Awake/01 - Awake.mp3" focus
```

## Use a custom filename

```bash
music-link "Tycho/Awake/01 - Awake.mp3" focus --name "tycho-awake.mp3"
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
