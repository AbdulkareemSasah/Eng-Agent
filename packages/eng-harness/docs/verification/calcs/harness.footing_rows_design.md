# Verification record: harness.footing_rows_design

- Calc id: `harness.footing_rows_design`
- Version: 1
- Content hash: `09d45025fad9493e8e88dbfa81fbc18ddbb3982c6389ea737ee39071c607365d` (from `calcs.lock.json`)
- Status: draft
- Method source: eng-harness spec 0010 §4.4.7 K1 to K3 and AC35
- Constants: cited calc version only. The method reads zero basis fields.

## Golden case

`tests/data/golden/footing/rows-design.json` runs through `tests/golden/footing/test_rows.py::test_golden_cases`. The inputs are disjoint. J1 comes from `base` and J2 comes from `extra`. The expected rows are copied in id order with every design field preserved. The fixture records its hand derivation.

## Other verification

The golden runner also checks the stored output kind, draft metadata, trace, provenance and completeness.

The CalcPort requires whole-record references of the declared kind. The trace records the references and the source selected for each requested id.

## Reviewer and date

Pending independent review and owner approval.
