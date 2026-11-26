# Verification record: harness.footing_rows_status

- Calc id: `harness.footing_rows_status`
- Version: 1
- Content hash: `42ebdf30ff93cb99ba50106db391ddde218c33453173b8364c43bb0a4f76c2d6` (from `calcs.lock.json`)
- Status: draft
- Method source: eng-harness spec 0010 §4.4.7 K1 to K3 and AC35
- Constants: cited calc version only. The method reads zero basis fields.

## Golden case

`tests/data/golden/footing/rows-status.json` runs through `tests/golden/footing/test_rows.py::test_golden_cases`. The extra record is empty. J1 is copied from `base` with its closure, family ratios and decision state intact. The fixture records its hand derivation.

## Other verification

The golden runner also checks the stored output kind, draft metadata, trace, provenance and completeness.

The CalcPort requires whole-record references of the declared kind. The trace records the references and the source selected for each requested id.

## Reviewer and date

Pending independent review and owner approval.
