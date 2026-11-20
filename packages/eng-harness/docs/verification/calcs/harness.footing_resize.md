# Verification record for harness.footing_resize

- Calc id: `harness.footing_resize`
- Version: 1
- Content hash: `43c83593a8e420c7e2167698abf4a087b210af0378d2cbf31c661cd31c5727a1`
- Status: draft under ADR-0028 §4. Independent verification and owner approval are pending.
- Method: [spec 0010 §4.4.4](../../specs/0010-design-isolated-footing.md), R1–R4 and AC9, as amended by B-567 (OQ-Q64).
- Constants: zero from the plan-from-zero counting rule; one from the R1 next-multiple step; status strings `OK`,
  `LIMIT_REACHED`, `OUTSIDE_BASIS_BOUNDS`, `OFF_INCREMENT` and source `engineer` from §4.4.4 / Q13 / Q17; version 1.
  Increments and bounds come from the nine confirmed basis fields.

## Hand checks

The fixtures under `tests/data/golden/footing/resize-*.json` carry synthetic inputs and their derivations. The shared
basis of the action and limit cases is `plan_increment = 200 mm`, `depth_increment = 50 mm`,
`spacing_increment = 25 mm`, plan bounds `1000..3000 mm`, depth bounds `400..800 mm`, spacing bounds `100..300 mm`.

| Fixture and row | Hand derivation and outcome |
|---|---|
| `resize-actions` F1 | R1: `L = 2000 = 10·i`; `L' = (⌊2000/200⌋ + 1)·200 = 11·200 = 2200 mm`. |
| `resize-actions` F2 | R2: `h' = 500 + 50 = 550 mm`. |
| `resize-actions` F3 | R3: `s' = 200 − 25 = 175 mm`. |
| `resize-actions` F4 | Action `none`: sizes unchanged. |
| `resize-actions` F5 | R1 from `L = 2100` (between `10·i` and `11·i`): `L' = (⌊2100/200⌋ + 1)·200 = 2200 mm`. |
| `resize-limits` F1 | Next plan `3200 > 3000`: unchanged, `LIMIT_REACHED`, `plan_at_max`. |
| `resize-limits` F2 | Next depth `850 > 800`: unchanged, `LIMIT_REACHED`, `depth_at_max`. |
| `resize-limits` F3 | Next spacing `75 < 100`: unchanged, `LIMIT_REACHED`, `spacing_at_min`. |
| `resize-limits` F4 | R1 from `2800`: `L' = (⌊2800/200⌋ + 1)·200 = 3000 ≤ 3000`, status `OK`. |
| `resize-engineer-ok` | R4: `L = 2000`, `h = 500`, `s = 200` inside bounds and on the plan grid; `source = engineer`, status `OK`. |
| `resize-engineer-off-increment` | R4: `L = 2100` inside bounds, not a multiple of `200`; status `OFF_INCREMENT`. |
| `resize-engineer-outside-plan-high/low` | R4: `L = 3600 (=18·200) > 3000` and `L = 800 < 1000`; status `OUTSIDE_BASIS_BOUNDS` (each side). |
| `resize-engineer-outside-depth-high/low` | R4: `h = 900 > 800` and `h = 300 < 400`; status `OUTSIDE_BASIS_BOUNDS`. |
| `resize-engineer-outside-spacing-high/low` | R4: `s = 350 > 300` and `s = 50 < 100`; status `OUTSIDE_BASIS_BOUNDS`. |
| `resize-engineer-outside-and-off` | R4: `L = 3500` outside and off-grid (`17·200 = 3400`, `18·200 = 3600`); status `OUTSIDE_BASIS_BOUNDS`, reason `OFF_INCREMENT`. |

Every expected value was derived by hand from §4.4.4; none was taken from running the calc.

## Reviewer and date

Owner review and date are pending.

## Findings and open gaps

None open for this draft calc beyond the owner verification that every draft calc requires.
