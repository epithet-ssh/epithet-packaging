#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
load_release "$1"
"$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" verify-source "$RELEASE_DIR"
exec "$PACKAGING_ROOT/freebsd/ops/epithet-pkg-publish" publish "$RELEASE_DIR"
