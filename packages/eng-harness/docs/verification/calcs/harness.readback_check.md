# harness.readback_check

- Calc id, version and content hash: `harness.readback_check` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0003 Q10)
- Method source: spec 0003 section 4.8, rules R0 to R4; R1 runs `harness.model_diff` (section 4.7, the seven `compare.*` basis fields of section 4.4, no default) and R2 compares with its tolerances by D3 and D4; an effect's key is the reported D2 key, list name included (amendment B-483); `stale_ok` on `before_*` only (section 4.13)
- Golden cases (`tests/data/golden/calcs/`; each derived by hand in its `derivation` field):
  - `readback-pass.json` (R4): a section set and a frame load read back 0.4 kN/m from the expected value within 1 kN/m; both changes explained. Result: pass.
  - `readback-mismatch.json` (R2): a frame load read back 1.5 kN/m off (mismatch) and an added frame that is absent (missing): `FAIL`. Result: pass.
  - `readback-unexpected.json` (R3): a section change on a frame no effect names is unexpected: `FAIL`. Result: pass.
  - `readback-unit-scale.json` (R2): thickness 0.2 expected, 200 read: mismatch, `FAIL`. Result: pass.
- Boundary and unit tests: `tests/unit/calcs/test_readback.py` (not read, circular inputs refused, tolerance boundary on both sides, set, add and remove results, duplicate keys, incomplete side, pointer-prefix explanation, unexpected objects, key location, trace and `stale_ok` marks); `tests/contract/test_calc_lock.py::test_stale_ok_fields_match_spec` (AC49)
- Reviewer and date: awaiting review
- Findings and open gaps: R0 requires the same model id on both sides; `RefMeta` carries no `derived_from`, so a working copy read against its original is refused rather than recognized (in the edit cycle both reads are of the working copy, spec 0007 step 9). Under a key that occurs more than once in the after set, an effect is compared with each object and matches only when all match; the report's ambiguous key still gives `NEEDS_ENGINEER`. The trace outputs are the report's `identical` and this calc's `status`. The live checks are local-testing item 16b (spec L-2).
