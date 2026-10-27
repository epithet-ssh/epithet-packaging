# Debian package

## Package installation

Debian amd64 is supported initially. The package installs `/usr/bin/epithet`
and its license, with dependencies on `openssh-client` and `ca-certificates`.
It does not enroll the host, change sshd configuration, or install/start Epithet
services. Hosts accepting SSH connections also need `openssh-server` installed.

Replace `REPOSITORY_BASE_URL` below with the operator's HTTPS base URL, after
that operator has published the Debian repository and its public signing key.
The key download trusts HTTPS for bootstrap. Apt then verifies the signed
repository metadata and package hashes. `Signed-By` limits the key to this
repository, following [Debian's third-party repository guidance](https://wiki.debian.org/DebianRepository/UseThirdParty).

```sh
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsS --proto '=https' REPOSITORY_BASE_URL/keys/epithet-debian.asc -o /tmp/epithet-debian.asc
sudo install -m 0644 /tmp/epithet-debian.asc /etc/apt/keyrings/epithet-debian.asc
rm /tmp/epithet-debian.asc
sudo tee /etc/apt/sources.list.d/epithet.sources >/dev/null <<'SOURCES'
Types: deb
URIs: REPOSITORY_BASE_URL/debian
Suites: ./
Architectures: amd64
Signed-By: /etc/apt/keyrings/epithet-debian.asc
SOURCES
sudo apt-get update
sudo apt-get install -y epithet
epithet --version
epithet host enroll --help
```

Epithet updates are included in normal apt upgrades. Enrollment is a separate
operation using your Epithet domain's enrollment instructions.

For an initial install from an operator-supplied `.deb`, run this from the
package's directory, replacing `X.Y.Z` with its version:

```sh
sudo apt-get install ./epithet_X.Y.Z-1_amd64.deb
epithet host enroll --help
```

Installing a file directly does not configure an apt repository or authenticate
it through repository signatures; obtain it from a trusted source. Configure
the repository above for subsequent updates.

## Build and publication

The release coordinator runs `scripts/debian.sh` independently of the other
platform jobs. The Linux VM's installed `epithet-debian-worker` starts a fresh
amd64 Debian container containing Go. The default image is
`golang:1.27.3-trixie`; use a reviewed image satisfying the source's `go.mod`.

The container tests and builds the frozen, vendored application source, packages
it using the pinned nFPM tool, and generates `Packages` with `dpkg-scanpackages`.
`tests/debian.sh` exercises the production publisher using a disposable key and
HTTP server: apt install, upgrade, purge, fresh install, retention of old URLs,
preservation of enrollment/sshd files, and rejection of damaged packages or
untrusted metadata. Only then does it emit the artifact receipt.

The FreeBSD publisher verifies the receipt and index, signs `Release` as
`InRelease`, retains immutable `.deb` URLs, and promotes one metadata generation.
It needs Python and GnuPG, with no Debian tools on FreeBSD. This is a
[flat apt repository](https://wiki.debian.org/DebianRepository/Format#Flat_Repository_Format),
using `Suites: ./` without a component or Debian release codename. The executable
is built with `CGO_ENABLED=0`.

See the [operations guide](../ops/README.md) for worker installation, signing-key
configuration, and release commands. Native package checks modify apt/dpkg state
and must run only in the disposable container.
