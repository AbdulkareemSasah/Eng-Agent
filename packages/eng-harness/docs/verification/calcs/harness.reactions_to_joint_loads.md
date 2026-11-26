# Verification record: harness.reactions_to_joint_loads

- Calc id: `harness.reactions_to_joint_loads`
- Version: 1
- Content hash: `fd070ff9ddcc5fa34b9f121b6d41b285b61d46a1bfb97b4d681c0e6857424c71` (from `calcs.lock.json`; any later change to the calc or to a module it imports changes it and the owner re-verifies)
- Status: draft (not approved; ADR-0028 section 4: no entry in `approvals.yaml`)
- Method source: eng-harness spec 0010 section 4.9 items M1 to M4 (and step 2), acceptance criterion AC24; basis field `compare.length_mm` read as spec 0003 section 4.4 states (confirmed, unit mm, value >= 0); sign negation as BP section 4.1 (action and reaction); soft engineering outcomes as payload statuses per spec 0003 section 4.2
- Constants: two `Cited`: zero length 0 mm (lower bound of `compare.length_mm`, spec 0003 4.4) and calc version 1. The length tolerance is the basis field, never a literal. No engineering number.

## Golden cases

Files `tests/data/golden/footing/loads-*.json`, test `tests/golden/footing/test_reactions_to_loads.py::test_golden_cases`. Every case is synthetic and its derivation is written in the file; the expected values were derived by hand, not taken from the calc.

| File | Method rule | Hand derivation (summary) |
|---|---|---|
| `loads-basic-negation` | M1, M2, M3 | Exact match at (1000, 2000); reaction FX=10, FY=-20, FZ=100, MX=1, MY=-2, MZ=3; loads are the negatives; punch null (SG-7); S1 absent on SAFE so combinations_to_add = S1; status OK, reason null |
| `loads-match-at-tolerance` | M2 | Subject (0,0), SAFE (10,0), tol=10: distance squared 100 = tol squared, inclusive match; SAFE already has S1, combinations_to_add empty; status OK |
| `loads-unmatched` | M2 | Subject (0,0), SAFE (10.1,0), tol=10: 102.01 > 100; payload status NEEDS_ENGINEER, reason UNMATCHED (spec 0010 4.9 M2; 0003 4.2) |
| `loads-double-match` | M2 | Two SAFE points within tol; INVALID_ARGUMENT hint DOUBLE_MATCH (genuinely invalid input) |
| `loads-pattern-missing` | M4 | LIVE transferred, SAFE has only DEAD; payload status NEEDS_ENGINEER, reason PATTERN_MISSING |
| `loads-combo-conflict` | step 2 | SAFE S1 items differ from ETABS S1 (scale 1.2 vs 1.0); payload status NEEDS_ENGINEER, reason COMBO_CONFLICT (never replaced) |
| `loads-chosen-cases-only` | M1 | Engineer chooses S1 only; LIVE reaction not transferred; status OK |

## Other tests

`tests/unit/footing/test_calcs_registered.py`: metadata, lock entry, this record, cited constants only. Kind fixture and contract cases in `tests/contract/test_footing_kinds.py` and `tests/data/kinds/footing/reactions_to_joint_loads.json` (`status` / `reason` on the result kind).

## Reviewer and date

Pending: a subagent that did not write the calc (bootstrap mode), then the owner. Written 2026-11-20; soft-outcome delivery corrected 2026-11-20 (adversarial verification r1, lead Reading A).

## Findings and open points for the owner

1. Spec 0010 4.9 says the calc "gives NEEDS_ENGINEER" for UNMATCHED, PATTERN_MISSING and a conflicting combination. The result kind carries `status` / `reason`; those three soft outcomes are payload `NEEDS_ENGINEER` with reason codes `UNMATCHED`, `PATTERN_MISSING` and `COMBO_CONFLICT` (COMBO_CONFLICT is not parenthetical in the spec; it names the step-2 conflict). Dual match remains `INVALID_ARGUMENT` hint `DOUBLE_MATCH`. Recommend: accept.
2. The stored result kind is `harness.reactions_to_joint_loads/1` (loads plus `combinations_to_add`, plus `status` / `reason`) so one calc result carries the change set and the engineering outcome. Spec 0010 4.9 names the loads as `harness.joint_loads/1`; the workflow builds that import payload from the loads field when status is OK. Recommend: accept.
3. Plan matching uses plan (x, y) only; z is ignored. Recommend: accept (spec: "in plan").
