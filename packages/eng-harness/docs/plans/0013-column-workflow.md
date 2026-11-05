---
id: plan-b083-column-workflow
issue: "B-083"
spec: packages/eng-harness/docs/specs/0013-column-workflow.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r3]  # r3 from the public_modules entries in pyproject.toml (amendment B-356)
tasks:
  - id: T1
    title: Column workflow kinds and request models
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.kinds, eng_harness.kinds.column_design, eng_harness.workflows and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/kinds/__init__.py"
      - "packages/eng-harness/src/eng_harness/kinds/column_design.py"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/_requests.py"
      - "packages/eng-harness/tests/contract/test_column_design_kinds.py"
      - "packages/eng-harness/tests/data/kinds/column_design/**"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_column_design_kinds.py::test_request_models"
      - "packages/eng-harness/tests/contract/test_column_design_kinds.py::test_kind_fixtures"
    covers: [AC3]
    depends_on: []
  - id: T2
    title: Calc harness.column_select with golden and property tests
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.column_design, eng_harness.calcs.column_design.column_select (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.column_select.md"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/column_select.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/golden/column_design/__init__.py"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py"
      - "packages/eng-harness/tests/data/golden/column_design/column-select-*.json"
      - "packages/eng-harness/tests/property/test_column_select.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-select-names]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-select-story-section]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-select-vertical-boundary]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-select-not-vertical]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-select-unknown-names]"
      - "packages/eng-harness/tests/property/test_column_select.py::test_permutation_invariant"
    covers: [AC4, AC5]
    depends_on: [T1]
  - id: T3
    title: Calc harness.column_demands (sign, axes, length, layout, not-checked reasons)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.column_design, eng_harness.calcs.column_design.column_demands (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.column_demands.md"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/column_demands.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py"
      - "packages/eng-harness/tests/data/golden/column_design/column-demands-*.json"
      - "packages/eng-harness/tests/unit/calcs/test_column_demands.py"
    max_changed_lines: 340
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-compression-tension]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-square-uniaxial]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-square-unequal-bars]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-reinforcement-limits-per-column]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-biaxial]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-not-checked]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-bar-area-from-basis]"
      - "packages/eng-harness/tests/unit/calcs/test_column_demands.py::test_refusals"
      - "packages/eng-harness/tests/unit/calcs/test_column_demands.py::test_axes_undeclared"
    covers: [AC6, AC7]
    depends_on: [T2]
  - id: T4
    title: Calc harness.column_review (members, governing references, changes)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.column_design, eng_harness.calcs.column_design.column_review (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.column_review.md"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/column_review.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py"
      - "packages/eng-harness/tests/data/golden/column_design/column-review-*.json"
      - "packages/eng-harness/tests/property/test_column_review.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-review-sources]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-review-two-ends]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-review-not-checked]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-review-changes]"
      - "packages/eng-harness/tests/property/test_column_review.py::test_ratios_are_referenced_not_computed"
    covers: [AC8]
    depends_on: [T2]
  - id: T5
    title: Calcs harness.column_section_match and harness.column_change_set
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.column_design, eng_harness.calcs.column_design.change_set and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.column_section_match.md"
      - "packages/eng-harness/docs/verification/calcs/harness.column_change_set.md"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/section_match.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/change_set.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py"
      - "packages/eng-harness/tests/data/golden/column_design/column-match-*.json"
      - "packages/eng-harness/tests/unit/calcs/test_column_section_match.py"
      - "packages/eng-harness/tests/unit/calcs/test_column_change_set.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-one]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-none]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-ambiguous]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-other-material]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-boundary]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-circular]"
      - "packages/eng-harness/tests/unit/calcs/test_column_section_match.py::test_size_must_be_rounding_result"
      - "packages/eng-harness/tests/unit/calcs/test_column_change_set.py::test_items_and_refusals"
    covers: [AC9, AC10]
    depends_on: [T2]
  - id: T6
    title: Code-pack route in the CalcPort for the three ACI 318-14 column checks
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/_calc/__init__.py"
      - "packages/eng-harness/src/eng_harness/_calc/_port.py"
      - "packages/eng-harness/src/eng_harness/_calc/_code_packs.py"
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/docs/adr/0004-workspace-code-packs.md"
      - "uv.lock"   # workspace root lock file (stated outside packages/eng-harness/)
      - "packages/eng-harness/tests/unit/calcs/test_code_pack_route.py"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/calcs/test_code_pack_route.py::test_batch_through_calcport"
      - "packages/eng-harness/tests/unit/calcs/test_code_pack_route.py::test_production_refused"
      - "packages/eng-harness/tests/unit/calcs/test_code_pack_route.py::test_only_listed_checks"
    covers: [AC13]
    depends_on: []
  - id: T7
    title: Calc harness.revit_column_update (plan of Revit type changes by reference)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.column_design, eng_harness.calcs.column_design.revit_update (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.revit_column_update.md"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/revit_update.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py"
      - "packages/eng-harness/tests/data/golden/column_design/revit-update-*.json"
      - "packages/eng-harness/tests/property/test_revit_column_update.py"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-update-no-change]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-update-reuse-type]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-update-new-type-shared]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-update-name-conflict]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-update-roles-unmapped]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-update-shapes]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-update-orientation-unverified]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-update-origin]"
      - "packages/eng-harness/tests/property/test_revit_column_update.py::test_permutation_invariant"
    covers: [AC11]
    depends_on: [T2]
  - id: T8
    title: Calc harness.revit_column_readback
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.column_design, eng_harness.calcs.column_design.revit_readback (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.revit_column_readback.md"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/revit_readback.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py"
      - "packages/eng-harness/tests/data/golden/column_design/revit-readback-*.json"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-readback-pass]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-readback-wrong-type]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-readback-value-mismatch]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-readback-unexpected-change]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[revit-readback-missing-and-not-read]"
    covers: [AC12]
    depends_on: [T7]
  - id: T9
    title: Decision points and rules of the column workflow
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.rules, eng_harness.rules.column_design, eng_harness.workflows and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/_points.py"
      - "packages/eng-harness/src/eng_harness/rules/column_design.py"
      - "packages/eng-harness/src/eng_harness/decisions.lock.json"
      - "packages/eng-harness/tests/unit/rules/test_column_design_rules.py"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/rules/test_column_design_rules.py::test_member_action_rules"
      - "packages/eng-harness/tests/unit/rules/test_column_design_rules.py::test_revit_rules"
      - "packages/eng-harness/tests/unit/rules/test_column_design_rules.py::test_lock"
    covers: [AC14]
    depends_on: [T1]
  - id: T10
    title: Engine and edit-cycle amendments (allowed modes, exported child blocks, generated change sets)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.block, eng_harness.calcs, eng_harness.calcs.edit_cycle and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/block.py"
      - "packages/eng-harness/src/eng_harness/errors.py"
      - "packages/eng-harness/src/eng_harness/engine/_runner.py"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_cycle.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/change_set_check.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/src/eng_harness/blocks.lock.json"
      - "packages/eng-harness/tests/unit/test_engine_column_amendments.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_exports.py"
      - "packages/eng-harness/tests/unit/calcs/test_change_set_check_v2.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_engine_column_amendments.py::test_allowed_modes_refused"
      - "packages/eng-harness/tests/unit/edit_cycle/test_exports.py::test_child_blocks_exported"
      - "packages/eng-harness/tests/unit/calcs/test_change_set_check_v2.py::test_accepts_generated_set"
    covers: [AC31, AC23]   # AC23 in part: the engine refusal; T13 holds the workflow test
    depends_on: [T1]
  - id: T11
    title: Workflow column_design part 1 - definition, basis fields, scope, review cycle (steps 1 to 10 and 15)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.workflows, eng_harness.workflows.column_design (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/_cycle.py"
      - "packages/eng-harness/src/eng_harness/blocks.lock.json"
      - "packages/eng-harness/tests/unit/column_design/__init__.py"
      - "packages/eng-harness/tests/unit/column_design/test_definition.py"
      - "packages/eng-harness/tests/rules/test_column_design_modules.py"
      - "packages/eng-harness/tests/workflow/column_design/__init__.py"
      - "packages/eng-harness/tests/workflow/column_design/conftest.py"
      - "packages/eng-harness/tests/workflow/column_design/test_cycle.py"
      - "packages/eng-harness/tests/workflow/column_design/test_checks.py"
      - "packages/eng-harness/tests/fakes/sasaah_csi/scenarios/columns/**"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/column_design/test_definition.py::test_workflow_definitions"
      - "packages/eng-harness/tests/rules/test_column_design_modules.py::test_modules_follow_block_rules"
      - "packages/eng-harness/tests/workflow/column_design/test_cycle.py::test_review_only_cycle"
      - "packages/eng-harness/tests/workflow/column_design/test_checks.py::test_gaps_reach_review"
    covers: [AC1, AC2, AC15, AC18]   # AC1 for column_design; T13 adds column_revit_update
    depends_on: [T3, T4, T6, T9, T10]
  - id: T12
    title: Workflow column_design part 2 - proposals, rounding and match, decisions, apply, design record (steps 11 to 14)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.workflows, eng_harness.workflows.column_design (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/_cycle.py"
      - "packages/eng-harness/src/eng_harness/blocks.lock.json"
      - "packages/eng-harness/tests/workflow/column_design/conftest.py"
      - "packages/eng-harness/tests/workflow/column_design/test_cycle.py"
      - "packages/eng-harness/tests/workflow/column_design/test_proposals.py"
      - "packages/eng-harness/tests/fakes/sasaah_csi/scenarios/columns/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/column_design/test_cycle.py::test_revise_applies_section"
      - "packages/eng-harness/tests/workflow/column_design/test_cycle.py::test_missing_section_then_hand_edit"
      - "packages/eng-harness/tests/workflow/column_design/test_cycle.py::test_hand_edit_kept_and_flagged"
      - "packages/eng-harness/tests/workflow/column_design/test_cycle.py::test_design_record"
      - "packages/eng-harness/tests/workflow/column_design/test_proposals.py::test_one_batched_screen"
    covers: [AC16, AC17, AC19, AC20, AC22]
    depends_on: [T5, T11]
  - id: T13
    title: Workflow column_revit_update (steps R1 to R9)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.workflows, eng_harness.workflows.column_design (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/_revit.py"
      - "packages/eng-harness/src/eng_harness/blocks.lock.json"
      - "packages/eng-harness/tests/unit/column_design/test_definition.py"
      - "packages/eng-harness/tests/workflow/column_design/conftest.py"
      - "packages/eng-harness/tests/workflow/column_design/test_revit_update.py"
      - "packages/eng-harness/tests/fakes/sasaah_revit/scenarios/columns/**"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/column_design/test_revit_update.py::test_mode_refused"
      - "packages/eng-harness/tests/workflow/column_design/test_revit_update.py::test_etabs_changed_after_design"
      - "packages/eng-harness/tests/workflow/column_design/test_revit_update.py::test_update_by_reference"
      - "packages/eng-harness/tests/workflow/column_design/test_revit_update.py::test_lengths_by_reference"
      - "packages/eng-harness/tests/workflow/column_design/test_revit_update.py::test_unmatched_never_written"
      - "packages/eng-harness/tests/workflow/column_design/test_revit_update.py::test_declined_and_readback_failure"
    covers: [AC1, AC23, AC24, AC25, AC26, AC27, AC28]   # AC1 for column_revit_update
    depends_on: [T7, T8, T12]
  - id: T14
    title: Report renderers, verdict-source audit and the local-testing list
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.report (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_column_design.py"
      - "packages/eng-harness/src/eng_harness/report/_sections.py"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/tests/unit/report/test_column_design_report.py"
      - "packages/eng-harness/tests/workflow/column_design/test_audits.py"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/report/test_column_design_report.py::test_sections"
      - "packages/eng-harness/tests/workflow/column_design/test_audits.py::test_value_and_verdict_sources"
    covers: [AC21, AC30]
    depends_on: [T13]
  - id: T15
    title: Replay crash matrix of both workflows
    files:
      - "packages/eng-harness/tests/replay/column_design/**"
    max_changed_lines: 60
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/replay/column_design/test_resume.py::test_crash_matrix_design"
      - "packages/eng-harness/tests/replay/column_design/test_resume.py::test_crash_matrix_revit"
    covers: [AC29]
    depends_on: [T13]
---

# Implementation plan: the column workflow (`column_design`, `column_revit_update`)

## 1. Approach

The workflow is composed from parts that other plans build: the edit cycle's child blocks and calcs
([plan 0007](0007-model-edit-cycle.md)), the calcs framework and `harness.section_round`
([plan 0003](0003-calcs.md)), the decision layer ([plan 0005](0005-decisions.md)), the Revit adapter and
`harness.frame_element_map` ([plan 0011](0011-revit-adapter.md)), and the ACI 318-14 column checks
([structural-codes plan 0004](../../../structural-codes/docs/plans/0004-aci318-14-column-checks.md)). This plan adds the
column-specific kinds, six calcs, a code-pack route, decision points, two blocks, the report parts and the tests.

Risky parts first. The R1 calcs come before any workflow code, each with hand-derived golden cases: the selection
(T2), the demands with their sign and axis rules (T3, the riskiest: a wrong sign or axis is a wrong verdict), the
review (T4), the proposal path (T5), and the Revit plan and read-back (T7, T8). The code-pack route (T6) and the
amendments to the engine and the edit cycle (T10) are small shared changes that land before the blocks, each with the
regression proof that the existing suites (engine, edit cycle) pass unchanged. Then the blocks: the review cycle
(T11), the proposal and apply path (T12), and the Revit run (T13). The report and audits (T14) and the crash matrix
(T15) close the plan.

Every task is test-first ([process/05](../../../../design/process/05-testing-and-verification.md) §9): its first commit
holds the tests of `tests_first` (and, for calc tasks, the golden files with hand-derived expected values and a
`derivation` field), and they fail on `build/v1`. `max_changed_lines` counts non-test code; a task that measures over
is split by a plan amendment in its own reviewed pull request (decision D-12). Several tasks edit `CHANGELOG.md`,
`calcs.lock.json`, `blocks.lock.json` or the shared golden test module, so they merge one after another;
`depends_on` shows the needed order. Nothing in this plan needs a host program in CI.

R1 content in bootstrap mode ([ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4): calcs and
rules are registered `draft` and no approval is added; `src/eng_harness/calcs/`, `src/eng_harness/rules/` and
`tests/data/golden/` are protected paths, so each calc and rule pull request is R1 and lists the calc ids and content
hashes for the owner queue. The code checks stay `draft` in their pack (CK-AC5); every workflow test runs in the
`trial` run class. No golden value comes from a code text: the column-demand cases test conversions (sign, axis
selection, bar count, length), not code capacities.

## 2. Tasks

**T1 Kinds and requests** (spec §4.2, §4.3). The eight `harness.*` kinds with strict models and registration beside
the edit-cycle kinds; `ColumnScopeRequest`, `ColumnLayoutRequest` and `ColumnProposalRequest`, with the refused
variants (`spiral`, `special_seismic: true`) parsed so the engineer sees a reasoned refusal with the gap id.

**T2 `harness.column_select`** (spec §4.4.1). Name and story-section resolution, the exact verticality test against
`compare.length`, shape and material per column, issues, and the shared golden test module for the column calcs.

**T3 `harness.column_demands`** (spec §4.4.2). Refusal unless `host_local/1`; rows per selected column and combination;
`Pu_kN = −P_kN`; the axis rule for sections symmetric by geometry and layout only (`b_mm == h_mm` and `n_bars_b == n_bars_h`) and
`AXES_UNDECLARED` otherwise; `Ag_mm2 = b_mm·h_mm` and one reinforcement-limits item per column with `case: null`; `lu_mm` from the frame length; `Ast_mm2` from the
layout; `not_checked` reasons; the trace steps E3 to E5. The verification record names each conversion as a C item
for the owner (contract G-3, CW-G9 to CW-G11).

**T4 `harness.column_review`** (spec §4.4.3). Reads the host and code verdict sets by reference, filters to the
selected columns, members per 0003 S5, governing references, `not_checked` as `NEEDS_ENGINEER`, changes from the
previous review. The property test proves that every ratio in the output equals the ratio of the verdict it references.

**T5 Proposal calcs** (spec §4.4.4). `harness.column_section_match` (input sizes only as `harness.section_size/1`
references; exact tolerance comparison; `matched`, `no_section_in_model`, `ambiguous`) and
`harness.column_change_set` (names only; refusals with CW-G3).

**T6 Code-pack route** (spec §4.5). `_calc/_code_packs.py` with the fixed allowlist of the three column check ids,
`describe` from `CheckMeta`, `run` building `BatchItem`s with references and calling `evaluate_batch` in the run's
mode, storage of the `verdicts.set/1` payload, refusal in `production`. If a merged plan already provides a code-pack
route when T6 starts, T6 adds the three ids to it and its tests instead; the lead records which by a plan amendment.

**T7 `harness.revit_column_update`** (spec §4.4.5). Targets by shape as references to ETABS `model.sections/1` fields,
role statuses, `no_change`, reuse of an equal type, one new type per family and ETABS section, name clashes, the
orientation-unverified issue with both rotations, the `origin` of each assignment from the design record's
changed frames, and the expected effects for the read-back.

**T8 `harness.revit_column_readback`** (spec §4.4.6). Type and value checks per planned element and type, unplanned
type changes, missing elements, `not_read`, `stale_ok` on `before` only.

**T9 Points and rules** (spec §4.8). The four points with their state models, the rules `cm.no_proposal` (only
for `PASS` columns), `cm.fail_matched`, `map.clean`, `rr.pass`, policy without the model and language-model tiers, lock entries.

**T10 Amendments** (spec §11 Q2 to Q4). `WorkflowDef.allowed_modes` with `RunRefused MODE_NOT_ALLOWED` before
`run_started`; the edit cycle exports `read_state`, `apply_change_set`, `run_and_summarize` and `finish`, and
`apply_change_set` takes a change-set reference; `harness.change_set_check` version 2 accepts a
`harness.generated_change_set/1` reference beside the answer field. The edit-cycle suite of plan 0007 passes
unchanged (only its imports may change).

**T11 Review cycle** (WS steps 1 to 10 and 15). The definitions and basis fields of `column_design`, the scope and
layout requests, the cycle with selection, analysis and design through the edit cycle's `run_and_summarize`, the frame
forces read, host verdicts, demands, the code checks through T6, the review, the engineer turn, and the finish. The
CSI fake gains a column scenario (test data): frames, sections, combinations, frame forces and steel design ratios.

**T12 Proposal and apply** (WS steps 11 to 14). The proposal request, rounding per dimension, matching, `decide_many`,
the generated change set, `apply_change_set`, and the design record after promotion.

**T13 Revit run** (WS steps R1 to R9). Mode refusal, the ETABS fingerprint gate, the Revit working copy and reads,
the map and its decision, the update plan, the approval, the ordered writes with references, the read-back and its
decision, sign-off; the Revit fake gains a column scenario with families, types and role parameters.

**T14 Report and audits** (spec §4.10). Renderers for both runs (verdict sources, size chain, map, plan, read-back,
unsaved-document notice, draft marks), `audit_verdict_sources`, and the column section of `docs/local-testing.md`
(spec §12, items 1 to 8).

**T15 Crash matrix.** Test code only: the engine killed at every step of both workflows against the fake processes.

## 3. Dependencies

- Runtime: no new third-party package. T6 makes `eng-harness` depend on the workspace packages `structural-codes` and
  `aci318-14` (the layering of CF §1); whether an internal workspace dependency needs a package ADR is spec Q12, and T6
  waits for that answer or writes the ADR. Development: none new.
- Before T1: plan 0003 T4 (kind registration) and plan 0007 T1a (edit-cycle kinds; T1 was split, amendment B-386).
- Before T2 to T5, T7, T8: plan 0003 T1 to T6 (calc framework, golden infrastructure); T5 also needs plan 0003 T11
  (`harness.section_round`); T7 and T8 need plan 0011 T6 (Revit kinds and role map) and T12 (`harness.frame_element_map`).
- Before T6: plan 0003 T5 (`HarnessCalcPort`); structural-codes core plan 0001 T8 (`evaluate_batch`) and T11 (lifecycle
  and mode usability), and plan 0004 T5 (the column checks registered).
- Before T9: plan 0005 T4 and T9 (rules, `decide_many`).
- Before T10: engine plan 0001 (`block.py`, `_runner.py`) and plan 0007 T8, T9 and T2 (the blocks and the check it
  amends).
- Before T11: plan 0007 T9 (the cycle blocks) and T4 (`harness.host_design_verdicts`); plan 0002 T4 (the CSI fake);
  plan 0004 T5 (`FieldSpec`).
- Before T13: plan 0011 T7 to T11 and T15 (reader, edits, attended writes, reconciliation, session, wiring) and T2 (the
  Revit fake).
- Before T14: plan 0007 T10 (`audit_value_sources` and the report sections).
- Owner decisions that do not block T1 to T15: the spec's Q1 to Q11 (the recommendations are implemented); C1 (basis
  paths) must be settled by the lead before T3 merges, or T3 uses the clause specs' names as written.

## 4. Verification

- Local gate per task (`uv run eng-gate check` once available; until then ruff, mypy strict and pytest with coverage
  from `packages/eng-harness/`); the pull request links its CI run.
- Fake-host workflow tests run the CSI and Revit fakes as real processes through the harness launcher (POSIX in Linux
  CI), with the real `aci318-14` pack.
- Review: correctness, Python, type-design, silent-failure and test lenses on every task; the R1 source-check lens on
  T2 to T5, T7 to T9 (no literal, every value from the basis, an answer or a read; golden values derived by hand); the
  security lens on T6 and T10 (the allowlist of check ids and the mode refusal). Second-family review and owner
  approvals are `awaiting owner` (ADR-0028 §4).
- Needs local test (spec §12, listed in `docs/local-testing.md` by T14): every step that drives ETABS or Revit, the
  sign and axis conventions, the owner's column families, and the benchmark. No task claims a live result.
- Owner queue after the plan: the spec's Q1 to Q11, C1 to C4, CW-G1 to CW-G12, and the calc ids, rule ids and content
  hashes of T2 to T5, T7 to T9.

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; reverting it removes it and its dependants. T10 changes
shared code: its revert restores the edit cycle's own change-set path and removes `allowed_modes`, and the engine and
edit-cycle suites are its regression tests. Calcs and rules are registered `draft`; a defective one is withdrawn
through `approvals.yaml` in a later change, never edited under its id. Nothing here writes to ETABS or Revit in CI.
