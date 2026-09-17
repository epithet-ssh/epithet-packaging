# Arch package

## Package installation

Use the repository operator's HTTPS base URL. Download the signing key over
HTTPS, trusting the server's TLS certificate for the initial key installation.
Pacman then requires signatures on repository metadata and packages.

Run as root, replacing `REPOSITORY_BASE_URL` with that HTTPS URL:

```sh
set -eu
repository=REPOSITORY_BASE_URL
key=$(mktemp)
curl -fsS --proto '=https' "$repository/keys/epithet-arch.asc" -o "$key"
fingerprint=$(gpg --batch --show-keys --with-colons "$key" |
  awk -F: '$1 == "fpr" {print $10; exit}')
[ -n "$fingerprint" ]
pacman-key --init
pacman-key --add "$key"
pacman-key --lsign-key "$fingerprint"
rm -f "$key"
```

Add the following to `/etc/pacman.conf`, replacing `REPOSITORY_BASE_URL` with the
same HTTPS URL. Keep pacman's literal `$arch` variable:

```ini
[epithet]
SigLevel = Required
Server = REPOSITORY_BASE_URL/arch/$arch
```

Then run `pacman -Syu epithet`. Only x86_64 is supported initially. The package
installs the binary and license and depends on OpenSSH and CA certificates. It
does not configure sshd, enroll the host, or start services.

## cloud-init

Use an Arch image with cloud-init, curl, GnuPG, and CA certificates. Replace
`REPOSITORY_BASE_URL` in both places with the operator's HTTPS URL. The machine
fetches and trusts the signing key at boot; no key or fingerprint is embedded in
user-data. No AUR helper or build user is needed.

```yaml
#cloud-config
write_files:
  - path: /etc/pacman.d/epithet.conf
    owner: root:root
    permissions: '0644'
    content: |
      [epithet]
      SigLevel = Required
      Server = REPOSITORY_BASE_URL/arch/$arch
  - path: /root/install-epithet
    owner: root:root
    permissions: '0700'
    content: |
      #!/bin/sh
      set -eu
      repository=REPOSITORY_BASE_URL
      key=$(mktemp)
      trap 'rm -f "$key"' EXIT
      curl -fsS --proto '=https' "$repository/keys/epithet-arch.asc" -o "$key"
      fingerprint=$(gpg --batch --show-keys --with-colons "$key" |
        awk -F: '$1 == "fpr" {print $10; exit}')
      [ -n "$fingerprint" ]
      pacman-key --init
      pacman-key --add "$key"
      pacman-key --lsign-key "$fingerprint"
      include='Include = /etc/pacman.d/epithet.conf'
      grep -Fxq "$include" /etc/pacman.conf || printf '\n%s\n' "$include" >> /etc/pacman.conf
      pacman -Syu --noconfirm epithet
runcmd:
  - [/root/install-epithet]
```
