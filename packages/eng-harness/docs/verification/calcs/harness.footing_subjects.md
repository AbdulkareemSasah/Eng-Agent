# Verification record: harness.footing_subjects

- Calc id: `harness.footing_subjects`
- Version: 1
- Content hash: `6023c85a3e67111231ffb12370ae81c5eefed11befba474e74f1a8dc6121d4ff` (from `calcs.lock.json`; any later change to the calc or to a module it imports changes it and the owner re-verifies)
- Status: draft (not approved; ADR-0028 section 4: no entry in `approvals.yaml`)
- Method source: eng-harness spec 0010 section 4.4.1 (rules S1 to S6), acceptance criterion AC6; basis field `compare.angle_deg` read as spec 0003 section 4.4 states (confirmed, unit deg, value >= 0)
- Constants: five `Cited` angles (0, 90, 180, 270, 360 deg), source "Geometry"; no engineering number. The angle tolerance is the basis field `compare.angle_deg`, never a literal.

## Golden cases

Files `tests/data/golden/footing/subjects-*.json`, test `tests/golden/footing/test_subjects.py::test_golden_cases`. Every case is synthetic and its derivation is written in the file; the expected values were derived by hand, not taken from the calc.

| File | Method rule | Hand derivation (summary) |
|---|---|---|
| `subjects-basic` | S1, S2, S3, S5, S6 | Lower joint is the end with the smaller z (a column listed with its top end first); a beam is no column; rotations 0 and 180 give cx = b, 90 and 270 give cx = h; two reaction rows at one joint are one support joint |
| `subjects-excluded` | S1 to S5 | Upper joint only, unnamed lower end, beam end and horizontal "column" give NO_COLUMN_AT_JOINT; two columns give TWO_COLUMNS_AT_JOINT; circular and other shapes give SECTION_NOT_RECTANGULAR; 45 deg gives COLUMN_ROTATED; excluded rows sorted by joint as text |
| `subjects-angle-tolerance` | S5 | Tolerance 2 deg: distance equal to the tolerance is within (2.0, 88.0, 182.0, 272.0, 358.0), just beyond is not (2.5, 87.9); wrap-around and negative rotations (361.5, -88.0, -2.5, 450.0) |
| `subjects-zero-tolerance` | S5 | Tolerance 0: only exact multiples of 90 deg |
| `subjects-wide-tolerance` | S5 | Tolerance 50: a rotation within the tolerance of both a along-axis and an across-axis target (45, 135) is undecided and gives COLUMN_ROTATED |
| `subjects-no-reactions` | S2 | No reaction rows: no subject, nothing excluded |

## Other tests

`test_subjects.py`: trace inputs, constants and counts; basis field missing, unconfirmed, wrong unit, not a number, negative (the error codes); a zero tolerance is accepted; a section name missing from the sections; a run through `HarnessCalcPort` with a real store (the stored payload validates as `harness.footing_subjects/1`, `draft` is true, literals are refused). `tests/unit/footing/test_calcs_registered.py`: metadata, lock entry, this record, cited constants only.

## Reviewer and date

Pending: a subagent that did not write the calc (bootstrap mode), then the owner. Written 2026-11-05.

## Findings and open points for the owner

1. S1 does not say what a "column" with both ends at one height is. This calc gives it no lower end, so it is not counted at any joint (the joint is excluded NO_COLUMN_AT_JOINT if nothing else stands there). Recommend: accept.
2. S5 does not say what happens when `compare.angle_deg` is large enough for a rotation to be within it of both a along-axis and an across-axis target (any tolerance of 45 deg or more). This calc then excludes the column as COLUMN_ROTATED instead of choosing an orientation. Recommend: accept.
3. S3 and S4: a column's section name that is not in the sections is an input error (`INVALID_ARGUMENT`, field `sections`), looked up only for a column that stands alone at a support joint.
4. Which of `b_mm` and `h_mm` lies along local axis 2 at zero rotation is the CSI convention: local test L2 (`docs/local-testing.md`).
5. Excluded rows and subjects are sorted by joint name as text, so "J10" precedes "J5". The spec fixes ordering only for subjects (kind validator); the ordering of excluded rows is this calc's choice.
