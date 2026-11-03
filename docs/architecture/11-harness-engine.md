# 11. Harness Engine: `eng-harness`

Status: Proposed (phase 1 revised by ADR-0024, ADR-0025 and ADR-0027) · Phase 1 · Language: Python

## 1. Responsibilities

The engine runs engineer-defined workflows deterministically, step by step, through MCP servers, harness calcs and
code packs. The MCP servers are Sasaah's, reached through one adapter per server
([ADR-0024](../adr/0024-harness-on-existing-sasaah-servers.md)). The engine owns the order of steps, the
check-after-write rule, permissions, the journal, and resumption. It does not own a language-model loop; language
models are used only for typed answers, behind an interface ([ADR-0013](../adr/0013-pydanticai-behind-interface.md)).

## 2. Concepts

| Concept | Definition |
|---|---|
| **Block** | A typed, versioned, async Python function with an input model and an output model (Pydantic). It performs one engineering task by calling steps. Example: `design_isolated_footing` |
| **Workflow** | A block registered with a name, description and setup form (command-line options in phase 1, [ADR-0027](../adr/0027-phase-1-interface.md)). A workflow is a top-level block; blocks compose recursively |
| **Step** | One call on the context: tool, read, calc, decide, ask, approve, child block, check. Steps are the unit of journaling, display, retry and resumption |
| **Run** | One execution of a workflow, with its own id, design basis, permission mode, journal and working models, in `<workspace>/runs/<run_id>/` |

One abstraction (the block) covers both small tasks and full workflows ([ADR-0011](../adr/0011-harness-owns-workflow-engine.md)).

## 3. The context API

Blocks talk to the world only through `ctx`.

| Call | Purpose |
|---|---|
| `ctx.tool(name, **args)` | Call an MCP tool. Returns `ok`, `summary` (with quantities as `Quantity` objects), `ref`, `warnings`. The engine generates `op_id` deterministically from run id, step path and attempt, so retries and resumption are idempotent on servers that accept it; on the Sasaah servers a write is never retried before reconciliation (§6) |
| `ctx.read(ref, pointer)` | Read part of a stored result, journaled, returned as typed values with `Quantity` objects |
| `ctx.calc(id, **args)` | Evaluate an approved harness calc or code-pack check in process. Returns verdict or result summaries and a reference |
| `ctx.decide(question, options, state, rules, policy)` | Make a typed decision through the cascade ([12](12-decision-layer.md)). Returns the chosen option and who decided |
| `ctx.decide_many(...)` | Several decisions in one batched request, and one batched engineer screen when the engineer is needed |
| `ctx.ask(fields)` | Ask the engineer for inputs; the run pauses durably until answered. Answers become `basis` results |
| `ctx.approve(title, preview)` | Request approval; behavior depends on the permission mode (§7). In phase 1 the engineer answers on the local approval page. An approval is bound to the hash of what was shown and to the model state, is used once, and is checked again just before the write; a mismatch voids it. The engineer may reject single items of a change set |
| `ctx.block(other, input)` | Run a child block as a sub-step |
| `ctx.parallel(*steps)` | Run independent steps concurrently, within resource limits (§8) |
| `ctx.attempts(max)` | The only way to loop. Exceeding `max` raises an escalation |
| `ctx.escalate(reason, evidence)` | Stop the block with `NEEDS_ENGINEER` and show the evidence |
| `ctx.basis` | The design basis as references and quantities, for example `ctx.basis.ref("limits.drift_ratio")` |

### Rules for block and rule code

1. **No direct I/O.** Blocks and decision rules never open files, sockets or processes and never import host SDKs.
2. **No engineering arithmetic.** `Quantity` objects support no arithmetic operators. They can be compared only with
   another `Quantity` of the same dimension (typically a design-basis threshold). Any computation that produces an
   engineering value is a `ctx.calc` call.
3. **No literal thresholds.** Numeric literals are not allowed in block and rule modules (the same lint as for checks);
   thresholds and tolerances come from the design basis.
4. **Deterministic.** Given the same step results, a block makes the same calls in the same order. No clocks, random
   numbers or environment reads.
5. **Bounded.** Loops only through `ctx.attempts(max)`.
6. **Typed.** Inputs, outputs, decision options and decision state are Pydantic models or enums.

## 4. Harness calcs

Deterministic computations that are not code clauses live in `eng_harness.calcs`: comparing two model states (the
difference report of the edit cycle), summarizing design results (governing ratios, failing members), rounding new
section sizes to the basis increment, and comparing element counts and positions.

They follow the same rules as code-pack checks: pure functions, bounded inputs, cited sources or basis references for
every constant, a recorded trace, golden tests with sources, and an **approval bound to the content hash** in the
harness's `approvals.yaml`. Only approved calcs run in production runs. A new section size is always the output of the
rounding calc or an engineer input, never a decision.

## 5. Journal, replay and resumption

- Every run has an append-only event journal in `<workspace>/runs/<run_id>/journal.sqlite`.
- Events: `run_started`, `step_started`, `step_completed` (with result reference), `step_failed` (with error code),
  `decision_made`, `input_requested`, `input_provided`, `approval_requested`, `approval_resolved`, `check_enforced`,
  `model_saved` (with model id, revision, fingerprint and file hash), `run_paused`, `run_resumed`, `run_escalated`,
  `run_completed`, `run_failed`, `signed_off`.
- **Replay**: after a crash or a pause, the engine runs the block function again from the start. Each step whose result
  is in the journal returns the recorded result immediately; execution continues live from the first step without a
  result. If the replayed calls differ from the journal, the run stops with `ReplayDivergence`.
- **Host state is checked before live execution resumes.** For every model the run wrote to, the engine reads the
  model's identity, revision and fingerprint (through the server's read tools; the adapter computes the fingerprint
  when the server cannot) and compares them with the last `model_saved` event. A mismatch (the host crashed and lost
  unsaved edits, or someone edited the model) stops the run with three choices: accept the differences as engineer
  changes and continue (the normal turn of the edit cycle, [18](18-first-slice-dxf-to-etabs.md)), restore the last
  saved working copy and continue from the step after its `model_saved` event, or abandon the run.
- In `work_on_copy` mode, the working copy is saved after every write step, so a host crash loses at most one step.
- A step that was in flight when the engine stopped is reconciled first: tool writes through `reconcile_operation`, or
  by reading the model state on servers without it; pending approvals and inputs are re-presented.
- The terminal progress, the approval page and the run report read the same journal, so what the engineer sees is
  exactly what happened.

## 6. Enforced invariants

The engine enforces these regardless of what block code does:

1. **Check after write (P7).** After any successful write step on a model, the model is marked dirty. Before the next
   step that reads results from that model, before any approval, and before the block returns, the engine inserts a
   `check_model` step (for the Sasaah servers, the adapter's read-back check). Errors fail the step with
   `ModelIntegrityError`, which the block may route to a decision or an escalation; it cannot be skipped.
2. **References for engineering quantities (P2).** The engine rejects literals for parameters marked
   `engineering_quantity` before calling a tool. The adapters mark those parameters for the Sasaah servers and resolve
   references themselves; servers that follow [05](05-mcp-server-standard.md) are also started with
   `ENG_REQUIRE_REFS=1`.
3. **No stale inputs.** Every reference passed to `ctx.calc`, `ctx.decide` or `ctx.approve` that comes from a host model
   must be at that model's current revision.
4. **Decisions cannot produce numbers (P10).** Decision outputs are enum members or indexes into lists of references.
5. **Never assume inputs (P8).** A run does not start until the design basis has every field the workflow declares as
   required, each with a source and confirmed.
6. **Honest outcomes (P9).** `TIMEOUT_UNKNOWN_OUTCOME` and `HOST_WEDGED` always lead to reconciliation before any
   further step on that host. The adapters report a Sasaah server timeout during a write, an analysis or a design run
   as `TIMEOUT_UNKNOWN_OUTCOME`.
7. **Save before analysis.** The engine saves the model before every analysis or design run, so no run waits on a
   save dialog.
8. **Server builds.** At run start every server's build must be at least the minimum the workflow declares, and the
   fingerprint of its tool list (names and input schemas) must match the one its adapter was tested with; otherwise the
   run stops before any write ([ADR-0024](../adr/0024-harness-on-existing-sasaah-servers.md)).
9. **Host units.** After any timeout, reconnect or server restart, the adapter reads the model's present units before
   the next step. If they differ from the units it expects, the run stops with `PRECONDITION_FAILED` until they are
   restored and the step is reconciled. The Sasaah CSI engine does not check that it restored units after a call and
   skips the restore when a call times out.
10. **One driver per host instance.** The engine takes a lock per host instance before attaching, so two servers or two
    runs never drive the same instance; the Sasaah servers do not guard this themselves. The engine closes only host
    instances it started, identified by process id and start time, and never ends an instance it did not start.

## 7. Permission modes

Chosen per run (a command-line option in phase 1), with a default in settings
([ADR-0018](../adr/0018-permission-modes.md)):

| Mode | Behavior |
|---|---|
| `work_on_copy` (default) | **New models** are created in the run folder; promotion copies the final file to the target path, keeping a backup of anything it replaces. **Existing models** are saved as a working copy before the first write; all writes go to the copy; promotion replays the journaled write steps on the original (fresh `op_id`s), runs `check_model`, and compares the change sets with the copy's. Promotion always needs approval |
| `approve_each_write` | Every write step shows its dry-run change set and waits for approval |
| `autonomous_logged` | Writes apply directly and are journaled; the engineer reviews afterwards |

In every mode, the "always ask" list still asks: deleting objects, overwriting a saved original, and anything a workflow
marks as always-ask.

In the model edit cycle, promotion copies the accepted revision's file to the target path, keeping a backup, instead of
replaying write steps: the revision may hold manual edits by the engineer that no journaled step can replay. Promotion
stops if the original's file hash changed since the working copy was taken.

## 8. Concurrency and resources

- Independent steps run concurrently with `ctx.parallel`. Steps on the same host are serialized by its server.
- Resource limits in settings: maximum concurrent host programs (to respect workstation memory), maximum concurrent
  decision requests.

## 9. Server management

- Servers are declared in `harness.toml` with their command, toolsets, options and the minimum build the workflows
  need. In phase 1 they are the Sasaah servers, each with its adapter. Sasaah command-line tools are declared the same
  way and wrapped by an adapter, so blocks call them with `ctx.tool`.
- Each adapter's allowlist leaves out every tool that runs scripts or writes database tables directly (on the Sasaah
  CSI server today: `csi_run_script` and `csi_db_tables_apply`), and the CSI server is started with its `DisableScript`
  option.
- Analysis and design runs get a call timeout suited to them, or are started and then followed through the server's
  status tool (`csi_analysis_status`); they are never a single call bounded by the server's default timeout of
  120 seconds.
- The engine starts every server inside a Windows Job Object configured to terminate its processes when the engine
  exits, so no orphaned server keeps a host locked.
- Servers that follow [05](05-mcp-server-standard.md) get `ENG_WORKSPACE` (the project workspace) and
  `ENG_REQUIRE_REFS=1`; for the Sasaah servers the adapters provide both behaviors. The engine checks each server's
  build and tool list at start (§6), restarts a crashed server, and reconciles any write that was in flight. `HOST_LOCKED` (`model_locked`
  from the Sasaah CSI server) is shown to the engineer, never retried.
- Workflows are tested without host programs against recorded server replies (the adapters' contract tests) and, on
  servers that offer one, a fake host (`--host-mode fake --fake-model <fixture>`).

## 10. Performance targets

| Measure | Target |
|---|---|
| Engine overhead per step (excluding the tool's own time) | under 20 ms at p95 |
| Rule decision | under 1 ms |
| Decision-model decision, batched (from phase 2) | under 800 ms at p95, measured in spike S-07 |
| Progress display update after an event | under 200 ms |
| First workflow, request to accepted revision, including engineer interaction | at most 50% of the baseline time ([18](18-first-slice-dxf-to-etabs.md) §5) |

## 11. Interfaces

- **Phase 1** ([ADR-0027](../adr/0027-phase-1-interface.md)): the command line, live progress in the terminal, a local
  HTML approval page and an HTML run report. The full UI ([14](14-harness-ui.md)) comes later.
- **CLI**: `eng-harness run <workflow> --basis <file> --mode <mode>`, `eng-harness resume <run_id>`,
  `eng-harness status <run_id>` and `eng-harness stop <run_id>`, for people, coding agents and CI tests. There is no
  approve command; approvals are given on the page.
- **Library**: blocks and the engine are importable for tests.

## 12. Phase 1 scope

Phase 1 builds: the engine with journal, replay and host-state checks; adapters for `sasaah-csi-mcp` and the Sasaah
tools the first slice uses; harness calcs for the edit cycle ([18](18-first-slice-dxf-to-etabs.md)); templates and the
design basis; the decision layer with rules and the engineer tier; the command line, terminal progress, approval page
and run report. The decision-model tier, the language-model tier and PydanticAI arrive in phase 2
([ADR-0025](../adr/0025-first-workflow-edit-cycle.md)).
