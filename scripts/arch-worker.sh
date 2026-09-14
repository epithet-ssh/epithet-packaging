#!/bin/sh
# Install on the Linux VM. Invoked through SSH by the trusted builder account.
# stdout is a result archive; all diagnostics go to stderr. No signing keys here.
set -eu
exec 3>&1 1>&2
work=$(mktemp -d)
container=epithet-arch-$(basename "$work")
cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || :
    rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
tar -xf - -C "$work"
image=$(cat "$work/arch-image")
case "$image" in ''|-*|*[!a-zA-Z0-9_./:@-]*) echo 'invalid Arch image reference' >&2; exit 1 ;; esac
docker run --pull=always --rm --name "$container" \
    -e OUTPUT_UID="$(id -u)" -e OUTPUT_GID="$(id -g)" \
    -v "$work:/work" -w /work "$image" bash /work/scripts/arch-container.sh
python3 "$work/tools/metadata.py" verify "$work" arch
tag=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag"])' "$work/release.json")
tar -cf - -C "$work/arch" "epithet-${tag#v}-1-x86_64.pkg.tar.zst" \
    epithet.db.tar.gz epithet.files.tar.gz manifest.json >&3
