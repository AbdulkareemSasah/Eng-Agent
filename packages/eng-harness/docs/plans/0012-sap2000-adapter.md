---
id: plan-b081-sap2000-adapter
issue: "B-081"
spec: packages/eng-harness/docs/specs/0012-sap2000-adapter.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r3]  # r3 from the public_modules entries in pyproject.toml (amendment B-356)
tasks:
  - id: T1
    title: SAP2000 server section, product by extension, profile, allowlist entries and pinned fingerprint
    # Amendment (B-413, documents only): test_sap2000_build_mismatch_stops_run runs the real engine and build_ports, so T1
    # starts after plan 0002 T19 (and engine plan 0001 T13, T15, T16, T19); it fails at T1's base for want of the SAP2000 product T1 adds.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products and more (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/servers/_config.py"
      - "packages/eng-harness/src/eng_harness/adapters/_allowlist.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_allowlist.toml"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/__init__.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_sap2000.py"
      - "packages/eng-harness/tests/unit/servers/test_config.py"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py"
      - "packages/eng-harness/tests/unit/adapters/test_products.py"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/servers/test_config.py::test_sap2000_server_section"
      - "packages/eng-harness/tests/unit/adapters/test_products.py::test_product_by_extension_three_products"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_sap2000_entries_match_coverage_table"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_sap2000_gap_tools_refused"
      - "packages/eng-harness/tests/unit/adapters/test_allowlist.py::test_escape_hatches_refused_for_sap2000"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_sap2000_against_inventory"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_sap2000_fingerprint_from_inventory"
      - "packages/eng-harness/tests/unit/servers/test_buildcheck.py::test_fingerprint_three_products"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_sap2000_build_mismatch_stops_run"
    covers: [AC1, AC2, AC3]
    depends_on: []
  - id: T2
    title: Synthetic SAP2000 mode of the CSI fake and its schema check
    files:
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py"
    max_changed_lines: 60
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/contract/test_csi_allowlist.py::test_sap2000_fake_schemas_match_inventory"
    covers: [AC19]
    depends_on: [T1]
  - id: T3
    title: Session operations for .SDB, SAP2000 gap entries and product isolation
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_session_ops.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_gaps.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_sap2000.py"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_session_ops.py"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_isolation.py"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_gaps.py"
      - "packages/eng-harness/tests/workflow/adapters/test_csi_session_ops.py"
      - "packages/eng-harness/tests/workflow/servers/test_guard.py"
    max_changed_lines: 300
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_session_ops.py::test_working_copy_sdb"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_isolation.py::test_epochs_independent"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_gaps.py::test_new_model_gap"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_gaps.py::test_gaps_not_implemented"
    covers: [AC4, AC5, AC6, AC17]
    depends_on: [T1, T2]
  - id: T4
    title: Table data (all unknown), model-state reader with declared absences, fingerprint
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_sap2000_tables.toml"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_sap2000_state.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_sap2000.py"
      - "packages/eng-harness/tests/unit/adapters/test_sap2000_tables.py"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_state.py"
      - "packages/eng-harness/tests/property/test_fingerprint.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/adapters/test_sap2000_tables.py::test_unknown_tables_are_gaps"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_state.py::test_kinds_and_fingerprint"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_state.py::test_declared_absences"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_state.py::test_other_unsupported_raises"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_state.py::test_truncated_raises"
      - "packages/eng-harness/tests/property/test_fingerprint.py::test_sap2000_order_independent_and_edit_sensitive"
    covers: [AC7, AC8, AC9, AC10]
    depends_on: [T3]
  - id: T5
    title: Add-frame edit with name from the reply, typed read-back edits, reconciliation by geometry
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_sap2000_edits.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_sap2000.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_reconcile.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/_checks.py"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_edits.py"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_reconcile.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_edits.py::test_add_frame_name_from_reply"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_reconcile.py::test_add_frame_outcomes"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_edits.py::test_typed_readback_edits"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_edits.py::test_pattern_partial_readback"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_edits.py::test_table_readback_edits_are_gap"
    covers: [AC11, AC12, AC13]
    depends_on: [T4]
  - id: T6
    title: Analysis, result readers and design run and results for SAP2000
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.adapters, eng_harness.adapters.csi, eng_harness.adapters.csi.products (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_sap2000_results.py"
      - "packages/eng-harness/src/eng_harness/adapters/csi/products/_sap2000.py"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_analysis.py"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_results.py"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_design.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_analysis.py::test_long_role_save_first"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_results.py::test_reply_kinds_and_units"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_design.py::test_steel_and_concrete_run"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_design.py::test_concrete_non_beam_results_gap"
      - "packages/eng-harness/tests/workflow/adapters/test_sap2000_design.py::test_other_kinds_refused"
    covers: [AC14, AC15, AC16]
    depends_on: [T4]
  - id: T7
    title: End-to-end block, crash matrix, recorded-reply contract tests and SAP2000 local-testing part
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/tests/workflow/test_sap2000_cycle.py"
      - "packages/eng-harness/tests/replay/test_sap2000_resume.py"
      - "packages/eng-harness/tests/contract/test_csi_recordings.py"
    max_changed_lines: 150
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/test_sap2000_cycle.py::test_cycle_steps"
      - "packages/eng-harness/tests/replay/test_sap2000_resume.py::test_crash_matrix"
      - "packages/eng-harness/tests/contract/test_csi_recordings.py::test_sap2000_adapter_on_recordings"
      - "packages/eng-harness/tests/contract/test_csi_recordings.py::test_sap2000_synthetic_matches_recordings"
    covers: [AC18, AC19]
    depends_on: [T5, T6]
---

# Implementation plan: SAP2000 through the CSI adapter

## 1. Approach

SAP2000 is the third product of the CSI adapter: a profile, allowlist entries, a fake mode, readers and gap entries,
on the framework of [plan 0002](0002-servers-and-adapters.md) and the product mechanics of [plan 0008](0008-safe-adapter.md)
(profile registry, per-product fingerprint, `[servers.<name>].product`, table framework, gap module). Nothing is reused
by copying. Risky parts first: the allowlist and the pinned fingerprint (T1, the barrier against escape hatches), then
the state reader with declared absences (T4) and the add-frame reconciliation by geometry (T5), because the host ignores
the requested frame name. Every table is `unknown`, so no task reads or writes a table; that work is T8.

## 2. Tasks

**T1 Product, allowlist, fingerprint** (AC1 to AC3). The `[servers.csi_sap2000]` rules, `.SDB` resolution, the SAP2000
profile skeleton, the allowlist entries exactly as the coverage table of the spec §4.1 lists them (a test compares
the two), the pinned fingerprint computed from the S-12 inventory, and the build-mismatch stop. The stop
(`test_session.py::test_sap2000_build_mismatch_stops_run`) runs the real engine through `build_ports`, which plan 0002
T19 adds and which writes the ETABS and SAFE stops into the same file, so T1 starts after 0002 T19; it fails at T1's
base because the SAP2000 server section, product and pinned fingerprint (`servers/_config.py`, `_allowlist.toml`,
`products/_sap2000.py`) do not exist there (test-first TF004; B-413).

**T2 Fake mode** (AC19). SAP2000 mode of the test-only fake: schemas from the inventory, `unsupported_by_version` for
stories, grids, frame details, joint export, story drifts and `csi_new_model`, frame replies without `label` and `story`,
renamed added frames, no sections in a blank model.

**T3 Session and gaps** (AC4 to AC6, AC17). Working copy of a `.SDB`, the session-operation suite parametrized over
three products, epoch isolation, gaps SP-1, SP-2, SP-5, SP-7, SP-8 as `NotImplementedGap`.

**T4 State** (AC7 to AC10). `_sap2000_tables.toml` with every entry `unknown`, the state reader with declared absences
(`LEVELS_NOT_AVAILABLE`, `GRID_NOT_AVAILABLE`), truncation, the fingerprint over the profile's kinds.

**T5 Edits** (AC11 to AC13). Add frame with the name from the reply, assign section, area, patterns and combinations with
typed read-back, the table-read-back edits as gap SP-4, reconcile by geometry.

**T6 Analysis, results, design** (AC14 to AC16). Long-role analysis after save, the result kinds, steel and concrete
design runs, steel results, concrete non-beam results as SP-3, `aluminum` and `coldformed` refused before any call.

**T7 End to end** (AC18, AC19). Cycle block, crash matrix, recorded-reply contract tests (skipped with a reason until
the owner commits SAP2000 recordings), the SAP2000 part of `docs/local-testing.md` (spec §12 L1 to L8). If plan 0008 T8
has not created that file, T7 creates it with the SAP2000 part only.

**T8 Tables and loads (blocked, not in the front matter).** Starts only after the owner has run L4 and committed
recordings, and decided Q3 and Q5. Then: table entries `unknown` to `reference` or `candidate`, the load and
restraint edits with their read-back, replacing the SP-4 gap tests (a spec change, not a test changed to pass). Its own
plan amendment lists its files and budget. If no recording is committed, SP-4 stays.

## 3. Dependencies

- Runtime: none new. Development: none new.
- Plans: plan 0002 T1, T6 to T15, T17 and T19 (T19 for the SAP2000 engine stop of T1, B-413; it brings in engine plan
  0001 T13, T15, T16 and T19); plan 0008 T1 (profile registry, config and fingerprint per product), T2
  (fake framework) and T3 (session operations, gap module) before T1 of this plan; plan 0008 T4 (table framework)
  before T4. Specs: `eng-contract` 0.1.0 merged; the column workflow spec (B-083) uses the kinds and gaps here.
- Owner decisions that do not block T1 to T7: Q1 to Q6 of the spec (the recommendations are implemented).

## 4. Verification

- Local gate per task (`uv run eng-gate check` once available; until then ruff, mypy strict and pytest with coverage from
  `packages/eng-harness/`); the pull request links its CI run.
- Fake-host workflow tests run the SAP2000-mode fake as a real process through the harness launcher.
- Needs local test (spec §12, listed in `docs/local-testing.md`): everything that drives `sasaah-csi-mcp` and SAP2000.
  No task claims a live result.
- Review: correctness, type-design, silent-failure and test lenses on every task; R1 review against the spec's
  evidence rules and reconciliation on T4 and T5; the security lens on T1 (allowlist). Second-family review and owner
  approvals are `awaiting owner` (ADR-0028 §4).

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; reverting it removes it and its dependants. T1 only adds a
product, so its revert leaves ETABS and SAFE (and their pinned fingerprints) untouched. A wrong table or frame
behavior is fixed forward in the data file or profile; a SAP2000 build the allowlist was not tested with is refused by the
build check rather than run.
