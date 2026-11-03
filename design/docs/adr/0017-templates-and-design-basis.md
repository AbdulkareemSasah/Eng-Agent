# ADR-0017: Templates and a design basis with per-field sources

Status: Proposed · Date: 2026-10-24

## Context

The agent must never assume an input, and the owner wants to be asked each run. Asking everything every time is slow.
The owner proposed templates that bundle sections, code, combinations, materials and more.

## Decision

- Templates are versioned YAML data files (no code) validated by schema, with inheritance.
- Each run builds a design basis: template values, engineer overrides and per-run answers, every field with its source
  and confirmation. The basis is stored as a result, so it is referenced like any other data.
- A run does not start until every required field is present and confirmed.

## Consequences

- Runs start quickly with a full, explicit basis.
- Template content becomes reviewed project knowledge, shareable and open-sourceable.

## Alternatives considered

- **Read everything from the host model**: models are often incomplete or inconsistent. Model values can be a source
  (`model:<ref>`) but are confirmed like others.
- **Defaults in code**: hidden assumptions. Rejected.
