# Verification record: harness.footing_schedule

- Calc id: `harness.footing_schedule`
- Version: 1
- Content hash: `b0e55b805078f3f65f1805e04a389b191ab72bfe60b147962003efa1913e9218` (from `calcs.lock.json`; any later change to the calc or to a module it imports changes it and the owner re-verifies)
- Status: draft (not approved; ADR-0028 section 4: no entry in `approvals.yaml`)
- Method source: eng-harness spec 0010 section 4.4.6 (schedule assembly and clearance), acceptance criterion AC11; basis field `foundation.min_clear_distance_mm` (confirmed, in mm by the unit suffix of its path, value >= 0)
- Constants: three `Cited`: the divisor 2 of "half the length to each side" (Geometry, plans centred on their joints, BP 2), the length 0 mm (Geometry; the lower bound of the clear distance) and the calc version 1. The clear distance is the basis field, never a literal. No engineering number.

## Golden cases

Files `tests/data/golden/footing/schedule-*.json`, test `tests/golden/footing/test_schedule.py::test_golden_cases`. Every case is synthetic and its derivation is written in the file; the expected values were derived by hand, not taken from the calc. Layout fields of the design rows are placeholders that this calc does not read.

| File | Method rule | Hand derivation (summary) |
|---|---|---|
| `schedule-overlap` | 4.4.6 overlap | 2000 mm squares at (0, 0) and (1500, 500): gx = 1500 - 2000 = -500, gy = 500 - 2000 = -1500, both negative: overlap, both marked; a third footing 10000 mm away is not |
| `schedule-corner-below`, `-at`, `-above` | 4.4.6 both gaps positive | Squares at (0, 0) and (2300, 2400): gx = 300, gy = 400, squared distance 250000 (distance 500). Clear distance 501: below, both marked; 500: equal, no conflict; 499: above, no conflict |
| `schedule-edge-y-at`, `-y-below` | 4.4.6 one gap negative | (0, 0) and (1000, 2600): gx = -1000, gy = 600, distance 600; clear 600: none; 601: both marked |
| `schedule-edge-x-at`, `-x-below` | 4.4.6 one gap negative | (0, 0) and (2600, 1000): gx = 600, gy = -1000, distance 600; clear 600: none; 601: both marked |
| `schedule-rectangles` | 4.4.6 per axis | Lx and Ly differ: gx = 2500 - (3000 + 1000)/2 = 500, gy = 1800 - (1000 + 2000)/2 = 300, squared 340000 (583.09 mm, not an integer); clear 584 (341056) is above: both marked. With the lengths swapped the distance would be 1000 and there would be no conflict |
| `schedule-zero-clear-distance` | 4.4.6 touching, overlap | Clear 0: corners that touch (gaps 0 and 0) are no conflict; an overlap (gaps -100 and -100) is |
| `schedule-assembled` | 4.4.6 schedule | Four footings on a line; neighbour is the closest conflicting one (J2 names J3: 200 before 300); reasons in order and without repeats (design reason, closure reasons, CLEARANCE); an already NEEDS_ENGINEER design keeps its reason; a LIMIT_REACHED design becomes NEEDS_ENGINEER with reason CLEARANCE and keeps its flags and its engineer source; families, ratios and closures from the status rows; verdict-set and decision references per footing, in the order given, repeats dropped |

## Other tests

`test_schedule.py`: the trace (inputs with references, the three cited constants, the five steps with their `uses`, outputs) and the counts of overlapping and close pairs; the neighbour tie rule (smaller id) and overlap-before-touching; rows sorted by footing id; the basis field missing, unconfirmed, not a number, negative, in the wrong unit (refused by the basis kind); a zero clear distance; the refusals (design footing that is no subject, subject without design row, footing without status row, status row outside the design, closure, verdict-set and decision rows that name a footing outside the design); a run through `HarnessCalcPort` with a real store (the stored payload validates as `harness.footing_schedule/1`, `draft` is true, the four ref rules, literals refused). `tests/unit/footing/test_calcs_registered.py`: metadata, lock entry, this record, cited constants only.

## Reviewer and date

Pending: a subagent that did not write the calc (bootstrap mode), then the owner. Written 2026-11-18.

## Findings and open points for the owner

1. 4.4.6 lists "closures (reasons)" and "the decision references" as inputs and names no kind for them. This calc takes three lists as data (not references): closures `{id, reason}`, verdict sets `{id, result}` (the record ids that last judged the footing) and decisions `{id, decision}`. The output has verdict-set references per footing, so the verdict sets had to come in too. Recommend: accept; the block (plan 0010 T8) builds the lists.
2. The kind `harness.footing_schedule/1` requires `closure` to follow the family statuses, so the clearance mark "NEEDS_ENGINEER (CLEARANCE)" cannot be carried by `closure`. This calc carries it in the design row (`status` NEEDS_ENGINEER, `reason` CLEARANCE, unless the row already says NEEDS_ENGINEER, then its own reason stays), in `reasons` (CLEARANCE) and in `neighbour`. Recommend: accept, or change the kind (plan 0010 T1 files) to let `closure` say `needs_engineer` for a clearance mark.
3. 4.4.6 gives no rule for a gap of exactly zero or for a conflict between a footing and several neighbours. A gap of zero is not negative: touching plans are at distance 0, a conflict only when the clear distance is above 0. An overlap is always a conflict, also at clear distance 0. The neighbour named is the overlapping one before one at a distance, then the smaller squared distance, then the smaller id (as text); only one neighbour fits the kind.
4. The reasons are the reason of the design row, the closure reasons given and CLEARANCE, in this order, without repeats. Recommend: accept.
5. Every subject must have a design row and a status row, and every row of the design, status, closures, verdict sets and decisions must belong to a subject or footing of the design: the calc refuses an inconsistent set instead of dropping footings from the schedule. A footing closed before the layout or the checks (for example at the plan size) has no design or status row in the kinds of plan 0010 T1 to T4; the block (T8) must give such footings rows, or the kinds must allow it. This is the main thing the block task must settle.
6. A plan of a footing is centred on its joint (BP 2); the column offset is not modelled. Footings of other kinds (combined, strap) are not in the schedule.
