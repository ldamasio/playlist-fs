#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/playback.sh"
bash "$SCRIPT_DIR/install.sh"
python3 -m unittest discover -s "$SCRIPT_DIR" -p 'test_*.py' -v

echo "smoke test passed"
