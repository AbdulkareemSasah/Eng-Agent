# Verification record for harness.footing_plan_size

- Calc id: `harness.footing_plan_size`
- Version: 1
- Content hash: `536e99afec44f1dd51d9faab7fda55c70a78e8825c438a37117048391768dc16`
- Status: draft under ADR-0028 §4. Independent verification and owner approval are pending.
- Method: [spec 0010 §4.4.2](../../specs/0010-design-isolated-footing.md), P0–P6 and AC7, as amended by B-567 (OQ-Q64).
  The sign and gross overburden terms come from [the bearing-pressure clause spec](../../../../structural-codes/docs/clauses/aci318_14/aci318_14.13_3_1_1.bearing_pressure_service.md), §3 and §4.1 S3.
- Constants: 1000 mm per m from the SI prefix milli, and zero from the physical bounds and sign tests in P1 and P2.
  Loads, allowable pressure, unit weights, dimensions and spacing come from references.

## Hand checks

The fixtures under `tests/data/golden/footing/plan-*.json` carry synthetic inputs and their derivations. P2 gives
`w = (500/1000)·24 + (1000/1000)·18 + 10 = 40 kPa`; the gross fixture uses `q_net = 200 − 40 = 160 kPa`.
For all dimensional outputs, `h = 500 mm` and `s = 200 mm` are read from the basis, both plan sides are equal,
the source is `calc`, and the depth and spacing flags are false.

| Fixture and row | Hand derivation and outcome |
|---|---|
| `plan-gross` F1 | Selected service FZ values are 576 and 400 kN. P3 gives 576/160 = 3.6 m². The 200 mm grid brackets it with 1.8² = 3.24 and 2.0² = 4 m². P4 gives 2000 mm. |
| `plan-gross` F2 | 640/160 = 4 m² = 2.0². P4 keeps the exact 2000 mm multiple. |
| `plan-gross` F3 | 64/160 = 0.4 m² lies between 0.6² and 0.8². The 800 mm area grid size is below 900 mm, so P4 gives 5 × 200 = 1000 mm. |
| `plan-gross` F4 | 1600/160 = 10 m² lies between 3.0² = 9 and 3.2² = 10.24. The 3200 mm trial exceeds 2450 mm, so P5 gives floor(2450/200) × 200 = 2400 mm, `LIMIT_REACHED`, with `plan_at_max` true. |
| `plan-gross` F5, F6, F7 | F5 has zero FZ despite another positive service row, and F7 has negative FZ. Both give `UPLIFT`. F6 has only a factored row and gives `NO_SERVICE_LOAD`. P6 gives ceil(900/200) × 200 = 1000 mm for all three. |
| `plan-net` | P0 takes the declared net allowable to `NET_ALLOWABLE`. P6 gives 5 × 200 = 1000 mm. |
| `plan-overburden`, `plan-overburden-equal` | 39 − 40 = −1 kPa and 40 − 40 = 0 kPa both satisfy P2. Each gives `OVERBURDEN`, with 5 × 200 = 1000 mm by P6. |
| `plan-no-positive-multiple` | floor(199/200) = 0, so P5 refuses the basis with `OUT_OF_RANGE`. |
| `plan-equal-projection` | P0 reaches the declared FG-1 gap and returns `NOT_IMPLEMENTED`. |

The Hypothesis test independently checks grid alignment, the minimum, the squared area at the returned side and
one increment below it, and monotonicity under increased compression. Targeted tests also pin exact trace values
and references, basis error details, fractional grid spacing, and a trial side exactly equal to the maximum.

The sizing step uses FZ only. Spec 0010 P3 assigns moment and full-contact checks to the bearing check. A P6
dimension is carried with `NEEDS_ENGINEER` and closes at the block's first step as defined in §4.6.

## Reviewer and date

Owner review and date are pending. An independent review was conducted on 2026-11-19.

## Findings and open gaps

- N2: The specification does not explicitly list ZERO as a constant or state all basis positivity bounds; clarification is pending.
- N3: The specification does not resolve minimum plan dimension exceeding the maximum; owner decision is pending.
- N4: Reason precedence and the ordering of shape and kind checks are not fixed by the specification.
