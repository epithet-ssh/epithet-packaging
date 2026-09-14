#!/bin/sh
# Cross-compile both macOS targets. No macOS install/service tests in v1.
set -eu
. "$(dirname -- "$0")/common.sh"
load_release "$1"
if [ -f "$RELEASE_DIR/macos/manifest.json" ]; then
    exec "$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" verify "$RELEASE_DIR" macos
fi
"$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" verify-source "$RELEASE_DIR"
work=$(mktemp -d "$RELEASE_DIR/.macos.XXXXXX")
trap 'rm -rf "$work"' EXIT
trap 'exit 130' HUP INT TERM
mkdir "$work/source" "$work/output"
tar -xf "$RELEASE_DIR/source.tar.gz" -C "$work/source"
for arch in amd64 arm64; do
    log "Cross-compiling macOS $arch"
    mkdir "$work/$arch"
    (cd "$work/source" && CGO_ENABLED=0 GOOS=darwin GOARCH="$arch" GOPROXY=off \
        go build -mod=vendor -trimpath -buildvcs=false \
        -ldflags "-s -w -X main.version=$VERSION -X main.commit=$SOURCE_COMMIT -X main.date=$BUILD_DATE" \
        -o "$work/$arch/epithet" ./cmd/epithet)
    cp "$work/source/LICENSE-2.0.txt" "$work/$arch/LICENSE-2.0.txt"
    "$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" archive "$work/$arch" \
        "$work/output/epithet_${VERSION}_darwin_${arch}.tar.gz" "$SOURCE_EPOCH"
done
mkdir -p "$RELEASE_DIR/macos"
cp "$work/output/"* "$RELEASE_DIR/macos/"
"$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" receipt "$RELEASE_DIR" macos
