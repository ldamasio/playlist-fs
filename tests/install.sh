#!/usr/bin/env bash
set -euo pipefail

ROOT="$(mktemp -d)"
cleanup() { rm -rf "$ROOT"; }
trap cleanup EXIT

export HOME="$ROOT/home"
export INSTALL_BIN_DIR="$HOME/.local/bin"
TEST_BIN="$ROOT/bin"

mkdir -p "$HOME" "$TEST_BIN"

cat > "$TEST_BIN/mpg123" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TEST_BIN/mpg123"

PATH="$TEST_BIN:/usr/bin:/bin" bash "$(dirname "$0")/../bin/install" > "$ROOT/install.out"

test -L "$INSTALL_BIN_DIR/music"
test "$(readlink -f "$INSTALL_BIN_DIR/music")" = "$(readlink -f "$(dirname "$0")/../bin/music")"
grep -F "linked $INSTALL_BIN_DIR/music ->" "$ROOT/install.out" >/dev/null
grep -F "add $INSTALL_BIN_DIR to PATH with:" "$ROOT/install.out" >/dev/null

PATH="$TEST_BIN:$INSTALL_BIN_DIR:/usr/bin:/bin" bash "$(dirname "$0")/../bin/install" > "$ROOT/reinstall.out"
grep -F "already installed at $INSTALL_BIN_DIR/music" "$ROOT/reinstall.out" >/dev/null
grep -F "$INSTALL_BIN_DIR is already in PATH" "$ROOT/reinstall.out" >/dev/null

PATH="$TEST_BIN:$INSTALL_BIN_DIR:/usr/bin:/bin" bash "$(dirname "$0")/../bin/uninstall" > "$ROOT/uninstall.out"
test ! -e "$INSTALL_BIN_DIR/music"
grep -F "removed $INSTALL_BIN_DIR/music" "$ROOT/uninstall.out" >/dev/null

PATH="$TEST_BIN:$INSTALL_BIN_DIR:/usr/bin:/bin" bash "$(dirname "$0")/../bin/uninstall" > "$ROOT/uninstall-empty.out"
grep -F "nothing to remove at $INSTALL_BIN_DIR/music" "$ROOT/uninstall-empty.out" >/dev/null

echo "install smoke test passed"
