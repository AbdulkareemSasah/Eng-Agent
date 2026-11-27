---
id: spec-0010-design-isolated-footing
issue: "B-075"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1]
---

# Spec 0010: eng-harness block `design_isolated_footing` and workflow `isolated_footing_design`

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-04

This spec builds the workflow of the [workflow spec](../workflows/isolated-footing-design.md) ("WS §n"): the block
`design_isolated_footing` of [11](../../../../design/docs/architecture/11-harness-engine.md) §2 ("11 §n") and the
decision of [12](../../../../design/docs/architecture/12-decision-layer.md) §2, on the basis of
[13](../../../../design/docs/architecture/13-templates-and-design-basis.md), with the checks of
[10](../../../../design/docs/architecture/10-structural-codes.md) §7 and §9. It uses, and does not repeat: engine
[spec 0001](0001-engine.md) ("engine §n"), adapters [0002](0002-servers-and-adapters.md), calcs [0003](0003-calcs.md)
("calcs §n"), basis [0004](0004-templates-and-basis.md), decisions [0005](0005-decisions.md) ("decisions §n"), command
line, page and report [0006](0006-cli-progress-pages-report.md), the edit cycle [0007](0007-model-edit-cycle.md) (its
engine amendments and report helpers), SAFE [0008](0008-safe-adapter.md) ("SAFE §n"), providers
[0009](0009-providers.md), the contract [eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md)
("contract §n"), the code-pack core [structural-codes spec 0001](../../../structural-codes/docs/specs/0001-core-framework.md)
("CF §n"), the ACI 318-14 footing checks [plan 0002](../../../structural-codes/docs/plans/0002-aci318-14-footing-checks.md)
("ACI plan §n", clause specs "BP", "OS", "PS", "FL", "MR", "DL") and the SBC 304-2018 overlay
[spec 0003](../../../structural-codes/docs/specs/0003-sbc304-2018-footing-overlay.md) ("SBC §n"). Evidence of the
owner's practice is a read-only reading of the Sasaah footing tool and sessions (WS §2). Items marked **[added]** are
not in the architecture and are listed in §11.

**Amendment B-568.** By the owner answer of 2026-11-18 (OQ-Q60), rule L1 of §4.4.3 takes the ceiling: `WIDTH_TOO_SMALL`
applies when the span between the outer bar centres is zero or less, and for each positive span the bar count is the
smallest count whose actual spacing is at most the input `s`, which plan sizing initialises from
`reinforcement.max_spacing_mm` (§4.4.3 L1, AC8). The same amendment records the two points of OQ-Q63: a depth with no
room for both bottom layers is refused with `OUT_OF_RANGE`, field `dims` (§4.4.3 L3, §6), and the numbers of a
`WIDTH_TOO_SMALL` row are informative only (§4.4.3 L1, §4.6). No engineering number is added (Q21).

**Amendment B-597.** By the owner answer of 2026-11-20 (OQ-Q93, option (b)), the block passes the open footings only:
each round the layout, the check batches, the status and the resize read a record that holds only the footings still
open; a closed footing keeps its last result aside; no merged calc changes (§4.6, AC34, Q22). How block code stores
that record and prepares the schedule inputs is decided by B-613 (Q23 to Q28).

## 1. Problem

The footing workflow is the second workflow (10 §9, phase 2 of
[19](../../../../design/docs/architecture/19-roadmap-and-spikes.md) §1). The checks exist as specs; what is missing is
the part only the workflow knows: where each check input comes from, how the first size is found, how a failure becomes
a new size without a guessed number, how the loop stays bounded, what the engineer sees, and what reaches SAFE. Today
this lives in a tool that embeds its own load factors, ratios and spacing limits and writes SAFE through table imports
(WS §2, Q9). The harness version must take every value from the basis, a reaction, a cited calc or the engineer, and
reach hosts only through allowlisted tools.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| Specs 0001 to 0009 | Engine, adapters (ETABS reactions, SAFE loads and results), calcs, basis, decisions with shadow tiers, page, report, edit-cycle helpers | Used; this spec adds a workflow, a block, eight calcs, one decision point with rules, kinds, and the code-pack route of §4.3 |
| `structural_codes.evaluate_batch`, `notes.render_html` (CF §4.10, §4.12), ACI and SBC packs | Pure batch evaluation to `verdicts.set/1`; calculation notes; `check_id_for` for SBC ids (SBC Q1) | Used through the CalcPort (§4.3); nothing copied (A12) |
| `harness.section_round` (calcs §4.10) | Rounds up to the single `modeling.section_increment_mm` | Not used: plan and depth have their own increments and bounds (§4.4.2, §4.4.4) |
| Sasaah footing tool (`FootingSizer`, `FootingGrouper`, SAFE phase) | Sizing, grouping, SAFE build with table writes; embedded values (load factors, subgrade ratio, spacing cap, equilibrium tolerance); ACI 318-19 | Not adopted or called (SAFE Q4, Q9). Its step order is the evidence for WS §2 |
| `audit_value_sources`, `count_prompts` (spec 0007 §4.9, plan 0007 T10) | Journal audits | Reused for F2 and F4 |

Runtime dependencies added: the workspace packages `structural-codes-core`, `structural-codes-aci318-14` and
`structural-codes-sbc304-2018` (allowed from phase 2 by [03](../../../../design/docs/architecture/03-repositories.md)
§2; no third-party package, Q11).

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Fake-host workflow test" runs the real engine, the real CSI adapter
and the real code packs against the synthetic CSI fake server process in ETABS mode (and SAFE mode for §3.7; spec 0002
§4.8.3, SAFE §3, lead decision D-5), with a real journal and store and scripted page answers (spec 0006 fakes). Golden
data lives under `tests/data/golden/footing/`; each case names the section of this spec that defines its method, and
values are synthetic and say so. Synthetic basis templates follow spec 0004 §4.8.

### 3.1 Definition and code rules

- AC1. Given the workflow module, then `isolated_footing_design` is a `WorkflowDef` (version 1) whose `basis_fields`
  are exactly §4.7, whose `min_server_builds` names the CSI adapter's pinned build, with `copy_on_open = True` (spec
  0007 AC33) and an empty `always_ask`; `design_isolated_footing` (version 1) and `footing_safe_cross_check` (version 1)
  are blocks; all three are in `blocks.lock.json`. Test: `tests/unit/footing/test_definition.py::test_workflow_and_blocks`.
- AC2. Given the workflow, block, point and rule modules, then they follow engine §4.1.2 and §4.3.4 (imports, no numeric
  literal beyond integer indexes and `len` comparisons, no `while`, no I/O). Test:
  `tests/rules/test_footing_modules.py::test_modules_follow_block_rules`.

### 3.2 Code-pack route (§4.3)

- AC3. Given a check id of a registered pack and `items` of references, when `ctx.calc` runs it, then the CalcPort calls
  `evaluate_batch` with the store as `source` and `require_refs`, stores the `verdicts.set/1` payload with `draft` from
  the check state, provenance `tool: "structural-codes"` (the spelling of spec 0013 §4.5), the pack version and the check's `content_sha256`, and returns
  a summary of counts only. Test: `tests/unit/calcs/test_code_pack_route.py::test_batch_stored_as_verdict_set`.
- AC4. Given a draft check, then a `trial` run evaluates it and a `production` run refuses it with `CalcRefused`
  (calcs §4.12, CF AC25); given an unknown check id or one outside the route's allowlist (§4.3), then `ContractError` `NOT_FOUND` before any
  evaluation (as calcs AC13 and §6 for an unknown calc id; spec 0013 AC13 expects the same since B-405, C4); given a literal where a
  reference is required, then `INVALID_ARGUMENT`. Tests: `::test_production_refuses_draft`, `::test_unknown_id`,
  `::test_literal_refused`.
- AC5. Given `design.code_pack = sbc304_2018`, when the workflow runs, then every check id is resolved with
  `check_id_for`, every verdict is `NEEDS_ENGINEER` with its SBC gap, every footing is closed after round 0 with status
  `NEEDS_ENGINEER` and its initial size, and no decision is requested. Test:
  `tests/workflow/footing/test_code_packs.py::test_sbc_all_need_engineer`.

### 3.3 Calcs (§4.4)

- AC6. `harness.footing_subjects`: given synthetic placements, sections, points and reactions, then each column whose
  lower joint has reaction rows becomes a subject with `cx_mm`, `cy_mm` mapped through its rotation (within
  `compare.angle_deg` of 0, 90, 180 or 270 degrees), and every other case is excluded with its reason
  (`NO_COLUMN_AT_JOINT`, `SECTION_NOT_RECTANGULAR`, `COLUMN_ROTATED`, `TWO_COLUMNS_AT_JOINT`). Test:
  `tests/golden/footing/test_subjects.py::test_golden_cases`.
- AC7. `harness.footing_plan_size`: golden cases of §4.4.2 (between and on multiples, the minimum plan governing, the
  maximum reached, uplift, overburden above the allowable, net allowable, no service load with the size of P6, a
  maximum plan below the increment refused `OUT_OF_RANGE` (amendment B-567), shape `equal_projection` as
  `NotImplementedGap` FG-1); and properties: the plan area is at least `A_req`, one increment less is below it unless the
  minimum governs, and a larger load never gives a smaller plan. Tests:
  `tests/golden/footing/test_plan_size.py::test_golden_cases`, `tests/property/test_footing_plan_size.py::test_minimal_and_monotone`.
- AC8. `harness.footing_layout`: golden cases of §4.4.3 for both bottom layers and both reaction points; a span
  between the outer bar centres of zero or less gives `NEEDS_ENGINEER` (`WIDTH_TOO_SMALL`), and a depth with no room
  for both layers gives `OUT_OF_RANGE`, field `dims` (L1, L3; amendment B-568); properties: for each valid layout the
  actual spacing is at most `s`, and either `n = 2` or `span/(n − 2) > s`, and `As` grows with the bar count. Tests:
  `tests/golden/footing/test_layout.py::test_golden_cases`,
  `tests/property/test_footing_layout.py::test_spacing_bound`.
- AC9. `harness.footing_resize`: each action of §4.4.4 gives the next size; a step past a bound leaves the size
  unchanged with `LIMIT_REACHED`; `engineer_set` takes the single plan size `L`, `h` and `s` as engineer-input
  references (one triple per call, `engineer_plan`, `engineer_depth`, `engineer_spacing`), sets `Lx = Ly = L`, and
  flags values outside the basis bounds of §4.4.4, each side (`OUTSIDE_BASIS_BOUNDS`), and a plan that is
  not a multiple of `plan_increment_mm` (`OFF_INCREMENT`); `enlarge_plan` from a plan that is not a multiple gives the
  smallest multiple above it (golden cases: an engineer plan between multiples, then enlarged). Test:
  `tests/golden/footing/test_resize.py::test_golden_cases`.
- AC10. `harness.footing_status`: golden cases of §4.4.5 for the family status order, the closure and the decision
  state, including a mix of `FAIL` and `NEEDS_ENGINEER`. Test: `tests/golden/footing/test_status.py::test_golden_cases`.
- AC11. `harness.footing_schedule`: golden cases of §4.4.6 (overlap, corner distance below and at the clear distance,
  no conflict) and the assembled schedule. Test: `tests/golden/footing/test_schedule.py::test_golden_cases`.
- AC12. Given the calc registry, then each calc of §4.4 has a method source naming its section here, verification
  `draft`, a verification record under `docs/verification/calcs/`, a lock entry, and only `Cited` constants. Test:
  `tests/unit/footing/test_calcs_registered.py::test_metadata_and_constants`.
- AC35. Given two stored records of the calc's declared kind, each copy calc returns that kind with the requested
  rows unchanged and sorted by id. An overlapping id uses the extra row. A missing id is refused with
  `INVALID_ARGUMENT`, and a reference of the wrong kind is refused (§4.4.7). Tests:
  `tests/golden/footing/test_rows.py::test_golden_cases`, `tests/unit/footing/test_rows.py`,
  `tests/property/test_footing_rows.py::test_copy_preserves_rows`.

### 3.4 Decision point and rules (§4.5)

- AC13. Given `footing_fix_strategy`, then it is version 1 with the options of §4.5, its state holds only statuses,
  booleans and labels, it passes the redaction check (decisions §4.10) and is in `decisions.lock.json`. Test:
  `tests/unit/footing/test_point.py::test_point_definition`.
- AC14. Given each rule of §4.5, then it picks its option on its typical state, returns `None` on each boundary state
  (one more failing family, the bound reached), and the rules run in the order given. Test:
  `tests/rules/test_footing_rules.py::test_typical_and_boundary` (parametrized), `::test_order`.
- AC15. Given failing footings that no rule matches and a fake decision provider (the fakes of spec 0005, plan 0005 T5) that
  suggests an option, when a round decides, then the engineer's choice is applied, the suggestion is recorded as a shadow
  suggestion, and without a provider the engineer decides alone. Test:
  `tests/workflow/footing/test_decisions.py::test_shadow_suggestion_not_applied`, `::test_no_provider`.
- AC16. Given three footings that need the engineer in one round, then one `decide_many` step shows them on one screen.
  Test: `tests/workflow/footing/test_decisions.py::test_one_screen_per_round`.

### 3.5 The block (§4.6)

- AC17. Given reactions that fail bearing at the initial size, then the rounds enlarge the plan until every check passes;
  the final plan is the smallest multiple that passes, and each round's verdict sets are in the journal. Test:
  `tests/workflow/footing/test_block.py::test_enlarge_until_pass`.
- AC18. Given a footing that fails punching only, then the depth increases; given flexure only, then the spacing
  reduces. Tests: `::test_shear_deepens`, `::test_flexure_reduces_spacing`.
- AC19. Given the last attempt with footings still failing, then they are closed `NEEDS_ENGINEER`
  (`ATTEMPTS_EXHAUSTED`), the closed footings keep their result, and the workflow continues to the schedule (Q24). Given an
  eccentric reaction (a large moment with the axial force) whose minimum corner pressure is negative at the size of
  §4.4.2, then bearing is `NEEDS_ENGINEER` (BP precondition `FULL_CONTACT`, gap G-1), no other family fails, no
  decision is requested, no enlargement round runs, and the footing is closed `NEEDS_ENGINEER` with the gap (Q18).
  Tests: `::test_attempts_exhausted_closes_open_footings`, `::test_eccentric_reaction_needs_engineer`.
- AC20. Given the engineer chooses `ask_engineer`, then the block asks one plan size, a depth and a spacing (no
  separate `Lx` and `Ly`, so no rectangular footing can be entered, Q17), the schedule marks them `engineer`, and the
  next round checks them; given `combine_with_neighbor`, then the footing is closed
  `NEEDS_ENGINEER` (`COMBINE_REQUESTED`); given a resize at its bound, then closed (`LIMIT_REACHED`). Tests:
  `::test_engineer_dimensions`, `::test_combine_closes`, `::test_limit_closes`.
- AC34. Given several footings of which some close (at plan size, `WIDTH_TOO_SMALL`, at status, by
  `combine_with_neighbor` or `LIMIT_REACHED`) while the others continue, then every later layout, check batch, status
  and resize of the block holds only the open footings, no closed footing is laid out, checked, judged or resized
  again, and each closed footing keeps its last result in its closure; when no footing is open, the block leaves the
  loop and runs no calc on an empty record (amendment B-597, OQ-Q93). Test:
  `::test_rounds_pass_open_footings_only`.

### 3.6 The workflow (§4.8)

- AC21. Given any scenario, then every tool call on the ETABS server is a read, and the original file hash is
  unchanged. Test: `tests/workflow/footing/test_workflow.py::test_etabs_read_only`.
- AC22. Given a model without analysis results, then the run stops `NEEDS_ENGINEER` before step 4 (WS §4). Given case names
  that do not exist in the reactions, then they are asked again, bounded by `attempts.cases`. Given basis
  `seismic.design_category` D, E or F or `seismic.special_system = yes`, then the run stops before any sizing. Tests:
  `::test_not_analysed_stops`, `::test_unknown_cases_asked_again`, `::test_seismic_refusal`.
- AC23. Given a SAFE model as `--input`, then `NotImplementedGap` FG-2 before any call. Test:
  `tests/unit/footing/test_inputs.py::test_safe_source_gap`.

### 3.7 SAFE cross-check (§4.9)

- AC24. `harness.reactions_to_joint_loads`: golden cases of §4.9 (negation, matching within `compare.length_mm`, an
  unmatched or doubly matched joint, a missing pattern, only the cases of the chosen combinations). Test:
  `tests/golden/footing/test_reactions_to_loads.py::test_golden_cases`.
- AC25. `harness.safe_equilibrium`: golden cases (within and outside the tolerance; a self-weight pattern not compared).
  Test: `tests/golden/footing/test_equilibrium.py::test_golden_cases`.
- AC26. Given `safe.cross_check = loads_and_analysis` and a prepared fake SAFE model, then the stage asks one change-set
  approval, writes loads only with `csi_set_point_load` and missing combinations only with `csi_add_load_combo`, reads
  the loads back, saves, analyses on the long role, reads soil pressures and reactions, and stores the equilibrium
  result; a soil-pressure result with `field_map_status: candidate` produces no verdict and is marked "needs local
  test"; `LIMIT_EXCEEDED` on soil pressures is reported and the stage continues. Test:
  `tests/workflow/footing/test_safe_stage.py::test_stage_steps`, `::test_candidate_pressure_no_verdict`,
  `::test_soil_pressure_limit_reported`.
- AC27. Given `safe.cross_check = off` (or no `--safe-model`), then no SAFE server starts; given a basis without
  `compare.length_mm` or `checks.equilibrium_relative_tolerance_ratio` (required whatever `safe.cross_check` says, §4.7, Q19),
  then the basis does not freeze (spec 0004 AC23) and the run does not start. Test:
  `::test_stage_off_and_missing_fields`.
- AC28. Given the tool names any step of this workflow can call, then they are a subset of the CSI allowlist and none is
  an escape hatch (`csi_db_tables_apply`, `csi_run_script`, ...). Test:
  `tests/contract/test_footing_tools.py::test_tools_allowlisted`.

### 3.8 Outputs, approvals, replay

- AC29. Given a finished run, the report shows the schedule for subjects with both rows and lists early closures
  with their status and reason. Any `harness.footing_schedule/1` result validates. When every footing closes early,
  step 13 skips the schedule calc (Q25). The report also holds the verdicts with one calculation note per verdict
  set (`render_html`), the decisions, the value sources, and the `DRAFT` and "DRAFT SOURCES" marks. Tests:
  `tests/unit/report/test_footing_report.py::test_sections_and_marks` (golden HTML) and the step 13 scenarios in plan T9.
- AC30. Given each permission mode, then the approvals follow WS §6. Test:
  `tests/workflow/footing/test_workflow.py::test_approvals_per_mode` (parametrized).
- AC31. Given every test journal, then the value-source audit finds no engineering value without a source (F2) and the
  prompt count is at most one engineer screen per round besides review and sign-off (F4). Test:
  `tests/workflow/footing/test_acceptance.py::test_value_sources_and_prompts`.
- AC32. Given a run killed at every step and resumed with the same answers, then the schedule equals the uninterrupted
  run's; a recorded journal replays without divergence; two runs with `PYTHONHASHSEED` 0 and 1 give byte-identical
  schedules. Tests: `tests/replay/test_footing_replay.py::test_crash_matrix`, `::test_replay`, `::test_hash_seed`.
- AC33. Given the valid and invalid fixtures of each kind of §4.2, then the valid ones validate and each invalid one
  fails naming its field. Test: `tests/contract/test_footing_kinds.py::test_fixtures`.

## 4. Design

### 4.1 Modules

| Module | Content | Risk floor |
|---|---|---|
| `src/eng_harness/workflows/isolated_footing/__init__.py` | `isolated_footing_design`, `basis_fields`, input and output models | block code |
| `src/eng_harness/workflows/isolated_footing/_block.py` | `design_isolated_footing` (§4.6) | block code |
| `src/eng_harness/workflows/isolated_footing/_safe.py` | `footing_safe_cross_check` (§4.9) | block code |
| `src/eng_harness/workflows/isolated_footing/_points.py` | `footing_fix_strategy`, `footing_review` and their state models | block code |
| `src/eng_harness/rules/footing.py` | the rules of §4.5 | R1 |
| `src/eng_harness/calcs/footing/` | the calcs of §4.4 and §4.9 | R1 |
| `src/eng_harness/kinds/footing.py` | the kinds of §4.2 | R2 |
| `src/eng_harness/_calc/_code_packs.py` | the code-pack route (§4.3) | R1 (verdict storage) |
| `src/eng_harness/report/_footing.py` | schedule and calculation-note sections | report |

### 4.2 Workflow, input, output, kinds

`isolated_footing_design` (version 1): `basis_fields` §4.7, `min_server_builds = {"sasaah-csi-mcp": <pinned build>}`,
`copy_on_open = True`, `always_ask = ()`.

- Input `FootingInput`: `model` (`harness.file_input/1` reference, an `.EDB`; product by extension, SAFE AC2),
  `safe_model` (optional `.FDB` reference). No engineering value is part of the input.
- Output `FootingOutput`: `schedule` (reference to `harness.footing_schedule/1` or null when step 13 is skipped),
  `verdict_sets` (references), `rounds` (count), `safe` (reference to `harness.safe_equilibrium/1` or null),
  `accepted: bool`, `signed: bool`.
- Kinds **[added]**, registered with `KindRegistry.extend`: `harness.footing_subjects/1` (`subjects`: `{id, joint,
  column, x_mm, y_mm, cx_mm, cy_mm}`; `excluded`: `{joint, column|null, reason}`), `harness.footing_dims/1`
  (`footings`: `{id, Lx_mm, Ly_mm, h_mm, s_mm, source: calc|engineer, plan_at_max, depth_at_max, spacing_at_min,
  status, reason|null}`), `harness.footing_design/1` (dims plus `db_mm`, `n_x`, `n_y`, `s_x_mm`, `s_y_mm`, `As_x_mm2`,
  `As_y_mm2`, `d_x_mm`, `d_y_mm`, `d_mm`, `cover_mm`, `end_cover_mm`, `reaction_height_mm`), `harness.footing_status/1`
  (per footing: the six family statuses, `closure`, `state`), `harness.footing_schedule/1` (§4.4.6),
  `harness.safe_equilibrium/1` (§4.9). Ids are the support joint names.

### 4.3 The code-pack route of the CalcPort **[added]**

Engine §4.8 and calcs §4.12 item 4 (amendment B-405, Q10, C2) name this route as the one way a code-pack check
reaches the `CalcPort`. [Spec 0013](0013-column-workflow.md) §4.5 describes the same route from the column side. There
is one route, `CodePackRoute` in `_calc/_code_packs.py`, built by whichever task merges first (plan 0013 T6 or this
plan's T2); the other adds its ids and tests (C3). Its allowlist holds both workflows' ids: the three column ids of
spec 0013 §4.5, and from this workflow the six ACI footing ids and, for `sbc304_2018`, the ids `check_id_for` gives
for them (resolved when the registry is built, SBC Q1). `run` takes either argument form: the inline `items` below or
the `batch` reference of spec 0013 §4.5. This workflow also adds `NotImplementedGap` as a verdict. `CodePackRoute` is
consulted by `HarnessCalcPort` for an id that does not start with `harness.` (harness calc ids do):

1. `describe(check_id)`: an id outside the allowlist, or one the `Registry` the run was built with does not know (packs
   discovered once at engine construction, CF §4.6), is `ContractError` `NOT_FOUND`, as an unknown calc id in calcs §6,
   never an exception of `structural_codes` raised to the block (C4; the pack's own `Registry.get` answers `NOT_FOUND`
   for an unknown id too). Otherwise `CalcInfo` (the fields of engine §4.8) with `version` = the check's
   `CheckMeta.version` (Q20, draft decision B-442), `content_sha256`, `status` (the check's lifecycle state: `draft`,
   `verified`, `approved` or `withdrawn`, the values of a calc status), `basis_fields` (the basis paths its input model
   declares as sources) and `ref_rules` (no `stale_ok`).
2. `run(check_id, {"items": [{"subject": Subject, "inputs": {name: Ref}}]})` or `run(check_id, {"batch": <reference to
   an item list>})` (the list is resolved into the same items): the allowlist as in step 1, then the refusals of calcs
   §4.12 item 4 before any evaluation: a `withdrawn` check is refused in both run classes (`CalcRefused`
   `CALC_WITHDRAWN`), and in `production` a check that is not `approved` is refused (`CalcRefused` `CALC_NOT_APPROVED`).
   The pack's own `CheckNotUsable` (CF AC25, raised for a withdrawn check in either mode and for a check that is not
   approved in `production`) is unreachable only because of these two refusals. Then `evaluate_batch(check_id, items,
   mode=<run class>, registry, source=store, current_revision=..., policy=InputPolicy(require_refs=True))`; it stores
   the payload as `verdicts.set/1` (parents the referenced results) and returns `make_success` with the counts.
   `NotImplementedGap` from a check is a verdict, not an error (CF §4.4); a contract error of an item becomes a failure
   envelope (calcs §4.12 item 3); every other exception is `INTERNAL` with an incident id.
3. Item limit `CalcSettings.max_items` applies to the item count, in both argument forms.

`code_pack_check(base_id)` in the workflow resolves the id: the base id for `aci318_14`, `sbc304_2018.check_id_for(base_id)`
for `sbc304_2018` (SBC Q1). It is an engine-side helper passed to the block as data (a mapping from base id to id), so
block code imports no pack.

### 4.4 Calcs

All calcs follow calcs §4.2 and §4.4: pure, exact (`Fraction`) for every comparison, basis fields read as field objects,
constants only `Cited` (the integers of geometric identities with source `Geometry`, `k_m` with source "SI prefix
milli", as BP §5, and π with source "mathematical constant, area of a circle", used by L2 only). Each ships `draft` with a verification record.

#### 4.4.1 `harness.footing_subjects` v1

Input: `placements` (`model.frame_placements/1`), `sections` (`model.sections/1`), `reactions`
(`forces.joint_reactions/1`), `basis` (`compare.angle_deg`). Method: S1 a column is a frame of kind `column`; its lower
joint is the end with the smaller `z_mm`. S2 a support joint is a joint with at least one reaction row. S3 a subject is a
support joint with exactly one column whose lower joint it is; zero columns gives `NO_COLUMN_AT_JOINT`, more gives
`TWO_COLUMNS_AT_JOINT`. S4 the section must be `rectangular` (`SECTION_NOT_RECTANGULAR` otherwise, ACI plan §6.3). S5
with `θ = rotation_deg` reduced to [0, 360): within `compare.angle_deg` of 0 or 180 gives `cx = b`, `cy = h`; of 90 or 270
gives `cx = h`, `cy = b`; otherwise `COLUMN_ROTATED`. Which of `b_mm` and `h_mm` lies along local axis 2 at zero
rotation is the CSI convention to confirm (L2). S6 `x_mm`, `y_mm` from the lower joint.

#### 4.4.2 `harness.footing_plan_size` v1

Input: `subjects`, `reactions`, `service_cases` (engineer input reference), `basis`
(`foundation.allowable_bearing_pressure_kPa`, `.allowable_bearing_kind`, `.soil_unit_weight_kN_m3`,
`.soil_depth_above_footing_mm`, `.surcharge_kPa`, `materials.concrete_unit_weight_kN_m3`, `foundation.min_depth_mm`,
`.min_plan_dimension_mm`, `.max_plan_dimension_mm`, `.plan_increment_mm`, `.plan_shape`, `reinforcement.max_spacing_mm`).
Output `harness.footing_dims/1` with `h = min_depth_mm`, `s = max_spacing_mm`.

- P0. `allowable_bearing_kind` must be `gross`, else `NEEDS_ENGINEER` (`NET_ALLOWABLE`, BP G-2). `plan_shape` must be
  `square`, else `NotImplementedGap` FG-1.
- P1. `N_k = FZ_k` for every service case `k` of the joint (BP S3 sign convention); any `N_k ≤ 0` gives
  `NEEDS_ENGINEER` (`UPLIFT`). A joint with no reaction row for any service case has no `N_k` (P3 has no maximum) and
  gives `NEEDS_ENGINEER` (`NO_SERVICE_LOAD`) (amendment B-567, OQ-Q64).
- P2. `w = h·γc + soil_depth·γs + surcharge` (BP S3 per unit area); `q_net = q_allow − w`; `q_net ≤ 0` gives
  `NEEDS_ENGINEER` (`OVERBURDEN`).
- P3. `A_req = max_k N_k / q_net`. Moments are not used here. The bearing check then includes them: a bearing `FAIL`
  (full contact, `q_max` above the allowable) is enlarged by the rounds (§4.6, `ff.bearing_only`), but partial contact
  at the trial size (`q_min < 0`) is bearing `NEEDS_ENGINEER` (BP precondition `FULL_CONTACT`, gap G-1), which closes
  the footing `needs_engineer` under §4.4.5 without a round (AC19, Q18).
- P4. `n` is the smallest integer with `(n·i)² ≥ A_req` and `n·i ≥ min_plan`, found with integer square roots of the
  exact fraction and confirmed by both comparisons; `Lx = Ly = n·i`.
- P5. `n·i > max_plan` gives the largest multiple not above `max_plan`, `plan_at_max = true` and status
  `LIMIT_REACHED` (the checks then decide). A basis with `max_plan_dimension_mm < plan_increment_mm` has no positive
  multiple to give and is refused with `OUT_OF_RANGE` (calcs §6) (amendment B-567, OQ-Q64).
- P6. A footing with a `NEEDS_ENGINEER` status (P0, P1, P2) still carries a size in the output: `Lx = Ly` the smallest
  multiple of `i` not below `min_plan_dimension_mm`, with `h` and `s` as above. The block closes it at §4.6 step 1
  and passes no such size to a check (amendment B-567, OQ-Q64).

#### 4.4.3 `harness.footing_layout` v1

Input: `dims`, `subjects`, `basis` (`reinforcement.bar_diameter_mm`, `.bottom_layer`, `durability.cover_footing_mm`,
`foundation.reaction_point`). Output `harness.footing_design/1`. Bars spanning in X lie across the width `Ly` (and Y
across `Lx`); `c` is the cover, `db` the diameter.

- L1. The span between the outer bar centres is `span_x = Ly − 2c − db`. If `span_x ≤ 0`, the row is `NEEDS_ENGINEER`
  (`WIDTH_TOO_SMALL`) before computing any actual spacing (its numbers — the given spacing `s` shown, the steel of 0
  or 1 bars — are informative only: the block closes the footing at §4.6 step 2.1 and never passes them to a check,
  plan T8). For `span_x > 0`, `n_x = ⌈span_x/s⌉ + 1` (at least two bars, with `n_x = 2` for `0 < span_x ≤ s`), the
  smallest bar count whose actual spacing is at most the input `s`, which plan sizing initialises from
  `reinforcement.max_spacing_mm` (AC8; §4.4.2; rule R4 lets `engineer_set` keep and flag a value above that bound),
  and the actual spacing is `s_x = span_x/(n_x − 1)`. The same holds for `n_y` and `s_y` with `span_y = Lx − 2c − db`.
  The ceiling is taken on the exact fraction, so a positive span that is an exact multiple of `s` gives `s_x = s`.
  Amendment B-568: the ceiling by the owner answer of 2026-11-18 (OQ-Q60, Q21), in place of the floor
  `⌊span/s⌋ + 1`, which could give an actual spacing above the input `s`.
- L2. `As = n·π·db²/4` each way (geometry). `As` is a float output (`As_x_mm2`, `As_y_mm2`) passed to the checks by
  reference; no comparison inside the calcs of §4.4 uses it, so the exact-comparison rule holds.
- L3. `bottom_layer = x_bottom`: `d_x = h − c − db/2`, `d_y = h − c − 3·db/2`; `y_bottom` swaps them; `d = (d_x + d_y)/2`
  for punching (ACI plan Q5). A depth with no room for both layers (the upper layer's effective depth,
  `h − c − 3·db/2`, zero or less) is refused with `OUT_OF_RANGE`, field `dims` (calcs §6; amendment B-568, OQ-Q63).
- L4. `cover_x = cover_y = end_cover = c` (bars end at the cover from each face).
- L5. `reaction_point = top_of_footing` gives `reaction_height = h`; `base_of_footing` gives 0 (BP §3).

#### 4.4.4 `harness.footing_resize` v1

Input: `dims`, `actions` (per footing: `enlarge_plan`, `increase_depth`, `reduce_bar_spacing`, `engineer_set` or
`none`), `engineer_plan`, `engineer_depth`, `engineer_spacing` (references to the fields `L`, `h`, `s` of one
`basis.engineer_input/1` answer), `basis` (`foundation.plan_increment_mm`, `.min_plan_dimension_mm`,
`.max_plan_dimension_mm`, `.depth_increment_mm`, `.min_depth_mm`, `.max_depth_mm`,
`reinforcement.spacing_increment_mm`, `.min_spacing_mm`, `.max_spacing_mm`). The engineer values are one triple of
top-level references per call (the CalcPort resolves top-level references only, calcs §4.7), taken by the footings
of that call whose action is `engineer_set`; the block (plan T8, run by the workflow of plan T9) therefore calls the
resize once per engineer answer (§4.6 step 7), and once for the footings with the other actions, each call on a record
of only the open footings of that call (§4.6, amendment B-597). The bounds of R4 are
`min_plan_dimension_mm` to `max_plan_dimension_mm` for `L`, `min_depth_mm` to `max_depth_mm` for `h` and
`min_spacing_mm` to `max_spacing_mm` for `s` (amendment B-567, OQ-Q64: the three lower or upper bounds
`min_plan_dimension_mm`, `min_depth_mm` and `max_spacing_mm` join the six fields listed before). Footings stay square (FG-1): `Lx = Ly = L` in every output. R1 `enlarge_plan`: `L' = (⌊L/i⌋ + 1)·i`, the smallest multiple of
`i` above `L` (`(n + 1)·i` when `L = n·i`; exact floor division of the fractions). R2 `increase_depth`: `h + depth_increment_mm`. R3 `reduce_bar_spacing`:
`s − spacing_increment_mm`. A result past its bound leaves the size unchanged, sets the flag and status `LIMIT_REACHED`.
R4 `engineer_set` takes the three values `L`, `h`, `s` of `basis.engineer_input/1` with `source: engineer` and sets
`Lx = Ly = L`; the engineer cannot enter a rectangle (Q17). A value outside its basis bounds (above) is kept and flagged
`OUTSIDE_BASIS_BOUNDS` (Q13); a plan that is not a multiple of `i` is kept and flagged `OFF_INCREMENT` (no check
depends on the increment). Depths are counted from `min_depth_mm`, plans from zero.

#### 4.4.5 `harness.footing_status` v1

Input: `subjects`, `design`, the six verdict-set references of one round. Per footing and family (bearing, one-way
shear, punching, flexure, minimum steel, development) the family status is `FAIL` if any verdict fails, else `ERROR`,
else `NEEDS_ENGINEER`, else `NOT_APPLICABLE`, else `PASS`; with the governing ratio for display. `closure`: `passed` when
all six are `PASS`; `failing` when any is `FAIL`; else `needs_engineer`. `state` is the `FootingFailureState` of §4.5.

#### 4.4.6 `harness.footing_schedule` v1

Input: `subjects`, `design` and `status` for the same set of footings (§4.6, Q25), closures (reasons), the decision
references, `basis` (`foundation.min_clear_distance_mm`). Clearance per pair of footings, plans centred on their joints (the column is centred,
BP §2): `gx = |xi − xj| − (Lxi + Lxj)/2`, `gy` likewise; both negative is an overlap; one negative gives the other as the
distance; both positive give `√(gx² + gy²)` (compared squared). A distance below `min_clear_distance_mm` marks both
footings `NEEDS_ENGINEER` (`CLEARANCE`, the neighbour named). Output `harness.footing_schedule/1`: per footing the design,
status, reasons, family statuses and ratios, verdict-set references, decision references, sources of each size.

#### 4.4.7 Footing row copy calcs v1 **[added]** (amendment B-613)

The four calcs share one implementation. Each declares a fixed input kind for both `base` and `extra` and a fixed
output kind (Q26, Q28).

| Calc id | Input kind | Output kind |
|---|---|---|
| `harness.footing_rows_dims` | `harness.footing_dims/1` | `harness.footing_dims/1` |
| `harness.footing_rows_design` | `harness.footing_design/1` | `harness.footing_design/1` |
| `harness.footing_rows_status` | `harness.footing_status/1` | `harness.footing_status/1` |
| `harness.footing_rows_subjects` | `harness.footing_subjects/1` | `harness.footing_subjects/1` |

Input: `base` and `extra`, two top-level references to whole stored records, resolved by the CalcPort. `ids` is the
ordered list of footing ids to keep.

- K1. Refuse a reference of the wrong kind (`REF_KIND_MISMATCH`). For each id in `ids`, copy its row unchanged
  from `extra` if present there, otherwise from `base`. Refuse an id found in neither input with `ContractError`
  `INVALID_ARGUMENT`, field `ids`, naming the missing id (Q27).
- K2. Return the selected rows sorted and unique by id, in `subjects` for `harness.footing_subjects/1` and in
  `footings` for the other kinds. For `harness.footing_subjects/1`, keep the `base` record's `excluded` list
  unchanged. The method is pure, uses no basis fields and performs no arithmetic on the rows.
- K3. Trace the two input references and the row selection, citing this section. The CalcPort records the input
  references and parent records and sets `tool: "harness"` provenance as for the sibling calcs (calcs §4.12).

Output: a stored record of the declared kind with fresh `calc`, `draft` and `trace` metadata. The CalcPort marks
a successful result complete by default. A refusal stores no result.

Verification: `draft` for each calc, with its own verification record citing §4.4.7 and hand-derived golden cases
for its kind. Cover filtering, overlap, disjoint inputs, chaining, ordering, missing ids and wrong-kind refusal (AC35).

### 4.5 Decision point and rules

`footing_fix_strategy` (version 1, 12 §2): options `FootingAction` = `enlarge_plan`, `increase_depth`,
`reduce_bar_spacing` **[added]**, `combine_with_neighbor`, `ask_engineer`. State `FootingFailureState`: `bearing`,
`one_way_shear`, `punching`, `flexure`, `min_steel`, `development` (`VerdictStatus`), `plan_at_max`, `depth_at_max`,
`spacing_at_min`, `engineer_sized` (booleans). No ratio and no number (Q4). Policy `DecisionPolicy(model=True,
llm=False)` with the defaults (`shadow` on, 12 §3): without a release (none exists in v1, decisions §4.3) a decision
model's answer is only a suggestion on the engineer screen.

Rules (`src/eng_harness/rules/footing.py`), in this order, `thresholds=()` (no basis value is needed):

| Id | When | Pick |
|---|---|---|
| `ff.limits_reached` | `plan_at_max` and `depth_at_max` and `spacing_at_min` | `ask_engineer` |
| `ff.bearing_only` | bearing `FAIL`, the five others `PASS`, not `plan_at_max` | `enlarge_plan` (12 §2) |
| `ff.shear_only` | one-way or punching `FAIL`, bearing, flexure, minimum steel, development `PASS`, not `depth_at_max` | `increase_depth` |
| `ff.steel_only` | flexure or minimum steel `FAIL`, bearing, one-way, punching, development `PASS`, not `spacing_at_min` | `reduce_bar_spacing` (Q5) |
| `ff.development_only` | development `FAIL`, the five others `PASS`, not `plan_at_max` | `enlarge_plan` |

`footing_review` (version 1): options `accept`, `reject`; `require_engineer=True`; state: counts of footings by status as
labels and a reference to the schedule when step 13 produces one.

### 4.6 The block `design_isolated_footing`

Input: `subjects`, `reactions`, `service_cases`, `factored_cases` (references), `check_ids` (base id to id). Output:
`design` (`harness.footing_design/1`) and `status` (`harness.footing_status/1`) for the subjects with both rows,
or null when there are none (Q25), `closures` (each with the footing's last result, below), `decisions`,
`verdict_sets`, `rounds`.

1. `dims = ctx.calc("harness.footing_plan_size", ...)`. Footings with a `NEEDS_ENGINEER` status are closed; the others
   are the open footings. If no footing is open, the block does not enter the loop (`break` at its start) and runs no
   further round calc on an empty record.
2. `async for a in ctx.attempts(ctx.basis.count("attempts.footing_rounds"))`, over the open footings:
   1. Build the open footings' `dims` with `harness.footing_rows_dims` and pass it to
      `ctx.calc("harness.footing_layout", ...)`. `WIDTH_TOO_SMALL` closes (its numbers are informative only, §4.4.3 L1).
      If no footing remains open, `break`; no further round calc runs on an empty record.
   2. Build the still-open footings' `design` with `harness.footing_rows_design`. Run six `ctx.calc` batches, items per open
      footing: bearing per service case; one-way shear, punching, flexure per factored case; minimum steel and
      development once. Inputs are references: reaction rows by pointer
      (`/rows/<n>/FX_kN`, ...), basis fields (the ACI clause-spec paths, ACI plan Q2), design fields
      (`/footings/<i>/Lx_mm`, ...).
   3. `ctx.calc("harness.footing_status", ...)` on that same design record. `passed` and `needs_engineer` footings
      close. If no footing remains open, `break`; no further round calc runs on an empty record.
   4. No failing footing: `break`. On `a.is_last`: failing footings close `ATTEMPTS_EXHAUSTED`, then `break` (Q1).
   5. `ctx.decide_many` with one request per failing footing (rules of §4.5).
   6. `ask_engineer`: `ctx.ask(FootingDimensions, title=...)` per such footing (`L` the square plan size, `h`, `s`,
      with units; no separate `Lx` and `Ly`, Q17);
      `combine_with_neighbor`: closes `COMBINE_REQUESTED`.
   7. `dims = ctx.calc("harness.footing_resize", ...)` once per engineer answer and once for the other actions
      (§4.4.4), each call on a `dims` record built with `harness.footing_rows_dims` for only the open footings that call
      acts on, with an action for each of them. `LIMIT_REACHED` closes. If no footing is open before a resize call
      or after these closures, `break`; no further round calc runs on an empty record.

Open footings only (amendment B-597; owner answer of 2026-11-20, OQ-Q93, option (b)): the block passes the open
footings only. Each round, the layout and the resize read a `harness.footing_dims/1`, and the check batches and the
status a `harness.footing_design/1`, that hold only the footings still open, each row copied unchanged from the last
record of that kind that holds it; a footing that closes at any step leaves every later round record and is never laid out,
checked, judged or resized again (so the numbers of a `WIDTH_TOO_SMALL` row never reach a check, §4.4.3 L1). A closed
footing keeps its last result aside: its closure holds its status, its reason and the references of the last records
that hold its row (`harness.footing_dims/1`, and `harness.footing_design/1` and `harness.footing_status/1` when it
reached them).

Amendment B-613 (Q23 to Q27): the block calls the copy calc for the record's kind (§4.4.7) to store these
records. For a single source, pass its reference as both `base` and `extra`. For multiple sources of one kind,
start with the oldest source as `base` and chain one call per extra source in record order. After the first call,
use the previous result as `base`. Request only the wanted ids available so far. This selects each row from the
latest source that holds it. In step 2.1 this also joins the open rows from the preceding round's separate resize results.

At block exit, keep only subjects with both a stored design row and a stored status row. For those subjects,
assemble `design` with `harness.footing_rows_design` and `status` with `harness.footing_rows_status` using the last
records that hold each row, including the closure references for closed footings. Early closures at plan sizing or
`WIDTH_TOO_SMALL` supply status and reason to the report from their closures (Q25).

The `for` over footings builds argument lists only; every engineering value is a calc output or a reference.

### 4.7 Design basis fields

No value is shipped (spec 0004 Q8). Paths of the ACI clause specs are kept (ACI plan Q2); the others are **[added]**
(Q12). The last segment of each quantity path ends with the contract §4.7.2 suffix of its unit (spec 0007 §4.8 naming;
amendment B-484). All are required unless marked; units are those of `BasisField.unit`.

| Path | Kind | Unit | Used by |
|---|---|---|---|
| `design.code_pack` | choice `aci318_14`, `sbc304_2018` | — | §4.3 |
| `seismic.design_category` | choice `a` to `f` | — | refusal of D to F (ACI plan Q16) |
| `seismic.special_system` | choice `yes`, `no` | — | refusal (ACI plan Q8) |
| `foundation.allowable_bearing_pressure_kPa` | quantity | kPa | plan size, bearing (asked each run, 13 §2) |
| `foundation.allowable_bearing_kind` | choice `gross`, `net` | — | plan size, bearing |
| `foundation.soil_unit_weight_kN_m3`, `materials.concrete_unit_weight_kN_m3` | quantity | kN/m3 | plan size, bearing |
| `foundation.soil_depth_above_footing_mm` | quantity | mm | plan size, bearing |
| `foundation.surcharge_kPa` | quantity | kPa | plan size, bearing |
| `materials.concrete_fc_MPa`, `materials.rebar_fy_MPa` | quantity | MPa | checks |
| `materials.concrete_class` | choice `normalweight`, `lightweight`, `sand_lightweight` | — | checks |
| `materials.rebar_coating` | choice `uncoated`, `epoxy`, `zinc_epoxy_dual` | — | development |
| `durability.cover_footing_mm` | quantity | mm | layout, development |
| `limits.ratio_limit_ratio` | quantity | 1 | verdicts |
| `foundation.min_plan_dimension_mm`, `.max_plan_dimension_mm`, `.plan_increment_mm` | quantity | mm | plan size, resize |
| `foundation.plan_shape` | choice `square`, `equal_projection` | — | plan size (FG-1) |
| `foundation.min_depth_mm`, `.max_depth_mm`, `.depth_increment_mm` | quantity | mm | plan size, resize |
| `foundation.reaction_point` | choice `top_of_footing`, `base_of_footing` | — | layout (Q6) |
| `foundation.min_clear_distance_mm` | quantity | mm | schedule |
| `reinforcement.bar_diameter_mm` | quantity | mm | layout |
| `reinforcement.max_spacing_mm`, `.min_spacing_mm`, `.spacing_increment_mm` | quantity | mm | plan size, resize (Q15) |
| `reinforcement.bottom_layer` | choice `x_bottom`, `y_bottom` | — | layout |
| `compare.angle_deg` | quantity | deg | subjects (calcs §4.4) |
| `attempts.footing_rounds`, `attempts.cases` | count | — | `ctx.attempts` (engine Q1) |
| `safe.cross_check` | choice `off`, `loads_and_analysis` | — | §4.9 |
| `compare.length_mm`, `checks.equilibrium_relative_tolerance_ratio` | quantity | mm, 1 | §4.9 (required in every run: spec 0004 has no conditional requirement, Q19) |

### 4.8 The workflow steps

WS §4 as ctx calls: 1, 2 engine (build check, `copy_on_open`). 3 `ctx.tool("csi_analysis_status")`; not finished →
`ctx.escalate("not_analysed", ...)`. 4 `ctx.basis.choice` of the two seismic fields; a refused value →
`ctx.escalate("seismic_out_of_scope", ...)`. 5 the model-state reader (placements, sections) and
`csi_results_joint_reactions` (spec 0002 §4.6.1 step 13), then `harness.footing_subjects`. 6 `ctx.ask(FootingCases)`
(`service_cases`, `factored_cases`: lists of case names) inside `ctx.attempts(ctx.basis.count("attempts.cases"))`, each
name checked against the case names of the reaction rows (string equality, no engineering value). 7 to 12
`ctx.block(design_isolated_footing, ...)`. 13 For subjects that have both rows, build the filtered subjects reference
with `harness.footing_rows_subjects`, passing the step 5 subjects reference as both `base` and `extra` and the
qualifying ids as `ids`. Pass the filtered subjects, assembled design and status references, and those subjects'
closure, verdict-set and decision entries to `harness.footing_schedule` (§4.6, Q25, Q28). Skip both calls if none
qualify. 14 `ctx.block(footing_safe_cross_check, ...)` when on.
15 `ctx.decide("footing_review", ...)`. 16 report and sign-off (spec 0006), including the status and reason of early
closures. A `.FDB` as `--input` is FG-2.

### 4.9 SAFE cross-check `footing_safe_cross_check`

Runs SAFE §4.2 steps 1 to 7 on a working copy of the engineer's prepared `.FDB`. It writes nothing that a check depends
on, and no SAFE result changes a verdict.

1. Read the SAFE model state (points, load set; SAFE §4.4).
2. `harness.reactions_to_joint_loads` v1 **[added]** (SAFE §4.2 names it): inputs the ETABS reactions, subjects, the
   ETABS `model.load_set/1`, the SAFE points and load set, the engineer's cases, `basis` (`compare.length_mm`). M1 the
   transferred cases are the `load_pattern` or `load_case` items of the chosen combinations. M2 each subject joint is
   matched to the one SAFE point within `compare.length_mm` in plan; none gives `NEEDS_ENGINEER` (`UNMATCHED`), two or more
   `INVALID_ARGUMENT`. M3 loads are the negatives of the reactions (action and reaction, as BP §4.1). M4 a case without a
   SAFE pattern of the same name is `NEEDS_ENGINEER` (`PATTERN_MISSING`): the workflow never creates a pattern (it would
   need a self-weight value). Output `harness.joint_loads/1` with null punching dimensions (SG-7), and the combinations
   to add (items and scales read from the ETABS model, source `model:`); a SAFE combination of the same name with other
   items is `NEEDS_ENGINEER`, never replaced.
3. `ctx.approve` (change set: the loads and combinations), then the import and `csi_add_load_combo` `under=` it; the
   adapter reads back (SAFE AC18).
4. Save, `csi_run_analysis` (long role), `csi_analysis_status`.
5. Soil pressures for the chosen service combinations (SAFE §4.6), base reactions.
6. `harness.safe_equilibrium` v1 **[added]**: per transferred pattern without self weight in the SAFE load set,
   `| |R| − |A| | ≤ tol·|A|` with `A` the sum of applied `FZ` and `R` the base reaction `FZ` (magnitudes, because the
   base-reaction sign is unconfirmed, SAFE Q6); `PASS` or `FAIL` per pattern; self-weight patterns `NOT_COMPARED`.
7. Soil pressures go to the report as raw host values with `field_map_status`; a `candidate` map never feeds a verdict
   (SAFE Q8). The SAFE footing areas keep the engineer's geometry, because the workflow cannot resize them (FG-3).

## 5. Inputs and outputs

| Field | Type | Unit | Source |
|---|---|---|---|
| Reactions `FX_kN` to `MZ_kNm` | float | kN, kN.m | `forces.joint_reactions/1` (ETABS) |
| Column `cx_mm`, `cy_mm`, positions | float | mm | ETABS model reads through §4.4.1 |
| Service and factored cases | list of names | — | engineer input |
| Plan, depth, spacing | float | mm | calcs §4.4.2, §4.4.4 or engineer input |
| Bars, depths, areas | int, float | mm, mm2 | calc §4.4.3 |
| Basis fields | §4.7 | §4.7 | basis |
| Outputs | kinds of §4.2, `verdicts.set/1`, the report | canonical | this workflow |

## 6. Errors

| Condition | Result |
|---|---|
| Model not analysed; seismic scope refused | `NEEDS_ENGINEER` escalation before sizing |
| Unknown cases after the attempts | `attempts_exhausted` escalation |
| A footing returned with a per-footing `NEEDS_ENGINEER` status | that footing `NEEDS_ENGINEER` with its reason; the run continues |
| Layout with a depth that leaves no room for both bottom layers (§4.4.3 L3) | `harness.footing_layout` refuses with `OUT_OF_RANGE`, field `dims` (calcs §6; amendment B-568) |
| A copy calc finds a requested id in neither record (§4.4.7 K1) | `ContractError` `INVALID_ARGUMENT`, field `ids` |
| FG-1, FG-2 | `NotImplementedGap` (`NOT_IMPLEMENTED`) |
| Draft check or calc in a production run | `CalcRefused` (calcs §4.12) |
| Check id outside the code-pack route's allowlist, or unknown to the registry | `ContractError` `NOT_FOUND` before any evaluation (§4.3, calcs §6) |
| SAFE stage failures | SAFE §6; the stage stops and the report shows it; the design stands |

## 7. Non-goals

WS §9; also: any value or default in code; host design results as verdicts; detailing checks the packs do not have
(band rule, bar spacing limits, minimum effective depth, ACI plan Q7, Q13); drawings.

## 8. Risks

| Risk | Floor | Mitigation |
|---|---|---|
| A wrong input mapping makes a check pass on wrong data | R1 | References only; golden cases of every calc; the value-source audit (AC31) |
| The reaction sign or axis convention is wrong | R1 | Local test L1; the bearing value does not depend on moment signs (BP S4) |
| The loop does not converge | R1 | `ctx.attempts`; closure per footing; bounds flags |
| A decision model's answer is applied | R1 | Shadow on, no release in v1 (AC15) |
| A SAFE pressure is read through a guessed column | R1 | No verdict from a `candidate` map (AC26) |

## 9. Test strategy

| Criteria | Level | Folder |
|---|---|---|
| AC1, AC12, AC13, AC23 | Unit | `tests/unit/footing/` |
| AC2, AC14 | Rules | `tests/rules/` |
| AC3, AC4 | Unit (code-pack route) | `tests/unit/calcs/` |
| AC6 to AC11, AC24, AC25, AC35 | Golden and property | `tests/golden/footing/`, `tests/property/` |
| AC35 | Unit | `tests/unit/footing/` |
| AC5, AC15 to AC22, AC26, AC27, AC30, AC31, AC34 | Fake-host workflow | `tests/workflow/footing/` |
| AC28, AC33 | Contract | `tests/contract/` |
| AC29 | Golden HTML | `tests/unit/report/` |
| AC32 | Replay and crash matrix | `tests/replay/` |

## 10. Version impact

Part of `eng-harness` 0.1.0: a new workflow, blocks, calcs, kinds and a point (additive). The `CalcPort` gains the
code-pack route (additive to engine §4.8).

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | On the last attempt, failing footings are closed `ATTEMPTS_EXHAUSTED` and the run continues, instead of the escalation of 11 §3 that would stop the whole run | Owner | Accept: the passing footings and the evidence reach the report; the escalation still applies to the case question |
| Q2 | Square footings only (FG-1), because the band rule for rectangular footings is not checked (ACI plan Q7) | Owner | Accept for v1; enable `equal_projection` (the owner's practice) when a band-rule check exists |
| Q3 | `footing_fix_strategy` as the one decision point of phase 2 run with the decision model in shadow mode (ADR-0025 decision 5, 19 §1) | Owner | Accept; leave shadow only by the evaluation of spec 0009 §4.10 |
| Q4 | The decision state holds statuses and bound flags, no ratios | Owner | Accept for the rules; add ratios in a new point version only if the shadow evaluation shows the model needs them |
| Q5 | Flexure-only failures reduce the spacing before deepening (an engineering preference) | Owner | Review the rule order of §4.5 as R1 content |
| Q6 | Reaction point `top_of_footing` or `base_of_footing`; pedestals not modelled (FG-4) | Owner | Accept; a pedestal height field later |
| Q7 | Grouping into footing types and the office's fixed type table (Sasaah `FootingGrouper`, `fixedTypes`) | Owner | Later calc `harness.footing_types` once the basis has a list kind (spec 0004 has none) |
| Q8 | Service and factored cases are asked each run, not stored in the basis | Owner | Accept; a template may later hold name patterns |
| Q9 | The Sasaah tool embeds engineering values (load factors 1.2 and 1.6, subgrade modulus as a multiple of the bearing pressure, a spacing cap, an equilibrium tolerance) and implements ACI 318-19 | Owner | Not adopted (as OQ-G14); none of its values appears here; no tool result is compared with a code-pack result |
| Q10 | The code-pack route (§4.3) amends specs 0001 and 0003 | Owner | Settled by amendment B-405 (draft; the owner approves): engine §4.8 and calcs §4.12 item 4 and §6 name the one route |
| Q11 | `eng-harness` depends on three workspace packages of `structural-codes` | Owner | No ADR (no third-party code; 03 §2 allows it from phase 2); spec 0013 Q12 asks the same and plan 0013 T6 lists `docs/adr/0004-workspace-code-packs.md`: one answer for both |
| Q12 | New basis paths (`design.*`, `seismic.*`, `foundation.*` sizing, `reinforcement.*`, `safe.*`) | Owner | Adopt with spec 0004's template schema, with the clause-spec paths (ACI plan Q2) |
| Q13 | Engineer dimensions outside the basis bounds are kept and flagged, not refused | Owner | Accept: the engineer decides; the report shows the flag. The bounds are the minimum and maximum plan, depth and spacing fields of §4.4.4 (amendment B-567, OQ-Q64) |
| Q14 | `foundation.min_depth_mm` is the engineer's value; the code minimum effective depth is not checked (ACI plan Q13) | Owner | Add the check to the pack later |
| Q15 | Bar spacing limits of the code are not checked; the basis spacings are the engineer's (ACI plan Q7) | Owner | As Q14 |
| Q16 | No measured manual time for footing design exists | Owner | Prepare a footing benchmark (two or three past projects) before the first release, for F6 and F7 |
| Q17 | Engineer dimensions are one square plan size `L` with `h` and `s`; a rectangular footing cannot be entered, because the band rule is not checked (Q2, ACI plan Q7); an engineer plan off the increment is kept and flagged, and `enlarge_plan` then rounds up to the next multiple | Owner | Accept for v1; add `Lx`, `Ly` in a new `FootingDimensions` version together with the band-rule check |
| Q18 | A large moment can give partial contact (`q_min < 0`) at the size found from `N` only; bearing is then `NEEDS_ENGINEER` (BP G-1), not `FAIL`, so the footing goes to the engineer with no enlargement round | Owner | Accept for v1 (explicit and tested, AC19). Later, preferred: a cited calc that sizes for `q_min ≥ 0` from the moments (BP S5 solved for the plan), so the first size already has full contact; alternative: a rule that may enlarge a bearing `NEEDS_ENGINEER` with reason `FULL_CONTACT` while `plan_at_max` is false (needs the reason in the decision state, a new point version) |
| Q19 | `compare.length_mm` and `checks.equilibrium_relative_tolerance_ratio` are required in every run, also with `safe.cross_check = off`, because spec 0004 has no conditional requirement (`FieldSpec.required: bool`; conditionals are its non-goal) | Owner | Accept for v1 (two values confirmed and unused when off); derive `required_basis` from a choice field in spec 0004 if more conditional fields appear |
| Q20 | **[added]** A code-pack check's `CalcInfo.version` (§4.3 step 1): engine §4.8 and `eng_harness.ports.CalcInfo` require an integer of at least 1 (also `ctx` `calc_version` and the journaled step version, engine AC13), but a merged check has no integer version: `CheckMeta` has none, and the only version is the pack's string `version`, which CF AC9 makes the trace's `calc_version` | Owner, lead | Decided (draft, B-442; owner queue): each check has an integer `version` in `CheckMeta` (default 1, raised when the check's behaviour changes; CF §4.2, structural-codes core plan T15), which the route passes as `CalcInfo.version`; the pack's string version stays in the trace (CF AC9) |
| Q21 | Rule L1 of §4.4.3 (`⌊span/s⌋ + 1`) could give an actual spacing above the input `s`, contradicting AC8 (and `reinforcement.max_spacing_mm` when plan sizing initialises `s` from it); §4.4.3 was silent on a depth with no room for both layers and on the numbers of a `WIDTH_TOO_SMALL` row (OQ-Q60, OQ-Q63) | Owner | Decided (owner answer of 2026-11-18, OQ-Q60; amendment B-568): `WIDTH_TOO_SMALL` for a span of zero or less before computing actual spacing, and the ceiling `⌈span/s⌉ + 1` for a positive span so the actual spacing is at most the input `s`, which plan sizing initialises from `reinforcement.max_spacing_mm` (while rule R4 lets `engineer_set` keep and flag a value above that bound); a depth with no room for both layers is `OUT_OF_RANGE`, field `dims`; the numbers of a `WIDTH_TOO_SMALL` row are informative only and plan T8 never uses them (OQ-Q63); no engineering number is added |
| Q22 | The block must close some footings while the others continue (§4.6, §4.4.2 P6), but `harness.footing_status` needs a verdict for every footing of the design it reads, `harness.footing_resize` never drops a row, and checking a `WIDTH_TOO_SMALL` row again breaks OQ-Q63 (OQ-Q93) | Owner | Decided (owner answer of 2026-11-20, OQ-Q93, option (b); amendment B-597): the block passes the open footings only; each round the layout, the check batches, the status and the resize read a record of the open footings only; a closed footing keeps its last result aside; no merged calc changes (§4.6, AC34) |
| Q23 | **[added]** How block code stores an open footings' record (§4.6): the engine stores results only for tools, calcs and `ctx.ask` (engine §4.3.2), and a calc refuses a literal `dims` or `design` under `require_refs` (calcs §6), so no merged step stores a record with the closed rows left out | Lead, then owner | Decided (owner answer of 2026-11-26; amendment B-613): option (i), the copy method (§4.4.7, one calc per kind under Q26), copies named rows unchanged from two top-level references to same-kind records. Chain one call per extra source. Plan T7b adds the calcs beside the merged calcs, which keep their versions, inputs and rules |
| Q24 | **[added]** `harness.footing_schedule` (§4.4.6, merged) requires design and status rows for every subject passed to it. A record from the last round can omit footings that closed earlier (§4.6) | Lead, then owner | Decided (owner answer of 2026-11-26; amendment B-613): option (i) of Q23 also builds the design and status inputs to step 13 from each qualifying subject's last stored rows and the closure references (§4.6). Q25 defines which subjects qualify |
| Q25 | A footing closed at plan sizing has neither a design nor a status row. A footing closed by `WIDTH_TOO_SMALL` has a design row but no status row | Owner | Decided (owner answer of 2026-11-26; amendment B-613): pass only subjects with both rows to the merged schedule calc. Report early closures from their status and reason. Skip the schedule calc when every footing closed early |
| Q26 | The registry and CalcPort declare and store one fixed `output_kind` per calc (calcs §4.2, §4.5, §4.12) | Lead, then owner | Decided (owner answer of 2026-11-26; amendment B-613): use `harness.footing_rows_dims`, `harness.footing_rows_design` and `harness.footing_rows_status` with a shared implementation and fixed output kinds (§4.4.7). The existing framework serves all three |
| Q27 | The copied kinds have no issue or payload `complete` field | Lead, then owner | Decided (owner answer of 2026-11-26; amendment B-613): a requested id found in neither input is a programming error. Refuse it with `ContractError` `INVALID_ARGUMENT` and store no result. The footing kinds stay as merged |
| Q28 | Step 13 needs a filtered `harness.footing_subjects/1` reference for runs with both qualifying subjects and early closures. The merged schedule requires a stored reference under `require_refs` | Lead | Decided by the lead (amendment B-613), following the owner answer to Q26 of 2026-11-26: add `harness.footing_rows_subjects` to the shared implementation with fixed input and output kind `harness.footing_subjects/1`. Step 13 uses it to build the filtered subjects reference, and T7b registers and verifies it |
| FG-1 | Plan shapes other than square | — | `NotImplementedGap` |
| FG-2 | SAFE as the source of column loads: SAFE models carry no column frames (SAFE §4.4); loads would come from `harness.joint_loads/1` with a sign change | Owner | After SAFE L5 and L8, a calc from joint loads with the punching dimensions as column sizes |
| FG-3 | Footings cannot be resized in SAFE (SAFE SG-4); the cross-check uses the prepared geometry | Owner | Sasaah typed `csi_resize_area_rect` (SAFE Q5) |
| FG-4 | Pedestals and other reaction points | — | Q6 |
| FG-5 | Seismic categories D to F and special systems | Owner | ACI plan Q8, Q16 |
| A1 | **[added]** Kinds of §4.2; the code-pack route; calcs of §4.4 and §4.9; option `reduce_bar_spacing`; basis paths of §4.7; `footing_review` | Owner | Accept with this spec |
| C1 | Conflict: 12 §2 lists four options; flexure and minimum-steel failures need a fifth | Owner | Amend 12 §2's example when accepted |
| C2 | Conflict: engine §4.8 says the `CalcPort` serves code packs; calcs §4.12 defines harness calcs only | Owner | Settled by amendment B-405 (draft; the owner approves): calcs §4.12 item 4 serves code-pack checks through the route of §4.3, with the run-class rule of §4.12 |
| C3 | Conflict: spec 0013 §4.5 (merged first) defines the code-pack route with a fixed allowlist and a `batch` reference; §4.3 here used a registry lookup and inline `items` | Owner | Settled by amendment B-405 (draft; the owner approves): one route (§4.3, spec 0013 §4.5): the allowlist holds both workflows' ids, `run` takes `items` or `batch`; the first of plan 0013 T6 and plan T2 builds it, the other extends it; provenance `tool: "structural-codes"` in both |
| C4 | Conflict: for a check id outside the allowlist, spec 0013 AC13 (`tests/unit/calcs/test_code_pack_route.py::test_only_listed_checks`) expects `RegistryError`; AC4 and §4.3 here expect `ContractError` `NOT_FOUND`. Both specs map their tests to the same test file, so the second of plan 0013 T6 and plan T2 to merge cannot meet both without changing an existing expectation (A4) | Lead, then owner | Settled by amendment B-405 (draft; the owner approves): spec 0013 AC13, §4.5 and §6 now expect `NOT_FOUND`. Reason: it is the CalcPort's answer for an unknown calc id (calcs AC13 and §6), it reaches the block as a `ContractError` like every other CalcPort failure, and an exception of `structural_codes` is internal to the pack (the merged pack defines no `RegistryError`; its `Registry.get` answers `NOT_FOUND`) |

## 12. Needs local test

Listed in `docs/local-testing.md` by the plan; no host program runs in CI.

- L1. Sign and axes of ETABS joint reactions for the footing statics (ACI plan §4 "Reaction convention"); which joints
  report reactions.
- L2. Column section axes and `rotation_deg` values on a real model (§4.4.1 S5).
- L3. A full run on a copy of a real analysed model: the schedule against the engineer's own design (F1, F6), the read-only
  check (F3), timings (F7).
- L4. The SAFE stage on a prepared copy: load import, replace semantics and punching dimensions (SAFE L8), analysis,
  soil-pressure columns (SAFE L5, L6), base-reaction sign (SAFE L7), equilibrium.
- L5. The program comparisons PC-1 of the ACI plan §4 against SAFE.
- L6. Decision-model suggestions with a real provider after spike S-07 (spec 0009 Q1).
