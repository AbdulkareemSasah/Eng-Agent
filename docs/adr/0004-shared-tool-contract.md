# ADR-0004: One shared tool contract package, `eng-contract`

Status: Proposed; amended by ADR-0024 (the contract applies at the harness boundary) · Date: 2026-10-24

## Context

Independent servers, code packs and the harness must agree on result envelopes, references, units, errors and
verdicts. If each repository implements them, they drift; drift in units or references produces wrong numbers.

## Decision

- The contract is specified in [04-tool-contract](../architecture/04-tool-contract.md) and implemented once in the
  Python package `eng-contract`: Pydantic models, the result store, reference resolution, unit conversion, error codes,
  verdict and issue types, and helpers for the standard tools.
- It also defines the **neutral kinds** (`geom.*`, `model.*`, `forces.*`, `basis.*`, `verdicts.*`, `issues.*`) for
  every result that travels between packages. Servers accept only neutral kinds and their own; translation between
  them is a harness calc. No package depends on another server's schemas.
- Every Python package depends on it. No package re-implements any part of it.
- `eng-contract` depends only on the Python standard library and Pydantic.
- The contract has a major version in every envelope and record.

## Consequences

- One place to review for correctness of the most dangerous code (units, references).
- `eng-contract` becomes a critical dependency: it has the strictest review rules and the highest test coverage
  requirement ([process/05](../../process/05-testing-and-verification.md)).

## Alternatives considered

- **Specification only, each repository implements it**: invites drift. Rejected.
- **JSON Schema plus generated code**: useful for non-Python consumers later; the Pydantic models already emit JSON
  Schema, which is published with each release.
