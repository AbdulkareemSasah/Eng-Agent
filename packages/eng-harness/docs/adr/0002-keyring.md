# ADR-0002: keyring as a runtime dependency of eng-harness (provider keys in the operating system's credential store)

Status: Proposed · Date: 2026-11-04 · Deciders: owner

## Context
[16](../../../../design/docs/architecture/16-security-safety-privacy.md) §3 requires provider keys to be stored in the
operating system's credential store and never in project files, templates, journals, logs, error messages or URLs. The
provider layer ([spec 0009](../specs/0009-providers.md) §4.4) needs one library that reaches Windows Credential
Manager (the owner's platform), and the macOS Keychain and the Secret Service on the other platforms the CI uses.
Process/04 §7 requires an ADR for a runtime dependency.

Measured on 2026-11-04 in a scratch uv project outside the repository (CPython 3.14.6, Linux): `keyring` 25.7.0 resolved
with the packages below; sizes are installed files from each package's `RECORD`. Licenses are as published in each
package's metadata and enforced for the whole lock by the gate's license check. The Windows resolution
(`pywin32-ctypes`, declared by `keyring` for `sys_platform == "win32"`) was not resolved in this Linux environment; its
license and wheel size are taken from its PyPI page, and the Windows CI job of the first task that adds the dependency
confirms the resolution.

Maintenance health (PyPI release history, read 2026-11-04): `keyring` has 203 releases since 2009, the latest 25.7.0 on
2025-11-16 (two to four releases a year recently); it is a long-lived, widely used library. `pywin32-ctypes` is a small,
stable package (8 releases, the latest 0.2.3 on 2024-08-14), slow-moving by design. Whether this health is acceptable is
for the owner to confirm at review.

## Decision
Add `keyring` to `packages/eng-harness`, pinned exactly in `uv.lock`, imported by one module (`providers/_credentials.py`)
behind a `CredentialStore` protocol. Use is restricted by an allow-list of concrete backends
(`keyring.backends.Windows.WinVaultKeyring`, `keyring.backends.macOS.Keyring`, `keyring.backends.SecretService.Keyring`,
`keyring.backends.kwallet.DBusKeyring`, names confirmed against the installed 25.7.0), used directly and not through the
library's chainer. The fail and null backends and any plain-text or file backend are refused. `keyrings.alt` is not
added.

| Package (resolved version) | Role | License | Installed size |
|---|---|---|---|
| `keyring` 25.7.0 | Credential store interface | MIT | 101 KiB |
| `jaraco.classes` 3.4.0, `jaraco.context` 6.1.2, `jaraco.functools` 4.6.0 | Helpers of `keyring` | MIT | 14, 18, 29 KiB |
| `more-itertools` 11.2.1 | Helper of `jaraco.classes` | MIT | 295 KiB |
| `secretstorage` 3.5.0, `jeepney` 0.9.0 (Linux only) | Secret Service access | BSD-3-Clause, MIT | 37, 137 KiB |
| `pywin32-ctypes` 0.2.3 (Windows only) | Windows Credential Manager access | BSD-3-Clause | about 30 KiB (wheel size; not installed here) |

On Linux `secretstorage` also brings `cryptography` 50.0.2 (Apache-2.0 OR BSD-3-Clause, 14648 KiB), `cffi` 2.1.1
(MIT-0, 714 KiB) and `pycparser` 3.12 (BSD-3-Clause, 256 KiB); they are Linux only and add about 15.6 MiB there.

**License outside the process/04 §7 list: owner approval requested.** `cffi` is published as MIT-0 (MIT No
Attribution), which is not named in the allowed list of process/04 §7 (MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0), so by
that rule it needs an ADR approved by the owner. MIT-0 is the MIT license without the attribution condition, so it is
no more restrictive than MIT. This ADR asks for the approval of `cffi` under MIT-0 only; the matching entry
(`distribution: cffi`, `license: MIT-0`, `adr`: this file) in `license_exceptions` of `.gate/gate.yml` is a protected path
and is made by the owner, or by the agent when the owner asks, before T1 merges. It is one named exception, not a
change of the allowed list. Every
other package in the table is on the allowed list. A headless Linux CI runner has no Secret Service, so tests use an in-memory backend double and the real stores are
"needs local test".

## Consequences
- Easier: one tested interface to the platform stores; no key handling code of our own.
- Harder: the backend a machine selects is environment-dependent; the allow-list and the direct use of one backend
  make that explicit and make an unusable store a reported condition (`status`, `credential_store`), never a silent
  fallback to a file or an environment variable.
- Scope: keys are set by `python -m eng_harness.providers set-key NAME` with a no-echo prompt; there is no key in
  `harness.toml`.

## Alternatives considered
- **Environment variables**: visible to child processes and crash dumps, and not the operating system's credential
  store that 16 §3 requires.
- **An encrypted file with a passphrase**: moves the problem to the passphrase and adds our own key-management code.
- **Direct calls to the Windows Credential Manager API through `ctypes`**: Windows-only, a security surface to write and
  review ourselves, and no store for the CI platforms.
- **`keyrings.alt` or any plain-text backend**: stores keys in files; forbidden by 16 §3.
- **A third-party secret manager command-line tool**: an extra program to install and trust on the owner's machine.

## Pre-mortem
The owner's machine selects a backend outside the allow-list (for example after an operating system update), so keys
cannot be read and every remote provider reports `credential_store`. Early warning: `status` shows "credential store
unavailable"; runs continue with rules and the engineer, so nothing stops. The allow-list is a code change reviewed with
the security lens.
