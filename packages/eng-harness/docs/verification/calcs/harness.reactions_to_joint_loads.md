# Verification record: harness.reactions_to_joint_loads

- Calc id: `harness.reactions_to_joint_loads`
- Version: 1
- Content hash: `de5b118cf353ada90fb181ce84eddc11bce77330298a177fe7ba2f6dce425fdf` (from `calcs.lock.json`; any later change to the calc or to a module it imports changes it and the owner re-verifies)
- Status: draft (not approved; ADR-0028 section 4: no entry in `approvals.yaml`)
- Method source: eng-harness spec 0010 section 4.9 items M1 to M4 (and step 2), acceptance criterion AC24; basis field `compare.length_mm` read as spec 0003 section 4.4 states (confirmed, unit mm, value >= 0); sign negation as BP section 4.1 (action and reaction)
- Constants: two `Cited`: zero length 0 mm (lower bound of `compare.length_mm`, spec 0003 4.4) and calc version 1. The length tolerance is the basis field, never a literal. No engineering number.

## Golden cases

Files `tests/data/golden/footing/loads-*.json`, test `tests/golden/footing/test_reactions_to_loads.py::test_golden_cases`. Every case is synthetic and its derivation is written in the file; the expected values were derived by hand, not taken from the calc.

| File | Method rule | Hand derivation (summary) |
|---|---|---|
| `loads-basic-negation` | M1, M2, M3 | Exact match at (1000, 2000); reaction FX=10, FY=-20, FZ=100, MX=1, MY=-2, MZ=3; loads are the negatives; punch null (SG-7); S1 absent on SAFE so combinations_to_add = S1 |
| `loads-match-at-tolerance` | M2 | Subject (0,0), SAFE (10,0), tol=10: distance squared 100 = tol squared, inclusive match; SAFE already has S1, combinations_to_add empty |
| `loads-unmatched` | M2 | Subject (0,0), SAFE (10.1,0), tol=10: 102.01 > 100; INVALID_ARGUMENT hint UNMATCHED |
| `loads-double-match` | M2 | Two SAFE points within tol; INVALID_ARGUMENT hint DOUBLE_MATCH |
| `loads-pattern-missing` | M4 | LIVE transferred, SAFE has only DEAD; INVALID_ARGUMENT hint PATTERN_MISSING |
| `loads-combo-conflict` | step 2 | SAFE S1 items differ from ETABS S1; INVALID_ARGUMENT hint COMBO_CONFLICT |
| `loads-chosen-cases-only` | M1 | Engineer chooses S1 only; LIVE reaction not transferred |

## Other tests

`tests/unit/footing/test_calcs_registered.py`: metadata, lock entry, this record, cited constants only. Kind fixture and contract cases in `tests/contract/test_footing_kinds.py` and `tests/data/kinds/footing/reactions_to_joint_loads.json`.

## Reviewer and date

Pending: a subagent that did not write the calc (bootstrap mode), then the owner. Written 2026-11-20.

## Findings and open points for the owner

1. Spec 0010 4.9 says the calc "gives NEEDS_ENGINEER" for UNMATCHED, PATTERN_MISSING and a conflicting combination. The calc raises `ContractError` `INVALID_ARGUMENT` with those hints; the SAFE stage block (plan 0010 T11) maps the hints to `NEEDS_ENGINEER`. Recommend: accept.
2. The stored result kind is `harness.reactions_to_joint_loads/1` (loads plus `combinations_to_add`) so one calc result carries the change set. Spec 0010 4.9 names the loads as `harness.joint_loads/1`; the workflow builds that import payload from the loads field. Recommend: accept.
3. Plan matching uses plan (x, y) only; z is ignored. Recommend: accept (spec: "in plan").
