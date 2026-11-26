# Verification record: harness.footing_rows_design

- Calc id: `harness.footing_rows_design`
- Version: 1
- Content hash: `d9d092efcd66779387d216de5840b6c739917d2510fe18c7a7b25ae8b83e32d6` (from `calcs.lock.json`)
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
