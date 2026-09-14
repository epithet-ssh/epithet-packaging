# Operating the package repository infrastructure

This guide covers the infrastructure that builds, signs, and serves Epithet
packages: builders, publication, and recovery. To install the Epithet package
for client or server use, follow the platform guides in the
[main README](../README.md#documentation). For changes to the packaging code,
see [Contributing](../CONTRIBUTING.md).

## Runtime layout

Use a privileged FreeBSD VNET builder jail, a separate serving jail, and one
persistent amd64 Linux VM under bhyve/vm-bhyve. The outer host manages their
lifecycle, networking, kernel modules, and storage. All packaging work happens
inside the builder and disposable containers on the VM.

Merge [builder-jail.conf](builder-jail.conf) into the builder's jail-manager
configuration. It needs functioning VNET loopback, outbound networking, child
jails, and the listed mount permissions. Load nullfs/tmpfs on the outer host if
needed. Poudriere uses directory-backed storage (`NO_ZFS=yes`), so the builder
needs no ZFS pool delegation. Validate nested jail creation and teardown on the
selected kernel before scheduling. Stop child jails before stopping the builder.

Mount one public directory read/write at `/srv/epithet-pkg` in the builder and
read-only at `/srv/pkg` in the serving jail. Keep keys, source caches, logs, and
private workspaces out of that mount. Configure Caddy in the serving jail using
[Caddyfile](Caddyfile), with `PACKAGE_HOST` supplied privately in its service
environment. DNS, TLS, network addresses and port mappings are deployment inputs.

## Builder installation

Inside the builder, install Poudriere, Git, Go, Python 3.11+, GnuPG, and SSH.
Use a Go version satisfying the source's go.mod. Python needs no third-party
modules. Install a reviewed snapshot containing `bin`, `scripts`, `tools`, `arch`,
`freebsd`, `macos`, and `tests` under `/usr/local/libexec/epithet-packaging`.
Preserve executable bits and make the snapshot root-owned and not group/world
writable. Install subsequent snapshots together while release jobs are stopped.
The installed recipes and configured source repository are trusted: source code
executes during builds and tests. Do not automatically update executable
packaging code from Git. Source tags are fetched without force, and the selected
tag must match the requested source commit.

Copy [epithet-packaging.conf.sample](epithet-packaging.conf.sample) to
`/usr/local/etc/epithet-packaging.conf`, owned by root, mode 0600. It is trusted
shell configuration shared by all scripts. Fill in the source Git URL, public
HTTPS URL, homepage, SSH target, key fingerprint, and tap URL. Use dedicated
absolute paths. `EPITHET_PACKAGING_CONFIG` can select another config for a manual
invocation. No credentials or deployment values belong in the repository.

Install [poudriere.conf](../freebsd/ops/poudriere.conf) as
`/usr/local/etc/poudriere.d/poudriere.conf`. Its `DISTFILES_CACHE` must match the
packaging config. Create a Poudriere amd64 jail and ports tree matching the
configured names, ABI, package path, and desired FreeBSD release. For the sample:

```sh
poudriere jail -c -j 151amd64 -v 15.1-RELEASE -a amd64
poudriere ports -c -p epithet -m git+https
```

Choose a release supported by the actual builder/kernel and adjust the sample
names together. `PORT_DIR` must be a dedicated Epithet port inside that tree.
The publisher renders it before each native build.

## Linux VM

Keep a modest Linux VM running; there is no per-release VM creation or boot
step. Install Docker, SSH, Python 3.11+, and tar. Give a dedicated builder login
Docker access (which grants control of this dedicated VM). Install the reviewed
`scripts/arch-worker.sh` as `/usr/local/libexec/epithet-arch-worker`, executable
and owned by the VM administrator. Set up SSH from the FreeBSD builder, pin the
VM's host key in known_hosts, and set `ARCH_SSH_TARGET` to that SSH alias.

The SSH request streams a source/recipe bundle to the worker. It starts a fresh
`archlinux:base` container, installs build tools, runs Go and pacman tests, and
returns an artifact archive. Logs use stderr; stdout carries only artifacts.
The worker removes the container and workspace when done. It receives no
production package-signing key or tap credential. Tests generate disposable
signing keys inside the container. `ARCH_IMAGE` can use an operator-pinned image
reference; the build updates Arch's package set with pacman.

The VM is persistent infrastructure; maintain its OS/Docker normally. The scripts
do not administer bhyve or the VM from the builder jail.

## Signing and tap credentials

Preserve existing signing keys and complete public trees during migration. A new
installation needs a dedicated RSA pkg signing key and an OpenPGP signing key in
`ARCH_GNUPG_HOME`, both usable unattended. Neither is an Epithet SSH CA key.
Record the full OpenPGP fingerprint in `ARCH_KEY_FINGERPRINT`; export only its
public key as `$PUBLIC_ROOT/keys/epithet-arch.asc`. FreeBSD publication exports
`keys/epithet.pub`. Keep public files readable by the serving jail and private keys
restricted to the builder. Distribute reviewed fingerprints to clients separately.

Configure Git author identity and noninteractive push credentials for the
existing `TAP_BRANCH` at `TAP_URL`. `TAP_CHECKOUT` is dedicated to this publisher.
Disable the previous GoReleaser Homebrew writer at cutover. Package builds and
the tap need no GitHub APIs: ordinary Git transport is sufficient.

## First release

After review and provisioning, select a new stable source tag and its full
commit, then observe one release inside the builder:

```sh
/usr/local/libexec/epithet-packaging/bin/epithet-release release vX.Y.Z FULL_SOURCE_COMMIT
/usr/local/libexec/epithet-packaging/bin/epithet-release status
```

Verify all three target logs, the real pacman tests, native Poudriere/package
checks, the formula URLs/hashes, and HTTPS installs from clean clients. The
FreeBSD first-run upgrade check requires an existing published package. macOS
installation/service testing is deliberately manual in v1. Test Arch cloud-init
with the [package installation example](../arch/README.md#cloud-init) before
depending on unattended boots.

## Release commands and scheduling

The `release` command above starts work immediately. The `status` command prints
the published version for each target. Each platform publishes independently;
a release returns nonzero if any target fails, even if the others succeed.

An external CI or event handler can invoke that same command with the exact tag
and commit; no inbound handler is implemented here. To discover the newest stable `vX.Y.Z` source tag,
run:

```sh
/usr/local/libexec/epithet-packaging/bin/epithet-release poll
```

Polling retries incomplete targets and skips published versions. Optionally
install [crontab](crontab) in the builder's system crontab for a one-minute
source-tag fallback. Overlapping runs fail at the lock without starting a
second build. No GitHub workflow schedule is
involved. Enable the schedule only after the observed run succeeds.

## Logs and retries

Create `/var/log/epithet-packaging.log` owned by root with mode 0640 and install
[newsyslog.conf](newsyslog.conf). It captures coordinator progress/errors. Detailed
logs are under `$WORK_ROOT/vX.Y.Z/logs/`, with verified results alongside that
directory. A retry replaces that target's log. Connect failures to the
installation's existing monitoring. There is no notification service here.

Rerun the same `release` command or let the next poll retry. Each workspace
freezes the source commit and installed recipe digest. Artifacts carry hashes
and a test receipt; a retry verifies completed artifacts before reusing them.
Arch and macOS do not rebuild merely because publication failed.

A changed recipe cannot silently rebuild the same frozen release. Use a new
source version for a packaging correction. An entirely unpublished failed
workspace may be removed explicitly before retrying with revised recipes. Do
not remove a workspace after any target has published it.

Packages use Arch `pkgrel=1` and FreeBSD `PORTREVISION=0`. Package-only revision
selection is not implemented. Additional architectures, AUR, Debian/Ubuntu, and
RPM publication are also outside the current implementation.

## Retention and rollback

Arch retains package filenames and metadata generations. A single pointer changes
its active database and signatures; HTTP requests straddling a promotion can
observe a mismatched pair, which pacman rejects until a refresh. macOS archives
are retained before the tap push, allowing safe retry. No target downgrades
implicitly, and no automatic artifact/workspace pruning is configured.

Pause the schedule before rollback. FreeBSD retains its explicit rollback
command; Arch can select a retained `generations/vX.Y.Z` by atomically replacing
`current` with a relative symlink. Homebrew rollback is an explicit tap change.
Keep old blobs: clients may still reference them. None of these metadata changes
forces installed clients to downgrade. Resume scheduling only when its newest
stable tag is the version intended for publication.
