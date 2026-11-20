---
id: spec-0013-column-workflow
issue: "B-083"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1]
---

# Spec 0013: eng-harness column workflow (`column_design`, `column_revit_update`)

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-04

This spec builds the workflow of the [workflow spec](../workflows/column-design.md) ("WS §n"): phase 3 of
[19](../../../../design/docs/architecture/19-roadmap-and-spikes.md) §1, "design columns in ETABS and update Revit by
reference". It composes, and does not repeat: the edit cycle [spec 0007](0007-model-edit-cycle.md) ("EC §n"), the
engine [spec 0001](0001-engine.md) ("engine §n"), the CSI adapter [0002](0002-servers-and-adapters.md), calcs
[0003](0003-calcs.md), basis [0004](0004-templates-and-basis.md), decisions [0005](0005-decisions.md), page and report
[0006](0006-cli-progress-pages-report.md), the Revit adapter [0011](0011-revit-adapter.md) ("RV §n"), the SAP2000
coverage check [0012](0012-sap2000-adapter.md), the contract
[eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract §n"), the code-pack
framework [structural-codes spec 0001](../../../structural-codes/docs/specs/0001-core-framework.md) ("CF §n") and the
ACI 318-14 column checks of [plan 0004](../../../structural-codes/docs/plans/0004-aci318-14-column-checks.md)
("CK §n") with their clause specs. Values move by reference
([ADR-0005](../../../../design/docs/adr/0005-pass-by-reference.md)). Items marked **[added]** are not in the
architecture and are listed in §11.

## 1. Problem

Column review is one of the slow tasks of the Sasaah sessions (146 agent and 116 engineer minutes for load
combinations and the review of columns and beams, Sasaah `agent-sessions/_baseline/REPORT.md` §3); the sizing tool
used there divided loads by unsourced thresholds (S-12 OQ-G14), and a column orientation check passed while the columns
were rotated (baseline §5.5). The parts exist: the edit cycle writes and verifies ETABS changes, the code pack checks
column sections, the Revit adapter reads and writes column types, and `harness.frame_element_map` pairs ETABS frames
with Revit elements. What only this spec defines: which columns are checked with which demands, how a section change
is proposed (rounding calc, existing model section, rules, engineer), how the edit cycle's write path applies it, and
how the accepted ETABS sections reach Revit by reference, with read-back, under the limits of the Sasaah servers.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| Edit cycle (EC §4.5) | Read, difference report, approval, revision save, writes, read-back, analysis, design, engineer turn, promotion, sign-off | Reused as child blocks `read_state`, `apply_change_set`, `run_and_summarize` and `_finish` (Q3) |
| `harness.section_round` (0003 §4.10) | Smallest basis multiple not below a required size | Used for every proposed dimension; no rounding here |
| `harness.design_summary` (0003 §4.9) | Summary of one verdict set (`verdicts.set/1` or `harness.host_design_verdicts/1`, 0003 §4.9); traces are local to a payload, so sets cannot be merged | Its member method S5 is cited by `harness.column_review` (§4.4.3), which reads several sets by reference without copying verdicts |
| `harness.host_design_verdicts` (EC §4.4.3) | Steel ratio per frame; concrete `NEEDS_ENGINEER` | Used unchanged; concrete columns have no host verdict (CW-G1) |
| `harness.frame_element_map` (RV §4.11) | Exact geometric pairing, links as hints | Used unchanged |
| Code checks `aci318_14.22_4_2_1.max_axial_strength`, `aci318_14.22_4_1_1.axial_flexure_uniaxial`, `aci318_14.10_6_1_1.longitudinal_reinforcement_limits` (CK §1) | Draft, pure, `evaluate_batch` (CF §4) | Called through the CalcPort code-pack route (§4.5, C2) |
| Sasaah `classify-columns.ps1`, `column-angles` check (baseline) | Unsourced thresholds; a check that compared a constant with itself | Not used; selection is by the engineer plus geometry, orientation stays unverified (CW-G7) |
| SAP2000 through the CSI adapter (0012 §4.2) | No concrete column design results (SP-3), no design orientation (SP-5) | Not in v1 (Q9) |

No runtime dependency is added. `eng-harness` already may import `structural-codes` (CF §1 consumers).

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Fake-host workflow test" runs the real engine, the real CSI and
Revit adapters against the synthetic CSI and Revit fake servers (spec 0002 §4.8.3, RV §4.13, lead decision D-5), the
real `structural-codes` pack, a real journal and store, and scripted page ports (spec 0006 fakes). Golden data lives in
`tests/data/golden/column_design/`, each case with a `source` naming the section of this spec that defines its method;
values are synthetic and say so.

### 3.1 Definitions, requests, kinds

- AC1. Given the workflow modules, when loaded, then `column_design` (version 1) is a `WorkflowDef` whose
  `basis_fields` are §4.7 table A, `min_server_builds` the CSI pin, `always_ask` `csi_unlock_model`, `copy_on_open`
  true; and `column_revit_update` (version 1) has §4.7 table B, the CSI and Revit pins, `copy_on_open` true and
  `allowed_modes = ("approve_each_write",)` **[added]**; both are in `blocks.lock.json`. Test:
  `tests/unit/column_design/test_definition.py::test_workflow_definitions`.
- AC2. Given the workflow, rule and point modules, when scanned, then they import only what engine §4.1.2 allows and
  hold no numeric literal, no `while` and no I/O. Test: `tests/rules/test_column_design_modules.py::test_modules_follow_block_rules`.
- AC3. Given valid and invalid answers files for `ColumnScopeRequest`, `ColumnLayoutRequest` and
  `ColumnProposalRequest` (§4.3), when validated, then the valid ones parse and each invalid one (unknown field,
  count below its bound, a value without unit, `transverse_kind: spiral`, `special_seismic: true`) is refused, the last
  two with `NOT_IMPLEMENTED` and their gap ids; and given a valid and an invalid fixture per kind of §4.2, then only
  the valid one validates. Tests: `tests/contract/test_column_design_kinds.py::test_request_models`,
  `::test_kind_fixtures`.

### 3.2 Calcs

- AC4. Given the golden cases of §4.4.1 (by names; by story and section; a frame vertical within `compare.length_mm`;
  one exactly at it; one beyond it; unknown names), when `harness.column_select` runs, then `columns`, `excluded` and
  `issues` equal the expected ones. Test: `tests/golden/column_design/test_golden.py::test_case[column-select-*]`.
- AC5. Given any permutation of the frames, sections or scope lists, when `harness.column_select` runs, then the output
  and its content hash are equal. Test: `tests/property/test_column_select.py::test_permutation_invariant`.
- AC6. Given the golden cases of §4.4.2 (compression and tension rows, one moment zero on a symmetric section with the
  sole nonzero magnitude in `Mu` and `Mu_other` = 0 (amendment B-596; OQ-Q98; was the old E3 fixed `Mu = |M3|`,
  `Mu_other = |M2|` mapping), both moments non-zero, a square section, a layout missing, a circular and an `other`
  section, the bar area copied from the layout answer as a literal `A_bar_mm2` (`column-demands-layout-bar-area`; never
  a basis reference), a square section with `n_bars_b ≠ n_bars_h`, the one-per-column
  `longitudinal_reinforcement_limits` item with `Ag_mm2` and `case: null`), when `harness.column_demands` runs, then the
  items per check, their converted values and units, `not_checked` and the trace equal the expected ones. Test:
  `tests/golden/column_design/test_golden.py::test_case[column-demands-*]`.
- AC7. Given forces whose `sign_convention` is not `host_local/1` (enforced by the `forces.member_end/1` kind at input
  validation), or a basis without a confirmed field of §4.7 A it reads, when `harness.column_demands` runs, then
  `ContractError` `INVALID_ARGUMENT` (for the basis check, `field` is that basis path, `basis.fields.<path>`) and
  nothing is stored (amendment B-578); given a rectangular section that is
  not symmetric (`b_mm ≠ h_mm`, or `b_mm == h_mm` with `n_bars_b ≠ n_bars_h`) and no axis declaration from the adapter
  (CW-G9), then no `axial_flexure_uniaxial` item is built for it
  (`not_checked` `AXES_UNDECLARED`) while its other two checks are. Tests:
  `tests/unit/calcs/test_column_demands.py::test_refusals`, `::test_axes_undeclared`.
- AC8. Given the golden cases of §4.4.3 (steel host-only, concrete code-only, a `PASS` and a `FAIL` at two ends, a
  `not_checked` column, a previous review with a newly failing, a newly passing and an appeared member), when
  `harness.column_review` runs, then the `members` snapshot (keyed by frame id, source and check id), column and member
  statuses, governing references and changes (with the same key) equal the expected ones, and no ratio in the output
  differs from the verdict it references (amendment B-577). Tests:
  `tests/golden/column_design/test_golden.py::test_case[column-review-*]`,
  `tests/property/test_column_review.py::test_ratios_are_referenced_not_computed`.
- AC9. Given the golden cases of §4.4.4 (one matching section; none; two; same size other material; a dimension
  exactly at `compare.length_mm`; circular), when `harness.column_section_match` runs, then `status` and `section` equal
  the expected ones; given a literal size instead of a `harness.section_size/1` reference, or a `size_b`, `size_h` or
  `size_d` reference whose pointer is not exactly `/size` (for example `#/required` or `#/increment`), then
  `INVALID_ARGUMENT` (amendment B-580). Tests: `tests/golden/column_design/test_golden.py::test_case[column-match-*]`,
  `tests/unit/calcs/test_column_section_match.py::test_size_must_be_rounding_result`,
  `tests/unit/calcs/test_column_section_match.py::test_size_pointer_must_be_size`,
  `tests/unit/calcs/test_port.py::test_ref_meta_preserves_pointer`.
- AC10. Given matches and accepted frame ids, when `harness.column_change_set` runs, then it holds one `frame_section`
  item per accepted frame with status `matched`, sorted by frame id, and each accepted frame without a match is an
  issue `NOT_IMPLEMENTED` with gap CW-G3 and no item. Test: `tests/unit/calcs/test_column_change_set.py::test_items_and_refusals`.
- AC11. Given the golden cases of §4.4.5 (no change; reuse of an existing type; one new type shared by two pairs of one
  family and section; a name clash; unmapped roles; circular; `other` shape; a non-square orientation-unverified issue with both rotations; one
  `preexisting` and one `changed_in_design` assignment), when
  `harness.revit_column_update` runs, then the plan equals the expected one and every length is a reference to an
  ETABS `model.sections/1` field, never a number; any permutation gives the same output. Tests:
  `tests/golden/column_design/test_golden.py::test_case[revit-update-*]`,
  `tests/property/test_revit_column_update.py::test_permutation_invariant`.
- AC12. Given the golden cases of §4.4.6 (all applied; a wrong type; a role value off by more than `compare.length_mm`;
  an unplanned type change; an element missing; a role not read), when `harness.revit_column_readback` runs, then
  status and issues equal the expected ones. Test: `tests/golden/column_design/test_golden.py::test_case[revit-readback-*]`.

### 3.3 Code checks and decisions

- AC13. Given the code-pack route (§4.5) and the three check ids, when the workflow calls `ctx.calc` with a reference
  to an item list of `harness.column_check_items/1`, then `structural_codes.evaluate_batch` runs in mode `trial`, the
  stored `verdicts.set/1` has one trace per item in item order and `draft: true`. With a real `harness.column_check_items/1`
  record and the three real ACI 318-14 checks, each `verdicts.set/1` has `parents` exactly `[items result, basis result]`
  (every check carries a basis `ratio_limit` reference; the two strength checks also carry `fc_MPa`, `fy_MPa` and
  `k_factor`); `batch` is a `RefInput` for every check; `ratio_limit` is a `RefInput` for every check; `fc_MPa`, `fy_MPa`
  and `k_factor` are `RefInput`s for the two strength checks; every other input is a `LiteralInput` equal to the stored
  value (amendment B-578; owner answer 2026-11-19). With either a bare `RefString` item input or a literal `fc_MPa` in a
  permissive stored-list fixture, the route returns `INVALID_ARGUMENT` and stores no verdict (amendment B-578).
  In run class `production`, the step is refused before any write (`CalcRefused`, CK-AC5); given a check id outside the route's allowlist (§4.5),
  then `ContractError` `NOT_FOUND` before any evaluation (calcs §6; amendment B-405, spec 0010 C4).
  Tests: `tests/unit/calcs/test_code_pack_route.py::test_batch_through_calcport`, `::test_ref_strings_refused`,
  `::test_literal_fc_refused`, `::test_production_refused`, `::test_only_listed_checks`.
- AC14. Given every state of the §4.8 tables, when the rules run, then the listed option or no decision (engineer)
  results (a `FAIL` or `NEEDS_ENGINEER` column with `proposal` `none` gets no decision and reaches the engineer), and the points and rules are in `decisions.lock.json`. Tests:
  `tests/unit/rules/test_column_design_rules.py::test_member_action_rules`, `::test_revit_rules`, `::test_lock`.

### 3.4 `column_design` (fake-host workflow)

- AC15. Given a fake model whose selected columns all pass, when the run reaches the engineer turn and the engineer
  accepts, then the journal holds steps 1 to 10 and 15 of WS §4.1 in order, no ETABS write, a promotion and a sign-off.
  Test: `tests/workflow/column_design/test_cycle.py::test_review_only_cycle`.
- AC16. Given one failing column and a proposal whose rounded size matches an existing model section, when the engineer
  revises, then one `frame_section` item is approved, written and read back `PASS`, the next cycle runs analysis and
  design, and the review lists the column as newly passing (fake configured to pass). Test:
  `tests/workflow/column_design/test_cycle.py::test_revise_applies_section`.
- AC17. Given a proposal with no matching model section, then nothing is written and the item shows gap CW-G3; given
  the engineer then adds the section by hand and chooses "edited by hand", then the next cycle's difference report shows
  it and the same proposal now matches. Test: `tests/workflow/column_design/test_cycle.py::test_missing_section_then_hand_edit`.
- AC18. Given columns with both moments non-zero, a slender column, a tension row, a circular, a steel and a concrete
  column, then the review shows `NEEDS_ENGINEER` with the code pack's gap ids (CK §6.2), `not_checked` reasons, and gap
  CW-G1 for the concrete host verdict; no verdict is produced by the workflow. Test:
  `tests/workflow/column_design/test_checks.py::test_gaps_reach_review`.
- AC19. Given several unresolved members in one cycle, then they reach the engineer in one batched screen
  (`decide_many`); given an engineer `change_section` for a member without a match, then the change set refuses it
  (AC10). Test: `tests/workflow/column_design/test_proposals.py::test_one_batched_screen`.
- AC20. Given a hand edit between cycles on a column with a proposal, then the difference report shows it, the change
  set check warns `CONFLICTS_WITH_ENGINEER_CHANGE` (EC §4.4.1 K6) and the approval preview carries it. Test:
  `tests/workflow/column_design/test_cycle.py::test_hand_edit_kept_and_flagged`.
- AC21. Given the journals of AC15 to AC20, when the value-source audit (EC AC25, `audit_value_sources`) and the
  verdict-source audit (§4.10) run, then every engineering argument of an ETABS write or a code check is a reference
  and every verdict in a review has `source` `host` or `code_pack` with a check id and, for `code_pack`, a clause.
  Test: `tests/workflow/column_design/test_audits.py::test_value_and_verdict_sources`.
- AC22. Given an accepted, promoted run, then `harness.column_design_record/1` holds the accepted revision identity,
  fingerprint and file hash, the changed frames (from and to section) and references to the selection and the last
  review. Test: `tests/workflow/column_design/test_cycle.py::test_design_record`.

### 3.5 `column_revit_update` (fake-host workflow)

- AC23. Given a mode other than `approve_each_write`, when the run starts, then `RunRefused` (`MODE_NOT_ALLOWED`
  **[added]**) before `run_started`; nothing is opened. Test: `tests/workflow/column_design/test_revit_update.py::test_mode_refused`.
- AC24. Given an ETABS model whose fingerprint differs from the design record's accepted fingerprint, then the run stops
  with `PRECONDITION_FAILED` (`etabs_revision`) before Revit is opened. Test:
  `tests/workflow/column_design/test_revit_update.py::test_etabs_changed_after_design`.
- AC25. Given a clean map, one pair needing a new type and one an existing type, when the engineer approves and answers
  Yes in each fake dialog, then the writes run in the order duplicate, set type parameters, change element type, each
  with its preview, the read-back is `PASS`, and the report states that the Revit document is unsaved. Test:
  `tests/workflow/column_design/test_revit_update.py::test_update_by_reference`.
- AC26. Given AC25's journal, then every length argument sent to Revit is a reference whose lineage ends at a
  `model.sections/1` field read from ETABS in this run. Test:
  `tests/workflow/column_design/test_revit_update.py::test_lengths_by_reference`.
- AC27. Given ambiguous, unmatched and conflicting columns, then the map decision goes to the engineer and, on
  "continue", only matched pairs are written. Test: `tests/workflow/column_design/test_revit_update.py::test_unmatched_never_written`.
- AC28. Given a declined dialog on one write, then that write is not applied and not retried; given a read-back
  `FAIL`, then the engineer chooses `accept` or `abandon` and no restore is attempted (RV §4.12). Test:
  `tests/workflow/column_design/test_revit_update.py::test_declined_and_readback_failure`.

### 3.6 Resumption and report

- AC29. Given the engine killed at every step of each workflow and resumed, then the final state equals an
  uninterrupted run and no write repeats. Tests: `tests/replay/column_design/test_resume.py::test_crash_matrix_design`,
  `::test_crash_matrix_revit`.
- AC30. Given each workflow's journal, when the report renders, then it has the columns and their verdict sources, the
  size chain (required, rounded, model section), the map, the Revit plan and read-back, the unsaved-document notice and
  the draft marks. Test: `tests/unit/report/test_column_design_report.py::test_sections`.

### 3.7 Amendments (§11 Q2 to Q4)

- AC31. Given a `WorkflowDef` with `allowed_modes` and a run in another mode, when the engine starts it, then
  `RunRefused` `MODE_NOT_ALLOWED` before `run_started`; given the edit-cycle module, then `read_state`,
  `apply_change_set`, `run_and_summarize` and `finish` are exported and `apply_change_set` accepts a change-set
  reference; given a `harness.generated_change_set/1` reference, then `harness.change_set_check` version 2 checks it
  like an answer (rules K1 to K7) and records the source; the edit-cycle suite passes unchanged. Tests:
  `tests/unit/test_engine_column_amendments.py::test_allowed_modes_refused`,
  `tests/unit/edit_cycle/test_exports.py::test_child_blocks_exported`,
  `tests/unit/calcs/test_change_set_check_v2.py::test_accepts_generated_set`.

## 4. Design

### 4.1 Modules

| Module | Content | Risk floor |
|---|---|---|
| `src/eng_harness/workflows/column_design/__init__.py` | both `WorkflowDef`s, `basis_fields`, input and output models | block code |
| `src/eng_harness/workflows/column_design/_requests.py` | the request models of §4.3 | block code |
| `src/eng_harness/workflows/column_design/_cycle.py` | `column_cycle_once`, `check_columns`, `propose_and_apply` | block code |
| `src/eng_harness/workflows/column_design/_revit.py` | the steps of `column_revit_update` | block code |
| `src/eng_harness/workflows/column_design/_points.py` | decision points and state models (§4.8) | block code |
| `src/eng_harness/rules/column_design.py` | the rules of §4.8 | R1 |
| `src/eng_harness/calcs/column_design/` | the calcs of §4.4 | R1 |
| `src/eng_harness/_calc/_code_packs.py` | the code-pack route of §4.5 | R1 |
| `src/eng_harness/kinds/column_design.py` | the kinds of §4.2 | R2 |
| `src/eng_harness/report/_column_design.py` | renderers and `audit_verdict_sources` | report |

### 4.2 Definitions, inputs, outputs, kinds

- `column_design`: input `ColumnDesignInput` (`model`: `harness.file_input/1` reference; `visible_host: bool`, default
  true); output `ColumnDesignOutput` (the EC output fields plus `record`: reference to
  `harness.column_design_record/1`).
- `column_revit_update`: input `ColumnRevitInput` (`etabs_model`, `revit_model`: `harness.file_input/1` references;
  `design_record`: reference to a `harness.column_design_record/1` result in this workspace); output
  `ColumnRevitOutput` (`plan`, `readback`: references; `written: int`; `revit_unsaved: true`; `signed: bool`).
- Kinds **[added]**: `harness.column_selection/1`, `harness.column_check_items/1`, `harness.column_review/1`,
  `harness.column_match/1`, `harness.generated_change_set/1` (the `ChangeSetDraft` shape of EC §4.3.1 plus `source`),
  `harness.revit_column_update/1`, `harness.revit_column_readback/1`, `harness.column_design_record/1`.

### 4.3 Engineer requests

Each is a data request (`ctx.ask`, answered with `resume --answers`), stored as `basis.engineer_input/1` (engine
AC61), bounded by `ctx.attempts`. A **value** is as EC §4.3.1: `{"source": "basis", "path": ...}` or
`{"source": "input", "value": ..., "unit": ...}`.

- `ColumnScopeRequest`: `frames` (names) or `select` (`stories`, `sections`: names or null; at least one);
  `combinations` (1 or more names of existing combinations); `special_seismic: bool` (true is refused with
  `NOT_IMPLEMENTED` CK Q10).
- `ColumnLayoutRequest`: per reinforced-concrete rectangular frame section in scope, as the engineer lists them: `transverse_kind` (`tied`; `spiral`
  refused, CK Q4), `n_bars_b`, `n_bars_h` (integers, at least 2: bars along each face of width `b` and depth `h`,
  corners included, as AF §3), `A_bar` (area value), `d_prime` (length value).
- `ColumnProposalRequest`: per frame id, `required`: `{b, h}` (length values) for a rectangular column or `{D}` for a
  circular one.

### 4.4 Calcs

All follow spec 0003 §4.2 to §4.5 (pure, traced, golden cases with sources, content hash, `draft` until the owner
approves them in `approvals.yaml`); runs are `--run-class trial` until then. None holds an engineering constant.

#### 4.4.1 `harness.column_select` v1

Input: `scope` (answer reference), `frames` (`model.frame_placements/1`), `sections` (`model.sections/1`), `basis`
(`compare.length_mm`). Method: L1 resolve `frames` names, or every frame whose story is in `stories` (when given) and whose
section is in `sections` (when given); unknown names are error issues (`UNKNOWN_FRAME`, `UNKNOWN_STORY`,
`UNKNOWN_SECTION`). L2 a frame is a column when the squared plan distance between its ends is at most
`compare.length_mm`² (exact `Fraction`, as 0003 §4.11 P2); otherwise `excluded` with `NOT_VERTICAL`. The contract `kind`
is not used: the CSI reader gives `other` (H-G5, C3). L3 per column: `frame_id`, `section`, `shape` (`rectangular`,
`circular`, `other` from `model.sections/1`), `material`, `story`, `length_mm` (distance between the ends, display
float). Output `harness.column_selection/1`; `status` `FAIL` on an error issue or an empty selection.

#### 4.4.2 `harness.column_demands` v1

Input: `selection`, `forces` (`forces.member_end/1`), `sections`, `layouts` (answer reference), `combinations` (from the
scope answer), `basis` (`materials.concrete_fc_MPa`, `materials.rebar_fy_MPa`,
`columns.effective_length_factor_ratio`). Method:

- E1 `sign_convention` must be `host_local/1`, enforced by the `forces.member_end/1` kind at input validation
  (`ContractError` `INVALID_ARGUMENT`, nothing stored; contract G-3; amendment B-578). A missing or unconfirmed §4.7 A
  basis field likewise gives `ContractError` `INVALID_ARGUMENT` (`field = basis.fields.<path>`), with nothing stored.
- E2 rows: every row of a selected column whose `case` is a selected combination, sorted by member, case, station.
  A selected column without a row for a selected combination is `not_checked` `FORCES_MISSING`.
- E3 `Pu_kN = −P_kN`: `host_local/1` reports axial tension positive (contract G-3, CSI convention; a C item for the
  owner and local test 3, §12). `Mu_kNm` and `Mu_other_kNm` are magnitudes of the moments about the axes parallel to
  `b` and to `h`. Which of `M2`, `M3` that is depends on how the adapter maps `b_mm` and `h_mm` to the local axes,
  which no spec states (CW-G9). Only for a section that is symmetric by geometry and layout (`b_mm == h_mm` and
  `n_bars_b == n_bars_h` — the existing condition of this rule; kept) is an axial-flexure item built. For that
  symmetric section: when exactly one of `|M2|` and `|M3|` is non-zero, that sole nonzero magnitude is `Mu` and
  `Mu_other` is 0 (amendment B-596; owner answer OQ-Q98, 2026-11-20); when both are non-zero, the item is still built
  and the check answers `NEEDS_ENGINEER` (AF G-1), as today. For any other rectangular section, a square one with
  unequal bar counts included, no axial-flexure item is built (`not_checked` `AXES_UNDECLARED`) until spec 0002
  declares the mapping.
- E4 `lu_mm = length_mm`: the distance between the frame's end joints, not less than the clear height of 6.2.3, so the
  slenderness applicability limit is tested on the safe side (C item, CW-G11). `k_factor` from the basis.
- E5 section: `b_mm`, `h_mm` from `model.sections/1`; `Ag_mm2 = b_mm·h_mm` (rectangular, a geometry identity);
  layout fields from the answer; `Ast_mm2` is the bar count of the layout times `A_bar` (the count of AF CS S1,
  `2·n_bars_b + 2·n_bars_h − 4`, a geometry identity); `fc_MPa`, `fy_MPa` from the basis.
- E6 `circular` and `other` shapes and sections without a layout are `not_checked` (`SHAPE_NOT_CHECKED`,
  `LAYOUT_MISSING`). The contract has no material type, so a rectangular section the engineer gives no layout for
  (for example a steel tube) is `LAYOUT_MISSING`; steel members have host verdicts only (CW-G5).

Output `harness.column_check_items/1`: per check id of §4.5 a list of `{subject: {kind: frame, id, station_mm, case},
inputs}` (input names and units of the clause specs' §3): for the two strength checks one item per E2 row; for
`aci318_14.10_6_1_1.longitudinal_reinforcement_limits` one item per selected column with inputs `Ag_mm2` and `Ast_mm2`,
no station and `case: null` (its clause spec §3: the limits do not depend on loads); `not_checked` (`frame_id`, `code`, `gap`), trace with E3 to
E5 as steps. The item list for each check is passed as one `batch` reference to `/items/<check id>` of this result,
and inside each item (amendment B-578):

- values the calc converts or copies (`Pu_kN`, `Mu_kNm`, `Mu_other_kNm`, `Ag_mm2`, `Ast_mm2`, `b_mm`, `h_mm`, `lu_mm`,
  `d_prime_mm`, `A_bar_mm2`, `n_bars_b`, `n_bars_h`, with `n_bars_b` and `n_bars_h` integers) are literal JSON values
  under the clause-spec names and units, each equal to an E3 to E5 trace step;
- `transverse_kind` is the literal `"tied"` (spirals are `NOT_IMPLEMENTED`, §6);
- `fc_MPa`, `fy_MPa`, `k_factor` and `ratio_limit` are `{"$ref": "res_<basis id>#/fields/<path>/value"}` references to
  the confirmed basis fields `materials.concrete_fc_MPa`, `materials.rebar_fy_MPa`,
  `columns.effective_length_factor_ratio` and `limits.ratio_limit_ratio` (the calc verifies presence and confirmation
  before emitting any reference). Every ACI 318-14 column check input model inherits `ratio_limit` from
  `CheckInputs` (`structural_codes/inputs.py`), so each of the three checks carries this fourth reference-object field
  beside `fc_MPa`, `fy_MPa` and `k_factor` for the two strength checks (owner answer 2026-11-19; amendment B-578; same
  basis path the footing workflow uses);
- a bare reference string (`RefString`) is never an input value; a calc cannot reference its own result, and under
  `require_refs` only `engineering_quantity` fields must be references (architecture [04](../../../../design/docs/architecture/04-tool-contract.md) §3.5).

#### 4.4.3 `harness.column_review` v1

Input: `selection`, `host` (`harness.host_design_verdicts/1`, the output of `harness.host_design_verdicts`), the three
code-check `verdicts.set/1` results bound to separate named top-level optional reference fields, one per check of §4.5 —
`max_axial_strength` (`aci318_14.22_4_2_1.max_axial_strength`), `axial_flexure_uniaxial`
(`aci318_14.22_4_1_1.axial_flexure_uniaxial`), and `longitudinal_reinforcement_limits`
(`aci318_14.10_6_1_1.longitudinal_reinforcement_limits`) — because the contract parameter pipeline resolves one
reference per top-level field and the `CalcPort` derives result IDs and parents from those fields (amendment B-577;
optional when §4.6 step 8 had no items for that check), `items` (for `not_checked`), optional `previous`
(`harness.column_review/1`), `basis` (`report.top_n`). Method: R1 only verdicts whose subject is a selected column
(`frame`, id) are read. R2 members and member status per 0003 §4.9 S5, keyed by `(frame_id, source, check_id)` (where
`source` is `host` or `code_pack`); a column's `status` is the worst of its members, and `NEEDS_ENGINEER` when it has
a `not_checked` entry or no verdict. R3 `governing` per column: the reference `<result>#/verdicts/<i>` of the verdict
first by 0003 S2 order; its ratio is copied with the reference, never computed. R4 `changes` compares the complete
`members` snapshot against `previous.members` by `(frame_id, source, check_id)` per 0003 S5's table (`top` is capped by
`report.top_n`, `governing` retains at most one verdict per frame, and `changes` retains only deltas, while reused
`SummaryChanges` omits `source`, so R4 requires every previous member keyed with `source`; keeping S5 status transitions
and ratios on both sides; amendment B-577). Output `harness.column_review/1`: `columns` (per column `frame_id`, `status`,
`host_status`, `code_status`, `governing`, `not_checked`, `gaps`), `failing`, `attention`, `top` (`report.top_n`),
`members` (complete snapshot of every member keyed by `frame_id`, `source`, `check_id` with `status` and `ratio`),
`changes` (column-specific change rows carrying the same `(frame_id, source, check_id)` key with S5 status transitions
and ratios on both sides), `complete`.

#### 4.4.4 `harness.column_section_match` v1

Input: `column` (a row reference into the selection), top-level `size_b` and `size_h` (rectangular) or `size_d`
(circular) — each a `harness.section_size/1` reference whose JSON pointer is exactly `/size` (not `#/required` or
`#/increment`; amendment B-580; named as separate top-level fields so the CalcPort resolves one reference per
dimension), `sections`, `basis` (`compare.length_mm`). Method: M1 candidates are frame sections with the column's
shape type and material whose every dimension differs from the rounded size by at most `compare.length_mm` (exact).
M2 one candidate is `matched` with its name; none is `no_section_in_model` (CW-G3, H-G1); several are `ambiguous`
with all names. A size reference whose parsed pointer is not `/size` is `INVALID_ARGUMENT` on that field; the calc
writes each validated size reference (pointer included) to the trace. Output `harness.column_match/1`.

`harness.column_change_set` v1: input `matches` (references) and `accepted` (frame ids whose decision is
`change_section`); output `harness.generated_change_set/1` with one `frame_section` item (`frames: [id]`, `section`)
per accepted, matched frame, sorted by frame id; others are issues `NOT_IMPLEMENTED` CW-G3. It holds names only.

#### 4.4.5 `harness.revit_column_update` v1

Input: `map` (`harness.frame_element_map/1`), `frames`, `sections` (this run's ETABS reads), `revit`
(`harness.revit_structure/1`, with role statuses, RV §4.8), `changed` (reference to the changed frames of the design
record, AC22), `basis` (`compare.length_mm`). Method:

- U1 targets per pair from the frame's ETABS section: `rectangular` sets roles `section_b` and `section_h`,
  `circular` sets `section_D`; `other` is `not_updatable` `SHAPE_NOT_SUPPORTED`. Each target is the reference
  `<sections result>#/frame_sections/<i>/shape/<field>`.
- U2 a role `unmapped` for the element's family gives `SECTION_ROLES_UNMAPPED`.
- U3 the element's current type with every role within `compare.length_mm` of its target is `no_change`.
- U4 otherwise a type of the same family with every role within `compare.length_mm` is `assign` to it; several are
  `TYPE_AMBIGUOUS`; none gives one `new_type` per (family, ETABS section name), named after the ETABS section,
  duplicated from the current type of the first pair by `unique_id`; a type of that name already in the family is
  `NAME_CONFLICT` (RV AC16). The new type's role sets carry the U1 references; its instances before the assignment
  are none (RV AC15 `expected_instances: []`).
- U5 both sides carry `rotation_deg` (`model.frame_placements/1` of ETABS and of Revit; RV §4.5 leaves an element
  with a null rotation out of that kind, so every paired element has one), but how the two conventions relate is
  unverified until local test 6 (CW-G7). A non-square rectangular target carries the info issue
  `ORIENTATION_UNVERIFIED` with references to both rotations, shown in the R6 preview; no rotation is compared or
  written. Without a mapped `rotation` role no Revit element enters `model.frame_placements/1`, so no column maps (all
  frames `unmatched_frames`) and nothing is written.
- U6 each assignment carries `origin`: `changed_in_design` when its frame is in `changed`, otherwise `preexisting`
  (Q10); a new type lists the origins of its pairs.

Output `harness.revit_column_update/1`: `new_types` (with the origins of their pairs), `assignments` (`unique_id`,
`element_id`, `from_type_id`, target type id or new type name, `origin`), `no_change`, `not_updatable`, `expected` (per element its type; per type its role
references), `complete`.

#### 4.4.6 `harness.revit_column_readback` v1

Input: `plan`, `before` (`harness.revit_structure/1`, `stale_ok`, 0003 §4.13), `after` (current), `basis`
(`compare.length_mm`). Method: B1 each planned element exists by `unique_id` (`ELEMENT_MISSING`) and has its planned type
(`TYPE_MISMATCH`); B2 each planned role value resolves and is within `compare.length_mm` (`VALUE_MISMATCH`); B3 no other
element of the read set changed type between `before` and `after` (`UNEXPECTED_TYPE_CHANGE`); B4 an unread role is
`not_read`. `status` `PASS` only without issues and with `after` at a later revision than `before`.

### 4.5 Code checks through the CalcPort

The CalcPort serves the code packs through one route (engine §4.8, calcs §4.12 item 4, amendment B-405; CF §1; C2
settled). [Spec 0010](0010-design-isolated-footing.md) §4.3 describes the same route from the footing side, and the two
descriptions are one route (spec 0010 C3). `_calc/_code_packs.py` (`CodePackRoute`, consulted by `HarnessCalcPort` for
an id that does not start with `harness.`) runs a check id only from a fixed allowlist that holds both workflows' ids.
B-393 (plan 0010 T2) shipped the route, including the three column allowlist entries
(`aci318_14.22_4_2_1.max_axial_strength`,
`aci318_14.22_4_1_1.axial_flexure_uniaxial`, `aci318_14.10_6_1_1.longitudinal_reinforcement_limits`) and the `batch`
argument. `describe` returns the check's `CheckMeta` as `CalcInfo` (`status` is the check's lifecycle state; `version`
is the check's `CheckMeta.version`, spec 0010 Q20, see Q13), and `run(check_id, {"batch": <reference to an item
list>})` resolves the list (the inline `items` argument of spec 0010 §4.3 is the other form of the same `run`), passes
each stored item unchanged as a `BatchItem` (references and literals as stored; under `require_refs` only
`engineering_quantity` fields must be references, architecture [04](../../../../design/docs/architecture/04-tool-contract.md) §3.5; amendment B-578), refuses before any evaluation a `withdrawn` check in both run classes (`CalcRefused`
`CALC_WITHDRAWN`) and, in run class `production`, a check that is not `approved` (`CalcRefused` `CALC_NOT_APPROVED`;
calcs §4.12 item 4; so the pack's `CheckNotUsable`, CF AC25, is never reached), calls
`structural_codes.evaluate_batch(check_id, items, mode=<run class>, registry, source=store,
policy=InputPolicy(require_refs=True))` and stores the `verdicts.set/1` payload with the provenance tool
`structural-codes/evaluate_batch`. A check id outside the allowlist or unknown to the registry returns
`ContractError` `NOT_FOUND` before any evaluation, as an unknown calc id (calcs §6), never an exception of `structural_codes` raised to the block
(spec 0010 C4, settled by B-405). Plan T6 adds test-only companion coverage for the shipped route through the
three column checks (AC13, amendment B-578).

### 4.6 Steps as ctx calls

`m` is the model handle, `B` the basis view, `k` the cycle index. Steps and checks of EC §4.5 that are reused keep their
engine checks.

| WS | Calls |
|---|---|
| 1 | Run start (invariants 5 and 8); `ctx.tool("csi_open_model", ...)` with `copy_on_open` (EC step 2) |
| 2 | `ctx.ask(ColumnScopeRequest)`, `ctx.ask(ColumnLayoutRequest)`, each in `ctx.attempts(B.count("attempts.column_inputs"))` |
| — | `async for c in ctx.attempts(B.count("attempts.cycles"))`: `ctx.block(column_cycle_once, ...)` |
| 3 | `ctx.block(read_state, ...)` (EC steps 3, 4) |
| 4 | `ctx.calc("harness.column_select", ...)`; `FAIL` re-asks the scope |
| 5, 6 | `ctx.block(run_and_summarize, ...)` (EC steps 11 to 14, including D-3; the engine saves first, invariant 7); then `ctx.tool("csi_results_frame_forces", {"model": m, ...})` for the selected columns and combinations (argument model of spec 0002) |
| 7, 8 | `ctx.calc("harness.host_design_verdicts", ...)` (EC); `ctx.calc("harness.column_demands", ...)`; per check id of §4.5 with items, `ctx.calc(<check id>, {"batch": <ref>})` |
| 9 | `ctx.calc("harness.column_review", {"selection": ..., "host": ..., "max_axial_strength": ..., "axial_flexure_uniaxial": ..., "longitudinal_reinforcement_limits": ..., "items": ..., "previous": <cycle k−1>, "basis": ...})` (each code-check argument passed when step 8 produced a result for that check, §4.4.3; amendment B-577) |
| 10 | `ctx.decide("column_design.engineer_turn", ...)` (engineer, always) |
| 11 | `ctx.ask(ColumnProposalRequest)` |
| 12 | per proposed dimension `ctx.calc("harness.section_round", {"required": <answer ref>, "basis": ...})`; per column `ctx.calc("harness.column_section_match", ...)` |
| 13 | `ctx.decide_many("column_design.member_action", ...)` (§4.8) |
| 14 | `ctx.calc("harness.column_change_set", ...)`; `ctx.block(apply_change_set, {"change_set": <ref>, ...})` (EC steps 5 check, 6 to 10, D-2, D-5); next cycle |
| 15 | `ctx.block(finish, ...)` (EC steps 16, 17) after storing `harness.column_design_record/1` from the accepted cycle |

`column_revit_update`:

| WS | Calls |
|---|---|
| R1 | Run start: invariants 5 and 8 for both servers; `allowed_modes` check (AC23) |
| R2 | `ctx.tool("csi_open_model", ...)` (copy), `ctx.tool("csi_read_model_state", ...)`, `ctx.calc("harness.model_fingerprint", ...)`; unequal to `design_record.fingerprint` → `PRECONDITION_FAILED` (`etabs_revision`) |
| R3 | `ctx.tool("revit_open_model", ...)` (the adapter's `working_copy`, RV AC23); the Revit state reader (RV §4.9) |
| R4 | `ctx.calc("harness.frame_element_map", {"frames": <selected columns of this read>, ...})`; `ctx.decide("column_revit.map_result", ...)` |
| R5 | `ctx.calc("harness.revit_column_update", {"changed": <design record changed frames ref>, ...})` |
| R6 | `ctx.approve(..., Preview(items=<map summary, one item per new type, role set and assignment, each with its origin and issues>, models=[etabs, revit]), kind=CHANGE_SET)` |
| R7 | per accepted item in the order new types, role sets, assignments: `ctx.tool("revit_duplicate_family_type" | "revit_set_type_parameter_values" | "revit_change_element_type", args, under=approval, item=<id>)`, lengths as references (engine invariant 2); `approve_each_write` previews and the Revit dialog follow |
| R8 | Revit state read; `ctx.calc("harness.revit_column_readback", ...)`; `ctx.decide("column_revit.readback_result", ...)` |
| R9 | `ctx.approve(..., kind=SIGN_OFF)`; no promotion (RV R-G1, R-G2) |

The selected columns of R4 are the frames of the design record's selection, read again in R2 (same fingerprint, so the
same frames).

### 4.7 Design basis fields

No value is shipped (spec 0004 Q8). Every field is required and confirmed on the page.

Table A, `column_design`: the EC §4.8 fields the reused blocks and calcs declare (`compare.*`,
`checks.readback_relative_tolerance_ratio`, `report.top_n`, `limits.ratio_limit_ratio`, `limits.drift_ratio`, `bounds.*`,
`design.run`, `attempts.cycles`, `attempts.change_set`, `attempts.approval_void`), plus:

| Path | Kind | Unit | Used by | Source |
|---|---|---|---|---|
| `materials.concrete_fc_MPa` | quantity | `MPa` | column demands | project basis (13 §2 materials); the clause specs' name with the unit suffix (C1) |
| `materials.rebar_fy_MPa` | quantity | `MPa` | column demands | same |
| `columns.effective_length_factor_ratio` | quantity | `1` | column demands | engineer, per project (CK Q5) |
| `modeling.section_increment_mm`, `modeling.section_rounding` | quantity, choice | `mm`, `up` | `harness.section_round` | 0003 §4.4 |
| `attempts.column_inputs` | count | — | scope, layout and proposal requests | engineer |

Table B, `column_revit_update`: `compare.length_mm`, `mapping.offset_x_mm`, `mapping.offset_y_mm`,
`mapping.offset_z_mm` (RV §4.11), `checks.readback_relative_tolerance_ratio` (RV §4.8), `attempts.approval_void`.

### 4.8 Decision points and rules

Built with `decision_point` and `rule` (spec 0005 §4.2, §4.4), R1 and `draft`; policy `require_engineer=True` after the
rules, `model=False`, `llm=False` (Q8). States hold statuses, booleans and labels only.

| Point | Options | State | Rules, in order |
|---|---|---|---|
| `column_design.member_action` (per column, `decide_many`) | `keep`, `change_section`, `refer_to_engineer` | `status`, `host_status`, `code_status`, `has_not_checked`, `proposal` (`none`, `matched`, `no_section_in_model`, `ambiguous`), refs | `cm.no_proposal`: `status` `PASS` and `proposal` `none` → `keep`; `cm.fail_matched`: `status` `FAIL` and `proposal` `matched` → `change_section` |
| `column_design.engineer_turn` | `accept`, `revise`, `hand_edit` | review and read-back statuses, counts as labels, refs | none (engineer, always) |
| `column_revit.map_result` | `continue_matched`, `stop` | `has_ambiguous`, `has_unmatched_frames`, `has_conflicts`, `complete` | `map.clean`: all false and `complete` → `continue_matched` |
| `column_revit.readback_result` | `accept`, `abandon` | `status`, issue codes as labels | `rr.pass`: `PASS` → `accept` |

EC points `edit_cycle_readback_result` and `edit_cycle_analysis_messages` (spec 0007 §4.6, amendment B-417) run inside the reused blocks. `hand_edit`
starts the next cycle with no change set (EC §4.7). Unmatched Revit elements are normal (the Revit model holds columns
outside the selection) and are not in the map rule.

### 4.9 Approvals and permission modes

`column_design` follows EC §4.7 in every mode; `decide_many` adds at most one batched screen per cycle. The Revit run
is allowed only in `approve_each_write` **[added]** (`work_on_copy` fails at the first engine save, RV §4.12;
`autonomous_logged` would write without the engine's preview while a person still has to answer Revit's dialog, RV
Q1): every Revit write gets the engine preview, then the attended Revit dialog. Sign-off is always asked; there is no
Revit promotion.

### 4.10 Mapping and references

ETABS frames and Revit elements are paired only by `harness.frame_element_map` (RV §4.11: geometry with the basis
offset and `compare.length_mm`, links as hints, the engineer approves the map with the change set at R6). Every Revit
length is a reference to this run's ETABS `model.sections/1` field (U1), so a copying error cannot happen
(ADR-0005); the map and the plan become stale when either model changes (`REF_STALE`). `audit_verdict_sources`
(report) checks AC21: every verdict a review references has a source, a check id and, for `code_pack`, a clause.

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `model`, `etabs_model`, `revit_model` | `harness.file_input/1` reference | — | `.EDB`, `.rvt` (non-workshared) | yes | engineer (`--input`) |
| `design_record` | reference | — | a `harness.column_design_record/1` | yes | an earlier `column_design` run |
| Layout and proposal values | basis path or number with unit | length, area | contract kind bounds; integers ≥ 2 for bar counts | yes | design basis or engineer input |
| Names in requests | `str` | — | 1 to 200 characters, must exist | no | engineer; model state |

## 6. Errors

| Condition | Code | Fields |
|---|---|---|
| Invalid request answer | `INVALID_ARGUMENT` (asked again) | `field` |
| Spiral, special seismic | `NOT_IMPLEMENTED` with gap | field |
| Selection empty or unknown names | `harness.column_selection/1` `FAIL`, scope asked again | issues |
| Forces not `host_local/1` (`forces.member_end/1`), basis field missing or unconfirmed (amendment B-578) | `ContractError` `INVALID_ARGUMENT` | field (`basis.fields.<path>` for basis) |
| Production run with draft checks or calcs | `CalcRefused` (0003 §4.12) | calc id |
| Check id outside the §4.5 allowlist, or unknown to the registry | `NOT_FOUND` (0003 §6; B-405) | `check_id` |
| Mode not allowed (Revit run) | `RunRefused` `MODE_NOT_ALLOWED` **[added]** | mode |
| ETABS changed since the design run | `PRECONDITION_FAILED` (`etabs_revision`) | fingerprints |
| Revit gaps (save, restore) | `NotImplementedGap` (RV AC24) | gap id |

Errors of the engine, adapters, calcs and code pack pass through unchanged.

## 7. Non-goals

- SAP2000 as the frame model (Q9); IDEA StatiCa and SAFE.
- Defining ETABS sections, materials or reinforcement; reducing passing sections; automatic sizing (a required size
  is an engineer input, Q6).
- Checks beyond CK §1: biaxial bending, slenderness effects, tension, spirals, special seismic columns, transverse
  reinforcement, steel code checks.
- Revit: steel types, rebar, materials, geometry, saving or closing, workshared models, writing the ETABS link (RV Q5).
- Any engineering value in workflow, rule or calc code.

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A wrong demand reaches a check (sign, axis, station) | R1 | E1 refusal, E3 symmetric-section sole-nonzero-in-`Mu` rule (B-596 / OQ-Q98), golden cases, C items, local test 3 |
| A draft check is mistaken for an approved one | R1 | Trial run class, `draft: true`, DRAFT SOURCES mark, production refusal (AC13) |
| A section change hits a frame the engineer edited | R1 | EC difference report, K6 warning, approval binding (AC20) |
| Revit gets a size from a stale ETABS state | R1 | Fingerprint gate (AC24), references and `REF_STALE` (§4.10) |
| A Revit column is paired or typed wrongly | R1 | Exact map, no write for ambiguous or conflicting pairs, engineer approval, plan read-back (AC12, AC27) |
| Orientation of non-square columns differs between models | R1 | `ORIENTATION_UNVERIFIED` with both rotations on each item, local test 6; the engineer sees it at R6 |
| Most real columns return `NEEDS_ENGINEER` (biaxial moments) | R2 | Stated in the report; first follow-up CK Q3 |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1, AC7, AC9 (unit part), AC10, AC13, AC14, AC30, AC31 | Unit | `tests/unit/column_design/`, `tests/unit/calcs/`, `tests/unit/rules/`, `tests/unit/report/` |
| AC2 | Unit (source rules) | `tests/rules/` |
| AC3 | Contract | `tests/contract/` |
| AC4, AC6, AC8, AC9, AC11, AC12 | Golden | `tests/golden/column_design/`, data in `tests/data/golden/column_design/` |
| AC5, AC8, AC11 | Property | `tests/property/` |
| AC15 to AC28 | Fake-host workflow | `tests/workflow/column_design/` |
| AC29 | Replay | `tests/replay/column_design/` |

No host program and no network. Coverage floors 85% line and 75% branch; mutation score at least 80% on
`rules/column_design.py`, `calcs/column_design/` and `_calc/_code_packs.py`.

## 10. Version impact

Minor within `eng-harness` 0.1.0. New kinds, calcs, points and rules start at version 1 with lock entries; the
EC and engine amendments of §11 (Q3, Q4) are additive.

## 11. Open questions, conflicts and gaps

| Id | Question, conflict or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | Two runs (ETABS, then Revit) instead of one, because one run has one permission mode and Revit needs `approve_each_write` | Owner | Accept; revisit when Sasaah offers save and close for Revit (RV Q2) |
| Q2 | `WorkflowDef.allowed_modes` and `RunRefused MODE_NOT_ALLOWED` (engine amendment) | Owner | Accept; carried by plan T10 |
| Q3 | EC child blocks reused across workflows: EC exports `read_state`, `apply_change_set`, `run_and_summarize`, `finish`, and `apply_change_set` takes a change-set reference | Owner | Amend spec 0007 §4.1, §4.5 (additive), plan T10 |
| Q4 | `harness.change_set_check` takes a reference to the answer field only; here the set is `harness.generated_change_set/1` | Owner | Accept either kind (calc version 2); the approval preview names the source |
| Q5 | `ColumnLayoutRequest` per section: the reinforcement is entered, not read (CW-G2) | Owner | Accept for v1; ask Sasaah for a typed read of concrete frame-section reinforcement |
| Q6 | Required size is an engineer input; no sizing calc exists | Owner | Accept for v1; a sizing calc needs its own spec with sources |
| Q7 | Effective length factor as one per-project basis field (CK Q5) | Owner | Accept; per-column factors later if needed |
| Q8 | Decision tiers: rules and engineer only (no Jev or language model) for `member_action` | Owner | Accept for v1; shadow mode after labeled examples exist (spec 0009) |
| Q9 | SAP2000 as the frame model | Owner | Not in v1: concrete column results (SP-3) and design orientation (SP-5) are missing |
| Q10 | Update in Revit every matched pair whose size differs (including differences older than this design), or only the columns changed in this design | Owner | Every differing pair, each item marked `preexisting` or `changed_in_design` in the preview so the engineer can reject single items |
| Q11 | A column-review benchmark like B-1 | Owner | The owner picks two or three past projects; CA8 is measured locally |
| Q12 | `eng-harness` depending on the workspace packages `structural-codes` and `aci318-14` (§4.5): does an internal dependency need a package ADR (rule A10)? | Owner | Yes, one short package ADR, since the split into repositories (ADR-0028) turns it into a real dependency. The lead owns the ADR as a separate documents follow-up (plan §3, amendment B-578; lead decision D-19). |
| Q13 | **[added]** A code-pack check's `CalcInfo.version` (§4.5): `CalcInfo.version` is an integer of at least 1 and a merged check has only its pack's string version | Owner, lead | Decided as spec 0010 Q20 (draft, B-442; owner queue): `CalcInfo.version` is the check's `CheckMeta.version` (structural-codes core plan T15) |
| Q14 | **[added]** Whether the ACI 318-14 column demand fields (`MaxAxialInputs.Pu_kN`, `AxialFlexureInputs.Pu_kN`, `Mu_kNm`, `Mu_other_kNm`) should be `ref_capable` and `engineering_quantity` per CF §4.3 (`MaxAxialInputs.Pu_kN` and `AxialFlexureInputs.Mu_kNm` have neither flag; `AxialFlexureInputs.Pu_kN` and `Mu_other_kNm` have `ref_capable` only); non-blocking for v1 (amendment B-578) | Owner | v1 goes ahead with literal demands inside the referenced `harness.column_check_items/1` record; making them `ref_capable` and `engineering_quantity` later requires a structural-codes plan 0004 amendment paired with a follow-up code-pack route task (the kind stays unchanged) |
| C1 | Clause specs name `materials.concrete_fc` and `materials.rebar_fy`; spec 0004 AC21 requires a quantity field's unit to match its path suffix, and spec 0004 §4.2 shows paths such as `materials.concrete.<grade>.fc_MPa` (blocked by its Q1) | Owner | Done by amendment B-484 (owner decision OQ-Q44): Table A names `materials.concrete_fc_MPa` and `materials.rebar_fy_MPa` |
| C2 | CF §1 and engine §4.8 say code packs run through the CalcPort, but no merged harness spec defines that route | Owner | Settled by amendment B-405 (draft; the owner approves): engine §4.8 and calcs §4.12 item 4 name the one route; §4.5 here and spec 0010 §4.3 describe it; an id outside the allowlist is `NOT_FOUND` (spec 0010 C3, C4) |
| C3 | CK Q1 says B-083 passes "frames of kind `column`", but the CSI reader gives `kind: other` (spec 0002 H-G5) | Owner | Columns are the `harness.column_select` result (§4.4.1); amend CK Q1's text |
| C4 | 19 §1 names one workflow; this spec has two runs (Q1) | Owner | As Q1 |
| CW-G1 | `csi_design_results` returns concrete design for beams only (S-12 §1 step 13; EC-G2): no host verdict for concrete columns | Owner | Code-pack checks only; Sasaah typed column result tool |
| CW-G2 | No allowlisted read of concrete section reinforcement | Owner | Q5 |
| CW-G3 | A rounded size with no existing model section cannot be defined (H-G1) | Owner | Refused; the engineer defines it in ETABS and continues with "edited by hand" |
| CW-G4 | Biaxial bending, slenderness effects, tension, non-unique root (CK §6.2) | Owner | `NEEDS_ENGINEER`; CK Q3 first |
| CW-G5 | No steel column code check; steel Revit types not mapped | Owner | Host steel verdicts only; Revit steel later |
| CW-G6 | Revit document left unsaved; no promotion (RV R-G1, R-G2) | Owner | Engineer saves; project-lane save and close tools |
| CW-G7 | Both models give `rotation_deg`, but how the ETABS and Revit conventions relate is unverified, and the Revit rotation comes from a role confirmed only locally (RV R-G15, L6); without that role no Revit column maps | Owner | Info issue with both rotations per non-square item; local test 6 |
| CW-G8 | Spirals and special seismic columns (CK Q4, Q10) | Owner | Refused in the requests |
| CW-G9 | Which local axis `b_mm` and `h_mm` of `model.sections/1` lie along is not stated by spec 0002 | Owner | Spec 0002 amendment after local test 3; until then axial-flexure items for square sections only |
| CW-G10 | Sign of `P` in `host_local/1` (contract G-3) | Owner | E3 as written; confirm in local test 3 |
| CW-G11 | `lu` taken as the frame length (E4) | Owner | C item for the C3 verifier; keep until a clear-height read exists |
| CW-G12 | All calcs, rules and the three code checks ship `draft` | Owner | Review and approve after local tests |

## 12. Needs local test

Listed in `docs/local-testing.md` by the plan, on copies of an owner project: (1) a full `column_design` run on ETABS
with steel and concrete columns, including the reply of `csi_results_frame_forces` for the selected combinations and
of `csi_design_results` for columns (CW-G1); (2) a proposal that matches an existing section, applied and read back;
(3) the sign of `P` and the local axes of `M2`, `M3` against `b_mm`, `h_mm` on a non-square column (CW-G9, CW-G10);
(4) a hand edit between cycles; (5) a `column_revit_update` run in an attended Revit session with the owner's column
families (role map, dialogs, new types, assignments, read-back), RV §12 L3, L6, L8, L12, L14; (6) orientation of
non-square columns in both models (CW-G7); (7) a process kill during the Revit writes; (8) the column-review benchmark
(Q11, CA8).
