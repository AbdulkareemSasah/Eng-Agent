# Verification record: harness.safe_equilibrium

- Calc id: `harness.safe_equilibrium`
- Version: 1
- Content hash: `05ab7cb50825a3c5352e30802016281555762c63b9402ce5cb0bcb60305d9b11` (from `calcs.lock.json`; any later change to the calc or to a module it imports changes it and the owner re-verifies)
- Status: draft (not approved; ADR-0028 section 4: no entry in `approvals.yaml`)
- Method source: eng-harness spec 0010 section 4.9 step 6, acceptance criterion AC25; basis field `checks.equilibrium_relative_tolerance_ratio` read as spec 0003 section 4.4 states (confirmed, unit `1`, value >= 0); magnitudes because the base-reaction sign is unconfirmed (SAFE Q6)
- Constants: two `Cited`: zero 0 (lower bound of the relative tolerance) and calc version 1. The tolerance is the basis field, never a literal. No engineering number.

## Golden cases

Files `tests/data/golden/footing/equilibrium-*.json`, test `tests/golden/footing/test_equilibrium.py::test_golden_cases`. Every case is synthetic and its derivation is written in the file; the expected values were derived by hand, not taken from the calc.

| File | Method rule | Hand derivation (summary) |
|---|---|---|
| `equilibrium-pass-within` | step 6 | A = -600 + -400 = -1000; \|A\|=1000; R=-1004; \|R\|=1004; tol=0.01; tol\|A\|=10; \|1004-1000\|=4 <= 10: PASS |
| `equilibrium-fail-outside` | step 6 | A=-1000; R=-1020; \|1020-1000\|=20 > 10: FAIL |
| `equilibrium-at-tolerance` | step 6 | A=-1000; R=-1010; \|1010-1000\|=10 <= 10: PASS (boundary inclusive) |
| `equilibrium-self-weight-not-compared` | step 6 | Pattern SELF has self_weight_ratio=1.0: NOT_COMPARED regardless of \|R\| and \|A\| |

## Other tests

`tests/unit/footing/test_calcs_registered.py`: metadata, lock entry, this record, cited constants only.

## Reviewer and date

Pending: a subagent that did not write the calc (bootstrap mode), then the owner. Written 2026-11-20.

## Findings and open points for the owner

1. A pattern present only in base reactions (or only in applied loads) is still compared, with the missing side treated as 0. Spec 0010 4.9 step 6 says "per transferred pattern"; transferred patterns are those with applied loads. This calc unions both sides so a missing applied side fails when R ≠ 0. Recommend: accept, or restrict to patterns that appear in the loads.
2. `self_weight` is `self_weight_ratio > 0` on the SAFE load-set pattern. Recommend: accept.
3. The input shape for base reactions matches spec 0008 §4.6 (`harness.base_reactions/1`) and is validated locally until plan 0008 T7 registers the kind. Recommend: accept.
