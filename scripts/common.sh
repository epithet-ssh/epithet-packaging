#!/bin/sh
# Shared installed paths and trusted, operator-owned configuration.
set -eu
PACKAGING_ROOT=${PACKAGING_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
export PACKAGING_ROOT
CONFIG=${EPITHET_PACKAGING_CONFIG:-/usr/local/etc/epithet-packaging.conf}
if [ -f "$CONFIG" ]; then
    set -a
    . "$CONFIG"
    set +a
fi
PYTHON=${PYTHON:-python3}
export PYTHON

load_release() {
    RELEASE_DIR=$(CDPATH= cd -- "$1" && pwd)
    export RELEASE_DIR
    # The helper validates fields and quotes shell values before emitting them.
    release_environment=$("$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" environment "$RELEASE_DIR")
    eval "$release_environment"
    export TAG VERSION SOURCE_COMMIT SOURCE_EPOCH BUILD_DATE
}

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}
