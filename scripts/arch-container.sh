#!/usr/bin/env bash
# This script intentionally modifies a disposable Arch container, never the VM.
set -euo pipefail
cd /work
trap 'chown -R "${OUTPUT_UID:?}:${OUTPUT_GID:?}" /work' EXIT
pacman -Syu --noconfirm --needed base-devel go python gnupg openssh ca-certificates
source scripts/common.sh
load_release /work
python3 tools/metadata.py verify-source /work
mkdir source dist
tar -xf source.tar.gz -C source
export CGO_ENABLED=0
export GOFLAGS=-mod=vendor
export GOPROXY=off
export SOURCE_DATE_EPOCH=$SOURCE_EPOCH
(
    cd source
    go test ./...
    go build -trimpath -buildvcs=false \
        -ldflags "-s -w -X main.version=$VERSION -X main.commit=$SOURCE_COMMIT -X main.date=$BUILD_DATE" \
        -o /work/dist/epithet ./cmd/epithet
)
cp source/LICENSE-2.0.txt dist/LICENSE-2.0.txt
# nFPM is build tooling, pinned separately from Epithet's vendored dependencies.
env GOFLAGS= GOPROXY=https://proxy.golang.org go install github.com/goreleaser/nfpm/v2/cmd/nfpm@v2.47.0
export PATH="$(go env GOPATH)/bin:$PATH"
python3 - "$VERSION" <<'PY'
import json, sys
config = json.load(open('arch/nfpm.json'))
config['version'] = sys.argv[1]
json.dump(config, open('dist/nfpm.json', 'w'))
PY
nfpm package --config dist/nfpm.json --packager archlinux --target "dist/epithet-$VERSION-1-x86_64.pkg.tar.zst"
bash tests/arch.sh
mkdir -p arch
cp "dist/epithet-$VERSION-1-x86_64.pkg.tar.zst" dist/epithet.db.tar.gz dist/epithet.files.tar.gz arch/
# A receipt is written only after every source/package test passed.
python3 tools/metadata.py receipt /work arch
