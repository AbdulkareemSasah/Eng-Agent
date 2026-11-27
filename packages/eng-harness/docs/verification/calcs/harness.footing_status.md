# Verification record: harness.footing_status

- Calc id: `harness.footing_status`
- Version: 1
- Content hash: `d10b33ad332b2d0757a531fc5ba638104428654ab4f526f604933875f5c9a469` (from `calcs.lock.json`; any later change to the calc or to a module it imports changes it and the owner re-verifies)
- Status: draft (not approved; ADR-0028 section 4: no entry in `approvals.yaml`)
- Method source: eng-harness spec 0010 section 4.4.5 (family status order, governing ratio, closure, decision state), acceptance criterion AC10; reads no basis field
- Constants: none but the calc version (`Cited`, 1); the family order is a tuple of statuses (a rule, not an engineering number). No engineering number.

## Golden cases

Files `tests/data/golden/footing/status-*.json`, test `tests/golden/footing/test_status.py::test_golden_cases`. Every case is synthetic and its derivation is written in the file; the expected values were derived by hand, not taken from the calc. The inputs are full stored records (a verdict set holds code-pack verdicts with demand, capacity and a ratio that agrees with its status).

| File | Method rule | Hand derivation (summary) |
|---|---|---|
| `status-family-order` | 4.4.5 order | One family carries every combination: PASS gives PASS; PASS with NOT_APPLICABLE gives NOT_APPLICABLE; NOT_APPLICABLE with NEEDS_ENGINEER gives NEEDS_ENGINEER; NEEDS_ENGINEER with ERROR gives ERROR; ERROR with FAIL gives FAIL; PASS, FAIL and ERROR give FAIL. Verdicts of different footings are interleaved. Ratios: the governing verdict's (0.5, 0.5, null, null, 1.2, 1.5). Closures: passed, needs_engineer x3, failing x2 |
| `status-mixed-fail-and-needs-engineer` | 4.4.5 closure, state | A footing with bearing FAIL and punching NEEDS_ENGINEER is failing (FAIL wins); one with only NEEDS_ENGINEER is needs_engineer; two FAIL families are failing. State flags `plan_at_max`, `depth_at_max`, `spacing_at_min` copied from the design rows; `engineer_sized` true only for the engineer-sized row |
| `status-ratio-governing` | 4.4.5 ratio | The ratio shown is the raw ratio of the governing verdict: 0.8 among 0.3, 0.8, 0.6; 0.95 FAIL against a ratio limit 0.9 next to 0.85 PASS (never divided by the limit) |

## Other tests

`test_status.py`: the trace (inputs with their references and counts, no constants, steps and their `uses`, outputs); rows sorted by footing id; the largest of several governing ratios; no ratio without a governing verdict; the state flags; the refusals (a design footing that is no subject, a footing without a verdict in each of the six sets, a verdict about a footing outside the design, a verdict about a subject that is not a footing, with field, received value and message); a run through `HarnessCalcPort` with a real store (the stored payload validates as `harness.footing_status/1`, `draft` is true, the six ref rules are `verdicts.set/1` and the two harness kinds, literals are refused). `tests/unit/footing/test_calcs_registered.py`: metadata, lock entry, this record, cited constants only.

## Reviewer and date

Pending: a subagent that did not write the calc (bootstrap mode), then the owner. Written 2026-11-18.

## Findings and open points for the owner

1. The order of 4.4.5 ends with "else NOT_APPLICABLE, else PASS". A set with no verdict for a footing would therefore read as PASS. This calc refuses it (`INVALID_ARGUMENT`, field the family, received the footing id): a missing verdict means a check did not run, which is not an engineering result. Recommend: accept.
2. A family with PASS and NOT_APPLICABLE verdicts is NOT_APPLICABLE (the literal order), and its closure is then `needs_engineer`. Recommend: confirm; an alternative reading (NOT_APPLICABLE ignored beside a PASS) would change the order of 4.4.5.
3. "Governing ratio for display" is not defined in 4.4.5. This calc takes the ratio of the verdicts that carry `governing` (the pack marks, per subject, the PASS or FAIL verdict with the largest ratio: structural-codes core spec AC14), the largest if several do, null if none does or the governing verdict has no ratio. The ratio is shown as the pack reports it, not divided by `ratio_limit`. Recommend: accept.
4. Verdicts must be about `footing` subjects whose id is a footing of the design; others are refused rather than ignored. The input `subjects` is used only to check that every design row is a subject (the spec names it as an input and gives no other use).
5. The calc reports the footings of the design it is given. The block (plan 0010 T8) therefore passes the design rows of the open footings of the round with the verdict sets of that round; a footing closed before the layout (for example at the plan size) has no design row and no verdict, and is not reported here.
