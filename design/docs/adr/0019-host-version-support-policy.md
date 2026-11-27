# ADR-0019: Host version support policy

Status: Proposed · Date: 2026-10-24

## Context

The owner wants the add-ins to support all versions, and currently has only the latest versions available for testing.

## Decision

- A host version is supported only when it is tested, with a live acceptance record.
- Testing starts with the latest installed versions only.
- Designs allow older versions from the start: multi-target add-ins (.NET 8 for Revit and AutoCAD 2025 and newer,
  .NET Framework 4.8 for older), late binding and capability flags for CSI, version detection at connect,
  `NOT_SUPPORTED_BY_VERSION` errors.
- Each repository keeps a `SUPPORT.md` matrix.

## Consequences

- No false promises of compatibility.
- Adding older versions later is a test-and-record task, not a redesign.

## Alternatives considered

- **Claim support for versions without testing**: produces failures in front of users. Rejected.
