# Epithet packaging

Package definitions, build scripts, and repository publication for
[Epithet](https://github.com/epithet-ssh/epithet). This repository owns the
FreeBSD port, Arch package, and Homebrew formula. Application source remains in
the Epithet repository.

| Platform | Package | Validation |
| --- | --- | --- |
| FreeBSD amd64 | Native pkg with disabled-by-default rc.d services | Go tests and native package checks |
| Arch x86_64 | Binary package for a signed pacman repository | Go tests and pacman installation, upgrade, and signature checks |
| macOS amd64 and arm64 | Binary archives and Homebrew formula | Cross-compilation; installation and service tests are manual |

## How the pieces fit together

A FreeBSD builder jail prepares one source snapshot and runs the three platform
jobs independently. FreeBSD builds with Poudriere. Arch builds in a disposable
container on a persistent Linux VM. macOS binaries are cross-compiled in the
builder jail.

The builder signs and publishes packages; a separate serving jail exposes the
public files over HTTPS through a read-only mount. The Homebrew formula points
to the published macOS archives. GitHub Actions is optional: package publication
does not depend on its release artifacts or workflow results.

## Documentation

Each platform uses the same package for Epithet clients and servers. Running an
Epithet server requires configuration and service startup after installation.

- [Arch package installation](arch/README.md#package-installation): repository
  trust, pacman setup, and a cloud-init example.
- [FreeBSD package installation](freebsd/README.md#package-installation):
  repository trust and pkg setup, followed by port and service details.
- [macOS package installation](macos/README.md#package-installation): Homebrew
  setup, followed by formula, archive, and tap details.
- [Package repository operations](ops/README.md): provision the build and serving
  infrastructure, publish releases, inspect failures, and roll back.
- [Contributing](CONTRIBUTING.md): code layout and local validation.
