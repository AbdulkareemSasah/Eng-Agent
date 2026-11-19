# harness.placement_compare

- Calc id, version and content hash: `harness.placement_compare` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0003 Q10)
- Method source: spec 0003 section 4.11, rules P1 to P6; `compare.length_mm` (mm, >= 0) from the basis (section 4.4: confirmed, no default); squared distances compared exactly as fractions (P2); `a_frames` and `a_areas` are `stale_ok`, `b_*` and `basis` are not (section 4.13); the only numeric literals are the cited lower bound 0 of section 4.4 and the cardinality one of P5
- Golden cases (`tests/data/golden/calcs/`; each derived by hand in its `derivation` field):
  - `placement-counts.json` (P1, AC42): one column and one beam fewer on side b; type and story count differences are `b − a`. Result: pass.
  - `placement-frames.json` (P2, P3, AC43): swapped ends `reversed`; (3, 4, 0) offset at tolerance 5 mm is `same` (`d² = t²`); (6, 8, 0) is `moved` with distance 10 mm. Result: pass.
  - `placement-areas.json` (P4, AC44): cyclic shift of points `same`; reversed order `reversed`; different point count `reshaped`. Result: pass.
  - `placement-renames.json` (P5, AC45): one mutual geometric partner is `renamed`; two coincident partners make the a-side id `ambiguous` with both candidates listed. Result: pass.
- Boundary and unit tests: `tests/unit/calcs/test_placement.py` (the four golden scenarios as unit cases; basis refusals; incomplete sides; `stale_ok` marks; every golden expectation is a valid `PlacementComparison`); `tests/contract/test_calc_lock.py::test_stale_ok_fields_match_spec` (AC49); `tests/golden/test_calcs_golden.py` for the placement stems
- Reviewer and date: awaiting review
- Findings and open gaps: two models with different origins are out of scope (no offset parameter; non-goal). Section and kind changes are not reported here (the difference report covers them). P5 is quadratic in the number of unmatched objects and is bounded by `max_items`.
