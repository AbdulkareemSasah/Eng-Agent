<!-- The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text. -->

**Status of this copy:** the writer handoff of B-484 (pull request 330, merged): the inventory of the basis path renames, kept for the next lead. Section 2d is the table of the protected ACI clause documents that the owner edits or approves (BUILD-STATUS section 6).

# B-484 writer handoff (documents amendment DOC.BASISNAMES)

Branch `docs/b484-remaining-basis-paths-with-suffixes`, worktree `<worktrees>/b484`, base a5e05d9, head a4def34
(not pushed). Commits: 33ced7b docs(eng-harness), 960a2ba docs(structural-codes), a4def34 docs(eng-harness) (wraps the
new lines). Only trailer: `Assisted-by: anthropic/claude`. Note: origin/build/v1 moved to e73816e (B-113, B-466) while
I worked; neither touches a spec or plan or a renamed path, so the integrator's merge should be clean.

## 1. The rule (from merged text and code)

- Contract spec 0001 §4.7.2 and `eng_contract/kinds/basis.py` (`BasisPath`, B-464): lowercase segments, at least two;
  the last may end with one §4.7.2 suffix written as the table writes it (`_mm`, `_mm2`, `_mm3`, `_mm4`, `_kN`, `_kNm`,
  `_MPa`, `_kN_m`, `_kPa`, `_kN_m3`, `_kg`, `_deg`, `_s`, `_C`, `_m_s2`, `_ratio`). `DesignBasis` checks the unit only
  when the last segment has a suffix; a path with no suffix is accepted by the contract with any unit.
- The refusals come from the harness: spec 0004 AC4 / `templates/_model.py` `_walk` (an entry's unit must equal the
  canonical unit of its key suffix, null when the key has none: a unit on an unsuffixed key is `unit_mismatch`) and
  AC21 / `basis/_fields.py` (a `quantity` FieldSpec needs `kind_for_field(last segment)` not None and `unit` equal to
  its canonical unit; `count`, `choice`, `text` carry no unit).
- So every `quantity` path must end with the suffix of its unit; counts, choices (enums), text and flags carry none.
  A dimensionless ratio or factor declared as a quantity with unit `1` takes `_ratio` (the only suffix of kind
  `dimensionless`; B-467's reading, `kind_for_field("x_ratio")` is `dimensionless`, `kind_for_field("effective_length_factor")`
  is None and so cannot be a quantity FieldSpec).
- Harness rule wider than the contract (confirmed): `_SEGMENT = [A-Za-z_][A-Za-z0-9_]*` in `_model.py` and `_fields.py`
  accepts capitals in any segment (`Compare.stress_MPa`, `compare.Stress_MPa`, `compare.stress_MPa.max`) and a leading
  underscore; template ask paths and keys may be a single segment. Spec 0004 §4.5 already says `path: BasisPath` and
  Q1 already called alignment a follow-up, so narrowing is code catching up with the spec: new templates plan T11.

## 2. Inventory (every basis path named under packages/*/docs, src, tests)

Line numbers are at head a4def34 for specs and plans, at base for code, tests and protected documents.

### 2a. Specs and plans: renamed (kind and unit stated in the documents)

| Old path | Kind, unit (where stated) | Named at (head) | New name |
|---|---|---|---|
| `checks.equilibrium_relative_tolerance` | quantity, 1 (spec 0010 §4.7 table) | spec 0010:179, 431, 548 | `checks.equilibrium_relative_tolerance_ratio` |
| `columns.effective_length_factor` | quantity, `1` (spec 0013 Table A) | spec 0013:268, 429; SC plan 0004:249 (Q5) | `columns.effective_length_factor_ratio` |
| `durability.cover_footing` | quantity, mm (0010 table) | spec 0010:312, 418; SC plan 0002:438 | `durability.cover_footing_mm` |
| `foundation.allowable_bearing_pressure` | quantity, kPa | spec 0010:290, 410; SC plan 0002:438 | `foundation.allowable_bearing_pressure_kPa` |
| `foundation.soil_unit_weight` | quantity, kN/m3 | spec 0010:290 (`.`-shorthand), 412; SC plan 0002:438 | `foundation.soil_unit_weight_kN_m3` |
| `materials.concrete_unit_weight` | quantity, kN/m3 | spec 0010:291, 412; SC plan 0002:438 | `materials.concrete_unit_weight_kN_m3` |
| `foundation.soil_depth_above_footing` | quantity, mm | spec 0010:291, 413; SC plan 0002:438 | `foundation.soil_depth_above_footing_mm` |
| `foundation.surcharge` | quantity, kPa | spec 0010:291, 414; SC plan 0002:438 | `foundation.surcharge_kPa` |
| `materials.concrete_fc`, `materials.rebar_fy` | quantity, MPa (0010 table, 0013 Table A) | spec 0010:415; spec 0013:267, 427, 428; SC plan 0002:438 | `materials.concrete_fc_MPa`, `materials.rebar_fy_MPa` |
| `foundation.min_depth`, `.max_depth`, `.depth_increment` | quantity, mm | spec 0010:291, 328-329, 422, 543 (Q14) | `..._mm` each |
| `foundation.min_plan_dimension`, `.max_plan_dimension`, `.plan_increment` | quantity, mm | spec 0010:108 (AC9), 291-292, 328, 420 | `..._mm` each |
| `foundation.min_clear_distance` | quantity, mm | spec 0010:348, 350, 424 | `foundation.min_clear_distance_mm` |
| `reinforcement.bar_diameter` | quantity, mm | spec 0010:312, 425 | `reinforcement.bar_diameter_mm` |
| `reinforcement.max_spacing`, `.min_spacing`, `.spacing_increment` | quantity, mm | spec 0010:292-293, 329-332, 426 | `..._mm` each |
| `modeling.section_increment` | quantity, `mm` (spec 0003 §4.4 table; 0013 Table A) | spec 0003:340, 626; spec 0010:47; spec 0013:430 | `modeling.section_increment_mm` |
| `modeling.section_rounding_allowance` | example field, `mm` (spec 0003 Q14) | spec 0003:846 | `modeling.section_rounding_allowance_mm` |
| `mapping.offset_x`, `_y`, `_z` | float, mm (spec 0011 §4.11, table) | spec 0011:520, 577, 657; spec 0013:433-434; plan 0011:409 | `mapping.offset_x_mm`, `_y_mm`, `_z_mm` |

Bare last-segment references in spec 0010 method text that name these fields were renamed with them (AC9
`plan_increment_mm`, `h = min_depth_mm`, `s = max_spacing_mm`, R2 `depth_increment_mm`, R3 `spacing_increment_mm`,
"counted from `min_depth_mm`", `min_clear_distance_mm`). Formula symbols of clause formulas were left (P2
`w = h·γc + soil_depth·γs + surcharge`, P4/P5 `min_plan`, `max_plan`, `i`), as were `mapping.offset_*` globs (spec 0011
AC29 line 223, plan 0011 T12 line 384), which still match the new names.

Text added besides names: spec 0010 §4.7 one sentence (quantity paths carry the suffix; the clause specs keep the old
names until the owner renames them); spec 0013 Table A source cell and C1 answer (done by B-484, clause specs keep the
old names); SC plan 0002 Q2 answer (same note); spec 0004 Q1 and plan 0004 §1 (alignment is plan T11).

### 2b. Conforming, not renamed

- Already suffixed (B-417, B-467): `compare.length_mm`, `compare.angle_deg`, `compare.stress_MPa`,
  `compare.unit_weight_kN_m3`, `compare.line_load_kN_m`, `compare.area_load_kPa`, `compare.dimensionless_ratio`,
  `checks.readback_relative_tolerance_ratio`, `limits.ratio_limit_ratio`, `limits.drift_ratio`, the eight `bounds.*`,
  `modeling.merge_tolerance_mm`, `modeling.snap_tolerance_mm`, `modeling.section_rounding_increment_mm` (spec 0004 §4.5),
  `materials.concrete.<grade>.fc_MPa` (spec 0004 §4.2), `columns.required_d_mm` (column kind fixtures).
- Choices (no suffix): `design.code_pack`, `design.run`, `seismic.design_category`, `seismic.special_system`,
  `foundation.allowable_bearing_kind`, `foundation.plan_shape`, `foundation.reaction_point`, `materials.concrete_class`,
  `materials.rebar_coating`, `reinforcement.bottom_layer`, `modeling.section_rounding`, `safe.cross_check`.
- Counts: `report.top_n`, `attempts.*` (cycles, change_set, approval_void, footing_rounds, cases, column_inputs).
- Text: `connection.design_code` (spec 0014 AC15, table: str 1 to 100).
- Not basis paths: `limits.max_task_lines` (gate setting), `info.*`, `ctx.*`, module names.

### 2c. Merged code and test data

| Path | Where | Kind, unit | Conforms | Action |
|---|---|---|---|---|
| `compare.angle` (B-467 old name) | eng-harness `src/eng_harness/calcs/footing/subjects.py` 26, 29, 36; `tests/golden/footing/test_subjects.py` 51, 69, 121; `tests/data/golden/footing/subjects-*.json` (basic 265, zero-tolerance 256, wide-tolerance 157, no-reactions 76, angle-tolerance 421, excluded 374) | quantity, deg | no | footing plan T3b → `compare.angle_deg` |
| `#/fields/compare.length` (example ref) | `tests/data/kinds/calcs/model_diff.json` 72, `readback_check.json` 73; `tests/data/snapshots/report/report.html`, `sections.html` | quantity, mm | no | T3b → `compare.length_mm` |
| `loads.floor_dead_kpa` | `tests/unit/edit_cycle/test_change_set.py` 21 (value of `area_uniform_load.q`, an area load, spec 0007 §4.3.1) | quantity, kPa | no (`kpa` is not a suffix) | T3b → `loads.floor_dead_kPa` |
| `foundation.allowable_bearing_pressure` | structural-codes `aci318-14/tests/unit/test_bearing.py` 132 (synthetic `DesignBasis`, unit kPa; the contract accepts it, no harness rule runs) | quantity, kPa | no | owner/lead question O-2 below; no task |
| `foundation.allowable_bearing_kind` | same file 133, 186; docstrings `aci318_14/checks/bearing_pressure.py` 33, `development_length.py` 66 (`materials.rebar_coating`), `_common.py` 70 (`materials.concrete_class`) | choice | yes | none |
| Synthetic rule-test paths (eng-contract `tests/contract/test_kinds.py`, `tests/data/kinds/basis.design_basis-1/*`; eng-harness `test_template_*`, `test_basis_*`, `test_ctx_basis.py`, `decisions/test_rules.py`, `rules/fixtures`, `workflow/test_invariants.py`, `fixtures/templates/synthetic-full-0.1.0.json`) | e.g. `materials.cover_mm`, `loads.live_kPa`, `bounds.w_kN_m`, `limits.bearing_ratio`, `limits.other_ratio`, `limits.cover_mm`, `analysis.stories` (count), `analysis.method`/`mode` (choice), `drawing.title` (text), `code.edition`, `loads.risk_category`, `site.seismic_class`, `limits.n` (count) | as declared | yes, except the deliberately invalid cases (`compare.stress_Mpa`, `compare.Stress_MPa`, `limits.drift` with unit 1, `limits.drift_mm` with unit 1, `limits.wrong_unit_MPa`, `analysis.störies`, ...) that test the rules | none (T11 may rename synthetic keys its narrower rule refuses) |
| `CHANGELOG.md` line 16 (`compare.angle`) | history | | | not edited (history) |

### 2d. Protected engineering content: owner queue (not edited)

| File (packages/structural-codes/docs/clauses/aci318_14/) | Line | Old | Proposed |
|---|---|---|---|
| aci318_14.13_3_1_1.bearing_pressure_service.md | 56 | `foundation.soil_depth_above_footing` | `foundation.soil_depth_above_footing_mm` |
| same | 57 | `materials.concrete_unit_weight`, `foundation.soil_unit_weight` | `..._kN_m3` each |
| same | 58 | `foundation.surcharge` | `foundation.surcharge_kPa` |
| same | 59 | `foundation.allowable_bearing_pressure` | `foundation.allowable_bearing_pressure_kPa` |
| same | 110 | `limits.ratio_limit` (B-467 queue entry, still open) | `limits.ratio_limit_ratio` |
| aci318_14.25_4_2_3.development_length_bottom_bars.md | 50 | `durability.cover_footing` | `durability.cover_footing_mm` |
| same | 52 | `materials.concrete_fc`, `materials.rebar_fy` | `materials.concrete_fc_MPa`, `materials.rebar_fy_MPa` |
| aci318_14.22_4_2_1.max_axial_strength.md | 66 | fc, fy as above | as above |
| aci318_14.22_4_1_1.axial_flexure_uniaxial.md | 71 | fc, fy | as above |
| aci318_14.22_5_5_1.one_way_shear.md | 51 | `materials.concrete_fc` | `materials.concrete_fc_MPa` |
| aci318_14.8_6_1_1.min_flexural_reinforcement.md | 42 | `materials.rebar_fy` | `materials.rebar_fy_MPa` |
| aci318_14.13_2_7_1.flexure_at_column_face.md | 53 | fc, fy | as above |
| aci318_14.22_6_5_2.punching_shear.md | 54 | `materials.concrete_fc` | `materials.concrete_fc_MPa` |

Verification record of merged code: `packages/eng-harness/docs/verification/calcs/harness.footing_subjects.md` lines 5
(hash), 7, 8, 34 (`compare.angle`): changed by footing plan T3b, not by a documents PR (GC010).
SBC clause map (`sbc304_2018/clause-map.md`) names no basis path.

## 3. New plan tasks (code follow-ups)

- Footing plan 0010 **T3b** "Merged harness.footing_subjects and test data read the suffixed basis names": files
  CHANGELOG, `calcs/footing/subjects.py`, `calcs/calcs.lock.json`, the verification record, `test_subjects.py`,
  `subjects-*.json`, the two kind fixtures, the two report snapshots, `test_change_set.py`; budget 40 counted lines
  (estimate: subjects.py 6, lock 2, record about 8, CHANGELOG 2), 1 session; tests_first the three `test_subjects.py`
  tests that the rename makes fail at the base (`test_golden_cases`, `test_trace_records_inputs_constants_and_counts`,
  `test_missing_basis_field_is_refused`); covers AC6; depends_on T3; needs eng-contract T19 (merged). Text says the
  lock entry and the hash line are regenerated, the record stays draft, the owner re-verifies; fixtures, snapshots and
  the change-set test go in a later commit (they pass at the base, TF004).
- Templates plan 0004 **T11** "Template keys and FieldSpec paths follow the contract basis path rule": files CHANGELOG,
  `templates/_model.py` (CODEOWNERS-protected path), `basis/_fields.py`, `test_template_model.py`,
  `test_template_check.py`, `test_basis_fields.py`; budget 60, 1 session; tests_first `test_extra_keys_forbidden` and
  `test_field_spec_rules` (new refusals added there fail at the base); covers AC3, AC21; depends_on T5. Reasons stay
  as merged (`unknown_key`, `value_invalid` for an ask path, `field_invalid`).
- Not measured by a trial: editing test files to check that the tests_first fail at the base was refused by this
  session's permission classifier (outside the documents scope), so the failure is reasoned, not run.

## 4. Branches written before this rename that use an old name (read-only check)

- b395 (footing plan T4, `plan_size.py` 26-37, 166-175; `resize.py` 24-32; golden and verification files): uses
  `foundation.allowable_bearing_pressure`, `.soil_unit_weight`, `materials.concrete_unit_weight`,
  `foundation.soil_depth_above_footing`, `.surcharge`, `.min_depth`, `.min_plan_dimension`, `.max_plan_dimension`,
  `.plan_increment`, `.depth_increment`, `.max_depth`, `reinforcement.max_spacing`, `.min_spacing`,
  `.spacing_increment` → all need the `_mm` / `_kPa` / `_kN_m3` names of spec 0010 §4.7.
- b396 (footing plan T5, `layout.py` 29-32 and its tests and data): `reinforcement.bar_diameter`,
  `durability.cover_footing` → `_mm`; also `reinforcement.max_spacing` in its data.
- b281 (column plan G.T2 `column_select.py` 4, 27, 29, 108 and tests): `compare.length` (the B-467 old name;
  covered by the playbook standing note) → `compare.length_mm`.
- b460: none.

## 5. Verification

- `uv run eng-gate check --package eng-harness --skip mutation`: `check: pass` (log
  <lead>/logs/b484-gate-harness.log; notice RT001 on tools/eng-dev-gate noqa count, unrelated).
- `uv run eng-gate check --package structural-codes-aci318-14 --skip mutation`: `check: pass`
  (<lead>/logs/b484-gate-aci.log). Both SC plans touched (0002, 0004) belong to that member.
- Docs rules with the gate library (`spec_plan_findings`, base a5e05d9, head a4def34): no finding, so GC005 (front
  matter valid, task cap 400), GC010 (only specs and plans, two packages allowed) and GC016 (every criterion covered)
  hold. `eng-gate risk-floor --base a5e05d9 --head HEAD` with body `Risk: r0`: pass. TF008 does not apply to a
  documents PR; the new tasks list as tests_first only tests that the rename makes fail at the base.
- Grep of specs and plans for every old quantity path: only spec 0013 C1's problem statement (line 552) keeps the old
  names, on purpose.
- Counted lines: 171 (120 added, 51 deleted), 10 files, all specs and plans.

## 6. Questions for the owner or lead (not decided here)

- O-1. Calcs spec §4.2: "a change of output for the same input is a new version". The rename makes the footing calc
  refuse a basis that holds `compare.angle`. T3b keeps version 1 (draft, never approved) and says the lead amends T3b
  if the owner rules that this needs version 2.
- O-2. `aci318-14/tests/unit/test_bearing.py` line 132 uses `foundation.allowable_bearing_pressure` (kPa) in a synthetic
  record. Renaming it is cosmetic (the contract accepts it, no harness rule runs there) and a test-only task cannot
  pass test-first (TF004/TF010). Fold it into the next aci318-14 task that touches the file, or leave it?
- O-3. Owner queue: the clause document renames of 2d (with B-467's line 110 entry).
