# Verification record: harness.footing_rows_dims

- Calc id: `harness.footing_rows_dims`
- Version: 1
- Content hash: `c2a80d14c40223690ca34ac88c246c9c177867e9930b091ed9ec635317534847` (from `calcs.lock.json`)
- Status: draft
- Method source: eng-harness spec 0010 §4.4.7 K1 to K3 and AC35
- Constants: cited calc version only. The method reads zero basis fields.

## Golden case

`tests/data/golden/footing/rows-dims.json` runs through `tests/golden/footing/test_rows.py::test_golden_cases`. The first call selects J1 from `extra` and J2 from `base`. The second takes J1 from the stored first result and J2 from the later source. The expected rows are copied as J1, J2 despite the reverse request order. The fixture records its hand derivation.

## Other verification

The refusal tests also call this calc with a wrong kind in each input and with a missing id. They check the error codes and verify that a refusal stores no result.

The CalcPort requires whole-record references of the declared kind. The trace records the references and the source selected for each requested id.

## Reviewer and date

Pending independent review and owner approval.
