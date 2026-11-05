---
id: plan-b066-model-edit-cycle
issue: "B-066"
spec: packages/eng-harness/docs/specs/0007-model-edit-cycle.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2, r3]  # r3 from the public_modules entries in pyproject.toml (amendment B-356)
tasks:
  - id: T1a
    title: Edit-cycle payload kinds (change_set_check, analysis_summary, csi_name_lists) and their registration
    # Amendment (B-386, documents only): the former T1 measured 562 changed non-test lines against its limit of 320
    # (B-195): about 215 for the kinds and their registration, about 350 for the change-set model. Split into T1a and
    # T1b (D-12); T1b may add to kinds/edit_cycle.py the shared constants its model needs (FB005 keeps numeric literals
    # out of block modules).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.kinds, eng_harness.kinds.edit_cycle (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/kinds/edit_cycle.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/contract/test_edit_cycle_kinds.py"
      - "packages/eng-harness/tests/data/kinds/edit_cycle/**"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_edit_cycle_kinds.py::test_fixtures"
    covers: [AC3]
    depends_on: []
  - id: T1b
    title: The change-set model (ChangeSetDraft, item and value models, refused kinds as parseable models)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.workflows and its model_edit_cycle module (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/kinds/edit_cycle.py"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_change_set.py"
      - "packages/eng-harness/tests/unit/edit_cycle/__init__.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_change_set.py"
    max_changed_lines: 380
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/edit_cycle/test_change_set.py::test_model_parses_and_refuses"
    covers: [AC3]
    depends_on: [T1a]
  - id: T2
    title: Calc harness.change_set_check (resolve, validate, conflicts, refused kinds)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.edit_cycle, eng_harness.calcs.edit_cycle.change_set_check (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/change_set_check.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.change_set_check.md"
      - "packages/eng-harness/tests/golden/edit_cycle/__init__.py"
      - "packages/eng-harness/tests/golden/edit_cycle/test_change_set_check.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/check-*.json"
      - "packages/eng-harness/tests/unit/edit_cycle/test_change_set.py"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/golden/edit_cycle/test_change_set_check.py::test_golden_cases"
      - "packages/eng-harness/tests/unit/edit_cycle/test_change_set.py::test_refused_kinds_name_their_gap"
    covers: [AC4, AC5, AC6, AC7]
    depends_on: [T1b]
  - id: T3
    title: Calc harness.expected_effects (projection of a resolved change set)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.edit_cycle, eng_harness.calcs.edit_cycle.expected_effects (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/expected_effects.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.expected_effects.md"
      - "packages/eng-harness/tests/golden/edit_cycle/test_expected_effects.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/effects-*.json"
      - "packages/eng-harness/tests/property/test_expected_effects.py"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/edit_cycle/test_expected_effects.py::test_golden_cases"
      - "packages/eng-harness/tests/property/test_expected_effects.py::test_order_independent"
    covers: [AC8]
    depends_on: [T2]
  - id: T4
    title: Calcs harness.host_design_verdicts and harness.analysis_summary
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.edit_cycle, eng_harness.calcs.edit_cycle.analysis_summary and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/host_design_verdicts.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/analysis_summary.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.host_design_verdicts.md"
      - "packages/eng-harness/docs/verification/calcs/harness.analysis_summary.md"
      - "packages/eng-harness/tests/golden/edit_cycle/test_design_verdicts.py"
      - "packages/eng-harness/tests/golden/edit_cycle/test_analysis_summary.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/verdicts-*.json"
      - "packages/eng-harness/tests/data/golden/edit_cycle/analysis-*.json"
    max_changed_lines: 340
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/edit_cycle/test_design_verdicts.py::test_golden_cases"
      - "packages/eng-harness/tests/golden/edit_cycle/test_analysis_summary.py::test_golden_cases"
    covers: [AC30]
    depends_on: [T1b]
  - id: T5
    title: CSI adapter read tool, revision save and open, analysis-messages read (spec 0002 amendment)
    # Amendment (B-415, documents only): the CSI ToolInfo implements saves_new_file (true for as_new_revision and
    # csi_open_revision) and both results carry summary saved_file (name, sha256), spec §4.10; the base default
    # (false) comes with T6, whichever of the two merges first.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_read_state_tool.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_revisions.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_read_state_tool.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_revisions.py"
    max_changed_lines: 330
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_read_state_tool.py::test_read_set"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_revisions.py::test_save_as_new_revision_and_open_revision"
    covers: [AC31]
    depends_on: [T1b]
  - id: T6
    title: Engine amendments (copy on open, tool saves journaled, mode approvals and always-ask, basis fields)
    # Amendment (B-415, documents only): the engine spec text is engine spec 0001 §4.2, §4.6 "Tool saves", §4.7,
    # §4.8, §4.9 and AC70 to AC75; ports.py gains ToolInfo.saves_new_file, _ctx_impl.py only the calls into the hooks.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.block, eng_harness.engine (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/block.py"
      - "packages/eng-harness/src/eng_harness/engine/_modes.py"
      - "packages/eng-harness/src/eng_harness/engine/_invariants.py"
      - "packages/eng-harness/src/eng_harness/engine/_approvals.py"
      - "packages/eng-harness/src/eng_harness/ports.py"  # ToolInfo.saves_new_file, engine §4.8 (amendment B-415)
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"  # calls into the copy-on-open and tool-save hooks (amendment B-415)
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py::test_copy_on_open_every_mode"
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py::test_tool_save_journals_revision"
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py::test_mode_resolved_approval_not_always_ask"
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py::test_required_basis_from_fields"
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py::test_save_under_approval_keeps_chain"
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py::test_revision_save_no_write_preview"
    covers: [AC33]
    depends_on: []
  - id: T7
    title: Decision points and rules of the edit cycle
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.rules, eng_harness.rules.edit_cycle, eng_harness.workflows and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_points.py"
      - "packages/eng-harness/src/eng_harness/rules/edit_cycle.py"
      - "packages/eng-harness/src/eng_harness/decisions.lock.json"
      - "packages/eng-harness/src/eng_harness/rules.lock.json"
      - "packages/eng-harness/tests/unit/edit_cycle/test_rules.py"
    max_changed_lines: 240
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/edit_cycle/test_rules.py::test_rules_typical_and_boundary"
    covers: [AC18]
    depends_on: [T1b]
  - id: T8
    title: Workflow part 1 - definition, basis fields, steps 1 to 10 (read, differences, change set, approval, apply, read back)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.templates, eng_harness.templates.shipped, eng_harness.workflows and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_cycle.py"
      - "packages/eng-harness/src/eng_harness/blocks.lock.json"
      - "packages/eng-harness/src/eng_harness/templates/shipped/blank-0.1.0.template.yaml"
      - "packages/eng-harness/tests/data/golden/shipped_templates.json"
      - "packages/eng-harness/tests/unit/edit_cycle/test_definition.py"
      - "packages/eng-harness/tests/rules/test_edit_cycle_modules.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/__init__.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/conftest.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_apply.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_change_set_step.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_engineer_changes.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/edit_cycle/test_definition.py::test_workflow_definition"
      - "packages/eng-harness/tests/rules/test_edit_cycle_modules.py::test_modules_follow_block_rules"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_apply.py::test_model_holds_exactly_the_changes"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_apply.py::test_rejected_items_not_written"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_apply.py::test_readback_failure_routes"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_change_set_step.py::test_invalid_change_set_asked_again"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_engineer_changes.py::test_edit_during_approval_wait"
    covers: [AC1, AC2, AC10, AC11, AC13, AC17, AC24]
    depends_on: [T2, T3, T5, T6, T7]
  - id: T9
    title: Workflow part 2 - steps 11 to 17 (analysis, design, summaries, engineer turn, promotion, sign-off) and the cycle loop
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.workflows, eng_harness.workflows.model_edit_cycle (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_cycle.py"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_finish.py"
      - "packages/eng-harness/src/eng_harness/blocks.lock.json"
      - "packages/eng-harness/tests/workflow/edit_cycle/conftest.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_cycle.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_engineer_changes.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_turn.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_promotion.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_modes.py"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/edit_cycle/test_cycle.py::test_one_cycle_step_sequence"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_cycle.py::test_cycle_limit"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_cycle.py::test_unlock_under_change_set_approval"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_engineer_changes.py::test_hand_edit_between_cycles"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_engineer_changes.py::test_edit_while_stopped"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_engineer_changes.py::test_restore_keeps_hand_edit"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_engineer_changes.py::test_restore_refuses_changed_snapshot"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_turn.py::test_engineer_turn_branches"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py::test_analysis_timeout_reconciles"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py::test_design_timeout_reconciles"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py::test_save_before_analysis_and_design"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py::test_stale_build_stops_before_any_write"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_promotion.py::test_promote_and_conflict"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_promotion.py::test_sign_off_and_draft"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_modes.py::test_approvals_per_mode"
    covers: [AC9, AC12, AC14, AC15, AC16, AC19, AC20, AC21, AC22, AC23, AC34]
    depends_on: [T4, T8]
  - id: T10
    title: Report renderers, value-source audit, prompt counter and B-1 cycle timings
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.report (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_edit_cycle.py"
      - "packages/eng-harness/src/eng_harness/report/_sections.py"
      - "packages/eng-harness/src/eng_harness/report/_write.py"
      - "packages/eng-harness/tests/unit/report/test_edit_cycle_renderers.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_audit.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_prompts.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_timings.py"
      - "packages/eng-harness/tests/data/journals/edit_cycle/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/report/test_edit_cycle_renderers.py::test_renderers_and_sources"
      - "packages/eng-harness/tests/unit/edit_cycle/test_audit.py::test_audit_finds_literal"
      - "packages/eng-harness/tests/unit/edit_cycle/test_prompts.py::test_prompt_counter"
      - "packages/eng-harness/tests/unit/edit_cycle/test_timings.py::test_cycle_and_turn_timings"
    covers: [AC29, AC32]
    depends_on: [T1b]
  - id: T11
    title: Acceptance support in CI (A3 and A7 over the workflow scenarios) and the local-testing list
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.report (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/src/eng_harness/report/__main__.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_prompts.py"
      - "packages/eng-harness/tests/property/test_edit_cycle_sources.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_acceptance_entry.py"
    # Amendment B-354: the read-only entry point for A3 and A7 on real journals (spec AC35), about 70 lines; 80 -> 150.
    max_changed_lines: 150
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/edit_cycle/test_prompts.py::test_scenarios_within_one_prompt"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_prompts.py::test_unclassified_messages_use_the_prompt"
      - "packages/eng-harness/tests/property/test_edit_cycle_sources.py::test_generated_change_sets_all_sourced"
      - "packages/eng-harness/tests/unit/edit_cycle/test_acceptance_entry.py::test_audit_and_count_read_run_folder"
      - "packages/eng-harness/tests/unit/edit_cycle/test_acceptance_entry.py::test_entry_is_read_only_and_exit_codes"
    covers: [AC25, AC26, AC35]
    depends_on: [T9, T10]
  - id: T12
    title: Replay test and crash matrix of the workflow (A6)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/tests/replay/edit_cycle/__init__.py"
      - "packages/eng-harness/tests/replay/edit_cycle/test_replay.py"
      - "packages/eng-harness/tests/replay/edit_cycle/test_crash_matrix.py"
      - "packages/eng-harness/tests/data/journals/edit_cycle/**"
    max_changed_lines: 60
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/replay/edit_cycle/test_crash_matrix.py::test_every_step"
      - "packages/eng-harness/tests/replay/edit_cycle/test_replay.py::test_recorded_journal_replays"
    covers: [AC27, AC28]
    depends_on: [T9]
---

# Implementation plan: eng-harness model edit cycle (spec 0007)

## 1. Approach

The spec is [0007](../specs/0007-model-edit-cycle.md); the owner-facing description is the
[workflow spec](../workflows/model-edit-cycle.md). `max_changed_lines` counts non-test, non-generated lines, as in
plans 0001 to 0006; golden data, journals and fixtures are test data.

Build the data first and the R1 parts early: the kinds and the change-set model (T1a, T1b), then the four calcs (T2 to T4),
which carry the engineering checks and go to the owner for review as soon as they merge. The adapter additions (T5)
and the engine amendments (T6) are small, separate and reviewable on their own; T6 waits until the engine spec is
amended in its own documents pull request (spec Q2, Q3, Q5 and spec 0004 Q7), as B-068 does for earlier amendments.
The decision points and rules (T7) are R1 and reviewed separately from the block. The block is split in two (T8 steps
1 to 10, T9 steps 11 to 17 and the loop), each tested end to end against the synthetic CSI fake server process. The
report, audit, prompt counter and timings (T10) are pure functions over the journal. T11 and T12 add the acceptance
support and the replay suite, mostly tests.

Reuse (spec §2): everything from plans 0001 to 0006; no code is copied from Sasaah or elsewhere (A12). Tests use the
synthetic CSI fake of plan 0002 T4 (extended by T5 here with the `Analysis Messages` table, design replies, a lock
after analysis, and a hand-edit hook that changes the fake model between calls), the engine's fake ports for
approvals and inputs with scripted answers, the contract `FixedClock` and `SeededIdSource`, and real SQLite stores in
temporary workspaces.

## 2. Tasks

**T1a Kinds and T1b change-set model** (spec §4.2, §4.3.1, §4.3.2). T1a: `harness.change_set_check/1`,
`harness.analysis_summary/1`, `harness.csi_name_lists/1` in `kinds/edit_cycle.py`, registered in `_kinds.py`, with
fixtures under `tests/data/kinds/edit_cycle/`. T1b: `ChangeSetDraft`, the item models, value models (basis path or
number with unit) and the refused kinds as parseable models. No logic beyond Pydantic validation. Amendment (B-386):
the former T1 is split because it measured 562 lines against 320 (B-195).

**T2 `harness.change_set_check`** (spec §4.4.1, rules K1 to K7). Golden cases for resolution, unknown names,
duplicates, bounds (including the unit-scale case of baseline د6), missing or unconfirmed sources, conflicts with
engineer changes, and every refused kind with its gap id. A verification record from the spec 0003 template, for the
owner. Calc ships `draft`.

**T3 `harness.expected_effects`** (spec §4.4.2). The projection per kind, golden cases per kind and a property test
for item order. Ships `draft`.

**T4 Host design verdicts and analysis summary** (spec §4.4.3, §4.4.4). Steel mapping by comparison with
`limits.ratio_limit`; concrete gives `NEEDS_ENGINEER` (gap EC-G2); messages `unclassified` until the local test (gap
EC-G3). Golden cases with synthetic replies whose field names follow the S-12 inventory. Ship `draft`.

**T5 Adapter additions** (spec §4.10, Q1). `csi_read_model_state`, `csi_open_revision`, `csi_read_analysis_messages`
and the `as_new_revision` argument of `csi_save_model`; allowlist entries (no escape hatch: each composes allowlisted
tools only, checked by plan 0002's allowlist contract test); fake extensions.

**T6 Engine amendments** (spec AC33). `WorkflowDef.copy_on_open` and `basis_fields` (deriving `required_basis`);
`model_saved` for tool steps with action `save`; a save passed `under=` an approval is re-checked and continues the
approval's write chain (with the engine's `p~post.save` results), and a save to a new file gets no
`approve_each_write` preview (spec Q3); an approval resolved by the mode never satisfies an always-ask step.
Starts only after the engine spec amendment is merged. Amendment B-415: that amendment is work item B-415 (engine spec
§4.2, §4.6 "Tool saves", §4.7, §4.8 `ToolInfo.saves_new_file`, §4.9; AC70 to AC75, one per test of this task;
§11 Q26 to Q30). It adds `ports.py` (`saves_new_file`, default false) and `engine/_ctx_impl.py` (only the calls into
the new hooks) to this task's files; the CSI override and the `saved_file` summary are T5's (spec §4.10).

**T7 Points and rules** (spec §4.6). Three decision points with their state models, two rules (`rb.pass`,
`am.clean`) with typical and boundary tests, lock entries. Rules ship `draft` for the owner's review.

**T8 Workflow part 1** (spec §4.2, §4.5 steps 1 to 10, §4.7, §4.8). Input and output models, `basis_fields`, the
child blocks `read_state`, `obtain_change_set` and `apply_change_set` (with D-2 and the approval-void loop), and the
blank template's `ask_each_run` list (paths only, no value, spec 0004 §4.8). If plan 0004 T9 has already pinned the
template, the new pin is a golden change: the pull request carries the golden diff report and the change goes to the
owner queue (process/05 §5); if T9 has not merged yet, T9 takes the list from spec §4.8 and this task does not touch
the template. Tests drive the child blocks through test
workflows defined in `tests/workflow/edit_cycle/conftest.py`.

**T9 Workflow part 2** (spec §4.5 steps 11 to 17, §4.6, §4.7). `run_and_summarize` (analysis, design, results, D-3,
summaries; D-2 and D-3 are never open together, spec §4.6), the engineer turn, the cycle loop, promotion and sign-off in
`_finish.py`, and the full-workflow tests. `test_unlock_under_change_set_approval` expects the interim `HOST_LOCKED`
stop until plan 0002 T15 (ADR-0031) merges, then the approved unlock; the test states both and is switched with T15.

**T10 Report and B-1 support** (spec §4.9). Renderers for the kinds of T1a and value cells with sources (spec 0006
AC52), `audit_value_sources`, `count_prompts`, `edit_cycle_timings`, the timings section and
`report/cycle-timings.json` (base names only).

**T11 Acceptance support** (spec AC25, AC26). The prompt-count check over the workflow scenarios of T8 and T9 (the
A7 bound on the normal paths of spec §4.9, failure and escalation paths counted and reported) and the
property test over generated change sets; the needs-local-test items of spec §12 in `docs/local-testing.md`.
Amendment B-354 (spec AC35, Q11): `python -m eng_harness.report` with `audit-sources RUN_DIR` and
`count-prompts RUN_DIR`, a read-only wrapper over the T10 functions so that the owner can run A3 and A7 on the
journals of the local B-1 runs; no seventh `eng-harness` command. `docs/local-testing.md` names the command form
`uv run --package eng-harness python -m eng_harness.report ...` (spec 0006 §4.1).

**T12 Replay and crash matrix** (spec AC27, AC28). A two-cycle run killed at every step in a worker process (plan 0001
T19's harness) and resumed with the same scripted answers; the replay test over a journal recorded by the
uninterrupted run.

## 3. Dependencies

- Runtime: none new. Development: none new (Hypothesis and pytest from plan 0001 T1).
- Work items of other plans that must be merged before each task (same plan ids as in their files):

| Task | Needs merged |
|---|---|
| T1a, T1b | eng-contract T11, T12 (kinds); plan 0001 T1, T3 (`_kinds.py`); plan 0003 T4 (kinds package) |
| T2 | plan 0003 T1 to T6 (calc framework, hash, approvals, port, rules test, golden loader), T8 (difference report payload); plan 0004 T5 (`FieldSpec`) |
| T3 | plan 0003 T9 (`harness.expected_effects/1`, read-back check) |
| T4 | plan 0003 T10 (design summary); plan 0002 T13 (design results and analysis kinds) |
| T5 | plan 0002 T4, T11 to T14 (fake, reader, edits, analysis, reconciliation) |
| T6 | plan 0001 T5, T15, T16 (registry, approvals, modes); the engine spec amendment, work item B-415 (documents pull request; engine spec AC70 to AC75) |
| T7 | plan 0005 T1 to T4, T7 (points, rules, cascade core) |
| T8 | plan 0001 T10 to T17; plan 0002 T19; plan 0004 T8 to T10; plan 0005 T10; plan 0006 T7 (answer models) |
| T9 | plan 0001 T16 (promotion); plan 0002 T13, T15 (for the final unlock test); plan 0006 T10 (engineer-turn labels) |
| T10 | plan 0006 T11 to T13 (report model, sections, document) |
| T11 | plan 0006 T14 is not needed: the tests drive the engine directly |
| T12 | plan 0001 T19 (crash-matrix worker); plan 0002 T19 |

## 4. Verification

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` exists; until then, from `packages/eng-harness/`,
  `uv run ruff format --check`, `uv run ruff check`, `uv run mypy --strict src tests`, `uv run pytest` with coverage.
  The pull request links its CI run (process/05 §8).
- Fake-host workflow and replay tests on every pull request (process/05 §2: the workflow has both); mutation on the R1
  modules `calcs/edit_cycle/**`, `rules/edit_cycle.py`, `adapters/csi/_read_state_tool.py` and `_revisions.py`.
- Engineering content: the four calcs, the two rules and the field list are R1, ship `draft`, and go to the owner queue
  with their verification records (ADR-0028 §4). No agent adds an `approvals.yaml` entry.
- Live acceptance needed before the first release (spec §12, all listed in `docs/local-testing.md` by T11): a full
  cycle on a copy of a real model with ETABS 22 and the pinned `sasaah-csi-mcp` build; acceptance A1 to A7 on
  benchmark B-1 (all of A4 is local); ETABS and process kills (A6); promotion with the original open.
- Review: each pull request by a subagent that did not write it, with the correctness, Python, type-design,
  silent-failure and test lenses; T2 to T5 and T7 also against the R1 rules (no literal, cited method, golden sources);
  T5 and T6 also with the security lens (allowlist, always-ask). Second-family review and owner approvals are
  `awaiting owner`.

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; a revert removes it and its dependants (T8 and T9 depend
on T2 to T7). Until T8 merges, nothing registers the workflow. Calcs, points, rules and blocks are versioned with lock
files, so a fix after runs have been journaled is a new version; old journals keep replaying against the version they
recorded (engine §4.2) or stop with `ReplayDivergence`, never silently.
