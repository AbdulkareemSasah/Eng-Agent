---
id: spec-0007-model-edit-cycle
issue: "B-066"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2]
---

# Spec 0007: eng-harness model edit cycle workflow (`model_edit_cycle`)

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-04

This spec builds the workflow of [workflow spec](../workflows/model-edit-cycle.md) ("WS §n") as a block. It implements
[18](../../../../design/docs/architecture/18-first-slice-dxf-to-etabs.md) ("18 §n") as rewritten by
[ADR-0025](../../../../design/docs/adr/0025-first-workflow-edit-cycle.md), with the permission modes of
[ADR-0018](../../../../design/docs/adr/0018-permission-modes.md), the project lane of
[ADR-0026](../../../../design/docs/adr/0026-project-lane-for-tools.md) and the interface of
[ADR-0027](../../../../design/docs/adr/0027-phase-1-interface.md). It uses, and does not repeat: engine
[spec 0001](0001-engine.md) ("engine §n"), servers and adapters [0002](0002-servers-and-adapters.md), calcs
[0003](0003-calcs.md), templates and basis [0004](0004-templates-and-basis.md), decisions [0005](0005-decisions.md),
command line, page and report [0006](0006-cli-progress-pages-report.md), and the contract
[eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract §n"). Tool facts come
from [spike S-12](../../../../spikes/S-12-sasaah-tool-inventory/REPORT.md) and replay facts from
[spike S-10](../../../../spikes/S-10-replay/REPORT.md). Items marked **[added]** are not in the architecture and are
listed in §11.

## 1. Problem

The edit cycle is where the owner's time goes: 342 agent minutes and 500 engineer minutes in one reviewed task, against
about 9 minutes for the first model from DXF, with design runs failing on `model_locked`, analysis timeouts, 45
"I ran it" messages and manual edits that an agent later lost (ADR-0025, Sasaah baseline `REPORT.md` §3 and §5).
Specs 0001 to 0006 provide the parts; this spec puts them together into the one workflow that proves the
architecture, and defines what only this workflow knows: the change-set model, the order of steps and checks, the
decision points and rules, the engineer turn, the field list of the design basis, and the measurements for
benchmark B-1.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| Engine, adapters, calcs, basis, decisions, page and report (specs 0001 to 0006) | Every step of 18 §4 maps to a ctx call or an engine-inserted step | Used; this spec adds a block, four calcs, decision points and rules, kinds, and one adapter read tool |
| Sasaah `csi_*` tools (S-12 §1, §2) | Typed tools for four of the six edit kinds; one call per object; synchronous analysis and design | Used through the CSI adapter (spec 0002 §4.6) |
| Sasaah `tools/agent-loop/pairs/compare.py` (baseline ب2) | Geometry comparison with a tolerance | Not copied (A12); the difference report and placement comparison of spec 0003 cover it |
| Sasaah `csi_db_tables_apply` for bulk or seismic edits (baseline ج4) | Fast, but an escape hatch that corrupted a seismic table in the sessions | Never used; excluded by every allowlist (spec 0002 §4.5.1) |
| Sasaah Agent's exported tool manifest (OQ-Q5) | Not available here | The S-12 inventory stands in until the local run |

No runtime dependency is added.

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Fake-host workflow test" runs the real engine and the real CSI
adapter against the synthetic CSI fake server process (spec 0002 §4.8.3, lead decision D-5) with a real journal and
store in a temporary workspace, and the page ports replaced by scripted answer ports (spec 0006 fakes). Golden data of
the calcs lives under `tests/data/golden/edit_cycle/`, each case with a `source` naming the section of this spec that
defines its method; values are synthetic and say so.

### 3.1 Definition and code rules

- AC1. Given the workflow module, then `model_edit_cycle` is a `WorkflowDef` (version 1) whose `basis_fields` are
  exactly §4.8, whose `required_basis` equals their required paths, whose `min_server_builds` names the CSI adapter's
  pinned build, whose `always_ask` holds `csi_unlock_model`, and whose entries are in `blocks.lock.json`. Test:
  `tests/unit/edit_cycle/test_definition.py::test_workflow_definition`.
- AC2. Given the workflow, rule and point modules, then they import only what engine §4.1.2 allows, hold no numeric
  literal (only integer indexes and `len` comparisons, OQ-Q11), no `while` and no I/O. Test:
  `tests/rules/test_edit_cycle_modules.py::test_modules_follow_block_rules`.

- AC33. Given the engine amendments of §11 (Q2, Q3, Q5, spec 0004 Q7), then: a workflow with `copy_on_open` gets its
  working copy right after the open step in every mode; a tool step with action `save` journals `model_saved` (role
  `revision` when `as_new_revision`); an always-ask step is not satisfied by an approval resolved `mode:*`; and
  `required_basis` is derived from `basis_fields`. Tests:
  `tests/unit/test_engine_edit_cycle_amendments.py::test_copy_on_open_every_mode`, `::test_tool_save_journals_revision`,
  `::test_mode_resolved_approval_not_always_ask`, `::test_required_basis_from_fields`; and a save passed `under=` an
  approval is re-checked against the binding like a write and its result is the expected state of the next write under
  that approval, as is each engine `p~post.save`, and a save to a new file gets no `approve_each_write` preview (Q3).
  Tests: `::test_save_under_approval_keeps_chain`, `::test_revision_save_no_write_preview`. Amendment B-415: the cases
  each test checks are engine spec 0001 §3.9 rules EC1 to EC6, which add no engine criterion; this criterion covers
  them.

### 3.2 Change set (§4.3)

- AC3. Given an answers file with one item of each v1 edit kind, when validated as `ChangeSetDraft`, then it parses;
  given an unknown field, a quantity value without a unit, or a unit of the wrong dimension for the field, then
  `INVALID_ARGUMENT` naming the field; the kinds of §4.2 validate their fixtures. Tests:
  `tests/unit/edit_cycle/test_change_set.py::test_model_parses_and_refuses`,
  `tests/contract/test_edit_cycle_kinds.py::test_fixtures`.
- AC4. Given a change set and a model state, when `harness.change_set_check` runs, then selections resolve to sorted
  explicit names, and an unknown frame, area, joint, section, material or pattern, two items on the same target and
  property, or an empty selection is an `error` issue and the status is `FAIL`. Test:
  `tests/golden/edit_cycle/test_change_set_check.py::test_golden_cases` (cases `check-resolve-*`, `check-unknown-*`,
  `check-duplicate-*`).
- AC5. Given a value outside the basis bounds of its quantity kind (§4.8 `bounds.*`), including a thickness entered
  as 200 where 0.2 is in the bounds' unit scale (baseline د6), or a basis path that is absent or unconfirmed, then
  `OUT_OF_BOUNDS` or `SOURCE_MISSING` and `FAIL`. Test: same file, cases `check-bounds-*`, `check-source-*`.
- AC6. Given an item of a refused kind or variant of §4.3.2, then the issue `NOT_IMPLEMENTED` carries the gap id
  (H-G1, H-G2, H-G3, OQ-G8, CG-1) and the status is `FAIL`. Test:
  `tests/unit/edit_cycle/test_change_set.py::test_refused_kinds_name_their_gap`.
- AC7. Given a step 4 difference report in which the engineer changed a property that an item also sets, then the
  item gets the `warning` issue `CONFLICTS_WITH_ENGINEER_CHANGE` with both values, the status stays `PASS`, and the
  change-set preview marks the item. Test: golden cases `check-conflict-*`.
- AC8. Given a resolved change set, when `harness.expected_effects` runs, then it gives the effects of §4.4.2 per kind
  (a wall thickness is one `set` effect on `model.sections/1`; a combination replace is one `set` of the whole object;
  a delete is `remove`); a permutation of the items gives the same effects. Tests:
  `tests/golden/edit_cycle/test_expected_effects.py::test_golden_cases`,
  `tests/property/test_expected_effects.py::test_order_independent`.

### 3.3 The cycle (§4.5)

- AC9. Given a valid change set in `work_on_copy`, when one cycle runs with the engine's real approval binding and
  re-check (engine §4.9), then the journal holds the step sequence of §4.5 in order, with the engine-inserted working
  copy (step 2), the step 7 revision save passed `under=` the step 6 approval as its first write, check after write
  before step 9's reads, and the `pre_analysis` save before steps 11 and 12; no `ApprovalVoid` is raised and step 6 is
  asked once. Test: `tests/workflow/edit_cycle/test_cycle.py::test_one_cycle_step_sequence`.
- AC10. (A1) Given that cycle, then the read-back check is `PASS`, the difference report from the step 3 read to the
  step 9 read holds exactly the expected effects, and the fake's final model equals the baseline plus the effects.
  Test: `tests/workflow/edit_cycle/test_apply.py::test_model_holds_exactly_the_changes`.
- AC11. Given an approval with rejected items, then no write step names a rejected item; given a rejection of the
  whole set, then no write runs, steps 7 to 14 are skipped and the engineer turn follows. Test:
  `tests/workflow/edit_cycle/test_apply.py::test_rejected_items_not_written`.
- AC12. (A5) Given a fake hand edit between two cycles, then it appears in the next step 4 difference report, in the
  change-set preview's `diff_ref` and in the report's changes section, and the engineer's value stays when the
  conflicting item is rejected. Test: `tests/workflow/edit_cycle/test_engineer_changes.py::test_hand_edit_between_cycles`.
- AC13. (A5) Given a fake hand edit while the run waits at the change-set approval, then the first write raises
  `ApprovalVoid`, nothing is written under that approval, and the cycle returns to step 3 with the edit in the new
  differences. Test: `tests/workflow/edit_cycle/test_engineer_changes.py::test_edit_during_approval_wait`.
- AC14. (A5) Given a fake hand edit while the run is stopped, when it resumes and the engineer chooses `accept` at the
  host-state check, then the next step 4 shows the edit. Test:
  `tests/workflow/edit_cycle/test_engineer_changes.py::test_edit_while_stopped`.
- AC15. Given a locked model at step 8 of cycle 2, then the change-set preview lists the unlock item and
  `csi_unlock_model` runs `under=` that approval in `work_on_copy` and `approve_each_write`, while in
  `autonomous_logged` the engine asks separately (§4.7). Test:
  `tests/workflow/edit_cycle/test_cycle.py::test_unlock_under_change_set_approval` (needs spec 0002 plan T15, blocked
  on ADR-0031; until then the test expects the interim `HOST_LOCKED` stop).
- AC16. (A2) Given a fake timeout during analysis, and separately during design, then the step ends
  `TIMEOUT_UNKNOWN_OUTCOME`, the engine's `engine.in_flight` request opens, the outcome is not decided automatically
  (spec 0002 Q4, gap H-G7: unknown in v1, the engineer decides), and no further step on the host runs until it is
  answered; given a stale build pin, then the run is refused before any write. Tests:
  `tests/workflow/edit_cycle/test_long_runs.py::test_analysis_timeout_reconciles`, `::test_design_timeout_reconciles`,
  `::test_save_before_analysis_and_design`, `::test_stale_build_stops_before_any_write`.
- AC17. Given a read-back `FAIL` or `NEEDS_ENGINEER`, then the D-2 screen opens and analysis does not run;
  `restore_previous` opens a new working file copied from this cycle's step 7 snapshot `P[k]` (§4.5.1) and returns to
  step 3. Test: `tests/workflow/edit_cycle/test_apply.py::test_readback_failure_routes`.
- AC34. (A5) Given a fake hand edit between cycles 1 and 2, then a read-back `FAIL` in cycle 2 and the choice
  `restore_previous`, then the restored model holds the engineer's value, `P[2]` is unchanged on disk, and the next
  step 4 still shows the edit; given a snapshot whose file hash no longer equals its `model_saved`, then the restore
  ends `CONFLICT`, nothing is opened and the run escalates. Tests:
  `tests/workflow/edit_cycle/test_engineer_changes.py::test_restore_keeps_hand_edit`,
  `::test_restore_refuses_changed_snapshot`.
- AC18. Given each rule of §4.6, then a typical case and a boundary case (equality with its basis threshold where it
  has one) give the stated option, and states outside the rule give `None`. Test:
  `tests/unit/edit_cycle/test_rules.py::test_rules_typical_and_boundary`.
- AC19. Given the engineer turn, then it is a choice request with the three options of §4.6 even in
  `autonomous_logged`; `accept` goes to step 16, `more_edits` asks for a change set in the next cycle, and `hand_edit`
  starts the next cycle with an empty change set, no step 6 approval and a saved revision. Test:
  `tests/workflow/edit_cycle/test_turn.py::test_engineer_turn_branches`.
- AC20. Given more cycles than `attempts.cycles`, then the run escalates with `attempts_exhausted`. Test:
  `tests/workflow/edit_cycle/test_cycle.py::test_cycle_limit`.
- AC21. Given `accept`, then a `PROMOTION` approval precedes `ctx.promote(..., Promotion.FILE_COPY, ...)`, the backup
  exists, and the original holds the accepted revision; given an original changed since the copy, then `CONFLICT`,
  nothing is copied, and the run escalates. Test: `tests/workflow/edit_cycle/test_promotion.py::test_promote_and_conflict`.
- AC22. Given promotion, then a `SIGN_OFF` approval follows, `signed_off` is journaled, and `run_completed.draft` is
  true while any calc or rule used is draft. Test: `tests/workflow/edit_cycle/test_promotion.py::test_sign_off_and_draft`.
- AC23. Given the same scripted cycle in each permission mode, then the approvals journaled match the table of §4.7.
  Test: `tests/workflow/edit_cycle/test_modes.py::test_approvals_per_mode`.
- AC24. Given the change-set data request, then it carries `x-eng-input: data`; an answer that fails `ChangeSetDraft`
  is refused and presented again (engine AC61); an answer whose check is `FAIL` is asked again in the next attempt
  with the check result as evidence; exhausting `attempts.change_set` escalates. Test:
  `tests/workflow/edit_cycle/test_change_set_step.py::test_invalid_change_set_asked_again`.

### 3.4 Acceptance support (18 §5)

- AC25. (A3) Given any journal of this workflow, when `audit_value_sources` runs, then it reports every write step
  argument at an engineering parameter that is not a reference to `basis.design_basis/1` or `basis.engineer_input/1`;
  it reports nothing for every workflow test journal, reports a forged literal, and holds over generated change sets.
  Tests: `tests/unit/edit_cycle/test_audit.py::test_audit_finds_literal`,
  `tests/property/test_edit_cycle_sources.py::test_generated_change_sets_all_sourced`.
- AC26. (A7) Given a journal, when `count_prompts` runs, then it counts per cycle the engineer requests of §4.9 (a
  repeated step 6 approval, a re-asked change set and every engine request count; the first step 6 approval, the
  first change-set request, the engineer turn and the run-level steps 16 and 17 do not); every normal-path scenario of
  §4.9 (AC9 to AC12, AC15, AC19, AC21, AC22, with the fake returning no analysis messages) in `work_on_copy` has at
  most one per cycle; given the fake returning analysis messages (all `unclassified`, EC-G3), then D-3 reaches the
  engineer and is that cycle's one prompt; and the interruption, failure and escalation scenarios (AC13, AC14, AC16,
  AC17, AC20, AC24, AC34) are counted and reported but not bounded. Tests:
  `tests/unit/edit_cycle/test_prompts.py::test_prompt_counter`,
  `tests/workflow/edit_cycle/test_prompts.py::test_scenarios_within_one_prompt`,
  `::test_unclassified_messages_use_the_prompt`.
- AC35. (A3, A7 on real journals; B-354) Given the module entry point `python -m eng_harness.report` (run from the
  workspace root as `uv run --package eng-harness python -m eng_harness.report ...`, spec 0006 §4.1) with the
  subcommand `audit-sources RUN_DIR` or `count-prompts RUN_DIR` (and `--json`), then it opens the run folder read-only
  through `JournalReader` and the run's result store, calls `audit_value_sources` or `count_prompts` on it and prints
  the result (one line per finding with the step path, tool and argument; one line per cycle with its count and the
  counted requests by kind and title; `--json` one JSON object), data-derived text sanitized as in spec 0006 AC21; the
  exit code is 0 (`audit-sources` with no finding; `count-prompts` always, because the A7 bound depends on the path,
  §4.9), 1 (`audit-sources` with a finding), 2 (usage, not a run folder, or a run of another workflow), 5 (altered
  journal, naming the first bad `seq`) or 6 (no such folder), the numbers of spec 0006 §4.2.3; a run held by a live
  engine is read up to its last committed event and the output says "run in progress as of seq N"; the journal, store
  and folder bytes and modification times are unchanged; and `eng-harness --help` still lists exactly the six commands
  of spec 0006 AC1. Tests: `tests/unit/edit_cycle/test_acceptance_entry.py::test_audit_and_count_read_run_folder`,
  `::test_entry_is_read_only_and_exit_codes`.
- AC27. (A6) Given a two-cycle run in a worker process, when the engine is killed at every step and resumed with the
  same scripted answers, then each run ends with the same fake model, revision chain and outputs as the uninterrupted
  run, and no write is sent twice. Test: `tests/replay/edit_cycle/test_crash_matrix.py::test_every_step`.
- AC28. Given a recorded journal of the workflow, then it replays without divergence (process/05 §2). Test:
  `tests/replay/edit_cycle/test_replay.py::test_recorded_journal_replays`.
- AC29. (B-1) Given a fixture journal, when `edit_cycle_timings` runs, then it gives the measures of §4.9 and their sums
  equal the sums over the fixture events. Test: `tests/unit/edit_cycle/test_timings.py::test_cycle_and_turn_timings`.
- AC30. Given synthetic host design results and analysis messages, then `harness.host_design_verdicts` and
  `harness.analysis_summary` give the golden outputs of §4.4.3 and §4.4.4. Tests:
  `tests/golden/edit_cycle/test_design_verdicts.py::test_golden_cases`,
  `tests/golden/edit_cycle/test_analysis_summary.py::test_golden_cases`.
- AC31. Given the read tool of §4.10 against the fake, then it stores the read set and the name lists; a truncated list
  raises `LIMIT_EXCEEDED`; a read-back gap leaves its section out (`not_read` downstream). Given `as_new_revision`,
  then the open working file is saved in place, its files are copied to a new snapshot file in the run's copies folder,
  the host keeps the working file open, and an existing target is refused; given `csi_open_revision`, then the snapshot
  is copied to a new working file and opened, and the snapshot is unchanged; a snapshot whose hash differs from its
  `model_saved` is refused with `CONFLICT`. Tests: `tests/workflow/adapters/test_csi_read_state_tool.py::test_read_set`,
  `tests/workflow/adapters/test_csi_revisions.py::test_save_as_new_revision_and_open_revision`.
- AC32. Given the kinds of §4.2, then the report renders them through registered renderers with a source on every value
  cell, and adds the timings of §4.9. Test: `tests/unit/report/test_edit_cycle_renderers.py::test_renderers_and_sources`.

## 4. Design

### 4.1 Modules

| Module | Content | Risk floor |
|---|---|---|
| `src/eng_harness/workflows/model_edit_cycle/__init__.py` | `model_edit_cycle` (`WorkflowDef`), `basis_fields`, input and output models | block code |
| `src/eng_harness/workflows/model_edit_cycle/_cycle.py` | child blocks `edit_cycle_once`, `read_state`, `obtain_change_set`, `apply_change_set`, `run_and_summarize` | block code |
| `src/eng_harness/workflows/model_edit_cycle/_finish.py` | steps 16 and 17: promotion and sign-off (§4.5) | block code |
| `src/eng_harness/workflows/model_edit_cycle/_change_set.py` | `ChangeSetDraft` and the item models (§4.3) | block code |
| `src/eng_harness/workflows/model_edit_cycle/_points.py` | decision points and their state models (§4.6) | block code |
| `src/eng_harness/rules/edit_cycle.py` | the rules of §4.6 | R1 |
| `src/eng_harness/calcs/edit_cycle/` | the four calcs of §4.4 | R1 |
| `src/eng_harness/kinds/edit_cycle.py` | the kinds of §4.2 | R2 |
| `src/eng_harness/adapters/csi/_read_state_tool.py` | `csi_read_model_state` and `csi_read_analysis_messages` (§4.10) | R1 |
| `src/eng_harness/adapters/csi/_revisions.py` | `csi_open_revision` and `as_new_revision` (§4.10, §4.5.1) | R1 |
| `src/eng_harness/report/_edit_cycle.py` | renderers, `audit_value_sources`, `count_prompts`, `edit_cycle_timings` | report |
| `src/eng_harness/report/__main__.py` | the read-only entry point `python -m eng_harness.report` with `audit-sources` and `count-prompts` (AC35, B-354) | report |

### 4.2 Workflow definition, input, output, kinds

`model_edit_cycle` (version 1) with `basis_fields` (§4.8, the `WorkflowDef` member proposed by spec 0004 Q7
**[added]**), `min_server_builds = {"sasaah-csi-mcp": <the adapter's pinned build>}`, `always_ask =
("csi_unlock_model",)` (`csi_delete_load_combo` is always asked by its `delete` action, engine §4.7), and
`copy_on_open = True` (§4.5, Q2 **[added]**).

- Input `EditCycleInput`: `model` (the model file as the command line passes it, a `harness.file_input/1` reference,
  spec 0002 §4.7), `visible_host: bool` (default true: the engineer edits by hand in the instance the run launched,
  spec 0002 §4.6.1 step 2). No engineering value is part of the input.
- Output `EditCycleOutput`: `accepted_revision` (the `model_saved` identity, revision, fingerprint, file hash),
  `cycles` (count), `promoted` (model handle), `summaries` (references to the last `harness.design_summary/1` and
  `harness.analysis_summary/1`), `signed: bool`.
- Kinds (registered with `KindRegistry.extend` beside spec 0003's): `harness.change_set_check/1`,
  `harness.analysis_summary/1`, `harness.csi_name_lists/1` (§4.10). Host design results become `verdicts.set/1`
  (§4.4.3). `harness.expected_effects/1` is spec 0003's.

### 4.3 The change-set model

#### 4.3.1 Shape

The change set is the answer to one `ctx.ask(ChangeSetRequest, title=...)` per cycle (a data request,
`x-eng-input: data`, answered with `run --answers FILE` for the first change set of the run and with
`resume --answers FILE` after a pause, spec 0006 §4.2.1, AC64). `ChangeSetRequest` has one field
`change_set: ChangeSetDraft`; the answer is stored as `basis.engineer_input/1` (engine AC61), so its literal values are
engineer inputs with `entered_by` and `entered_at`, and the change-set approval is where the engineer confirms them
(spec 0006 Q3).

`ChangeSetDraft` (frozen, `extra="forbid"`): `items` (1 to `ChangeSetSettings.max_items`, a software setting),
`note` (`Label`, optional), `benchmark_request` (`Label`, optional: the B-1 request id, §4.9). Each item has a unique
`id` (`Label`) and a `kind` (discriminator):

| `kind` | Fields | Tool (spec 0002 §4.6.2) |
|---|---|---|
| `frame_section` | `frames` (names) or `select` (`story`, `section`: names or null; at least one), `section` (name) | `csi_assign_frame_section` per frame |
| `area_section` | `areas` or `select` (`story`, `section`, `area_kind` `slab`/`wall`/null), `section` | `csi_assign_area_section` per area |
| `wall_section` | `name`, `material` (name), `thickness` (length value), `shell_type` (`ShellThin`, `ShellThick`, `Membrane`) | `csi_define_wall_section` |
| `frame_uniform_load` | `frames` or `select`, `pattern`, `direction` (`gravity`), `w` (line-load value) | `csi_set_frame_load_distributed` per frame |
| `area_uniform_load` | `areas` or `select`, `pattern`, `direction` (`gravity`), `q` (area-load value) | `csi_set_area_load_uniform` per area |
| `load_pattern_add` | `name`, `type` (`dead`, `live`, `seismic`, `wind`, `snow`, `other`), `self_weight` (ratio value) | `csi_add_load_pattern` |
| `load_combination_set` | `name`, `type` (`linear_add`, `envelope`, `absolute_add`, `srss`), `items` (`case`: `CaseRef`, `scale`: ratio value) | `csi_add_load_combo` |
| `load_combination_delete` | `name` | `csi_delete_load_combo` (always ask) |
| `joint_restraints` | `joints` (names), `ux`, `uy`, `uz`, `rx`, `ry`, `rz` (bool) | `csi_set_point_restraint` per joint |

A **value** is `{"source": "basis", "path": "<basis path>"}` or `{"source": "input", "value": <number>, "unit":
"<unit>"}`. The unit must be one of contract §4.7.3 with the dimension of the field (length: `mm`, line load: `kN/m`,
area load: `kPa`, ratio: `1`); the value is converted to the canonical unit by `eng_contract.units`, never by hand.
Names (frames, sections, patterns) are strings, never engineering values; each must exist in the step 3 model state or
be added by an earlier item of the same set (a pattern for a load or combination, a wall section for an area
assignment).

#### 4.3.2 Refused kinds and variants (P5, never improvised)

`slab_section`, `frame_section_define`, `area_section_define`, `material_define` (gap H-G1); a `direction` other than
`gravity` and frame point loads (H-G2); pattern types `superimposed_dead`, `roof_live` and combination type `range`
(H-G3); `load_pattern_change` and `load_pattern_delete` (OQ-G8); `seismic_parameters` (CG-1, OQ-G8). These parse, so
the engineer sees a reasoned refusal instead of a schema error, and the check gives `NOT_IMPLEMENTED` with the gap id
(AC6). Anything else is a schema error.

#### 4.3.3 Validation (18 step 5, P5)

Shape, units and literal types: `ChangeSetDraft` (engine AC61 refuses an invalid answer). Everything that needs the
model or the basis: `harness.change_set_check` (§4.4.1), a calc so that it is deterministic, traced, golden-tested
and approved like every other R1 calc (spec 0003 §4.5). Bounds come from the design basis (§4.8 `bounds.*`), each
field with its own source; the contract kinds' structural bounds (dimensions greater than zero, contract §4.10.2)
apply too.

### 4.4 Calcs

All four follow spec 0003 §4.2 to §4.5 (pure, traced, golden cases with sources, content hash, `draft` until the owner
approves them in `approvals.yaml`). Runs use `--run-class trial` until then (spec 0003 §4, spec 0006 Q7).

#### 4.4.1 `harness.change_set_check` v1

Input: `change_set` (reference to the answer field), `state` (the read set of step 3, not `stale_ok`), `names`
(`harness.csi_name_lists/1`), `diff` (the step 4 `harness.model_diff/1`), `basis`. Output
`harness.change_set_check/1`: `status` (`PASS`, `FAIL`), `resolved` (per item: `item_id`, `kind`, explicit targets
sorted by code point, `values` as `{pointer, ref, unit}` where `ref` is the reference to the basis field or to the
answer field, never a number), `issues` (`item_id`, `severity` `error`/`warning`, `code`, `detail`), `complete`.

Rules: K1 resolve `select` against `model.frame_placements/1` or `model.area_placements/1` (story equal, section equal,
area kind from `model.sections/1`); an empty result is `EMPTY_SELECTION`. K2 every name exists (`UNKNOWN_<CLASS>`) or
is added earlier in the set. K3 two items setting the same target and property is `DUPLICATE_TARGET`. K4 each value:
a `basis` path present and confirmed (else `SOURCE_MISSING`), unit of the field's dimension (`UNIT_MISMATCH`), value
within `bounds.<kind>_min` and `_max` by exact comparison of canonical values (`OUT_OF_BOUNDS`). K5 refused kinds
(§4.3.2). K6 an item whose target and property appear in `diff.changes` gets the warning
`CONFLICTS_WITH_ENGINEER_CHANGE`. K7 `FAIL` on any error.

#### 4.4.2 `harness.expected_effects` v1 (spec 0003 Q6)

Input: `check` (`harness.change_set_check/1`, status `PASS`), `approval_items` (the accepted item ids), `state`.
Output: spec 0003's `harness.expected_effects/1`. Projection per kind: section assignments, loads and restraints are
`set` effects per target at the property's pointer; `wall_section` is one `set` of `thickness_mm` on
`model.sections/1` (spec 0003 §4.8 edge cases); `load_pattern_add` is `add` on `model.load_set/1` patterns;
`load_combination_set` is `set` of the whole combination (or `add` when new); `load_combination_delete` is `remove`;
an unlock has no model effect. Effects are sorted by section, key and pointer, so item order does not matter.

#### 4.4.3 `harness.host_design_verdicts` v1

Maps `harness.csi_design_results/1` (spec 0002 §4.6.1 step 13, raw host output) to `verdicts.set/1` with
`source: host`, so spec 0003's design summary can read it (resolves the spec 0003 Q7 conflict, §11 C4). Steel: one
verdict per frame with the host's ratio and `ratio_limit` from the basis (`limits.ratio_limit`); the status is the
contract's (`PASS` when the ratio is at most the limit, else `FAIL`, contract §4.9.1), computed by comparison only.
Concrete: the host reply holds beam design output without a single ratio (S-12 §1 step 13), so every concrete frame
gets `NEEDS_ENGINEER` with the message "host concrete design output not mapped" (gap EC-G2). The reply field names are
those of the S-12 inventory and need a local test (§12).

#### 4.4.4 `harness.analysis_summary` v1

Input: `messages` (`harness.csi_analysis_messages/1`), `drifts` (`forces.story_drifts/1`), `basis`
(`limits.drift_ratio`). Output `harness.analysis_summary/1`: message counts by the severity the host reports
(`error`, `warning`, `info`, `unclassified`), `has_errors`, `has_unclassified`, governing drift per direction (story,
case, ratio, by ordering only), stories whose drift ratio exceeds the limit, `status` (`PASS`, `NEEDS_ENGINEER` on
unclassified messages or drifts above the limit, `FAIL` on error messages). The severity column of the
`Analysis Messages` table needs a local test (§12); until it is confirmed every message is `unclassified`.

### 4.5 Steps as ctx calls

Notation: `m` is the model handle, `B` the basis view, `k` the cycle index. Steps run in the child blocks of §4.1, so
paths are stable (engine §4.3.1). Checks marked "engine" are enforced whatever the block does.

| # | Calls | Checks the engine enforces |
|---|---|---|
| 1 | none (run start) | Invariant 8: build and tool-list fingerprint, before `run_started` (`RunRefused SERVER_CHECK_FAILED`); invariant 5: every §4.8 field present and confirmed |
| 2 | `ctx.tool("csi_open_model", {"model": inp.model})` on a launched instance | `copy_on_open`: working copy (`model_saved` role `working_copy`, `origin_sha256`) right after the open, in every mode; `model_bound`; units read (invariant 9); host lock (invariant 10) |
| — | `async for c in ctx.attempts(B.count("attempts.cycles"))`: one `ctx.block(edit_cycle_once, ...)` per cycle | Bounded loop; exhaustion escalates |
| 3 | `ctx.tool("csi_read_model_state", {"model": m})` (§4.10) | Check after write before the read (invariant 1) |
| 4 | `ctx.calc("harness.model_diff", {"before": R[k-1], "after": S[k], "basis": B.ref(...)})` | `before` is `stale_ok`, `after` current (spec 0003 §4.13) |
| 5 | Turn `more_edits` or cycle 1: `async for a in ctx.attempts(B.count("attempts.change_set"))`: `ctx.ask(ChangeSetRequest, ...)`, then `ctx.calc("harness.change_set_check", ...)`; `FAIL` asks again. Turn `hand_edit`: empty set | Invariant 3 on every reference; engine AC61 schema validation |
| 6 | `ctx.approve(title, Preview(items=<the item "revision" (step 7), one per change-set item, plus unlock and delete items>, diff_ref=<step 4>, models=[m]), kind=CHANGE_SET)`; skipped when the set is empty | Binding to the model state (engine §4.9); single use |
| 7 | `ctx.tool("csi_save_model", {"model": m, "as_new_revision": True}, under=approval, item="revision")`; without `under=` when step 6 was skipped (empty set) | Binding re-check before it (`ApprovalVoid`, D-5); first link of the approval's write chain (Q3); `model_saved` role `revision` for the snapshot `P[k]` (§4.5.1); never over an existing file |
| 8 | If the step 3 status shows `locked`: `ctx.tool("csi_unlock_model", ..., under=approval, item="unlock")`. Then per accepted item and target: `ctx.tool(<tool>, args, under=approval, item=<id>)`, arguments from `resolved` (references only) | Re-check before the first write and between writes (`ApprovalVoid`); invariant 2 (references for engineering parameters); always-ask list; `approve_each_write` previews |
| 9 | `ctx.tool("csi_read_model_state", ...)` (S'), `ctx.calc("harness.expected_effects", ...)`, `ctx.calc("harness.readback_check", {"effects", "before": S[k], "after": S', "basis"})`; then D-2 (§4.6) | Invariant 1 inserts `check_model` before the read; read-back independence R0 (spec 0003 §4.8) |
| 10 | `ctx.tool("csi_save_model", {"model": m})` | `model_saved` |
| 11 | `ctx.tool("csi_run_analysis", {"model": m})` | Invariant 7 save first; long role and timeout (spec 0002 AC28); invariant 6 on a timeout: `engine.in_flight`, outcome unknown in v1 (spec 0002 Q4, H-G7); invariant 9 units after a timeout |
| 12 | Per kind in `B.choice("design.run", DesignRun)`: `ctx.tool("csi_design_run", {"model": m, "kind": ...})` | Same as step 11 |
| 13 | `ctx.parallel(ctx.tool("csi_read_analysis_messages", ...), ctx.tool("csi_results_story_drifts", ...), ctx.tool("csi_design_results", ...))` (reads of one model in one parallel are allowed, engine §4.3.1) | Invariant 1; units labels converted by the adapter |
| 14 | `ctx.calc("harness.analysis_summary", ...)`, then D-3; `ctx.calc("harness.host_design_verdicts", ...)`, `ctx.calc("harness.design_summary", {"verdicts", "frames", "previous": <cycle k-1>, "basis"})` | Invariant 3 |
| 15 | `ctx.decide("edit_cycle.engineer_turn", EngineerTurn, TurnState(...), rules=(), policy=require_engineer)` | Invariant 4; the choice is on the page only (spec 0006 AC46) |
| 16 | `ctx.approve(..., kind=PROMOTION)`, `ctx.promote(m, Promotion.FILE_COPY, approval)` | Always ask; binding with file hashes; original unchanged (`CONFLICT`) (engine §4.7) |
| 17 | `ctx.approve(..., kind=SIGN_OFF)` with the outputs as preview items | Always ask; `signed_off`; the page refuses exceptions without a reason (spec 0006 AC42) |

`R[k]` is the recorded state of revision `k`: the step 9 read of cycle `k`, or its step 3 read when the cycle wrote
nothing; `R[0]` is the step 3 read of cycle 1 (the baseline, compared with itself only for completeness). `S[k]` is
the step 3 read of cycle `k`. When the step 3 fingerprint equals that of `R[k-1]`, step 4 still runs (a cheap,
journaled proof that nothing changed).

#### 4.5.1 Revision files

- `W`, the working file: step 2's working copy, the only file the host has open. Every write, the engine's
  `p~post.save` after each write (engine §4.7), the step 10 and `pre_analysis` saves, and the engineer's own saves in
  ETABS go into `W` in place.
- `P[k]`, the snapshot of cycle `k`: step 7 (`as_new_revision`, §4.10) saves `W` in place, copies its files to a new
  file in the run's copies folder, verifies the copy's hash and journals `model_saved` (role `revision`) with the
  snapshot's name and hash; the host keeps `W` open. `P[k]` holds `S[k]`, so the engineer's changes are in it. No
  tool writes a snapshot: the adapter refuses a write or save whose target is one, and the page tells the engineer to
  edit only the open model. A new approval-void iteration (D-5) makes a new snapshot at its own step 7.
- `restore_previous` (D-2) runs `csi_open_revision` on this cycle's latest `P[k]`, never on `R[k-1]`: it checks that
  the snapshot's file hash equals its `model_saved`, copies it to a new working file, opens that file on the bound
  instance without saving `W` (action `open`, `model_bound`, `model_saved` role `revision`), and the new file becomes
  `W`. The writes of the failed apply are gone and the engineer's changes stay (AC34). A snapshot whose hash differs
  (someone saved over it) gives `CONFLICT`: nothing is opened and the run escalates; the engineer decides.
- The accepted revision that step 16 promotes is `W` as saved at step 10 of the accepted cycle (or by a later engineer
  save, which the promotion binding shows).

**Return to step 3 (D-5).** Steps 3 to 8 run inside `async for v in ctx.attempts(B.count("attempts.approval_void"))`.
`ApprovalVoid` before the first write starts the next iteration (a new read, difference report and approval). A void
after a write cannot be undone silently: it opens D-2 with the reason `model_changed_during_apply`.

### 4.6 Decision points and rules

Points are built with `decision_point` (spec 0005 §4.2) and listed in `decisions.lock.json`; rules with `rule` (spec
0005 §4.4), in the given order, R1 and `draft` until the owner approves them (spec 0005 Q7). State models carry
statuses, booleans and labels only; no rule holds a number (thresholds are in the calcs, read from the basis).

| Point | Options | State | Rules, in order | Policy |
|---|---|---|---|---|
| `edit_cycle.readback_result` (D-2) | `continue`, `restore_previous`, `stop_cycle` | readback status, counts of mismatch, missing, unexpected and not-read items as booleans (`has_mismatch`, ...), reason (`readback`, `model_changed_during_apply`), refs | `rb.pass`: status `PASS` and reason `readback` → `continue` | `require_engineer=True` after the rules; `model=False`, `llm=False` |
| `edit_cycle.analysis_messages` (D-3) | `continue`, `stop_cycle` | `has_errors`, `has_unclassified`, drift status, refs | `am.clean`: not `has_errors`, not `has_unclassified` → `continue` | same |
| `edit_cycle.engineer_turn` (D-6) | `accept`, `more_edits`, `hand_edit` | readback, analysis and design statuses, counts as labels, refs to the summaries and the difference report | none | `require_engineer=True` |

D-2 and D-3 are never open at the same time: D-2 is asked before analysis and an open D-2 means analysis does not
run (AC17), so no batching is needed. D-2 reaches the engineer only on a read-back failure, a failure path of §4.9;
on a normal path at most D-3 reaches the engineer, so A7 holds there. Until EC-G3 is resolved every analysis
message is `unclassified`, so `am.clean` sends D-3 to the engineer whenever the host reports any message, as real
analyses usually do; D-3 is then the cycle's one prompt and any further request in that cycle exceeds A7 (Q10). D-1 (WS §5) is the attempts loop of step 5 and D-5 the loop of §4.5; neither is a decision point. D-4 is
the engine's in-flight request (engine §4.5.3), not a workflow point. `stop_cycle` skips to the engineer turn of the
same cycle with the summaries available so far; `restore_previous` runs `ctx.tool("csi_open_revision", {"model": m,
"revision": P[k]})` (§4.5.1, §4.10, Q4) and starts the next approval-void iteration (a new step 3 read, a step 4
difference report against `R[k-1]` that still shows the engineer's changes, and a new approval).

### 4.7 Approvals, permission modes and the engineer turn

| Request | `work_on_copy` | `approve_each_write` | `autonomous_logged` |
|---|---|---|---|
| Step 6 `CHANGE_SET` | page | page | resolved by the mode (engine §4.7) |
| Step 7 revision save | `under=` step 6 (item `revision`) | `under=` step 6, no per-write preview (Q3) | direct |
| Step 8 writes | `under=` step 6 | `under=` step 6, plus the engine's `p~pre.approve` preview per write | direct |
| Unlock, combination delete | `under=` step 6, listed as items | same | the engine inserts its always-ask approval (Q5) |
| Steps 11, 12 | none | engine preview per call (analysis and design are writes) | none |
| Step 15 engineer turn | page | page | page |
| Steps 16, 17 | page (always ask) | page | page |

The workflow never passes `under=` an approval that the mode resolved; with Q5 accepted, the engine enforces it too.

**Engineer turn (18 step 15, ADR-0025 decision 3).** A choice request (spec 0006 Q14), not an approval: it binds no
model state and writes nothing. The page shows the three buttons of spec 0006 AC43; the state links the design and
analysis summaries and the difference report. `accept` ends the loop with this revision. `more_edits` starts the next
cycle, which asks for a change set at step 5. `hand_edit` (the label tells the engineer to save in ETABS first)
starts the next cycle with an empty change set: steps 3 and 4 read and show the engineer's changes, step 6 is
skipped, step 7 records them as a revision, steps 8 and 9 are skipped, steps 10 to 15 run. The differences are
journaled as `harness.model_diff/1` and shown in the report and at the next turn; nothing overwrites them, because
every write in a later cycle needs an approval whose preview carries them and whose binding includes them.

### 4.8 Design basis fields (final list; spec 0004 §4.5 proposed, this spec decides)

No value is shipped (spec 0004 Q8). Every field is required, asked at run start through the blank template's
`ask_each_run` (spec 0004 §4.8), and confirmed on the page.

| Path | Kind | Unit | Used by |
|---|---|---|---|
| `compare.length`, `compare.angle`, `compare.stress`, `compare.unit_weight`, `compare.line_load`, `compare.area_load`, `compare.ratio` | quantity | `mm`, `deg`, `MPa`, `kN/m3`, `kN/m`, `kPa`, `1` | difference report and read-back check (spec 0003 §4.4) |
| `checks.readback_relative_tolerance` | quantity | `1` | adapter `check_model` (spec 0002 §4.5.8, G-2; Q6) |
| `report.top_n` | count | — | design summary |
| `limits.ratio_limit` | quantity | `1` | host design verdicts |
| `limits.drift_ratio` | quantity | `1` | analysis summary |
| `bounds.thickness_min`, `bounds.thickness_max` | quantity | `mm` | change-set check |
| `bounds.line_load_min`, `bounds.line_load_max` | quantity | `kN/m` | change-set check |
| `bounds.area_load_min`, `bounds.area_load_max` | quantity | `kPa` | change-set check |
| `bounds.ratio_min`, `bounds.ratio_max` | quantity | `1` | change-set check (self-weight multiplier, combination scale) |
| `design.run` | choice | `steel`, `concrete`, `steel_and_concrete` | step 12 |
| `attempts.cycles`, `attempts.change_set`, `attempts.approval_void` | count | — | `ctx.attempts` limits (engine Q1) |

Spec 0004's proposed `modeling.merge_tolerance_mm`, `modeling.snap_tolerance_mm` and
`modeling.section_rounding_increment_mm` are not used: v1 adds or moves no object and computes no section size.

### 4.9 Benchmark B-1 instrumentation

Every journal event carries its time from the contract `Clock` (engine §4.4). The workflow adds no event type; it makes
the journal sufficient for B-1:

- each cycle is the scope `<loop path>/<k>`, so every event's cycle follows from its step path;
- the change set carries the optional `benchmark_request` label, recorded through the answer;
- `edit_cycle_timings(reader) -> CycleTimings` (pure, over `JournalReader`) gives per step its kind, name and duration;
  per cycle the wall time, machine time (completed step durations), host time (tool steps), engineer wait (approval,
  input and decision waits), and prompt count (§3.4 AC26); per engineer turn the wait from request to answer (hand
  editing happens inside it); per `benchmark_request` the time from the first change-set `input_requested` to the
  `accept` decision, engineer time included, and the cycles it took;
- the report shows them in its timings section, and `report` also writes `report/cycle-timings.json` (base names
  only) for the owner's B-1 sheet.

`count_prompts` counts, per cycle, every `input_requested`, `approval_requested` and engineer-decided decision request
except the first step 6 approval of the cycle, the first change-set request of the cycle and the engineer turn. A
repeated step 6 approval (after `ApprovalVoid` or `restore_previous`), a re-asked change set, an engine request
(`engine.in_flight`, `engine.host_state`, `engine.escalation`), a separately asked always-ask approval and a D-2 or D-3
screen each count; one batched screen counts once. Steps 16 and 17 are once per run, outside the cycle, and are not
counted. The A7 bound (at most one per cycle) applies to the normal paths: AC9 to AC12, AC15, AC19, AC21 and AC22.
In those fake-host scenarios the fake returns no analysis messages, so D-3 resolves by `am.clean` and no request is
counted; one added scenario has the fake return messages, which are `unclassified` (EC-G3), and shows D-3 as that
cycle's one prompt. Interruption, failure and escalation paths (resume after a stop with its `engine.host_state`
request, approval void, read-back failure and restore, timeout, change-set re-asks and exhaustion, cycle limit: AC13,
AC14, AC16, AC17, AC20, AC24, AC34) are counted and shown in the report but not bounded; the B-1 journals show how
often they occur. AC14 is not a normal path: its host-state request is the engine's answer to a stop, and it counts.

### 4.10 Adapter additions (spec 0002 amendment, Q1 **[added]**)

Three adapter-local tools in the CSI allowlist and one argument, each composed of allowlisted Sasaah tools only (no new
server tool):

- `csi_read_model_state` (effect `read`): runs the spec 0002 §4.6.4 reader and stores each kind as its own result
  (`model.stories/1`, `model.frame_placements/1`, `model.area_placements/1`, `model.sections/1` where readable,
  `model.load_set/1`, `model.joint_restraints/1`, `harness.csi_model_status/1`) plus `harness.csi_name_lists/1`
  (frame section, area section, material, pattern and combination names). Its summary holds the references. A
  section that a read-back gap leaves unreadable is absent, so downstream calcs give `not_read` (spec 0003 §4.8).
- `csi_open_revision` (effect `write`, action `open`): checks that a snapshot of this run still has the file hash of
  its `model_saved` (else `CONFLICT`), copies it to a new working file in the run's copies folder, opens that file on
  the bound instance without saving the current one, and records `model_saved` (role `revision`); used by D-2
  `restore_previous` (§4.5.1). Amendment B-415: the engine, not the adapter, journals that `model_saved` (engine §4.6
  "Tool saves"): the tool's `ToolInfo.saves_new_file(args)` returns true and its result summary carries `saved_file`
  (`name`, the new working file's base name; `sha256`, its file hash).
- `csi_read_analysis_messages` (effect `read`): the `Analysis Messages` table through `csi_db_table_read` (read
  only), stored as `harness.csi_analysis_messages/1`.
- `csi_save_model` gains `as_new_revision`: saves the open file in place, then copies its files to a snapshot at a
  path in the run's copies folder chosen by the adapter (refuses an existing file) and verifies the copy's hash; the
  host keeps the working file open (§4.5.1). The adapter refuses any write or save whose target is a snapshot.
  Amendment B-415 (engine §4.6 "Tool saves", §4.8): with `as_new_revision` true, the CSI `ToolInfo.saves_new_file(args)`
  returns true and the result summary carries `saved_file` (`name`, the snapshot's base name; `sha256`, its verified
  file hash), from which the engine journals `model_saved` (role `revision`); without it, `saves_new_file` is false and
  the engine journals the in-place save.

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `EditCycleInput.model` | `harness.file_input/1` reference | — | an existing `.EDB` | yes | engineer (`--input`) |
| `EditCycleInput.visible_host` | bool | — | — | no | engineer |
| `ChangeSetDraft` values | basis path or number with unit | length, line load, area load, ratio (§4.3.1) | `bounds.*` (§4.8) and contract kind bounds | yes (basis) | design basis or engineer input |
| Names in items | `str` | — | 1 to 200 characters, must exist | no | engineer; model state |
| `EditCycleOutput` | §4.2 | — | — | — | the run |

## 6. Errors

| Condition | Code | Fields |
|---|---|---|
| Change set fails its model | `INVALID_ARGUMENT` (engine AC61: refused, presented again) | `field` |
| Change set fails the check | none: `harness.change_set_check/1` `FAIL`, asked again (AC24) | issues |
| Refused kind | issue `NOT_IMPLEMENTED` with `gap` | item id |
| Change sets exhausted, cycles exhausted | `Escalation` (`attempts_exhausted`) | evidence refs |
| Model changed after approval | `ApprovalVoid` (engine §4.9), handled by D-5 | binding |
| Read-back failure | `harness.readback_check/1` status; D-2 | items |
| Promotion conflict | `ContractError CONFLICT` (engine §4.7), escalates | hashes |
| Truncated read | `LIMIT_EXCEEDED` (spec 0002 §4.6.4) | tool |

Errors of the engine, adapters and calcs pass through unchanged.

## 7. Non-goals

- The refused kinds of §4.3.2 and any other kind; geometry edits; stories and grids; other hosts; code checks; the
  DXF start (18 §2, §6).
- Promotion by replaying writes (gap E-G1).
- Any engineering value: the workflow, its rules and calcs hold none; every threshold is a basis field.
- Choosing a fix for failing members: the engineer turn decides.
- The B-1 data, the manual times and the A4 measurement (owner, local stage).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A hand edit is written over | R1 | Difference report every cycle; conflicts marked; approval binding and re-check; host-state check on resume (AC12 to AC14) |
| A wrong value reaches the model (unit scale, wrong source) | R1 | Basis bounds, references only, read-back from the saved state (AC5, AC10, AC25) |
| A write repeats after a crash | R1 | Engine in-flight rule and crash matrix (AC27); live test |
| Rules or calcs in draft used for real work | R1 | Trial run class, DRAFT SOURCES mark, owner queue |
| The cycle is too slow for A4 (one call per object, S12-G4) | R2 | Timings per step (§4.9) show where; typed batch tools through the project lane |
| The slice grows (ADR-0025 pre-mortem) | R2 | Refused kinds with gap ids; new kinds only through the project lane |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1, AC3, AC6, AC18, AC25 (unit part), AC26 (unit part), AC29, AC32, AC33, AC35 | Unit | `tests/unit/edit_cycle/`, `tests/unit/report/` |
| AC2 | Unit (source rules) | `tests/rules/` |
| AC3 (kinds) | Contract | `tests/contract/` |
| AC4, AC5, AC7, AC8, AC30 | Golden | `tests/golden/edit_cycle/`, data in `tests/data/golden/edit_cycle/` |
| AC8, AC25 (generated) | Property | `tests/property/` |
| AC9 to AC17, AC19 to AC24, AC26, AC31, AC34 | Fake-host workflow | `tests/workflow/edit_cycle/`, `tests/workflow/adapters/` |
| AC27, AC28 | Replay | `tests/replay/edit_cycle/` |

No host program and no network. Coverage floors 85% line and 75% branch; mutation score at least 80% on the R1
modules (`rules/edit_cycle.py`, `calcs/edit_cycle/`, `adapters/csi/_read_state_tool.py`, `adapters/csi/_revisions.py`).

## 10. Version impact

Minor within `eng-harness` 0.1.0 (phase 1 is unreleased). New kinds are new kind versions; the block, points and rules
start at version 1 with lock entries.

## 11. Open questions, conflicts and gaps

| Id | Question, conflict or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | Adapter-local tools `csi_read_model_state`, `csi_open_revision`, `csi_read_analysis_messages` and `as_new_revision` (§4.10) are not in spec 0002 | Owner | Accept as a spec 0002 amendment carried by this plan's T5 |
| Q2 | 18 §3 says the run works on a copy in every case, while engine §4.7 takes a working copy only before the first write and only in `work_on_copy` | Owner | Add `WorkflowDef.copy_on_open` (engine amendment): the copy is taken right after the open, in every mode; amend 11 §7. Engine text written by amendment B-415 (engine §4.7, rule EC1, Q27; draft until the owner approves); 11 §7 is in the owner queue |
| Q3 | 18 step 7 saves "as the next revision" (a new file, baseline أ5); engine §4.6 journals `model_saved` only for its own saves, and its re-check (§4.9) would void the step 6 approval at the first write because the save changes the file hash | Owner | Engine amendment: journal `model_saved` (role `revision`) for a tool step with action `save` from its result's provenance; a save passed `under=` an approval is re-checked against the binding like a write and its result (and each engine `p~post.save` result) becomes the expected state of the next write under that approval; a save to a new file (not `overwrites_original`) gets no `approve_each_write` preview. Engine text written by amendment B-415 (engine §4.6 "Tool saves", §4.7, §4.8 `saves_new_file`, §4.9, rules EC2, EC5, EC6, Q28, Q30; draft until the owner approves) |
| Q4 | Restoring an earlier revision inside a cycle (D-2) has no engine or adapter operation | Owner | `csi_open_revision` on this cycle's step 7 snapshot (§4.5.1, §4.10), which keeps the engineer's changes; it never overwrites a file and refuses a changed snapshot |
| Q5 | Conflict: ADR-0018's always-ask list applies in every mode, but `under=` a mode-resolved approval would satisfy it (engine §4.7) | Owner | Engine amendment: an approval resolved by `mode:*` never satisfies an always-ask step. Engine text written by amendment B-415 (engine §4.7, rule EC3, Q29; draft until the owner approves) |
| Q6 | Two read-back tolerances: spec 0002 `checks.readback_relative_tolerance` and spec 0003 `compare.*` | Owner | Keep both in v1 (both required); converge on `compare.*` in the next spec 0002 revision |
| Q7 | The first change set arrives only by `resume --answers` after `run` pauses at the request | Owner | Decided by amendment B-354 in spec 0006 (§4.2.1, §4.4.7, AC47, AC64, Q17): `run --answers FILE` pre-answers the first change-set request; the engineer starts `run` without `--no-wait`, confirms the basis on the page and approves the change set there. The interim `run --no-wait` route is withdrawn: a `--no-wait` run cannot confirm the basis, so it cannot start this workflow |
| Q11 | The A3 audit and the A7 prompt count (AC25, AC26) are functions, and spec 0006 AC1 allows six commands only (`LOCAL-TESTING.md` open point 7) | Owner | Decided by amendment B-354: the read-only module entry point `python -m eng_harness.report` with `audit-sources` and `count-prompts` (AC35), as spec 0009 exposes `python -m eng_harness.providers` (its Q6); no seventh command |
| Q8 | Which A7 requests count, and on which paths (§4.9) | Owner | As §4.9: the first change-set request and the first step 6 approval are the cycle's own and do not count; re-asks, repeated approvals and engine requests do; the bound applies to normal paths, failure and escalation paths are counted and reported |
| Q9 | OQ-Q4: the v1 edit-kind list (WS §3.1) | Owner | Confirm; seismic parameters wait for a Sasaah tool (OQ-G8) |
| Q10 | A7 depends in practice on EC-G3: while every analysis message is `unclassified`, D-3 asks the engineer in almost every real cycle, so the CI scenarios hold A7 only because the fake returns no messages, and in the local B-1 runs any other request in a cycle with messages exceeds the bound | Owner | Resolve EC-G3 in local test (1) of §12 before the B-1 acceptance runs; until then report A7 per cycle with the D-3 prompts shown separately, and do not relax `am.clean` (an unknown message must not pass silently) |
| C1 | 18 step 11 "or followed through the status tool": S-12 §5 shows synchronous runs | Owner | As spec 0002 C1: long role with its own timeout |
| C2 | 18 step 15 calls the engineer turn "approve"; spec 0006 Q14 makes it a choice | Owner | Choice request (§4.7) |
| C3 | 18 §2 seismic parameters "through a dedicated tool": none exists | Owner | Refused (CG-1, OQ-G8) |
| C4 | Spec 0002 stores design results raw; spec 0003's summary needs `verdicts.set/1` | Owner | `harness.host_design_verdicts` (§4.4.3) |
| EC-G1 | Edit kinds refused in v1: H-G1, H-G2, H-G3, OQ-G8, CG-1 | Owner | Project lane or Sasaah changes; tests expect `NOT_IMPLEMENTED` (AC6) |
| EC-G2 | Concrete design output has no single ratio; verdicts are `NEEDS_ENGINEER` | Owner | Map after the local test shows the reply fields; until then the engineer reads the host's concrete design |
| EC-G3 | Analysis message severity is not known from the sources | Owner | Every message `unclassified` until the local test confirms the table's columns |
| EC-G4 | Calcs and rules of this spec are R1 and ship `draft` | Owner | Review the verification records and rules; approve in `approvals.yaml` after the local tests |

## 12. Needs local test

Listed in `docs/local-testing.md` by the plan: (1) a full cycle on a copy of a real model, with the reply fields of
`csi_design_results` (steel and concrete) and the columns of `Analysis Messages`; (2) `csi_save_model` as a new
revision and `csi_open_revision` on a server-launched instance; (3) the engineer editing by hand in the visible
launched instance, saving, and pressing "I edited by hand"; (4) acceptance A1 to A7 on benchmark B-1, all of A4, with
`cycle-timings.json` filled into the owner's sheet; (5) an ETABS kill and a process kill at analysis, apply and
promotion (A6); (6) promotion when the original is open in the engineer's ETABS (file lock).
