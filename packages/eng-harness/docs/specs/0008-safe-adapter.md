---
id: spec-0008-safe-adapter
issue: "B-073"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1]
---

# Spec 0008: eng-harness, SAFE through the CSI adapter

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-04

This spec adds SAFE as the second product of the CSI adapter of [spec 0002](0002-servers-and-adapters.md) ("0002 §n")
for phase 2 (foundations, [19](../../../../design/docs/architecture/19-roadmap-and-spikes.md) §1). It follows
[ADR-0024](../../../../design/docs/adr/0024-harness-on-existing-sasaah-servers.md): the harness is a client of
`sasaah-csi-mcp`; no SAFE server is built, and [06](../../../../design/docs/architecture/06-csi-servers.md) §8 (a
`csi-safe-mcp` with soil supports, punching output and strips) is not met by the server and is not built. Tool facts
come from the [S-12 report](../../../../spikes/S-12-sasaah-tool-inventory/REPORT.md) ("S-12 §n") and
`inventory/sasaah-csi-mcp.json` at Sasaah commit `61da80f61a6562c8e3553168056bc107e3f93013`, and from a read-only
reading of the Sasaah engine and session reports at that same commit (the SAFE parts S-12 did not cover: the SAFE 22
table reference `docs/csi-mcp-server/reference/safe22-all-tables.json`, `CsiModel.cs`, and the footing-design command-line
tool with `agent-sessions/*etabs-safe*` reports). The contract API is
[eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract §n"); the engine ports are
in [spec 0001](0001-engine.md) ("engine §n"). Everything here that needs SAFE is "needs local test" (§12). Details the
architecture leaves open are marked **[added]** and listed in §11. The edit-cycle workflow spec 0007 was not on
`build/v1` when this was written; nothing here depends on its section numbers.

## 1. Problem

The footing workflow (the second workflow, [10](../../../../design/docs/architecture/10-structural-codes.md) §9, phase 2 of
[19](../../../../design/docs/architecture/19-roadmap-and-spikes.md)) needs SAFE to cross-check what the code packs compute: column loads on a footing model, soil pressures under a soil-spring
support, and the host's punching and slab-design output. The Sasaah sessions that did ETABS-to-SAFE work show where the
time and the risk went: 759 column loads moved by table writes through `csi_db_tables_apply` (an excluded escape hatch),
about 76 `csi_invoke` or script calls in one session (the report's own estimate), 31 footing areas deleted and re-added by hand (18 of them first with the
wrong orientation), an ETABS hung for about 30 minutes by repeated analysis requests, and a soil-pressure result that looked
wrong because the loads were on other combinations (agent-sessions `2026-11-03_0145_etabs-safe_loads-and-footings`,
`..._model-build-edit`, `2026-10-10_0010_etabs-safe_f2k-export-diagnosis`). The tools that `sasaah-csi-mcp` allows without
escape hatches cover part of this (S-12); the rest must be listed as gaps, never worked around.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| 0002 CSI adapter (framework, error table, roles, guard, ledger, state reader, reconciliation) | Product-neutral except `products/_etabs.py` and the `products` field of each allowlist entry (0002 §4.5.1, §4.6, §4.6.5) | Reused unchanged; SAFE adds a product profile, allowlist entries, table readers and kinds (§4) |
| S-12 inventory, 83 tools | The `target` parameter of the tools names "ETABS, SAFE or SAP2000"; SAFE-aware tool descriptions: `csi_list_stories` ("ETABS and SAFE only"), `csi_add_area_by_coord` and `csi_move_area` (written for SAFE slabs), `csi_capture_window` (bridge targets only) | The allowlist is chosen tool by tool (§4.3) |
| Sasaah `tools/footing-design` (CLI over `Sasaah.Csi.Engine`) | Builds a SAFE model for isolated footings from an analysed ETABS model: sizing, ACI 318-19 checks, grouping, a SAFE model with soil springs, loads and a service combination, all through engine calls plus table imports | Not adopted as an adapter tool here: not inventoried by S-12, embeds engineering decisions (its code edition differs from the platform's ACI 318-14 scope, 10 §9) and builds with table writes inside its own process. Open question Q4 |
| Sasaah `Sasaah.Safe.Bridge.Plugin` (in-process plugin, TCP) | Lets the server attach to a SAFE instance the engineer started; `csi_open_model`, `csi_new_*`, `csi_exit` and deletes are refused on bridge targets (S-12 §2) | Not used: the harness drives instances it launched (0002 §4.4) |
| SAFE 22 table reference (Sasaah, 283 tables) | Field keys with units for importable tables; result tables (`Soil Pressures`, `Base Reactions`, `Concrete Slab Design - Punching Shear Data`, ...) are listed with **no fields** | Keys of importable tables are used as `reference` (confirmed by a local test); result-table columns are `candidate` or unknown (§4.5) |
| `csi_db_table_read` (read-only, `row_limit` at most 2000) | The only route to results and definitions without a typed tool; has a `group` filter and no case filter | Used through typed readers with explicit field maps; never a generic table API for workflows |

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Synthetic SAFE fake" is the SAFE mode of the test-only CSI fake of
0002 §4.8.3 (lead decision D-5), run as a real process over stdio. "Fake-host workflow test" is a test block run by the
real engine with the real `ToolPort` and `HostPort` against the fake.

### 3.1 Product selection and separation

- AC1. Given a `harness.toml` with `[servers.csi_safe]` (`product = "SAFE"`, own `host_key`, own roles and timeouts, the
  same executable path as `[servers.csi]`) and `[host_programs.safe]`, when loaded, then `ServersConfig` holds both
  servers; a server without `product`, an unknown product, two servers with one `host_key`, or a server whose build pin
  differs from another server of the same executable path give `ConfigError` naming the key. Test:
  `tests/unit/servers/test_config.py::test_safe_server_section`, `::test_product_and_host_key_rules`.
- AC2. Given a model file name, when the product is resolved, then `.FDB` is SAFE and `.EDB` is ETABS; an unknown
  extension, or a product different from the one of the server the step addresses, gives `INVALID_ARGUMENT` (`field:
  model`) before any call; a shared module never branches on a product name. Tests:
  `tests/unit/adapters/test_products.py::test_product_by_extension`, `::test_no_product_branches_in_shared`.
- AC3. Given the allowlist, when loaded for a product, then only entries that list that product are served; every SAFE
  entry has the fields of 0002 AC16; a tool without SAFE in `products` (for example `csi_results_story_drifts`) gives
  `INVALID_ARGUMENT` on a SAFE server; the escape-hatch deny list of 0002 §4.5.1 is applied for every product
  (`csi_db_tables_apply` included). Tests: `tests/unit/adapters/test_allowlist.py::test_safe_entries_complete`,
  `::test_tool_not_served_for_product`, `::test_escape_hatches_refused_for_safe`,
  `tests/contract/test_csi_allowlist.py::test_safe_against_inventory`.
- AC4. Given the S-12 inventory, when the tool-list fingerprint is computed per product (0002 §4.3.4 item 4, over the
  allowlisted tools that list the product), then each equals the value pinned in the allowlist header; adding SAFE
  entries leaves the ETABS fingerprint unchanged; a SAFE server is checked against the SAFE fingerprint and a mismatch
  stops the run before any write (engine AC44). Tests: `tests/unit/servers/test_buildcheck.py::test_fingerprint_per_product`,
  `tests/contract/test_csi_allowlist.py::test_safe_fingerprint_from_inventory`,
  `tests/workflow/servers/test_session.py::test_safe_build_mismatch_stops_run`.
- AC5. Given an ETABS server and a SAFE server in one run and a timeout injected on the ETABS server, then
  `session_epoch` of the ETABS host key increases and that of the SAFE host key does not; launch ownership, wedge state
  and the pending reconciliation of one product never mark the other. Test:
  `tests/workflow/adapters/test_safe_isolation.py::test_epochs_independent`.

### 3.2 Session and files

- AC6. Given a `.FDB` model, when `working_copy` runs, then a hidden SAFE instance is launched on the `csi_safe` main
  role (`csi_launch` with `product: "SAFE"`), locked, the copy opened with `csi_open_model(confirm)`, the copy's hash
  equals the original's, the expected units are recorded and the identity is `derived_from` the original (0002 AC30);
  the copy includes the companion files the profile lists. Test:
  `tests/workflow/adapters/test_safe_session_ops.py::test_working_copy_fdb`.
- AC7. Given the session-operation suite of 0002 (AC15, AC30), when run with `product = SAFE`, then it passes: close only
  what was started, fallback after a timeout, restore after a timeout, identity resolution. Test:
  `tests/workflow/adapters/test_csi_session_ops.py` (parametrized over products), `tests/workflow/servers/test_guard.py`
  (parametrized).
- AC8. Given a workflow step that needs a new SAFE model, when called, then `NotImplementedGap` (`NOT_IMPLEMENTED`, gap
  SG-1) is raised and no call is sent; `csi_new_model` and `csi_new_blank_model` are not served for SAFE. Test:
  `tests/workflow/adapters/test_safe_gaps.py::test_new_model_gap`.

### 3.3 Model state

- AC9. Given a SAFE model in the synthetic fake, when the model-state reader runs, then it produces `model.grid_system/1`,
  `model.area_placements/1`, `model.frame_placements/1`, `harness.model_points/1`, `model.sections/1` (slab sections),
  `model.materials/1`, `model.load_set/1` (patterns and combinations), `harness.joint_loads/1`,
  `harness.safe_soil_supports/1` and the status, all validating, and a fingerprint that is equal for the same state read
  twice and differs after each edit kind of §4.4. Tests: `tests/workflow/adapters/test_safe_state.py::test_kinds_and_fingerprint`,
  `tests/property/test_fingerprint.py::test_safe_order_independent_and_edit_sensitive`.
- AC10. Given a list or table read with `truncated: true`, then `LIMIT_EXCEEDED` with the received count; no partial
  payload is stored. Test: `tests/workflow/adapters/test_safe_state.py::test_truncated_raises`.
- AC11. Given the tables `Slab Property Definitions`, `Material Properties - General`, `- Basic Mechanical Properties`
  and `- Concrete Data`, when read, then slab sections become `model.sections/1` entries with `thickness_mm` converted from
  the present units, property types `Slab`, `Drop`, `Stiff`, `Mat`, `Footing` become kind `slab`, types `Ribbed` and
  `Waffle` are left out with an `info` issue `SECTION_TYPE_NOT_MAPPED`, and concrete materials carry `fc_MPa` and
  `gamma_kN_m3`; other material types are kind `other`. Test: `tests/unit/adapters/test_safe_tables.py::test_sections_and_materials`.
- AC12. Given the tables `Spring Property Definitions - Area Springs` and `Area Assignments - Area Springs`, when read,
  then `harness.safe_soil_supports/1` lists each property with its three stiffnesses and the nonlinear option of U3, and
  each area with its property name or `null` for "None". Test: `tests/unit/adapters/test_safe_tables.py::test_soil_supports`.
- AC13. Given a table whose reply lacks a column the field map requires, or whose map entry is unknown (§4.5), then
  `INTERNAL` with an `incident_id` naming the table and the missing logical column when the entry is `reference` or
  `candidate`, and `NotImplementedGap` when the entry is `unknown`; the columns seen are stored as failure evidence. Given
  a reply in which two or more columns match one logical column, then `INTERNAL` naming the logical column and the
  matching columns, never a first match. Tests: `tests/unit/adapters/test_safe_tables.py::test_missing_column`,
  `::test_ambiguous_column`, `::test_unknown_table_is_gap`.

### 3.4 Loads and edits

- AC14. Given a `harness.joint_loads/1` reference, when imported, then for each row one `csi_set_point_load` is sent with
  `name`, `load_pattern`, `force = [FX, FY, FZ]`, `moment = [MX, MY, MZ]`, `units = "kN_m_C"`, the explicit `target`,
  values converted from `kN` and `kN.m` by `eng_contract.units`, each with its own `op_id`; the provenance holds the
  reference, not the values; a literal where a reference is required is refused (engine invariant 2). Test:
  `tests/workflow/adapters/test_safe_loads.py::test_set_point_load_mapping`.
- AC15. Given a row whose six values are all zero, when imported, then nothing is sent for it if the table
  `Joint Loads Assignments - Force` shows no load for that joint and pattern (warning `ZERO_LOAD_SKIPPED`), and
  `NotImplementedGap` (gap SG-8) if it shows a load (the host rejects a zero assignment, so it cannot be cleared). Test:
  `tests/workflow/adapters/test_safe_loads.py::test_zero_rows`.
- AC16. Given a row naming a joint or a pattern that does not exist, when imported, then `NOT_FOUND` (`field` names the
  row) before the first write of the batch; no partial batch is written. Given a row with `punch_x_mm` or `punch_y_mm`
  not null, then `NotImplementedGap` (gap SG-7). Tests: `tests/workflow/adapters/test_safe_loads.py::test_missing_joint_no_partial_write`,
  `::test_punch_dimensions_gap`.
- AC17. Given the model present units set to millimetres (synthetic fault `present_units_mm`), when loads are imported,
  then the loads land in kN and kN.m (the token is always passed), and the read-back finds equality within the basis
  tolerance. Test: `tests/workflow/adapters/test_safe_loads.py::test_units_token_independent_of_present_units`.
- AC18. Given a successful import, when `check_model` runs, then every written load is read back from
  `Joint Loads Assignments - Force` and compared; a mismatch is `READBACK_MISMATCH` (error); the punching dimensions of
  each loaded joint read before and after the write must be equal, else `READBACK_MISMATCH` naming `punch_x_mm` or
  `punch_y_mm`; SAFE integrity issues are produced per §4.7. Tests: `tests/workflow/adapters/test_safe_readback.py::test_load_mismatch`,
  `::test_punch_dimension_change_detected`, `::test_safe_integrity_issues`.
- AC19. Given a `csi_set_point_load` in flight at a timeout, when reconciled, then the adapter reads the joint's loads for
  the pattern and answers `applied` (equal to the request), `not_applied` (equal to the pre-image, including "no load"),
  else `unknown`, per 0002 §4.5.7; a batch is reconciled row by row from the ledger and no row is repeated before its
  answer. Test: `tests/workflow/adapters/test_safe_reconcile.py::test_point_load_outcomes`.
- AC20. Given load patterns and combinations to add, when applied on SAFE, then the argument mapping of 0002 §4.6.2 holds;
  additionally pattern type `superimposed_dead` maps to `SuperDead` for SAFE only (evidence in §4.4), and
  `roof_live` stays a gap (H-G3). Test: `tests/workflow/adapters/test_safe_edits.py::test_patterns_and_combos`.

### 3.5 Analysis and results

- AC21. Given a SAFE analysis, then the call goes to the `long` role of the SAFE server with its own configured timeout,
  after the engine's save; the model is `locked` afterwards and an edit before `csi_unlock_model` is refused as in 0002
  AC29. Test: `tests/workflow/adapters/test_safe_analysis.py::test_long_role_save_first_and_locked`.
- AC22. Given the tables of §4.6 and a case list, when soil pressures are read, then `harness.safe_soil_pressures/1` holds
  the rows (`area`, `element` and `joint` each when the table has the column and `null` otherwise, `case`, `step_type`
  and `case_type` each when the table has the column and `null` otherwise, pressure in `kPa` converted from the present
  units), `field_map_status` is `candidate` until L5 promotes the entry (§4.5),
  `sign_convention` is `host_unconfirmed/1`, no absolute value is taken, `group` is passed when requested, and a
  `truncated` reply gives `LIMIT_EXCEEDED` (gap SG-6) with the `group` hint. Given an envelope combination or a
  multi-step case, which the table reports as several rows (Max and Min) told apart only by the step-type column, then
  every row carries its `step_type` and none is dropped or merged; given a reply in which (`area`, `element`, `joint`,
  `case`, `step_type`) is not unique, then `INTERNAL` with the columns seen, never a silent ambiguity. Tests:
  `tests/workflow/adapters/test_safe_results.py::test_soil_pressure_rows`, `::test_soil_pressure_truncated`,
  `::test_soil_pressure_group`, `::test_soil_pressure_step_type_and_unique_key`.
- AC23. Given `csi_results_base_reactions` and `csi_results_joint_reactions`, then the replies become
  `harness.base_reactions/1` and `forces.joint_reactions/1` in canonical units; the moment reference of the base
  reactions is `host_unconfirmed/1`. `csi_analysis_status` becomes `harness.csi_analysis_status/1` (0002 §4.6.1 step 11). Reading the table
  `Analysis Messages` gives `NotImplementedGap` as for any `unknown` entry (AC13, §4.5) until an owner recording (L5) sets
  its keys. Tests: `tests/workflow/adapters/test_safe_results.py::test_base_and_joint_reactions`, `::test_analysis_status`,
  `::test_analysis_messages_unknown_is_gap`.
- AC24. Given a request to run SAFE slab design (flexure, shear, punching) or to read its results, then
  `NotImplementedGap` (gap SG-5), nothing is sent; `csi_design_run` and `csi_design_results` are not served for SAFE until plan task T9 (blocked on local tests L5 and L11) replaces
  this criterion with the accepted behavior, tested by `tests/workflow/adapters/test_safe_slab_design.py::test_design_run_and_punching_rows`. Test:
  `tests/workflow/adapters/test_safe_gaps.py::test_slab_design_gap`.
- AC25. Given each remaining gap of §4.8 (SG-2, SG-3, SG-4, SG-8, SG-9), then the step raises `NotImplementedGap` with its
  gap id and nothing is sent. Test: `tests/workflow/adapters/test_safe_gaps.py::test_gaps_not_implemented` (parametrized).

### 3.6 End to end and recordings

- AC26. Given a test block that launches the synthetic SAFE, opens a copy, reads the state, imports loads, saves, runs
  the analysis, reads soil pressures and base reactions, and ends the run, then the journal holds every step, check and
  save, and only the started instance is closed. Test: `tests/workflow/test_safe_cycle.py::test_cycle_steps`.
- AC27. Given the same block, when the engine is killed at each write step (loads, save, analysis) and resumed, then it
  reconciles and completes without a repeated load write. Test: `tests/replay/test_safe_resume.py::test_crash_matrix`.
- AC28. Given SAFE recordings, then the adapter's contract tests pass on them and the synthetic SAFE fake gives the same
  reply shape and error codes for every recorded operation; the fake's tool list for SAFE entries equals the S-12
  inventory schemas. Tests: `tests/contract/test_csi_recordings.py::test_safe_adapter_on_recordings`,
  `::test_safe_synthetic_matches_recordings` (skip with reason when no recording exists),
  `tests/contract/test_csi_allowlist.py::test_safe_fake_schemas_match_inventory`.

## 4. Design

### 4.1 Product separation (0002 §4.6, §4.6.5)

A **product profile** is the only product-specific code: `adapters/csi/products/_safe.py` and `_etabs.py` each export a
frozen `ProductProfile` registered in `products/__init__.py` **[added]**:

| Field | Meaning |
|---|---|
| `name` | `"ETABS"`, `"SAFE"`; the value of `csi_launch.product` |
| `model_extensions` | `(".EDB",)`, `(".FDB",)` (`.FDB` evidence: opened live by the Sasaah footing tool; the `csi_open_model` schema text lists only `.EDB`, `.SDB`, `.MDB`, S-12) |
| `host_executables` | from `[host_programs.<name>]`; Sasaah names `SAFE.exe` |
| `companion_globs` | files next to the model file that belong to it (the profile's list; empty until the local test L2) |
| `state_reader`, `result_readers`, `edit_kinds` | the product's readers and edit kinds (§4.4, §4.6); an unlisted one is `NotImplementedGap` |
| `table_fields` | path of the field-map data (§4.5) |

Everything else (framework, error table, timeouts, ledger, guard, reconciliation, ADR-0031 handling) is shared and
unchanged. Rules: a profile imports nothing from the other profile; a shared module never branches on a product name,
it asks the profile (a lint test, `tests/unit/adapters/test_products.py::test_no_product_branches_in_shared`).

**One server section per product [added]**: `[servers.csi_safe]` runs the same executable with `product = "SAFE"`, its own
`host_key`, roles, timeouts and `build` pin. Reason: each `sasaah-csi-mcp` process has one COM worker, one current target
and one cached session, and a `timeout` abandons the worker and invalidates that session (S-12 §5); a long ETABS analysis
or a wedged ETABS would otherwise stall or de-own the SAFE instance. Q1.

**Allowlist [added]**: the header's `tool_fingerprint` becomes a table `[fingerprint]` with one entry per product, each
computed over the entries that list the product (0002 §4.3.4 item 4); `products` on an entry may list several products.
SAFE needs no change of the forbidden options (0002 §4.2 item 3): `--disable-script` stays required, and
`csi_db_tables_apply` stays listed by the server and refused by the loader. The pinned ETABS value is unchanged, so the
existing 0002 tests that read the header change only in how they read it, not in what they expect (plan T1).

### 4.2 Footing workflow steps on SAFE

What the footing workflow (phase 2; the workflow and its block `design_isolated_footing`, 11 §2, are a separate spec)
needs from the adapter, in order:

| # | Step | Tools (role) | Neutral kind or result |
|---|---|---|---|
| 1 | Server build | `csi_status`, `tools/list` on the SAFE server | §4.1 fingerprint |
| 2 | Working copy of the engineer's SAFE model | `csi_launch(product="SAFE", visible=false)` (main), `csi_open_model`, `csi_save_model` | `HostPort.working_copy` |
| 3 | Read the model | §4.4 | `model.*`, `harness.*` kinds |
| 4 | Column loads in | `csi_set_point_load`, `csi_add_load_pattern`, `csi_add_load_combo`, `csi_delete_load_combo` (main) | input `harness.joint_loads/1` (§4.3) |
| 5 | Read back and check | table reads, `csi_list_*` | `issues.model_check/1` |
| 6 | Save, analysis | `csi_save_model`, `csi_run_analysis` (long), `csi_analysis_status` | `harness.csi_analysis_run/1`, `harness.csi_analysis_status/1` |
| 7 | Results | `csi_db_table_read` (soil pressures; analysis messages are a gap until recorded, §4.5), `csi_results_base_reactions`, `csi_results_joint_reactions` | §4.6 |
| 8 | Slab design and punching | none confirmed | gap SG-5 |
| 9 | Unlock for the next iteration | `csi_unlock_model` (ADR-0031, 0002 T15) | approved step |

The column loads come from the analysed ETABS model: the ETABS adapter reads `forces.joint_reactions/1` (0002 §4.6.1
step 13), and a harness calc outside this spec matches ETABS base joints to SAFE joints and turns reactions into loads on
the footing model. The sign flip and the matching tolerance are engineering content of that calc; the adapter never
flips a sign, matches a joint or invents a tolerance. Host verdicts stay raw host output; the verdict on bearing
pressure and punching is the code pack's (06 §9).

### 4.3 Kind `harness.joint_loads/1` and the loads import

`harness.joint_loads/1` **[added]** (owned by `eng-harness`; a neutral `model.joint_loads/1` is proposed in Q2):
`axes: "global"`; `loads`: list of `{joint, pattern, FX_kN, FY_kN, FZ_kN, MX_kNm, MY_kNm, MZ_kNm, punch_x_mm,
punch_y_mm}` (the last two `float > 0` or null: the dimensions of the loaded area for punching shear at the joint, which
SAFE keeps in the `XDim` and `YDim` columns of `Joint Loads Assignments - Force`; reads fill them, writes must leave them
null, gap SG-7); `(joint, pattern)` unique. The loads are forces applied to the footing model. Import of a payload =
one `csi_set_point_load` per row (host call `PointObj.SetLoadForce` with `Replace` true, Sasaah `CsiModel.cs:3090`, so
a row replaces that pattern's load on the joint), tool class `call`, effect `write`, `readback` helper = the table
`Joint Loads Assignments - Force`, `units = "token"` with `kN_m_C`, `confirm = never`. Import runs in rows ordered by
`(joint, pattern)` so a crash matrix is deterministic. Joints are the SAFE point names (`UniqueName` of the table; the
adapter does no label lookup). `csi_add_point` is not served: a load on a joint that does not exist is `NOT_FOUND`, because
a point added outside an area does not carry the load to the footing.

### 4.4 Model-state reader (0002 §4.6.4 for SAFE)

| Kind | Source |
|---|---|
| `model.grid_system/1` | `csi_list_grids` (Cartesian systems), as 0002 |
| `harness.model_points/1` **[added]** | `csi_list_points`: `points`: list of `{name, x_mm, y_mm, z_mm}` (units token `kN_mm_C`) |
| `model.area_placements/1` | `csi_list_areas` (`points`, `section`); `kind` is `slab` for every area (SAFE areas are slabs; walls are not read) |
| `model.frame_placements/1` | `csi_list_frames`; `kind: other` (ground beams) |
| `model.sections/1`, `model.materials/1` | tables of AC11 |
| `model.load_set/1` | `csi_list_load_patterns` and `csi_list_load_combos` plus tables `Load Pattern Definitions`, `Load Combination Definitions` for types and self weight; `frame_loads` and `area_loads` are empty (not read in v1) |
| `harness.joint_loads/1` | table `Joint Loads Assignments - Force` (present units, labelled by `csi_model_info.units`) |
| `harness.safe_soil_supports/1` **[added]** | AC12 tables: `properties`: `{name, stiffness_option, u1_kN_m3, u2_kN_m3, u3_kN_m3, nonlinear_u3}`; `assignments`: `{area, property}`; the stiffness unit is per area, so its dimension is that of a unit weight (Q3) |
| status `harness.csi_model_status/1` | `csi_model_info` (0002 §4.6.4), file base name only |

`csi_list_stories` is not read for SAFE (a footing model has no story stack to compare). The fingerprint is
`sha256(canonical_json(...))` over the payloads in the units the reads used, sorted by name, plus object counts (0002
§4.6.4). Edit kinds of SAFE v1 (each changes the fingerprint, property test AC9): assign an existing slab section to an area
(`csi_assign_area_section`, read back from `csi_list_areas`), add a load pattern, add or replace a combination, delete a
combination (`owned`), set a joint load. Combination and pattern mapping is 0002 §4.6.2. `superimposed_dead` maps to
`SuperDead` on SAFE: the Sasaah footing tool adds its super-dead patterns to a SAFE model with the type name
`SuperDead` (`SafePhase.EnsurePatterns`), and the SAFE 22 table lists "Super Dead" as a pattern type; both are Sasaah
sources, so the mapping is confirmed by local test L12 before use.

### 4.5 Table readers and field maps

`adapters/csi/_tables.py` reads `csi_db_table_read(table, fields, group, row_limit = 2000)` (no `units` parameter: values
are in the present units, labelled with the system of `csi_model_info.units` and converted by
`eng_contract.units.csi_unit_system`, never by hand; a `Ton_*` system is refused as in 0002 §4.5.4), checks `truncated`,
and maps columns to logical names through the data file `products/_safe_tables.toml`. Each table entry has a
`status`:

| Status | Meaning | Tables |
|---|---|---|
| `reference` | field keys from the Sasaah SAFE 22 table reference (importable tables); confirmed by `csi_db_table_fields` at the first local run | `Slab Property Definitions` (`Name`, `PropType`, `Material`, `Thickness`), `Material Properties - General` (`Material`, `Type`), `- Basic Mechanical Properties` (`Material`, `UnitWeight`, `E1`, `U12`), `- Concrete Data` (`Material`, `Fc`), `Spring Property Definitions - Area Springs` (`Name`, `StiffOpt`, `StiffU1`, `StiffU2`, `StiffU3`, `NonlinOpt3`), `Area Assignments - Area Springs` (`UniqueName`, `SpringProp`), `Joint Loads Assignments - Force` (`UniqueName`, `LoadPattern`, `FX`..`MZ`, `XDim`, `YDim`), `Load Pattern Definitions`, `Load Combination Definitions` |
| `candidate` | each logical column has a fixed list of accepted names, taken from the names the Sasaah footing tool reads in `Soil Pressures` (`SafePhase.cs:529-531` and `550-551`; `uniquename` is the area part of its (area, element, joint) key, line 573) and compared by **exact equality** of the normalized name (lower case, letters and digits only): `case` = `outputcase`, `loadcase`, `case`; `pressure` = `pressure`, `soilpressure`; `joint` = `joint`; `area` = `uniquename`; `element` = `shellelm`, `element`; `step_type` = `steptype`; `case_type` = `casetype` (the result tables of the host report envelope and multi-step output as Max and Min rows told apart by this column, and the Sasaah ETABS sessions read it so). `case` and `pressure` are required; `area`, `element`, `joint`, `step_type` and `case_type` are optional and `null` in the row when absent. Exactly one column of the reply may match a logical column: none for a required one, or more than one for any, is `INTERNAL` with the columns seen (AC13), never a first match. Sasaah's own `FindColumn` (`CsiHelpers.cs:188-200`) matches by substring and takes the first hit, and falls back to column 0 for a missing `uniquename`; the adapter does neither | `Soil Pressures` |
| `unknown` | the SAFE 22 reference lists the table with no fields and no Sasaah code reads it; the reader is a gap until a recording gives the keys | `Soil Pressures Summary`, `Soil Pressures Enveloping Summary`, `Base Reactions`, `Analysis Messages`, `Concrete Slab Design - Punching Shear Data`, `Concrete Slab Design - Flexure and Shear Data` |

A `candidate` table may be read before any recording, because a wrong or ambiguous column raises instead of being picked
and the result carries `field_map_status: "candidate"`; the workflow decides whether a candidate-mapped result may feed a
verdict (recommendation Q8). No field key is invented: an `unknown` entry becomes `reference` or `candidate` only from a recording the owner commits
(§12 L5) in a pull request that edits the data file and its tests. The field-map data is the single place a Sasaah or
SAFE change is absorbed.

### 4.6 Results

- **Soil pressures** (`harness.safe_soil_pressures/1` **[added]**): `source_table`; `sign_convention:
  "host_unconfirmed/1"`; `field_map_status` (`candidate` or `reference`); `rows`: `{area|null, element|null, joint|null, case: CaseRef, step_type|null, case_type|null, pressure_kPa}`; (`area`, `element`, `joint`, `case`, `step_type`) must be unique in a reply, otherwise `INTERNAL` with the columns seen, so that Max and Min rows of an envelope are never confused; `summary` with the row
  count and the raw minimum and maximum (no absolute values, no envelope computed by the adapter; the Sasaah tool takes
  `abs` and superposes service patterns itself, which is a calc, not a read). The case list is an argument, the `group`
  filter optional. **Limit (SG-6):** the tool returns at most 2000 rows and has no case or area filter; a realistic
  footing model (tens of footings, a mesh, tens of cases) exceeds it. v1 therefore supports (a) models whose table fits,
  (b) reads per group when the engineer's model defines one group per footing, (c) the `unknown` summary tables once
  recorded. Otherwise `LIMIT_EXCEEDED`. The proper fix is a typed Sasaah result tool with case and area filters.
- **Base reactions** (`harness.base_reactions/1` **[added]**): `rows`: `{case: CaseRef, FX_kN, FY_kN, FZ_kN, MX_kNm,
  MY_kNm, MZ_kNm}`, `moment_reference: "host_unconfirmed/1"`; `csi_results_base_reactions` (units token `kN_m_C`). Joint
  reactions: `csi_results_joint_reactions` → `forces.joint_reactions/1` as for ETABS.
- **Analysis**: `csi_run_analysis` (long role), `csi_analysis_status` and the `Analysis Messages` table as in 0002; the
  messages reader is a gap-until-recorded like the other `unknown` tables.
- The equilibrium comparison (applied column loads plus self weight against base reactions) is a harness calc with a basis
  tolerance (`checks.*`, never a constant here); this spec supplies its inputs.

### 4.7 `check_model` for SAFE (0002 §4.5.8)

Read-back of every written load (AC18), read-back of assigned sections, and integrity issues without tolerance:
`SECTION_UNDEFINED` (an area names a section not in `model.sections/1`), `COMBO_REFERENCE_MISSING`, `MODEL_LOCKED` (info),
`JOINT_LOAD_ON_MISSING_JOINT` (error), `AREA_WITHOUT_SOIL_SUPPORT` (warning: an area whose `SpringProp` is `None`; a
footing slab without a soil support is unstable, but a slab that is meant to be unsupported exists, so the workflow
decides). No engineering check is made.

### 4.8 Gaps (never an escape hatch)

Every SAFE step without an allowlisted tool is a `NotImplementedGap`; the way out is a project-lane permanent tool when the
owner asks in a live project ([ADR-0026](../../../../design/docs/adr/0026-project-lane-for-tools.md)), or a gap report to Sasaah (the order of value is Q5):

| Id | Missing | Why | Way out |
|---|---|---|---|
| SG-1 | Creating a SAFE model | `csi_new_model` returns `unsupported_by_version` on SAFE ("no File object", `CsiModel.cs:836-852`) while the footing tool builds one with a blank-model call (README, live); the two disagree (L3) | The engineer provides the prepared `.FDB` (Q5); Sasaah gap report if L3 shows `csi_new_blank_model` works |
| SG-2 | Defining or changing a footing (slab) section: `csi_define_area_section` takes an untyped `spec` (H-G1); the engine's typed `DefineSlabSection` is not exposed | A new footing thickness or type cannot be created | Existing sections only; Sasaah typed `csi_define_slab_section` |
| SG-3 | Soil support: defining or assigning an area spring | No tool; the footing tool uses table imports (excluded) | Prepared model carries the spring; Sasaah typed spring tools |
| SG-4 | Resizing or moving a footing (delete and re-add) | `csi_delete_object` is not served for SAFE: a re-added area has no soil spring (SG-3) and the sessions flipped orientations twice | Sasaah typed `csi_resize_area_rect` (requested in the session report), which keeps orientation and assignments |
| SG-5 | SAFE slab design run, flexure and shear results, punching results | `csi_design_run(concrete)` calls the concrete designer and `csi_design_results` reads beams only (S-12 §1); whether the call runs the SAFE slab designer is unconfirmed (L11); the result tables' keys are unknown (§4.5) | After L5 and L11: plan task T9 (blocked) |
| SG-6 | Soil pressure rows over 2000 | §4.6 | Groups per footing; Sasaah typed result tool with filters |
| SG-7 | Column dimensions for punching at a loaded joint (`XDim`, `YDim`) | `csi_set_point_load` cannot set them; whether `Replace` keeps or clears existing values is unknown (L8) | Prepared model carries them (read-back guards a change); Sasaah `csi_set_point_load` extension |
| SG-8 | Clearing a joint load | The host rejects an all-zero assignment (Sasaah footing README, "quirks") | None needed for a fresh copy; Sasaah typed clear |
| SG-9 | FE slab forces, strips, displacements | `csi_results_area_forces` reply shape and axes unspecified; strip results need strip objects no tool creates | Not adopted in v1 |

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `FX_kN`, `FY_kN`, `FZ_kN` (joint load) | float | kN | finite | yes, engineering quantity | the footing workflow's calc |
| `MX_kNm`, `MY_kNm`, `MZ_kNm` | float | kN.m | finite | yes, engineering quantity | same |
| `punch_x_mm`, `punch_y_mm` | float or null | mm | > 0 | read only (gap SG-7) | model |
| `thickness_mm` (read) | float | mm | > 0 | n/a | model |
| `pressure_kPa` (read) | float | kPa | finite | n/a | model |
| `u3_kN_m3` (read) | float | kN/m3 | finite | n/a | model (Q3) |
| `call_timeout_s`, `client_grace_s`, `timeout_s` of the SAFE server | int | s | ≥ 1 | no | `harness.toml`, required, no default (0002 §4.2) |
| `checks.readback_relative_tolerance` | float | 1 | > 0 | basis field | design basis (0002 G-2) |
| Outputs | envelopes of the kinds in §4.3 to §4.6 | canonical | - | - | adapter |

## 6. Errors

Everything of 0002 §6 applies. Additions:

| Condition | Code | Fields |
|---|---|---|
| Product of the model or tool does not match the server | `INVALID_ARGUMENT` | `field: model` or `tool` |
| Joint or pattern of a load row missing | `NOT_FOUND` | `field` names the row |
| Gap SG-1 to SG-9 | `NotImplementedGap` (`NOT_IMPLEMENTED`) | gap id |
| Table reply without a required column | `INTERNAL` | `incident_id`; table and column in the evidence |
| Soil pressure or other table over 2000 rows | `LIMIT_EXCEEDED` | `received`, hint `group` |
| Written load differs from the read-back, punching dimension changed | `READBACK_MISMATCH` (issue) | subject joint |

## 7. Non-goals

- Any SAFE server or plugin; bridge targets; the footing-design tool as an adapter tool (Q4).
- The footing workflow, the block `design_isolated_footing`, the calc that turns ETABS reactions into footing loads, the
  equilibrium check and every code-pack check.
- Building or resizing footings, soil springs, slab design and punching results, strips, FE forces (gaps §4.8).
- SAP2000 (phase 3); a registry probe for installed products (0002 H-G6).
- Scripts, generic invoke, table writes, `csi_db_tables_apply`, in any form and as a workaround for any gap.
- Setting the SAFE design code (`csi_set_design_code`) and reading it: the engineer's model carries it; whether a host
  result is comparable with a code-pack result is the workflow's question (L11).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| Wrong sign or wrong axes of loads or pressures read from SAFE | R1 | No sign flip in the adapter; `host_unconfirmed/1` conventions; read-back equality; local tests L7, L8 |
| A load lands 1000 times too large or small (units) | R1 | Token always passed; AC17; read-back of every load |
| A load replace silently changes the punching dimensions | R1 | Before/after comparison of `XDim`, `YDim` (AC18) |
| A table column guessed wrongly | R1 | Field-map statuses; no invented keys; exact-name matching and an error on none or several matches; `unknown` tables are gaps until recorded; candidate results are flagged and promoted only by an owner recording (§4.5, AC13, AC22) |
| Product sessions disturbing each other | R1 | One server per product (AC5, Q1) |
| Soil pressure result truncated and used as complete | R1 | `LIMIT_EXCEEDED`, never a partial payload (AC10, AC22) |
| Sasaah SAFE behavior differs from the fake | R3 | Fake built from the inventory; fidelity test against recordings (AC28) |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1, AC2, AC3, AC4 (fingerprint definition), AC11, AC12, AC13 | Unit | `tests/unit/` |
| AC3, AC4 (inventory), AC28 | Contract (inventory, recordings; markers `synthetic`, `recorded`) | `tests/contract/` |
| AC4 (stop), AC5, AC6 to AC8, AC9, AC10, AC14 to AC26 | Fake-host workflow (real engine, real fake-server processes) | `tests/workflow/` |
| AC27 | Replay | `tests/replay/` |
| AC9 (fingerprint) | Property (Hypothesis, derandomized in CI) | `tests/property/` |

No golden engineering tests: the adapter computes no engineering value (conversions are the contract's). Coverage floors
85% line and 75% branch (process/05 §2); mutation testing on `products/_safe_loads.py`, `_tables.py` and the SAFE reconcile
rules (R1).

## 10. Version impact

Part of `eng-harness` 0.1.0. A new allowlist header table `[fingerprint]` and new harness kinds (a minor release of the
package, changelog entries). `eng-contract` is unchanged; Q2 and Q3 ask for additive minors.

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | One server process per product (`[servers.csi_safe]`) or one shared process | Owner | Per product: one COM worker, one cached session per process (S-12 §5); a shared process is allowed by configuration only if the local test L15 shows no interference |
| Q2 | Neutral kind for joint loads (`model.joint_loads/1`, shared with SAP2000) or the harness kind | Owner | `harness.joint_loads/1` now; propose `model.joint_loads/1` as an `eng-contract` minor after the footing and column workflows use it |
| Q3 | A subgrade modulus has the dimension of a unit weight; canonical/1 has no quantity kind for it, and the suffix `_kN_m3` means unit weight | Owner | Add an additive quantity kind `subgrade_modulus` (suffix `_kN_m3` stays, the kind is declared per field) in an `eng-contract` minor; until then the field is read-only here |
| Q4 | Adopt `tools/footing-design` as a command-line tool step that only builds the SAFE model from fixed types (its `fixedTypes` mode), ignoring its own checks | Owner | Not in v1. Run an S-12 addendum first (inputs, outputs, exit codes, host side effects); its sizing and checks are engineering content with another code edition (ACI 318-19 in the tool, ACI 318-14 in 10 §9) and must not become a verdict. Then amend this spec |
| Q5 | v1 route to a SAFE model: engineer-prepared `.FDB` with footings, soil springs and column dimensions, versus a project-lane tool | Owner | Prepared model plus gap reports to Sasaah in this order: soil pressure result tool (SG-6), `csi_resize_area_rect` (SG-4), spring tools (SG-3), `csi_set_point_load` dimensions (SG-7), typed slab section (SG-2) |
| Q6 | Sign conventions and moment reference of SAFE soil pressures and base reactions | Owner | Record `host_unconfirmed/1`; settle by local test L7 and then add the convention to the kinds as a new kind version |
| Q7 | `SuperDead` as the pattern type name | Owner | Use after L12; keeps `superimposed_dead` mapped for SAFE only |
| Q8 | May a result read through a `candidate` field map (soil pressures before L5) feed a verdict | Owner | No verdict before L5 promotes the map to `reference`; the footing workflow spec checks `field_map_status` and reports `needs local test` otherwise |
| SG-1 to SG-9 | §4.8 | Owner | As tabled |
| A1 | **[added]** `ProductProfile`; `[servers.<name>].product`; allowlist `[fingerprint]` per product; harness kinds `harness.joint_loads/1`, `harness.model_points/1`, `harness.safe_soil_supports/1`, `harness.safe_soil_pressures/1`, `harness.base_reactions/1`; warnings `ZERO_LOAD_SKIPPED`; issue codes `SECTION_TYPE_NOT_MAPPED`, `JOINT_LOAD_ON_MISSING_JOINT`, `AREA_WITHOUT_SOIL_SUPPORT` | Owner | Accept with this spec |
| C1 | Conflict: 06 §8 lists soil supports, punching output and strip results as SAFE tools; `sasaah-csi-mcp` has none of them (ADR-0024 made 06 a target) | Owner | This spec follows the server; amend 06 §8 with the gap table when the owner accepts it |
| C2 | Conflict: S-12 §2 and 0002 assume `csi_new_model` for new models; on SAFE it is `unsupported_by_version` in the same Sasaah source that the footing tool contradicts | Owner | Settle by L3. The same `_model.File` object serves `csi_open_model` (`File.OpenFile`, `CsiModel.cs:1758`) and `csi_save_model` (`File.Save`, `CsiModel.cs:1730`), which steps 2 and 6 of §4.2 depend on; the footing command-line tool opens and saves `.FDB` live through them (`SafePhase.cs:88`, `111`), which is the evidence that they work on SAFE, to be confirmed by L2 |
| C3 | Conflict: ADR-0025 and 10 §9 scope ACI 318-14; the Sasaah footing tool implements ACI 318-19 | Owner | Not an adapter issue; recorded so that no host design result is compared with a code-pack result before the design code of the SAFE model is known |

## 12. Needs local test

Listed in `docs/local-testing.md` by the plan (no host program runs in CI), on a copy of a footing model, SAFE 22:

- L1. `csi_launch(product="SAFE", visible=false)`: the pid the reply names, the SAFE parent process, survival after the
  server job closes (silent breakaway, 0002 §12 item 1), and `csi_exit` of a launched hidden instance.
- L2. `csi_open_model` and `csi_save_model` on a `.FDB` (both use the same `File` object as `csi_new_model`, C2): the
  `saved_to` path, the hash change after a save, the files a SAFE model keeps next to it; copy hash equality; what
  `companion_globs` must list.
- L3. `csi_new_blank_model` and `csi_new_model` on SAFE (SG-1, C2).
- L4. The live `tools/list` fingerprint of the SAFE entry set, `csi_status` installed products, `serverInfo`.
- L5. `csi_db_table_fields` and `csi_db_table_read` of every table in §4.5, with the real columns (for `Soil Pressures`, whether a `StepType` and a `CaseType` column exist and how an envelope
  combination reports Max and Min), units (also when the
  present units are millimetres), and `truncated` behavior; the SAFE tables with `unknown` status are recorded for the
  owner's review.
- L6. Whether `Soil Pressures` needs an output selection before it has rows, the `StepType` values it reports for an
  envelope combination and a multi-step case (key uniqueness of AC22), its row count for a model of about 30
  footings, and whether groups of one footing each read within 2000 rows (SG-6).
- L7. Sign convention of soil pressure; moment reference and sign of base reactions (Q6).
- L8. `csi_set_point_load` on SAFE: replace semantics, rejection of an all-zero row, effect on `XDim` and `YDim`, units
  tokens, and the read-back table (SG-7, SG-8).
- L9. Replies of `csi_list_points`, `csi_list_areas`, `csi_list_grids`, `csi_list_frames` on SAFE (names, unique names).
- L10. `csi_run_analysis` on SAFE: duration for a footing model (sizes the `long` role timeout), the save dialog the sessions
  met, `locked` afterwards, `csi_unlock_model`, the proof-of-end question (0002 H-G7).
- L11. `csi_design_run(kind="concrete")` and `csi_design_results` on SAFE: what runs, what the tables hold afterwards, and
  the design code the model carries (SG-5, C3).
- L12. `csi_add_load_pattern` with type `SuperDead` and `csi_add_load_combo` on SAFE (Q7).
- L13. `close_started` on a hidden SAFE instance and on a visible one.
- L14. Record mode on a SAFE copy; the owner's review of the recordings before commit.
- L15. An ETABS server and a SAFE server in one run: epochs, host-instance locks, a timeout on one (Q1).
