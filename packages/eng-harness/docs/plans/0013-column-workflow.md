---
id: plan-b083-column-workflow
issue: "B-083"
spec: packages/eng-harness/docs/specs/0013-column-workflow.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2, r3]  # r3 from the public_modules entries in pyproject.toml (amendment B-356); r2 from the kinds (amendment B-453)
tasks:
  - id: T1
    title: Column workflow kinds
    # Amendment (B-447, D-12): split from the request models (now T1b). The eight kinds written as ordinary classes
    # measured 322 counted lines, the kinds and requests together 427, over the 400-line cap.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.kinds, eng_harness.kinds.column_design, eng_harness.workflows and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/kinds/__init__.py"
      - "packages/eng-harness/src/eng_harness/kinds/column_design.py"
      - "packages/eng-harness/tests/contract/test_column_design_kinds.py"
      - "packages/eng-harness/tests/data/kinds/column_design/*.json"
    max_changed_lines: 340
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_column_design_kinds.py::test_kind_fixtures"
    covers: [AC3]
    depends_on: []
  - id: T1b
    title: Column workflow request models
    # Amendment (B-447, D-12): the request models of spec 4.3, split from T1.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.workflows.column_design
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/_requests.py"
      - "packages/eng-harness/tests/contract/test_column_requests.py"
      - "packages/eng-harness/tests/data/kinds/column_design/requests/**"
    max_changed_lines: 120
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_column_requests.py::test_request_models"
    covers: [AC3]
    depends_on: [T1]
  - id: T2
    title: Calc harness.column_select with golden and property tests
    # Amendment (B-467, documents only): the calc reads the basis field compare.length_mm (spec 0007 4.8 name).
    # Amendment (B-459, D-12): the branch of B-281 measured 313 counted lines against its merge base with build/v1
    # (column_select.py 279, calcs/__init__.py registration 7, column_design/__init__.py 5, calcs.lock.json 5,
    # verification page 14, pyproject.toml 2, CHANGELOG.md 1): one calc module with its registration, so the budget is
    # the measurement plus about 10 percent, and calcs/__init__.py (the registration) joins the files. T2 registers
    # through COLUMN_DESIGN_CALCS and COLUMN_DESIGN_KINDS in calcs/column_design/__init__.py, as calcs/footing/__init__.py
    # does with FOOTING_CALCS and FOOTING_KINDS, so calcs/__init__.py is edited once here and the later calc tasks (T3,
    # T4, T5, T7, T8) add their calcs and kinds in calcs/column_design/__init__.py only.
    # Amendment (B-462, documents only): the calc-module rules test allows kinds.column_design and kinds.edit_cycle
    # (spec 0003 4.3), and T2 registers COLUMN_DESIGN_KINDS in HARNESS_KINDS (_kinds.py), which T1 left out; budget
    # 345 kept (294 counted on the B-281 branch plus about 5 for the registration).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.column_design, eng_harness.calcs.column_design.column_select (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.column_select.md"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/column_select.py"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/src/eng_harness/_kinds.py"  # COLUMN_DESIGN_KINDS in HARNESS_KINDS (amendment B-462)
      - "packages/eng-harness/tests/rules/test_calc_modules.py"  # allowed imports of spec 0003 4.3 (amendment B-462)
      - "packages/eng-harness/tests/golden/column_design/__init__.py"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py"
      - "packages/eng-harness/tests/data/golden/column_design/column-select-*.json"
      - "packages/eng-harness/tests/property/test_column_select.py"
    max_changed_lines: 345
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
    # Amendment (B-578, documents only): T3 produces harness.column_check_items/1, so it also updates ColumnCheckItems
    # in kinds/column_design.py (field-aware validation of _Item.inputs; the kind id harness.column_check_items/1
    # stays), its column_check_items*.json fixtures and its contract test,
    # and regenerates calcs.lock.json (already in files; kinds/column_design.py is in the hash closure of
    # harness.column_select as well as harness.column_demands). The separate amendment B-577 handles ColumnReview's
    # member snapshot in T4. column_demands.py types forces with forces.member_end/1 (refusal at input validation,
    # ContractError INVALID_ARGUMENT) and validates basis fields before emitting references; the changed-line estimate
    # rises from 340 to 400 (B-552).
    # Owner answer (2026-11-19): each check whose input model has ratio_limit emits it as
    # {"$ref": "res_<basis id>#/fields/limits.ratio_limit_ratio/value"} (fourth reference-object field beside
    # fc_MPa, fy_MPa and k_factor; all three ACI 318-14 column checks inherit it from CheckInputs).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.column_design, eng_harness.calcs.column_design.column_demands (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.column_demands.md"
      - "packages/eng-harness/src/eng_harness/kinds/column_design.py"  # ColumnCheckItems item inputs hold literals or {"$ref"} objects (amendment B-578)
      - "packages/eng-harness/src/eng_harness/calcs/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/column_demands.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/contract/test_column_design_kinds.py"  # ColumnCheckItems input-shape contract tests (amendment B-578)
      - "packages/eng-harness/tests/data/kinds/column_design/column_check_items*.json"  # valid/invalid fixtures for ColumnCheckItems (amendment B-578)
      - "packages/eng-harness/tests/golden/column_design/test_golden.py"
      - "packages/eng-harness/tests/data/golden/column_design/column-demands-*.json"
      - "packages/eng-harness/tests/unit/calcs/test_column_demands.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/contract/test_column_design_kinds.py::test_kind_fixtures"
      - "packages/eng-harness/tests/contract/test_column_design_kinds.py::test_check_item_inputs_are_ref_objects_or_literals"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-compression-tension]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-square-uniaxial]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-square-unequal-bars]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-reinforcement-limits-per-column]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-biaxial]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-not-checked]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-demands-layout-bar-area]"
      - "packages/eng-harness/tests/unit/calcs/test_column_demands.py::test_refusals"
      - "packages/eng-harness/tests/unit/calcs/test_column_demands.py::test_axes_undeclared"
      - "packages/eng-harness/tests/unit/calcs/test_column_demands.py::test_items_validate_against_checks"
    covers: [AC6, AC7]
    depends_on: [T2]
  - id: T4
    title: Calc harness.column_review (members, governing references, changes)
    # Amendment (B-577, documents only): the B-283 writer measured that ColumnReview in kinds/column_design.py has no
    # members field (rejecting members as extra_forbidden) and reuses SummaryChanges whose rows omit source, whereas R4
    # needs every previous member keyed by frame id, source and check id (top is capped by report.top_n, governing holds
    # at most one verdict per frame, and changes holds only deltas). Extend ColumnReview with the complete S5 member
    # snapshot and column-specific change rows carrying the same key, update column_review.json and
    # column_review.invalid.json (preserving the invalid fixture's not_checked status violation) and
    # test_column_design_kinds.py, and regenerate calcs.lock.json (already in files; kinds/column_design.py is in the
    # hash closure of harness.column_select as well as harness.column_review, and harness.column_select.md points to
    # the lock with no literal hash). Raise max_changed_lines from 300 to 360 for the ColumnReview kind models,
    # validators, and lock entry.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.column_design, eng_harness.calcs.column_design.column_review (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.column_review.md"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/column_review.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/src/eng_harness/kinds/column_design.py"  # ColumnReview member snapshot and keyed change rows (amendment B-577)
      - "packages/eng-harness/tests/contract/test_column_design_kinds.py"  # kind contract tests for the extended ColumnReview (amendment B-577)
      - "packages/eng-harness/tests/data/kinds/column_design/column_review.json"  # updated valid fixture (amendment B-577)
      - "packages/eng-harness/tests/data/kinds/column_design/column_review.invalid.json"  # updated invalid fixture preserving not_checked status violation (amendment B-577)
      - "packages/eng-harness/tests/golden/column_design/test_golden.py"
      - "packages/eng-harness/tests/data/golden/column_design/column-review-*.json"
      - "packages/eng-harness/tests/property/test_column_review.py"
    max_changed_lines: 360
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
    # Amendment (B-580, documents only): the B-284 re-review found that HarnessCalcPort drops the pointer when
    # building RefMeta, and column_section_match appends #/size to the record id whatever field supplied the value,
    # so a size_b / size_h / size_d reference to #/required or #/increment can match on an unrounded dimension while
    # the trace points at #/size (R1 provenance break). T5 therefore also edits the plan 0003 modules
    # packages/eng-harness/src/eng_harness/_calc/_port.py and packages/eng-harness/src/eng_harness/calc.py (RefMeta),
    # plus packages/eng-harness/tests/unit/calcs/test_port.py: the port preserves each input reference with its
    # pointer in RefMeta; column_section_match refuses a size reference whose parsed pointer is not exactly /size
    # (INVALID_ARGUMENT, field size_b, size_h or size_d) and writes the validated reference to the trace; port-level
    # regression cases cover both sibling fields on a harness.section_size/1 record whose required differs from size.
    # Those port regressions fail on T5's current base (pointer dropped today), so they join tests_first. Raise
    # max_changed_lines from 300 to 400 for the shared metadata and port changes. External amendment recorded in
    # plan 0003 §3.
    # Amendment (B-582, documents only): RefMeta.ref in calc.py is in every calc's content-hash closure, so T5's
    # calcs.lock.json rewrite moves every content_sha256; six footing verification records (plan 0010) embed those
    # hashes and must refresh the content-hash line only (nothing else) in the same pull request (footing_resize once
    # that record exists on build/v1). External amendment recorded in plan 0010 §3.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.column_design, eng_harness.calcs.column_design.change_set and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.column_section_match.md"
      - "packages/eng-harness/docs/verification/calcs/harness.column_change_set.md"
      - "packages/eng-harness/src/eng_harness/calc.py"  # RefMeta keeps the original input reference with its pointer (amendment B-580)
      - "packages/eng-harness/src/eng_harness/_calc/_port.py"  # HarnessCalcPort preserves that reference in RefMeta (amendment B-580)
      - "packages/eng-harness/src/eng_harness/calcs/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/section_match.py"
      - "packages/eng-harness/src/eng_harness/calcs/column_design/change_set.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.footing_layout.md"  # content-hash line only; hash moved by RefMeta.ref in calc.py (amendment B-582)
      - "packages/eng-harness/docs/verification/calcs/harness.footing_plan_size.md"  # content-hash line only; hash moved by RefMeta.ref in calc.py (amendment B-582)
      - "packages/eng-harness/docs/verification/calcs/harness.footing_schedule.md"  # content-hash line only; hash moved by RefMeta.ref in calc.py (amendment B-582)
      - "packages/eng-harness/docs/verification/calcs/harness.footing_status.md"  # content-hash line only; hash moved by RefMeta.ref in calc.py (amendment B-582)
      - "packages/eng-harness/docs/verification/calcs/harness.footing_subjects.md"  # content-hash line only; hash moved by RefMeta.ref in calc.py (amendment B-582)
      - "packages/eng-harness/docs/verification/calcs/harness.footing_resize.md"  # content-hash line only; hash moved by RefMeta.ref in calc.py (amendment B-582); once that record exists on build/v1
      - "packages/eng-harness/tests/golden/column_design/test_golden.py"
      - "packages/eng-harness/tests/data/golden/column_design/column-match-*.json"
      - "packages/eng-harness/tests/unit/calcs/test_port.py"  # RefMeta pointer preservation regressions (amendment B-580)
      - "packages/eng-harness/tests/unit/calcs/test_column_section_match.py"
      - "packages/eng-harness/tests/unit/calcs/test_column_change_set.py"
    max_changed_lines: 400
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-one]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-none]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-ambiguous]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-other-material]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-boundary]"
      - "packages/eng-harness/tests/golden/column_design/test_golden.py::test_case[column-match-circular]"
      - "packages/eng-harness/tests/unit/calcs/test_column_section_match.py::test_size_must_be_rounding_result"
      - "packages/eng-harness/tests/unit/calcs/test_column_section_match.py::test_size_pointer_must_be_size"
      - "packages/eng-harness/tests/unit/calcs/test_column_change_set.py::test_items_and_refusals"
      - "packages/eng-harness/tests/unit/calcs/test_port.py::test_ref_meta_preserves_pointer"
    covers: [AC9, AC10]
    depends_on: [T2]
  - id: T6
    # Amendment (B-418, documents only): starts only after the documents pull request B-405 (spec 0013 AC13 and §4.5:
    # an id outside the allowlist gives ContractError NOT_FOUND, spec 0010 C4) has merged; see section 3
    # Amendment (B-578, documents only): the code-pack route (_code_packs.py, _port.py, _calc/__init__.py,
    # pyproject.toml, uv.lock) already landed in B-393 (plan 0010 T2) and the three column checks in B-334;
    # B-393 also shipped the column allowlist and batch argument. The lead owns the package ADR required by
    # spec Q12 as a separate documents follow-up (see section 3; lead decision D-19). T6 is a test-only
    # pull request (title type test, test files only, no failing-first run under gate spec 4.7). The changed-line
    # estimate becomes 60 and max_sessions becomes 1. The companion tests in test_code_pack_route.py are expected
    # to pass at T6's base (merged B-393 + B-334 + T3), so tests_first is empty under TF004 and B-482.
    # depends_on becomes [T3] because
    # test_batch_through_calcport stores a harness.column_check_items/1 record conforming to the T3-amended kind.
    title: Code-pack route tests for the three ACI 318-14 column checks
    files:
      - "packages/eng-harness/tests/unit/calcs/test_code_pack_route.py"
    max_changed_lines: 60
    max_sessions: 1
    tests_first: []
    covers: [AC13]
    depends_on: [T3]
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
    # Amendment (B-573, documents only): rules.lock.json joins the files; required by test_lock, spec 0005 AC14 and plan 0005 T4. Its writer's trial passed the gate with exactly that file set.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.rules, eng_harness.rules.column_design, eng_harness.workflows and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/_points.py"
      - "packages/eng-harness/src/eng_harness/rules/column_design.py"
      - "packages/eng-harness/src/eng_harness/decisions.lock.json"
      - "packages/eng-harness/src/eng_harness/rules.lock.json"  # required by test_lock, spec 0005 AC14 and plan 0005 T4 (amendment B-573)
      - "packages/eng-harness/tests/unit/rules/test_column_design_rules.py"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/rules/test_column_design_rules.py::test_member_action_rules"
      - "packages/eng-harness/tests/unit/rules/test_column_design_rules.py::test_revit_rules"
      - "packages/eng-harness/tests/unit/rules/test_column_design_rules.py::test_lock"
    covers: [AC14]
    depends_on: [T1, T1b]  # T1b: the decision points answer with the request models (amendment B-447)
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
    # Amendment (B-417, documents only): registers column_design by adding its blocks to the shipped-workflow tuple of workflows/__init__.py, which block.discover() reads (plan 0007 T9b, spec 0007 4.2); T12's blocks reach it through the same column_design export.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.workflows, eng_harness.workflows.column_design (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/_cycle.py"
      - "packages/eng-harness/src/eng_harness/workflows/__init__.py"  # shipped-workflow registry (amendment B-417)
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
    # Amendment (B-417, documents only): adds column_revit_update to the shipped-workflow tuple of workflows/__init__.py, which block.discover() reads (plan 0007 T9b, spec 0007 4.2).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.workflows, eng_harness.workflows.column_design (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/column_design/_revit.py"
      - "packages/eng-harness/src/eng_harness/workflows/__init__.py"  # shipped-workflow registry (amendment B-417)
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
column-specific kinds, six calcs, decision points, two blocks, report parts and tests. B-393 shipped the shared
code-pack route, including the column allowlist and the `batch` argument (amendment B-578).

Risky parts first. The R1 calcs come before any workflow code, each with hand-derived golden cases: the selection
(T2), the demands with their sign and axis rules (T3, the riskiest: a wrong sign or axis is a wrong verdict), the
review (T4), the proposal path (T5), and the Revit plan and read-back (T7, T8). T6 adds companion tests for the merged
code-pack route (amendment B-578). The engine and edit-cycle amendments (T10) land before the blocks and run the
existing engine and edit-cycle suites for regression coverage. Then the blocks: the review cycle
(T11), the proposal and apply path (T12), and the Revit run (T13). The report and audits (T14) and the crash matrix
(T15) close the plan.

For test-first tasks ([process/05](../../../../design/process/05-testing-and-verification.md) §9), the first commit
holds the `tests_first` tests (and, for calc tasks, golden files with hand-derived expected values and a `derivation`
field). Those tests fail on the task's base before implementation. T6 is a test-only PR and is exempt from the
failing-first rule under gate §4.7. Its companion tests pass on its base, so `tests_first: []` follows the B-482
precedent and TF004 (amendment B-578). `max_changed_lines` estimates counted non-test lines (B-552).
Several tasks edit `CHANGELOG.md`, `calcs.lock.json`, `blocks.lock.json` or the shared golden test module,
so they merge one after another; the registry serializes T3, T4 and T5 (each depends only on T2, so
`depends_on` alone does not order them). Nothing in this plan needs a host program in CI.

R1 content in bootstrap mode ([ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4): calcs and
rules are registered `draft` and no approval is added; `src/eng_harness/calcs/`, `src/eng_harness/rules/` and
`tests/data/golden/` are protected paths, so each calc and rule pull request is R1 and lists the calc ids and content
hashes for the owner queue. The code checks stay `draft` in their pack (CK-AC5); every workflow test runs in the
`trial` run class. No golden value comes from a code text: the column-demand cases test conversions (sign, axis
selection, bar count, length), not code capacities.

## 2. Tasks

**T1 Kinds** (spec §4.2). The eight `harness.*` kinds with strict models, written as ordinary classes, and registration
beside the edit-cycle kinds.

**T1b Requests** (spec §4.3). `ColumnScopeRequest`, `ColumnLayoutRequest` and `ColumnProposalRequest`, with the refused
variants (`spiral`, `special_seismic: true`) parsed so the engineer sees a reasoned refusal with the gap id. Amendment
B-447 (D-12): split from T1, whose explicit kinds alone measured 322 counted lines.

**T2 `harness.column_select`** (spec §4.4.1). Name and story-section resolution, the exact verticality test against
`compare.length_mm`, shape and material per column, issues, and the shared golden test module for the column calcs. T2
also registers `COLUMN_DESIGN_KINDS` in `HARNESS_KINDS` (`_kinds.py`), so the CalcPort can store column calc results.
Amendment (B-462).

**T3 `harness.column_demands`** (spec §4.4.2; amendment B-578). Updates `ColumnCheckItems` in `kinds/column_design.py`
with field-aware validation of `_Item.inputs`. For each supplied field, require a strict JSON integer for
`n_bars_b` and `n_bars_h`, exactly `"tied"` for `transverse_kind`, and a `{"$ref": "..."}` object validated by
`eng_contract.refs.Ref` for `fc_MPa`, `fy_MPa`, `k_factor` and `ratio_limit` (owner answer 2026-11-19). Require a
strict JSON integer or finite float for each remaining numeric input. Exclude booleans and coercion. The
check-model test below verifies that every required field of the check's input model is present, every emitted
name is a field of that model, and the emitted names equal the §4.4.2 list for that check (`ratio_limit`
included). Keep the `harness.column_check_items/1` id. Amendment B-577 covers `ColumnReview`'s member snapshot.

Update `tests/data/kinds/column_design/column_check_items*.json` and `tests/contract/test_column_design_kinds.py`.
The valid fixture round-trips literal values and basis reference objects with the `$ref` alias.
`test_check_item_inputs_are_ref_objects_or_literals` exercises each invalid shape in a separate case by replacing
one otherwise valid input: a bare `RefString`, a float in each bar-count field, `"spiral"`, a numeric literal in
each basis-reference field, a malformed reference object, a reference object in a numeric-literal field, a
numeric string, a boolean, and a non-finite float.

T3 types the `forces` input with `forces.member_end/1` (`ref_kinds={"forces.member_end/1"}`), so non-`host_local/1` `sign_convention` fails at input
validation (`ContractError` `INVALID_ARGUMENT`, nothing stored); checks presence and confirmation of the §4.7 A basis
fields before emitting any reference (`ContractError` `INVALID_ARGUMENT`, `field = basis.fields.<path>`, nothing
stored). Rows per selected column and combination; `Pu_kN = −P_kN`; the axis rule for sections symmetric by geometry
and layout only (`b_mm == h_mm` and `n_bars_b == n_bars_h`) and `AXES_UNDECLARED` otherwise; `Ag_mm2 = b_mm·h_mm` and
one reinforcement-limits item per column with `case: null`; `lu_mm` from the frame length; `Ast_mm2` from the layout;
emits literal JSON values (equal to E3–E5 trace steps), `"tied"`, and `{"$ref": "res_<basis id>#/fields/<path>/value"}`
for `fc_MPa`, `fy_MPa`, `k_factor` and `ratio_limit` per spec §4.4.2 (`ratio_limit` → `limits.ratio_limit_ratio`; owner answer 2026-11-19); `not_checked` reasons; the trace steps E3 to E5. `test_column_demands.py::test_items_validate_against_checks` validates every emitted item against its real `aci318_14` check input model under `InputPolicy(require_refs=True)` and checks that every required field of the check's input model is present, every emitted name is a field of that model, and the emitted names equal the §4.4.2 list for that check (`ratio_limit` included); the golden harness uses a fixed result-id source so basis references are deterministic. The verification record names each conversion as a C item for the owner (contract G-3, CW-G9 to CW-G11).

**T4 `harness.column_review`** (spec §4.4.3). Reads the host and code verdict sets by reference (separate named
top-level reference fields for the three code checks), filters to the selected columns, members per 0003 S5, governing
references, `not_checked` as `NEEDS_ENGINEER`, changes from the previous review. The property test proves that every
ratio in the output equals the ratio of the verdict it references. Amendment (B-577, documents only): `ColumnReview` in
`kinds/column_design.py` gains the complete `members` snapshot and column-specific `changes` rows keyed by frame id,
`source` and check id; `column_review.json`, `column_review.invalid.json` (preserving its `not_checked` violation) and
`test_column_design_kinds.py` are updated alongside it, and `calcs.lock.json` is regenerated (which also updates the
entry of `harness.column_select`, whose hash closure includes `kinds/column_design.py`).

**T5 Proposal calcs** (spec §4.4.4). `harness.column_section_match` (top-level `size_b` and `size_h`, or
`size_d`, each a `harness.section_size/1` reference whose pointer is exactly `/size`; exact tolerance comparison;
`matched`, `no_section_in_model`, `ambiguous`) and `harness.column_change_set` (names only; refusals with CW-G3).
Amendment (B-580, documents only): the port preserves each input reference with its pointer in `RefMeta`
(`calc.py`, `_calc/_port.py`); the matcher refuses a size reference whose parsed pointer is not `/size`
(`INVALID_ARGUMENT`, field `size_b`, `size_h` or `size_d`) and writes the validated reference to the trace; port-level
regression `test_port.py::test_ref_meta_preserves_pointer` covers `#/required` and `#/increment` on a record whose
`required` differs from `size`, and `test_column_section_match.py::test_size_pointer_must_be_size` covers the calc
refusal (both fail on T5's current base, so both are in `tests_first`).
Amendment (B-582, documents only): T5 may refresh only the content-hash line in the six footing verification records (`harness.footing_layout`, `harness.footing_plan_size`, `harness.footing_schedule`, `harness.footing_status`, `harness.footing_subjects`, and `harness.footing_resize` once that record exists on build/v1) so each matches the lock after `RefMeta.ref` moves every calc's `content_sha256`; nothing else in those records.

**T6 Code-pack route tests** (spec §4.5, AC13; amendment B-578). The route itself (`_calc/_code_packs.py`, `_port.py`,
`COLUMN_CHECK_IDS`, `batch` argument, `pyproject.toml`, `uv.lock`) already merged in B-393 (plan 0010 T2), and the
three column checks merged in B-334 (structural-codes plan 0004 T5). T6 is therefore a test-only task (`test(eng-harness): ...`,
`tests_first: []` per TF004 and the B-482 precedent) depending on T3 for the amended `harness.column_check_items/1`
kind, adding companion coverage in `tests/unit/calcs/test_code_pack_route.py`:
`test_batch_through_calcport` (real `aci318_14` registry through `HarnessCalcPort.run` in `trial` mode on a conforming
`harness.column_check_items/1` and `basis.design_basis/1`, asserting one trace per item in order, `draft: true`, exact
`parents` `[items, basis]` for every check, `RefInput`/`LiteralInput` split including `ratio_limit` as a `RefInput`,
and stored-value equality). For `test_ref_strings_refused` and
`test_literal_fc_refused`, use a permissive stored-list fixture that accepts raw item inputs. Resolve the list
through `batch` and assert that the route returns `INVALID_ARGUMENT` with no verdict stored, for a bare
`RefString` (`field = items[0].<name>`) and for a literal `fc_MPa` under `require_refs`, respectively.
Run `test_production_refused` and `test_only_listed_checks` with the column ids. T6 starts after B-405 (already merged)
and structural-codes core plan T15 (`CheckMeta.version`, B-442, already merged).

**T7 `harness.revit_column_update`** (spec §4.4.5). Targets by shape as references to ETABS `model.sections/1` fields,
role statuses, `no_change`, reuse of an equal type, one new type per family and ETABS section, name clashes, the
orientation-unverified issue with both rotations, the `origin` of each assignment from the design record's
changed frames, and the expected effects for the read-back.

**T8 `harness.revit_column_readback`** (spec §4.4.6). Type and value checks per planned element and type, unplanned
type changes, missing elements, `not_read`, `stale_ok` on `before` only.

**T9 Points and rules** (spec §4.8). The four points with their state models, the rules `cm.no_proposal` (only
for `PASS` columns), `cm.fail_matched`, `map.clean`, `rr.pass`, policy without the model and language-model tiers, lock entries.
Amendment (B-573, documents only): `rules.lock.json` joins T9's files; required by `test_lock`, spec 0005 AC14 and
plan 0005 T4 lock. Its writer's trial passed the gate with exactly that file set.

**T10 Amendments** (spec §11 Q2 to Q4). `WorkflowDef.allowed_modes` with `RunRefused MODE_NOT_ALLOWED` before
`run_started`; the edit cycle exports `read_state`, `apply_change_set`, `run_and_summarize` and `finish`, and
`apply_change_set` takes a change-set reference; `harness.change_set_check` version 2 accepts a
`harness.generated_change_set/1` reference beside the answer field. The edit-cycle suite of plan 0007 passes
unchanged (only its imports may change).

**T11 Review cycle** (WS steps 1 to 10 and 15). The definitions and basis fields of `column_design`, the scope and
layout requests, the cycle with selection, analysis and design through the edit cycle's `run_and_summarize`, the frame
forces read, host verdicts, demands, the code checks through T6, the review, the engineer turn, and the finish. The
CSI fake gains a column scenario (test data): frames, sections, combinations, frame forces and steel design ratios. Amendment
(B-417): the task registers `column_design` by adding its blocks to the shipped-workflow tuple of
`workflows/__init__.py`, which `block.discover()` reads (plan 0007 T9b); `blocks.lock.json` is regenerated from it.

**T12 Proposal and apply** (WS steps 11 to 14). The proposal request, rounding per dimension, matching, `decide_many`,
the generated change set, `apply_change_set`, and the design record after promotion.

**T13 Revit run** (WS steps R1 to R9). Mode refusal, the ETABS fingerprint gate, the Revit working copy and reads,
the map and its decision, the update plan, the approval, the ordered writes with references, the read-back and its
decision, sign-off; the Revit fake gains a column scenario with families, types and role parameters. Amendment (B-417):
the task adds `column_revit_update` to the same tuple of `workflows/__init__.py` (plan 0007 T9b).

**T14 Report and audits** (spec §4.10). Renderers for both runs (verdict sources, size chain, map, plan, read-back,
unsaved-document notice, draft marks), `audit_verdict_sources`, and the column section of `docs/local-testing.md`
(spec §12, items 1 to 8).

**T15 Crash matrix.** Test code only: the engine killed at every step of both workflows against the fake processes.

## 3. Dependencies

- Runtime: no new third-party package. `eng-harness` already depends on the workspace packages `structural-codes` and
  `aci318-14` from B-393 (plan 0010 T2, CF §1; amendment B-578). Development: none new.
- Before T1: plan 0003 T4 (kind registration) and plan 0007 T1a (edit-cycle kinds; T1 was split, amendment B-386).
- Before T2 to T5, T7, T8: plan 0003 T1 to T6 (calc framework, golden infrastructure); T5 also needs plan 0003 T11
  (`harness.section_round`); T7 and T8 need plan 0011 T6 (Revit kinds and role map) and T12 (`harness.frame_element_map`).
- Before T6: plan 0003 T5 (`HarnessCalcPort`), plan 0010 T2 (B-393 shared code-pack route), structural-codes core plan
  0001 T8 (`evaluate_batch`) and T11 (lifecycle and mode usability), structural-codes plan 0004 T5 (B-334 column checks),
  B-405 (`NOT_FOUND`, spec 0010 C4), and T3 (amendment B-578: amended `harness.column_check_items/1` kind).
- Before T9: plan 0005 T4 and T9 (rules, `decide_many`).
- Before T10: engine plan 0001 (`block.py`, `_runner.py`) and plan 0007 T8, T9b and T2 (the blocks and the check it
  amends).
- Before T11: plan 0007 T9b (the cycle blocks) and T4b (`harness.host_design_verdicts`; amendment B-511); plan 0002 T4 (the CSI fake);
  plan 0004 T5 (`FieldSpec`).
- Before T13: plan 0011 T7 to T11 and T15 (reader, edits, attended writes, reconciliation, session, wiring) and T2 (the
  Revit fake).
- Before T14: plan 0007 T10 (`audit_value_sources` and the report sections).
- B-484 settled spec C1. T3 uses the merged §4.7 Table A paths `materials.concrete_fc_MPa`,
  `materials.rebar_fy_MPa`, `columns.effective_length_factor_ratio` and `limits.ratio_limit_ratio`
  (amendment B-578; owner answer 2026-11-19 for `ratio_limit`).
- Owner decisions that do not block T1 to T15: the spec's Q1 to Q11 (the recommendations are implemented).
- Documents follow-up for spec Q12 (amendment B-578). The lead owns a separate documents task to write the
  short workspace code-packs ADR under `docs/adr/` (recommendation adopted by lead decision D-19). The ADR
  records the workspace dependencies on `structural-codes` and `aci318-14` under rule A10 and their impact after
  the repository split (ADR-0028).

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
