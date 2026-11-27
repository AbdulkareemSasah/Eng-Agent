# harness.model_diff

- Calc id, version and content hash: `harness.model_diff` v1; the hash is the entry in `src/eng_harness/calcs/calcs.lock.json`
- Status: draft (bootstrap mode, ADR-0028 section 4; owner approval awaited, spec 0003 Q10)
- Method source: spec 0003 section 4.7, rules D1 to D7, on the comparison core `calcs/_compare.py` (D2 to D5); tolerances from the seven `compare.*` basis fields of section 4.4 (`compare.length_mm`, `compare.angle_deg`, `compare.stress_MPa`, `compare.unit_weight_kN_m3`, `compare.line_load_kN_m`, `compare.area_load_kPa`, `compare.dimensionless_ratio`; each the tolerance of the quantity kind its unit suffix names; no default); keys begin with their list name (D2, T8c); `stale_ok` per section 4.13
- Golden cases (`tests/data/golden/calcs/`; each derived by hand in its `derivation` field):
  - `diff-section-changed.json` (D4): one frame's section S1 to S2, one changed row at `/section`. Result: pass.
  - `diff-added-removed.json` (D2): one frame removed and one added, whole objects shown. Result: pass.
  - `diff-boundary.json` (D3): a coordinate that differs by exactly the tolerance 0.5 mm is within tolerance; one that differs by the next binary64 above 0.5 (1/2 + 2^-53) is changed. Result: pass.
  - `diff-zero-tolerance.json` (D3): tolerance 0; a difference of 2^-1074 mm is changed. Result: pass.
  - `diff-angle-full-turn.json` (D6): `rotation_deg` 0 to 360 is changed (no wrapping). Result: pass.
  - `diff-ambiguous-row.json` (D2, D7): a frame-load key that occurs twice on each side is ambiguous and the report is incomplete. Result: pass.
- Boundary and property tests: `tests/property/test_diff.py::test_boundary_exact`, `::test_zero_tolerance_needs_exact_equality`, `::test_identity_and_symmetry` (Hypothesis, derandomized); `tests/unit/calcs/test_diff.py` (basis fields required, basis and sections as records, side models and revisions, not compared and ambiguous, identical and incomplete, tolerances and trace, `stale_ok` marks)
- Workflow and contract: `tests/workflow/test_calc_step.py::test_older_revision_inputs` (AC48: real engine and CalcPort; `before_frames` at revision n accepted, `after_frames` at n refused with `REF_STALE` before the port call); `tests/contract/test_calc_lock.py::test_stale_ok_fields_match_spec` (AC49)
- Reviewer and date: awaiting review
- Findings and open gaps: the inputs are the flat fields `before_<section>` and `after_<section>` (spec 4.7, amendment B-469). The contract's basis kind already refuses a `compare.*` field whose unit differs from its suffix's unit (B-464), so the calc's own unit check (AC26) is reached only by a basis built past that check; a test covers both. The calc reads the basis but the CalcPort learns `basis_fields` from its caller (`BASIS_FIELDS`), as for the other calcs.
