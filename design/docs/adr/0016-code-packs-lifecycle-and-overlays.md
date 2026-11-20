# ADR-0016: Code packs, lifecycle and overlays

Status: Proposed · Date: 2026-10-24

## Context

The owner wants a defined structure into which agents convert design code clauses so the harness can check them, for
ACI 318 and the Saudi code SBC 304, which is derived from ACI 318-14. A clause converted wrongly is a hidden safety
failure, and clause text is copyrighted.

## Decision

- One repository, `structural-codes`, as a uv workspace: a core framework and one package per code edition.
- Each check is a pure function with metadata, bounded inputs in canonical units, explicit applicability, cited
  constants, a full trace, and verdict outputs.
- Lifecycle: `draft`, `verified`, `approved`. Only approved checks run in production. Approval is bound to the content
  hash of the check and is lost on any change.
- SBC 304-2018 is an overlay on ACI 318-14 with explicit inherit, override, add and remove entries; inheritance is
  confirmed per check.
- Verification needs worked examples, program comparison where available, boundary and property tests, and an
  independent reviewer.
- No clause text is copied.

## Consequences

- Converting clauses is slower than writing formulas freely, by design.
- Engineering output changes are always visible (major version and changelog per affected check).

## Alternatives considered

- **Checks as data (formulas in YAML)**: clauses have conditions, tables and iterations that need real code and tests.
  Rejected.
- **One package for all codes**: overlays and separate approvals are clearer with one package per edition. Rejected.
