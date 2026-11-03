# ADR-0030: Replay by step path, in-flight reconciliation, durability, one engine per run, one Job Object per server

Status: Proposed · Date: 2026-11-03 · Deciders: owner (pending); proposed by the agent identity with the engine spec

Amends [ADR-0014](0014-run-journal-and-replay.md) (Proposed), which stays in force where this ADR does not change it.

## Context

[ADR-0014](0014-run-journal-and-replay.md) decided an append-only SQLite journal and resumption by replay, to be
validated by spike S-10 before the engine is built. The [S-10 report](../../../spikes/S-10-replay/REPORT.md) confirms
the approach on Linux under process crashes (a crash matrix of 32 runs, every write applied exactly once; divergence
detected in ten variants before any call; write-step overhead p95 0.54 ms against the 20 ms target of
[11](../architecture/11-harness-engine.md) §10) and found what ADR-0014 leaves open:

- Step identity must not depend on scheduling: `ctx.parallel` children need identities from their argument position.
- Divergence is detectable only on the replayed prefix. A block changed after its first unrecorded step looks like
  its normal live part (`v_tail`), so a changed block can resume an old run unnoticed unless its version is recorded.
- "Reconciled through `reconcile_operation`" is not enough: none of the Sasaah servers has one
  ([S-12 report](../../../spikes/S-12-sasaah-tool-inventory/REPORT.md) §6), a read in flight needs no reconciliation,
  and an unclear outcome needs the engineer.
- Durability per event: WAL with `synchronous=FULL` on every commit costs little, but the safety argument needs only
  some events to be durable before the next action.
- Two engines on one run would both believe a step is theirs.
- A Job Object closes only processes assigned after creation; a plain start leaves a race in which grandchildren
  escape. With kill-on-close alone, a host program a server launches (ETABS through `csi_launch`) joins the server's
  job and would end with the engine, including an instance the engineer is editing during an engineer turn
  ([11](../architecture/11-harness-engine.md) §6 item 10 forbids ending an instance the engine did not decide to close).

The Windows CI job of B-006 has run the Job Object cases of `windows_check.py` (kill on close at engine exit and on
kill, nested jobs, suspended start with no escape, late assignment escaping as documented); the report update is
queued (B-067). The breakaway case below was not part of it.

## Decision

1. **Step identity by path.** Each ctx call takes the next index in its scope; a child block at path `p`, child `i`
   of `ctx.parallel` at `p`, and iteration `i` of `ctx.attempts` at `p` open the scope `p/i` (child block: `p`).
   Identity depends on call order and argument position only. Two overlapping steps in one scope outside
   `ctx.parallel` are a block rule violation. `op_id` is derived from run id, step path and attempt (11 §3); the
   attempt increases only after a reconciled `not_applied` or an allowed retry.
2. **Run header.** `run_started` records the workflow, the root block's name, version and code hash, and the input
   hash; each child-block step records its child's name, version and code hash. At resume a changed name, version or
   input is `ReplayDivergence`; a changed code hash with the same version is a recorded warning. Any change to a block
   that has open runs requires a new version; the package enforces it with a committed lock file of block versions
   and hashes checked in CI.
3. **`ReplayDivergence` is a stop, not an end.** It is raised before any live call, journaled as `run_escalated`, and
   leaves the journal otherwise unchanged, so the right block still resumes the run. A recorded step that the block no
   longer reaches is a divergence too.
4. **In-flight steps.** A step with a start and no result is in flight. A write in flight is reconciled before
   anything else on its host, with its `op_id` (`reconcile_operation`, or by reading model state on servers without
   it): `applied` records `step_reconciled` and returns the result; `not_applied` records `step_reconciled` and runs
   the step again as the next attempt with a new `op_id`; `partial`, an unclear outcome, a missing reconciler, or an
   exception, `TIMEOUT_UNKNOWN_OUTCOME` or `HOST_WEDGED` inside a write stops the run with `NEEDS_RECONCILIATION` for
   the engineer. A write is never run again until its outcome is known. A read, calc or non-engineer decision in
   flight is run again and journaled as `step_rerun`. The event list of 11 §5 gains `step_reconciled`,
   `step_rerun` and `host_started` (decision 8). At resume, reconciliation runs only after the server check
   (11 §6 item 8), the host lease (item 10) and a units read on every model the run addressed (item 9, always at a
   resume, because the server is a new process); a failure of any of them stops the run and leaves the write in
   flight. A write in flight on a model the host no longer has loaded (a host crash) is never reconciled against the
   empty or new instance: the host-state check treats the missing model as a mismatch and offers `restore` (the write
   runs again as a new attempt after the restored save, units read first) or `abandon`.
5. **Durability.** WAL mode. `synchronous=FULL` for `run_started`, `run_completed`, `run_failed`, the `step_started`
   of a write, `step_reconciled`, `approval_requested`, `approval_resolved`, `input_provided`, `model_saved`,
   `host_started` and `signed_off`; `NORMAL` for the rest. A lost `NORMAL` event after a power failure is repaired by reconciliation or a
   rerun. Large values go to the result store and are referenced from the journal.
6. **One engine per run.** The engine holds an exclusive OS file lock on the run folder while it works on a run; the
   operating system releases it when the process ends. The engine is the journal's only writer; answers from the
   approval page reach it through its ports.
7. **One Job Object per server.** The engine creates each server process suspended (`CreateProcessW`, keeping the
   process and thread handles), assigns it to a job of its own with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, then resumes
   it; only the engine holds the job handle. Engine exit or crash ends every server; restarting one server terminates
   its job only. Adapters address a server as its whole job, never as one process id.
8. **Host programs stay outside the server jobs.** The jobs also set `JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK`, so a host
   program a server launches is not killed with the server or the engine. The engine journals every host instance a run
   started (process id and start time) as a `host_started` event and closes only those, read from the journal, when
   the run completes or fails (never at a pause), by an explicit decision (11 §6 item 10). Trade-off:
   silent breakaway also lets helper processes of a server outlive it; the engine tracks what it started and the server
   spec lists the helpers to check. `JOB_OBJECT_LIMIT_BREAKAWAY_OK`, which keeps helpers inside the job, needs the
   server to pass `CREATE_BREAKAWAY_FROM_JOB` when it starts a host program; it becomes the target once Sasaah does so.

The engine is specified in [eng-harness spec 0001](../../../packages/eng-harness/docs/specs/0001-engine.md);
decisions 7 and 8 in the server and adapter spec (eng-harness spec 0002).

## Consequences

- When accepted: [11](../architecture/11-harness-engine.md) §3 (scopes; `ctx.tool` arguments as a mapping),
  §5 (events, identity, in-flight rule, durability, run lock, divergence) and §9 (Job Objects, breakaway), and
  [02](../architecture/02-system-overview.md) §3 (one job per server) are updated, and ADR-0014's status becomes
  "Proposed; amended by ADR-0030" (or both are accepted together).
- Correctness after a change to a block rests on versioning discipline, which the lock-file check makes mechanical.
- Reconciliation by reading model state is the weakest part: it needs a live test on each Sasaah server.
- The breakaway case has no Windows result yet: `windows_check.py` gains it (a child that starts a grandchild under
  `SILENT_BREAKAWAY_OK`, asserting the grandchild survives job close), before this ADR is accepted.
- Power loss is not tested; decision 5 rests on SQLite's WAL guarantees and the reasoning in the S-10 report. The fsync
  cost on the owner's workstation is measured during local testing.

## Alternatives considered

- **Step identity by a counter over completion order**: identities would change between runs of a parallel group.
  Rejected (S-10 "parallel determinism").
- **Record the code hash only, no version**: any refactor would stop every open run. Rejected; the hash warns, the
  version stops.
- **Treat divergence as a terminal failure**: a fixed block could never finish the run. Rejected.
- **Re-run writes in flight on servers that accept `op_id`**: the Sasaah servers do not deduplicate (ADR-0024).
  Rejected for v1.
- **`synchronous=FULL` for every event**: safe and affordable on the spike's disk (write step p95 0.66 ms against
  0.54 ms for the mixed policy), but its cost on the owner's disk is unknown; kept as the fallback if the Windows
  measurement shows the mixed policy gains nothing.
- **One shared job with the engine assigned to it first**: no race, but restarting one server cannot end only its
  processes. Rejected.
- **Kill-on-close without breakaway**: host programs would die with the engine, losing the engineer's unsaved work.
  Rejected.

## Pre-mortem

If this is wrong a year from now, the likely cause is reconciliation by model reads deciding `applied` or
`not_applied` wrongly for a Sasaah tool, so a write is lost or applied twice. Early warning: engineer resolutions of
`NEEDS_RECONCILIATION` in more than one run in ten, or a difference report after a resumed run that shows a change the
change set did not contain. A second risk is helper processes left behind by silent breakaway holding a host or a
pipe; early warning: a server restart that fails because a port or a file is still held.
