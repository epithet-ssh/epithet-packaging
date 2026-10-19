#!/usr/bin/env bash
# Run only in the disposable Debian container: modifies apt and dpkg state.
set -euo pipefail
cd /work
work=$(mktemp -d)
# The apt sandbox user must be able to traverse the test HTTP document root.
chmod 755 "$work"
server_pid=
trap 'test -z "$server_pid" || kill "$server_pid"; rm -rf "$work"' EXIT
tag=$(python3 -c 'import json; print(json.load(open("release.json"))["tag"])')
package="epithet_${tag#v}-1_amd64.deb"
mkdir -m 700 "$work/gnupg"
gpg --batch --homedir "$work/gnupg" --passphrase '' --quick-generate-key 'Packaging CI' rsa3072 sign 0
fingerprint=$(gpg --homedir "$work/gnupg" --with-colons --list-keys | awk -F: '$1 == "fpr" {print $10; exit}')
mkdir -p /etc/apt/keyrings
gpg --homedir "$work/gnupg" --armor --export "$fingerprint" > /etc/apt/keyrings/epithet-test.asc
chmod 644 /etc/apt/keyrings/epithet-test.asc
mkdir "$work/old"
python3 - "$work/old/nfpm.json" <<'PY'
import json, sys
config = json.load(open('dist/nfpm.json'))
config['version'] = '0.0.0'
json.dump(config, open(sys.argv[1], 'w'))
PY
nfpm package --config "$work/old/nfpm.json" --packager deb --target "$work/old/epithet_0.0.0-1_amd64.deb"
(cd "$work/old" && dpkg-scanpackages --hash sha256 . /dev/null > Packages)
python3 tests/stage_debian.py "$work/old" "$work/public" "$work/gnupg" "$fingerprint" v0.0.0
python3 -m http.server 8765 --bind 127.0.0.1 --directory "$work/public" > "$work/http.log" 2>&1 &
server_pid=$!
python3 - <<'PY'
import time, urllib.request
for attempt in range(100):
    try:
        urllib.request.urlopen('http://127.0.0.1:8765/debian/InRelease', timeout=1).close()
        break
    except OSError:
        time.sleep(.1)
else:
    raise RuntimeError('test HTTP server did not start')
PY
cat > /etc/apt/sources.list.d/epithet.sources <<'SOURCES'
Types: deb
URIs: http://127.0.0.1:8765/debian
Suites: ./
Architectures: amd64
Signed-By: /etc/apt/keyrings/epithet-test.asc
SOURCES
apt-get -o APT::Update::Error-Mode=any update
apt-get install -y epithet
test "$(dpkg-query -W -f='${Version}' epithet)" = '0.0.0-1'
mkdir -p /var/lib/epithet /etc/ssh/sshd_config.d
printf 'preserved enrollment\n' > /var/lib/epithet/domain
printf '# preserved ssh config\n' > /etc/ssh/sshd_config.d/60-epithet.conf
sha256sum /var/lib/epithet/domain /etc/ssh/sshd_config.d/60-epithet.conf > "$work/state.sha256"
python3 tests/stage_debian.py dist "$work/public" "$work/gnupg" "$fingerprint" "$tag"
python3 - <<'PY'
import urllib.request
urllib.request.urlopen('http://127.0.0.1:8765/debian/epithet_0.0.0-1_amd64.deb').close()
PY
apt-get -o APT::Update::Error-Mode=any update
apt-get install -y --only-upgrade epithet
test "$(dpkg-query -W -f='${Version}' epithet)" = "${tag#v}-1"
epithet --version | grep -F "${tag#v}"
epithet host enroll --help >/dev/null
test -f /usr/share/doc/epithet/copyright
sha256sum -c "$work/state.sha256"
apt-get purge -y epithet
test ! -e /usr/bin/epithet
sha256sum -c "$work/state.sha256"
apt-get install -y epithet
apt-get purge -y epithet

# apt authenticates package bytes through the signed index's SHA256 value.
public="$work/public/debian"
cp "$public/$package" "$work/package.deb"
printf 'damaged package' > "$public/$package"
rm -f /var/cache/apt/archives/epithet_*.deb
if apt-get install -y epithet; then echo 'accepted damaged package' >&2; exit 1; fi
cp "$work/package.deb" "$public/$package"
apt-get install -y epithet

cp "$public/current/InRelease" "$work/InRelease"
printf 'damaged signature' > "$public/current/InRelease"
if apt-get -o APT::Update::Error-Mode=any update; then echo 'accepted damaged repository signature' >&2; exit 1; fi
cp "$work/InRelease" "$public/current/InRelease"
apt-get -o APT::Update::Error-Mode=any update
rm /etc/apt/keyrings/epithet-test.asc
if apt-get -o APT::Update::Error-Mode=any update; then echo 'accepted untrusted repository' >&2; exit 1; fi
