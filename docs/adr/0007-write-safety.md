# ADR-0007: Write safety

Status: Proposed; amended by ADR-0024 (a target for the Sasaah servers; the harness covers the gap meanwhile) · Date: 2026-10-24

## Context

Spikes in the earlier project showed that timeouts were reported as plain failures while the write could still be
applied later, that there was no idempotency key, and that nothing re-read the model after a write. CSI programs have no
transactions, so a batch that times out can be partly applied; a hung COM call blocks the only worker thread; a killed
server loses anything held in memory. In a structural model, a duplicated or half-applied edit is a safety problem.

## Decision

Every write tool in every server:

1. supports `dry_run`, returning the exact change set without changing the model;
2. requires an `op_id` idempotency key; repeats return the first result; the same key with different inputs is
   `CONFLICT`;
3. writes a **write-ahead op ledger** entry (intent and planned objects) before calling the host and the outcome after,
   persisted in the workspace, so idempotency and reconciliation survive restarts;
4. names created objects deterministically from `op_id` and item index, so partial application is detectable;
5. returns a change set with host ids and the new `model_revision`, and marks the model dirty until `check_model` runs;
6. requires `confirm: true` for destructive operations;
7. reports write timeouts as `TIMEOUT_UNKNOWN_OUTCOME`; `reconcile_operation(op_id)` answers `applied`, `partial`
   (with the missing items) or `not_applied`, with evidence;
8. enters a **wedged** state (`HOST_WEDGED`) while a timed-out call is still inside the host, and refuses new calls
   until it returns.

Servers hold a per-instance lock file with their process id; a live holder means `HOST_LOCKED`. The harness generates
`op_id`s deterministically per run, step and attempt, runs servers in a Job Object, and enforces check-after-write.

## Consequences

- Retries, crashes and resumption are safe, including partial batches on hosts without transactions.
- Servers must implement the ledger, naming and reconciliation per host; this is real work, tested with the fake host.

## Alternatives considered

- **Retry on timeout**: can apply a write twice. Rejected.
- **Re-read the whole model after every write**: too slow on large models. Replaced by change sets, fingerprints and
  `check_model`.
- **In-memory op tracking**: lost on restart. Rejected.
