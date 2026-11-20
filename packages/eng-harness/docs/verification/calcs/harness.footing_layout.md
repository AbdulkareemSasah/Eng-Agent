# Verification record: harness.footing_layout

- Calc id: `harness.footing_layout`
- Version: 1
- Content hash: `eaa22be73677d1f31a1d9890dc5d5451688e6e3f60325585c9a143fb0d119ba3` (from `calcs.lock.json`; any later change to the calc or to a module it imports changes it and the owner re-verifies)
- Status: draft (not approved; ADR-0028 section 4: no entry in `approvals.yaml`)
- Method source: eng-harness spec 0010 section 4.4.3 (rules L1 to L5, amendment B-568 / OQ-Q60, OQ-Q63), acceptance criteria AC8 and AC12; basis fields `reinforcement.bar_diameter_mm`, `reinforcement.bottom_layer`, `durability.cover_footing_mm`, `foundation.reaction_point` read as spec 0003 section 4.4 states (confirmed, exact unit, range)
- Constants: `ZERO_MM` (0 mm, Geometry), `ZERO_COUNT` (0, Geometry), `ZERO_AREA` (0.0 mm2, Geometry), `ONE` (1, Geometry), `TWO` (2, Geometry), `THREE` (3, Geometry), `FOUR` (4, Geometry), `PI` (math.pi, Mathematical constant, area of a circle), `MAX_SAFE_INT` (9007199254740991, RFC 8785 3.2.2.3 / `eng-contract` `canonical.py` maximum exact I-JSON integer `2^53 - 1`); no engineering number.

## Golden cases

Files `tests/data/golden/footing/layout-*.json`, test `tests/golden/footing/test_layout.py::test_golden_cases`. Every case is synthetic and its hand derivation is written in the file; expected values were derived by hand from L1 to L5, never taken from the calc. Fixtures store the exact independently derived pi coefficients (`As_x_pi_coeff`, `As_y_pi_coeff`), and `test_golden_cases` compares `As_x_mm2` and `As_y_mm2` against `coeff * math.pi` within the L2 binary64 roundoff bound `4u = 2 * sys.float_info.epsilon = 2^-51` (exact `0.0` when `coeff == 0`), while checking all counts, spacings, depths, covers, reaction heights, statuses, and input fields for exact equality.

| File | Method rule | Hand derivation (summary) |
|---|---|---|
| `layout-x-bottom-top` | L1 to L5 | `db = 16`, `c = 75`, `x_bottom`, `top_of_footing`; `J1` (`2166x2566`, `h=500`, `s=200`): `span_x = 2400` (exact multiple `12*200` -> `n_x = 13`, `s_x = 200.0`, `As_x = 832*pi`), `span_y = 2000` (exact `10*200` -> `n_y = 11`, `s_y = 200.0`, `As_y = 704*pi`), `d_x = 417.0`, `d_y = 401.0`, `d = 409.0`, `reaction_height = 500.0`; `J2` (`1966x1766`, `h=400`, `s=250`, `LIMIT_REACHED`): `span_x = 1600` (`n_x = ceil(6.4)+1 = 8`, `s_x = 1600/7`, `As_x = 512*pi`), `span_y = 1800` (`n_y = ceil(7.2)+1 = 9`, `s_y = 225.0`, `As_y = 576*pi`), `d_x = 317.0`, `d_y = 301.0`, `d = 309.0`, `LIMIT_REACHED` preserved |
| `layout-y-bottom-base` | L1 to L5 | `db = 32`, `c = 50`, `y_bottom`, `base_of_footing`; `J1` (`1332x1932`, `h=450`, `s=200`, `source=engineer`): `span_x = 1800` (`n_x = 10`, `s_x = 200.0`, `As_x = 2560*pi`), `span_y = 1200` (`n_y = 7`, `s_y = 200.0`, `As_y = 1792*pi`), `y_bottom` swaps `d_y = 384.0`, `d_x = 352.0`, `d = 368.0`, `reaction_height = 0.0` |
| `layout-span-below-and-multiple` | L1 to L5 | `db = 16`, `c = 50`, `x_bottom`, `top_of_footing`; `J1` (`316x200`, `s=200`): `span_x = 84 < s` -> `n_x = 2`, `s_x = 84.0`, `As_x = 128*pi`, `span_y = 200 == s` -> `n_y = 2`, `s_y = 200.0`, `As_y = 128*pi`; `J2` (`517x317`, `s=200`): `span_x = 201` (just above `s` -> `n_x = 3`, `s_x = 100.5`, `As_x = 192*pi`), `span_y = 401` (just above `2*s` -> `n_y = 4`, `s_y = 401/3`, `As_y = 256*pi`) |
| `layout-span-zero-and-negative` | L1, L3 to L5 | `db = 16`, `c = 75`, `x_bottom`, `base_of_footing`; `J1` (`span_x = span_y = 0`), `J2` (`Lx=466`, `Ly=120`, `span_x = -46 < 0`, `span_y = 300 > 0` where calculated `s_y` would be `150 != 200`), `J3` (`span_x = span_y = -66 < 0`) all give `NEEDS_ENGINEER` (`WIDTH_TOO_SMALL`) before computing spacing in either direction, with informative `n_x = n_y = 0`, `s_x = s_y = s_mm`, `As_x = As_y = 0.0` |
| `layout-depth-out-of-range` | L3 | `db = 20`, `c = 75`, `h = 105` (`d_upper = 105 - 75 - 30 = 0 <= 0`) refuses with `ContractError` `OUT_OF_RANGE`, field `dims` |

## Boundary and property tests

- `tests/property/test_footing_layout.py::test_spacing_bound`: Hypothesis check that for every valid layout (`span > 0`, `d_upper > 0`), `n >= 2`, actual spacing `<= s`, either `n == 2` or `span / (n - 2) > s`, and `As` grows strictly with bar count.
- `tests/golden/footing/test_layout.py`: trace inputs, constants (`pi`, `max_safe_int`, geometric constants) and step counts; all four basis fields checked for missing, unconfirmed, wrong unit, non-number, unsupported choice, and out-of-range (`bar_diameter_mm <= 0`, `cover_footing_mm < 0`); `cover = 0` accepted; L3 depth boundary (`104`, `105` refused `OUT_OF_RANGE` `dims` for both `x_bottom` and `y_bottom`, `106` accepted); `WIDTH_TOO_SMALL` in Y direction only (`Lx=166, Ly=466`) before computing spacing in either direction and preservation of non-`WIDTH_TOO_SMALL` row status; unknown footing id in `dims`, empty `dims`, missing `meta.refs`; and `HarnessCalcPort` execution storing `harness.footing_design/1` with `draft=True`, literal refusal, bar-count limit refusal (`400 mm / 2^-45 mm` and `2^53 - 1` / `2^53` exact boundary), large finite area without intermediate overflow (`db = 8e153 mm`, `n = 2`), and overflow refusal (`db = 1.5e154 mm`, `OUT_OF_RANGE` `dims`).
- `tests/unit/footing/test_calcs_registered.py`: registration, metadata, lock entry, this record, cited constants only, and public module importability.

## Reviewer and date

Pending: an independent reviewer subagent (bootstrap mode), then the owner. Written 2026-11-18.

## Findings and open points

1. By amendment B-568 (OQ-Q60, OQ-Q63), `WIDTH_TOO_SMALL` (`NEEDS_ENGINEER`) applies at row level before computing actual spacing in either direction whenever `span_x <= 0` or `span_y <= 0`; both directions carry informative numbers `n_x = n_y = 0`, `s_x = s_y = s_mm`, and `As_x = As_y = 0.0` (consistent with `DesignRow` positive-spacing constraints), and the block closes the footing before any code-pack check runs.
2. When both spans are positive (`span_x > 0` and `span_y > 0`), the row preserves the incoming `DimRow.status` and `DimRow.reason` (such as `OK` or `LIMIT_REACHED`).
3. Every `DimRow.id` in `dims.footings` must be present in `subjects.subjects` (`INVALID_ARGUMENT`, field `dims` otherwise); `dims.footings` may be a subset of `subjects.subjects` (closed footings are omitted in later rounds).
4. Output representability is checked at the calc boundary: bar counts exceeding `2^53 - 1` (`eng_contract.canonical._MAX_SAFE_INT`) and binary64 overflow or positive-field underflow are refused with `ContractError` `OUT_OF_RANGE`, `field="dims"`. Steel areas are computed in exact `Fraction` and converted once to binary64 so large finite areas such as `db = 8e153 mm`, `n = 2` succeed without intermediate overflow.
