#!/usr/bin/env bash
set -euo pipefail

ROOT="$(mktemp -d)"
cleanup() { rm -rf "$ROOT"; }
trap cleanup EXIT

export MUSIC_DIR="$ROOT/Music"

# Run init
bash "$(dirname "$0")/../bin/music-init.sh" "$MUSIC_DIR"

# Create a fake track in canonical library
mkdir -p "$MUSIC_DIR/_library/Artist/Album"
TRACK="$MUSIC_DIR/_library/Artist/Album/01 - Track.mp3"
printf "fake" > "$TRACK"

# Link into a playlist
bash "$(dirname "$0")/../bin/music-link" "Artist/Album/01 - Track.mp3" focus --name "artist-track.mp3"

DEST="$MUSIC_DIR/Playlists/focus/artist-track.mp3"

# Assertions
test -L "$DEST"
test -e "$DEST"
test "$(readlink -f "$DEST")" = "$TRACK"

echo "✅ smoke test passed"
