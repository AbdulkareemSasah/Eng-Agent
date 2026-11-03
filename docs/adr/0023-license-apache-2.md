# ADR-0023: License Apache-2.0

Status: Proposed (owner decision) · Date: 2026-10-24

## Context

The tools will be open source after their first solid release. Engineering firms and other developers should be able to
use and contribute without legal friction.

## Decision

- All repositories use the Apache License 2.0: permissive, with an explicit patent grant and a contribution clause.
- Contributions are accepted under the same license (inbound equals outbound), stated in `CONTRIBUTING.md`, with a
  Developer Certificate of Origin sign-off on commits once a package is public and accepts outside contributions.
- Third-party notices are kept in `THIRD_PARTY_NOTICES.md` per repository.

## Consequences

- Companies can adopt the tools; improvements are not forced back, which the owner accepts.

## Alternatives considered

- **MIT**: simpler, no patent grant. Acceptable alternative if the owner prefers it.
- **GPL or AGPL**: forces openness of derivatives but blocks many companies from adopting. Rejected.
