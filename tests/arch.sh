#!/usr/bin/env bash
# Run only in a disposable Arch Linux container: this modifies its package DB.
set -euo pipefail
cd /work
work=$(mktemp -d)
server_pid=
trap 'test -z "$server_pid" || kill "$server_pid"; rm -rf "$work"' EXIT
tag=$(python3 -c 'import json; print(json.load(open("release.json"))["tag"])')
package="epithet-${tag#v}-1-x86_64.pkg.tar.zst"

# Generate both unsigned indexes exactly as the FreeBSD publisher will receive them.
(cd dist && repo-add epithet.db.tar.gz "$package")
mkdir -m 700 "$work/gnupg"
gpg --batch --homedir "$work/gnupg" --passphrase '' --quick-generate-key 'Packaging CI' rsa2048 sign 0
fingerprint=$(gpg --homedir "$work/gnupg" --with-colons --list-keys | awk -F: '$1 == "fpr" {print $10; exit}')
gpg --homedir "$work/gnupg" --armor --export "$fingerprint" > "$work/key.asc"
pacman-key --init
pacman-key --add "$work/key.asc"
pacman-key --lsign-key "$fingerprint"

# An older package/index exercises upgrade and old-URL retention using identical
# payload bytes; package versions differ, independent of the binary's --version.
mkdir "$work/old"
python3 - "$work/old/nfpm.json" <<'PY'
import json, sys
config = json.load(open('dist/nfpm.json'))
config['version'] = '0.0.0'
json.dump(config, open(sys.argv[1], 'w'))
PY
nfpm package --config "$work/old/nfpm.json" --packager archlinux --target "$work/old/epithet-0.0.0-1-x86_64.pkg.tar.zst"
(cd "$work/old" && repo-add epithet.db.tar.gz epithet-0.0.0-1-x86_64.pkg.tar.zst)
python3 tests/stage_arch.py "$work/old" "$work/public" "$work/gnupg" "$fingerprint" v0.0.0
python3 -m http.server 8765 --bind 127.0.0.1 --directory "$work/public" > "$work/http.log" 2>&1 &
server_pid=$!
python3 - <<'PY'
import time, urllib.request
for attempt in range(100):
    try:
        urllib.request.urlopen('http://127.0.0.1:8765/arch/x86_64/epithet.db', timeout=1).close()
        break
    except OSError:
        time.sleep(.1)
else:
    raise RuntimeError('test HTTP server did not start')
PY
cat >> /etc/pacman.conf <<'EOF'

[epithet]
SigLevel = Required
Server = http://127.0.0.1:8765/arch/$arch
EOF
pacman -Syy --noconfirm
pacman -S --noconfirm epithet
test "$(pacman -Q epithet)" = 'epithet 0.0.0-1'

mkdir -p /var/lib/epithet /etc/ssh/sshd_config.d
printf 'preserved enrollment\n' > /var/lib/epithet/domain
printf '# preserved ssh config\n' > /etc/ssh/sshd_config.d/60-epithet.conf
sha256sum /var/lib/epithet/domain /etc/ssh/sshd_config.d/60-epithet.conf > "$work/state.sha256"
python3 tests/stage_arch.py dist "$work/public" "$work/gnupg" "$fingerprint" "$tag"
python3 - <<'PY'
import urllib.request
urllib.request.urlopen('http://127.0.0.1:8765/arch/x86_64/epithet-0.0.0-1-x86_64.pkg.tar.zst').close()
PY
pacman -Syu --noconfirm
test "$(pacman -Q epithet)" = "epithet ${tag#v}-1"
epithet --version | grep -F "${tag#v}"
epithet host enroll --help >/dev/null
test -f /usr/share/licenses/epithet/LICENSE
sha256sum -c "$work/state.sha256"
pacman -R --noconfirm epithet
test ! -e /usr/bin/epithet
sha256sum -c "$work/state.sha256"
# Fresh install of the current version, through the signed HTTP repository.
pacman -S --noconfirm epithet
pacman -R --noconfirm epithet

# No embedded PGPSIG is needed: missing or damaged detached package signatures
# must fail, including after pacman has previously cached the package.
public="$work/public/arch/x86_64"
rm -f /var/cache/pacman/pkg/epithet-*
cp "$public/$package.sig" "$work/package.sig"
printf 'damaged signature' > "$public/$package.sig"
if pacman -S --noconfirm epithet; then echo 'accepted damaged package signature' >&2; exit 1; fi
cp "$work/package.sig" "$public/$package.sig"

# A metadata/signature pair straddling generations fails closed.
cp "$public/current/epithet.db.tar.gz.sig" "$work/db.sig"
cp "$public/generations/v0.0.0/epithet.db.tar.gz.sig" "$public/current/epithet.db.tar.gz.sig"
if pacman -Syy --noconfirm; then echo 'accepted mismatched database signature' >&2; exit 1; fi
cp "$work/db.sig" "$public/current/epithet.db.tar.gz.sig"
pacman -Syy --noconfirm
pacman -S --noconfirm epithet

# An untrusted signing key must not validate the repository either.
pacman -R --noconfirm epithet
pacman-key --delete "$fingerprint"
if pacman -Syy --noconfirm; then echo 'accepted untrusted repository key' >&2; exit 1; fi
