#!/bin/sh
# Run packaging Go commands with a patched, installed release compiler.
# Shared by every platform; keeping it here also includes it in standalone ports.
# GOTOOLCHAIN=local keeps go.mod/go.work from selecting an unchecked toolchain.
set -eu
compiler=$1
shift
export GOTOOLCHAIN=local
version=$("$compiler" env GOVERSION)
if ! printf '%s\n' "$version" | awk '
    # Distribution compilers may append Go experiment metadata (e.g. Arch).
    /^go[0-9]+\.[0-9]+\.[0-9]+(-X:[A-Za-z0-9_,]+)?$/ {
        sub(/-X:.*/, "")
        sub(/^go/, "")
        split($0, v, ".")
        valid = v[1] > 1 || (v[1] == 1 && (v[2] > 27 ||
            (v[2] == 27 && v[3] >= 3) || (v[2] == 26 && v[3] >= 10)))
    }
    END { exit !valid }
'; then
    echo "Unsupported Go compiler: $version; packaging requires Go 1.26.10+, 1.27.3+, or a later stable release (eMudhra mitigation)." >&2
    exit 1
fi
exec "$compiler" "$@"
