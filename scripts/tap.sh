#!/bin/sh
# Publish a generated formula to a dedicated local tap checkout. This is the
# only packaging step which pushes Git data, and only when release is invoked.
set -eu
. "$(dirname -- "$0")/common.sh"
load_release "$1"
: "${TAP_URL:?}" "${TAP_CHECKOUT:?}" "${TAP_BRANCH:?}"
if [ ! -d "$TAP_CHECKOUT/.git" ]; then
    git clone --branch "$TAP_BRANCH" --single-branch -- "$TAP_URL" "$TAP_CHECKOUT"
fi
[ "$(git -C "$TAP_CHECKOUT" remote get-url origin)" = "$TAP_URL" ] || {
    echo 'TAP_CHECKOUT belongs to a different repository' >&2; exit 1;
}
[ "$(git -C "$TAP_CHECKOUT" branch --show-current)" = "$TAP_BRANCH" ] || {
    echo 'TAP_CHECKOUT is on the wrong branch' >&2; exit 1;
}
[ -z "$(git -C "$TAP_CHECKOUT" status --porcelain)" ] || {
    echo 'TAP_CHECKOUT has uncommitted changes' >&2; exit 1;
}
git -C "$TAP_CHECKOUT" fetch origin "$TAP_BRANCH"
git -C "$TAP_CHECKOUT" merge --ff-only FETCH_HEAD
"$PYTHON" "$PACKAGING_ROOT/tools/metadata.py" check-tap "$TAP_CHECKOUT/Formula/epithet.rb" "$TAG"
mkdir -p "$TAP_CHECKOUT/Formula"
cp "$RELEASE_DIR/macos/epithet.rb" "$TAP_CHECKOUT/Formula/epithet.rb"
git -C "$TAP_CHECKOUT" add Formula/epithet.rb
if ! git -C "$TAP_CHECKOUT" diff --cached --quiet; then
    git -C "$TAP_CHECKOUT" commit -m "chore: release epithet $VERSION"
fi
# Push even on a retry with no new diff: a preceding attempt may have committed
# locally and failed during push. Git rejects remote races without a force push.
git -C "$TAP_CHECKOUT" push origin "HEAD:refs/heads/$TAP_BRANCH"
