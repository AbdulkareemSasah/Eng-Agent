---
id: plan-b073-safe-adapter
issue: "B-073"
spec: packages/eng-harness/docs/specs/0008-safe-adapter.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r3]  # r3 from the public_modules entries in pyproject.toml (amendment B-356)
tasks:
  - id: T1
    # Amendment (B-418, documents only): external gate on plan 0002 written on depends_on; servers/_session.py added (the
    # build check takes the server's product); pre-start grep of the shared modules for ETABS-only names, each hit a
    # lead plan amendment adding the file here before T1 starts, no lint exclusions (section 2)
    title: Product profile, per-product fingerprint, SAFE server section and product resolution
    # Amendment (B-413, documents only): test_build_mismatch_stops_run is written in plan 0002 T19a (B-475); the
    # test_session.py glob and the workflow conftest.py stay to adapt the session-level build-check tests of 0002 T6b to the per-product header.
    # Amendment (B-475, documents only): plan 0002 T19a now merges before T1, so build_ports in adapters/__init__.py
    # joins the files: it builds the build check from the allowlist header that T1 makes per product (about 10 counted
    # lines, an estimate taken inside the unchanged 350). Plan 0002 T19b also edits build_ports: whichever of the two
    # lands second adapts to the other in its own task. Off the first-live-run path with T2 and T3 (section 3).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_config.py"
      - "packages/eng-harness/src/eng_harness/servers/_buildcheck.py"
      - "packages/eng-harness/src/eng_harness/servers/_session.py"  # ServerCheck passes the server product to the build check (0002 T6b)
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"  # build_ports reads the per-product header (B-475)
      - "packages/eng-harness/src/eng_harness/adapters/_allowlist.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_etabs.py"
      - "packages/eng-harness/tests/unit/servers/test_config.py"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py"
      - "packages/eng-harness/tests/unit/adapters/test_products.py"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"  # adapts 0002 T6b's session-level build-check tests to the per-product header (B-413)
      - "packages/eng-harness/tests/workflow/conftest.py"  # the fixture's build pins, where they read the allowlist header (B-413)
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_safe_server_section"
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_product_and_host_key_rules"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py::test_fingerprint_per_product"
      - "packages/eng-harness/tests/unit/adapters/test_products.py::test_product_by_extension"
      - "packages/eng-harness/tests/unit/adapters/test_products.py::test_no_product_branches_in_shared"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_tool_not_served_for_product"
    covers: [AC1, AC2, AC3, AC4]
    depends_on: []  # external: plan 0002 T1, T6, T6b, T7 to T14 (with T8b) and T19a merged first (B-475); T3 also 0002 T15; T8 also 0002 T17
  - id: T2
    title: Synthetic SAFE mode of the CSI fake and its schema check
    files:
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py"
    max_changed_lines: 60
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_safe_fake_schemas_match_inventory"
    covers: [AC28]
    depends_on: [T1]
  - id: T3
    # Amendment (B-418, documents only): T3 holds the SG-1 to SG-9 ids and messages in _gaps.py but wires only SG-1 (AC8)
    title: SAFE allowlist entries, pinned SAFE fingerprint, session operations for .FDB, gap entries
    # Amendment (B-475, documents only): test_safe_build_mismatch_stops_run (AC4's stop, engine AC44) returns here from
    # plan 0002 T19 (B-413 had moved it there). Plan 0002 T19a adds build_ports first, so the stop fails at T3's base for
    # want of the SAFE entries and pinned SAFE fingerprint; T3 waits for 0002 T19a and engine plan 0001 T13, T15, T16, T16b (B-499), T19.
    # Its expected error is defined in plan 0002 section 2, T19b.
    # Amendment (B-581, documents only): AC6 and AC7 need AdapterHostPort._record_save to skip the table read when
    # profile.tables is empty (SAFE before T5), so the prior fingerprint is kept; measured by the B-212 writer on
    # packages/eng-harness/src/eng_harness/adapters/_hostport.py (not previously in T3's files). Every other non-test
    # file of that branch was already listed here.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"  # _record_save skips table read when profile.tables is empty (SAFE before T5); AC6, AC7 (amendment B-581)
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_session_ops.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_gaps.py"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_session_ops.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_session_ops.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_isolation.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_gaps.py"
      - "packages/eng-harness/tests/workflow/servers/test_guard.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"  # the SAFE engine stop of AC4 (B-475)
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_safe_entries_complete"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_escape_hatches_refused_for_safe"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_safe_against_inventory"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_safe_fingerprint_from_inventory"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_session_ops.py::test_working_copy_fdb"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_isolation.py::test_epochs_independent"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_gaps.py::test_new_model_gap"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_safe_build_mismatch_stops_run"
    covers: [AC3, AC4, AC5, AC6, AC7, AC8]
    depends_on: [T1, T2]
  - id: T4
    title: Table reader framework, field-map data with statuses, sections, materials and soil supports
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tables.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe_tables.toml"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe_state.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/unit/adapters/test_safe_tables.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_safe_tables.py::test_sections_and_materials"
      - "packages/eng-harness/tests/unit/adapters/test_safe_tables.py::test_soil_supports"
      - "packages/eng-harness/tests/unit/adapters/test_safe_tables.py::test_missing_column"
      - "packages/eng-harness/tests/unit/adapters/test_safe_tables.py::test_ambiguous_column"
      - "packages/eng-harness/tests/unit/adapters/test_safe_tables.py::test_unknown_table_is_gap"
    covers: [AC11, AC12, AC13]
    depends_on: [T3]
  - id: T5
    title: SAFE model-state reader, points and joint-load kinds, fingerprint
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe_state.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe.py"
      - "packages/eng-harness/src/eng_harness/adapters/_hostport.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_state.py"
      - "packages/eng-harness/tests/property/test_fingerprint.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_safe_state.py::test_kinds_and_fingerprint"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_state.py::test_truncated_raises"
      - "packages/eng-harness/tests/property/test_fingerprint.py::test_safe_order_independent_and_edit_sensitive"
    covers: [AC9, AC10]
    depends_on: [T4]
  - id: T6
    title: Joint-load import, pattern and combination edits for SAFE, read-back, SAFE check_model, point-load reconciliation
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe_loads.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_reconcile.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_checks.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_loads.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_readback.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_reconcile.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_edits.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_safe_loads.py::test_set_point_load_mapping"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_loads.py::test_zero_rows"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_loads.py::test_missing_joint_no_partial_write"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_loads.py::test_punch_dimensions_gap"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_loads.py::test_units_token_independent_of_present_units"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_readback.py::test_load_mismatch"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_readback.py::test_punch_dimension_change_detected"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_readback.py::test_safe_integrity_issues"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_reconcile.py::test_point_load_outcomes"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_edits.py::test_patterns_and_combos"
    covers: [AC14, AC15, AC16, AC17, AC18, AC19, AC20]
    depends_on: [T5]
  - id: T7
    # Amendment (B-418, documents only): T7 wires SG-2, SG-3, SG-4, SG-5 and SG-9 to their steps (AC24, AC25) and SG-6
    title: SAFE analysis on the long role, soil pressure, base reaction and joint reaction readers, design gaps
    # Amendment (B-588, documents only): AC23's ToolPort path needs the SAFE result-reader TOKENS, ANALYSIS_MODELS and
    # READERS from products/_safe_results.py merged into the shared registries in adapters/csi/_tools.py (the T6 pattern
    # for _safe_loads); measured by the B-216 writer on packages/eng-harness/src/eng_harness/adapters/csi/_tools.py
    # (not previously in T7's files). Every other non-test file of that branch was already listed here.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe_results.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_tools.py"  # T7 may only merge the SAFE result-reader tokens, argument models and readers from products/_safe_results.py into the shared registries (the T6 pattern) (amendment B-588)
      - "packages/eng-harness/src/eng_harness/adapters/csi/_gaps.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_analysis.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_results.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_gaps.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_safe_analysis.py::test_long_role_save_first_and_locked"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_results.py::test_soil_pressure_rows"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_results.py::test_soil_pressure_truncated"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_results.py::test_soil_pressure_group"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_results.py::test_soil_pressure_step_type_and_unique_key"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_results.py::test_base_and_joint_reactions"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_results.py::test_analysis_status"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_results.py::test_analysis_messages_unknown_is_gap"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_gaps.py::test_slab_design_gap"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_gaps.py::test_gaps_not_implemented"
    covers: [AC21, AC22, AC23, AC24, AC25]
    depends_on: [T6]
  - id: T8
    title: Recordings contract tests for SAFE, end-to-end cycle and crash matrix, local-testing list
    # Amendment (B-413, documents only): runs the real engine, so it waits for plan 0002 T19a (B-475) and engine plan 0001 T13,
    # T15, T16, T16b (B-499) and T19; the SAFE engine stop of AC4 is not here (no source file of T8 makes it fail at the base): T3 (B-475).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/acceptance/scripts/record_csi.py"
      - "packages/eng-harness/tests/contract/test_csi_recordings.py"
      - "packages/eng-harness/tests/workflow/test_safe_cycle.py"
      - "packages/eng-harness/tests/replay/test_safe_resume.py"
    max_changed_lines: 150
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/test_safe_cycle.py::test_cycle_steps"
      - "packages/eng-harness/tests/replay/test_safe_resume.py::test_crash_matrix"
      - "packages/eng-harness/tests/contract/test_csi_recordings.py::test_safe_adapter_on_recordings"
      - "packages/eng-harness/tests/contract/test_csi_recordings.py::test_safe_synthetic_matches_recordings"
    covers: [AC26, AC27, AC28]
    depends_on: [T7]
  - id: T9
    title: SAFE slab design run and punching and flexure readers (blocked until local tests L5 and L11 give the keys)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe_tables.toml"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_safe_results.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_gaps.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_gaps.py"
      - "packages/eng-harness/tests/workflow/adapters/test_safe_slab_design.py"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_safe_slab_design.py::test_design_run_and_punching_rows"
    covers: [AC24]
    depends_on: [T8]
  - id: T10
    title: "Mutation scope: the section 9 modules in r1_modules"
    # Amendment (B-601, owner decision D-46, 2026-11-20): CI mutates only modules listed in
    # [tool.eng-gate] r1_modules; spec 0008 section 9 names products/_safe_loads.py, _tables.py
    # and the SAFE reconcile rules (held in adapters/csi/_reconcile.py: the joint_loads / SAFE
    # profile branch) that are merged but absent from that list. This task adds those paths to
    # r1_modules, adds a contract guard that the section 9 list is covered by a glob, and
    # strengthens the existing tests until each module reaches mutation_min (80 %) with real
    # tests. No exclusions, pragmas or lowered thresholds; no module may be removed from
    # r1_modules to pass MU001. No source module is listed: the work strengthens tests only.
    # If a module cannot reach 80 % without a source change, the implementing writer reports
    # NEEDS_PLAN_AMENDMENT.
    files:
      - "packages/eng-harness/pyproject.toml"  # r1_modules entries for the listed modules only, amendment B-601
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/tests/contract/test_mutation_scope.py"  # shared by the five B-601 tasks; this task adds test_spec_0008_section_9_modules_in_r1
      - "packages/eng-harness/tests/workflow/adapters/test_safe_loads.py"  # adapters/csi/products/_safe_loads.py
      - "packages/eng-harness/tests/unit/adapters/test_safe_tables.py"  # adapters/csi/_tables.py
      - "packages/eng-harness/tests/workflow/adapters/test_safe_reconcile.py"  # SAFE reconcile rules in adapters/csi/_reconcile.py
    max_changed_lines: 60
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_mutation_scope.py::test_spec_0008_section_9_modules_in_r1"
    covers: []  # section 9 mutation scope is not an AC; this plan's covers style lists ACs only
    depends_on: [T4, T6]  # T4 _tables.py; T6 _safe_loads.py and the SAFE reconcile rules in csi/_reconcile.py
---

# Implementation plan: SAFE through the CSI adapter

## 1. Approach

The shared CSI adapter of [plan 0002](0002-servers-and-adapters.md) already carries everything product-neutral, so this
plan adds one product in the order of risk. T1 separates the product-specific parts (profile, per-product fingerprint,
a server section per product) because a wrong separation would let SAFE share state with ETABS. T2 extends the test-only
fake so every later task runs against a real SAFE-mode fake process. T3 fixes what may be called on SAFE (the allowlist,
its pinned fingerprint, the session operations on `.FDB`, the gap entries), which is the safety boundary. T4 and T5 read:
tables with explicit field maps whose status says what is confirmed, then the model state and its fingerprint. T6 writes:
the column-load import with read-back, check and reconciliation, the part where a unit, sign or dimension error would
reach an engineering result. T7 runs the analysis and reads results. T8 closes the loop end to end with recordings and
the crash matrix. T9 is blocked on the owner's local tests and fills the one place no key is known (slab design and
punching).

Every task is test-first: its first commit is `test:` with the tests in `tests_first`, failing on `build/v1`
([process/05](../../../../design/process/05-testing-and-verification.md) §9). Each task adds a `CHANGELOG.md` line. No
public module is added (everything is internal), so `[tool.eng-gate] public_modules` is unchanged. Tasks that share a
source file are serialized by `depends_on`: `_allowlist.toml` (T1, T3, T6, T7, T9), `_safe.py` (T3, T5, T6, T7; plan 0012 T3 after them for the gap and step-gap registries only, B-586),
`products/__init__.py` (T1; plan 0012 T3 after it for the gap and step-gap registry fields only, B-586; plan 0012 T4 after it for ProductProfile.declared_absences only, B-590; plan 0012 T5 after it for ProductProfile.add_frame_naming only, B-594),
`_safe_state.py` (T4, T5), `_safe_results.py` (T7, T9), `_kinds.py` (T4, T5, T7, T9), `_gaps.py` (T3, T7, T9),
`_hostport.py` (T3, T5; amendment B-581: T3 for AC6 and AC7 before T5's table map; plan 0012 T4 after them for absences-aware state-reader selection and fingerprint on save only, B-590),
`_tools.py` (T6, T7; amendment B-588: T7 may only merge the SAFE result-reader tokens, argument models and readers from products/_safe_results.py into the shared registries, the T6 pattern; plan 0012 T5 and T6 after them, B-594: T5 may only merge the SAP2000 add-frame builders and tokens, the section check and the reply-name retarget, T6 may only merge the SAP2000 analysis, result-reader and design BUILDERS, TOKENS and READERS, serialize T5 then T6 or either order with the integrator merging), `_reconcile.py` (T6; plan 0012 T4 for absences-aware state-reader selection from the profile only, B-590).

Reuse (spec §2): everything in plan 0002; the SAFE 22 table reference of the Sasaah repository only as a source of field
keys recorded in `_safe_tables.toml` with status `reference`, never copied code.

## 2. Tasks

**T1 Separation** (spec §4.1). `ProductProfile` and the registry in `products/__init__.py`; `_etabs.py` reduced to its
profile (behavior unchanged, the 0002 suite still passes); `[servers.<name>].product` and `[host_programs.safe]` in
`ServersConfig`; the allowlist header table `[fingerprint]` with one entry per product and the loader's `products` filter;
the build check takes the server's product (in `_buildcheck.py` and in `ServerCheck` of `servers/_session.py`, its
caller since plan 0002 T6b, which picks the fingerprint entry by the server's product); product by model extension.
Touches files that plan 0002 creates or changes, so it starts only after plan 0002 T1, T6, T6b, T7, T8, T8b, T9, T10,
T11, T12, T13, T14 and T19a are merged on `build/v1` (amendment B-418, T19a by B-475; the gate is written as a comment on T1's `depends_on`,
and T3 also waits for 0002 T15 or drops `csi_unlock_model`, T8 for 0002 T17). Before starting, the writer checks with
`git ls-tree` that the 0002 files T1 lists exist, then greps the shared modules (`adapters/_hostport.py`,
`adapters/csi/_session_ops.py`, `_state.py`, `_replies.py`, `_edits.py`, `_tools.py`, `_checks.py`, `_reconcile.py`)
for `ETABS` or `.EDB`. Every hit is reported to the lead before T1 starts, and the lead adds that file to T1's files by
a plan amendment, so that T1 makes it ask the profile; T1 starts only when the grep finds no hit outside T1's files.
`test_no_product_branches_in_shared` carries no exclusions: no later task lists `test_products.py`, and `_state.py`,
`_replies.py` and `_edits.py` are in no other task of this plan, so an exclusion could never be removed in scope. The existing 0002 test that reads the pinned fingerprint
(`test_csi_allowlist.py::test_pinned_fingerprint_from_inventory`) is in T1's files: it changes only in how it reads the
header (the ETABS entry of `[fingerprint]`), never in the value it expects, and it is the regression proof that the
ETABS fingerprint is unchanged. The ETABS engine-stop test `test_session.py::test_build_mismatch_stops_run` exists when
T1 starts: plan 0002 T19a writes it, through the allowlist loader and `build_ports`, before T1 (B-413, B-475). T1
adapts `build_ports` (`adapters/__init__.py`) to the per-product header in the same way, never what that test expects.
The session-level build-check tests of plan 0002 T6b (`test_session.py`, with the pins of `tests/workflow/conftest.py`)
build the check from the allowlist header, so `test_session.py` and `tests/workflow/conftest.py` are in T1's files to
adapt them to the per-product header in the same way, never in what they expect (B-413).

**T2 Fake** (spec §4.1 and 0002 §4.8.3). Test code only: the fake gains a `product` setting; SAFE mode has points, slab
areas, sections, materials, patterns, combinations, joint loads, the area-spring tables, the result tables with
configurable row counts and truncation, `csi_new_model` returning `unsupported_by_version`, and the faults of 0002 plus
`present_units_mm`. Its tool list stays the S-12 schemas; the contract test checks the SAFE entries.

**T3 Allowlist and session** (spec §4.2, §4.8). The SAFE engine-stop test of AC4,
`test_session.py::test_safe_build_mismatch_stops_run`, is T3's (amendment B-475; plan 0002 T19 held it under B-413): it
runs the real engine through the `build_ports` of plan 0002 T19a and fails at T3's base because the SAFE entries and the
pinned SAFE fingerprint do not exist there; its expected error is the one plan 0002 §2 (T19b) defines. SAFE entries (`csi_status`, `csi_launch`, `csi_attach`, `csi_exit`,
`csi_open_model`, `csi_save_model`, `csi_model_info`, `csi_list_points`, `csi_list_areas`, `csi_list_frames`,
`csi_list_grids`, `csi_list_area_sections`, `csi_list_materials`, `csi_list_load_patterns`, `csi_list_load_cases`,
`csi_list_load_combos`, `csi_db_table_read`, `csi_db_table_fields`, `csi_set_point_load`, `csi_add_load_pattern`,
`csi_add_load_combo`, `csi_delete_load_combo`, `csi_assign_area_section`, `csi_run_analysis`, `csi_analysis_status`,
`csi_results_base_reactions`, `csi_results_joint_reactions`, `csi_unlock_model` once plan 0002 T15 has landed) each with
kind, class, effect, action, units, args model, confirm and read-back helper; the SAFE fingerprint computed from the
inventory and pinned; `working_copy` and `restore` for `.FDB` through the 0002 session operations; `AdapterHostPort._record_save`
skips the table read when `profile.tables` is empty so SAFE keeps its prior fingerprint until T5 (AC6, AC7; amendment B-581);
the gap registry in
`_gaps.py` holds the SG-1 to SG-9 ids and messages (`NotImplementedGap`), and T3 wires only SG-1 (AC8) to a step.
SG-7 and SG-8 are raised in T6 (AC16, AC15), SG-6 (`LIMIT_EXCEEDED`) in T7, and T7 wires SG-2, SG-3, SG-4, SG-5 and
SG-9 to their steps (AC24, AC25); T3 does not wire those, so T7's first-commit tests fail at its base (amendment
B-418). T3 also adds the isolation test with two servers. `csi_db_tables_apply`, `csi_delete_object`,
`csi_new_model`, `csi_new_blank_model`, `csi_define_*`, `csi_design_*` and `csi_results_story_drifts` are not SAFE entries.

**T4 Tables** (spec §4.5). `read_table` with units labelling and `truncated` handling, the field-map data with the three
statuses (exact normalized-name matching; none or several matching columns is `INTERNAL`, never a first match), the readers for slab sections, concrete materials and soil supports, the harness kinds they produce. No key is
added whose source is not named in the data file next to it.

**T5 State** (spec §4.4). The SAFE reader: grids, points, areas, frames, load set, joint loads, soil supports, status;
the fingerprint; `locate` and `model_state` for SAFE through the profile; `LIMIT_EXCEEDED` on truncation.

**T6 Loads** (spec §4.3, §4.7, AC14 to AC20). Argument model for `harness.joint_loads/1` import, rows ordered and one
`op_id` each, the zero-row rule, validation of all rows before the first write, the table read-back with the punching
dimension comparison, SAFE integrity issues, reconciliation of a point load from the table, pattern and combination
mapping including `SuperDead`.

**T7 Analysis and results** (spec §4.6). Long-role routing for SAFE, the soil pressure reader with `group` (rows carry `step_type` and `case_type`; a non-unique key is `INTERNAL`), the
base-reaction and joint-reaction readers, analysis status, the `Analysis Messages` read as a `NotImplementedGap` until recorded, and the explicit gaps for
slab design. T7 may only merge the SAFE result-reader tokens, argument models and readers from `products/_safe_results.py` into the shared registries in `csi/_tools.py` (the T6 pattern for `_safe_loads`; amendment B-588), so AC23 reaches the CSI tool port.
T7 wires the steps of SG-2, SG-3, SG-4, SG-5 and SG-9 to their registry entries (AC24, AC25; amendment
B-418). AC25's parametrized cases include SG-8, which T6 already raises and which is green at T7's base; this is
acceptable because the test-first gate counts the test red while any case fails.

**T8 End to end** (spec AC26 to AC28). The cycle test block through the real engine and fake processes, the
crash matrix at each write step, the recorded-reply contract tests (run on every applicable committed recording under
`acceptance/recordings` and on the synthetic recording produced by record mode for that adapter; verified against the
real server only once the owner commits SAFE recordings, spec §12 item L14; amendment B-573), the record script
gaining a SAFE scenario, and the SAFE part of `docs/local-testing.md` (spec §12 L1 to L15).

**T9 Slab design (blocked).** Starts only after the owner has run L5 and L11 and committed recordings of the result tables
and of `csi_design_run` on SAFE, and decided whether `csi_design_run` and a design read are allowlisted for SAFE. Then:
the field-map entries (`unknown` to `reference` or `candidate`), the `kind` of the design run, the readers, and the
gap tests for SG-5 replaced because the accepted behavior changes (a spec change, not a test changed to pass). If the
local test shows that no allowlisted tool can run the SAFE designer, this task is cancelled and SG-5 stays.

## 3. Dependencies

- Runtime: none new (`mcp`, `eng-contract`, `pydantic` as in plan 0002). Development: none new.
- Work items: plan 0002 T1 (config), T6 and T6b (allowlist, build check), T7 (guard), T8 to T10 (framework, errors, session
  operations), T11 to T14 (state, edits, analysis, reconciliation) before T1 of this plan; T15 (ADR-0031 switch) before the
  `csi_unlock_model` SAFE entry; T19a (port wiring and the ETABS engine stops) before T1 of this plan, because T1 adapts
  `build_ports` and T3 writes the SAFE engine stop of AC4 (`test_session.py::test_safe_build_mismatch_stops_run`) next
  to the ETABS one (B-475); T17 (record mode) before T8 of this plan.
  Engine plan 0001: T3 (the SAFE engine stop) and T8 of this plan run the real engine and wait for engine 0001 T13, T15,
  T16, T16b and T19 (T13 brings in T9 to T12; T16b, B-499), as plan 0002 T19a does (B-413, B-475). No cycle: plan 0002 waits for no task of
  this plan; T1 to T3 wait for plan 0002 T1 to T14 and T19a (0002 T15 only for T3's conditional `csi_unlock_model` entry).
- First live run (amendment B-475, lead decision D-32): T1 to T3 are off its path (it runs ETABS only) and are not
  weakened; they return before T4, which the footing workflow (plan 0010 T10 and T11, through T5 to T7) and plan 0012
  T1 need.
- Specs: `eng-contract` 0.1.0 merged. The edit-cycle workflow spec 0007 is not needed; the footing workflow spec uses the
  kinds and gaps defined here.
- Owner decisions that do not block T1 to T8: Q1 to Q7 of the spec (the recommendations are implemented). Q8 (whether a candidate-mapped soil-pressure result may feed a verdict) is for the footing-workflow spec and does not affect T1 to T9.
- External amendment (B-586, from plan 0012 T3 / the B-247 writer): plan 0012 T3 amends
  `packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py` and
  `packages/eng-harness/src/eng_harness/adapters/csi/products/_safe.py` so the gap and step-gap registries live on
  `ProductProfile` (`profile(product).step_gaps`); T3 may only move those registries onto the profile (no other change);
  required for spec 0008 AC2 (`test_no_product_branches_in_shared`). Recorded in this plan's `_safe.py` and
  `products/__init__.py` serialization above.
- External amendment (B-590, from plan 0012 T4 / the B-248 writer): plan 0012 T4 amends
  `packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py` so `ProductProfile` carries
  `declared_absences` (wired from `_sap2000.DECLARED_ABSENCES`), and
  `packages/eng-harness/src/eng_harness/adapters/csi/_reconcile.py` so it selects the absences-aware state reader from
  the profile (no product-name branch; spec 0008 AC2); T4 may only make those profile-field and reader-selection
  changes. Recorded in this plan's `products/__init__.py`, `_hostport.py` and `_reconcile.py` serialization above. Plan 0002 records
  the matching external amendment for `_hostport.py`, `products/__init__.py` and `csi/_reconcile.py`.
- External amendment (B-594, from plan 0012 T5 and T6 / the B-249 and B-250 writers): plan 0012 T5 amends
  `packages/eng-harness/src/eng_harness/adapters/csi/_tools.py` so it may only merge the SAP2000 add-frame builders
  and tokens, the section check and the reply-name retarget into the shared registries (no product-name branch), and
  amends `packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py` so `ProductProfile` carries
  `add_frame_naming` (wired from `_sap2000`; spec 0008 AC2); plan 0012 T6 amends the same `_tools.py` so it may
  only merge the SAP2000 analysis, result-reader and design BUILDERS, TOKENS and READERS (the B-588 pattern);
  T5 and T6 both edit `_tools.py` (serialize T5 then T6, or either order with the integrator merging); required for
  SAP2000 AC11–AC13 and AC14–AC16 through the CSI tool port. Recorded in this plan's `_tools.py` and
  `products/__init__.py` serialization above. Plan 0002 records the matching external amendment for `csi/_tools.py`
  and `products/__init__.py`.

## 4. Verification

- Local gate per task (`uv run eng-gate check` once available; until then ruff, mypy strict and pytest with coverage from
  `packages/eng-harness/`); the pull request links its CI run.
- Fake-host workflow tests run the SAFE-mode fake as a real process through the harness launcher (POSIX in Linux CI).
- Needs local test (spec §12, listed in `docs/local-testing.md`): everything that drives `sasaah-csi-mcp` and SAFE, in
  particular the table columns (L5), the soil pressure row counts and signs (L6, L7), the point-load semantics (L8), the
  analysis timeout (L10), and slab design (L11). No claim of a live result is made by any task.
- Review: correctness, Python, type-design, silent-failure and test lenses on every task; R1 review against the spec's
  units, read-back and reconciliation rules on T3, T6 and T7; the security lens on T3 (allowlist as the barrier against
  `csi_db_tables_apply` and the other escape hatches). Second-family review and owner approvals are `awaiting owner`
  (ADR-0028 §4).

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; reverting it removes it and its dependants. T1 changes the
allowlist header shape and the ETABS profile: its revert restores the single fingerprint, and the plan 0002 suite (with the tests
T1 adapts) is its regression test. Nothing here writes to a host program in CI. A wrong field key is fixed forward in the data file; a SAFE
build the allowlist was not tested with is refused by the build check rather than run.
