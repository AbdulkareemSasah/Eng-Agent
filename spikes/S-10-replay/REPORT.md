# Spike report S-10: can async Python blocks resume by replay from an append-only journal, and can Job Objects stop child servers with the engine?

Work item: B-006 · Time box: at most two days ([19](../../design/docs/architecture/19-roadmap-and-spikes.md) §2) · Date: 2026-11-03 · Author: agent (Claude)
Environment: Python 3.14.6, Linux 6.18 (ext4, 4 CPUs, SQLite 3.53.1), no host program. Windows: GitHub Actions `windows-latest` (Windows Server 2025, Python 3.14.10, SQLite 3.50.4, 2 CPUs), CI run [41729982994](https://github.com/AbdulkareemSasah/Eng-Agent/actions/runs/41729982994) on 2026-11-03 (see "Windows results").

## Question

From [19](../../design/docs/architecture/19-roadmap-and-spikes.md) §2 and [ADR-0014](../../design/docs/adr/0014-run-journal-and-replay.md):

1. Can a block written as an async Python function be resumed after a crash or a pause by running it again from the
   start, with recorded steps returning their recorded results, with a step in flight at the crash never silently run
   again, a changed block detected, and concurrent steps given a stable identity?
2. Is the engine's own cost per step under 20 ms at p95 ([11](../../design/docs/architecture/11-harness-engine.md) §10)
   with the journal on disk?
3. Can a Windows Job Object make child servers (and their children) end with the engine, and how must a server be
   started so that no process escapes the job?

## Method

All code is throwaway, in `spikes/S-10-replay/`, standard library only.

| File | Role |
|---|---|
| `engine.py` | The minimal engine: `Ctx` with `tool`, `approve`, `parallel`, `block`; SQLite journal; replay index; run lock; resolution functions for the approval page and for in-flight writes |
| `scenarios.py`, `worker.py` | A fake host (a ledger of calls that records every `op_id`), the test blocks, and one engine process that can be told to crash at a named point |
| `check.py` | PEP 723 script, `uv run --script check.py`: ten end-to-end scenarios on Linux, exit code non-zero on any failure |
| `bench.py` | Per-step overhead, fsync cost and replay speed |
| `jobobject.py` | ctypes wrapper: `CreateJobObjectW`, `SetInformationJobObject` with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `AssignProcessToJobObject`, plus `popen_in_job` (start suspended, assign, resume) |
| `windows_check.py` | PEP 723 script for Windows only; prints SKIPPED and exits 0 elsewhere (a SKIPPED run is not a Windows result) |

**Engine design.** A block is `async def block(ctx, inp)`. Every step gets a path from its position in its scope
(`0`, `1`, `2/0`, `2/1`, ...). Journal events are those of 11 §5 plus `step_reconciled` and `step_rerun`. The journal is
one table with `UPDATE` and `DELETE` blocked by triggers. A step is journaled as `step_started` (kind, name, arguments,
argument hash, effect `read` or `write`, attempt, `op_id`) before the call and `step_completed` or `step_failed` after
it. `op_id` is a hash of run id, step path and attempt (11 §3). On every start the engine takes an OS file lock on the
run directory (released by the OS when the process dies), rebuilds an index of the journal, then calls the block.
`EngineStop` (pause, divergence, reconciliation) derives from `BaseException`, so a block's `except Exception` cannot
swallow it.

**Crash simulation.** A worker process runs the block and calls `os._exit` at a chosen path and point
(`before_started`, `after_started`, `after_effect`, `after_completed`), which leaves the state a kill leaves. One
scenario also kills a process from outside while a write is running. These are process crashes. **Power loss and disk
failure are not simulated.**

**Overhead.** `bench.py` runs N steps through `await ctx.tool(...)` with a tool that returns a small dict at once and
times itself. Overhead of a step = time around `ctx.tool` minus the tool's own time. Clock `time.perf_counter_ns`,
percentiles by nearest rank, journal a real SQLite file in a temporary directory on ext4, first 5% of steps discarded
as warm-up, 1000 steps per row, 256-byte result unless stated. Command: `uv run --script bench.py --n 1000`.

## Findings

### Replay and recovery (`check.py`, Linux)

```
S-10 check: python 3.14.6 on linux
[PASS] baseline run, pause, resume (0.3 s)
       25 events; 8 tool steps; resume replayed 9 recorded steps
[PASS] crash matrix (11.4 s)
       32 crash runs (every tool step x 4 points); each: writes exactly once, same result, same step identities
[PASS] nested block, completed run (0.3 s)
       child block crashed inside, resumed; completed run returns its result without a call
[PASS] external kill, in-flight reconciliation, run lock (1.0 s)
       killed mid-step; second engine refused by the run lock; no silent re-run; resolved as applied / not applied / by reconciler
[PASS] replay divergence (1.5 s)
       10 changed blocks detected before any call; v_tail accepted (known limit); original block still resumes
[PASS] parallel determinism (0.4 s)
       completion order A ['3', '1', '4', '2', '0'] vs B ['0', '4', '3', '1', '2'], identical identities; crash inside the group reconciled 4 in-flight writes
[PASS] approval pause and resume (0.6 s)
       pause, answer from another process, resume; wrong hash / reuse / non-approval refused; rejection branch
[PASS] rules: overlap, append-only, codec (0.0 s)
       overlapping steps refused; journal append-only (UPDATE and DELETE abort); live == replayed value
[PASS] engine overhead target (0.2 s)
       mixed policy, write step: p50 0.312 ms, p95 0.639 ms (target < 20 ms); raw append+fsync p50 0.105 ms. Full table: bench.py
[PASS] job object structure layout (0.0 s)
       Win32 structure sizes match (48, 64, 144, 28 bytes); behavior on Windows: windows_check.py (pending)
RESULT: PASS
```

(Time stamps and the work-directory line are omitted; exit code 0; about 16 s wall time.)

| Finding | Evidence |
|---|---|
| Replay works: a rerun block gets recorded results for recorded steps and goes live at the first unrecorded step. Live and replayed values are identical because every live result passes through the same canonical-JSON codec before the block sees it | scenarios "baseline", "nested block", "rules ... codec" |
| Crash at any point of any tool step recovers with each write applied exactly once and the same final result | crash matrix: 8 tool steps x 4 crash points = 32 runs, all pass |
| Crash points and what recovery does. `before_started` and `after_started` with no effect: the step is run live (a write whose start is journaled is first reconciled, and the host answers "not applied"). `after_effect` (host applied, completion not journaled): the step is in flight, the host's ledger of `op_id` shows it applied, the engine records `step_reconciled` and continues without calling again. `after_completed`: plain replay | crash matrix, "external kill" scenario |
| **Reconciliation rule for a step in flight** (`step_started` without a result): a *write* is never run again until its outcome is known. The engine asks the tool's reconciler (the stand-in for `reconcile_operation`) with the recorded `op_id`; `applied` records the result and continues; `not_applied` runs the step again as attempt + 1 with a new `op_id`; no reconciler or an unclear answer stops the run with `NEEDS_RECONCILIATION` and the engineer resolves it (`resolve_in_flight`: applied with a result, or not applied). A *read* has no side effect and is run again, journaled as `step_rerun`. A write that raises an exception or times out inside the call is treated as in flight too, because the outcome is unknown | scenario "external kill, in-flight reconciliation, run lock": all three resolutions, and the host's call count is 1 for the write |
| Only one engine can work on a run: a second engine on the same run directory is refused by the file lock, so two processes cannot both think a step is theirs. The lock dies with the process, so a crash never leaves a stale lock | same scenario |
| Divergence is detected on the replayed prefix, before any tool call: a changed argument, a different tool, an inserted step, a removed step, a changed parallel size, a changed approval preview, a block that ends before the journal does (recorded steps unconsumed), a changed run input, a changed block name or a changed block version | scenario "replay divergence": 10 variants, all code 12 `REPLAY_DIVERGENCE`, host call count unchanged |
| **Known limit of divergence detection.** The check compares what the block calls with what was recorded. Code that differs only *after* the first unrecorded step (`v_tail`: same recorded prefix plus an extra step later) is indistinguishable from the block's normal live part, and is accepted. The only guard is the block version in the run header: a new version is a divergence ("same code, new version" is detected). The engine spec must therefore make the version bump mandatory for any change to a block that has runs in progress, and lint or CI should derive the version from the block's source hash | scenario "replay divergence", `v_tail` |
| Divergence does not damage the run: it is journaled as `run_escalated`, not as a terminal event, and the journal is untouched, so the right block still resumes it afterwards | same scenario, last assertions |
| `ctx.parallel`: child `i` gets scope `<path>/<i>`, so step paths depend on argument position only. Two runs of five children with opposite completion orders produce identical step identities and results; a crash inside the group reconciled all four in-flight writes. Results come back in argument order; when several children stop the run, the error raised is chosen by class and then lowest child index, never by completion order | scenario "parallel determinism" |
| Concurrency outside `ctx.parallel` is a rule violation: two overlapping steps in one scope raise `BLOCK_RULE_VIOLATION`. Without this, step identity would depend on scheduling | scenario "rules" |
| Pause and resume of an approval: `approval_requested` is journaled (durably) and the run ends `PAUSED`; the answer is written by a different process (the approval page stand-in) with no engine running; the next engine start replays and continues. The answer is bound to the hash of the preview shown, can be used once, and cannot be given to a step that is not an approval. Rejection takes the other branch | scenario "approval pause and resume" |
| A broad `except Exception` in a block does not swallow a pause or divergence, because `EngineStop` is a `BaseException` | the `footing` test block wraps its approval in `except Exception` |

### Overhead and journal settings (`bench.py --n 1000`, Linux ext4, Python 3.14.6, SQLite 3.53.1)

Engine overhead per step in ms:

| policy / step type | steps | p50 | p95 | p99 | max |
|---|---|---|---|---|---|
| full / write | 1000 | 0.297 | 0.656 | 0.872 | 1.963 |
| full / read | 1000 | 0.310 | 0.721 | 1.275 | 4.467 |
| **mixed / write** | 1000 | 0.257 | 0.535 | 0.842 | 2.195 |
| mixed / read | 1000 | 0.038 | 0.062 | 0.100 | 9.912 |
| normal / write | 1000 | 0.037 | 0.063 | 0.089 | 8.182 |
| normal / read | 1000 | 0.038 | 0.062 | 0.096 | 13.014 |
| delete_full / write (rollback journal, not WAL) | 1000 | 1.751 | 2.735 | 4.713 | 10.489 |
| delete_full / read | 1000 | 1.618 | 2.386 | 3.186 | 8.803 |
| off / write | 1000 | 0.036 | 0.055 | 0.074 | 0.201 |
| off / read | 1000 | 0.035 | 0.055 | 0.076 | 0.180 |
| mixed / write, 10 KB result | 250 | 0.325 | 0.579 | 0.852 | 4.863 |

Raw `os.write` of 200 bytes plus `os.fsync` on the same disk: p50 0.111 ms, p95 0.261 ms, p99 0.424 ms, max 0.587 ms.

Replay speed (resume of a paused run): 1,000 recorded steps in 15.2 ms (15 us per step); 10,000 in 125.8 ms (13 us per
step); about 270 bytes of journal per step.

Policies: `full` is WAL with `synchronous=FULL` for every commit. `mixed` is WAL with `synchronous=NORMAL` for ordinary
events and `FULL` for the events whose loss could make the engine act wrongly: `run_started`, `run_completed`, the
`step_started` of a write step, `step_reconciled`, `approval_requested`, `approval_resolved`. `normal` and `off` are
for comparison only. The `check.py` run measured mixed/write at p50 0.312 ms and p95 0.639 ms; the two runs differ
by run-to-run noise.

| Finding | Evidence |
|---|---|
| Engine overhead is far under the target: p95 0.54 ms (mixed, write) against 20 ms, a factor of about 37. Even `full` is 0.66 ms. The target is not at risk from the journal on this disk | table above |
| One fsync is cheap on this machine (0.11 ms p50), so the whole write-step overhead is dominated by two SQLite commits and the fsync of one of them. **This disk is a virtual disk of a cloud sandbox; an NTFS laptop SSD can be slower or faster and the number must not be carried over.** `windows_check.py` Part B prints the same table on the Windows runner | raw fsync row |
| WAL is the right mode: the rollback journal (`delete_full`) costs about seven times as much per step (p50 1.75 ms against 0.26 ms) | table above |
| Why `mixed` is safe with `NORMAL` on ordinary events (reasoning; power loss was not simulated): in WAL mode a `NORMAL` commit is not fsynced, so after a power failure the newest commits may be lost, but the file is not corrupted and earlier commits stay. A `FULL` commit also makes all earlier commits durable. So the start of a write is always on disk before the write is sent. If the `step_completed` after it was lost, replay finds the step in flight, and reconciliation (not a re-run) restores the result. A lost start of a *read* only means the read runs again | design reasoning, journal order |
| Result size has little effect (10 KB result: p95 0.58 ms) and the journal grows about 270 bytes per small step. Large results must go to files with a reference in the journal (11 §3 already says "result reference") | table and replay row |

### Job Objects (`jobobject.py`, `windows_check.py`)

**Nothing in this section has run on Windows.** On Linux, `check.py` verifies only that the ctypes structure sizes equal
the 64-bit Win32 sizes (`IO_COUNTERS` 48, `JOBOBJECT_BASIC_LIMIT_INFORMATION` 64, `JOBOBJECT_EXTENDED_LIMIT_INFORMATION`
144, `THREADENTRY32` 28 bytes), and `windows_check.py` prints `SKIPPED`. The statements below come from the Microsoft
Win32 documentation (Job Objects, Nested Jobs, AssignProcessToJobObject, Process Creation Flags) and are to be confirmed
by the post-merge Windows CI job, which runs every `spikes/*/windows_check.py`. That job ran on 2026-11-03 and passed; its
results are in "Windows results" below.

| Finding | Evidence |
|---|---|
| Mechanism: `CreateJobObjectW`, then `SetInformationJobObject` with `JobObjectExtendedLimitInformation` (class 9) and `LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x2000)`, then `AssignProcessToJobObject`. When the last handle to the job closes, which includes the owning process ending for any reason (exit, crash, termination), Windows terminates every process in the job | documentation; `windows_check.py` cases `assign_after`, `suspended`, `self_assign` (engine exit and kill from outside) assert that the child and both grandchildren are gone; case `none` is the control and asserts that without a job they survive |
| **The race.** A process becomes a member of the job at assignment. Processes it created *before* that moment are not members and are not killed. A plain `Popen` followed by `AssignProcessToJobObject` leaves a window in which the new process can start grandchildren that then escape. Case `late` makes the window two seconds long on purpose and asserts that the two grandchildren escape (documenting the rule); the loop `race_loop` counts how often a child's first act (starting a grandchild) beats the assignment, and requires zero escapes for the suspended start. The count for the plain start is printed as INFO only: with a slow Python start-up it may be zero, which would not prove safety | documentation; to be measured by `windows_check.py` |
| **Closing the race.** Three ways exist: (a) create the process suspended (`CREATE_SUSPENDED`), assign it, resume it: no instruction of the new process runs before assignment; (b) the engine assigns *itself* to the job first, and all later children inherit membership (no window, but the job is then shared by all servers and by the engine); (c) a small launcher that is itself in the job before it starts the server. (c) only moves the race: the launcher must be started suspended or be in the job already, so it needs (a) or (b) anyway | `jobobject.popen_in_job` implements (a); case `self_assign` tests (b) |
| **Nested jobs.** From Windows 8 on, a process may be in a chain of nested jobs; earlier versions allow one job per process. An engine started from a terminal, a CI runner or a scheduler that already uses a job is therefore not a problem on supported Windows versions. Case `nested` puts the engine in an outer job and each server in its own inner job: `TerminateJobObject` on one inner job ends exactly that server's tree and leaves the other, and the engine ending ends the rest | documentation; `windows_check.py` case `nested`. The check prints whether the check process is already in a job |
| Breakaway: with `JOB_OBJECT_LIMIT_BREAKAWAY_OK`, a child leaves the job only if its creator passes `CREATE_BREAKAWAY_FROM_JOB`; with `JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK`, every process a job member creates leaves the job automatically. The spike sets neither, so in the spike nothing escapes. The engine needs a choice here (see open risks): silent breakaway lets host programs survive but also lets every helper process a server starts outlive it; `BREAKAWAY_OK` keeps helpers in the job but needs the server to start host programs with the breakaway flag, which is a Sasaah change | documentation |
| A Python virtual-environment launcher (`python.exe` in `.venv\Scripts`) can start the real interpreter as a child process. In a job both stay members, but a test that tracks "the server's PID" would track the wrong process. `windows_check.py` therefore uses the base interpreter, and adapters must track the whole job rather than a PID | note in `windows_check.py` |
| Resuming a suspended process: `subprocess.Popen` does not hand back the primary thread handle, so `resume_process` enumerates threads with `CreateToolhelp32Snapshot` and resumes those of the new PID. This works for a process that has just been created, but it is more machinery than needed and it works by PID | `jobobject.py` |
| PID use (review note). `popen_in_job` opens the child by PID with `OpenProcess` to assign it, instead of using the handle `Popen` already holds. A PID can in principle be reused if a child dies in between; for a suspended child that has run no code this is not a practical risk. The engine should not depend on it: it should call `CreateProcessW` itself, keep `PROCESS_INFORMATION.hProcess` and `.hThread`, assign with the process handle and resume with the thread handle. No PID lookup is then needed | design recommendation, not tested |

### Recommendation: how the harness starts servers

**One job per server, created by the engine, with the server process created suspended, assigned to its job, then
resumed.** Each job has `KILL_ON_JOB_CLOSE` and its handle is held by the engine only (not inheritable).

- Engine exit or crash closes all handles, so every server process ends: this is the ADR-0014 requirement. Host
  programs a server starts must not end with it (open risk "Host programs inside a server's job"): they leave the job,
  and the engine closes only host instances it started, by an explicit decision, never as a side effect of a job ending
  ([11](../../design/docs/architecture/11-harness-engine.md) §6 item 10).
- Restarting one crashed server terminates its job (the server and the helper processes that stayed in it), without
  touching the other servers or any host program.
- No code of the server runs before it is in the job, so the race is closed, whatever the server does at start.
- If the engine is itself inside a job (CI, terminal, scheduler), nested jobs keep this working on Windows 8 and later.
- A launcher is not needed: it would have to be started the same way. The engine should do the creation itself with
  `CreateProcessW` (handles in hand), not through `Popen` plus a thread scan.
- Adapters must treat "the server" as the whole job (list with `JobObjectBasicProcessIdList`), not as one PID.

## Answer

1. **Replay: yes.** The approach in ADR-0014 works as specified on Linux under process crashes, with the changes in the
   next section. Proven on Linux with a fake host and process kills: every step of a mixed read/write/parallel/approval block recovers
   from a crash at four points; in-flight writes are reconciled and never silently repeated; changed blocks are
   detected, within the limit described above.
2. **Overhead: yes, by a wide margin.** p50 0.26 ms and p95 0.54 ms per write step with the journal on disk (`mixed`
   policy), against a target of 20 ms at p95, on a Linux virtual disk. On the Windows CI runner: p50 3.5 ms and p95 7.0 ms
   (see "Windows results"); a workstation disk with antivirus still needs a local run.
3. **Job Objects: yes, on the Windows CI runner.** Every case of `windows_check.py` Part A passed on `windows-latest`
   (see "Windows results"), so the recommendation above stands. The breakaway case of the open risks (host programs
   leaving a server's job) is not yet in the check and remains to be added and run.

### Windows results

From CI run [41729982994](https://github.com/AbdulkareemSasah/Eng-Agent/actions/runs/41729982994) (job `windows`, step "Windows spike checks"), `windows-latest`, Python 3.14.10:

| Case | Expected | Observed |
|---|---|---|
| The check process itself | | already inside a job (nested jobs in use) |
| `none` (no job) | children survive the engine | survive: pass |
| `assign_after`, engine exit and engine kill | children end | none alive: pass |
| `suspended`, engine exit and engine kill | children end | none alive: pass |
| `self_assign`, engine exit and engine kill | children end | none alive: pass |
| `late` assignment | grandchildren started before assignment escape | 2 escaped (2 expected): pass |
| `nested` | inner job ends its tree; the outer job ends the rest | pass |
| Suspended start, 40 immediate grandchildren | none escape | 0 of 40: pass |
| Plain `Popen` then assign, 40 grandchildren | informational | 0 of 40 (Python starts slowly, so this does not prove safety) |
| Part B: the replay scenarios of `check.py` | pass | all pass |
| Engine overhead, `mixed` policy, write step | under 20 ms at p95 | p50 3.5 ms, p95 7.0 ms; raw append plus fsync p50 2.5 ms |
| Replay of a paused run | | 1,000 steps in 31 ms; 10,000 steps in 141 ms |

Not covered: power loss during commits, the host-state check against `model_saved` (11 §5), the working-copy save after
write steps, `ctx.ask`, `ctx.decide`, `ctx.attempts`, `ctx.read`, and a real `reconcile_operation` of a Sasaah server
(needs a live test). The spike's reconciler is a ledger of `op_id` in a fake host.

## Consequences for the design

These are proposals. The hub documents and the ADR are not changed by this spike; the owner decides on the ADR status.

**ADR-0014 (Proposed).** Keep the decision. Proposed changes, to be made by a new ADR or by the owner before acceptance:

1. Replace "A difference between replayed calls and the journal stops the run with `ReplayDivergence`" with: "...stops
   the run with `ReplayDivergence` before any live call. The stop is not terminal and is journaled as `run_escalated`;
   the journal is unchanged, so restoring the block resumes the run. Differences after the first unrecorded step are not
   detectable, so the run header records the block name, block version and input hash, and any change to a block with open
   runs requires a new block version."
2. Replace "In-flight writes are reconciled through `reconcile_operation` before continuing." with: "A write step's
   `step_started` is committed durably before the call. A step that has a start and no result is in flight: a write is
   reconciled with its `op_id` (`reconcile_operation`, or by reading model state on servers without it) and is never
   run again until the outcome is known; `not_applied` runs it again as the next attempt with a new `op_id`; an unclear
   outcome, a missing reconciler, or an exception or timeout inside a write stops the run with
   `NEEDS_RECONCILIATION` for the engineer. A read in flight is run again."
3. Replace "Servers run in a Job Object that terminates them with the engine" with: "Each server runs in its own Job
   Object with kill-on-close, created suspended, assigned, then resumed, with the job handle held by the engine, so no
   orphan server keeps a host locked; host programs a server starts leave the job (the breakaway choice of the open
   risks), and the engine closes only host instances it started, by an explicit decision". Add under Consequences: "The Windows behavior is
   validated by the Windows CI job; until it has passed, this decision is not validated" and change "validated in spike
   S-10 before the engine is built" to name this report.
4. Add under Decision: "One engine works on a run at a time (an OS file lock on the run directory)."

**11 section 5 (Journal, replay and resumption).**
- Add the events `step_reconciled` (outcome, result, who decided) and `step_rerun` to the event list. Define the
  `step_started` payload: kind, name, arguments and their hash, effect (`read` or `write`), attempt, `op_id`.
- Define step identity: the path of a step is its position in its scope; `ctx.parallel` and `ctx.block` open child
  scopes by argument position or path, so identity never depends on completion order.
- Replace the in-flight sentence with the reconciliation rule in point 2 above.
- Add durability: WAL; `synchronous=FULL` for `run_started`, `run_completed`, the start of a write step, reconciliation and approval events;
  `NORMAL` for the rest. The loss of a normal event after a power failure is repaired by reconciliation.
- State that divergence is non-terminal and has the limit above.
- Add a short statement of the run lock.

**11 section 3 (context API) and the rules for block code.**
- Rule 4 (deterministic) gains: no step runs concurrently with another in the same scope except through `ctx.parallel`;
  the engine rejects overlapping steps with a block rule violation.
- `ctx.tool` already says `op_id` is deterministic from run id, step path and attempt: confirmed; attempt increases only after a reconciled `not_applied`.
- State that engine stops (pause, divergence, reconciliation) are not `Exception`s and blocks must not catch
  `BaseException` or use a bare `except`; the block lint (ADR-0011 rules) must forbid both.

**11 section 9 (server management).** Replace "inside a Windows Job Object configured to terminate its processes when the engine exits" with the
per-server, suspended-assigned-resumed rule, state that the engine creates processes itself with `CreateProcessW` and holds
process and thread handles, that adapters address a server as a job, and that restarting a server terminates its job.

**Engine spec (the document the phase 1 engine is built from) must require:**
1. Single engine per run (file lock) and the journal append-only (triggers or equivalent).
2. Path-based step identity as above; `ctx.parallel` identity independent of completion order; deterministic choice among
   several errors from a parallel group.
3. All live results pass through the journal codec (canonical JSON) before a block sees them.
4. `step_started` of a write is durable before the call; in-flight handling as above; `op_id` passed to every write.
5. Run header check (block, version, input hash) and the unconsumed-journal check at the end of the block.
6. Approval answers written by a separate process, bound to the shown hash, used once, re-checked just before the write
   (the spike covers the first two; the re-check before the write is not covered).
7. Large results by reference; replay of 10,000 steps takes about 0.13 s, so no snapshotting is needed in phase 1.
8. A benchmark of per-step overhead in the engine's own test suite with the 20 ms p95 bound (11 §10), run on the Windows runner.
9. Server start with the Windows rule above, with a `windows_check`-style test in the engine's Windows job.

## Open risks

- **Windows result pending.** Every Job Object statement is documented but unmeasured. If `windows_check.py` fails on
  a case (for example `nested`, or the thread scan in `resume_process`), the recommendation changes.
- **Power loss and disk faults** were not tested; the `mixed` policy rests on the SQLite WAL guarantees and the reasoning above.
- **fsync cost on the owner's machine** is unknown (the Linux virtual disk gives 0.11 ms). Antivirus or a synchronized
  folder on a Windows workstation could make it much larger; the workspace should not be inside a synchronized folder, and the
  Windows run of `bench.py` must be read before the policy is fixed.
- **Reconciliation depends on the servers.** The spike's reconciler is a ledger of `op_id` in a fake host. A real
  `reconcile_operation` exists on none of the servers checked here; adapters for servers without one must read model state and
  decide `applied` or `not_applied` from it, which is the weakest part of the design and needs a live test.
- **Divergence limit.** A change after the first unrecorded step is accepted by design; correctness then rests on
  disciplined block versioning (derive the version from the source hash).
- **Replay assumes blocks follow the rules** (no clocks, no randomness, no I/O). The engine detects a violation only when it
  changes a call or an argument; a block that reads the clock and uses it in a branch that changes no call goes unnoticed.
- **Not exercised:** model-state check against `model_saved`, working-copy saves, `ctx.ask`, `ctx.decide`, `ctx.attempts`,
  `ctx.read`, a database of many concurrent runs, and a long run (the largest replay tested is 10,000 steps).
- **Thread-scan resume and PID-based assignment** in `jobobject.py` are spike shortcuts and must not be copied into the
  engine (see the recommendation).
- **Host programs inside a server's job (lead's note).** With `KILL_ON_JOB_CLOSE` alone, a host program that a server
  launches (for example ETABS started by `csi_launch`) is a child of the server and joins its job, so it would end with
  the engine, including an instance the engineer is editing during an engineer turn. The session evidence (Sasaah
  `agent-sessions/_baseline/DESIGN-NOTES.md`, item ج7) and [11](../../design/docs/architecture/11-harness-engine.md)
  §6 item 10 require host programs to stay outside the job and to be closed only by an explicit decision about
  instances the engine started. The engine spec must decide it; the likely answer is
  `JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK` together with `KILL_ON_JOB_CLOSE`, which keeps the servers in the job and
  lets the processes they create break away. Not tested here; `windows_check.py` should gain this case. The trade-off: silent
  breakaway also lets every helper process a server starts outlive it (an orphan helper can hold a pipe or a lock), so
  the engine must still track and close what it started; `JOB_OBJECT_LIMIT_BREAKAWAY_OK` avoids that but needs the server
  to pass `CREATE_BREAKAWAY_FROM_JOB` when it starts a host program, which the Sasaah servers do not do today.
