#!/bin/sh
# Send a frozen source/recipe bundle to the persistent Linux VM. Its installed
# worker creates a disposable container and returns only tested artifacts.
set -eu
. "$(dirname -- "$0")/common.sh"
load_release "$1"
: "${ARCH_SSH_TARGET:?}" "${ARCH_IMAGE:?}"
if [ -f "$RELEASE_DIR/arch/manifest.json" ]; then
    exec "$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" verify "$RELEASE_DIR" arch
fi
"$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" verify-source "$RELEASE_DIR"
work=$(mktemp -d "$RELEASE_DIR/.arch.XXXXXX")
trap 'rm -rf "$work"' EXIT
trap 'exit 130' HUP INT TERM
printf '%s\n' "$ARCH_IMAGE" > "$work/arch-image"
tar --exclude=__pycache__ -cf "$work/input.tar" \
    -C "$PACKAGING_ROOT" bin scripts tools arch freebsd macos tests \
    -C "$RELEASE_DIR" release.json source.tar.gz source.sha256 \
    -C "$work" arch-image
log "Running Arch build and package tests on configured Linux VM"
# stdin/stdout carry archives; the worker sends progress exclusively to stderr.
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$ARCH_SSH_TARGET" \
    /usr/local/libexec/epithet-arch-worker < "$work/input.tar" > "$work/result.tar"
"$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" unpack-result "$work/result.tar" "$RELEASE_DIR"
