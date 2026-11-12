# harness.model_fingerprint

- Calc id, version and content hash: `harness.model_fingerprint` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0003 Q10)
- Method source: spec 0003 section 4.6, rules F1 to F6 and the F2 table; RFC 8785 for the canonical bytes
- Golden cases (`tests/data/golden/calcs/`; the canonical bytes are written by hand in each file's `derivation` and hashed with `hashlib` in `tests/unit/calcs/test_fingerprint.py::test_golden_hashes_match_the_hand_written_bytes`):
  - `fingerprint-canonical-bytes.json` (F2, F3, F4; case a): two frames and one frame section. Result: pass.
  - `fingerprint-point-order.json` (F2; cases b and d): frames reversed give the frames hash of case a; areas sort by id while their points and joints keep their order. Result: pass.
  - `fingerprint-moved-column.json` (F3; case c): one column end moved by 0.001 mm changes the frames hash only. Result: pass.
- Boundary and property tests: `tests/property/test_fingerprint.py::test_order_independent`, `::test_any_change_changes_fingerprint` (Hypothesis, derandomized); `tests/unit/calcs/test_fingerprint.py` (incomplete read and `same_state`, mixed models and revisions, record without a host model, literal without a record, no section, empty list hashed, area point and joint order, stories order, trace, CalcPort run)
- Reviewer and date: awaiting review
- Findings and open gaps: `items` counts the members of the payload's top-level lists (nested lists such as grid lines and combination items are not counted); the spec does not define it further. Live checks (spec L-1) are in `docs/local-testing.md`.
