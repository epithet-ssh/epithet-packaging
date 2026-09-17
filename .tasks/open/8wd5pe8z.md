---
yatl_version: 1
title: Publish signed Arch packages and automate Arch and FreeBSD releases
id: 8wd5pe8z
created: 2026-09-14T02:42:04.381801Z
updated: 2026-09-17T18:18:08.927658Z
author: Brian McCallister
priority: high
tags:
- packaging
- arch
- freebsd
- release
---

# Package publication and deployment

Published to epithet-ssh/epithet-packaging after user review and push approval.
Deployment is now authorized and underway. The release coordinator now
runs in a FreeBSD builder jail, consuming an exact source tag/commit and vendoring
once. FreeBSD builds/tests in Poudriere, Arch builds/tests in a disposable
container on a persistent bhyve/vm-bhyve Linux VM, and macOS cross-compiles both
architectures and updates a configured Git tap without Mac packaging tests.
Targets run and publish independently. GitHub Actions is optional.

## Production validation

- The builder uses the preserved FreeBSD signing key and a writable public mount;
  the existing serving jail retains its public endpoint and read-only mount.
- Production v0.34.1 passed all three platform jobs. Previous releases remain
  retained, and the original signing key is unchanged.
- Verified fresh FreeBSD installation over HTTPS, an actual Arch cloud-init boot,
  the four-command manual Arch installation, and both Homebrew archive hashes.
- Automatic discovery uses the one-minute source-tag poll, with rotated
  coordinator logs and per-release platform logs. The explicit release command
  remains available for immediate starts; no webhook service is implemented.

The initial public push and its GitHub checks passed. Debian/RPM, AUR, package-only rebuilds,
additional architectures, and a general repository manager remain out of scope.

---
# Log: 2026-09-14T03:14:33Z Brian McCallister

Prepared the public repository locally, migrated FreeBSD packaging, added Arch CI and shared automatic publication, and documented the privileged builder/readonly serving jail layout. Source build/tests, 11 publisher tests, and local nFPM package construction passed. Native CI/jail validation and deployment remain pending; nothing pushed.

---
# Log: 2026-09-16 Brian McCallister

Replaced GitHub release/workflow gating with self-hosted parallel shell builds,
one vendored source snapshot, a persistent Linux VM with disposable containers,
and macOS archive/tap publication without Mac packaging tests. The source change
removes the old Homebrew writer. Local validation is recorded in the review;
native deployment acceptance remains open.

---
# Log: 2026-09-17 Brian McCallister

Published the reviewed repository and began deployment. The builder jail and
Linux VM use a private network with outbound NAT; the existing public serving
jail remains the package endpoint. Installation instructions now use HTTPS to
bootstrap signing-key trust, including cloud-init. Native build validation and
publication cutover are still pending.

---
# Log: 2026-09-17 native staging validation

Provisioned the private builder jail and persistent Linux VM, and installed the
reviewed scripts. A full staging release passed all three targets: native
Poudriere/source tests and signed pkg install/upgrade/uninstall checks, real Arch
pacman tests, and macOS archives with a local staging tap update. The upgrade
check preserved enrollment state and operator-edited configuration. Partial
failure left other targets successful and retryable. Production publication and
scheduling remain disabled. The source GoReleaser tap writer is removed, and a
dedicated tap deploy key is registered; production credential and mount cutover
still need access approval.

Native validation identified and fixed nested-jail mount/locked-memory settings,
the login-capable Poudriere build account, and pkg test OSVERSION detection. The
packaging unit/shell checks and GitHub checks pass.

---
# Log: 2026-09-17 production cutover

After explicit approval, copied the existing FreeBSD signing key into the builder
with root ownership and mode 0600 and configured the production public-directory
mount. Published v0.34.1 for FreeBSD, Arch, and macOS through the independent
builder pipeline. The Homebrew tap now points to the package endpoint. Native
upgrade tests preserved operator configuration and enrolled-host state; HTTPS
client checks and both real Arch cloud-init and manual installation passed.
Manual Arch instructions now use four transparent shell commands without a
remote installer script or a keyserver dependency. macOS native installation
and service tests remain deliberately manual in v1.

---
# Log: 2026-09-17T18:18:08Z Brian McCallister

Closed: Published v0.34.1 on the jailed self-hosted pipeline; verified native package tests, public HTTPS installs, real Arch cloud-init boot, manual installation commands, retained releases, and Homebrew hashes. Enabled one-minute discovery and rotated logs.
