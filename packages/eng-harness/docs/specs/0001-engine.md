---
id: spec-0001-engine
issue: "B-060"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2]
---

# Spec 0001: eng-harness engine (blocks, ctx, journal, replay, invariants)

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-03

This spec implements the engine of [11-harness-engine](../../../../design/docs/architecture/11-harness-engine.md)
(cited as "11 §n") with the amendment of
[ADR-0030](../../../../design/docs/adr/0030-replay-by-step-path-and-reconciliation.md) (Proposed), which records the
findings of [spike S-10](../../../../spikes/S-10-replay/REPORT.md) ("S-10"). It does not repeat 11: where 11 states a
rule, this spec names the section and adds what an implementer and a reviewer need to decide a case. Details that 11
leaves open are marked **[added]** and listed in §11. The contract API it uses is
[eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract §n").

Later specs implement the engine's ports: 0002 servers and adapters (ToolPort, HostPort, server processes, Job
Objects, host-instance locks), 0003 calcs (CalcPort), 0004 templates and design basis (BasisPort), 0005 decision layer
(DecisionPort), 0006 command line, progress, approval page and run report (ApprovalPort, InputPort, ProgressSink,
RunControlPort), 0007 the model edit cycle workflow.

## 1. Problem

The first workflow, the model edit cycle ([ADR-0025](../../../../design/docs/adr/0025-first-workflow-edit-cycle.md)),
failed in the session review behind [ADR-0024](../../../../design/docs/adr/0024-harness-on-existing-sasaah-servers.md)
for workflow reasons, not server reasons: unknown analysis outcomes (10 of 74 runs), lost manual edits, runs that
waited on dialogs. The engine is what removes these: it runs typed blocks deterministically, journals every step,
resumes by replay without repeating a write, and enforces the safety invariants of 11 §6 whatever block code does.
Nothing exists yet; every phase 1 workflow, and every later spec of this package, depends on it.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| S-10 spike engine (`spikes/S-10-replay/engine.py`) | Proves the design: path identity, replay index, in-flight rule, run lock, append-only triggers, overhead p95 0.54 ms (Linux) | Design reused; code is throwaway and not copied (S-10 "Method") |
| Temporal, Restate, DBOS, other durable-execution services | Strong, but a service or heavy dependency for one workstation ([ADR-0014](../../../../design/docs/adr/0014-run-journal-and-replay.md) alternatives) | Not used |
| LangGraph and agent frameworks | Rejected by [ADR-0011](../../../../design/docs/adr/0011-harness-owns-workflow-engine.md) | Not used |
| `sqlite3` (standard library) | WAL, triggers, per-connection `synchronous`; measured by S-10 | Used |
| `fcntl.flock`, `msvcrt.locking` (standard library) | OS locks released when the process dies (S-10 "run lock") | Used for the run lock |
| `sys.addaudithook` (standard library, PEP 578) | Audit events for file, process, socket and sqlite operations | Used for the runtime guard (§4.3.4) |
| `eng-contract` 0.1 | Canonical JSON, ids, clocks, envelopes, store, refs, `Quantity`, kinds, `ContractError` | Used; no logic re-implemented |
| Pydantic 2 | Block, port and event models ([ADR-0011](../../../../design/docs/adr/0011-harness-owns-workflow-engine.md)) | Used (runtime dependency named by ADR-0011) |

No runtime dependency other than `eng-contract` and `pydantic` is added. Async code uses `asyncio` only.

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Fake ports" are the in-memory fakes of §4.8; "fake-host
workflow test" means a test block run by the real engine against fake ports with a real SQLite journal in a temporary
workspace (process/05 §1 "Workflow" layer, engine side; the server-process side is spec 0002).

### 3.1 Package, blocks and registry

- AC1. Given the package, when imported, then `eng_harness.__version__` equals `[project].version`, every module in
  `[tool.eng-gate].public_modules` imports, and every other module under `src/eng_harness/` has a name component
  starting with `_`. Tests: `tests/unit/test_package.py::test_version_matches_project`,
  `::test_public_modules_import`, `::test_private_modules_are_underscored`.
- AC2. Given a block function that is not `async def`, an input or output type that is not a Pydantic `BaseModel`
  subclass, a name not matching `^[a-z][a-z0-9_]*$`, a version not matching `^[1-9][0-9]{0,3}$`, or a second block
  with the same name, when it is registered, then `RegistryError` names the rule. Test:
  `tests/unit/test_block.py::test_registration_rules`.
- AC3. Given a registered block, then its `BlockDef` holds `name`, `version` and `code_sha256` (the SHA-256 of its
  module's source with line endings normalized to LF), identical across two interpreter runs. Test:
  `tests/unit/test_block.py::test_code_hash_is_stable`.
- AC4. Given a lock entry `{name, version, code_sha256}` and a block with the same name and version but another hash,
  when `check_lock` runs, then it reports `VERSION_BUMP_REQUIRED` for that block; and the committed
  `src/eng_harness/blocks.lock.json` matches the real registry. Tests: `tests/unit/test_block.py::test_check_lock`,
  `tests/contract/test_block_lock.py::test_lock_matches_registry`.

### 3.2 Steps, paths and the ctx API

- AC5. Given a block with sequential steps, a child block, `ctx.parallel` of three children and a `ctx.attempts`
  loop, when it runs twice with fake ports that complete the parallel children in opposite orders, then both runs
  record identical step paths (§4.3.1), including the inserted check steps, and results, and `ctx.parallel` returns
  results in argument order; and given two sibling children of one `ctx.parallel` of which one writes a model and the
  other reads or writes the same model, then `BlockRuleViolation` is raised before the second one's port call, in
  either completion order. Tests: `tests/unit/test_steps.py::test_paths_independent_of_completion_order`,
  `::test_sibling_model_conflict`.
- AC6. Given a run id, a path and an attempt, then `op_id` is `"op_"` followed by the first 32 hex digits of
  `sha256(run_id + "\n" + path + "\n" + str(attempt))`, differs for every attempt, and is passed to every write call.
  Test: `tests/unit/test_steps.py::test_op_id`.
- AC7. Given two steps that overlap in time in one scope without `ctx.parallel` (for example `asyncio.gather` of two
  `ctx.tool` calls), then the second raises `BlockRuleViolation` (`BLOCK_RULE_VIOLATION`) before its port call. Test:
  `tests/unit/test_steps.py::test_overlap_outside_parallel`.
- AC8. Given parallel children of which several fail, then every child runs to its end (none is cancelled), and the
  error raised is chosen by the class rank of §4.3.2 and then by the lowest child index, never by completion order.
  Test: `tests/unit/test_steps.py::test_parallel_error_choice`.
- AC9. Given `ctx.attempts(limit)` where `limit` is not a `BasisCount` or exceeds `EngineSettings.max_attempts_cap`,
  then `BlockRuleViolation`; given a loop that exhausts its limit, then `run_escalated` with reason
  `attempts_exhausted` and run status `NEEDS_ENGINEER`. Test: `tests/unit/test_ctx_attempts.py::test_attempts_rules`.
- AC10. Given block code that wraps `ctx.approve` in `except Exception`, when the approval pauses the run, then the
  pause still propagates, because `EngineStop` derives from `BaseException`. Tests:
  `tests/unit/test_errors.py::test_engine_stop_is_not_exception`,
  `tests/workflow/test_pause.py::test_except_exception_cannot_swallow_pause`.
- AC11. Given a tool whose envelope summary holds quantity objects, when `ctx.tool` returns live and when the same
  step is replayed, then both `ToolResult` values are equal, summaries hold `Quantity` objects, and the summary passed
  through `eng_contract.canonical` before the block saw it. A failure envelope raises `ToolFailed` with the
  `ErrorDetail`. Tests: `tests/unit/test_codec.py::test_live_equals_replayed`,
  `tests/unit/test_ctx_tool.py::test_tool_result_and_failure`.
- AC12. Given a stored result, when `ctx.read(ref, pointer)` runs, then the step is journaled with kind `read`, the
  value is returned with quantity objects as `Quantity`, and pointer and reference errors are the contract's
  `REF_*` codes. Test: `tests/unit/test_ctx_read.py::test_read`.
- AC13. Given a calc, when `ctx.calc(id, args)` runs, then the step is journaled with the calc's id, version, content
  hash and status, and returns a `CalcResult`; a `draft` or `verified` calc marks the run's outputs `DRAFT`. Test:
  `tests/unit/test_ctx_calc.py::test_calc_step`.
- AC14. Given `ctx.escalate(reason, evidence)`, then the block stops, `run_escalated` records the reason and the
  evidence references, and the run status is `NEEDS_ENGINEER`. Test: `tests/unit/test_ctx_escalate.py::test_escalate`.
- AC15. Given `ctx.block(child, input)`, then `step_started` records the child's name, version and code hash, the
  child's steps are under the block step's path, and the child's input and output are validated against its models.
  Test: `tests/unit/test_ctx_block.py::test_child_block`.
- AC61. Given `ctx.ask(fields, title=...)` with a Pydantic model `fields`, when no answer is stored, then
  `input_requested` (kind `block`) is journaled, the run pauses (`run_paused`, reason `awaiting_input`) and the process
  returns `PAUSED`; when it is resumed with an answer that validates against `fields`, then the answer is stored as a
  `basis.engineer_input/1` result, `input_provided` records its `answer_ref` and `by`, the block receives
  `Answered[M]` whose `value` is the validated model and whose `field_ref(name)` is a reference into that result, and a
  further resume replays it without asking again; an answer that fails `fields` is refused and the request presented
  again. Test: `tests/unit/test_ctx_ask.py::test_ask_stores_engineer_input`.
- AC16. Given a run input that fails the workflow's input model, then `start` raises `ContractError`
  (`INVALID_ARGUMENT`) and creates no run folder; given a block that returns a value that is not an instance of its
  output model, then `BlockRuleViolation`. Test: `tests/unit/test_runner.py::test_input_and_output_validation`.
- AC17. Given a design basis, then `ctx.basis.ref(path)` is the reference of contract §4.10.2
  (`res_<id>#/fields/<path>/value`), `ctx.basis.quantity(path)` is a `Quantity`, and a path the workflow did not
  declare in `required_basis` raises `BlockRuleViolation`. Test: `tests/unit/test_ctx_basis.py::test_basis_view`.
- AC18. Given block code that opens a file, starts a process, opens a socket or connects to SQLite while the block
  runs, directly, inside a child of `ctx.parallel`, inside a child block run by `ctx.block`, or inside the body of a
  `ctx.attempts` loop, then the runtime guard raises `BlockRuleViolation` and the operation does not happen; the
  engine's own I/O in the same process, including during those calls, is unaffected. Tests:
  `tests/unit/test_guard.py::test_guard_blocks_io_in_block_code`, `::test_guard_covers_parallel_children_and_child_blocks`.
- AC19. Given fixture block and rule modules with an import outside the allowlist of §4.1.2, a read of an attribute
  named `value`, an arithmetic operator, a `while` loop, a bare `except` or `except BaseException`, then the
  block-module rules test reports each; and every module matching `block_modules` or `rule_modules` in this package
  passes. Tests: `tests/rules/test_block_modules.py::test_rules_detect_violations`,
  `::test_package_block_modules_pass`.

### 3.3 Journal

- AC20. Given a new journal, then it is in WAL mode; `UPDATE` and `DELETE` on `events` and `meta` abort;
  `INSERT OR REPLACE`, `REPLACE` and `INSERT OR IGNORE` of an existing `events.seq` or `meta.key` abort; an event whose
  `seq` is not the last `seq` + 1 (a gap, a `NULL` or an earlier value) aborts; and an event type outside §4.4.2 is
  refused by a `CHECK` constraint. Test: `tests/unit/test_journal.py::test_append_only`.
- AC21. Given a journal whose stored payload or chain hash was altered outside the engine, when it is opened, then
  `JournalIntegrityError` (`JOURNAL_INTEGRITY`) names the first bad `seq`. Test:
  `tests/unit/test_journal.py::test_hash_chain_detects_tampering`.
- AC22. Given the durability policy of §4.4.3, then each event of the `FULL` set is committed with
  `synchronous=FULL` and every other event with `NORMAL`. Test: `tests/unit/test_journal.py::test_durability_policy`.
- AC23. Given a run held by a live engine process, when a second engine opens it, then `RunLocked` (`RUN_LOCKED`) and
  the journal is unchanged; when the holding process is killed, the next engine opens it. Test:
  `tests/unit/test_run_lock.py::test_one_engine_per_run` (and `tests/windows/test_run_lock_windows.py`, marker
  `windows`).
- AC24. Given a step result or argument set whose canonical JSON is larger than `INLINE_EVENT_BYTES`, then the event
  holds a `result_id` of a `harness.journal_blob/1` result instead, and the reader returns the full value. Test:
  `tests/unit/test_journal.py::test_large_payloads_by_reference`.
- AC25. Given a journal being appended by an engine, then `JournalReader` (read-only) folds the events into
  `RunView`, `StepView`, `RequestView` and `ModelSavedView` as §4.4.5 states, and `follow(after_seq)` returns only
  newer events. Test: `tests/unit/test_journal_reader.py::test_views_and_follow`.
- AC26. Given any event, then its payload is validated against its model on append and on read; an invalid payload is
  refused on append with `ContractError` `INTERNAL` (an engine bug, not a block error), and an invalid stored payload
  is `JournalIntegrityError`. Test:
  `tests/unit/test_journal.py::test_payload_models`.

### 3.4 Replay and resumption

- AC27. Given a run paused at an approval, when it is resumed after the answer arrives, then every recorded step
  returns its recorded result without a port call and execution continues live at the first unrecorded step. Test:
  `tests/replay/test_resume.py::test_pause_and_resume`.
- AC28. Given each change of S-10's divergence list (changed argument, tool, inserted step, removed step, parallel
  size, approval preview, block ending before the journal does, run input, block name, block version), when the run is
  resumed, then `ReplayDivergence` stops it before any live port call, the journal gains only `run_escalated`, and the
  original block still resumes it afterwards. Test: `tests/replay/test_divergence.py::test_divergence_variants`.
- AC29. Given a block whose code hash changed but whose version did not, when the run resumes, then `run_resumed`
  records `code_hash_changed: true` and the run continues. Test: `tests/replay/test_divergence.py::test_hash_change_warns`.
- AC30. Given a mixed read, write, parallel and approval test workflow run in a worker process killed at each of the
  four crash points of S-10 for every step, when each is resumed, then every write is applied exactly once on the fake
  host, and the final output and step identities equal those of an uninterrupted run. Test:
  `tests/replay/test_crash_matrix.py::test_crash_matrix`.
- AC31. Given a write in flight (a `step_started` without a result) at resume, then it is reconciled before the block
  is called: `applied` records `step_reconciled` and the step returns the reconciled result with no call;
  `not_applied` records `step_reconciled` and runs the step as attempt + 1 with a new `op_id`; `partial`, `unknown`,
  no reconciler or a reconciler error stops the run with `NEEDS_RECONCILIATION` and an engineer request whose answer
  resolves it. Test: `tests/replay/test_in_flight.py::test_write_in_flight`.
- AC32. Given a read, calc or decision step in flight at resume, then `step_rerun` is recorded and the step runs
  again. Test: `tests/replay/test_in_flight.py::test_read_in_flight`.
- AC33. Given a write step whose call raises, returns `TIMEOUT_UNKNOWN_OUTCOME` or returns `HOST_WEDGED`, then the
  step is treated as in flight at once: no further step on that host is sent until reconciliation. Test:
  `tests/workflow/test_honest_outcomes.py::test_unknown_outcome_reconciled_first`.
- AC34. Given a run that wrote a model, when it resumes and the model's identity, revision or fingerprint differs
  from the last `model_saved`, then the run stops with the three choices of 11 §5; `accept` saves and records a new
  baseline and continues; `restore` restores the saved copy and replays from the step after its `model_saved` (§4.5.4);
  `abandon` records `run_failed`. Test: `tests/replay/test_host_state.py::test_three_choices`.
- AC35. Given a completed run, when it is resumed, then it returns the recorded output with no ToolPort, CalcPort,
  DecisionPort, ApprovalPort or InputPort call; the only HostPort call is `close_started` for its journaled host
  instances (invariant 10). Test:
  `tests/replay/test_resume.py::test_completed_run`.
- AC62. Given a run with a write in flight, when it is resumed with (a) a failing server preflight, (b) a refused host
  lease, or (c) units that differ, then neither `ToolPort.reconcile` nor `HostPort.model_state` is called, the step
  stays in flight in the journal, and a later resume with all three passing reconciles it; and given all three pass,
  then the port calls occur in the order `preflight`, `acquire`, `read_units`, `reconcile`, `model_state`, then the
  first block call (§4.5.1). Test: `tests/replay/test_in_flight.py::test_resume_order_guards_reconciliation`.
- AC63. Given a run with a write in flight on a model, when the host crashed (the fake host reports the model not
  loaded in its bound instance, and `locate` finds it in no instance) and the run resumes, then `ToolPort.reconcile`
  is not called for that write, the host-state check stops the run with reason `model_not_loaded` offering `restore`
  and `abandon` (not `accept`); on `restore`, the fake host restores into a new instance id, `HostPort.restore` returns
  it, `model_bound` (reason `restored`, that instance id) is journaled before the
  `@resume<n>.units_restored.<model_key>` read, that read is made against the new instance and returns `loaded: true`,
  and only then the first live step runs; the in-flight write gets `step_rerun` (reason `restored`) and runs as a new
  attempt with a new `op_id`. Test: `tests/replay/test_host_state.py::test_host_crash_with_write_in_flight`.
- AC64. Instance binding (§4.8): given the first step of a run addressed to a model that the engine did not start a
  host for, then `model_bound` (reason `first_use`) records the instance `HostPort.locate` returned before that step,
  and every later `read_units` and `model_state` on that model names that instance. Given a paused run whose host the
  engineer closed and reopened with the model's last saved file (a new instance id), when it resumes, then
  `model_bound` (reason `reopened`) is journaled, units are read against the new instance, and (a) with no write on the
  model after its last `model_saved`, the host-state check compares with that save and, on a match, the run continues
  with no engineer request; (b) with a write completed or in flight after that save, the write is not reconciled and
  the check stops with reason `model_reopened` offering `restore` and `abandon`. Test:
  `tests/replay/test_host_state.py::test_reopened_in_new_instance`.
- AC36. Given a pending approval or input at resume, then it is presented again with the same request id and a stored
  answer to it is consumed once. Test: `tests/replay/test_resume.py::test_pending_requests_represented`.

### 3.5 Invariants (11 §6)

- AC37. Invariant 1: given a write on a model, then before the next read on that model, any approval, any calc or
  decision, and the block's return, a `check_model` step runs; errors raise `ModelIntegrityError`; no ctx argument or
  setting disables it; and over generated step programs every write is followed by a check before any of those steps.
  Tests: `tests/workflow/test_invariants.py::test_check_after_write`,
  `tests/property/test_check_after_write.py::test_no_unchecked_use_after_write`.
- AC38. Invariant 2: given a literal (number, quantity object or `Quantity`) for a parameter the ToolPort or CalcPort
  marks `engineering_quantity`, then `ContractError` `INVALID_ARGUMENT` with `field`, and no port call. Test:
  `tests/workflow/test_invariants.py::test_engineering_literal_rejected`.
- AC39. Invariant 3: given a reference from a host model at an older revision than the model's current one, passed to
  `ctx.calc`, `ctx.decide` or `ctx.approve`, then `REF_STALE`. Test: `tests/workflow/test_invariants.py::test_stale_ref`.
- AC40. Invariant 4: given decision options that are not a `StrEnum` or a sequence of references, or a DecisionPort
  answer that is not one of the options, then `BlockRuleViolation` or `DecisionInvalid` respectively, and nothing
  numeric reaches the block. Test: `tests/unit/test_ctx_decide.py::test_decisions_cannot_produce_numbers`.
- AC41. Invariant 5: given a design basis with a required field absent or unconfirmed, then `start` raises
  `RunRefused` (`BASIS_INCOMPLETE`) listing the fields, creates no run folder and calls no ToolPort. Test:
  `tests/workflow/test_invariants.py::test_basis_incomplete_refused`.
- AC42. Invariant 6: given `TIMEOUT_UNKNOWN_OUTCOME` or `HOST_WEDGED` from any step on a host, then reconciliation
  runs before any further step on that host, while steps on other hosts continue. Test:
  `tests/workflow/test_honest_outcomes.py::test_reconcile_before_next_step_on_host`.
- AC43. Invariant 7: given a tool whose action is `analysis` or `design`, then a save step of that model runs
  immediately before it, and its `model_saved` is journaled. Test:
  `tests/workflow/test_invariants.py::test_save_before_analysis`.
- AC44. Invariant 8: given a server check that fails (build below the workflow's minimum, or tool-list fingerprint
  mismatch), then the run stops with `RunRefused` (`SERVER_CHECK_FAILED`) before any write, at start and at resume.
  Test: `tests/workflow/test_invariants.py::test_server_check`.
- AC45. Invariant 9: given present units that differ from the expected ones, when (a) a model is first addressed in a
  run, (b) a run resumes (always, in the new engine process, with no epoch change reported), or (c) the host's session
  epoch changed or the engine observed a timeout on that host, then before the next step on that host the run stops
  with `ContractError` `PRECONDITION_FAILED` (`units_verified`). Test:
  `tests/workflow/test_invariants.py::test_units_after_reconnect`.
- AC46. Invariant 10: given a host, then the engine acquires its lease before the first step on it and a refused
  lease raises `HOST_LOCKED`; every instance HostPort reports as started is journaled as `host_started`; at run end
  (`run_completed` or `run_failed` only) the engine passes exactly the journaled instances to `close_started`; given a
  run that paused or crashed after starting an instance, then nothing is closed at the pause, and when a new engine
  process resumes it to completion, it closes that instance from the journal. Tests:
  `tests/workflow/test_invariants.py::test_host_lease_and_close`,
  `tests/replay/test_resume.py::test_close_started_after_resume`.
- AC47. Given a resumed run, then the inserted check, save and first-contact unit steps of invariants 1, 7 and 9
  (`~pre`, `~post`, `~end`) are replayed from the journal like any other step, a journal in which one was removed
  diverges, and recorded `~host` unit steps are skipped without divergence. Test:
  `tests/replay/test_divergence.py::test_inserted_steps_are_replayed`.

### 3.6 Permission modes (11 §7)

- AC48. `work_on_copy`: given an existing model, then a working copy is made and saved (`model_saved`, role
  `working_copy`) before the first write, and every write goes to the copy's model key. Test:
  `tests/workflow/test_modes.py::test_work_on_copy`.
- AC49. `approve_each_write`: given a write, then an approval of its ToolPort preview precedes it; a rejection
  raises `ApprovalRejected` and the write is not called. Test: `tests/workflow/test_modes.py::test_approve_each_write`.
- AC50. `autonomous_logged`: given a write, then it is called without approval; given a `ctx.approve` of kind `INFO`,
  then it is resolved by the mode and journaled with `by: "mode:autonomous_logged"`. Test:
  `tests/workflow/test_modes.py::test_autonomous_logged`.
- AC51. Given, in each mode, a tool with action `delete`, a save over an original, a promotion, a sign-off, or a tool
  the workflow lists in `always_ask`, then an approval is required before it. Test:
  `tests/workflow/test_modes.py::test_always_ask_in_every_mode`.
- AC52. Given an approved file-copy promotion, then the original is backed up into the run folder and the accepted
  revision's files are copied to the target; given that the original's file hash changed since the working copy was
  taken, then `ContractError` `CONFLICT` and nothing is copied; given that the working copy's revision, fingerprint or
  file hash differs from the binding of the `PROMOTION` approval, then `ApprovalVoid` and nothing is copied; given an
  approval that is not of kind `PROMOTION`, not approved, bound to another model or already used, then
  `BlockRuleViolation` and nothing is copied. Tests: `tests/unit/test_promote.py::test_file_copy_promotion`,
  `::test_promotion_rechecks_approval`.
- AC53. Given `ctx.promote(model, Promotion.REPLAY_WRITES)`, then `NotImplementedGap` (`NOT_IMPLEMENTED`, gap E-G1).
  Test: `tests/unit/test_promote.py::test_replay_promotion_is_a_gap`.

### 3.7 Approvals (11 §3)

- AC54. Given an answer whose `shown_sha256` differs from the request, a second answer to a resolved request, or an
  approval answer to an input request, then each is refused, journaled as nothing, and the request stays open (the
  first is presented again). Test: `tests/unit/test_approvals.py::test_binding_and_single_use`.
- AC55. Given an approved change set, when the bound model's revision or fingerprint changed before the first write
  under it, then `ApprovalVoid` is raised before the write and the port is not called. Test:
  `tests/unit/test_approvals.py::test_recheck_before_write`.
- AC56. Given an answer that rejects some items, then writes passed `item=` of an accepted item proceed and a write
  of a rejected item raises `BlockRuleViolation`; a write under an expired approval (§4.9) also raises it. Test:
  `tests/unit/test_approvals.py::test_per_item_rejection_and_expiry`.

### 3.8 Ports, progress, concurrency, performance

- AC57. Given each port of §4.8, then its in-memory fake satisfies the `Protocol` (mypy) and passes the shared
  conformance test. Test: `tests/contract/test_ports_conformance.py::test_fakes_conform`.
- AC58. Given a ProgressSink, then it receives every event after its commit, in `seq` order, before the next step
  starts; a sink that raises is detached, the failure is logged, and the run continues. Test:
  `tests/unit/test_progress.py::test_sink_order_and_failure`.
- AC59. Given `EngineSettings` limits, then no more than `max_parallel_children` children, `max_concurrent_hosts`
  hosts and `max_concurrent_decisions` decision requests are active at once, and steps on one host never overlap.
  Test: `tests/unit/test_resources.py::test_limits`.
- AC60. Given 1,000 write steps through a fake ToolPort that returns at once, with a real SQLite journal, then the
  engine overhead per step is below 20 ms at p95 (11 §10), measured as S-10 measured it. Test:
  `tests/perf/test_overhead.py::test_engine_overhead_p95` (also run in the Windows CI job).

## 4. Design

### 4.1 Package layout and public API

#### 4.1.1 Modules

`packages/eng-harness/src/eng_harness/`. Public modules (listed in `[tool.eng-gate] public_modules`); every other
module has a leading underscore (contract §4.1 convention, 03 §3 rule 2).

| Module | Public names | Who may import |
|---|---|---|
| `eng_harness` | `__version__` | anyone |
| `eng_harness.block` | `block`, `workflow`, `BlockDef`, `WorkflowDef`, `Registry`, `RegistryError`, `check_lock`, `LockFinding` | block code, engine, CLI |
| `eng_harness.ctx` | `Ctx` (Protocol), `ToolResult`, `ReadResult`, `CalcResult`, `Decision`, `DecisionRequest`, `Answered`, `Approval`, `ApprovalKind`, `Preview`, `PreviewItem`, `Attempt`, `BasisView`, `BasisCount`, `ModelHandle`, `Promotion`, `ArgValue` | block code |
| `eng_harness.errors` | `HarnessCode`, `EngineStop` and subclasses, `StepError` and subclasses (§6) | block code (the `StepError` family only), engine |
| `eng_harness.ports` | the ports and data types of §4.8 | engine, later specs' implementations, tests |
| `eng_harness.engine` | `Engine`, `EngineSettings`, `EnginePorts`, `PermissionMode`, `RunRequest`, `RunOutcome`, `RunStatus` | CLI (0006), tests |
| `eng_harness.journal` | `JournalReader`, `Event`, `EventType`, `RunView`, `StepView`, `RequestView`, `ModelSavedView`, `DecisionView`, `RunHeader`, `JournalIntegrityError`, `is_locked` | engine, progress, approval page, run report (0006) |

Internal modules (planned): `engine/_runner.py` (start, resume, run loop), `engine/_ctx_impl.py`, `engine/_steps.py`
(paths, scopes, `op_id`, overlap), `engine/_replay.py` (index, divergence), `engine/_inflight.py`,
`engine/_hoststate.py`, `engine/_invariants.py` (1 to 3, 7), `engine/_hostsafety.py` (5, 6, 8 to 10),
`engine/_decide.py`, `engine/_approvals.py`, `engine/_modes.py`, `engine/_promote.py`, `engine/_guard.py`,
`engine/_codec.py`, `engine/_resources.py`, `_runlock.py` (the run lock, used by the engine and by
`journal.is_locked`), `_kinds.py` (harness kinds), `journal/_schema.py`, `journal/_writer.py`, `journal/_events.py`,
`journal/_reader.py`. Block modules live in `workflows/` and `blocks/`, rule modules in `rules/`
(later specs); the engine has none.

#### 4.1.2 What block and rule code may import

Block modules (`[tool.eng-gate] block_modules`: `src/eng_harness/workflows/**`, `src/eng_harness/blocks/**`) and rule
modules (`rule_modules`: `src/eng_harness/rules/**`) may import only: `eng_harness.block`, `eng_harness.ctx`, the
`StepError` family of `eng_harness.errors`, other block modules (child blocks) and rule modules, `eng_contract.quantity`,
`eng_contract.refs` (`Ref`, `RefString` only), `eng_contract.errors` (`ErrorCode` only, for routing),
`eng_contract.verdicts` (`VerdictStatus` only), `eng_contract.kinds` and its submodules (payload types), `pydantic`,
`enum`, `typing`, `collections.abc`, and `__future__`. Everything else, in particular `eng_harness.engine`,
`eng_harness.journal`, `eng_harness.ports`, adapters, the store, `asyncio` and any I/O module, is refused. This is
types and the ctx API only, never I/O. Enforced by the block-module rules test (AC19) and by the gate's FB004 and FB005
([eng-dev-gate spec](../../../../tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md) §4.8).

### 4.2 Blocks, workflows and the registry

```python
@block(name="apply_change_set", version=1)
async def apply_change_set(ctx: Ctx, inp: ChangeSetInput) -> ChangeSetOutput: ...


@workflow(
    name="model_edit_cycle",
    version=1,
    description="...",
    required_basis=("limits.drift_ratio",),
    min_server_builds={"sasaah-csi-mcp": "<pinned build>"},
    always_ask=("csi_unlock_model",),
)
async def model_edit_cycle(ctx: Ctx, inp: EditCycleInput) -> EditCycleOutput: ...
```

- `BlockDef[I, O]` (frozen): `name`, `version` (`int`), `input_model`, `output_model`, `fn`, `module`,
  `code_sha256`. `WorkflowDef` adds `description` (1 to 500 characters), `required_basis` (basis paths of contract
  §4.10.2), `min_server_builds` (server name to an opaque build string compared by the HostPort, spec 0002),
  `always_ask` (tool names) and `options_model` (the command-line setup form, spec 0006; default `None`).
- The decorators only build the definition; they never register globally (no global mutable state, process/04 §5).
  `Registry(blocks: Iterable[BlockDef])` is immutable; `Registry.with_(...)` returns a new one. Rules of AC2; a
  workflow is also a block (`WorkflowDef` is a `BlockDef`).
- `code_sha256` is the SHA-256 of the module source read with `importlib` (`loader.get_source`), line endings
  normalized to LF, computed once at definition. Missing source (frozen module) is `RegistryError`.
- **Version rule (S-10 divergence limit; OQ-Q17).** The run header records the root block's name, version and code
  hash; each `block` step records its child's. At resume: a name or version change is `ReplayDivergence`; a hash change
  with the same version is a warning in `run_resumed` (AC29). To make the version bump mandatory, the package commits
  `src/eng_harness/blocks.lock.json` (`[{name, version, code_sha256}]`, sorted by name), and the contract test of AC4
  fails when any block's hash changed without a version change. The lock is rewritten by
  `uv run python -m eng_harness.block --write-lock`, which refuses to write an entry whose hash changed while its
  version did not.

### 4.3 Steps, paths and the ctx API

#### 4.3.1 Step paths

- A scope holds a counter. Each ctx call made directly in a scope takes the next index: the root block's steps are
  `0`, `1`, `2`; the steps of a child block run at path `p` are `p/0`, `p/1`; child `i` of `ctx.parallel` at `p` runs
  in scope `p/i`; iteration `i` of `ctx.attempts` at `p` runs in scope `p/i`. Paths depend on argument position and
  call order only (S-10 "parallel determinism").
- Engine-inserted steps (§4.6) take the path of the step that triggered them plus a suffix: `p~pre.<kind>.<key>`
  (before step `p`), `p~post.<kind>.<key>` (after it), `p~end.<kind>.<key>` (before the block at `p` returns; the root
  block uses `~end...`). They are decided only from the block's own steps, so they are part of the replayed sequence
  (AC47). Steps triggered by a host event (a session epoch change or an observed timeout, invariant 9) take
  `p~host.<kind>.<key>`; they are journaled but not part of the replayed sequence (§4.5.2 rule 5).
- Housekeeping steps of a resume (host-state reads, server checks) take paths `@resume<n>.<kind>.<key>` and are not
  replayed: each resume runs them again.
- Grammar: `index = "0" | [1-9][0-9]*`; `path = index ("/" index)* [ "~" ("pre"|"post"|"end"|"host") "." kind ["." key] ]`,
  or `"@resume" index "." kind "." key`; `key` matches `^[A-Za-z0-9_.:-]{1,200}$`; at most 1024 characters.
- `op_id = "op_" + sha256(run_id + "\n" + path + "\n" + str(attempt)).hexdigest()[:32]` (11 §3, AC6). The attempt
  starts at 1 and increases only after a reconciled `not_applied` or a retry of §4.3.3.
- **Models in parallel children.** Each child of `ctx.parallel` keeps its own dirty flags (invariant 1), so the check
  steps inserted in a child depend only on that child's own steps. Before each port call in a child, the engine
  compares the step's model (`ToolInfo.model_param`) with the models its siblings in the same `ctx.parallel` have
  touched so far: a step that reads or writes a model a sibling wrote, or writes a model a sibling read, is
  `BlockRuleViolation` (a race the block must not contain). When the parallel ends, the models any child left dirty
  get `p~post.check_model.<model_key>` steps in model-key order. Which of two conflicting siblings reaches the check
  first may vary, but the outcome (a stop with `BlockRuleViolation` before the conflicting call) does not (AC5).
- A scope allows one step in progress at a time. A second overlapping step in the same scope is `BlockRuleViolation`
  (S-10 "rules"); concurrency exists only through `ctx.parallel`.

#### 4.3.2 The ctx calls

All calls are `async` unless marked. `ArgValue` = `str | bool | int | float | None | Ref | ToolResult | CalcResult |
ReadResult | StrEnum | Sequence[ArgValue] | Mapping[str, ArgValue]`; a result passed as an argument is sent as its
`Ref`. Arguments are passed as an explicit mapping, not as `**kwargs`, so tool arguments never collide with engine
options **[added: 11 §3 writes `**args`]**.

| Call | Signature and return | Step kind, effect |
|---|---|---|
| tool | `tool(name: str, args: Mapping[str, ArgValue] = {}, *, under: Approval \| None = None, item: str \| None = None) -> ToolResult` | `tool`; effect from `ToolInfo` |
| read | `read(ref: Ref \| ToolResult \| CalcResult, pointer: str = "") -> ReadResult` | `read`; none |
| calc | `calc(calc_id: str, args: Mapping[str, ArgValue] = {}) -> CalcResult` | `calc`; none |
| decide | `decide(question: str, options: type[E] \| Sequence[Ref], state: BaseModel, rules: Sequence[Rule], policy: DecisionPolicy) -> Decision[E \| Ref]` | `decide`; none |
| decide_many | `decide_many(requests: Sequence[DecisionRequest]) -> list[Decision]` | `decide_many`; none |
| ask | `ask(fields: type[M], *, title: str) -> Answered[M]` | `ask`; none |
| approve | `approve(title: str, preview: Preview, *, kind: ApprovalKind = ApprovalKind.CHANGE_SET) -> Approval` | `approve`; none |
| block | `block(child: BlockDef[I, O], inp: I) -> O` | `block`; scope |
| parallel | `parallel(*steps: Awaitable[T]) -> list[T]` (typed overloads up to six arguments return tuples) | `parallel`; scope |
| attempts | `attempts(limit: BasisCount) -> AsyncIterator[Attempt]` (use: `async for a in ctx.attempts(...)`) | `attempts`; scope |
| escalate | `escalate(reason: str, evidence: Sequence[Ref]) -> NoReturn` | `escalate` |
| promote | `promote(model: ModelHandle, how: Promotion, approval: Approval) -> ModelHandle` **[added]** | `promote`; write |
| basis | `basis: BasisView` (property, synchronous): `ref(path) -> Ref`, `quantity(path) -> Quantity`, `count(path) -> BasisCount`, `choice(path, enum: type[E]) -> E` | not a step (the basis is frozen and in the run header) |

Result types (frozen Pydantic models): `ToolResult` (`tool`, `ref: Ref`, `summary: Mapping[str, SummaryValue]`,
`warnings: tuple[ContractWarning, ...]`, `complete: bool`, `model: ModelHandle | None`), where `SummaryValue` is a JSON
value in which every quantity object of contract §4.8 is a `Quantity` or `LabeledQuantity`; `ReadResult` (`ref`,
`kind`, `value`); `CalcResult` (`calc_id`, `calc_version`, `status`, `ref`, `summary`, `draft: bool`); `Decision`
(`choice`, `decided_by`, `confidence: float | None`); `Answered[M]` (`value: M`, `ref: Ref` of the
`basis.engineer_input/1` result, `field_ref(name) -> Ref`); `Approval` (§4.9); `Attempt` (`index`, `is_last`).
`ctx.tool` raises `ToolFailed` for a failure envelope (it never returns `ok: false`); `TIMEOUT_UNKNOWN_OUTCOME` and
`HOST_WEDGED` never reach the block (§4.5.3).

**Parallel error choice.** `ctx.parallel` waits for every child (no child is cancelled, so no write is interrupted)
and then raises one error: the first by class rank `ReplayDivergence` > `NeedsReconciliation` > `BlockRuleViolation`
> `Escalation` > `Pause` > `StepError`, and within a class the lowest child index (S-10, AC8).

**Attempts.** `limit` must be a `BasisCount` (an `int` read from the design basis with `ctx.basis.count`, so no
literal appears in block code, gate FB005) and at most `EngineSettings.max_attempts_cap`; iteration `i` runs in scope
`p/i`; leaving the loop with `break` ends it; finishing the last iteration without `break` raises
`Escalation(reason="attempts_exhausted")` (11 §3).

#### 4.3.3 Retries

The engine retries a failed step only when the contract retry rule is `always` (`HOST_NOT_CONNECTED`, `HOST_BUSY`,
`TIMEOUT_NO_EFFECT`) and the step is a read, or a write that the adapter reports as not sent; at most
`EngineSettings.step_retry_limit` times, each as a new attempt (`step_failed`, then `step_started` with attempt + 1).
`after_wedge_clears` and `reconcile_first` go through §4.5.3. `depends` (`HOST_ERROR`) follows `retryable` of the
`ErrorDetail`. Everything else fails the step. At resume, a recorded `step_failed` with a retryable code runs again as
the next attempt; a non-retryable one is raised again from the journal (deterministic replay).

#### 4.3.4 Rules for block and rule code, enforced at runtime

The gate's lint (FB004, FB005) and the block-module rules test (AC19) check the source. The engine checks at runtime:

| Rule (11 §3) | Runtime enforcement |
|---|---|
| 1 No direct I/O | Runtime guard: one `sys.addaudithook` hook per process, installed by the first `Engine`. A context variable (`in_block_code`) is false only while the engine executes its own step work (port calls, journal and store writes, codec, invariant checks) and true whenever control is in block or rule code, including the children of `ctx.parallel`, the function of a child block run by `ctx.block`, and the body of an `async for` over `ctx.attempts`: each ctx call sets it false on entry and restores true before it awaits or returns into block-supplied code (a child coroutine, a child block's function, the next loop iteration). While true, the audit events `open`, `os.*` file and process events (`os.remove`, `os.rename`, `os.mkdir`, `os.listdir`, `os.scandir`, `os.system`, `os.exec`, `os.posix_spawn`, `os.spawn`, `os.startfile`), `subprocess.Popen`, `socket.*`, `sqlite3.connect`, `ctypes.*` and `import` raise `BlockRuleViolation` (AC18). The decision layer (0005) evaluates rules inside the same guard |
| 2 No engineering arithmetic | `Quantity` has no arithmetic (contract §4.8); values reach blocks only as `Quantity`; arguments that are numbers or `Quantity` objects for `engineering_quantity` parameters are refused (invariant 2) |
| 3 No literal thresholds | Source lint only (FB005); at runtime, `ctx.attempts` accepts only a `BasisCount` |
| 4 Deterministic | Replay divergence (§4.5.2); overlap detection (§4.3.1); the replay test of every workflow (process/05 §2) |
| 5 Bounded | `while` is refused by the rules test; retry loops only through `ctx.attempts`; a `for` loop over a finite typed collection (for example the items of a change set) is allowed **[added: interpretation of 11 §3 rule 5]** |
| 6 Typed | Input validated with `input_model.model_validate` (strict) at start; the returned value must be an instance of `output_model`; options, states, `ask` fields and previews must be Pydantic models or `StrEnum` (AC16, AC40) |

Engine stops (`EngineStop`) derive from `BaseException`; the rules test refuses a bare `except` and
`except BaseException` in block and rule modules, so no block can swallow a pause, a divergence or a reconciliation
stop (AC10).

### 4.4 The journal

#### 4.4.1 Files and schema

`<workspace>/runs/<run_id>/journal.sqlite`, with `run_id = "run_" + ULID` (from the contract `IdSource`). The run
folder also holds `run.lock` (§4.4.4), `copies/` (working copies, spec 0002), `backups/` (promotion backups) and
`inbox/` (answers, spec 0006).

```sql
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;  -- schema_version, run_id, created_at
CREATE TABLE events (
  seq            INTEGER PRIMARY KEY,          -- 1, 2, 3, ... assigned by the writer, no gaps (trigger)
  type           TEXT NOT NULL CHECK (type IN (<the 20 types of 4.4.2>)),
  path           TEXT,                         -- step path; NULL for run-level events
  attempt        INTEGER CHECK (attempt IS NULL OR attempt >= 1),
  at             TEXT NOT NULL,                -- contract Timestamp, from the injected Clock
  payload        BLOB NOT NULL,                -- canonical JSON (contract 4.3.1)
  payload_sha256 TEXT NOT NULL,
  chain_sha256   TEXT NOT NULL                 -- sha256(prev chain || canonical {seq,type,path,attempt,at,payload_sha256})
) STRICT;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
CREATE TRIGGER events_next_seq BEFORE INSERT ON events
  WHEN NEW.seq IS NOT (SELECT COALESCE(MAX(seq), 0) + 1 FROM events)
  BEGIN SELECT RAISE(ABORT, 'journal seq must be the next integer'); END;
-- the same no_update and no_delete triggers on meta, and:
CREATE TRIGGER meta_insert_once BEFORE INSERT ON meta
  WHEN EXISTS (SELECT 1 FROM meta WHERE key = NEW.key)
  BEGIN SELECT RAISE(ABORT, 'journal meta is write-once'); END;
```

The `BEFORE INSERT` triggers close the `REPLACE` conflict path, on which SQLite deletes the old row without firing
`BEFORE DELETE` triggers unless `recursive_triggers` is on: they fire before conflict resolution, so a replace of an
existing `seq` or `key` aborts (checked with SQLite while writing this spec; AC20). The hash chain additionally detects
an alteration made outside SQLite's triggers (AC21).

The first `chain_sha256` uses 64 zeros as the previous value. On open, the engine and the reader verify the chain
(AC21). One event is one `BEGIN IMMEDIATE` ... `COMMIT` transaction. The engine is the only writer (one engine per run,
§4.4.4); answers from the approval page arrive through ApprovalPort and InputPort and are journaled by the engine
when it consumes them **[added: S-10 let the page process write the journal; a single writer keeps the chain and the
lock simple]**.

**Payloads by reference.** Event payloads hold references, never full results: tool, calc and read results are
`result_id`s in the contract result store (written by the adapters and the CalcPort), with the envelope summary
(at most 4096 bytes, contract §4.2.5). Step arguments and any other payload whose canonical JSON exceeds
`INLINE_EVENT_BYTES` = 16384 (the contract's `INLINE_DATA_LIMIT_BYTES`) are stored as a `harness.journal_blob/1`
result and referenced (AC24). The engine stores run input and output as `harness.run_input/1` and
`harness.run_output/1`, and approval previews as `harness.approval_preview/1`; these kinds are registered with
`KindRegistry.extend` (contract §4.10.1).

#### 4.4.2 Events

The events of 11 §5 plus `step_reconciled`, `step_rerun`, `host_started` and `model_bound` (ADR-0030). Every payload is a Pydantic model with
`extra="forbid"`, validated on append and on read (AC26).

| Event | Payload | Durability |
|---|---|---|
| `run_started` | Run header: `run_id`, `workflow`, `block {name, version, code_sha256}`, `input_ref`, `input_sha256`, `basis_ref`, `mode`, `engine_version`, `contract_version`, `settings_sha256`, `servers` (ServerCheck list), `always_ask` | FULL |
| `step_started` | `kind`, `name`, `args` (canonical JSON, references as `$ref` objects) or `args_ref`, `args_sha256`, `effect` (`none`, `read`, `write`), `op_id` (writes), `host_key`, `model_key`, `under` (approval request id), `item`, `child {name, version, code_sha256}` (block steps) | FULL for writes, else NORMAL |
| `step_completed` | `result` (`ref`, `summary`, `warnings`, `complete`) or the block output ref, `duration_ms`, `calc {id, version, content_sha256, status}` (calc steps) | NORMAL |
| `step_failed` | `error` (contract `ErrorDetail`, or `{harness_code, message}`), `retryable`, `duration_ms` | NORMAL |
| `step_reconciled` | `op_id`, `outcome` (`applied`, `not_applied`), `result`, `decided_by` (`adapter`, `engineer:<name>`), `evidence` (refs) | FULL |
| `step_rerun` | `reason` (`read_in_flight`, `retryable_failure`, `restored`) | NORMAL |
| `decision_made` | 12 §5: `point`, `options`, `choice`, `decided_by`, `confidence`, `latency_ms`, `state_sha256`, `suggestions` | NORMAL |
| `input_requested` | `request_id`, `kind` (`block`, `engine.in_flight`, `engine.host_state`, `engine.escalation`), `title`, `fields_schema_sha256` | NORMAL |
| `input_provided` | `request_id`, `answer_ref` (`basis.engineer_input/1`), `by` | FULL |
| `approval_requested` | `request_id`, `kind`, `title`, `preview_ref`, `shown_sha256`, `binding` (§4.9), `items` (ids) | FULL |
| `approval_resolved` | `request_id`, `shown_sha256`, `decision` (`approve`, `reject`), `rejected_items`, `reason`, `by` (`engineer:<name>` or `mode:<mode>`) | FULL |
| `host_started` | `host_key`, `instance_id` (opaque, from HostPort), `pid`, `process_started_at` (contract Timestamp), `program` (host kind) | FULL |
| `model_bound` | `model_key`, `host_key`, `instance_id` (opaque, from HostPort), `reason` (`first_use`, `restored`, `reopened`) | FULL |
| `check_enforced` | `invariant` (1 to 10), `model_key` or `host_key`, `outcome` (`pass`, `fail`), `ref` | NORMAL |
| `model_saved` | `model_key`, `model_id`, `revision`, `fingerprint`, `file_sha256`, `file_name` (base name only), `role` (`working_copy`, `revision`, `pre_analysis`, `baseline`, `promoted`), `origin_sha256` (working copies) | FULL |
| `run_paused` | `reason` (`awaiting_approval`, `awaiting_input`, `stop_requested`), `request_ids` | NORMAL |
| `run_resumed` | `resume_no`, `code_hash_changed`, `servers`, `restored_to_seq` | NORMAL |
| `run_escalated` | `reason` (`replay_divergence`, `needs_reconciliation`, `host_state_mismatch`, `units_mismatch`, `attempts_exhausted`, `block_escalation`, `block_rule_violation`, `unhandled_error`), `detail`, `evidence`, `request_id` | NORMAL |
| `run_completed` | `output_ref`, `output_sha256`, `draft` | FULL |
| `run_failed` | `reason` (`abandoned`), `by` | FULL |
| `signed_off` | `outputs` (refs), `approval_request_id`, `by` | FULL |

`run_escalated` is not terminal: the journal is unchanged and a resume replays (S-10). Terminal events are
`run_completed` and `run_failed`; after them the run only accepts `signed_off`. A block that raises an uncaught
`StepError` escalates with `unhandled_error`.

#### 4.4.3 Durability (S-10, ADR-0030)

WAL mode; `synchronous=FULL` for the commit of every event marked FULL above, `NORMAL` for the rest (set per
transaction on the writer's connection). The FULL set is S-10's (`run_started`, `run_completed`, the `step_started` of a
write, `step_reconciled`, `approval_requested`, `approval_resolved`) **plus** `model_saved`, `input_provided`,
`run_failed`, `signed_off`, `host_started` and `model_bound` **[added]**: losing one of these after a power failure would make the
host-state check compare with an older baseline, re-ask an answered question, lose a terminal or sign-off record, or
leave a host instance the run started unknown to the engine that must close it, or check a model against the wrong
instance. A lost NORMAL event
is repaired by reconciliation or a rerun (S-10 reasoning). Power loss is not tested (S-10 open risk); the Windows
numbers come from the Windows CI job and the owner's machine (local testing).

#### 4.4.4 One engine per run

`Engine.start` and `Engine.resume` take an exclusive, non-blocking OS lock on `runs/<run_id>/run.lock` (`fcntl.flock`
on POSIX, `msvcrt.locking` on Windows) and hold it until the run returns; the OS releases it when the process dies, so a
crash never leaves a stale lock. A held lock is `RunLocked` (AC23). `journal.is_locked(run_dir)` tells readers whether
an engine is live (it tries the lock and releases it at once).

#### 4.4.5 Reading API

`JournalReader(run_dir)` opens the journal read-only (`file:...?mode=ro`), verifies the chain, and never writes.

| Method | Returns |
|---|---|
| `header() -> RunHeader` | The `run_started` payload |
| `events(after_seq: int = 0) -> list[Event]` | Events in `seq` order; `Event` = `seq`, `type`, `path`, `attempt`, `at`, typed `payload` |
| `follow(after_seq: int) -> list[Event]` | Same as `events`, for polling by the progress display |
| `run() -> RunView` | `run_id`, `workflow`, `mode`, `status` (`RUNNING`, `INTERRUPTED` when the last event is not run-level terminal or paused and no engine holds the lock, `PAUSED`, `NEEDS_ENGINEER`, `COMPLETED`, `FAILED`), `started_at`, `ended_at`, `draft`, `pending` (request ids), `escalation` |
| `steps() -> list[StepView]` | One per path and attempt: `path`, `kind`, `name`, `status` (`running`, `completed`, `failed`, `reconciled`, `rerun`), `started_at`, `ended_at`, `duration_ms`, `result_ref`, `error`, `inserted: bool` |
| `requests() -> list[RequestView]` | Approvals and inputs with their resolution, for the approval page |
| `models() -> list[ModelSavedView]` | `model_saved` history per model, for the report and the host-state check |
| `decisions() -> list[DecisionView]` | `decision_made` events, for the report |

The terminal progress, the approval page and the run report use only this API (11 §5).

### 4.5 Replay and resumption

#### 4.5.1 Start and resume

`start(request)`: validate the input (AC16); load the basis and check invariant 5; run the server checks (invariant 8);
create the run folder, take the lock, store the input, append `run_started`; call the root block.

`resume(run_id)` runs in this order, and no step of it may be moved (AC62):

1. Take the run lock (§4.4.4).
2. Open and verify the journal (AC21). A run whose last run-level event is terminal returns its recorded outcome
   (AC35), after `close_started` for its journaled host instances (invariant 10).
3. Compare the header with the registry (§4.2 version rule); append `run_resumed`.
4. Server preflight (invariant 8): `HostPort.preflight`; a failed check is `RunRefused` (`SERVER_CHECK_FAILED`).
5. Host leases (invariant 10): `HostPort.acquire` for every host key that has an in-flight write or a model the run
   wrote; a refused lease is `HOST_LOCKED` and the run stops.
6. Units (invariant 9): for every model key the journal addressed on those hosts, `HostPort.read_units` as housekeeping
   step `@resume<n>.units.<model_key>`, always (the server is a new process and its own units restore may have been
   skipped, 11 §6 item 9), against the model's bound instance (§4.8); a mismatch stops the run (`units_mismatch`). A
   model its bound instance does not have loaded (`UnitsState.loaded` false) is not a units mismatch: the step records
   `loaded: false` and the engine calls `HostPort.locate(model_key)`. If another instance has the model open (the
   engineer reopened it), the engine journals `model_bound` (reason `reopened`), reads units against that instance
   (`@resume<n>.units_reopened.<model_key>`; a mismatch stops the run) and marks the model **reopened**; if none has
   it, the model is marked **lost**. Both marks hold for steps 7 and 8.
7. In-flight reconciliation (§4.5.3) of every write in flight on a model that is neither lost nor reopened, then the
   rerun marking of reads in flight. A write in flight on a lost or reopened model is not reconciled (the host's memory
   since the last save is gone, so a reconciler could report `not_applied` for an edit that is only gone from memory);
   step 8 resolves it.
8. Host-state check (§4.5.4) for every model the run wrote; a lost model is a mismatch.
9. Call the root block from the start with the replay index.

Reconciliation therefore never runs without the preflight, a lease, a loaded model and verified units on its host; a
stop at steps 4 to 6 leaves the in-flight write in flight for the next resume.

#### 4.5.2 Replay index and divergence

The index maps each path to its events. When the block makes a call at path `p`:

1. If `p` is recorded, compare `kind`, `name`, `args_sha256` (for `approve`, the `shown_sha256`; for `block`, the child
   name and version; for `parallel`, the number of children). A difference is `ReplayDivergence`.
2. Recorded and completed (or reconciled `applied`): return the recorded result through the codec, with no port call.
3. Recorded and failed: §4.3.3.
4. Not recorded: the run goes live (at a resume, the host-state check of §4.5.4 has already run, §4.5.1 step 8).
5. Recorded `~host` steps (§4.6 invariant 9) are skipped: they are audit records of host events, not compared and not
   required.

When the root block returns, any recorded path not visited is `ReplayDivergence` (S-10 "block ending before the
journal does"). Divergence is raised before any live call because recorded steps precede live ones; it is journaled as
`run_escalated` (reason `replay_divergence`) and nothing else (AC28). Known limit (S-10): a change after the first
unrecorded step is not detectable; the version rule of §4.2 is the guard.

**Codec.** Every live result (envelope summary, read value, decision, answer) passes through `canonical_json` and
`canonical.loads` before the block sees it, and quantity objects are rebuilt as `Quantity` in both paths, so a live
and a replayed value are equal (AC11).

#### 4.5.3 In-flight steps and unknown outcomes

A step is in flight when its `step_started` has no `step_completed`, `step_failed` or `step_reconciled` for that
attempt. At resume, and at once when a write step's call raises, returns `TIMEOUT_UNKNOWN_OUTCOME` or returns
`HOST_WEDGED` (invariant 6):

| Step | Rule |
|---|---|
| Write (`effect: write`, including save, analysis, design, promote) | Reconciled before anything else on its host: `ToolPort.reconcile(tool, args, op_id)`. `applied` → `step_reconciled` with the result, the model is marked dirty (invariant 1), and replay returns the result. `not_applied` → `step_reconciled`; the step runs again as attempt + 1 with a new `op_id` (ADR-0030; OQ-Q16, §11 Q6). `partial`, `unknown`, no reconciler, or a reconciler error → `NeedsReconciliation`: `run_escalated` and an engineer input request (`engine.in_flight`) with choices `applied`, `not_applied`, `abandon`. For `applied` the engine asks `ToolPort.read_back` for the result; if the adapter has none, the step completes with an empty summary and `decided_by: engineer:<name>`. The write is never run again until its outcome is known |
| Read, calc, decision (tiers other than the engineer) | `step_rerun`, then the step runs again with the same attempt (no side effect) |
| Approval, ask, engineer-tier decision | Presented again with the same request id (AC36) |
| Block, parallel, attempts | Scopes, not steps: their children are handled one by one |

#### 4.5.4 Host-state check before live execution

For every model the run wrote to, the engine reads `HostPort.model_state(model_key, instance_id)` on its bound instance (identity, revision,
fingerprint, file hash) as housekeeping steps `@resume<n>.model_state.<model_key>` and compares it with the model's
last `model_saved`, or, when a write on it was reconciled `applied` after that save (§4.5.1 step 7), with the revision
and fingerprint of the reconciled result's `provenance.host`. A model with `HostModelState.loaded` false (a lost model,
§4.5.1 step 6) is a mismatch with reason `model_not_loaded`. A reopened model is compared with its last `model_saved`
only, never with a reconciled result, and any write on it after that save (completed, reconciled or in flight) is a
mismatch with reason `model_reopened`: the reopened file cannot hold it. On a mismatch the run stops (`run_escalated`, reason `host_state_mismatch`) with an engineer input
request (`engine.host_state`) offering three choices (11 §5):

- `accept`: the differences are engineer changes. The engine saves the model (`model_saved`, role `baseline`) and
  continues; the workflow shows and records the differences itself (18 step 4). Not offered for a lost model (there is
  no state to accept) or a `model_reopened` mismatch (the journal would hold writes the model lacks) **[added]**.
- `restore`: `HostPort.restore(model_key, saved)` reopens the last saved working copy and returns the instance that
  holds it (the bound instance if it still runs, else one spec 0002 starts, which is journaled as `host_started`); the
  engine journals `model_bound` (reason `restored`) for it before any other call on the model; `run_resumed` records
  `restored_to_seq` (the `seq` of that `model_saved`), and the replay index ignores every step event after it, so those
  steps run live again as new attempts (`step_rerun`, reason `restored`) with new `op_id`s. Offered only when no other
  model was written after that `seq` **[added: otherwise a restore would repeat writes on the other model]**. After the
  restore and before any live step on that model, the engine reads units again against the new binding
  (`@resume<n>.units_restored.<model_key>`, invariant 9); a mismatch or `loaded` false stops the run (`units_mismatch`). A write in flight on the model started
  after the restored `model_saved` (no save follows an in-flight write), so the cut covers it: it gets `step_rerun`
  (reason `restored`) and runs as a new attempt; it is never reconciled against the restored model.
- `abandon`: `run_failed` (reason `abandoned`).

For a lost or reopened model on which `restore` is not offered, only `abandon` is offered; the run stays escalated.
An engineer who reopens the model's last saved file in the host and resumes gets the binding of §4.5.1 step 6 and the
comparison above: with no write after that save the run continues (Q15, AC64).

In `work_on_copy` the working copy is saved after every write step (`p~post.save.<model_key>`, 11 §5), so a host
crash loses at most one step.

### 4.6 Enforced invariants (11 §6)

The engine tracks, per model key: dirty flag, current revision (from the last result's `provenance.host` or
`model_state`), last `model_saved`, and approval bindings; per host key: lease, session epoch, reconciliation pending.
Inserted steps are journaled like other steps and emit `check_enforced`. No ctx parameter, block attribute or setting
turns an invariant off (AC37); in every case the block's call raises before any port call when the invariant fails.

| # | Where and how | Raises | Tests |
|---|---|---|---|
| 1 Check after write (P7) | `_invariants`: a successful or reconciled-`applied` write marks the model dirty; before a read on that model, any `calc`, `decide`, `approve` and the block's return, the step `p~pre.check_model.<model>` (or `~end`) calls `HostPort.check_model` (for Sasaah servers, the adapter's read-back check, spec 0002); a clean result clears the flag | `ModelIntegrityError` (`StepError`, so the block may route it to a decision or escalate) | AC37, AC47 |
| 2 References for engineering quantities (P2) | `_invariants`, before the port call: every argument at a path in `ToolInfo.engineering_params` or `CalcInfo.engineering_params` must be a `Ref` or a result; a number, a quantity object or a `Quantity` is refused | `ContractError` `INVALID_ARGUMENT` with `field` (contract §5 step 2) | AC38 |
| 3 No stale inputs | `_invariants`: every reference to `calc`, `decide`, `approve` is resolved with `eng_contract.refs.resolve_ref` and a `current_revision` that knows every model attached in the run (contract Q4) | `ContractError` `REF_STALE` | AC39 |
| 4 Decisions cannot produce numbers (P10) | `_decide`: options must be a `StrEnum` subclass or a sequence of `Ref`; the answer must be a member value or an index into the sequence; the block receives the member or the `Ref` | `BlockRuleViolation` (options), `DecisionInvalid` (answer) | AC40 |
| 5 Never assume inputs (P8) | `_hostsafety`, in `start`: `DesignBasis.missing(workflow.required_basis)` (contract §4.10.2) must be empty | `RunRefused` (`BASIS_INCOMPLETE`, fields listed); no run folder | AC41 |
| 6 Honest outcomes (P9) | `_hostsafety`: `TIMEOUT_UNKNOWN_OUTCOME` or `HOST_WEDGED` sets "reconciliation pending" on the host; every later step on that host waits until §4.5.3 has run; other hosts continue | `NeedsReconciliation` when unresolved | AC33, AC42 |
| 7 Save before analysis | `_invariants`: before a tool with `ToolInfo.action` `analysis` or `design`, the step `p~pre.save.<model>` calls `HostPort.save` and journals `model_saved` (role `pre_analysis`) | `StepError` of the save | AC43, AC47 |
| 8 Server builds | `_hostsafety`, in `start` before `run_started`, and at each resume as step 4 of §4.5.1 (before any lease, reconciliation or host-state read): `HostPort.preflight(workflow.min_server_builds)`; any `ServerCheck.ok` false stops the run before any write | `RunRefused` (`SERVER_CHECK_FAILED`) | AC44 |
| 9 Host units | `_hostsafety`, `HostPort.read_units(model_key, instance_id)` against the model's bound instance (§4.8 "Instance binding"): (a) before the first step of the run addressed to a model, as `p~pre.units.<model_key>` (replayed), right after its `first_use` binding; (b) at each resume, for every model key the journal addressed, as `@resume<n>.units.<model_key>`, before reconciliation (§4.5.1 step 6), where a model not loaded is not a mismatch but goes to the host-state check (§4.5.4) and units are read again after a `restore`; (c) before the next step on a host when, within this engine process, `HostPort.session_epoch(host)` changed or the engine observed a timeout, `TIMEOUT_UNKNOWN_OUTCOME` or `HOST_WEDGED` on that host, as `p~host.units.<model_key>`. The epoch is compared only within one engine process, so it needs no journal baseline; a new process always reads units by (b). A mismatch stops the run before any reconciliation, until the units are restored | `ContractError` `PRECONDITION_FAILED` (`units_verified`), run escalated `units_mismatch` | AC45, AC47 |
| 10 One driver per host instance | `_hostsafety`: `HostPort.acquire(host_key)` before the first step on a host, and at each resume before reconciliation (§4.5.1 step 5). After every live step on a host, `HostPort.started_instances(host_key)` lists the instances this engine's servers started; each one not journaled yet is appended as `host_started` (FULL) before the next step. Run end is only after `run_completed` or `run_failed` is appended (never a pause, an escalation, a divergence or a refusal); then `HostPort.close_started(host_key, instances)` receives the instances read from the journal's `host_started` events, so a resumed engine closes what an earlier process started; spec 0002 closes an instance only if its process id and start time still match. A resume of a terminal run repeats `close_started` (idempotent) | `ContractError` `HOST_LOCKED` | AC46 |

### 4.7 Permission modes (11 §7, ADR-0018)

`PermissionMode` = `work_on_copy` (default), `approve_each_write`, `autonomous_logged`, chosen per run.

- **`work_on_copy`.** Before the first write to an existing model, the inserted step `p~pre.working_copy.<model>` calls
  `HostPort.working_copy(model_key, run_dir/"copies")`, which returns the copy's model key; `model_saved` (role
  `working_copy`) records the copy's state and `origin_sha256` (the original's file hash). Every later step addressed to
  the model goes to the copy. New models are created in the run folder by the workflow's tools.
- **`approve_each_write`.** Before each write, the inserted step `p~pre.approve` presents `ToolPort.preview(tool,
  args)` as a `CHANGE_SET` approval; a rejection raises `ApprovalRejected` (a `StepError`) and the write is not called.
- **`autonomous_logged`.** Writes run directly; a `ctx.approve` of kind `INFO` or `CHANGE_SET` is resolved by the mode
  (`approval_resolved`, `by: "mode:autonomous_logged"`) **[added: 11 §3 says approval behavior depends on the mode]**.
- **Always ask, in every mode.** Approval kinds `PROMOTION` and `SIGN_OFF`; tools with `ToolInfo.action` `delete`; a
  save whose target is an original (`ToolInfo.overwrites_original(args)`); and tools in `WorkflowDef.always_ask`. The
  engine inserts an approval before such a step unless the block passed `under=` an approval of the same request.
- **Promotion** (`ctx.promote`, always an approval of kind `PROMOTION`):
  - Before anything else, `_promote` checks the `approval` argument: it must be of kind `PROMOTION`, approved, bound
    to this model, and unused by an earlier promotion; and the working copy's current `HostPort.model_state` (revision,
    fingerprint, file hash) must equal the binding taken when the approval was shown (§4.9). Otherwise `ApprovalVoid`
    (a mismatch, for example an engineer edit to the copy while the run waited at the approval page) or
    `BlockRuleViolation` (wrong kind, not approved, other model, reused), and nothing is copied. The binding of a
    `PROMOTION` approval also records `file_sha256` of every model in the preview.
  - `Promotion.FILE_COPY` (the edit cycle and new models): `_promote` checks that the original's current file hash
    equals the working copy's `origin_sha256` (else `ContractError` `CONFLICT`, nothing copied); copies the original's
    files to `runs/<run_id>/backups/` and verifies their hashes; copies the accepted revision's files
    (`HostPort.model_files`) into the target folder under temporary names, verifies their hashes, and replaces the
    targets; journals `model_saved` (role `promoted`). File operations go through an internal `FileOps` port with a
    fake (AC52). Closing the files in the host before copying is the adapter's job (spec 0002).
  - `Promotion.REPLAY_WRITES` (11 §7 for existing models in general): **not implemented** in this version;
    `NotImplementedGap` (`NOT_IMPLEMENTED`, gap E-G1, AC53).

### 4.8 Ports

Every port is a `typing.Protocol` in `eng_harness.ports`, with an in-memory fake in `tests/fakes/` (test doubles,
lead decision D-5) and a shared conformance test (AC57). All results from host tools are contract `Envelope`s.

| Port | Methods | Implemented by |
|---|---|---|
| `ToolPort` | `describe(tool) -> ToolInfo` (refuses a tool outside the allowlist with `INVALID_ARGUMENT`); `call(tool, args, *, op_id, model) -> Envelope`; `supports_reconcile(tool) -> bool`; `reconcile(tool, args, op_id) -> Reconciliation`; `read_back(tool, args) -> Envelope \| None`; `preview(tool, args) -> Preview` | Spec 0002 (adapters) |
| `HostPort` | `preflight(min_builds) -> list[ServerCheck]`; `acquire(host_key) -> HostLease`; `release(lease)`; `session_epoch(host_key) -> int`; `locate(model_key) -> HostInstance \| None`; `model_state(model_key, instance_id) -> HostModelState`; `check_model(model_key) -> Envelope` (`issues.model_check/1`); `save(model_key, role) -> SavedModel`; `read_units(model_key, instance_id) -> UnitsState`; `working_copy(model_key, folder) -> ModelKey`; `restore(model_key, saved) -> HostInstance`; `model_files(model_key) -> tuple[Path, ...]`; `started_instances(host_key) -> list[HostInstance]`; `close_started(host_key, instances: Sequence[HostInstance]) -> None` | Spec 0002 (server processes, Job Objects, host-instance locks, process start times) |
| `CalcPort` | `describe(calc_id) -> CalcInfo` (`id`, `version`, `content_sha256`, `status`, `engineering_params`); `run(calc_id, args) -> Envelope` | Spec 0003 and code packs |
| `BasisPort` | `load(basis_ref) -> LoadedBasis` (`result_id`, `basis`: the `basis.design_basis/1` payload model) | Spec 0004 |
| `DecisionPort` | `decide(request) -> DecisionAnswer \| PendingAnswer`; `decide_many(requests) -> list[DecisionAnswer \| PendingAnswer]` | Spec 0005 |
| `ApprovalPort` | `present(request: ApprovalRequest) -> None`; `answer(request_id, *, wait: bool) -> ApprovalAnswer \| None` (`None`: no answer; the engine pauses) | Spec 0006 |
| `InputPort` | `present(request: InputRequest) -> None`; `answer(request_id, *, wait: bool) -> InputAnswer \| None` | Spec 0006 |
| `ProgressSink` | `emit(event: Event) -> None` (synchronous, must not block) | Spec 0006 |
| `RunControlPort` | `stop_requested(run_id) -> bool` (checked between steps; true → `run_paused`, reason `stop_requested`) | Spec 0006 |

Port data types (frozen models): `ToolInfo` (`name`, `effect` read or write, `action` (`plain`, `open`, `save`,
`analysis`, `design`, `delete`, `unlock`), `host_key`, `model_param` (argument naming the model, or `None`),
`engineering_params` (field paths), `overwrites_original(args) -> bool` is a method on the adapter's `ToolInfo`
subclass); `Reconciliation` (`outcome` `applied`, `not_applied`, `partial`, `unknown`; `result: Envelope | None`;
`missing: list[str]`; `evidence: list[Ref]`); `ServerCheck` (`server`, `build`, `min_build`, `fingerprint`,
`expected_fingerprint`, `ok`, `reason`); `HostModelState` (`loaded`, `model_id`, `revision`, `fingerprint`,
`file_sha256`; the last four `None` when `loaded` is false);
`SavedModel` (`model_id`, `revision`, `fingerprint`, `file_sha256`, `file_name`); `UnitsState` (`loaded`, `ok`, `present`,
`expected`; `ok` true and `present` `None` when `loaded` is false); `HostLease`; `HostInstance` (`instance_id`, `pid`, `process_started_at`, `program`); `ApprovalRequest`, `ApprovalAnswer`, `InputRequest`, `InputAnswer` (§4.9).

**Instance binding.** Each model key is bound to one host instance, recorded as `model_bound` (FULL); the reference
instance of a model is the `instance_id` of its last `model_bound`. The engine journals a binding (a) with reason
`first_use` before the first step of the run addressed to the model, from `HostPort.locate(model_key)`, whether or not
the engine started that instance (for a tool with action `open` or for `working_copy`, after that step instead, since
the model is not open before it; `locate` returning `None` before any other step refuses the step with `ContractError`
`PRECONDITION_FAILED`, condition `model_loaded`); (b) with reason `restored` after `HostPort.restore` (§4.5.4); (c)
with reason `reopened` at resume (§4.5.1 step 6). `HostPort.read_units` and `HostPort.model_state` take the bound
`instance_id` and never raise when that instance does not have the model open or is not running: they return
`loaded: false` (spec 0002 starts no host program to answer them). A server that cannot be reached fails the preflight (invariant 8).

`EnginePorts` bundles the ports; `Engine(workspace, registry, ports, store, settings, clock, ids)` takes everything
explicitly (contract `ResultStore`, `Clock`, `IdSource`).

### 4.9 Approvals

- `ctx.approve(title, preview, kind)`: `request_id = "apr_" + sha256(run_id + "\n" + path).hexdigest()[:32]`, stable
  across replay. `Preview` (`items: list[PreviewItem]` with unique `id`, `label`, `refs`; `diff_ref: Ref | None`;
  `models: list[ModelHandle]`) is stored as `harness.approval_preview/1`; `shown_sha256` is its `payload_sha256`.
  `binding` is `[{model_key, model_id, revision, fingerprint, file_sha256}]` of every model in `preview.models`, read from HostPort
  when the request is made (after invariant 1 has checked them).
- An answer is accepted only if its `request_id` names an open approval request of this run, its `shown_sha256` equals
  the request's, and the request has no `approval_resolved` yet (used once). Otherwise it is refused and the request is
  presented again (AC54).
- `Approval` (`request_id`, `approved`, `rejected_items`, `reason`, `accepts(item_id) -> bool`). A rejected approval
  returns `approved: false` to the block (the block decides); `ApprovalRejected` is raised only for the engine's own
  inserted approvals.
- **Re-check just before the write.** A write passed `under=approval` re-reads `HostPort.model_state` for its model
  before the first write under that approval and compares it with the binding; each later write under it must find the
  revision its predecessor under the same approval produced. A mismatch raises `ApprovalVoid` (a `StepError`, so the
  edit cycle can return to its step 3, 18 §4) before the write (AC55).
- **Expiry and items.** An approval authorizes writes until the first `check_model` on a bound model or the return of
  the scope that requested it; later use is `BlockRuleViolation`. A write passed `item=` of a rejected item is
  `BlockRuleViolation` (AC56).
- **Pause.** `answer(wait=...)` returning `None` raises `Pause` (`run_paused`, reason `awaiting_approval`); the process
  returns `RunOutcome(status=PAUSED)` and a later `resume` replays to the request and asks the port again.
- `kind` = `CHANGE_SET`, `PROMOTION`, `SIGN_OFF` (P11; an approved sign-off also appends `signed_off`), `INFO`.

### 4.10 Concurrency, resources and performance (11 §8, §10)

- `EngineSettings` (frozen; values are software settings, not engineering values): `max_parallel_children` (default
  8), `max_concurrent_hosts` (default 1), `max_concurrent_decisions` (default 4), `max_attempts_cap` (default 10),
  `step_retry_limit` (default 2). Spec 0006 reads them from `harness.toml`.
- `_resources` holds one semaphore per limit and one `asyncio.Lock` per host key, so steps on one host are serialized
  in the engine as well as by the server (11 §8). Semaphores are taken in argument order inside `ctx.parallel`.
- ProgressSink: `emit` is called synchronously after each commit, in `seq` order, before the next step starts; a sink
  that raises is detached and the failure logged (progress is derived from the journal, which stays complete) (AC58).
  The 200 ms display target of 11 §10 is measured by spec 0006.
- Performance: AC60 is a test in the normal suite (1,000 steps, about one second) and in the Windows CI job; it prints
  p50, p95, p99 and the replay time of the same run. The rule-decision target (under 1 ms) belongs to spec 0005.

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `RunRequest.workflow` | `str` | — | a registered workflow name | no | CLI (0006) |
| `RunRequest.input` | JSON object | — | the workflow's input model | values may be `$ref` | CLI |
| `RunRequest.basis_ref` | `RefString` | — | a `basis.design_basis/1` result | yes | 0004 |
| `RunRequest.mode` | `PermissionMode` | — | enum | no | CLI, default from settings |
| `EngineSettings.*` | `int` | — | ≥ 1 | no | `harness.toml` (0006) |
| `RunOutcome` | `run_id`, `status` (`COMPLETED`, `PAUSED`, `NEEDS_ENGINEER`, `FAILED`), `output` (the output model or `None`), `pending` (request ids), `escalation` (`reason`, `detail`) | — | — | — | engine |

## 6. Errors

`HarnessCode` (`StrEnum`) names engine conditions that are not contract error codes; contract errors stay
`ContractError` (contract §4.2.3). Every harness exception carries `code`, `message` and optional `evidence` (refs).

| Exception | Base | Code | Condition |
|---|---|---|---|
| `Pause` | `EngineStop` | `PAUSED` | Awaiting approval, input or stop request |
| `ReplayDivergence` | `EngineStop` | `REPLAY_DIVERGENCE` | §4.5.2 |
| `NeedsReconciliation` | `EngineStop` | `NEEDS_RECONCILIATION` | §4.5.3 |
| `HostStateMismatch` | `EngineStop` | `HOST_STATE_MISMATCH` | §4.5.4 |
| `Escalation` | `EngineStop` | `NEEDS_ENGINEER` | `ctx.escalate`, attempts exhausted, units mismatch, unhandled error |
| `BlockRuleViolation` | `EngineStop` | `BLOCK_RULE_VIOLATION` | §4.3, §4.9 |
| `RunRefused` | `Exception` | `BASIS_INCOMPLETE`, `SERVER_CHECK_FAILED` | Before `run_started`, or at resume before any live step |
| `RunLocked` | `Exception` | `RUN_LOCKED` | §4.4.4 |
| `JournalIntegrityError` | `Exception` | `JOURNAL_INTEGRITY` | §4.4.1 |
| `ToolFailed` | `StepError` | the contract `ErrorDetail.code` | Failure envelope |
| `ModelIntegrityError` | `StepError` | `MODEL_INTEGRITY` | Invariant 1 |
| `DecisionInvalid` | `StepError` | `DECISION_INVALID` | Invariant 4 |
| `ApprovalRejected` | `StepError` | `APPROVAL_REJECTED` | §4.7 inserted approvals |
| `ApprovalVoid` | `StepError` | `APPROVAL_VOID` | §4.9 |
| `NotImplementedGap` | `StepError` | `NOT_IMPLEMENTED` | Gap E-G1 |
| `ContractError` (from eng-contract) | `Exception` | `INVALID_ARGUMENT`, `REF_*`, `CONFLICT`, `PRECONDITION_FAILED`, `HOST_LOCKED`, `INTERNAL` | §4.6, §4.7; engine bugs on its own data are `INTERNAL` |

`EngineStop` derives from `BaseException`; `StepError` from `Exception`. A `StepError` that leaves the root block is
journaled `step_failed` then `run_escalated` (`unhandled_error`).

## 7. Non-goals

- Server processes, Job Objects, host-instance locks, process start times, adapters and allowlists (spec 0002); calcs
  (0003); templates and the basis (0004); the decision cascade (0005); command line, settings file, progress display,
  approval page, run report (0006); the edit-cycle workflow (0007).
- Promotion by replaying write steps (gap E-G1).
- Snapshotting long journals: replay of 10,000 steps takes about 0.13 s (S-10).
- Several engines on one run, or a journal shared between machines.
- Power-loss testing (S-10 open risk).
- Any engineering value or check; the engine computes none.

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A write repeated after a crash applies twice on a Sasaah server without idempotency (ADR-0024) | R1 (model write) | In-flight rule (§4.5.3), FULL durability of a write's start, crash matrix (AC30); reconciliation by model reads needs a live test (S-10 open risk, local testing) |
| A check after write is skipped | R1 | Engine-inserted steps, no opt-out, property test (AC37) |
| A changed block resumes an old run silently (divergence limit) | R1 | Version rule and lock file (§4.2, AC4, AC29) |
| An approval applies to a model that changed since it was shown | R1 | Binding and re-check (§4.9, AC55) |
| Block code reads a clock or the disk | R1 | Runtime guard, rules test, gate lint (§4.3.4) |
| Journal schema or reader API changes break the page and the report | R2 | `schema_version` in `meta`; payload models; reader is the only access path |
| fsync on the owner's disk (antivirus, synchronized folder) slows steps | R2 | Benchmark on Windows; workspace not in a synchronized folder (contract §4.5.1 refuses one) |
| Audit hook is process-wide and cannot be removed | R2 | Guard active only while the context variable is set; tests of the engine's own I/O under the hook (AC18) |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1 to AC18, AC20 to AC26, AC40, AC52 to AC56, AC58, AC59, AC61 | Unit | `tests/unit/` |
| AC19 | Unit (source rules) | `tests/rules/` |
| AC4 (lock), AC57 | Contract | `tests/contract/` |
| AC10, AC33, AC37 to AC39, AC41 to AC46, AC48 to AC51 | Fake-host workflow (real engine, fake ports, real SQLite) | `tests/workflow/` |
| AC27 to AC32, AC34 to AC36, AC46 (resume case), AC47, AC62 to AC64 | Replay (process/05 §1) | `tests/replay/` |
| AC37 (generated programs) | Property (Hypothesis, CI profile `derandomize=True`) | `tests/property/` |
| AC60 | Performance | `tests/perf/` |
| AC23 (Windows lock) | Unit, marker `windows` | `tests/windows/` |

Every workflow of later specs adds its own fake-host workflow test and replay test (process/05 §2). There are no golden
engineering tests in this spec: the engine computes no engineering value. Tests use the contract's `FixedClock` and
`SeededIdSource`; no network, no host program. Coverage floors 85% line and 75% branch (process/05 §2); mutation score
at least 80% on the R1 modules listed in the plan.

## 10. Version impact

New package; `eng-harness` 0.1.0 when phase 1 is complete. The journal `schema_version` is 1; a change to it or to an
event payload is a new schema version that the reader must still read (its changelog entry states the impact).

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| E-G1 | Promotion by replaying journaled write steps on the original (11 §7, ADR-0018) is not implemented; the edit cycle uses file copy | Owner | Implement when a workflow needs it (Revit, workshared models), with its own spec; until then `NOT_IMPLEMENTED` (AC53) |
| Q1 | Where `ctx.attempts` limits come from: 11 §3 writes `ctx.attempts(max)`, but a literal is refused by FB005 (gate Q5, Q12) | Owner | A `BasisCount` read from the design basis (`ctx.basis.count("attempts.<name>")`), shown and confirmed like any basis value, capped by `max_attempts_cap` |
| Q2 | OQ-Q17: block version and code hash for unfinished runs | Owner | Record both; a version change stops, a hash change with the same version warns; the lock-file test makes the bump mandatory (§4.2) |
| Q3 | The `restore` choice of the host-state check when several models were written | Owner | Offer it only when no other model was written after the restored save (§4.5.4); revisit for multi-model workflows |
| Q4 | `autonomous_logged` resolves `INFO` and `CHANGE_SET` approvals by mode | Owner | Yes; the always-ask list still asks (§4.7) |
| Q5 | The FULL durability set adds `model_saved`, `input_provided`, `run_failed`, `signed_off` to S-10's | Owner | Accept; read the Windows numbers before fixing the policy (S-10 open risk) |
| Q6 | OQ-Q16: after `not_applied`, retry with a new `op_id` or the old one | Owner | New `op_id` from attempt + 1 (11 §3); for a server that deduplicates by `op_id`, `not_applied` was confirmed, so a new id cannot double-apply |
| Q7 | Engine conditions without a contract code (basis incomplete, server check, divergence, reconciliation) | Owner | Harness codes (`HarnessCode`) now; extend 04 §8.1 preconditions by ADR only if a server needs them |
| Q8 | 11 §3 shows `ctx.tool(name, **args)`; this spec uses an explicit `args` mapping | Owner | Amend 11 §3 when ADR-0030 is accepted |
| Q9 | 11 §3 rule 5 "loops only through `ctx.attempts`": `for` over a finite typed collection | Owner | Allow (one call per object is needed on the Sasaah CSI server, S12-G4); forbid `while` |
| Q10 | The single-writer journal with an answer inbox replaces S-10's page-writes-journal | Owner | Accept (§4.4.1) |
| Q11 | Saving the working copy after every write step (11 §5) may cost seconds per step on ETABS | Owner | Keep for safety; measure in the local test (S-02) and revisit with data |
| Q12 | A `host_started` event (not in 11 §5) journals the host instances a run started, so a resumed engine can close them (invariant 10) | Owner | Accept with ADR-0030 (decision 8) |
| Q13 | Resume order (§4.5.1): preflight, leases and units before reconciliation; units always read at resume in a new engine process | Owner | Accept with ADR-0030 (decision 4); amend 11 §5 when it is accepted |
| Q14 | Sibling `ctx.parallel` children that touch the same model with a write are refused (`BlockRuleViolation`) | Owner | Accept; such a block has a race whatever the engine does |
| Q15 | After a host crash the model is not loaded; the in-flight write on it cannot be reconciled by reading the host | Owner | Treat it as a host-state mismatch (`model_not_loaded`): offer `restore` (re-runs the steps after the save, including the in-flight write) or `abandon`, never `accept`; never reconcile against an empty or new instance; a model the engineer reopened is bound to its new instance and continues only if no write follows its last save (§4.5.1, §4.5.4, AC64) |
| Q16 | A `model_bound` event (not in 11 §5) binds each model to one host instance, including instances the engineer opened, and moves after a restore or a reopen | Owner | Accept with ADR-0030 (decision 4); spec 0002 defines how `locate` identifies the instance holding a model file |
