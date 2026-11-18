# ADR-0036: Collateral test edits and the session estimate

Status: Accepted (decided by the owner, 2026-11-18) · Date: 2026-11-18 · Deciders: owner

## Context

After [ADR-0035](0035-no-changed-line-limit.md), two rules still stopped tasks for a documents-only plan amendment
that added no review value. A task that changed behaviour often had to adjust one existing test outside its `files`
(gate GC008), and a task that needed one more writer session had to wait for a plan change raising `max_sessions`
(rule A22). In two days four such amendments were needed (a collateral test twice, a helper's home, one extra
session), each a full pull request cycle of review, gate and local CI. The owner asked for a cheaper, faster process.

## Decision

1. A test file (any path under `tests/`) or the package `CHANGELOG.md` outside a task's `files` may be edited when the
   task needs it. The pull request lists each such file and why under "Collateral edits". `gate-check` reports such a
   path as a notice, not GC008. A non-test source file outside `files` still needs a plan amendment.
2. `max_sessions` is an estimate, like `max_changed_lines`: exceeding it is recorded in the handoff note and is never
   a reason to stop. Rule A22 now covers only editing a non-test source file outside the task's `files`.
3. Reviewers still judge collateral test edits: a changed expectation must follow the spec, never the code.

## Consequences

- Fewer documents-only pull requests; tasks finish in one cycle more often.
- The gate code (GC008), its spec and plan, the generated `AGENTS.md` files and the build copies of these documents
  must follow this decision.
- A weakened existing test could hide in a collateral edit; the reviewer checks every collateral test edit against
  the spec, and test-first still applies to the task's own tests.

## Alternatives considered

- **Keep both rules**: each stop cost a full pull request cycle for a one-line plan change.
- **Allow any file outside the list**: would let a task drift into another task's source; source scope stays.

## Pre-mortem

If this proves wrong, the likely reason is a collateral edit that relaxed an existing test's expectation. Early
warning: a collateral edit that changes an expected value rather than a call shape or an error type.
