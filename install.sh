#!/bin/sh
set -eu
PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$PACKAGE_DIR/install.py" "$@"
fi
exec python "$PACKAGE_DIR/install.py" "$@"
