# harness.model_diff

- Calc id, version and content hash: `harness.model_diff` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0003 Q10)
- Method source: spec 0003 section 4.7, rules D1 to D7; basis tolerances from section 4.4 `compare.*`
- Golden cases (`tests/data/golden/calcs/`):
  - `diff-section-changed.json` (D4; one frame section rename). Result: pass.
- Boundary and property tests: `tests/property/test_diff.py::test_boundary_exact`, `::test_identity_and_symmetry`; `tests/unit/calcs/test_diff.py` (basis required, not compared, ambiguous keys, nested input)
- Workflow: `tests/workflow/test_calc_step.py::test_older_revision_inputs` (AC48 stale rules, AC49 via `tests/contract/test_calc_lock.py::test_stale_ok_fields_match_spec`)
- Reviewer and date: awaiting review
- Findings and open gaps: nested `before`/`after` groups in golden files flatten to `before_*` and `after_*` fields for the CalcPort; full engine `REF_STALE` on `after_*` is checked through `resolve_ref` with the describe rules in the workflow test.
