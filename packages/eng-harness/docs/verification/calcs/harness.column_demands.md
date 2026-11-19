# harness.column_demands

- Calc id, version and content hash: `harness.column_demands` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0013 CW-G12)
- Method source: eng-harness spec 0013 section 4.4.2 (rules E1 to E6, amendment B-578, owner answer 2026-11-19), acceptance criteria AC6 and AC7; basis fields `materials.concrete_fc_MPa`, `materials.rebar_fy_MPa`, `columns.effective_length_factor_ratio`, `limits.ratio_limit_ratio` validated present, confirmed, finite and positive, and `limits.ratio_limit_ratio` at most the contract `Verdict.ratio_limit` default (04-tool-contract §5.1; same source as `structural_codes.inputs.CheckInputs.ratio_limit`), before emitting `{"$ref": "<basis id>#/fields/<path>/value"}` references.
- Constants: `ZERO` (0, Geometry: a bar area or cover distance is positive), `TWO` (`c_half = 2`, Geometry: two opposite faces per direction `b` and `h`, AF CS S1), `FOUR` (`c_corner = 4`, Geometry: four corner bars counted twice in `2*n_bars_b + 2*n_bars_h`, AF CS S1), `VERSION` (1, calc version); no engineering constant.
- Owner C items named by this verification record (spec 0013 §4.4.2, contract G-3, CW-G9 to CW-G11):
  1. Axial sign conversion `Pu_kN = -P_kN` (`host_local/1`: host axial tension positive; check axial compression positive; local test 3, CW-G10).
  2. Bending axis mapping `Mu_kNm = |M3_kNm|`, `Mu_other_kNm = |M2_kNm|` emitted only for symmetric rectangular sections (`b_mm == h_mm` and `n_bars_b == n_bars_h`); all other rectangular sections are marked `not_checked` `AXES_UNDECLARED` (`CW-G9`) until spec 0002 declares the local-axis mapping (local test 3).
  3. Unsupported length `lu_mm = length_mm` from `harness.column_selection/1` (centreline end-to-end distance, not less than clear height per ACI 318-14 6.2.3, safe side for `SHORT_COLUMN`; `CW-G11`).
  4. Total longitudinal reinforcement `Ast_mm2 = A_bar_mm2 * (2*n_bars_b + 2*n_bars_h - 4)` from `ColumnLayoutRequest` (`CW-G2`, AF CS S1) and `Ag_mm2 = b_mm * h_mm` from `model.sections/1`.

## Golden cases (`tests/data/golden/column_design/`)

Every case is synthetic and its hand derivation is written in the file; expected values are derived by hand from E1 to E6, never from running the code. Fixed basis result id `res_01KCD000000000000000000006` makes basis reference objects deterministic.

| File | Method rule | Hand derivation (summary) |
|---|---|---|
| `column-demands-compression-tension` | §4.4.2 E3 | `C1` (`C50`: `500x500`, `3x3`, `A_bar=500`, `Ag=250000`, `Ast=4000`); unselected `SLS1`, unselected `C9` and `load_case` `ULS1` filtered out; sorted E2 rows `(C1, ULS1, 0.0)` `P=-1200 -> Pu=1200.0`, `(C1, ULS1, 3000.0)` `P=0 -> Pu=0.0`, `(C1, ULS2, 0.0)` `P=250 -> Pu=-250.0`; 1 `longitudinal_reinforcement_limits` item. |
| `column-demands-square-uniaxial` | §4.4.2 E3 | Square `C1` (`400x400`, `4x4`, `A_bar=314`, `Ag=160000`, `Ast=3768`); `b_mm == h_mm` and `n_bars_b == n_bars_h`; `station 0.0` (`M2=0, M3=-60 -> Mu=60.0, Mu_other=0.0`) and `station 3500.0` (`M2=-15, M3=0 -> Mu=0.0, Mu_other=15.0`). |
| `column-demands-square-unequal-bars` | §4.4.2 E3 | Square `C1` (`500x500`, `n_bars_b=4 != n_bars_h=3`, `A_bar=500`, `Ast=5000`); `axial_flexure_uniaxial` omitted and `not_checked` holds `AXES_UNDECLARED` (`CW-G9`), while `max_axial_strength` and `longitudinal_reinforcement_limits` are emitted. |
| `column-demands-reinforcement-limits-per-column` | §4.4.2 E5 | `C1` (`400x400`, `3x3`, `Ag=160000`, `Ast=4000`, 2 load combos) and `C2` (`400x600`, `3x4`, `Ag=240000`, `Ast=5000`, 2 load combos, `AXES_UNDECLARED` `CW-G9`); `longitudinal_reinforcement_limits` emits 1 item per column (`station_mm: null, case: null`). |
| `column-demands-biaxial` | §4.4.2 E3 | Symmetric `C1` (`500x500`, `3x3`, `A_bar=400`, `Ast=3200`) with `M2=-35, M3=80` -> `Mu=80.0, Mu_other=35.0` emitted (check answers `NEEDS_ENGINEER` AF G-1). |
| `column-demands-not-checked` | §4.4.2 E2, E6 | E2 missing-combination check runs before E6 shape/layout exits: `C1` (`circular`) and `C2` (`other`) -> `FORCES_MISSING` and `SHAPE_NOT_CHECKED`; `C3` (no layout, no force rows) -> `FORCES_MISSING` and `LAYOUT_MISSING`; `C4` (missing `ULS2`) -> `FORCES_MISSING` with `ULS1` and `longitudinal_reinforcement_limits` emitted; `C5` (`400x600`) -> `AXES_UNDECLARED` (`CW-G9`). |
| `column-demands-layout-bar-area` | §4.4.2 E5 | `C1` (`400x400`, `3x3`) with `A_bar = 4.5 cm2` (`450.0 mm2` literal, never `$ref`) and `d_prime = 5.0 cm` (`50.0 mm`), `Ast = 450 * 8 = 3600.0 mm2`. |

## Boundary and contract tests

- `tests/contract/test_column_design_kinds.py`: `test_kind_fixtures` (updated `column_check_items*.json` with literals + `$ref` objects) and `test_check_item_inputs_are_ref_objects_or_literals` (field-aware validation of `n_bars_*` strict int, `"tied"`, `$ref` objects for `fc_MPa`/`fy_MPa`/`k_factor`/`ratio_limit`, finite numeric literals, rejection of bare `RefString`, bool, numeric strings, `"spiral"`, and non-finite floats).
- `tests/unit/calcs/test_column_demands.py`: `test_refusals` (non-`host_local/1` `sign_convention` via raw source at input validation -> `INVALID_ARGUMENT` `forces.sign_convention`, missing/unconfirmed basis -> `INVALID_ARGUMENT` `basis.fields.<path>`, zero puts), `test_axes_undeclared` (`b != h` and `n_bars_b != n_bars_h`), `test_items_validate_against_checks` (every item the fixture emits validates against real `aci318_14` `CheckInputs` under `InputPolicy(require_refs=True)` with exact §4.4.2 field sets), `test_registration_describe_and_trace`, `test_basis_value_bounds_and_types`, `test_layout_basis_values_conversion_and_errors` (optional layout basis paths under reserved `basis_in_*` input names), `test_layout_input_bounds_overflow_and_duplicate_sections`, `test_missing_refs_sections_spiral_sorting_and_zero_sign`, `test_ratio_limit_above_contract_default_is_refused`, and `test_layout_basis_path_does_not_collide_with_trace_step`.
- `tests/golden/column_design/test_golden.py`: golden suite (body plus hand-derived E3-E5 `expected_trace` for every `column-demands-*` case) and `COLUMN_DESIGN_CALCS` registration check.
- `tests/contract/test_calc_lock.py` and `tests/rules/test_calc_modules.py`: lock match, draft status, and FB005/import purity rules.

## Reviewer and date

Pending: an independent reviewer subagent (bootstrap mode), then the owner. Written 2026-11-19.

## Findings and open points

1. All values derived by `column_demands` or copied from `sections` and `layouts` are stored as literal JSON values in `harness.column_check_items/1` and traced as E3-E5 steps; confirmed basis fields (`fc_MPa`, `fy_MPa`, `k_factor`, `ratio_limit`) are `{"$ref"}` objects into `basis.design_basis/1` (amendment B-578; owner answer 2026-11-19).
2. Local test 3 (spec 0013 §12) is required before leaving `draft` to confirm ETABS `P` sign (`CW-G10`) and local-axis mapping for non-square sections (`CW-G9`).
