# harness.placement_compare

- Calc id, version and content hash: `harness.placement_compare` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0003 Q10)
- Method source: spec 0003 section 4.11, rules P1 to P6; `compare.length_mm` (mm, >= 0) from the basis (section 4.4: confirmed, no default); squared distances compared exactly as fractions (P2); `a_frames` and `a_areas` are `stale_ok`, `b_*` and `basis` are not (section 4.13); the only numeric literal outside structural `len(...)` / `[0]` checks is the cited lower bound 0 of section 4.4. By lead decision (option (a) on spec 0003 section 4.11 P5), an id that appears as a candidate of an `ambiguous` entry is never listed as one-sided (`only_in_a` or `only_in_b`).
- Golden cases (`tests/data/golden/calcs/`; each derived by hand in its `derivation` field):
  - `placement-counts.json` (P1, AC42): one column and one beam fewer on side b; type and story count differences are `b − a`. Result: pass.
  - `placement-frames.json` (P2, P3, AC43): swapped ends `reversed`; (3, 4, 0) offset at tolerance 5 mm is `same` (`d² = t²`); (6, 8, 0) is `moved` with distance 10 mm. Result: pass.
  - `placement-areas.json` (P4, AC44): cyclic shift of points `same`; reversed order `reversed`; different point count `reshaped`. Result: pass.
  - `placement-renames.json` (P5, AC45): one mutual geometric partner is `renamed`; two coincident partners make the a-side id `ambiguous` with both candidates listed, and those candidates are excluded from `only_in_b` (lead decision on P5). Result: pass.
- Boundary and unit tests: `tests/unit/calcs/test_placement.py` (the four golden scenarios as unit cases; basis refusals; incomplete sides and `basis.complete = false`; `stale_ok` marks; side-b and many-to-many ambiguous loops; area rename and area ambiguous cases; `(3, 4, 0)` offset below tolerance expecting `moved`; zero tolerance exactness; every golden expectation is a valid `PlacementComparison`); `tests/contract/test_calc_lock.py::test_stale_ok_fields_match_spec` (AC49); `tests/golden/test_calcs_golden.py` for the placement stems
- Reviewer and date: awaiting review
- Findings and open gaps:
  - P5 candidate classification (owner decision): spec 0003 section 4.11 P5 states "Exactly one candidate in each direction gives renamed. More than one gives ambiguous ... None gives only_in_a or only_in_b", without specifying an id that has one candidate whose partner has multiple candidates. Under the lead decision (option (a)), an id listed as a candidate of an `ambiguous` entry is never placed in `only_in_a` or `only_in_b`. Listed for the owner to confirm in spec 0003 §4.11 P5.
  - Story name collision: a real story literally named `unassigned` shares the `unassigned` bucket with elements whose `story` is null.
  - Two models with different origins are out of scope (no offset parameter; non-goal). Section and kind changes are not reported here (the difference report covers them). P5 is quadratic in the number of unmatched objects and is bounded by `max_items`.
