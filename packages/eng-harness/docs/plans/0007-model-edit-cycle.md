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
    # Amendment (B-503, documents only): a wall_section on a section the state holds also projects a set of /material
    # (spec 4.4.2, AC37, about 6 lines); the item order of an added combination is spec Q15 (open, nothing to build);
    # max_changed_lines 330 to 340 (an estimate).
    # Amendment (B-513, documents only): the effects record carries the calc port's wrapper members (calc, draft, trace),
    # so kinds/calcs.py gains three optional members on ExpectedEffects (3 lines); that module is in the hash closure of
    # every calc, so calcs.lock.json moves seven entries and the footing record's hash literal follows. max_changed_lines
    # stays 340 (311 measured with the trial).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.edit_cycle, eng_harness.calcs.edit_cycle.expected_effects (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/expected_effects.py"
      - "packages/eng-harness/src/eng_harness/kinds/calcs.py"  # ExpectedEffects gains the optional calc, draft and trace members (amendment B-513)
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.footing_subjects.md"  # its content-hash literal follows the lock (amendment B-513)
      - "packages/eng-harness/docs/verification/calcs/harness.expected_effects.md"
      - "packages/eng-harness/tests/golden/edit_cycle/test_expected_effects.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/effects-*.json"
      - "packages/eng-harness/tests/property/test_expected_effects.py"
    max_changed_lines: 340
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/edit_cycle/test_expected_effects.py::test_golden_cases"
      - "packages/eng-harness/tests/golden/edit_cycle/test_expected_effects.py::test_combination_edit_reads_back"
      - "packages/eng-harness/tests/golden/edit_cycle/test_expected_effects.py::test_wall_section_material_reads_back"  # AC37 (B-503)
      - "packages/eng-harness/tests/golden/edit_cycle/test_expected_effects.py::test_golden_bodies_are_valid_payloads"  # amendment B-513
      - "packages/eng-harness/tests/property/test_expected_effects.py::test_order_independent"
    covers: [AC8, AC36, AC37]
    depends_on: [T2]
  - id: T4
    title: Calc harness.analysis_summary
    # Amendment (B-417, documents only): calcs/__init__.py registers both calcs in REGISTRY (spec 0003 4.2); depends on T3 so that T2, T3 and T4 edit the shared registry files in turn; reads limits.ratio_limit_ratio (spec 4.8).
    # Amendment (B-503, documents only): the inputs harness.csi_design_results/1 and harness.csi_analysis_messages/1 are
    # typed with CsiRows of eng_harness.kinds.csi (spec 0003 4.3), which plan 0002 T21 moves there (section 3); files and budget unchanged.
    # Amendment (B-511, documents only): pre-flight audit. A calc cannot output verdicts.set/1 (spec 0003 AC1, AC47,
    # contract 4.10.1), so harness.host_design_verdicts moves to T4b, held until spec Q19 is answered; this task builds
    # harness.analysis_summary alone. max_changed_lines 340 to 200 (an estimate for one calc and its record).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.edit_cycle, eng_harness.calcs.edit_cycle.analysis_summary and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/analysis_summary.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.analysis_summary.md"
      - "packages/eng-harness/tests/golden/edit_cycle/test_analysis_summary.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/analysis-*.json"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/edit_cycle/test_analysis_summary.py::test_golden_cases"
    covers: [AC30]
    depends_on: [T3]
  - id: T4b
    title: Calc harness.host_design_verdicts, its kind harness.host_design_verdicts/1 and the design summary's input
    # Amendment (B-511, documents only): split from T4. Its output kind is spec Q19 (open): the registry refuses
    # verdicts.set/1 as a calc output. Not started before the answer; the documents amendment that records the answer
    # adds the files of the chosen option (spec Q19) and sets the budget. 240 is an estimate for option (a).
    # Amendment (B-538, documents only): the owner answered spec Q19 on 2026-11-16 with option (a). This task carries
    # the kind (kinds/edit_cycle.py, its fixture and contract test) and the design summary's acceptance of it (spec 0003
    # 4.9: design_summary.py, its record, its unit test; the calc lock). Measured analogs: B-197 (expected_effects)
    # 311 counted lines, module 267; B-149 (design summary) 264, module 237. Estimate: calc module about 170 (a mapping
    # by comparison), kind about 35, summary change about 15, lock about 15 (the new entry and the moved hashes of the
    # calcs that import kinds/edit_cycle.py), records about 20, registration, pyproject and CHANGELOG about 10: about
    # 265. max_changed_lines 240 to 320.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs.edit_cycle.host_design_verdicts (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/host_design_verdicts.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.host_design_verdicts.md"
      - "packages/eng-harness/tests/golden/edit_cycle/test_design_verdicts.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/verdicts-*.json"
      - "packages/eng-harness/src/eng_harness/kinds/edit_cycle.py"  # harness.host_design_verdicts/1 (amendment B-538)
      - "packages/eng-harness/tests/contract/test_edit_cycle_kinds.py"
      - "packages/eng-harness/tests/data/kinds/edit_cycle/host_design_verdicts*.json"
      - "packages/eng-harness/src/eng_harness/calcs/design_summary.py"  # spec 0003 4.9 input kind (amendment B-538)
      - "packages/eng-harness/docs/verification/calcs/harness.design_summary.md"
      - "packages/eng-harness/tests/unit/calcs/test_summary.py"
    max_changed_lines: 320
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/edit_cycle/test_design_verdicts.py::test_golden_cases"
      - "packages/eng-harness/tests/contract/test_edit_cycle_kinds.py::test_fixtures"  # amendment B-538
      - "packages/eng-harness/tests/unit/calcs/test_summary.py::test_host_design_verdicts_input"  # amendment B-538
    covers: [AC3, AC30]
    depends_on: [T4]
  - id: T5
    title: CSI adapter read tool, revision save and open, analysis-messages read (spec 0002 amendment)
    # Amendment (B-415, documents only): the CSI ToolInfo implements saves_new_file (true for as_new_revision and
    # csi_open_revision) and both results carry summary saved_file (name, sha256), spec §4.10; the base default
    # (false) comes with T6, whichever of the two merges first.
    # Amendment (B-505, documents only): max_changed_lines 330 to 375, measured on the finished task (B-199) with the
    # gate's counting rule: 371 lines (_read_state_tool.py 89, _revisions.py 118, _tools.py 160, one line each in
    # CHANGELOG, local-testing, pyproject and _allowlist.toml), margin 4; no file outside this list is needed.
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
    max_changed_lines: 375
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
      - "packages/eng-harness/src/eng_harness/ctx.py"  # BasisView.record_ref(), engine §4.3.2 (amendment B-511)
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py"
      # Amendment (B-535, documents only): a writer's trial (gate pass with exactly this file set, 259 counted lines).
      # Engine 4.6 makes a tool save without provenance.host a ModelIntegrityError, so the save_s tool of two existing
      # tests must name its revision (3 lines added, 1 changed, no expectation changed).
      - "packages/eng-harness/tests/workflow/test_modes.py"
    # Amendment (B-415 review fix, documents only): block.py exposes FieldSpec through a TYPE_CHECKING import and a
    # module-level __getattr__, and imports check_declaration inside workflow(); a module-level import of
    # eng_harness.basis._fields is an import cycle (engine §4.1.2, amendment B-511). The gate also runs
    # tests/rules/test_decision_imports.py::test_types_module_is_block_safe unchanged.
    # Amendment (B-511, documents only): pre-flight audit. The calcs take `basis` as a reference to the whole basis
    # record (spec 0003 §4.4), which BasisView cannot give; BasisView.record_ref() (about 5 lines in ctx.py) and its
    # test join this task, because T8 is its first user. max_changed_lines unchanged.
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
      - "packages/eng-harness/tests/unit/test_engine_edit_cycle_amendments.py::test_basis_view_record_ref"  # amendment B-511
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
      - "packages/eng-harness/tests/contract/test_rule_lock.py"  # skips its lock comparison under the mutation step (MUTANT_UNDER_TEST), because rules/edit_cycle.py is an R1 module and the mutated copy no longer matches rules.lock.json (amendment B-542)
      - "packages/eng-harness/tests/rules/test_block_modules.py"  # does not judge the mutmut import in the mutation step's copy of rules/edit_cycle.py, only under MUTANT_UNDER_TEST (amendment B-542)
      - ".gate/ratchet.json"  # eng-harness skip count 4 -> 5 for the lock-test skip (amendment B-542)
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
    # Amendment (B-511, documents only): after T15, without which FB005 refuses the version=1 of every point and rule
    # (T8 and T9a, T9b follow through T7).
    # Amendment (B-542, documents only): tests/contract/test_rule_lock.py, tests/rules/test_block_modules.py and .gate/ratchet.json join the files; trial: the mutation baseline passes with exactly these (see T7 prose).
    depends_on: [T1b, T15]
  - id: T7b
    title: D-3 stops on a story drift above the limit, and D-2 takes the reason check_model_failed (rules and points)
    # Amendment (B-544, documents only): new fix task for merged T7 code (owner decision of 2026-11-16, spec Q20; spec
    # Q14 interim reading; spec 4.6, AC18). edit_cycle_analysis_messages.clean also needs drift_status PASS (about 3
    # lines and the rationale), ReadbackReason gains check_model_failed (1), both rules and the D-2 point move to version
    # 2 (3; the rule lock hashes the module source, the point lock its state schema), the two locks follow (about 6),
    # 1 of CHANGELOG.md: about 15; budget 30 (an estimate). T7 is not changed; T8 waits for this task.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/rules/edit_cycle.py"
      - "packages/eng-harness/src/eng_harness/rules.lock.json"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_points.py"
      - "packages/eng-harness/src/eng_harness/decisions.lock.json"
      - "packages/eng-harness/tests/rules/test_edit_cycle.py"
    max_changed_lines: 30
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/rules/test_edit_cycle.py::test_clean_boundary"
      - "packages/eng-harness/tests/rules/test_edit_cycle.py::test_clean_drift_at_and_above_the_limit"
      - "packages/eng-harness/tests/rules/test_edit_cycle.py::test_pass_boundary"
    covers: [AC18]
    depends_on: [T7]
  - id: T8
    title: Workflow part 1 - definition, basis fields, steps 1 to 10 (read, differences, change set, approval, apply, read back)
    # Amendment (B-417, documents only): basis_fields and the blank template's ask_each_run use the unit-suffixed paths of spec 4.8; registration and blocks.lock.json move to T9 (this task is at the 400-line cap); T9b since the split (B-511).
    # Amendment (B-463, documents only): section 3 names eng-contract plan 0001 T19 (B-464) as a cross-plan dependency.
    # Amendment (B-536, documents only): EditCycleInput.model is the absolute pathlib.Path of the model file, and step 2 passes its base name as the model key (spec 4.2, 4.5; spec 0006 4.2.2 step 2); a type change, files and budget unchanged.
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
    # Amendment (B-544, documents only): EditCycleOutput.summaries is the ordered tuple of spec 4.2; step 8 passes the resolved references unchanged, which T16b makes valid write arguments; waits for T7b and T16b; no line added, files and budget unchanged.
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
    depends_on: [T2, T3, T5, T6, T7, T7b, T16b]
  - id: T9a
    title: Workflow part 2a - steps 11 to 15 (analysis, design, summaries, D-3, engineer turn)
    # Amendment (B-511, documents only): pre-flight audit. The former T9 was planned at the 400-line cap (B-417: 395 to
    # 400) with no margin; split by its own structure, as B-499 split engine T16. T9a: run_and_summarize and the
    # engineer turn, tested through the test workflows of conftest.py; 200 is an estimate, to measure at write time.
    # Amendment (B-544, documents only): first-live-run walk-through C21, C22, C23 and the owner's drift decision (spec
    # 4.5 steps 13 and 14, 4.6, Q20, Q21; AC41, AC42): the step 13 model-state read and its frames, the combinations
    # named in the drift read, one design summary per design kind, the D-3 drift_status and the turn's design status;
    # about 30 lines: 200 to 235 (an estimate). The rule it relies on is T7b's (through T8).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_cycle.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/conftest.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_turn.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py"
    max_changed_lines: 235
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/edit_cycle/test_turn.py::test_engineer_turn_branches"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_turn.py::test_drift_at_d3"  # AC42 (amendment B-544)
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py::test_step_13_and_14_inputs"  # AC41 (amendment B-544)
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py::test_analysis_timeout_reconciles"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py::test_design_timeout_reconciles"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py::test_save_before_analysis_and_design"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_long_runs.py::test_stale_build_stops_before_any_write"
    covers: [AC16, AC19, AC41, AC42]
    depends_on: [T4, T4b, T8]
  - id: T9b
    title: Workflow part 2b - steps 16 and 17 (promotion, sign-off), the cycle loop and registration
    # Amendment (B-417, documents only): registers the shipped workflow: workflows/__init__.py exports the blocks and block.discover() reads it lazily (spec 4.2), so blocks.lock.json gains the entries; about 15 lines, 380 to 395; tests/unit/test_block.py::test_main_writes_the_lock is isolated from the shipped blocks, about 3 lines, 395 to 400.
    # Amendment (B-511, documents only): split from the former T9 (see T9a); 230 is an estimate, to measure at write time.
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
      - "packages/eng-harness/tests/workflow/edit_cycle/test_promotion.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_modes.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_definition.py"
      - "packages/eng-harness/tests/unit/test_block.py"  # isolates test_main_writes_the_lock from the shipped blocks (amendment B-417)
    max_changed_lines: 230
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
      - "packages/eng-harness/tests/workflow/edit_cycle/test_promotion.py::test_promote_and_conflict"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_promotion.py::test_sign_off_and_draft"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_modes.py::test_approvals_per_mode"
    covers: [AC1, AC9, AC12, AC14, AC15, AC20, AC21, AC22, AC23, AC34]
    depends_on: [T9a, T13]  # T13: the reopened hook that restore_previous needs (amendment B-503)
  - id: T10
    title: Report renderers and value-source audit
    # Amendment (B-511, documents only): pre-flight audit. audit_value_sources takes the engineering parameter names as an input (spec 4.9, AC25).
    # Amendment (B-533, documents only): the former T10 (renderers, audit, prompt counter, timings) measured 451 counted lines against its
    # budget of 380 and the cap of 400 (B-204, complete implementation at d1cc688). Split into T10 (measured 157: _edit_cycle.py 147,
    # _sections.py 9, CHANGELOG.md 1) and T10b (measured 301). The scripted-journal helper `Script` and `PRODUCER` go to
    # `journal_script.py` so that T10 does not import T10b's tests; pyproject.toml needs no edit (`eng_harness.report` is already in
    # public_modules); tests/data/journals/edit_cycle/** is dropped (the journals are scripted in Python).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_edit_cycle.py"
      - "packages/eng-harness/src/eng_harness/report/_sections.py"
      - "packages/eng-harness/tests/unit/report/test_edit_cycle_renderers.py"
      - "packages/eng-harness/tests/unit/edit_cycle/journal_script.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_audit.py"
    max_changed_lines: 170
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/report/test_edit_cycle_renderers.py::test_renderers_and_sources"
      - "packages/eng-harness/tests/unit/edit_cycle/test_audit.py::test_audit_finds_literal"
    covers: [AC25, AC32]
    depends_on: [T1b]
  - id: T10b
    title: Prompt counter and B-1 cycle timings
    # Amendment (B-533, documents only): new, split from T10 (see T10). Measured 301 counted lines: _edit_cycle.py 286, _document.py 7,
    # _write.py 7, CHANGELOG.md 1. The timings section is _timings() in report/_document.py (amendment B-511 of T10). T10 and T10b both edit
    # _edit_cycle.py and CHANGELOG.md, so T10b depends on T10. `write_cycles` stays in test_timings.py, which test_prompts.py imports.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_edit_cycle.py"
      - "packages/eng-harness/src/eng_harness/report/_document.py"  # the timings section (amendment B-511)
      - "packages/eng-harness/src/eng_harness/report/_write.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_prompts.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_timings.py"
    max_changed_lines: 315
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/edit_cycle/test_prompts.py::test_prompt_counter"
      - "packages/eng-harness/tests/unit/edit_cycle/test_timings.py::test_cycle_and_turn_timings"
    covers: [AC26, AC29, AC32]
    depends_on: [T10]
  - id: T10c
    title: The B-1 timings read the benchmark request where the engine stores the change-set answer
    # Amendment (B-545, documents only): new fix task for merged T10b code (first-live-run walk-through C31; spec 4.9, AC29).
    # _benchmarks reads fields.benchmark_request.value, but the engine stores one entry per field of ChangeSetRequest, so the
    # label is at fields.change_set.value.benchmark_request and benchmarks is always empty for a real run. About 4 lines of
    # report/_edit_cycle.py and 1 of CHANGELOG.md: budget 15 (an estimate).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_edit_cycle.py"
      - "packages/eng-harness/tests/unit/edit_cycle/journal_script.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_timings.py"
    max_changed_lines: 15
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/edit_cycle/test_timings.py::test_benchmark_label_in_the_change_set_answer"
    covers: [AC29]
    depends_on: [T10b]
  - id: T11
    title: Acceptance support in CI (A3 and A7 over the workflow scenarios) and the local-testing list
    # Amendment (B-511, documents only): pre-flight audit. The workflow prompt tests and the property test pin merged
    # T9a, T9b and T10b and pass at the base (TF004): they leave tests_first and stay in files (as B-482). The entry
    # point takes the engineering parameter names from engineering_params() in adapters/csi/_tools.py (spec AC35),
    # about 8 lines; budget unchanged (an estimate). Pull request title type feat.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.report (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/src/eng_harness/report/__main__.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"  # engineering_params(), spec AC35 (amendment B-511)
      - "packages/eng-harness/tests/workflow/edit_cycle/test_prompts.py"
      - "packages/eng-harness/tests/property/test_edit_cycle_sources.py"
      - "packages/eng-harness/tests/unit/edit_cycle/test_acceptance_entry.py"
    # Amendment B-354: the read-only entry point for A3 and A7 on real journals (spec AC35), about 70 lines; 80 -> 150.
    max_changed_lines: 150
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/edit_cycle/test_acceptance_entry.py::test_audit_and_count_read_run_folder"
      - "packages/eng-harness/tests/unit/edit_cycle/test_acceptance_entry.py::test_entry_is_read_only_and_exit_codes"
    covers: [AC25, AC26, AC35]
    # Amendment (B-533, documents only): T10 was split; the report functions are complete with T10b.
    depends_on: [T9b, T10b]
  - id: T12
    title: Replay test and crash matrix of the workflow (A6)
    # Amendment (B-417, documents only): folder renamed from tests/replay/edit_cycle/ so that its package name differs from tests/unit/edit_cycle/ (mypy duplicate module); no tests/replay/__init__.py.
    # Amendment (B-511, documents only): pre-flight audit. Both tests pin merged T9b and pass at the base, so this is a
    # test-only pull request (title type test, test files only, no failing-first run; gate spec 4.7), as engine plan
    # T19 (B-509); CHANGELOG.md leaves files.
    files:
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
    depends_on: [T9b]
  - id: T13
    title: The host port follows the working file that csi_open_revision opens (reopened hook)
    # Amendment (B-503, documents only): new. After csi_open_revision the AdapterHostPort keeps the old path, so
    # model_files, locate and model_state, the engine's model_saved for the restore (EC2) and the next host-state check
    # cannot find the restored file. AdapterHostPort.reopened(model_key, path) (about 14 lines) and a reopened callback
    # of CsiToolPort called after a successful open (about 6), 1 of CHANGELOG.md: budget 40 (an estimate). Before T9
    # (T9b since B-511), whose restore_previous needs it, and before plan 0002 T19a, which wires the callback and also edits _hostport.py.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_reopened.py"
    max_changed_lines: 40
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_csi_reopened.py::test_restore_moves_host_port"
    covers: [AC38]
    depends_on: [T5]
  - id: T14
    title: Calc harness.change_set_check refuses an item id with a slash (INVALID_ITEM_ID)
    # Amendment (B-513, documents only): new. Spec 4.4.1 K3 and AC4 require the issue INVALID_ITEM_ID and name the golden
    # cases check-item-id-*; the merged calc (T2, B-196) raises none and holds no such case. After T3, which also edits
    # calcs.lock.json. About 6 lines of the calc, 2 of the lock, 1 of CHANGELOG.md and 3 of the record: budget 40 (an estimate).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/change_set_check.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.change_set_check.md"
      - "packages/eng-harness/tests/golden/edit_cycle/test_change_set_check.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/check-item-id-*.json"
    max_changed_lines: 40
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/golden/edit_cycle/test_change_set_check.py::test_item_id_with_a_slash_is_refused"
    covers: [AC4]
    depends_on: [T3]
  - id: T16b
    title: The change-set values carry their canonical number and the check's references reach it (write arguments)
    # Amendment (B-544, documents only): new fix task for merged T1b and T2 code (first-live-run walk-through C17; spec
    # 4.3.1, 4.4.1 K4, AC40). A resolved value's ref names the value record or a key without a unit suffix, so the CSI
    # tool port refuses it as an engineering argument (INVALID_ARGUMENT or REF_UNIT_MISMATCH). About 20 lines in
    # _change_set.py (value_<suffix> filled and checked by eng_contract.units), 4 in change_set_check.py (the two ref
    # forms), 4 of the lock (the check and expected_effects import the model), 4 of the record, 1 of CHANGELOG.md: about
    # 33; budget 50 (an estimate). After T16 (change_set_check.py, calcs.lock.json, the record, the golden test).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_change_set.py"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/change_set_check.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.change_set_check.md"
      - "packages/eng-harness/tests/unit/edit_cycle/test_change_set.py"
      - "packages/eng-harness/tests/golden/edit_cycle/test_change_set_check.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/check-*.json"
    max_changed_lines: 50
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/edit_cycle/test_change_set.py::test_value_refs_are_write_arguments"
    covers: [AC40]
    depends_on: [T16]
  - id: T9c
    title: Step 9 opens D-2 on a failed check, and step 17 adds the exception items of the sign-off
    # Amendment (B-544, documents only): new (first-live-run walk-through C19, C25, C32; spec 4.5, 4.6, AC17, AC22, Q14
    # interim reading). The check inserted before the step 9 read raises ModelIntegrityError, which escalates, so D-2
    # never sees a READBACK_MISMATCH or READBACK_UNAVAILABLE; and the sign-off of a run with exceptions cannot be signed
    # without the exc_<n> items. About 15 lines for the route in _cycle.py, 20 for the items (the verdict results
    # collected per cycle in _cycle.py, numbered in _finish.py), 1 of CHANGELOG.md: about 36; budget 50 (an estimate).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_cycle.py"
      - "packages/eng-harness/src/eng_harness/workflows/model_edit_cycle/_finish.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/conftest.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_apply.py"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_promotion.py"
    max_changed_lines: 50
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/workflow/edit_cycle/test_apply.py::test_check_failure_routes"
      - "packages/eng-harness/tests/workflow/edit_cycle/test_promotion.py::test_sign_off_exception_items"
    covers: [AC17, AC22]
    depends_on: [T9b, T7b]
  - id: T15
    title: FB005 admits the integer version of block, workflow, decision_point and rule (gate configuration)
    # Amendment (B-511, documents only): new. .gate/forbidden.yml line 16 lists only calc and CheckMeta under
    # versioned.callables, so FB005 refuses the version=1 that @block, @workflow, @decision_point and @rule require in
    # workflows/** and rules/**. A protected path (r3 floor): the pull request shows the awaiting-owner notice, and a
    # pull request is judged by the policy of its base commit, so T7 waits for this task.
    files:
      - ".gate/forbidden.yml"
      - "tools/eng-dev-gate/tests/unit/test_forbidden_fb005.py"
    max_changed_lines: 10
    max_sessions: 1
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_forbidden_fb005.py::test_version_keyword_of_versioned_callable"
    covers: [AC2]
    depends_on: []
  - id: T16
    title: Calc harness.change_set_check refuses an item id that is not a page token, or is revision or unlock (INVALID_ITEM_ID)
    # Amendment (B-545, documents only): new fix task for merged T2 and T14 code (first-live-run walk-through C20, C29; spec
    # 4.4.1 K3, AC4). An id the check accepts but that is not a page token of at most 57 characters makes the step 6
    # change-set screen a refusal screen with no button. After T4b, which also edits calcs.lock.json and moves the hashes of
    # the calcs that import kinds/edit_cycle.py. About 8 lines of the calc, 4 of the lock, 3 of the record and 1 of
    # CHANGELOG.md: budget 30 (an estimate, measured analog T14).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/edit_cycle/change_set_check.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.change_set_check.md"
      - "packages/eng-harness/tests/golden/edit_cycle/test_change_set_check.py"
      - "packages/eng-harness/tests/data/golden/edit_cycle/check-item-id-*.json"
    max_changed_lines: 30
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/golden/edit_cycle/test_change_set_check.py::test_item_id_not_a_page_token_is_refused"
    covers: [AC4]
    depends_on: [T14, T4b]
---

# Implementation plan: eng-harness model edit cycle (spec 0007)

## 1. Approach

The spec is [0007](../specs/0007-model-edit-cycle.md); the owner-facing description is the
[workflow spec](../workflows/model-edit-cycle.md). `max_changed_lines` counts non-test, non-generated lines, as in
plans 0001 to 0006; golden data, journals and fixtures are test data.

Build the data first and the R1 parts early: the kinds and the change-set model (T1a, T1b), then the four calcs (T2 to T4b),
which carry the engineering checks and go to the owner for review as soon as they merge. The adapter additions (T5)
and the engine amendments (T6) are small, separate and reviewable on their own; T6 waits until the engine spec is
amended in its own documents pull request (spec Q2, Q3, Q5 and spec 0004 Q7), as B-068 does for earlier amendments.
The decision points and rules (T7) are R1 and reviewed separately from the block. The block is split in three (T8 steps
1 to 10, T9a steps 11 to 15, T9b steps 16 and 17, the loop and registration; amendment B-511), each tested end to end against the synthetic CSI fake server process. The
report and audit (T10), the prompt counter and timings (T10b) are pure functions over the journal. T11 and T12 add the acceptance
support and the replay suite, mostly tests. T10c and T16 fix merged code found by the first-live-run walk-through
(amendment B-545): the benchmark label's place in the stored answer, and the item ids the change-set screen can carry.
T7b, T16b and T9c (amendment B-544) follow the same walk-through and the owner's drift decision of 2026-11-16: T7b
(rule and points) after T7 and before T8, T16b (change-set values as write arguments) after T16 and before T8, and T9c
(the step 9 route and the step 17 exception items) after T9b; T9a carries the step 13 and 14 changes.

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

**T2 `harness.change_set_check`** (spec §4.4.1, rules K1 to K7). Golden cases for resolution, unknown names, duplicates,
item ids with `/` (B-498), bounds (including the unit-scale case of baseline د6), missing or unconfirmed sources,
conflicts with engineer changes, and every refused kind with its gap id. A verification record from the spec 0003
template, for the owner. Calc ships `draft`. Amendment (B-417): the task registers the calc in `REGISTRY` through
`calcs/__init__.py` (spec 0003 §4.2: explicit registration, no discovery), so the calc lock test and `ctx.calc` find it;
the bounds are the unit-suffixed paths of spec §4.8 (`bounds.thickness_min_mm`, `bounds.line_load_min_kN_m`,
`bounds.area_load_min_kPa`, `bounds.ratio_min_ratio` and their `_max` pairs). Amendment (B-493): the task adds the
edit-cycle entries of spec 0003 §4.3 to `tests/rules/test_calc_modules.py`:
`eng_harness.workflows.model_edit_cycle._change_set` by that module's name, never its package, and
`eng_harness.kinds.edit_cycle` if not already present (plan 0013 T2 adds the same entry under amendment B-462); T3 uses
the same imports without further amendment.

**T3 `harness.expected_effects`** (spec §4.4.2). The projection per kind, golden cases per kind and a property test
for item order. Ships `draft`. Amendment (B-417): registers the calc in `REGISTRY` through `calcs/__init__.py`,
after T2. Amendment (B-498): combination edits are projected per item under the item keys of spec 0003 §4.7 D2, a
`set` on an object the step 3 state lacks is an `add`, values come from the inputs `change_set` and `basis`, and
`test_combination_edit_reads_back` runs the merged read-back check (plan 0003 T9) on the projected effects (AC36); the
read-back calc is unchanged. Amendment (B-503): a `wall_section` on a section the step 3 state holds projects a `set`
of `/thickness_mm` and a `set` of `/material` on `model.sections/1` (the merged `WallSection` item carries `material`;
spec §4.4.2), so a redefinition with another material is not `unexpected`;
`test_wall_section_material_reads_back` runs the merged read-back check on that projection with an after read set
holding the new material and thickness (`PASS`, no `unexpected` row) and with the old material still read (`FAIL`, the
material effect `mismatch`) (AC37). The order of the items of an added combination is spec Q15, open: until it is
answered the projection keeps the change set's item order and no test pins another.
Amendment (B-513): the calc port stores `body | {calc, draft, trace}` and the store validates that record against the
kind (spec 0003 §4.2, §4.12 item 2), but `ExpectedEffects` in `kinds/calcs.py` is a plain model with `extra="forbid"`,
so the effects record could not be stored and the read-back's `effects` input could not read it back. Form: the three
members are added to `ExpectedEffects` as optional (`calc: CalcMeta | None = None`, `draft: StrictBool | None = None`,
`trace: Trace | None = None`), and the kind does not take the `CalcPayload` base that `ModelDiff`, `ReadbackCheck`,
`ChangeSetCheck` and the other calc kinds take, because that base requires the members and the merged bodies of this
kind hold none: the kind fixture `tests/data/kinds/calcs/expected_effects.json`, `tests/unit/calcs/test_readback.py` and
the four `readback-*.json` goldens (plan 0003 T4 and T9), which this task may not change. A trial with the base failed
the kind fixture test, nine read-back unit tests and the four read-back goldens. Spec 0003 §4.8 lists the domain fields
of the kind as it does for every calc kind, and spec 0003 §4.2 has the framework add `calc`, `draft` and `trace`, so
no spec text contradicts the form and none changes. `kinds/calcs.py` is in the content-hash closure of every calc: the
change moves seven entries of `calcs.lock.json` at the B-197 head (six merged calcs and this one; regenerate with
`uv run python -m eng_harness._calc._hash --write-lock`), and the record `harness.footing_subjects.md` pins its hash
literal (`tests/unit/footing/test_calcs_registered.py::test_metadata_and_constants`), so its literal follows; the
hashes of the six merged calcs change, so the owner's re-verification of those drafts is as for any hash change (spec
0003 §4.5). Trial on the head of B-197 in a scratch worktree (removed): the edit above, the regenerated lock and
`test_golden_bodies_are_valid_payloads` (each `effects-*` golden body validates through the kind bare and with the
wrapper; a test of the first commit, red at the base because its module imports the calc, and red at the
implementation head until `kinds/calcs.py` changes) gave `uv run eng-gate check --package eng-harness --skip mutation`
`check: pass`; files touched: `kinds/calcs.py`, `calcs.lock.json`, `harness.footing_subjects.md` and the golden test
file; 311 counted lines of 340.

**T4 Host design verdicts and analysis summary** (spec §4.4.3, §4.4.4). Steel mapping by comparison with
`limits.ratio_limit_ratio` (amendment B-417, spec §4.8); concrete gives `NEEDS_ENGINEER` (gap EC-G2); messages `unclassified` until the local test (gap
EC-G3). Golden cases with synthetic replies whose field names follow the S-12 inventory. Ship `draft`. Amendment
(B-417): registers both calcs in `REGISTRY` through `calcs/__init__.py`; it depends on T3 so that T2, T3 and T4 edit
`calcs/__init__.py`, `calcs/edit_cycle/__init__.py` and `calcs.lock.json` one after another. Amendment (B-503): the
inputs `harness.csi_design_results/1` and `harness.csi_analysis_messages/1` are typed with `CsiRows` imported from
`eng_harness.kinds.csi`, the module spec 0003 §4.3 admits, never from `eng_harness.adapters.csi._replies`; plan 0002
T21 moves the model there and adds the rules-test entry, so T4 waits for it (section 3).
Amendment (B-511): the registry refuses an output kind outside the `harness.` family (spec 0003 AC1; contract §4.10.1
refuses a calc kind in a neutral family), so `harness.host_design_verdicts` cannot output `verdicts.set/1` as spec
§4.4.3 said; the output kind was spec Q19. T4 builds `harness.analysis_summary` alone (its golden test and record),
and `harness.host_design_verdicts` is T4b.

**T4b Host design verdicts** (amendments B-511 and B-538; spec §4.4.3, AC3, AC30; spec 0003 §4.9). The calc as spec
§4.4.3 states it, with the input list B-511 adds there and the output kind of the owner's answer to spec Q19 (option
(a), 2026-11-16): `harness.host_design_verdicts/1` in `kinds/edit_cycle.py`, registered through `EDIT_CYCLE_KINDS`,
with its fixture under `tests/data/kinds/edit_cycle/` in `test_fixtures` (and the kind set of
`test_kinds_are_harness_family_and_registered`). The task also makes the merged design summary (plan 0003 T10, B-149)
accept that kind as spec 0003 §4.9 states: `test_host_design_verdicts_input` runs the summary on a
`harness.host_design_verdicts/1` reference and gets the body it gives for the same verdicts in a `verdicts.set/1`; the
summary's existing tests and goldens stay as they are, except the `ref_kinds` mark of `verdicts` in its schema test.
The lock moves the summary's hash and those of the calcs that import `kinds/edit_cycle.py`; the summary's record
follows. T9a waits for it (step 14).

**T5 Adapter additions** (spec §4.10, Q1). `csi_read_model_state`, `csi_open_revision`, `csi_read_analysis_messages`
and the `as_new_revision` argument of `csi_save_model`; allowlist entries (no escape hatch: each composes allowlisted
tools only, checked by plan 0002's allowlist contract test); fake extensions. Amendment B-505: the adapter-local tool
descriptors (the tools that are not server tools) live in `adapters/csi/_tools.py`, not in `_allowlist.toml`, because every
allowlist name must be a server tool (the build check, the doctor and the pinned-fingerprint contract test require it).

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
Amendment B-499: continuing the chain (engine §4.9, EC5) means that after each tool save and each engine `p~post.save`
under the approval, the expected state of the next step under it takes that `model_saved`'s revision, fingerprint and
file hash (`_approvals.py`; the merged engine T15 keeps only the revision a write produced).
Review fix B-415: `block.py` exposes `FieldSpec` through a `TYPE_CHECKING` import and a module-level `__getattr__`,
and imports `check_declaration` inside `workflow()`; a module-level import of `eng_harness.basis._fields` is an import
cycle (amendment B-511: loading it runs `basis/__init__.py`, whose `_port` reaches `ports`, `decisions` and
`decisions/_points.py`, which imports `eng_harness.block`). Never from the `eng_harness.basis` package (engine
§4.1.2), so spec 0005 AC42 holds; T6 runs
`tests/rules/test_decision_imports.py::test_types_module_is_block_safe` unchanged among its checks.
Amendment B-511: `BasisView.record_ref()` (engine §4.3.2), the reference `res_<id>` to the whole basis record that
every calc's `basis` input takes (spec 0003 §4.4); `ref(path)` gives a field's value, which the calc input refuses.
`test_basis_view_record_ref` (spec AC33) checks the reference and that it needs no declared path.

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
Amendment (B-542): `rules/edit_cycle.py` is in `r1_modules` of `pyproject.toml` (that entry is already in the files), so the
mutation step rewrites it in its copy of the package: the hash no longer matches `rules.lock.json` and mutmut inserts
`from mutmut.mutation.trampoline import ...`. Two tests tolerate that copy, only when `MUTANT_UNDER_TEST` is set:
`tests/contract/test_rule_lock.py` skips its lock comparison (spec 0005 AC10) and `tests/rules/test_block_modules.py`
does not judge the mutmut import (spec 0001 AC19). The skip raises the eng-harness skip count in `.gate/ratchet.json`
from 4 to 5. No other test and no budget changes.

**T7b Drift at D-3 and the failed-check reason at D-2** (amendment B-544; spec §4.6, AC18, Q20, Q14). In
`rules/edit_cycle.py`, `edit_cycle_analysis_messages.clean` returns `continue` only when the state has no error, no
unclassified message and `drift_status` `PASS` (the owner's decision of 2026-11-16), with a rationale that says so;
`readback_result_pass` is unchanged. In `workflows/model_edit_cycle/_points.py`, `ReadbackReason` gains
`check_model_failed` and `AnalysisState`'s docstring states how `drift_status` is read (spec §4.6); the state models
keep their fields. Both rules move to version 2, because `rules.lock.json` hashes the module source, and the point
`edit_cycle_readback_result` moves to version 2, because its state schema changes (spec 0005 AC4, AC10); both locks are
regenerated with `uv run python -m eng_harness.decisions --write-lock`. The first `test:` commit changes the last
assertion of `test_clean_boundary` (a drift state gives `None`; the spec changed, not the test's aim), adds
`check_model_failed` to `test_pass_boundary` (`None`), and adds `test_clean_drift_at_and_above_the_limit`, whose states
are derived by hand in its docstring from spec §4.4.4 and §4.6: a summary whose highest drift ratio equals the limit has
`exceeding` empty, so `drift_status` is `PASS` and the rule continues; a ratio just above it is in `exceeding`, so
`NEEDS_ENGINEER` and `None` (synthetic values, no limit is hard-coded in the rule). All three fail at the merge base.
The version assertion of `test_discovery_finds_the_points_and_rules` follows in the implementation commit.

**T8 Workflow part 1** (spec §4.2, §4.5 steps 1 to 10, §4.7, §4.8). Input and output models, `basis_fields`, the
child blocks `read_state`, `obtain_change_set` and `apply_change_set` (with D-2 and the approval-void loop), and the
blank template's `ask_each_run` list (paths only, no value, spec 0004 §4.8). Amendment (B-417): plan 0004 T9 has pinned
the template with an empty `ask_each_run`; this task fills it with the unit-suffixed paths of spec §4.8, and the new pin
is a golden change: the pull request carries the golden diff report and the change goes to the owner queue
(process/05 §5). The same paths are the `FieldSpec`s of `basis_fields` (spec 0004 AC21). Registration of the workflow
is T9b's (this task is at its 400-line cap): `block.discover()` stays empty here and `blocks.lock.json` is unchanged, so
`test_workflow_definition` checks the definition and not the lock. Tests drive the child blocks through test
workflows defined in `tests/workflow/edit_cycle/conftest.py`.
Amendment (B-533): the report support of T10b identifies a cycle by the `block` step whose `child.name` is `edit_cycle_once`;
T8 keeps that block name (and its `block` step kind) for the cycle child block.
Amendment (B-544): `EditCycleOutput.summaries` is the ordered tuple of spec §4.2 (the analysis summary, then one design
summary per kind of `design.run`), which T9a and T9b fill; step 8 passes each resolved `ref` unchanged as the tool's
engineering argument, valid once T16b has merged; the D-2 reason `check_model_failed` is T7b's and its route T9c's, and
the D-3 state that T9a builds follows spec §4.6 as amended by B-544 (`drift_status`).
Amendment (B-503): plan 0001 T22 stops on a `check_model` that is not clean, which the check inserted before the S'
read of step 9 can meet; how the block routes that stop is spec Q14 (open). Until Q14 is answered this task adds no
routing code: the inserted check's `ModelIntegrityError` escalates like any other `StepError`, and
`test_readback_failure_routes` tests AC17 with a read-back `FAIL` that `check_model` does not see (the fake writes each
wanted value and also changes an item the change set does not touch, so `harness.readback_check` reports it
`unexpected`). Prose, files, tests and budget are otherwise unchanged.

**T9a and T9b Workflow part 2** (spec §4.5 steps 11 to 17, §4.6, §4.7; split by amendment B-511). T9a:
`run_and_summarize` (analysis, design, results, D-3, summaries; D-2 and D-3 are never open together, spec §4.6) and the
engineer turn, tested through test workflows in `conftest.py`. T9b: the cycle loop, promotion and sign-off in
`_finish.py`, the registration, and the full-workflow tests. `test_unlock_under_change_set_approval` expects the interim `HOST_LOCKED`
stop until plan 0002 T15 (ADR-0031) merges, then the approved unlock; the test states both and is switched with T15.
Amendment (B-417): T9b registers the shipped workflow (spec §4.2): `workflows/__init__.py` exports the blocks of
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
Amendment (B-544; spec §4.5 steps 13 and 14, §4.6, AC41, AC42): T9a's step 13 parallel also calls
`csi_read_model_state` (`F`) and passes the drift read `cases` empty and `combos` every combination of `R[k]`'s
`harness.csi_name_lists/1`; step 14 runs `harness.host_design_verdicts` and `harness.design_summary` once per kind of
`design.run`, steel before concrete, with `F.frames` and that kind's previous summary; the D-3 state's `drift_status` is
`PASS` when the analysis summary's `exceeding` is empty and its `governing_drift` is not, else `NEEDS_ENGINEER`; the
turn's design status is the worse of the summaries' statuses in the order of spec 0003 §4.9 S5. `test_step_13_and_14_inputs`
runs a cycle with `design.run` `steel_and_concrete` and checks the calls, the two summaries and the absence of
`REF_STALE`; `test_drift_at_d3` seeds the fake's drift rows at the limit, just above it and empty (synthetic values)
and checks D-3. The workflow tests of the normal paths seed drift rows not above the limit (spec §4.9).

**T10 and T10b Report and B-1 support** (spec §4.9; split by amendment B-533). T10: renderers for the kinds of T1a and
value cells with sources (spec 0006 AC52) and `audit_value_sources`. T10b: `count_prompts`, `edit_cycle_timings`, the
timings section and `report/cycle-timings.json` (base names only). Both edit `report/_edit_cycle.py` and `CHANGELOG.md`
(T10b after T10); `_sections.py` is T10's alone, `_document.py` and `_write.py` T10b's. The scripted-journal helper
(`Script`, `PRODUCER`) is `tests/unit/edit_cycle/journal_script.py` (T10); `write_cycles` is in `test_timings.py` (T10b).
Budgets from the counts measured on the complete implementation: T10 157 (limit 170), T10b 301 (limit 315).
Amendment (B-511): the timings section is extended in `_document.py` by calling `edit_cycle_timings`, only when
the journal holds edit-cycle steps, so the existing report snapshots stay unchanged. Renderers are registered from
`_sections.py` by a lazy import of `_edit_cycle`, not from `report/__init__.py` or `_model.py`, which T10 does not
list. `audit_value_sources` takes `engineering_params` (tool name to parameter names, spec §4.9, AC25); its tests pass
it explicitly (a forged literal at a listed parameter is reported, a literal at an unlisted one is not).
Amendment (B-533): `edit_cycle_timings(reader, store=None)` takes the optional store for the `benchmark_request` label
(spec §4.9). `write_cycle_timings` in `_write.py` has no caller until the report command is wired (plan 0006 T16,
which exports both functions from `report/__init__.py`; amendment B-536).

**T10c Benchmark label in the stored answer** (amendment B-545; spec §4.9, AC29). `_benchmarks` in
`report/_edit_cycle.py` reads the label at `fields["benchmark_request"]["value"]`; the engine's `ask` stores one entry
per field of the asked model, and `ChangeSetRequest` has the one field `change_set` (spec §4.3.1), so the label is at
`fields["change_set"]["value"]["benchmark_request"]`. T10c reads it there and nowhere else (one shape, the one a real
run journals). `Script.answer` in `journal_script.py` stores the answer in that shape
(`{"change_set": {"value": {"items": [...], "benchmark_request": label}, ...}}`), so the existing benchmark tests
follow the fix; `test_benchmark_label_in_the_change_set_answer` builds such an answer itself and checks the label and
its elapsed time, and fails at the merge base, where `benchmarks` is empty. `ChangeSetRequest` is not merged (T8), so
the test writes the dictionary, not the model.

**T11 Acceptance support** (spec AC25, AC26). The prompt-count check over the workflow scenarios of T8, T9a and T9b (the
A7 bound on the normal paths of spec §4.9, failure and escalation paths counted and reported) and the
property test over generated change sets; the needs-local-test items of spec §12 in `docs/local-testing.md`.
Amendment B-354 (spec AC35, Q11): `python -m eng_harness.report` with `audit-sources RUN_DIR` and
`count-prompts RUN_DIR`, a read-only wrapper over the T10 and T10b functions so that the owner can run A3 and A7 on the
journals of the local B-1 runs; no seventh `eng-harness` command. `docs/local-testing.md` names the command form
`uv run --package eng-harness python -m eng_harness.report ...` (spec 0006 §4.1).
Amendment (B-511): `audit-sources` passes `engineering_params()` of `adapters/csi/_tools.py`: per tool of
`tool_allowlist()`, the fields of its argument model (`EDIT_MODELS | ANALYSIS_MODELS`) marked `engineering_quantity`,
the rule `AdapterToolPort.describe` uses for `ToolInfo.engineering_params` (spec AC35); T13 and plan 0002 T15 also
edit `_tools.py` (whichever lands later adapts). Test order: the first `test:` commit holds only the two
`test_acceptance_entry.py` tests; `tests/workflow/edit_cycle/test_prompts.py` and
`tests/property/test_edit_cycle_sources.py` come in a later commit of the same task (they pass at the base, TF004).

**T12 Replay and crash matrix** (spec AC27, AC28). A two-cycle run killed at every step in a worker process (plan 0001
T19's harness) and resumed with the same scripted answers; the replay test over a journal recorded by the
uninterrupted run. Amendment (B-511): a test-only pull request, title type `test(eng-harness)`, as engine plan T19.

**T13 Reopened hook** (amendment B-503; spec §4.10, AC38). `AdapterHostPort.reopened(model_key, path)` binds
`model_key` to `path` on the instance it is already bound to (`model_files`, `locate` and `model_state` then use the new
file), drops the last state read so that the next `model_state` starts a new outside-edit baseline, and persists the
adapter run state; `CsiToolPort` takes a `reopened` callback like `wrote` and calls it with the model key and the new
working file after a successful `csi_open_revision` only. The model identity of the restored file is spec Q16 (open):
until it is answered, `reopened` keeps the binding's model id and records the file as its next revision
(`IdentityStore.record_save`), and the test does not pin the revision number. `test_restore_moves_host_port` wires a
`CsiToolPort` to an `AdapterHostPort` against the synthetic CSI fake, saves a snapshot, opens it with
`csi_open_revision`, and checks the host port's `model_files`, `locate` and first `model_state` (no
`MODEL_CHANGED_OUTSIDE`); a refused open (a changed snapshot, `CONFLICT`) leaves the previous file bound. Plan 0002
T19a passes `host.reopened` in `build_ports`.

**T14 Item id with a slash** (amendment B-513; spec §4.4.1 K3, AC4). `harness.change_set_check` raises the error issue
`INVALID_ITEM_ID` for an item id that contains `/` (a refused kind included), and the golden cases `check-item-id-*` and
`test_item_id_with_a_slash_is_refused` pin it. The merged calc (T2, B-196) gives none: a trial run of an item `a/b` gave
only the issues of its other rules, and T2's golden files hold no such case. The task changes no other rule of the check.
Open, not built (spec §11 Q18): two terms of one `load_combination_set` item with the same item key (`case.case`,
`case.case_type`, `case.step`) are not refused either; K3 speaks of two items, so the spec does not require it and no
test pins either behaviour.

**T16b Change-set values as write arguments** (amendment B-544; spec §4.3.1, §4.4.1 K4, AC40). In `_change_set.py`
each input value model holds `value_<suffix>` (`value_mm`, `value_kN_m`, `value_kPa`, `value_ratio`): a `before`
validator fills it from `value` and `unit` by `eng_contract.units` when it is absent and refuses a given one that
differs from that conversion, so the stored answer validates again on replay; the column workflow's requests reuse the
models and their round-trip test stays as it is. In `change_set_check.py` a resolved value's `ref` gains `/value`
(basis) or `/value_<suffix>` (input). No bound, unit rule or issue changes, and the calc keeps version 1 (spec §4.4.1).
The lock moves the entries of the check and of `harness.expected_effects` (both import the model); the record gains
the reference form. `test_value_refs_are_write_arguments` stores an answer as the engine does, runs the check, and
validates each resolved ref with `eng_contract` `validate_input(..., InputPolicy(require_refs=True))` against
`DefineWallSectionArgs`, `SetFrameLoadDistributedArgs` and `AddLoadPatternArgs`: 0.2 m gives 200 mm (derived by hand
from the contract's unit table); it fails at the merge base with `INVALID_ARGUMENT`. The golden outputs of the check
change their `ref` strings only.

**T9c Failed check at step 9 and exception items at step 17** (amendment B-544; spec §4.5, §4.6, AC17, AC22, Q14). The
step 9 block catches `ModelIntegrityError` from the S' read and opens D-2 with the state of spec §4.6 (reason
`check_model_failed`, `NEEDS_ENGINEER`, flags false, the step 6 expected effects as refs); `test_check_failure_routes`
has the fake change a written value before the inserted check, so `check_model` reports `READBACK_MISMATCH`, and checks
that D-2 opens, analysis does not run and `restore_previous` works. Step 17 adds after the outputs one item `exc_<n>`
per exception of every cycle's `harness.host_design_verdicts/1` results in call order (spec §4.5); the cycle loop
keeps those references. `test_sign_off_exception_items` runs two cycles whose verdicts hold `FAIL` and `NEEDS_ENGINEER`
rows, checks the items and their order against the sign-off screen of plan 0006 T9c (each exception row has a reason
field), and signs with a reason per exception; it fails at the merge base, where the request has no `exc_` item.

**T15 FB005 and the block version** (amendment B-511; spec AC2, gate spec §4.8 A4). `.gate/forbidden.yml` line 16
becomes `callables: [calc, CheckMeta, block, workflow, decision_point, rule]`; nothing else of FB005 changes. The first
`test:` commit extends `test_version_keyword_of_versioned_callable` with `@block(..., version=1)`,
`@workflow(..., version=1)`, `@decision_point(..., version=1)` and `@rule(..., version=1)` in a block and a rule module
(not FB005), while a float, a positional or an expression `version` of them stays FB005; it fails at the base because
the test reads the committed policy. Gate spec §4.8 A4 already says "initially" for its list and AC33a holds for any
listed callable, so no gate document changes. `.gate/**` is protected (r3 floor): the pull request shows the
awaiting-owner notice and the owner approves the policy change; T7, and through it T8, T9a and T9b, start after it.

**T16 Item id that is not a page token** (amendment B-545; spec §4.4.1 K3, AC4). `harness.change_set_check` raises
`INVALID_ITEM_ID` for an item id that does not fully match `[A-Za-z0-9_.-]{1,57}` (ASCII) or that is `revision` or
`unlock`, with a `detail` naming the rule and spec 0007 §4.4.1 K3; an id with `/` keeps T14's detail and golden cases
(one issue per id). The merged `test_item_id_without_a_slash_is_not_refused` uses the id literal `"a-b.c_1\\d"` (a backslash), which the token
rule refuses: it takes a token id in the implementation commit (it passes at the base, so it is not in the `test:`
commit). The calc carries the pattern and the two ids itself (it imports nothing from `pages`), citing
spec 0006 AC49 and the 7-character field prefixes. A new golden case `check-item-id-token.json` (ids with a space, a
non-ASCII letter, 58 characters, `revision` and `unlock` refused; 57 characters and `a.b_c-1` accepted; derivations by
hand) and `test_item_id_not_a_page_token_is_refused`, which fails at the merge base (an id `beam 1` gives no issue);
the verification record and the lock follow. Version 1 stays (spec §4.4.1 decision). T16 waits for T4b (both edit
`calcs.lock.json`).

## 3. Dependencies

- Runtime: none new. Development: none new (Hypothesis and pytest from plan 0001 T1).
- Work items of other plans that must be merged before each task (same plan ids as in their files):

| Task | Needs merged |
|---|---|
| T1a, T1b | eng-contract T11, T12 (kinds); plan 0001 T1, T3 (`_kinds.py`); plan 0003 T4 (kinds package) |
| T2 | plan 0003 T1 to T6 (calc framework, hash, approvals, port, rules test, golden loader), T8b (difference report calc, split by B-458); plan 0004 T5 (`FieldSpec`); B-417 (unit-suffixed basis paths, spec §4.8); eng-contract plan 0001 T19 (work item B-464, the path rule of spec Q12 (a), owner decision OQ-Q44), because the `_kN_m` and `_kPa` bounds cannot be stored in `basis.design_basis/1` before it |
| T3 | plan 0003 T9 (`harness.expected_effects/1`, read-back check) |
| T4, T4b | plan 0003 T10 (design summary); plan 0002 T13 (design results and analysis kinds) and T21 (`CsiRows` in `eng_harness.kinds.csi`, amendment B-503); B-417 (`limits.ratio_limit_ratio`, spec §4.8); T4b also T4 (both edit the calc registry files); the owner's answer to spec Q19 is recorded (amendment B-538) |
| T5 | plan 0002 T4, T11 to T14 (fake, reader, edits, analysis, reconciliation); plan 0002 T21 waits for T5, not T5 for T21: T5's `test_csi_read_state_tool.py` builds `HARNESS_KINDS.extend(CSI_KINDS)`, which `extend` refuses once T21 registers `CSI_KINDS`, so T21 adapts that line (amendment B-503) |
| T6 | plan 0001 T5, T15, T16 (registry, approvals, modes), T16b (it shares `_modes.py` and `_ctx_impl.py`, B-499), T11c (split from T11b by B-427; `_hoststate.py`, `_runner.py`: host-state check and resume order, extended for EC2, amendment B-415), T22 (it shares `_invariants.py`, amendment B-503); the engine spec amendment, work item B-415 (documents pull request; engine spec §3.9 rules EC1 to EC6, covered by spec AC33) |
| T7 | plan 0005 T1 to T4, T7 (points, rules, cascade core; T2 and T4 carry the discovery of spec 0005 §4.2 and §4.4); T15 of this plan (FB005, amendment B-511) |
| T8 | plan 0001 T10 to T17 and T22 (the stop on a check that is not clean, which step 9 can meet; until spec Q14 is answered T8 adds no routing for it, see T8; amendment B-503); plan 0002 T19a (amendment B-475); plan 0004 T8 to T10; plan 0005 T10; plan 0006 T7 (answer models); B-417 (unit-suffixed basis paths, spec §4.8); eng-contract plan 0001 T19 (work item B-464, owner decision OQ-Q44) and the renames in specs 0002 and 0003 of spec Q12 (owner queue, no work item yet), so that a basis holding the §4.8 paths can be frozen and the calcs' `basis_fields` equal the declared paths |
| T9a | plan 0002 T13 (analysis and design tools); plan 0006 T10 (engineer-turn labels) |
| T9b | plan 0001 T16b (promotion; B-499); plan 0002 T15 (for the final unlock test) |
| T10, T10b | plan 0006 T11 to T13 (report model, sections, document) |
| T11 | plan 0006 T14 is not needed: the tests drive the engine directly |
| T12 | plan 0001 T19 (crash-matrix worker); plan 0002 T19a (amendment B-475) |
| T13 | nothing outside this plan beyond T5's needs (amendment B-503); plan 0002 T19c and T19a wait for T13 (all three edit `adapters/_hostport.py`; T19c by amendment B-530), and T13 and plan 0002 T15 both edit `csi/_tools.py` without an order (whichever lands second adapts) |
| T14 | T3 (both edit `calcs.lock.json`; T2 is merged; amendment B-513) |
| T7b, T16b | nothing outside this plan (amendment B-544); T8 waits for both |
| T9c | plan 0006 T9c (the sign-off screen reads `harness.host_design_verdicts/1`; amendment B-544) |
| T10c | nothing outside this plan (amendment B-545) |
| T16 | T4b of this plan (both edit `calcs.lock.json`; amendment B-545) |
| T15 | gate plan T39 (FB005 form A4, merged); the owner's approval of the protected change (amendment B-511) |

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

Each task is one squash-merged pull request into `build/v1`; a revert removes it and its dependants (T8, T9a and T9b
depend on T2 to T7). Until T9b merges, nothing registers the workflow (amendment B-417: `block.discover()` reads
`workflows/__init__.py`, which T9b creates). Calcs, points, rules and blocks are versioned with lock
files, so a fix after runs have been journaled is a new version; old journals keep replaying against the version they
recorded (engine §4.2) or stop with `ReplayDivergence`, never silently.
