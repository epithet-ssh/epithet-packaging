# Arch package

## Package installation

Obtain the public repository URL, `epithet-arch.asc`, and its **full fingerprint**
from the operator. Verify the fingerprint through the operator's trusted
documentation before locally trusting the key; downloading a key from the
repository alone does not establish its identity.

```sh
gpg --show-keys --with-fingerprint epithet-arch.asc
pacman-key --init
pacman-key --add epithet-arch.asc
pacman-key --lsign-key "$EXPECTED_FINGERPRINT"
```

Add the following to `/etc/pacman.conf`, replacing `REPOSITORY_BASE_URL` with the
operator's HTTPS base URL. Keep pacman's literal `$arch` variable:

```ini
[epithet]
SigLevel = Required
Server = REPOSITORY_BASE_URL/arch/$arch
```

Then run `pacman -Syu epithet`. Only x86_64 is supported initially. The package
installs the binary and license and depends on OpenSSH and CA certificates. It
does not configure sshd, enroll the host, or start services.

## cloud-init

Use an Arch image that already supports cloud-init. Replace all three marked
values before boot. Embed the reviewed public key so boot does not trust a key
solely because it was downloaded from the package server. No AUR helper or build
user is needed.

```yaml
#cloud-config
write_files:
  - path: /root/epithet-arch.asc
    owner: root:root
    permissions: '0600'
    content: |
      REPLACE_WITH_REVIEWED_ARMORED_PUBLIC_KEY
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
      expected=REPLACE_WITH_FULL_FINGERPRINT
      actual=$(gpg --batch --show-keys --with-colons /root/epithet-arch.asc |
        awk -F: '$1 == "fpr" {print $10; exit}')
      [ "$actual" = "$expected" ]
      pacman-key --init
      pacman-key --add /root/epithet-arch.asc
      pacman-key --lsign-key "$expected"
      include='Include = /etc/pacman.d/epithet.conf'
      grep -Fxq "$include" /etc/pacman.conf || printf '\n%s\n' "$include" >> /etc/pacman.conf
      pacman -Syu --noconfirm epithet
runcmd:
  - [/root/install-epithet]
```
