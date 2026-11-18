---
id: spec-0012-sap2000-adapter
issue: "B-081"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1]
---

# Spec 0012: eng-harness, SAP2000 through the CSI adapter

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-04

This spec is the SAP2000 coverage check that [03](../../../../design/docs/architecture/03-repositories.md) §2 defers to
the start of phase 3, and it adds SAP2000 as the third product of the CSI adapter of
[spec 0002](0002-servers-and-adapters.md) ("0002 §n") after SAFE ([spec 0008](0008-safe-adapter.md), "0008 §n"). It
follows [ADR-0024](../../../../design/docs/adr/0024-harness-on-existing-sasaah-servers.md): the harness is a client of
`sasaah-csi-mcp`; no SAP2000 server is built, and [06](../../../../design/docs/architecture/06-csi-servers.md) §8
("SAP2000 adds general frame, shell and cable modeling") is a target the server does not meet (C1). Tool facts come from
the [S-12 report](../../../../spikes/S-12-sasaah-tool-inventory/REPORT.md) ("S-12 §n") and
`inventory/sasaah-csi-mcp.json` at Sasaah commit `61da80f61a6562c8e3553168056bc107e3f93013`, which is also the commit
of the read-only reading of the Sasaah working tree used for the SAP2000 parts S-12 did not cover (`CsiModel.cs`,
`docs/csi-mcp-server/{README,tools-reference,sap-plugin-bridge}.md`, `docs/agent-loop/playbooks/etabs-sap2000.md`).
The contract API is [eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract
§n"). Nothing here was run against SAP2000; everything that needs it is "needs local test" (§12). Details the
architecture leaves open are marked **[added]** and listed in §11.

## 1. Problem

Phase 3 adds a column workflow ([19](../../../../design/docs/architecture/19-roadmap-and-spikes.md) §1) whose
frame-model side may run in SAP2000. Before a spec promises that, the owner needs to know which of the 83 inventoried
tools serve SAP2000, with what evidence, what the product-specific parts of the adapter are, and which steps are gaps.
The evidence is thin: Sasaah's own matrix marks SAP2000 26 as verified live for attach, model info, lists and database
tables only; the rest was read by reflection on `SAP2000v1.dll` or inferred from product-neutral schemas. The adapter
must therefore serve what is evidenced, mark what is not, and raise `NotImplementedGap` for the rest, never improvise.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| 0002 CSI adapter, 0008 product profile (`ProductProfile`, `[servers.<name>].product`, per-product `[fingerprint]`, table-reader framework) | Product-neutral except the profile and the `products` field of allowlist entries (0002 §4.6.5; 0008 §4.1) | Reused unchanged; SAP2000 adds one profile, entries, a fake mode and readers (§4.2) |
| S-12 inventory, 83 tools | `csi_list_stories` states "SAP2000 returns unsupported_by_version"; all other descriptions are product-neutral (`product`: "ETABS, SAFE or SAP2000") | Per-tool table in §4.1 |
| Sasaah `Sasaah.Csi.Engine` (`CsiModel.cs`, `CsiProduct.cs`) | One engine for three products through the neutral `cSapModel`; SAP2000-specific branches: stories (`CsiModel.cs:138-140`, `855-859`), `NewModel` grid-only | Evidence for §4.1 |
| Sasaah `Sasaah.Sap.Bridge.Plugin` and `sap-plugin-bridge.md` | Member-by-member reflection on `SAP2000v1.dll` (2026-10-12), the source of the differences in §4.2; the plugin itself serves attached bridge targets | Facts used as evidence class R; the plugin is not used (the harness drives instances it launched, 0002 §4.4) |
| Sasaah playbook `etabs-sap2000.md` | Live runs on SAP2000 26 (2026-10-05/06) of a fixture build through scripts: no grid API, blank models ship no sections, `AddByCoord` ignores the requested name | Evidence class L for those facts only; the scripts themselves are excluded (escape hatch) |
| Sasaah table references | `etabs22-all-tables.json` and `safe22-all-tables.json` exist; **no SAP2000 table reference exists** (the playbook only counts 36 table keys) | Every SAP2000 table is `unknown` until recorded (§4.4) |

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Synthetic SAP2000 fake" is the SAP2000 mode of the test-only CSI
fake of 0002 §4.8.3 (lead decision D-5), a real process over stdio; "fake-host workflow test" runs the real engine with
the real `ToolPort` and `HostPort` against it.

### 3.1 Product selection and allowlist

- AC1. Given a `harness.toml` with `[servers.csi_sap2000]` (`product = "SAP2000"`, own `host_key`, roles and timeouts)
  and `[host_programs.sap2000]`, when loaded, then `ServersConfig` holds it beside the ETABS and SAFE servers and the
  rules of 0008 AC1 hold for three products; a model file name resolves `.SDB` to SAP2000, `.EDB` to ETABS and `.FDB` to
  SAFE; a product different from the server's gives `INVALID_ARGUMENT` (`field: model`) before any call. Tests:
  `tests/unit/servers/test_config.py::test_sap2000_server_section`,
  `tests/unit/adapters/test_products.py::test_product_by_extension_three_products`.
- AC2. Given the allowlist, when loaded for SAP2000, then exactly the tools marked `serve` or `serve-diff` in §4.1 are
  served, each with the fields of 0002 AC16; a tool marked `gap` or `not served` gives `INVALID_ARGUMENT` (`field:
  tool`) on a SAP2000 server; the escape-hatch deny list applies. Tests:
  `tests/unit/adapters/test_allowlist.py::test_sap2000_entries_match_coverage_table`, `::test_sap2000_gap_tools_refused`,
  `::test_escape_hatches_refused_for_sap2000`, `tests/contract/test_csi_allowlist.py::test_sap2000_against_inventory`.
- AC3. Given the S-12 inventory, when the SAP2000 tool-list fingerprint is computed (0002 §4.3.4 item 4), then it equals
  the value pinned in the allowlist header, the ETABS and SAFE values are unchanged, and a SAP2000 server whose live
  fingerprint differs stops the run before any write. Tests:
  `tests/contract/test_csi_allowlist.py::test_sap2000_fingerprint_from_inventory`,
  `tests/unit/servers/test_buildcheck.py::test_fingerprint_three_products`,
  `tests/workflow/servers/test_session.py::test_sap2000_build_mismatch_stops_run` (the stop; it runs the real engine
  through `build_ports`, so plan task T1 starts after plan 0002 task T19a and plan 0008 task T3; amendments B-413,
  B-475).
- AC4. Given three servers in one run and a timeout injected on one, then only its `session_epoch` increases; launch
  ownership, wedge state and pending reconciliation never mark another product. Test:
  `tests/workflow/adapters/test_sap2000_isolation.py::test_epochs_independent`.

### 3.2 Session and files

- AC5. Given a `.SDB` model, when `working_copy` runs, then a hidden SAP2000 instance is launched
  (`csi_launch(product="SAP2000", visible=false)`), the copy is opened with `csi_open_model(confirm)`, the hash and
  expected units are recorded and the identity is `derived_from` the original (0002 AC30); the session-operation suite of
  0002 passes with `product = SAP2000`. Tests: `tests/workflow/adapters/test_sap2000_session_ops.py::test_working_copy_sdb`,
  `tests/workflow/adapters/test_csi_session_ops.py` and `tests/workflow/servers/test_guard.py` (parametrized).
- AC6. Given a step that needs a new SAP2000 model, then `NotImplementedGap` (gap SP-1) is raised and nothing is sent;
  `csi_new_model` and `csi_new_blank_model` are not served. Test:
  `tests/workflow/adapters/test_sap2000_gaps.py::test_new_model_gap`.

### 3.3 Model state

- AC7. Given a SAP2000 model in the synthetic fake, when the model-state reader runs, then it produces
  `model.frame_placements/1` (`story: null`, `kind: other`, no label), `model.area_placements/1`,
  `harness.model_points/1`, `model.sections/1` (frame and area sections), `model.materials/1`, `model.load_set/1`
  (patterns and combinations) and the status, all validating, with a fingerprint equal for the same state read twice and
  different after each edit kind of §4.3. Tests: `tests/workflow/adapters/test_sap2000_state.py::test_kinds_and_fingerprint`,
  `tests/property/test_fingerprint.py::test_sap2000_order_independent_and_edit_sensitive`.
- AC8. Given the fake returns `unsupported_by_version` for `csi_list_stories` and `csi_list_grids`, then the reader does
  not call them (the profile declares both absent), `model.stories/1` and `model.grid_system/1` are not produced, one
  `info` issue `LEVELS_NOT_AVAILABLE` and one `GRID_NOT_AVAILABLE` name the cause, and the fingerprint is defined over the
  kinds the profile lists. Given `unsupported_by_version` from any other tool, then `NOT_SUPPORTED_BY_VERSION` is raised,
  never swallowed. Tests: `tests/workflow/adapters/test_sap2000_state.py::test_declared_absences`,
  `::test_other_unsupported_raises`.
- AC9. Given a list reply with `truncated: true`, then `LIMIT_EXCEEDED` with the received count (as 0008 AC10). Test:
  `tests/workflow/adapters/test_sap2000_state.py::test_truncated_raises`.
- AC10. Given any SAP2000 table (all `unknown`, §4.4), when a reader needs it, then `NotImplementedGap` (gap SP-4) is
  raised and nothing is guessed; given a recording the owner commits, the entry moves to `reference` or `candidate` only by
  a pull request that edits the data file and its tests. Test:
  `tests/unit/adapters/test_sap2000_tables.py::test_unknown_tables_are_gaps`.

### 3.4 Edits

- AC11. Given an `add frame` edit, when applied, then `csi_add_frame_by_coord` is sent with an existing `section`
  (checked against the state; an empty section list gives `NOT_FOUND` `field: section` before any call), the returned
  name (not the requested one) is recorded in the ledger and the identity map, and the read-back through
  `csi_list_frames` compares points and section. Test: `tests/workflow/adapters/test_sap2000_edits.py::test_add_frame_name_from_reply`.
- AC12. Given `csi_add_frame_by_coord` in flight at a timeout, when reconciled, then the adapter lists frames and answers
  `applied` (exactly one frame not in the pre-image has the requested points and section), `not_applied` (none), else
  `unknown`; no frame is added twice. Test: `tests/workflow/adapters/test_sap2000_reconcile.py::test_add_frame_outcomes`.
- AC13. Given the edit kinds of 0002 §4.6.2 that have a typed read-back (assign frame section, add area, add or delete
  load combination, add load pattern), when applied, then the argument mapping of 0002 holds; a pattern is read back by
  name only and `READBACK_PARTIAL` (warning) names type and self-weight as unchecked until the table is keyed. Edit kinds
  whose read-back needs a table (loads, restraints, area section assignment) raise `NotImplementedGap` (gap SP-4). Tests:
  `tests/workflow/adapters/test_sap2000_edits.py::test_typed_readback_edits`, `::test_pattern_partial_readback`,
  `::test_table_readback_edits_are_gap`.

### 3.5 Analysis, results and design

- AC14. Given a SAP2000 analysis, then the call goes to the `long` role of its server after the engine's save, the model
  state reports `locked` as the host says, and an edit while locked is refused as in 0002 AC29; the run-case selection
  is the saved one and no tool changes it (gap SP-6). Test: `tests/workflow/adapters/test_sap2000_analysis.py::test_long_role_save_first`.
- AC15. Given `csi_results_joint_reactions`, `csi_results_frame_forces`, `csi_results_base_reactions` and
  `csi_analysis_status`, then the replies become `forces.joint_reactions/1`, `forces.member_end/1` (`host_local/1`, contract
  G-3, rows keep `station` and `step_type`, none dropped or merged), `harness.base_reactions/1` (0008 §4.6) and
  `harness.csi_analysis_status/1`, in canonical units through `eng_contract.units`. Test:
  `tests/workflow/adapters/test_sap2000_results.py::test_reply_kinds_and_units`.
- AC16. Given `csi_design_run` with `kind` `steel` or `concrete` and `csi_design_results` for steel, then the replies become
  `harness.csi_design_run/1` and `harness.csi_design_results/1` as raw host output (never a verdict, 06 §9); given concrete
  design results for frames that are not beams, `NotImplementedGap` (gap SP-3); given `aluminum` or `coldformed`,
  `NOT_SUPPORTED_BY_VERSION` before any call. Tests: `tests/workflow/adapters/test_sap2000_design.py::test_steel_and_concrete_run`,
  `::test_concrete_non_beam_results_gap`, `::test_other_kinds_refused`.
- AC17. Given each remaining gap of §4.5 (SP-2, SP-5, SP-7, SP-8), the step raises `NotImplementedGap` with its gap id and
  nothing is sent. Test: `tests/workflow/adapters/test_sap2000_gaps.py::test_gaps_not_implemented` (parametrized).

### 3.6 End to end and recordings

- AC18. Given a test block that launches the synthetic SAP2000, opens a copy, reads the state, assigns a section, saves,
  runs the analysis and reads frame forces and reactions, then the journal holds every step, check and save and only the
  started instance is closed; when the engine is killed at each write step and resumed, it reconciles and completes
  without a repeated write. Tests: `tests/workflow/test_sap2000_cycle.py::test_cycle_steps`,
  `tests/replay/test_sap2000_resume.py::test_crash_matrix`.
- AC19. Given SAP2000 recordings, the adapter's contract tests pass on them and the synthetic fake gives the same reply
  shape and error codes for every recorded operation; the fake's SAP2000 tool schemas equal the S-12 inventory. The
  tests run on every applicable committed recording under `acceptance/recordings` and on the synthetic recording
  produced by record mode for that adapter; the real server is verified only once the owner commits a recording
  (spec §12 item L9; amendment B-573). Tests:
  `tests/contract/test_csi_recordings.py::test_sap2000_adapter_on_recordings`,
  `::test_sap2000_synthetic_matches_recordings`, `tests/contract/test_csi_allowlist.py::test_sap2000_fake_schemas_match_inventory`.

## 4. Design

### 4.1 Coverage table (the check required by 03 §2)

Evidence classes: **L** live record in Sasaah documents (README matrix: SAP2000 26 attach, model info, lists, database
tables; playbook runs of 2026-10-05/06); **R** reflection on `SAP2000v1.dll` or engine source (`sap-plugin-bridge.md` §3-§5,
2026-10-12; `CsiModel.cs`); **S** product-neutral S-12 schema only, no SAP2000 statement. L and R do not prove the harness
path: R concerns member existence (the bridge plugin), and the harness uses the COM path through the neutral `cSapModel`.
Status: `serve`, `serve-diff` (served with the difference named), `gap` (the server answers `unsupported_by_version`; not
on the SAP2000 allowlist), `not served` (no step needs it in v1). "ETABS set" is the tool set of 0002 §4.6.

| Tools | Status | Evidence | Note |
|---|---|---|---|
| `csi_status`, `csi_launch(product="SAP2000")` | serve | S, L (playbook: self-launched hidden instances) | Version 26 only was seen (Q2) |
| `csi_open_model`, `csi_save_model` | serve | S (`csi_open_model` text lists `.SDB`) | `.SDB` is the model extension (playbook fixture); companions unknown (L2) |
| `csi_unlock_model`, `csi_exit` | serve | S, R (`SetModelIsLocked`) | As in the ETABS set (ADR-0031) |
| `csi_new_blank_model` | not served (SP-1) | L (blank has no sections or frame sections), S | Needs section definition, itself a gap (SP-2) |
| `csi_new_model` | gap (SP-1) | L (`File.NewGridOnly` returns -100; `stories` refused, `CsiModel.cs:855-859`) | |
| `csi_model_info`, `csi_list_points`, `csi_list_areas`, `csi_list_materials`, `csi_list_frame_sections`, `csi_list_area_sections`, `csi_list_load_patterns`, `csi_list_load_cases`, `csi_list_load_combos` | serve | L (lists), R | `csi_list_points` builds from `GetNameList` and `GetCoordCartesian`; `truncated` rule unchanged |
| `csi_list_frames` | serve-diff | L (lists), tools-reference | Reply has no `label` or `story` |
| `csi_list_stories`, `csi_list_grids`, `csi_results_story_drifts` | gap | R, L (grid API returns -100, no grid table) | Declared absent in the state reader (AC8) |
| `csi_frame_details`, `csi_export_joint` | gap | R (`GetLabelFromName`, `GetDesignOrientation` not exposed; bridge targets) | Whether the COM path differs: L8 |
| `csi_db_tables_list`, `csi_db_table_fields`, `csi_db_table_read` | serve | L (README) | Keys unknown (§4.4) |
| `csi_db_tables_apply`, `csi_run_script`, `csi_invoke`, `csi_object_*` | refused | S-12 `excluded_from_allowlist` | Escape hatches, every product |
| `csi_add_frame_by_coord` | serve-diff | R, L (requested name ignored) | Name from the reply; a section must exist (AC11) |
| `csi_add_area_by_coord`, `csi_assign_frame_section` | serve | R, S | Section must exist |
| `csi_add_load_pattern`, `csi_add_load_combo`, `csi_delete_load_combo` | serve-diff | R | Partial read-back (AC13); `superimposed_dead` and `roof_live` stay unmapped (H-G3) |
| `csi_set_frame_load_distributed`, `csi_set_area_load_uniform`, `csi_set_point_restraint`, `csi_set_point_load`, `csi_assign_area_section` | gap (SP-4) | R (first three), S | Served by the tool; the harness edit is a gap until the read-back table is keyed |
| `csi_run_analysis`, `csi_analysis_status` | serve | R | Long role; not live (L5) |
| `csi_results_joint_reactions`, `csi_results_frame_forces`, `csi_results_base_reactions` | serve | R | Not live (L6) |
| `csi_results_joint_displacements`, `csi_results_frame_joint_forces`, `csi_results_area_forces`, `csi_results_link_forces`, `csi_results_modal_periods`, `csi_results_displacements_envelope` | not served | R (first), S | Added when a workflow step names them |
| `csi_design_run` (`steel`, `concrete`) | serve | R (`DesignSteel`, `DesignConcrete` `StartDesign`) | Not live (L7) |
| `csi_design_results`, `csi_list_design_combos` | serve-diff | S-12 §1 (concrete: beams only), tools-reference (concrete combos list works on SAP2000 only) | Concrete non-beam results: SP-3 |
| `csi_design_run` (`aluminum`, `coldformed`) | gap | R (`DesignAluminum`, `DesignColdFormed` exist in `SAP2000v1`, the engine accepts steel and concrete only) | Never |
| `csi_capture_window`, `csi_refresh_view`, `csi_move_area`, `csi_add_point`, `csi_delete_object`, `csi_get_selection`, `csi_point_connectivity`, `csi_get_assigned_loads`, `csi_set_frame_load_point`, `csi_set_frame_modifiers`, `csi_set_frame_releases`, `csi_set_frame_offsets`, `csi_set_area_modifiers`, `csi_set_area_pier`, `csi_define_wall_section`, `csi_get_design_code`, `csi_set_design_code`, `csi_design_prefs_get`, `csi_design_prefs_set`, `csi_attach`, `csi_detach` | not served | S | No step of the workflows in §4.2 names them (H-G2 for `csi_set_frame_load_point`) |
| `csi_define_material`, `csi_define_frame_section`, `csi_define_area_section`, `csi_define_load_case` | gap (SP-2) | S-12 §2 | Untyped `spec` (H-G1); same for every product |

### 4.2 What the column workflow and later workflows need from SAP2000

The column workflow is a separate spec (B-083). From the architecture ([10](../../../../design/docs/architecture/10-structural-codes.md)
§9, [19](../../../../design/docs/architecture/19-roadmap-and-spikes.md) §1) its SAP2000 side needs the following:

| Need | Tools | Status |
|---|---|---|
| Working copy and read of the frame model | §4.1 session and list tools | Covered; no levels, grids or labels |
| Identify columns | `csi_list_frames` points and section; design orientation from `csi_frame_details` | **Gap SP-5**: the adapter keeps `kind: other` (H-G5); a harness calc classifies vertical frames from the points, never the adapter |
| Member end forces by combination | `csi_results_frame_forces` | Covered, `host_local/1`, not live |
| Joint reactions for the foundation hand-off | `csi_results_joint_reactions` | Covered, not live |
| Change a column section | `csi_assign_frame_section` | Covered if the section exists; defining one is SP-2 |
| Host design of columns | `csi_design_run`, `csi_design_results` | Steel covered; concrete columns **SP-3** |
| Load changes | point, frame and area loads | **SP-4** until the tables are keyed |
| Offsets, releases, modifiers | none allowlisted | Not served; a later spec decides after S-12 review |

### 4.3 Product-specific parts

`adapters/csi/products/_sap2000.py` is the only SAP2000 code, a `ProductProfile` as in 0008 §4.1 (no import of another
profile, no product branch in shared modules):

| Field | Value |
|---|---|
| `name`, `model_extensions` | `"SAP2000"`, `(".SDB",)` |
| `host_executables` | from `[host_programs.sap2000]` (Sasaah names `SAP2000.exe`) |
| `companion_globs` | empty until L2 |
| `state_reader` | frames, areas, points, sections (frame and area), materials, load set, status; **declared absent**: stories, grid system. The fingerprint is `sha256(canonical_json(...))` over the kinds the profile lists, so adding an absent kind later is a new fingerprint version **[added]** |
| `result_readers`, `edit_kinds` | §4.1 rows `serve` and `serve-diff`; others `NotImplementedGap` |
| `table_fields` | `products/_sap2000_tables.toml`, every entry `unknown` (§4.4) |
| `add_frame_naming` | `reply`: the name comes from the reply and reconciliation matches by geometry (AC11, AC12) **[added]** |

Everything else (framework, errors, units tokens, timeouts, ledger, guard, ADR-0031) is shared. One server section per
product as in 0008 §4.1 (Q1).

### 4.4 Tables

`csi_db_table_read` is the only route to loads, restraints and definitions without a typed tool, and there is no SAP2000
table reference (§2). Each SAP2000 table entry is therefore `unknown`: the reader raises `NotImplementedGap` (SP-4) with
the table name, and the owner's recording (L4) turns an entry into `reference` or `candidate` under the rules of
0008 §4.5 (exact normalized names, none or several matching columns is `INTERNAL`). No key is taken from the ETABS or
SAFE references.

### 4.5 Gaps (never an escape hatch)

The way out of a gap is a project-lane permanent tool when the owner asks in a live project
([ADR-0026](../../../../design/docs/adr/0026-project-lane-for-tools.md)), or a gap report to Sasaah.

| Id | Missing | Way out |
|---|---|---|
| SP-1 | Creating a SAP2000 model (`File.NewGridOnly` -100; blank model has no sections) | Engineer provides the `.SDB` (Q4) |
| SP-2 | Defining sections, materials, load cases (untyped `spec`, H-G1) | Existing sections only; Sasaah typed tools |
| SP-3 | Concrete design results for frames that are not beams (`csi_design_results` reads beams, S-12 §1) | Sasaah typed column result tool; steel works |
| SP-4 | Table-based reads and the edits that need them (loads, restraints, area section assignment): all tables unknown | Recording L4, then a plan task |
| SP-5 | Design orientation, frame labels, local axes (`csi_frame_details` unsupported) | Sasaah gap report; geometry classification by a calc |
| SP-6 | Choosing which load cases an analysis runs | The saved selection is used; Sasaah typed tool |
| SP-7 | Levels and grids (no API in SAP2000 26) | None; declared absent |
| SP-8 | Cable, link and general-shell workflows named in 06 §8 | No tool (C1); not adopted in v1 |

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `section` (add frame, assign) | string | n/a | existing in `model.sections/1` | no | model |
| frame end points | Point3 | mm | finite | read-back only | workflow calc |
| `call_timeout_s`, `client_grace_s`, `timeout_s` of the SAP2000 server | int | s | >= 1 | no | `harness.toml`, required, no default (0002 §4.2) |
| Outputs | envelopes of the kinds in AC7, AC15, AC16 | canonical | - | - | adapter |

No new engineering number enters this spec.

## 6. Errors

Everything of 0002 §6 and 0008 §6 applies. Additions: gaps SP-1 to SP-8 are `NotImplementedGap` (`NOT_IMPLEMENTED`, gap id);
`unsupported_by_version` from a served tool is `NOT_SUPPORTED_BY_VERSION`; a frame added with no section in the model is
`NOT_FOUND` (`field: section`); `READBACK_PARTIAL` (warning) for patterns.

## 7. Non-goals

- A SAP2000 server or plugin; bridge targets; scripts, generic invoke, table writes in any form or as a workaround.
- The column workflow, column checks and every code-pack check (B-082, B-083); the equilibrium or design verdicts.
- Model creation, section definition, cable, link and shell modeling (gaps), levels and grids.
- Setting or reading the SAP2000 design code; versions other than the one Sasaah verified (Q2).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| Treating Sasaah reflection or bridge facts as proof for the COM path | R1 | Evidence classes in §4.1; every `R` and `S` row has a local test; no live claim |
| Added frame under another name is lost or added twice | R1 | Name from the reply; geometry reconciliation (AC11, AC12) |
| A guessed table key reads or writes the wrong data | R1 | All tables `unknown`; gap until recorded (AC10) |
| Missing levels and grids taken as an empty model | R1 | Declared absences with `info` issues, not empty payloads (AC8) |
| Host verdict on a column treated as a code check | R1 | Raw output kinds; concrete column results a gap (AC16) |
| Sasaah SAP2000 behavior differs from the fake | R3 | Fake from the inventory; recording fidelity test (AC19) |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1, AC2, AC3 (definition), AC10 | Unit | `tests/unit/` |
| AC2, AC3 (inventory), AC19 | Contract (markers `synthetic`, `recorded`) | `tests/contract/` |
| AC3 (stop), AC4 to AC9, AC11 to AC18 | Fake-host workflow | `tests/workflow/` |
| AC18 (crash matrix) | Replay | `tests/replay/` |
| AC7 (fingerprint) | Property (Hypothesis, derandomized in CI) | `tests/property/` |

No golden engineering tests: the adapter computes no engineering value. Coverage floors 85% line and 75% branch
(process/05 §2); mutation testing on `products/_sap2000.py` and the add-frame reconcile rule (R1).

## 10. Version impact

Part of `eng-harness` 0.1.0 (changelog entries): an allowlist `[fingerprint]` entry, one profile, one table data file,
issue codes `LEVELS_NOT_AVAILABLE`, `GRID_NOT_AVAILABLE`, `READBACK_PARTIAL`. `eng-contract` is unchanged.

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | One server process per product (`[servers.csi_sap2000]`) or one shared | Owner | Per product, as 0008 Q1 |
| Q2 | Supported SAP2000 versions: Sasaah verified 26 only (README: 24-25, 27+ "expected but unverified") | Owner | Pin 26; any other version is refused by the build check until the owner lists it |
| Q3 | Ask Sasaah for a `sap2000-all-tables.json` like the ETABS and SAFE references | Owner | Yes; it turns `unknown` entries into `reference` without a guess, still confirmed by L4 |
| Q4 | v1 route to a SAP2000 model: engineer-prepared `.SDB` or a project-lane tool | Owner | Prepared `.SDB`; gap reports to Sasaah in this order: typed column result tool (SP-3), frame details on SAP2000 (SP-5), typed section tools (SP-2), run-case selection (SP-6) |
| Q5 | Allowlist `csi_get_assigned_loads` (units declared but ignored, S-12) as the typed read-back for loads, instead of tables | Owner | After L4/L8: read in present units, labelled by `csi_model_info.units`, as 0002 §4.5.4; then replace SP-4 for loads |
| Q6 | Conclusion of the 03 §2 check | Owner | "Covered for frame-model reading, steel design, results and section assignment; gaps SP-1 to SP-8"; amend 03 §2 and 06 §8 with the gap table on acceptance |
| C1 | Conflict: 06 §8 lists general frame, shell and cable modeling; `sasaah-csi-mcp` has no cable or link tools and no model creation for SAP2000 (ADR-0024 made 06 a target) | Owner | This spec follows the server |
| C2 | Conflict: Sasaah's README marks SAP2000 live only for attach, model info, lists and tables, while `sap-plugin-bridge.md` §4 labels most tools "identical" to SAFE by reflection | Owner | Evidence classes of §4.1 count only L as live; the bridge table is R |
| A1 | **[added]** profile fields `add_frame_naming` and declared absences; fingerprint over profile kinds; issue codes of §10 | Owner | Accept with this spec |

## 12. Needs local test

Listed in `docs/local-testing.md` by the plan (no host program runs in CI), on a copy of a frame model, SAP2000 26:

- L1. `csi_launch(product="SAP2000", visible=false)`, the pid, survival after the server job closes, `csi_exit`, the live
  `tools/list` fingerprint and `csi_status` (AC3, AC5).
- L2. `csi_open_model` and `csi_save_model` on `.SDB`: hash change, companion files, copy equality (AC5).
- L3. The replies of every `serve` list tool: names, `truncated`, frame fields, and that `csi_list_stories`/`csi_list_grids`
  answer `unsupported_by_version` on COM (AC7, AC8).
- L4. `csi_db_table_fields` and `csi_db_table_read` of each table the readers need (frame, joint and area loads,
  restraints, pattern and combination definitions, `Analysis Messages`): the owner records them for review (AC10, SP-4).
- L5. `csi_run_analysis`: duration (sizes the `long` timeout), whether the model is locked afterwards, which cases run,
  the proof-of-end question (AC14, SP-6).
- L6. Sign, axes and station semantics of `csi_results_frame_forces`, reactions, and base reactions (AC15).
- L7. `csi_design_run` for steel and concrete and the shape of `csi_design_results` for steel and concrete columns (AC16, SP-3).
- L8. `csi_frame_details` and `csi_export_joint` on the COM path (the evidence is for bridge targets), `csi_add_frame_by_coord`
  naming, section requirement and units, `csi_set_point_load` semantics (AC11, SP-5).
- L9. Record mode on a SAP2000 copy: record-mode scenario, owner review and commit of recordings, and subsequent
  contract-test verification against the real server (AC19; amendment B-573).
