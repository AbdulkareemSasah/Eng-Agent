# ADR-0005: license exceptions for regex and cffi, transitive dependencies of the provider layer

Status: Proposed · Date: 2026-11-11 · Deciders: owner

## Context
Plan 0009 T1 adds `pydantic-ai-slim[openai]`, `keyring` and `httpx2` (ADR-0001, ADR-0002, ADR-0003). Process/04 §7
allows MIT, BSD, Apache-2.0, ISC, PSF and MPL-2.0. Two packages in that lock are outside the list, and the gate's
license step rejects them unless `.gate/gate.yml` names an exception and this ADR (amendment B-440):

- `regex`, brought in by `tiktoken` through the `openai` extra (ADR-0001). Metadata `License-Expression` is
  `Apache-2.0 AND CNRI-Python`. CNRI-Python is not on the allowed list. The lock for this task resolves `regex`
  2026.11.9.
- `cffi`, brought in on Linux by `cryptography` through `secretstorage` and `keyring` (ADR-0002). Metadata
  `License-Expression` is `MIT-0` (MIT No Attribution), which is not named in the allowed list. The lock resolves
  `cffi` 2.1.1. The requirement is Linux-only.

Neither package is copied into the repository. Accepting this ADR is the owner's approval of those two expressions
only. It does not change the allowed list.

## Decision
Record the two exceptions the gate checks. Each entry's `license` is the distribution's `License-Expression`, and
`adr` is this file:

- `distribution: cffi`, `license: MIT-0`
- `distribution: regex`, `license: Apache-2.0 AND CNRI-Python`

## Consequences
- The provider lock can pass the license step while the owner has not yet accepted ADR-0001 and ADR-0002.
- A later lock that publishes a different expression for either package fails the step until this ADR and the entry
  are updated. Declining this ADR means the `openai` extra and, on Linux, `keyring` cannot be used as published
  (ADR-0001, ADR-0002).

## Alternatives considered
- **Treat MIT-0 as MIT and CNRI-Python as an allowed permissive license in the gate**: changes the allowed list for
  every package, which process/04 §7 reserves to the owner as a process change.
- **Drop the `openai` extra or `keyring`**: contradicts ADR-0001 and ADR-0002, which already ask for these exceptions.

## Pre-mortem
A release of `regex` or `cffi` changes its SPDX expression, the exception no longer matches, and the license step
fails closed. Early warning: the license step names the new expression on the pull request that upgrades the lock.
