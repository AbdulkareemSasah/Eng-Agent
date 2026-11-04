# ADR-0001: Core runtime dependencies (PyYAML)

Status: Proposed · Date: 2026-11-04 · Deciders: owner (approval awaiting), reviewers

## Context
The core reads `approvals.yaml` and the verification case files, both YAML (spec 0001 section 4.8, 4.9; question Q12).
Its other runtime dependencies are `eng-contract` (workspace) and `pydantic`, already accepted for the platform. YAML is
not in the standard library. `types-PyYAML` is a development dependency only, so that `mypy --strict` types the import.

## Decision
Add PyYAML (MIT licence) as a runtime dependency of `structural-codes-core`, used through `yaml.safe_load` only, never
`yaml.load` or `unsafe_load`; duplicate keys are rejected by the loader wrapper (plan task T9). No other runtime
dependency is added.

## Consequences
Approvals and case files stay human-editable and reviewable. The gate's licence check allows MIT. Every YAML read goes
through one module, so the `safe_load` rule is testable. PDF notes remain deferred (Q6).

## Alternatives considered
- **JSON or TOML files**: TOML is in the standard library, but the specs and the owner's review flow use YAML for case files; rewriting them costs readability.
- **A hand-written parser**: error-prone, and a parser bug would sit in R1 code.

## Pre-mortem
A year on, the likely failure is a YAML construct (anchors, implicit typing such as `no` read as false) changing a case value silently. Early warning: a case-file test whose parsed value differs from its literal; mitigated by Pydantic strict models after loading.
