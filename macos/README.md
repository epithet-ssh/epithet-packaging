# macOS and Homebrew

## Package installation

Obtain the tap name and Git URL from the package repository operator. Add the
tap using `brew tap TAP_NAME TAP_GIT_URL`, then run
`brew install TAP_NAME/epithet`.

## Build and publication

The FreeBSD builder cross-compiles amd64 and arm64 binaries from the same
vendored source as the native packages. Each archive contains `epithet` and its
license, at `/macos/releases/vX.Y.Z/epithet_X.Y.Z_darwin_ARCH.tar.gz`.

The formula template selects the architecture, pins its SHA-256, and preserves
the existing `brew services start epithet` agent service. No macOS worker or
macOS installation/service test is part of v1. The receipt explicitly records
that packaging tests were not run.

Archives become available before the formula changes. The builder updates a
dedicated checkout of the configured Git tap, commits the formula, and pushes
without force. A failed push leaves the archives available for a retry but does
not advance the local `macos/current` completion marker. A retry reuses the same
archives and pushes an already-created local commit if necessary. A divergent
or dirty tap checkout fails for operator inspection; the scripts do not reset it.

Configure an existing tap branch, its URL, Git author identity, and push
credentials on the builder. The tap can live on any Git server. Disable the
source repository's old GoReleaser tap writer at cutover so there is one writer.
The corresponding source change removes that writer while retaining optional
GitHub Release archives.

Existing tap users keep their tap name and remote when the deployment preserves
them. Public archive URLs are deployment inputs; the checked-in template
contains no deployment hostname.
