---
yatl_version: 1
title: Add Debian binary package and signed apt repository
id: 5vr2rqzn
created: 2026-10-19T18:35:54.906284Z
updated: 2026-10-19T22:48:19.059106Z
author: Brian McCallister
priority: high
tags:
- packaging
- debian
---

Deploy a Debian amd64 binary package and signed apt repository, integrated into the existing automatic source-tag release pipeline. Preserve the Arch worker and published Arch, FreeBSD, and macOS packages. Run native Debian installation, upgrade, preservation, and trust tests, plus an Arch worker validation. Poll every minute and process pending stable vX.Y.Z tags in version order so multiple tags between polls are not skipped. Bootstrap Debian at the current source release without changing frozen existing release workspaces. Verify installation from the public HTTPS apt repository and leave automatic builds enabled.

---
# Log: 2026-10-19T18:35:54Z Brian McCallister

Created task.

---
# Log: 2026-10-19T18:36:08Z Brian McCallister

Started working.

---
# Log: 2026-10-19T18:41:32Z Brian McCallister

Started working.

---
# Log: 2026-10-19T18:41:32Z Brian McCallister

Implemented Debian amd64 nFPM package, independent Linux worker target, signed flat apt publication, release coordination/receipts, installation/operator docs, and native apt integration checks. make test passes all 24 tests. Built a static Linux amd64 Epithet executable and .deb locally with nFPM 2.48.0; inspected package payload and control metadata. Native container pipeline pins nFPM 2.47.0. Native apt tests remain unexecuted because this workstation has no Docker runtime; run on the configured Linux builder before publication. No infrastructure or public repository changed. Existing frozen release workspaces require a new source tag for the new packaging recipes.

---
# Log: 2026-10-19T20:59:18Z Brian McCallister

Native validation now passes on the existing Debian 13 amd64 packaging VM using frozen Epithet v0.42.0 source: full Go suite including real sshd integration; apt install, upgrade, purge/reinstall; enrollment and sshd-file preservation; retained old package URLs; rejection of damaged packages, damaged signed metadata, and missing trusted keys. Fixed disposable build-container setup to install openssh-server, create /run/sshd, and unlock the fixture account for certificate authentication. All 24 local packaging tests pass. Downloaded the validated .deb, manifest, and native log under ignored dist/debian-v0.42.0. Package SHA256: 1e4ebfe7f01a4094fefd5425615d0236a90eb78ce2505bb5131b6bcdee9bd8e7. Every tested recipe file matches local bytes/mode; the original test receipt additionally records unused macOS transfer sidecars. Public apt publication and production-worker installation have not been performed.

---
# Log: 2026-10-19T22:48:19Z Brian McCallister

Deployment complete: separate Debian worker installed alongside the unchanged Arch worker; existing package-signing key reused; signed apt repository bootstrapped at v0.42.0; automatic one-minute source-tag polling restored and live poll verified. Poller now processes all pending stable tags in version order and stops/retries failed releases before advancing. All 25 regression tests pass locally and in the FreeBSD builder. Concurrent native Debian and Arch builds pass; rebuilt Arch package SHA256 exactly matches the existing published package, and existing Arch/macOS artifact hashes and FreeBSD release identity remain unchanged. A clean Debian container installed 0.42.0-1 from the public HTTPS apt repository and ran the enrollment command help successfully. No test containers remain. Production recipes, config, and cron backups are retained for operator rollback.

---
# Log: 2026-10-19T22:48:19Z Brian McCallister

Closed.
