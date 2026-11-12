# harness.column_select

- Calc id, version and content hash: `harness.column_select` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited)
- Method source: spec 0013 section 4.4.1, rules L1 to L3; spec 0003 section 4.11 P2 for the plan-distance tolerance
- Golden cases (`tests/data/golden/column_design/`):
  - `column-select-names.json` (L1, L2, L3): scope by frame names; one horizontal member excluded. Result: pass.
  - `column-select-story-section.json` (L1): story and section filters together. Result: pass.
  - `column-select-vertical-boundary.json` (L2; P2 at d² = t²): two frames on the inclusive boundary. Result: pass.
  - `column-select-not-vertical.json` (L2): plan offset 5.001 mm against tolerance 5 mm. Result: pass.
  - `column-select-unknown-names.json` (L1): unknown frame name and empty selection. Result: fail.
- Property test: `tests/property/test_column_select.py::test_permutation_invariant` (Hypothesis, derandomized)
- Reviewer and date: awaiting review
- Findings and open gaps: none
