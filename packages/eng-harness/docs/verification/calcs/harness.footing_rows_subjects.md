# Verification record: harness.footing_rows_subjects

- Calc id: `harness.footing_rows_subjects`
- Version: 1
- Content hash: `4bd9c6a74525f56de53cfc3fde4b97edc57862cee0f05274ecddf746b0eacdf4` (from `calcs.lock.json`)
- Status: draft
- Method source: eng-harness spec 0010 §4.4.7 K1 to K3 and AC35
- Constants: cited calc version only. The method reads zero basis fields.

## Golden case

`tests/data/golden/footing/rows-subjects.json` runs through `tests/golden/footing/test_rows.py::test_golden_cases`. J1 comes from `base` and J20 from `extra`, in id order. The unrequested J2 is dropped. The expected `excluded` list contains base's J3. Extra's J10 is omitted. The fixture records its hand derivation.

## Other verification

`test_copy_preserves_rows` generates overlapping and disjoint inputs and requests that can repeat ids. It checks sorted, unique ids and exact equality with the selected source row.

The CalcPort requires whole-record references of the declared kind. The trace records the references and the source selected for each requested id.

## Reviewer and date

Pending independent review and owner approval.
