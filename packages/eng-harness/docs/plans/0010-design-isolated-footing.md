---
id: plan-b075-design-isolated-footing
issue: "B-075"
spec: packages/eng-harness/docs/specs/0010-design-isolated-footing.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2, r3]       # binding for every pull request of this plan; r2 from T1 (kinds), r3 from T2 (pyproject.toml, uv.lock)
tasks:
  - id: T1
    title: Footing kinds and their registration
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/kinds/footing.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/contract/test_footing_kinds.py"
      - "packages/eng-harness/tests/data/kinds/footing/**"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_footing_kinds.py::test_fixtures"
    covers: [AC33]
    depends_on: []
  - id: T2
    title: Code-pack route of the CalcPort and the structural-codes workspace dependencies
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/pyproject.toml"
      - "uv.lock"
      - "packages/eng-harness/src/eng_harness/_calc/_code_packs.py"
      - "packages/eng-harness/src/eng_harness/_calc/_port.py"
      - "packages/eng-harness/tests/unit/calcs/test_code_pack_route.py"
      - "packages/eng-harness/tests/unit/calcs/fixtures/code_pack/**"
    max_changed_lines: 320
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/calcs/test_code_pack_route.py::test_batch_stored_as_verdict_set"
      - "packages/eng-harness/tests/unit/calcs/test_code_pack_route.py::test_production_refuses_draft"
      - "packages/eng-harness/tests/unit/calcs/test_code_pack_route.py::test_unknown_id"
      - "packages/eng-harness/tests/unit/calcs/test_code_pack_route.py::test_literal_refused"
    covers: [AC3, AC4]
    depends_on: []
  - id: T3
    title: Calc harness.footing_subjects and the footing calc package
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/footing/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/footing/subjects.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.footing_subjects.md"
      - "packages/eng-harness/tests/unit/footing/__init__.py"
      - "packages/eng-harness/tests/unit/footing/test_calcs_registered.py"
      - "packages/eng-harness/tests/golden/footing/__init__.py"
      - "packages/eng-harness/tests/golden/footing/test_subjects.py"
      - "packages/eng-harness/tests/data/golden/footing/subjects-*.json"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/footing/test_subjects.py::test_golden_cases"
      - "packages/eng-harness/tests/unit/footing/test_calcs_registered.py::test_metadata_and_constants"
    covers: [AC6, AC12]
    depends_on: [T1]
  - id: T4
    title: Calcs harness.footing_plan_size and harness.footing_resize
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/footing/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/footing/plan_size.py"
      - "packages/eng-harness/src/eng_harness/calcs/footing/resize.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.footing_plan_size.md"
      - "packages/eng-harness/docs/verification/calcs/harness.footing_resize.md"
      - "packages/eng-harness/tests/unit/footing/test_calcs_registered.py"
      - "packages/eng-harness/tests/golden/footing/test_plan_size.py"
      - "packages/eng-harness/tests/golden/footing/test_resize.py"
      - "packages/eng-harness/tests/property/test_footing_plan_size.py"
      - "packages/eng-harness/tests/data/golden/footing/plan-*.json"
      - "packages/eng-harness/tests/data/golden/footing/resize-*.json"
    max_changed_lines: 360
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/golden/footing/test_plan_size.py::test_golden_cases"
      - "packages/eng-harness/tests/property/test_footing_plan_size.py::test_minimal_and_monotone"
      - "packages/eng-harness/tests/golden/footing/test_resize.py::test_golden_cases"
    covers: [AC7, AC9]
    depends_on: [T3]
  - id: T5
    title: Calc harness.footing_layout
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/footing/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/footing/layout.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.footing_layout.md"
      - "packages/eng-harness/tests/unit/footing/test_calcs_registered.py"
      - "packages/eng-harness/tests/golden/footing/test_layout.py"
      - "packages/eng-harness/tests/property/test_footing_layout.py"
      - "packages/eng-harness/tests/data/golden/footing/layout-*.json"
    max_changed_lines: 240
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/footing/test_layout.py::test_golden_cases"
      - "packages/eng-harness/tests/property/test_footing_layout.py::test_spacing_bound"
    covers: [AC8]
    depends_on: [T3]
  - id: T6
    title: Calcs harness.footing_status and harness.footing_schedule (with clearance)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/footing/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/footing/status.py"
      - "packages/eng-harness/src/eng_harness/calcs/footing/schedule.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.footing_status.md"
      - "packages/eng-harness/docs/verification/calcs/harness.footing_schedule.md"
      - "packages/eng-harness/tests/unit/footing/test_calcs_registered.py"
      - "packages/eng-harness/tests/golden/footing/test_status.py"
      - "packages/eng-harness/tests/golden/footing/test_schedule.py"
      - "packages/eng-harness/tests/data/golden/footing/status-*.json"
      - "packages/eng-harness/tests/data/golden/footing/schedule-*.json"
    max_changed_lines: 340
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/golden/footing/test_status.py::test_golden_cases"
      - "packages/eng-harness/tests/golden/footing/test_schedule.py::test_golden_cases"
    covers: [AC10, AC11]
    depends_on: [T3]
  - id: T7
    title: Decision points footing_fix_strategy and footing_review, and the footing rules
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/isolated_footing/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/isolated_footing/_points.py"
      - "packages/eng-harness/src/eng_harness/rules/footing.py"
      - "packages/eng-harness/src/eng_harness/decisions.lock.json"
      - "packages/eng-harness/src/eng_harness/rules.lock.json"
      - "packages/eng-harness/tests/unit/footing/test_point.py"
      - "packages/eng-harness/tests/rules/test_footing_rules.py"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/footing/test_point.py::test_point_definition"
      - "packages/eng-harness/tests/rules/test_footing_rules.py::test_typical_and_boundary"
      - "packages/eng-harness/tests/rules/test_footing_rules.py::test_order"
    covers: [AC13, AC14]
    depends_on: [T1]
  - id: T8
    title: Block design_isolated_footing (rounds, batched checks, decisions, engineer dimensions, resize)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/isolated_footing/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/isolated_footing/_block.py"
      - "packages/eng-harness/src/eng_harness/blocks.lock.json"
      - "packages/eng-harness/tests/workflow/footing/__init__.py"
      - "packages/eng-harness/tests/workflow/footing/conftest.py"
      - "packages/eng-harness/tests/workflow/footing/test_block.py"
      - "packages/eng-harness/tests/workflow/footing/test_decisions.py"
      - "packages/eng-harness/tests/data/footing/**"
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/footing/test_block.py::test_enlarge_until_pass"
      - "packages/eng-harness/tests/workflow/footing/test_block.py::test_shear_deepens"
      - "packages/eng-harness/tests/workflow/footing/test_block.py::test_flexure_reduces_spacing"
      - "packages/eng-harness/tests/workflow/footing/test_block.py::test_attempts_exhausted_closes_open_footings"
      - "packages/eng-harness/tests/workflow/footing/test_block.py::test_eccentric_reaction_needs_engineer"
      - "packages/eng-harness/tests/workflow/footing/test_block.py::test_engineer_dimensions"
      - "packages/eng-harness/tests/workflow/footing/test_block.py::test_combine_closes"
      - "packages/eng-harness/tests/workflow/footing/test_block.py::test_limit_closes"
      - "packages/eng-harness/tests/workflow/footing/test_decisions.py::test_shadow_suggestion_not_applied"
      - "packages/eng-harness/tests/workflow/footing/test_decisions.py::test_no_provider"
      - "packages/eng-harness/tests/workflow/footing/test_decisions.py::test_one_screen_per_round"
    covers: [AC15, AC16, AC17, AC18, AC19, AC20]
    depends_on: [T2, T4, T5, T6, T7]
  - id: T9
    title: Workflow isolated_footing_design (definition, basis fields, steps 1 to 13, review, code packs)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/isolated_footing/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/__init__.py"
      - "packages/eng-harness/src/eng_harness/blocks.lock.json"
      - "packages/eng-harness/tests/unit/footing/test_definition.py"
      - "packages/eng-harness/tests/unit/footing/test_inputs.py"
      - "packages/eng-harness/tests/rules/test_footing_modules.py"
      - "packages/eng-harness/tests/workflow/footing/conftest.py"
      - "packages/eng-harness/tests/workflow/footing/test_workflow.py"
      - "packages/eng-harness/tests/workflow/footing/test_code_packs.py"
      - "packages/eng-harness/tests/fixtures/templates/synthetic-footing-*.yaml"
    max_changed_lines: 360
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/footing/test_definition.py::test_workflow_and_blocks"
      - "packages/eng-harness/tests/unit/footing/test_inputs.py::test_safe_source_gap"
      - "packages/eng-harness/tests/rules/test_footing_modules.py::test_modules_follow_block_rules"
      - "packages/eng-harness/tests/workflow/footing/test_workflow.py::test_etabs_read_only"
      - "packages/eng-harness/tests/workflow/footing/test_workflow.py::test_not_analysed_stops"
      - "packages/eng-harness/tests/workflow/footing/test_workflow.py::test_unknown_cases_asked_again"
      - "packages/eng-harness/tests/workflow/footing/test_workflow.py::test_seismic_refusal"
      - "packages/eng-harness/tests/workflow/footing/test_workflow.py::test_approvals_per_mode"
      - "packages/eng-harness/tests/workflow/footing/test_code_packs.py::test_sbc_all_need_engineer"
    covers: [AC1, AC2, AC5, AC21, AC22, AC23, AC30]
    depends_on: [T8]
  - id: T10
    title: Calcs harness.reactions_to_joint_loads and harness.safe_equilibrium
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calcs/footing/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/footing/reactions_to_loads.py"
      - "packages/eng-harness/src/eng_harness/calcs/footing/safe_equilibrium.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/docs/verification/calcs/harness.reactions_to_joint_loads.md"
      - "packages/eng-harness/docs/verification/calcs/harness.safe_equilibrium.md"
      - "packages/eng-harness/tests/unit/footing/test_calcs_registered.py"
      - "packages/eng-harness/tests/golden/footing/test_reactions_to_loads.py"
      - "packages/eng-harness/tests/golden/footing/test_equilibrium.py"
      - "packages/eng-harness/tests/data/golden/footing/loads-*.json"
      - "packages/eng-harness/tests/data/golden/footing/equilibrium-*.json"
    max_changed_lines: 320
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/golden/footing/test_reactions_to_loads.py::test_golden_cases"
      - "packages/eng-harness/tests/golden/footing/test_equilibrium.py::test_golden_cases"
    covers: [AC24, AC25]
    depends_on: [T3]
  - id: T11
    title: Block footing_safe_cross_check and the allowlist contract test
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/workflows/isolated_footing/__init__.py"
      - "packages/eng-harness/src/eng_harness/workflows/isolated_footing/_safe.py"
      - "packages/eng-harness/src/eng_harness/blocks.lock.json"
      - "packages/eng-harness/tests/workflow/footing/conftest.py"
      - "packages/eng-harness/tests/workflow/footing/test_safe_stage.py"
      - "packages/eng-harness/tests/contract/test_footing_tools.py"
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"
      - "packages/eng-harness/tests/data/footing/**"
    max_changed_lines: 300
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/footing/test_safe_stage.py::test_stage_steps"
      - "packages/eng-harness/tests/workflow/footing/test_safe_stage.py::test_candidate_pressure_no_verdict"
      - "packages/eng-harness/tests/workflow/footing/test_safe_stage.py::test_soil_pressure_limit_reported"
      - "packages/eng-harness/tests/workflow/footing/test_safe_stage.py::test_stage_off_and_missing_fields"
      - "packages/eng-harness/tests/contract/test_footing_tools.py::test_tools_allowlisted"
    covers: [AC26, AC27, AC28]
    depends_on: [T9, T10]
  - id: T12
    title: Report sections (schedule, calculation notes), acceptance audits and the local-testing list
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_footing.py"
      - "packages/eng-harness/src/eng_harness/report/__init__.py"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/tests/unit/report/test_footing_report.py"
      - "packages/eng-harness/tests/data/golden/report/footing-*.html"
      - "packages/eng-harness/tests/workflow/footing/test_acceptance.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/report/test_footing_report.py::test_sections_and_marks"
      - "packages/eng-harness/tests/workflow/footing/test_acceptance.py::test_value_sources_and_prompts"
    covers: [AC29, AC31]
    depends_on: [T9]
  - id: T13
    title: Replay, crash matrix and hash-seed determinism of the footing workflow
    files:
      - "packages/eng-harness/tests/replay/test_footing_replay.py"
      - "packages/eng-harness/tests/data/journals/footing/**"
    max_changed_lines: 60
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/replay/test_footing_replay.py::test_crash_matrix"
      - "packages/eng-harness/tests/replay/test_footing_replay.py::test_replay"
      - "packages/eng-harness/tests/replay/test_footing_replay.py::test_hash_seed"
    covers: [AC32]
    depends_on: [T11, T12]
---

# Implementation plan: eng-harness isolated footing design (spec 0010)

## 1. Approach

The spec is [0010](../specs/0010-design-isolated-footing.md); the owner-facing description is the
[workflow spec](../workflows/isolated-footing-design.md). `max_changed_lines` counts non-test, non-generated lines, as in
plans 0001 to 0009; golden data, fixtures and journals are test data. File paths are relative to the workspace root.

Data first, then the R1 parts, each small enough to review against its spec section: the kinds (T1); the code-pack
route (T2), the one framework change, kept apart from engineering content because it touches the CalcPort and adds the
workspace dependencies; the six footing calcs in four tasks (T3 to T6), which carry the sizing and go to the owner as soon
as they merge; the decision point and rules (T7), reviewed separately from the block. The block (T8) and the workflow
(T9) are tested end to end against the synthetic CSI fake server process with the real ACI 318-14 and SBC 304-2018 packs.
The SAFE stage is last (T10, T11), because it depends on the SAFE adapter and never changes a verdict: the workflow is
useful without it. T12 adds the report sections and the acceptance audits; T13 is the replay suite, mostly tests.

Reuse (spec §2): plans 0001 to 0009 and the structural-codes packs; no code is copied from Sasaah or elsewhere (A12). The
footing calcs do not reuse `harness.section_round`, whose single increment field does not fit plan and depth. Tests use
the synthetic CSI fake (plan 0002 T4, SAFE mode from plan 0008 T2, in `tests/fakes/sasaah_csi/**`), extended in T8
with joint-reaction replies for the footing scenarios and in T11 with a prepared SAFE model (points, load patterns,
soil-pressure and base-reaction replies); both tasks list the fake's files, and the scenario data lives under
`tests/data/footing/**`, the fake decision provider of plan 0009, scripted page answers, `FixedClock` and `SeededIdSource`.

Every calc and rule ships `draft`; nothing is added to `approvals.yaml` (ADR-0028 §4). Every test value is synthetic and
labelled so; no case reproduces a project.

## 2. Tasks

**T1 Kinds** (spec §4.2). The six kinds in `kinds/footing.py`, registered in `_kinds.py`, with valid and invalid fixtures.
No logic beyond validation.

**T2 Code-pack route** (spec §4.3, Q10, Q11). `CodePackRoute` (describe, run, item limit, storage as `verdicts.set/1`,
run-class refusal) and its use by `HarnessCalcPort`; the three `structural-codes` workspace packages as dependencies.
Tests use a small test pack built with `Registry.of` in `tests/unit/calcs/fixtures/code_pack/`, so the task does not wait
for the ACI pack. Starts only after the documents pull request that amends engine §4.8 and calcs §4.12 (spec Q10).
Spec 0013 §4.5 defines the same route (spec C3): if plan 0013 T6 has merged when T2 starts, T2 adds the footing ids,
the `items` argument and its tests to that route (the dependencies are then already in place), and the lead records
which by a plan amendment; otherwise T2 builds the route with both workflows' ids and plan 0013 T6 extends it. T2 also
starts only after the documents pull request that settles spec C4 (an id outside the allowlist gives `NOT_FOUND`, spec
0013 AC13 amended); T2 never changes an expectation of a merged test of that file to meet this spec (A4). Provenance is
`tool: "structural-codes"` in both specs.

**T3 Subjects** (spec §4.4.1). Creates `calcs/footing/`, the registration test shared by the calc tasks, and the first
verification record (from the spec 0003 template).

**T4 Plan size and resize** (spec §4.4.2, §4.4.4). Exact integer search on fractions; `LIMIT_REACHED`; FG-1. The
minimality and monotonicity properties run with Hypothesis.

**T5 Layout** (spec §4.4.3). Bar counts, areas, effective depths for both bottom layers and both reaction points.

**T6 Status and schedule** (spec §4.4.5, §4.4.6). Family statuses, closure, decision state, clearance by exact squared
distances, assembled schedule.

**T7 Points and rules** (spec §4.5). Two points with their state models, five rules with typical and boundary tests, lock
entries; the rules' review table goes to the owner (spec 0005 §4.4).

**T8 Block** (spec §4.6). The rounds loop with `ctx.attempts`, the six batched checks through the route of T2 with the
ACI pack, `decide_many`, engineer dimensions, resize and closures. Tests drive the block through a test workflow in
`tests/workflow/footing/conftest.py`.

**T9 Workflow** (spec §4.2, §4.7, §4.8). Definition, input and output models, `basis_fields`, steps 1 to 13 and 15, the
seismic refusal, the SAFE-source gap, the SBC run, approvals per mode, and registration in `workflows/__init__.py`
(the module through which the command line of plan 0006 T14 finds workflows; if that task names another module, this
task follows it and the file list is amended).

**T10 SAFE calcs** (spec §4.9 items 2 and 6). Matching, negation, missing patterns, combinations to add; equilibrium by
magnitude with the basis tolerance.

**T11 SAFE stage** (spec §4.9). The child block, its approval, the candidate-map rule, the soil-pressure limit, and the
contract test that every tool the workflow can call is in the CSI allowlist and none is an escape hatch.

**T12 Report and acceptance** (spec AC29, AC31, §12). Report sections (schedule, one calculation note per verdict set
through `structural_codes.notes.render_html`, decisions, sources, marks); the value-source and prompt-count audits over
the scenarios of T8, T9 and T11 (reusing plan 0007 T10's helpers); the needs-local-test items L1 to L6 in
`docs/local-testing.md`.

**T13 Replay** (spec AC32). Crash matrix in a worker process (plan 0001 T19), replay of a recorded journal, hash-seed
determinism. The non-test lines are at most a test-support helper.

## 3. Dependencies

- Runtime: the workspace packages `structural-codes-core`, `structural-codes-aci318-14` and
  `structural-codes-sbc304-2018` (T2; no third-party package, so no ADR, spec Q11). Development: none new.
- Work items of other plans that must be merged before each task (plan ids as in their files; "SC" is the
  structural-codes core plan, "ACI" its plan 0002, "SBC" its plan 0003):

| Task | Needs merged |
|---|---|
| T1 | eng-contract T11, T12 (kinds); plan 0001 T3 (`_kinds.py`); plan 0003 T4 |
| T2 | plan 0003 T5 (CalcPort); SC T8, T11 (evaluate, lifecycle); the documents pull request of spec Q10 |
| T3 to T6, T10 | plan 0003 T1 to T6 (calc framework, hash, approvals, port, rules test, golden loader); plan 0004 T5 (`FieldSpec`) |
| T7 | plan 0005 T1 to T4, T7 |
| T8 | plan 0001 T10, T14, T14b (ctx calls, decide, ask); plan 0005 T9 (`decide_many`); plan 0009 T5 is not needed (the fake provider is in plan 0005 T5); ACI T9 (registered pack) |
| T9 | plan 0001 T16, T17; plan 0002 T11, T13, T19; plan 0004 T8 to T10; plan 0006 T10 (choice screens); plan 0007 T6 (`copy_on_open`, `basis_fields`); SBC T3 |
| T10 | plan 0008 T5 (`harness.joint_loads/1`, points) |
| T11 | plan 0008 T6, T7 (load import, analysis, soil pressures, reactions) |
| T12 | plan 0006 T11 to T13 (report); plan 0007 T10 (audits); SC T13 (calculation notes) |
| T13 | plan 0001 T19 (crash-matrix worker) |

## 4. Verification

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` exists; until then, from `packages/eng-harness/`,
  `uv run ruff format --check`, `uv run ruff check`, `uv run mypy --strict src tests`, `uv run pytest` with coverage.
  The pull request links its CI run (process/05 §8).
- Fake-host workflow and replay tests on every pull request from T8 on; mutation on the R1 modules
  `calcs/footing/**`, `rules/footing.py` and `_calc/_code_packs.py`.
- Engineering content: the eight calcs, the five rules and the basis field list are R1, ship `draft`, and go to the owner
  queue with their verification records. No agent adds an `approvals.yaml` entry.
- Live acceptance needed before the first release (spec §12, written to `docs/local-testing.md` by T12): a full run on a
  copy of a real analysed ETABS model with the pinned `sasaah-csi-mcp` build (L1 to L3); the SAFE stage on a prepared copy
  with SAFE 22 (L4); the program comparisons of the ACI plan (L5); the decision model after spike S-07 (L6); the footing
  benchmark for F6 and F7 (spec Q16).
- Review: each pull request by a subagent that did not write it, with the correctness, Python, type-design,
  silent-failure and test lenses; T3 to T7 and T10 also against the R1 rules (no literal, cited method, golden sources);
  T2 and T11 also with the security lens (route refusal, allowlist). Second-family review and owner approvals are
  `awaiting owner`.

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; a revert removes it and its dependants (T8 depends on T2 and
T4 to T7; T9 on T8; T11 on T9 and T10). Until T9 merges, nothing registers the workflow. Calcs, points, rules and blocks
are versioned with lock files, so a fix after runs have been journaled is a new version; old journals keep replaying
against the version they recorded or stop with `ReplayDivergence`, never silently. Reverting T2 removes the
`structural-codes` dependencies with it.
