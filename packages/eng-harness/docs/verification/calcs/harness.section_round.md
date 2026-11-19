# harness.section_round

- Calc id, version and content hash: `harness.section_round` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0003 Q10)
- Method source: spec 0003 section 4.10, rules N1 to N4 (13 §2 `modeling`, "rounding increment for new section sizes", and 11 §4); `modeling.section_increment_mm` (mm, > 0) and `modeling.section_rounding` (no unit, `up`) from the basis (section 4.4: confirmed, no default); `required` in mm and > 0 (section 5 bounds, applied by `validate_input`); no `compare.*` field is read; no field is `stale_ok` (section 4.13); the only numeric literal is the cited lower bound 0 of sections 4.4 and 5
- Golden cases (`tests/data/golden/calcs/`; each derived by hand in its `derivation` field):
  - `round-up.json` (N1, AC39): 437.5 mm with an increment of 50 mm rounds to 450 mm, multiple 9. Result: pass.
  - `round-exact.json` (N1, AC39): 400 mm is a multiple of 50 mm and stays 400 mm, multiple 8. Result: pass.
  - `round-just-above.json` (N1, AC39): 400 mm plus one unit in the last place (2^-44 mm) rounds to 450 mm, never 400 mm. Result: pass.
- Boundary and unit tests: `tests/unit/calcs/test_rounding.py` (rules other than `up`, gap CG-2; `required` of 0, -0 and below zero refused with `OUT_OF_RANGE`, 0.5 mm accepted, never clamped; no `compare.*` field in the basis or the trace; exact-fraction cases including a product halfway between two floats; basis refusals; increment not > 0; basis as a record; trace and schema marks; every golden expectation is a valid `SectionSize`); `tests/property/test_rounding.py` (AC41); `tests/contract/test_calc_lock.py::test_stale_ok_fields_match_spec` (AC49)
- Reviewer and date: awaiting review
- Findings and open gaps: rules other than `up` are gap CG-2. No allowance for float noise above a multiple (Q14): such a value rounds to the next multiple. Multiples count from zero; no catalog, minimum dimension or code limit is applied (separate checks). The trace records r / i as a float, so a ratio beyond the float range (an increment more than about 1e308 times smaller than the required size) ends as a calc defect (`INTERNAL`), never as a size.
