#!/usr/bin/env bash
set -euo pipefail

ROOT="$(mktemp -d)"
cleanup() { rm -rf "$ROOT"; }
trap cleanup EXIT

export MUSIC_DIR="$ROOT/Music"
LOG="$ROOT/mpg123.log"
export PLAYLIST_FS_TEST_LOG="$LOG"

mkdir -p \
  "$MUSIC_DIR/_library/Artist/Album" \
  "$MUSIC_DIR/Playlists/focus" \
  "$ROOT/bin"

printf 'mp3-one\n' > "$MUSIC_DIR/_library/Artist/Album/01 - One.mp3"
printf 'mp3-two\n' > "$MUSIC_DIR/_library/Artist/Album/02 - Two.mp3"
printf 'flac-skip\n' > "$MUSIC_DIR/_library/Artist/Album/03 - Skip.flac"

ln -s "$MUSIC_DIR/_library/Artist/Album/01 - One.mp3" \
  "$MUSIC_DIR/Playlists/focus/artist-one.mp3"
ln -s "$MUSIC_DIR/_library/Artist/Album/03 - Skip.flac" \
  "$MUSIC_DIR/Playlists/focus/artist-skip.flac"

cat > "$ROOT/bin/mpg123" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

log="${PLAYLIST_FS_TEST_LOG:?}"
printf '%s\n' "$@" > "$log"
EOF
chmod +x "$ROOT/bin/mpg123"

wait_for_log() {
  local log_file="$1"

  for _ in $(seq 1 50); do
    [ -s "$log_file" ] && return 0
    sleep 0.1
  done

  return 1
}

PATH="$ROOT/bin:$PATH" bash "$(dirname "$0")/../bin/music"
wait_for_log "$LOG"

grep -Fx -- '-q' "$LOG" >/dev/null
grep -Fx -- '-Z' "$LOG" >/dev/null
grep -Fx -- "$MUSIC_DIR/Playlists/focus/artist-one.mp3" "$LOG" >/dev/null
if grep -F -- '.flac' "$LOG" >/dev/null; then
  echo "unexpected flac passed to mpg123" >&2
  exit 1
fi

: > "$LOG"
PATH="$ROOT/bin:$PATH" bash "$(dirname "$0")/../bin/music" "$MUSIC_DIR/_library"
wait_for_log "$LOG"

grep -Fx -- "$MUSIC_DIR/_library/Artist/Album/01 - One.mp3" "$LOG" >/dev/null
grep -Fx -- "$MUSIC_DIR/_library/Artist/Album/02 - Two.mp3" "$LOG" >/dev/null
if grep -F -- '.flac' "$LOG" >/dev/null; then
  echo "unexpected flac passed to mpg123" >&2
  exit 1
fi

if PATH="$ROOT/bin:$PATH" bash "$(dirname "$0")/../bin/music" "$MUSIC_DIR" >/dev/null 2>&1; then
  echo "music unexpectedly accepted the music root" >&2
  exit 1
fi

echo "playback smoke test passed"
