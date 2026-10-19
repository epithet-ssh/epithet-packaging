#!/bin/sh
# Install on the Linux VM. Invoked through SSH by the trusted builder account.
# stdout is a result archive; all diagnostics go to stderr. No signing keys here.
set -eu
exec 3>&1 1>&2
work=$(mktemp -d)
container=epithet-debian-$(basename "$work")
cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || :
    rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM
tar -xf - -C "$work"
image=$(cat "$work/debian-image")
case "$image" in ''|-*|*[!a-zA-Z0-9_./:@-]*) echo 'invalid Debian image reference' >&2; exit 1 ;; esac
docker run --platform linux/amd64 --pull=always --rm --name "$container" \
    -e OUTPUT_UID="$(id -u)" -e OUTPUT_GID="$(id -g)" \
    -v "$work:/work" -w /work "$image" bash /work/scripts/debian-container.sh
python3 "$work/tools/metadata.py" verify "$work" debian
tag=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag"])' "$work/release.json")
tar -cf - -C "$work/debian" "epithet_${tag#v}-1_amd64.deb" Packages manifest.json >&3
