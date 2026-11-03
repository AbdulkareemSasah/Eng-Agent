# ADR-0014: Append-only run journal; resumption by replay

Status: Proposed · Date: 2026-10-24

## Context

Analyses can take long, host programs freeze, machines restart. A run must never be lost, and resuming must never repeat
a write or skip a check. The UI and the audit need the same truth about what happened.

## Decision

- Each run has an append-only SQLite journal of typed events in the workspace.
- Resumption re-executes the block from the start; recorded steps return their recorded results; live execution starts
  at the first unrecorded step. A difference between replayed calls and the journal stops the run with
  `ReplayDivergence`.
- In-flight writes are reconciled through `reconcile_operation` before continuing.
- Before live execution resumes, the engine compares each written model's identity, revision and fingerprint with the
  last `model_saved` event; a mismatch stops the run with the option to restore the last saved working copy. Working
  copies are saved after every write step.
- Servers run in a Job Object that terminates them with the engine, so no orphan keeps a host locked.
- The UI, reports and audits read the journal.

## Consequences

- Blocks must be deterministic (ADR-0011 rules), enforced by lint and tests.
- No external workflow service is needed on a single workstation.
- The approach is validated in spike S-10 before the engine is built.

## Alternatives considered

- **Checkpointing block state**: Python coroutines cannot be serialized safely. Rejected.
- **An external durable-execution service**: strong, but a heavy dependency for one workstation. Rejected for now; can
  be revisited by ADR for multi-user deployments.
