#!/bin/sh
set -eu
. "$(dirname -- "$0")/common.sh"
: "${SOURCE_URL:?}" "${SOURCE_CACHE:?}" "${WORK_ROOT:?}"
case "${1:-}" in
fetch)
    if [ ! -d "$SOURCE_CACHE" ]; then
        git clone --bare -- "$SOURCE_URL" "$SOURCE_CACHE"
    fi
    [ "$(git --git-dir="$SOURCE_CACHE" remote get-url origin)" = "$SOURCE_URL" ] || {
        echo 'SOURCE_CACHE belongs to a different source repository' >&2; exit 1;
    }
    # Deliberately do not force tags: changing an existing release is an error.
    git --git-dir="$SOURCE_CACHE" fetch origin 'refs/tags/*:refs/tags/*'
    ;;
prepare)
    [ "$#" -eq 3 ] || exit 64
    "$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" prepare "$2" "$3"
    load_release "$WORK_ROOT/$2"
    if [ -f "$RELEASE_DIR/source.tar.gz" ]; then
        "$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" verify-source "$RELEASE_DIR"
        exit 0
    fi
    work=$(mktemp -d "$RELEASE_DIR/.source.XXXXXX")
    trap 'rm -rf "$work"' EXIT
    trap 'exit 130' HUP INT TERM
    mkdir "$work/source"
    git --git-dir="$SOURCE_CACHE" archive --format=tar "$SOURCE_COMMIT" > "$work/source.tar"
    tar -xf "$work/source.tar" -C "$work/source"
    # Dependencies are gathered once for all OS targets and protected by go.sum.
    # Builders use the resulting vendor tree, not forge-specific archive URLs.
    (cd "$work/source" && go mod vendor)
    "$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" archive "$work/source" "$work/source.tar.gz" "$SOURCE_EPOCH"
    "$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" seal-source "$RELEASE_DIR" "$work/source.tar.gz"
    ;;
*) echo 'usage: source.sh fetch | prepare TAG FULL_COMMIT' >&2; exit 64 ;;
esac
