#!/usr/bin/env bash
# Run only inside the disposable Debian build container.
set -euo pipefail
cd /work
trap 'chown -R "${OUTPUT_UID:?}:${OUTPUT_GID:?}" /work' EXIT
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3 gnupg openssh-client openssh-server ca-certificates dpkg-dev
# Debian sshd requires its privilege-separation directory even when tests
# launch their own daemon with a temporary configuration.
install -d -m 0755 /run/sshd
# The SSH fixtures authenticate as the test runner using certificates. Debian
# locks root by default; unlock only this disposable container account. Fixture
# sshd disables password authentication, and no container ports are published.
passwd -d root
source scripts/common.sh
load_release /work
python3 tools/metadata.py verify-source /work
mkdir source dist
tar -xf source.tar.gz -C source
export CGO_ENABLED=0 GOFLAGS=-mod=vendor GOPROXY=off
export SOURCE_DATE_EPOCH=$SOURCE_EPOCH
(
    cd source
    go test ./...
    go build -trimpath -buildvcs=false \
        -ldflags "-s -w -X main.version=$VERSION -X main.commit=$SOURCE_COMMIT -X main.date=$BUILD_DATE" \
        -o /work/dist/epithet ./cmd/epithet
)
cp source/LICENSE-2.0.txt dist/LICENSE-2.0.txt
env GOFLAGS= GOPROXY=https://proxy.golang.org go install github.com/goreleaser/nfpm/v2/cmd/nfpm@v2.47.0
export PATH="$(go env GOPATH)/bin:$PATH"
python3 - "$VERSION" <<'PY'
import json, sys
config = json.load(open('debian/nfpm.json'))
config['version'] = sys.argv[1]
json.dump(config, open('dist/nfpm.json', 'w'))
PY
nfpm package --config dist/nfpm.json --packager deb --target "dist/epithet_${VERSION}-1_amd64.deb"
(cd dist && dpkg-scanpackages --hash sha256 . /dev/null > Packages)
bash tests/debian.sh
cp "dist/epithet_${VERSION}-1_amd64.deb" dist/Packages debian/
# The receipt is emitted only after source and native apt checks pass.
python3 tools/metadata.py receipt /work debian
