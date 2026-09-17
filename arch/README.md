# Arch package

## Package installation

Use the repository operator's HTTPS base URL. Download the signing key over
HTTPS, trusting the server's TLS certificate for the initial key installation.
Pacman then requires signatures on repository metadata and packages.

On an installed Arch system, replace `REPOSITORY_BASE_URL` with the operator's
HTTPS URL and `SIGNING_KEY_FINGERPRINT` with its full signing-key fingerprint.
Run these four commands once to import and trust the key, add the repository,
and install Epithet:

```sh
curl -fsS --proto '=https' REPOSITORY_BASE_URL/keys/epithet-arch.asc | sudo pacman-key --add -
sudo pacman-key --lsign-key SIGNING_KEY_FINGERPRINT
printf '\n[epithet]\nSigLevel = Required\nServer = REPOSITORY_BASE_URL/arch/$arch\n' | sudo tee -a /etc/pacman.conf
sudo pacman -Syu epithet
```

Keep the literal `$arch` in the repository URL. Only x86_64 is supported
initially. The package installs the binary and license and depends on OpenSSH
and CA certificates. It does not configure sshd, enroll the host, or start
services. Subsequent system updates include Epithet automatically.

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
