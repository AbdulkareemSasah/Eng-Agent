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
    # Amendment (B-417, documents only): calcs/__init__.py registers the calc in REGISTRY (spec 0003 4.2, no discovery); the bounds paths are the unit-suffixed names of spec 4.8.
    # Amendment (B-463, documents only): section 3 names eng-contract plan 0001 T19 (B-464) and calcs T8b as cross-plan dependencies.
    # Amendment (B-493, documents only): the calc-module rules test holds the edit-cycle entries of spec 0003 4.3: the
    # change-set model module, and kinds.edit_cycle if not already present (plan 0013 T2 adds it under B-462); test file, not counted.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.edit_cycle, eng_harness.calcs.edit_cycle.change_set_check (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/change_set_check.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.change_set_check.md"
      - "packages/eng-harness/tests/golden/edit_cycle/__init__.py"
      - "packages/eng-harness/tests/golden/edit_cycle/test_change_set_check.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/check-*.json"
      - "packages/eng-harness/tests/unit/edit_cycle/test_change_set.py"
      - "packages/eng-harness/tests/rules/test_calc_modules.py"  # the entries of spec 0003 4.3 for the edit-cycle calcs (amendment B-493)
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/golden/edit_cycle/test_change_set_check.py::test_golden_cases"
      - "packages/eng-harness/tests/unit/edit_cycle/test_change_set.py::test_refused_kinds_name_their_gap"
    covers: [AC4, AC5, AC6, AC7]
    depends_on: [T1b]
  - id: T3
    title: Calc harness.expected_effects (projection of a resolved change set)
    # Amendment (B-417, documents only): calcs/__init__.py registers the calc in REGISTRY (spec 0003 4.2); after T2, which edits the same file.
    # Amendment (B-498, documents only): spec 4.4.2 projects combination edits per item under the D2 item keys, a set on
    # an object the state lacks as add, unique effect item ids, values from the inputs change_set and basis; covers AC36
    # (a combination edit passes read-back, test in the task's own golden file); max_changed_lines raised from 260 to 330.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.edit_cycle, eng_harness.calcs.edit_cycle.expected_effects (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/expected_effects.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.expected_effects.md"
      - "packages/eng-harness/tests/golden/edit_cycle/test_expected_effects.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/effects-*.json"
      - "packages/eng-harness/tests/property/test_expected_effects.py"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/edit_cycle/test_expected_effects.py::test_golden_cases"
      - "packages/eng-harness/tests/golden/edit_cycle/test_expected_effects.py::test_combination_edit_reads_back"
      - "packages/eng-harness/tests/property/test_expected_effects.py::test_order_independent"
    covers: [AC8, AC36]
    depends_on: [T2]
  - id: T4
    title: Calcs harness.host_design_verdicts and harness.analysis_summary
    # Amendment (B-417, documents only): calcs/__init__.py registers both calcs in REGISTRY (spec 0003 4.2); depends on T3 so that T2, T3 and T4 edit the shared registry files in turn; reads limits.ratio_limit_ratio (spec 4.8).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.edit_cycle, eng_harness.calcs.edit_cycle.analysis_summary and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
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
    depends_on: [T3]
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
    # §4.8, §4.9 and rules EC1 to EC6 (§3.9, covered by spec AC33); ports.py gains ToolInfo.saves_new_file, _ctx_impl.py only the calls into the hooks.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.block, eng_harness.engine (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/block.py"
      - "packages/eng-harness/src/eng_harness/engine/_modes.py"
      - "packages/eng-harness/src/eng_harness/engine/_invariants.py"
      - "packages/eng-harness/src/eng_harness/engine/_approvals.py"
      - "packages/eng-harness/src/eng_harness/ports.py"  # ToolInfo.saves_new_file, engine §4.8 (amendment B-415)
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"  # calls into the copy-on-open and tool-save hooks (amendment B-415)
      - "packages/eng-harness/src/eng_harness/engine/_hoststate.py"  # resumed tool save: compared with its result's provenance.host, saved_file mismatch, engine §4.6 "At a resume" (amendment B-415)
      - "packages/eng-harness/src/eng_harness/engine/_runner.py"  # model_saved of a resumed tool save appended after the host-state check, before the root block, engine §4.5.1 step 8a (amendment B-415)
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py"
    # Amendment (B-415 review fix, documents only): block.py imports FieldSpec from eng_harness.basis._fields (engine
    # §4.1.2), and the gate also runs tests/rules/test_decision_imports.py::test_types_module_is_block_safe unchanged.
    # Amendment (B-415 review fix, documents only): _hoststate.py and _runner.py added for EC2's resume cases (both
    # extended from plan 0001 T11c, split from T11b by B-427); max_changed_lines raised from 200 to 300 for the two added modules (tests do not count).
    max_changed_lines: 300
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
    # Amendment (B-417, documents only): found by spec 0005 discovery (decisions._points.discover() over eng_harness.workflows, decisions._rules.discover() over eng_harness.rules), so no decisions/ file changes; rule tests move to tests/rules/test_edit_cycle.py (spec 0005 AC12); the two phase-1 tests of tests/unit/decisions/test_points.py and two of tests/unit/decisions/test_rules.py are isolated from the shipped package; point and rule names follow spec 0005 AC1 and AC9.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.rules, eng_harness.rules.edit_cycle, eng_harness.workflows and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_points.py"
      - "packages/eng-harness/src/eng_harness/rules/__init__.py"  # empty package marker; listed because AC10c covers only tests/ (amendment B-417)
      - "packages/eng-harness/src/eng_harness/rules/edit_cycle.py"
      - "packages/eng-harness/src/eng_harness/decisions.lock.json"
      - "packages/eng-harness/src/eng_harness/rules.lock.json"
      - "packages/eng-harness/tests/rules/test_edit_cycle.py"
      - "packages/eng-harness/tests/unit/decisions/test_points.py"  # isolates the two phase-1 discovery tests from the shipped points (amendment B-417)
      - "packages/eng-harness/tests/unit/decisions/test_rules.py"  # isolates two phase-1 discovery tests from the shipped rules and points (amendment B-417)
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/rules/test_edit_cycle.py::test_pass_typical"
      - "packages/eng-harness/tests/rules/test_edit_cycle.py::test_pass_boundary"
      - "packages/eng-harness/tests/rules/test_edit_cycle.py::test_clean_typical"
      - "packages/eng-harness/tests/rules/test_edit_cycle.py::test_clean_boundary"
    covers: [AC18]
    depends_on: [T1b]
  - id: T8
    title: Workflow part 1 - definition, basis fields, steps 1 to 10 (read, differences, change set, approval, apply, read back)
    # Amendment (B-417, documents only): basis_fields and the blank template's ask_each_run use the unit-suffixed paths of spec 4.8; registration and blocks.lock.json move to T9 (this task is at the 400-line cap).
    # Amendment (B-463, documents only): section 3 names eng-contract plan 0001 T19 (B-464) as a cross-plan dependency.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.templates, eng_harness.templates.shipped, eng_harness.workflows and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_cycle.py"
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
    title: Workflow part 2 - steps 11 to 17 (analysis, design, summaries, engineer turn, promotion, sign-off), the cycle loop and registration
    # Amendment (B-417, documents only): registers the shipped workflow: workflows/__init__.py exports the blocks and block.discover() reads it lazily (spec 4.2), so blocks.lock.json gains the entries; about 15 lines, 380 to 395; tests/unit/test_block.py::test_main_writes_the_lock is isolated from the shipped blocks, about 3 lines, 395 to 400.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.workflows, eng_harness.workflows.model_edit_cycle (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/block.py"
      - "packages/eng-harness/src/eng_harness/workflows/__init__.py"
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
      - "packages/eng-harness/tests/unit/edit_cycle/test_definition.py"
      - "packages/eng-harness/tests/unit/test_block.py"  # isolates test_main_writes_the_lock from the shipped blocks (amendment B-417)
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/edit_cycle/test_definition.py::test_workflow_registered"
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
    covers: [AC1, AC9, AC12, AC14, AC15, AC16, AC19, AC20, AC21, AC22, AC23, AC34]
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
    # Amendment (B-417, documents only): folder renamed from tests/replay/edit_cycle/ so that its package name differs from tests/unit/edit_cycle/ (mypy duplicate module); no tests/replay/__init__.py.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/tests/replay/edit_cycle_replay/__init__.py"
      - "packages/eng-harness/tests/replay/edit_cycle_replay/test_replay.py"
      - "packages/eng-harness/tests/replay/edit_cycle_replay/test_crash_matrix.py"
      - "packages/eng-harness/tests/data/journals/edit_cycle/**"
    max_changed_lines: 60
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/replay/edit_cycle_replay/test_crash_matrix.py::test_every_step"
      - "packages/eng-harness/tests/replay/edit_cycle_replay/test_replay.py::test_recorded_journal_replays"
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
owner. Calc ships `draft`. Amendment (B-417): the task registers the calc in `REGISTRY` through `calcs/__init__.py`
(spec 0003 §4.2: explicit registration, no discovery), so the calc lock test and `ctx.calc` find it; the bounds are the
unit-suffixed paths of spec §4.8 (`bounds.thickness_min_mm`, `bounds.line_load_min_kN_m`, `bounds.area_load_min_kPa`,
`bounds.ratio_min_ratio` and their `_max` pairs). Amendment (B-493): the task adds the edit-cycle entries of spec
0003 §4.3 to `tests/rules/test_calc_modules.py`: `eng_harness.workflows.model_edit_cycle._change_set` by that module's
name, never its package, and `eng_harness.kinds.edit_cycle` if not already present (plan 0013 T2 adds the same entry
under amendment B-462); T3 uses the same imports without further amendment.

**T3 `harness.expected_effects`** (spec §4.4.2). The projection per kind, golden cases per kind and a property test
for item order. Ships `draft`. Amendment (B-417): registers the calc in `REGISTRY` through `calcs/__init__.py`,
after T2. Amendment (B-498): combination edits are projected per item under the item keys of spec 0003 §4.7 D2, a
`set` on an object the step 3 state lacks is an `add`, values come from the inputs `change_set` and `basis`, and
`test_combination_edit_reads_back` runs the merged read-back check (plan 0003 T9) on the projected effects (AC36); the
read-back calc is unchanged.

**T4 Host design verdicts and analysis summary** (spec §4.4.3, §4.4.4). Steel mapping by comparison with
`limits.ratio_limit_ratio` (amendment B-417, spec §4.8); concrete gives `NEEDS_ENGINEER` (gap EC-G2); messages `unclassified` until the local test (gap
EC-G3). Golden cases with synthetic replies whose field names follow the S-12 inventory. Ship `draft`. Amendment
(B-417): registers both calcs in `REGISTRY` through `calcs/__init__.py`; it depends on T3 so that T2, T3 and T4 edit
`calcs/__init__.py`, `calcs/edit_cycle/__init__.py` and `calcs.lock.json` one after another.

**T5 Adapter additions** (spec §4.10, Q1). `csi_read_model_state`, `csi_open_revision`, `csi_read_analysis_messages`
and the `as_new_revision` argument of `csi_save_model`; allowlist entries (no escape hatch: each composes allowlisted
tools only, checked by plan 0002's allowlist contract test); fake extensions.

**T6 Engine amendments** (spec AC33). `WorkflowDef.copy_on_open` and `basis_fields` (deriving `required_basis`);
`model_saved` for tool steps with action `save`; a save passed `under=` an approval is re-checked and continues the
approval's write chain (with the engine's `p~post.save` results), and a save to a new file gets no
`approve_each_write` preview (spec Q3); an approval resolved by the mode never satisfies an always-ask step.
Starts only after the engine spec amendment is merged. Amendment B-415: that amendment is work item B-415 (engine spec
§4.2, §4.6 "Tool saves", §4.7, §4.8 `ToolInfo.saves_new_file`, §4.9; rules EC1 to EC6 of its §3.9, one per test of
this task, which add no engine criterion: spec AC33 covers them;
§11 Q30 to Q34). It adds `ports.py` (`saves_new_file`, default false) and `engine/_ctx_impl.py` (only the calls into
the new hooks), `engine/_hoststate.py` and `engine/_runner.py` (EC2's resume cases: the comparison with a resumed
save's result and the `model_saved` appended after the host-state check; both from plan 0001 T11c, split from T11b by B-427) to this task's
files; the CSI override and the `saved_file` summary are T5's (spec §4.10).
Review fix B-415: `block.py` takes `FieldSpec` from `eng_harness.basis._fields`, never from the `eng_harness.basis`
package (engine §4.1.2), so spec 0005 AC42 holds; T6 runs
`tests/rules/test_decision_imports.py::test_types_module_is_block_safe` unchanged among its checks.

**T7 Points and rules** (spec §4.6). Three decision points with their state models, two rules
(`edit_cycle_readback_result.pass`, `edit_cycle_analysis_messages.clean`; the point names `edit_cycle_readback_result`,
`edit_cycle_analysis_messages` and `edit_cycle_engineer_turn` pass spec 0005 AC1, which allows no dot, and each rule id
starts with its point name, spec 0005 AC9; amendment B-417) with typical and boundary tests, lock entries. Rules ship `draft` for the owner's review. Amendment
(B-417): the points and rules are found by the discovery of spec 0005 (amendment B-411): `decisions._points.discover()`
imports every module under `eng_harness.workflows`, so the module-level `DecisionPoint` objects of
`workflows/model_edit_cycle/_points.py` enter the real point registry, and `decisions._rules.discover()` imports every
module under `eng_harness.rules`, so the rules of `rules/edit_cycle.py` enter the real rule registry. The task edits no
file of `decisions/`; it regenerates `decisions.lock.json` and `rules.lock.json` with
`uv run python -m eng_harness.decisions --write-lock` (spec 0005 §4.4). The task creates `rules/__init__.py` as an empty
package marker and lists it in its files: the gate's empty-marker exception (gate spec AC10c) covers only `tests/`,
not `src/`, so the file is in scope only because the task names it. The rule tests are `tests/rules/test_edit_cycle.py` with
`test_pass_typical`, `test_pass_boundary`, `test_clean_typical` and `test_clean_boundary` (spec AC18, spec 0005 AC12,
whose `missing_rule_tests` looks for exactly these names); the test module imports `eng_harness.rules.edit_cycle` at
module level, so it fails at the merge base for the right reason (TF004). Once the three points exist, two merged
phase-1 tests of `tests/unit/decisions/test_points.py` (plan 0005 T2) would fail, because they pin an empty discovery
against the real package: `test_discover_is_empty_without_workflows` asserts `discover().points == ()`, and
`test_main_requires_write_lock_flag_and_writes` runs `main(["--write-lock"])`, which writes `discover()`, and expects an
empty lock. The task therefore lists that file and rewrites both tests so that they no longer depend on the shipped
package, keeping what each checks: the first monkeypatches `importlib.util.find_spec` to report `eng_harness.workflows`
absent and still expects an empty registry (the "empty when the package is absent" branch of spec 0005 §4.2), and the
second monkeypatches `_points.discover` to return an empty `PointRegistry` and still expects an empty lock. For the same reason
two merged tests of `tests/unit/decisions/test_rules.py` (plan 0005 T4) would fail once the two rules exist:
`test_discover_is_empty_without_rules_package` asserts `discover().rules == ()`, and
`test_write_lock_command_writes_both_and_refuses_a_bump` runs `command.main(["--write-lock"])`, which writes
`_points.discover()` and `_rules.discover()`, and expects both locks empty. The task lists that file too and rewrites
both tests the same way, keeping their expectations: the first monkeypatches `importlib.util.find_spec` to report
`eng_harness.rules` absent and still expects an empty registry (spec 0005 §4.4), and the second monkeypatches
`_points.discover` and `_rules.discover` to return empty registries before the first write and still expects both
locks empty. That the real discovery finds the three points and the two rules is checked by
`tests/contract/test_decision_lock.py` and `tests/contract/test_rule_lock.py` against the regenerated locks.

**T8 Workflow part 1** (spec §4.2, §4.5 steps 1 to 10, §4.7, §4.8). Input and output models, `basis_fields`, the
child blocks `read_state`, `obtain_change_set` and `apply_change_set` (with D-2 and the approval-void loop), and the
blank template's `ask_each_run` list (paths only, no value, spec 0004 §4.8). Amendment (B-417): plan 0004 T9 has pinned
the template with an empty `ask_each_run`; this task fills it with the unit-suffixed paths of spec §4.8, and the new pin
is a golden change: the pull request carries the golden diff report and the change goes to the owner queue
(process/05 §5). The same paths are the `FieldSpec`s of `basis_fields` (spec 0004 AC21). Registration of the workflow
is T9's (this task is at its 400-line cap): `block.discover()` stays empty here and `blocks.lock.json` is unchanged, so
`test_workflow_definition` checks the definition and not the lock. Tests drive the child blocks through test
workflows defined in `tests/workflow/edit_cycle/conftest.py`.

**T9 Workflow part 2** (spec §4.5 steps 11 to 17, §4.6, §4.7). `run_and_summarize` (analysis, design, results, D-3,
summaries; D-2 and D-3 are never open together, spec §4.6), the engineer turn, the cycle loop, promotion and sign-off in
`_finish.py`, and the full-workflow tests. `test_unlock_under_change_set_approval` expects the interim `HOST_LOCKED`
stop until plan 0002 T15 (ADR-0031) merges, then the approved unlock; the test states both and is switched with T15.
Amendment (B-417): this task registers the shipped workflow (spec §4.2): `workflows/__init__.py` exports the blocks of
`model_edit_cycle` (the workflow and its child blocks, `run_and_summarize` and those of `_finish.py` included) as one
tuple, and `block.discover()` builds its `Registry` from it, importing `eng_harness.workflows` inside the function to
avoid an import cycle. `blocks.lock.json` is written with `python -m eng_harness.block --write-lock`, and
`tests/contract/test_block_lock.py::test_lock_matches_registry` then covers the `model_edit_cycle` blocks;
`test_definition.py::test_workflow_registered` checks that `discover()` holds them (the lock part of AC1). The public
module `eng_harness.workflows` goes into `public_modules`. Plans 0010 T9 and 0013 T11 and T13 add their blocks to the same tuple.
Plan 0006 T18a binds the command line's workflow-registry default to this registry (amendment B-471), so `run` finds
the model edit cycle without plan 0010 T9.
The merged test `tests/unit/test_block.py::test_main_writes_the_lock` runs `main(["--write-lock"])`, which writes
`discover()`, and expects `"[]\n"`; once `discover()` returns the shipped blocks it would fail, so the task lists that file
and monkeypatches `block.discover` there to return an empty `Registry`, keeping the expectation (what the shipped blocks
are is checked by `test_block_lock.py` and `test_workflow_registered`).

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
| T2 | plan 0003 T1 to T6 (calc framework, hash, approvals, port, rules test, golden loader), T8b (difference report calc, split by B-458); plan 0004 T5 (`FieldSpec`); B-417 (unit-suffixed basis paths, spec §4.8); eng-contract plan 0001 T19 (work item B-464, the path rule of spec Q12 (a), owner decision OQ-Q44), because the `_kN_m` and `_kPa` bounds cannot be stored in `basis.design_basis/1` before it |
| T3 | plan 0003 T9 (`harness.expected_effects/1`, read-back check) |
| T4 | plan 0003 T10 (design summary); plan 0002 T13 (design results and analysis kinds); B-417 (`limits.ratio_limit_ratio`, spec §4.8) |
| T5 | plan 0002 T4, T11 to T14 (fake, reader, edits, analysis, reconciliation) |
| T6 | plan 0001 T5, T15, T16 (registry, approvals, modes), T11c (split from T11b by B-427; `_hoststate.py`, `_runner.py`: host-state check and resume order, extended for EC2, amendment B-415); the engine spec amendment, work item B-415 (documents pull request; engine spec §3.9 rules EC1 to EC6, covered by spec AC33) |
| T7 | plan 0005 T1 to T4, T7 (points, rules, cascade core; T2 and T4 carry the discovery of spec 0005 §4.2 and §4.4) |
| T8 | plan 0001 T10 to T17; plan 0002 T19a (amendment B-475); plan 0004 T8 to T10; plan 0005 T10; plan 0006 T7 (answer models); B-417 (unit-suffixed basis paths, spec §4.8); eng-contract plan 0001 T19 (work item B-464, owner decision OQ-Q44) and the renames in specs 0002 and 0003 of spec Q12 (owner queue, no work item yet), so that a basis holding the §4.8 paths can be frozen and the calcs' `basis_fields` equal the declared paths |
| T9 | plan 0001 T16 (promotion); plan 0002 T13, T15 (for the final unlock test); plan 0006 T10 (engineer-turn labels) |
| T10 | plan 0006 T11 to T13 (report model, sections, document) |
| T11 | plan 0006 T14 is not needed: the tests drive the engine directly |
| T12 | plan 0001 T19 (crash-matrix worker); plan 0002 T19a (amendment B-475) |

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
on T2 to T7). Until T9 merges, nothing registers the workflow (amendment B-417: `block.discover()` reads `workflows/__init__.py`,
which T9 creates). Calcs, points, rules and blocks are versioned with lock
files, so a fix after runs have been journaled is a new version; old journals keep replaying against the version they
recorded (engine §4.2) or stop with `ReplayDivergence`, never silently.
