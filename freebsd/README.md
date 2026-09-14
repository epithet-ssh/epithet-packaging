# FreeBSD package

This directory owns the port and repository publisher previously under
`contrib/freebsd` in the source repository. Disabled-by-default rc.d services,
the service account, and configuration preservation are retained. Existing
installation keys and client repository configuration do not belong in Git.

## Package installation

Install the operator's reviewed FreeBSD public key as
`/usr/local/etc/pkg/keys/epithet.pub`. In
`/usr/local/etc/pkg/repos/Epithet.conf`, use:

```ucl
Epithet: {
    url: "REPOSITORY_BASE_URL/${ABI}/latest",
    signature_type: "pubkey",
    pubkey: "/usr/local/etc/pkg/keys/epithet.pub",
    enabled: yes
}
```

Replace the base URL, retain `${ABI}`, then run `pkg update` and
`pkg install -r Epithet epithet`. The initial ABI is `FreeBSD:15:amd64`.

The package includes the server's rc.d scripts, disabled by default. To run an
Epithet server, configure and enable the appropriate service after installation;
the package itself is the same for client and server use.

## Build and publication

The coordinator prepares a vendored source archive at an exact source commit.
The publisher copies it into Poudriere's distfiles cache, fills the port's
version/commit/build date, and generates `distinfo` locally. There is no GitHub
archive or Go module proxy dependency during the package build.

Poudriere runs `testport` and `bulk`. The port runs `go test ./...` after building.
The binary-fetch blacklist prevents substitution of Epithet itself by an
upstream package. Dependencies and build tools can come from FreeBSD mirrors.
The signed Epithet-only candidate then undergoes fresh-install, version/help,
service-file, and uninstall checks using an isolated pkg root. When a current
package exists, it also tests upgrade and preservation of enrollment/SSH state
and operator-edited configuration. **The first publication has no previous
package and therefore no upgrade check.** No Epithet daemon is started by these
package checks.

Use the shared `bin/epithet-release` entrypoint described in the [setup guide](../ops/README.md).
`freebsd/ops/epithet-pkg-publish publish RELEASE_DIRECTORY` is its internal native
step. It consumes the prepared workspace and uses the same configuration; it
never resolves tags or fetches a different source tree.

The serving layout is `$PUBLIC_ROOT/$ABI/releases/X.Y.Z/`, with `latest` pointing
to the selected release. Staging happens on that filesystem, checks precede
retention, and the pointer changes last. The retained release records source and
recipe identity so an interrupted promotion can finish without rebuilding.

For migration, pause the old publisher and retain its complete public tree and
signing key outside source control. Do not run two builders concurrently.
Publish a new version after migration; an old version without a release identity
cannot be treated as a verified completion by the new scripts.

After pausing the schedule, `freebsd/ops/epithet-pkg-publish rollback X.Y.Z`
selects a retained repository. Its `status` command reports the current native
version. Rollback changes repository metadata; clients do not automatically
downgrade. Existing retained `_N` revisions can still be selected by rollback,
but the new build flow does not create package-only revisions.
