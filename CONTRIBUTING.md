# Working on packaging

Use Jujutsu (`jj`) for version control and Conventional Commits for change
descriptions. See the [overview](README.md) for the platform and runtime layout,
and the [operations guide](ops/README.md) for installing reviewed changes.

## Code layout

- `bin/epithet-release` coordinates the three platform jobs.
- `scripts/` prepares source and runs builds, the Arch worker, and tap updates.
- `tools/metadata.py` handles release identity, archives, and artifact receipts.
- `tools/publish.py` handles signing, immutable files, and metadata promotion.
- `freebsd/` contains the port, rc.d services, and Poudriere publication.
- `arch/` contains the nFPM definition; `macos/` contains the formula template.
- `ops/` contains configuration samples and service setup instructions.
- `tests/` contains publisher regression tests and Arch package checks.

## Validation

Run `make test` with Python 3.11+ and Git. It checks shell syntax, source identity,
artifact validation, publication failures, immutability, locking, and parallel
execution. The optional GitHub `check` workflow runs the same suite and has no
publication role.

Native Arch and FreeBSD checks require their intended runtime. Run the Arch
checks through the disposable container: `tests/arch.sh` modifies its package
database and keyring and must not run on a client. FreeBSD checks run through
Poudriere and the candidate repository tester. macOS installation and service
testing are manual.

Keep deployment addresses, signing material, and client trust details out of
source control. Local validation does not require publishing packages or
provisioning the deployment.
