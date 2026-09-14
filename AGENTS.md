# Repository guidelines

Use Jujutsu (`jj`) for history and Conventional Commits for descriptions. Use
YATL for substantial plans and deferred work. Run `make test` before completing
changes. Native package tests additionally require their intended OS/runtime.

Keep deployment hostnames, addresses, signing material, and client trust details
out of source control. Source/project and documentation URLs are public inputs.
The intended runtime is a privileged FreeBSD builder jail plus a separate serving
jail with a read-only public mount. Do not provision, start services, or publish
artifacts as part of a code-only change.

Prefer one publication path for automatic and explicit FreeBSD releases. Treat
downloaded manifests and artifacts as data; keep executable packaging machinery
operator-installed. Preserve immutable package versions and disabled-by-default
service behavior. Do not add platforms or operational modes beyond agreed scope.
