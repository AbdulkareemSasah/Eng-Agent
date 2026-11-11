---
id: spec-0003-calcs
issue: "B-062"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2]
---

# Spec 0003: eng-harness calcs (framework, approvals, the edit-cycle calcs)

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-03

This spec implements the harness calcs of [11 §4](../../../../design/docs/architecture/11-harness-engine.md) and the
`CalcPort` of the [engine spec](0001-engine.md) ("engine §n"). Calcs get the rigor of code-pack checks
([10](../../../../design/docs/architecture/10-structural-codes.md) §3 to §6) through
[process/10](../../../../design/process/10-engineering-verification.md) §4, with "clause" replaced by the method's
source. The contract API is [eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md)
("contract §n"). The calcs serve steps 4, 9 and 14 of the edit cycle
([18](../../../../design/docs/architecture/18-first-slice-dxf-to-etabs.md) §4) and acceptance A1 and A5 (18 §5).
What the CSI server can read comes from [spike S-12](../../../../spikes/S-12-sasaah-tool-inventory/REPORT.md)
("S-12"). Session findings from the Sasaah baseline design notes (`agent-sessions/_baseline/DESIGN-NOTES.md` in the
Sasaah repository, items ب2, ب5, ج9, د6, د8) are cited by item. Details not stated in those sources are marked
**[added]** and listed in §11.

**R1 content.** Every calc here is engineering content. It ships with status `draft` and goes to the owner queue
(ADR-0028 §4). No agent marks a calc `verified` or adds it to `approvals.yaml`.

**Amendment B-405.** Spec 0010 (Q10, C2) asked that this spec state how code-pack checks reach the `CalcPort`: the
same port serves them through the one code-pack route of spec 0010 §4.3 and spec 0013 §4.5 (§4.12 item 4), with the
run-class rule of §4.12, and the `NOT_FOUND` of §6 covers an id outside that route's allowlist. Listed in §11 (Q15).

## 1. Problem

The edit cycle decides whether a model is safe to keep by comparing states: what changed since the last revision
(manual edits must show and must never be overwritten, A5), whether each written value arrived (P7), and whether the
model holds exactly the requested changes (A1). In the session baseline these comparisons were circular (a check
compared a constant with itself and passed, ب5). They used literal tolerances, and the change fingerprint missed a
moved column (ج9). Sign and unit conventions also flipped values unnoticed (a factor of 1000 on thicknesses, د6).
Calcs that are pure, cited, traced and approved by content hash remove these failure modes. Nothing exists yet.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| Sasaah `tools/agent-loop/pairs/compare.py` (read-only) | Matches frames, areas, grids and levels by name, then by geometry within a tolerance; tries reversed frame ends; pairs renames. Its tolerances are literals (a 1.0 mm command-line default and a fixed grid-angle constant) | Matching ideas reused in §4.11 (reversed ends, rename pairing). No code copied (A12), no tolerance adopted |
| S-04 spike (`spikes/S-04-model-state/`) | Fingerprint per section and overall, order ignored; float rounding is a spike setting, not an engineering value | Per-section design reused; no rounding in the fingerprint (§4.6, Q3) |
| `eng-contract` 0.1 | `canonical_json` (RFC 8785), `payload_sha256`, `Quantity`, `Cited`, `Trace`, `ParamModel`, `validate_input`, `resolve_ref`, kinds and `KindRegistry.extend` | Used; nothing re-implemented |
| `fractions.Fraction`, `math.ceil`, `math.isqrt`, `hashlib` (standard library) | Exact tolerance and distance comparisons; SHA-256 | Used |
| `ast`, `inspect`, `importlib.util.find_spec` (standard library) | Static import closure of a calc module for the content hash | Used |
| A YAML parser for `approvals.yaml` | Not in the engine's dependencies; spec 0004 needs one for templates (13 §2) | One package ADR shared with plan 0004 (Q9) |

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Golden" cases are hand checks derived from the stated method.
Each one has its expected value in a data file under `tests/data/golden/calcs/` with a non-empty `source` naming the
method section of this spec (process/05 §5). All input values in fixtures are synthetic and stated as such; none is a
proposed project value.

### 3.1 Framework and registry

- AC1. Given a calc function registered with `@calc`, when its id does not match `^harness\.[a-z][a-z0-9_]*$`, its
  version is not an integer from 1 to 9999, its input type is not a `CalcInput` subclass, its output kind is not a
  registered harness kind, its `method_source` is blank, or the id is already registered, then `CalcRegistryError`
  names the rule. Test: `tests/unit/calcs/test_registry.py::test_registration_rules`.
- AC2. Given the committed `src/eng_harness/calcs/calcs.lock.json`, when compared with the registry, then every
  registered calc has an entry with the same id, version and content hash; a removed calc's id stays in the lock as
  `removed: true` and cannot be registered again. Tests: `tests/contract/test_calc_lock.py::test_lock_matches_registry`,
  `tests/unit/calcs/test_registry.py::test_removed_id_not_reused`.
- AC3. Given every module under `src/eng_harness/calcs/`, when the calc-module rules test runs, then each imports only
  the modules allowed by §4.3, reads no file, clock, environment or random source, uses no `global` or mutable
  module-level state, imports nothing inside a function, and contains no numeric literal outside gate FB005's allowed
  forms. Test: `tests/rules/test_calc_modules.py::test_calc_module_rules`.
- AC4. Given a calc and an input, when it runs twice in two interpreter processes, then the stored payloads are
  byte-identical canonical JSON. Test: `tests/unit/calcs/test_framework.py::test_deterministic_across_processes`.
- AC5. Given a calc run, then the payload's `trace` is a contract `Trace` whose `calc_id`, `calc_version` and
  `content_sha256` are the calc's. Every input field appears as a `TraceInput` with its `ref`, every basis field read
  appears as a `TraceInput` with its basis pointer, and every step names its method rule in `source`. Test:
  `tests/unit/calcs/test_framework.py::test_trace_records_inputs_and_rules`.

### 3.2 Content hash and approvals

- AC6. Given a calc, when a helper module it imports (directly or transitively inside `eng_harness`) changes by one
  byte, or its metadata, its input schema or its output kind schema changes, then its content hash changes; given a
  change only in line endings (CRLF to LF), then it does not. Test:
  `tests/unit/calcs/test_hash.py::test_hash_covers_helpers_and_metadata`.
- AC7. Given a calc module that imports with `importlib`, `__import__` or inside a function, or whose source is not
  available (bytecode only), then hashing raises `CalcRegistryError` and the calc cannot be registered. Test:
  `test_hash.py::test_unhashable_calc_refused`.
- AC8. Given an `approvals.yaml` entry whose id, version and hash match a calc, then the calc's status is `approved`.
  An entry whose hash differs gives `verified` or `draft` (the declared verification state), and `check_approvals`
  reports it as `stale_approval`. A matching `withdrawn` entry gives `withdrawn`. Test:
  `tests/unit/calcs/test_approvals.py::test_status_resolution`.
- AC9. Given an `approvals.yaml` entry without approver, date, verification record or pull request, with an unknown
  calc id, or with a duplicate key, then loading fails with the line. Given a file holding anything but the schema
  of §4.5 (YAML tags, anchors), then it is refused. Test: `test_approvals.py::test_file_validation`.
- AC10. Given the shipped `approvals.yaml`, then it parses, and every registered calc declares `verification:
  draft`. Test: `tests/contract/test_calc_lock.py::test_shipped_calcs_are_draft` (ADR-0028 §4; the owner changes it).
- AC11. Given a production run, when `preflight(calc_ids)` runs, then it lists every calc that is not `approved`. When
  `run` is called for such a calc, it raises `CalcRefused` (`CALC_NOT_APPROVED`) and nothing is stored. Given a
  `withdrawn` calc, both refuse in trial runs too (`CALC_WITHDRAWN`). Test:
  `tests/unit/calcs/test_port.py::test_production_and_withdrawn_refusal`.
- AC12. Given a trial run and a `draft` calc, when it runs, then the payload has `draft: true`, the envelope summary
  says `draft`, and the engine's `CalcResult.draft` is true. Test: `test_port.py::test_draft_marking`.

### 3.3 CalcPort

- AC13. Given `describe(calc_id)`, then `CalcInfo` carries `id`, `version`, `content_sha256`, `status`,
  `engineering_params` (every ref-capable input field), `basis_fields` (the basis paths the calc reads) **[added]** and
  `ref_rules` **[added]**: a map from every reference-carrying field path to its `RefRule` (`kinds`, `unit`,
  `stale_ok`, contract §4.6.2), built from the input model's `x-eng` metadata. The paths with `stale_ok` true are
  exactly those of the §4.13 table for that calc. An unknown id gives `ContractError` `NOT_FOUND`. Test:
  `test_port.py::test_describe`.
- AC14. Given `run(calc_id, args)` with a literal for an engineering input, a reference of the wrong kind, a pointer
  that does not resolve, or an out-of-bounds value, then the failure envelope carries the contract code of contract §5
  (validation order unchanged), and nothing is stored. Test: `test_port.py::test_input_validation_codes`.
- AC15. Given an input whose referenced records together hold more items than `CalcSettings.max_items`, then
  `LIMIT_EXCEEDED` and nothing is stored. Test: `test_port.py::test_item_limit`.
- AC16. Given a successful run, then the result is stored once in the result store with the calc's output kind and
  `complete` equal to the payload's `complete`. The record's parents are the referenced result ids, its provenance
  `tool` is `harness`, and its provenance `inputs` hold only references. Test: `test_port.py::test_result_record`.
- AC17. Given the real CalcPort and the real engine with fake tool ports, when a test block calls `ctx.calc`, then the
  step is journaled with id, version, content hash and status (engine AC13), and the result reads back with
  `ctx.read`. Test: `tests/workflow/test_calc_step.py::test_calc_step_end_to_end`.
- AC18. Given a calc that reaches a path marked "not implemented" in §4, then `NotImplementedGap` (code
  `NOT_IMPLEMENTED`, engine §6) names the gap id, and nothing is stored. Test: `test_port.py::test_not_implemented_gap`.
- AC48. Given the real engine, the real CalcPort and fake tool ports, a model read at revision n, then written (n+1)
  and read again, when a block calls `ctx.calc("harness.model_diff", before=<refs at n>, after=<refs at n+1>, ...)`,
  then the calc succeeds, because engine invariant 3 resolves `before` with the `RefRule` of
  `CalcInfo.ref_rules` (`stale_ok` true). When `after` holds a reference at n while the model is at n+1, then the
  engine raises `REF_STALE` before the port call and no step result is stored (§4.13). Test:
  `tests/workflow/test_calc_step.py::test_older_revision_inputs`.
- AC49. Given every registered calc, then the input fields whose JSON Schema carries `x-eng.stale_ok: true` are
  exactly those of the §4.13 table for that calc, and no `basis`, `effects`, `after`, `b_*`, `verdicts`, `frames` or
  `required` field carries it. Test: `tests/contract/test_calc_lock.py::test_stale_ok_fields_match_spec`.

### 3.4 Model fingerprint (§4.6)

- AC19. Given the same read set with list members in any order, then the fingerprint is the same. Area points and
  their joints keep their order. Tests: `tests/property/test_fingerprint.py::test_order_independent`,
  `tests/golden/test_calcs_golden.py::test_case[fingerprint-point-order]`.
- AC20. Given a read set, when any value changes (a coordinate, a section name, a restraint, a load value), an object
  is added or removed, or a section is left out, then the fingerprint changes. Tests:
  `test_fingerprint.py::test_any_change_changes_fingerprint`, `test_calcs_golden.py::test_case[fingerprint-moved-column]`.
- AC21. Given a small hand-written read set, then each section hash equals SHA-256 over the canonical bytes written by
  hand in the golden file from rules F1 to F4 (computed in the test with `hashlib`, not with the implementation's
  canonicalization). Test: `test_calcs_golden.py::test_case[fingerprint-canonical-bytes]`.
- AC22. Given a read set in which one record has `complete: false`, then the payload has `complete: false`, and
  `same_state` with any other fingerprint returns `unknown`, never `same`. Test:
  `tests/unit/calcs/test_fingerprint.py::test_incomplete_read`.
- AC23. Given records of different models or different revisions in one read set, then `INVALID_ARGUMENT` with the
  field. Test: `test_fingerprint.py::test_mixed_models_refused`.

### 3.5 Difference report (§4.7)

- AC24. Given two read sets, then every added, removed and changed object is reported per section with its key, and
  every changed property with its JSON pointer, before and after values, unit and the tolerance applied. Test:
  `test_calcs_golden.py::test_case[diff-section-changed]`.
- AC25. Given a numeric property whose difference equals the basis tolerance exactly, then it is equal within
  tolerance and listed in `within_tolerance`. Given a difference one unit in the last place above it, it is changed.
  Given a tolerance of zero, only exact equality is equal. Tests: `test_calcs_golden.py::test_case[diff-boundary]`,
  `tests/property/test_diff.py::test_boundary_exact`.
- AC26. Given a basis without one of the tolerance fields of §4.4, or a field with the wrong unit, a negative value or
  `confirmed: false`, then `INVALID_ARGUMENT` naming the basis path. No default is used. Test:
  `tests/unit/calcs/test_diff.py::test_basis_tolerances_required`.
- AC27. Given identical read sets, then `identical: true` and no changes. Given a diff of A to B and of B to A, then
  added and removed swap and every changed property swaps before and after. Test:
  `tests/property/test_diff.py::test_identity_and_symmetry`.
- AC28. Given a section present on one side only, or two keys that occur twice in one section, then the section is
  listed in `not_compared` (or the key as `ambiguous`), and `complete: false`. It is never reported as unchanged.
  Test: `test_diff.py::test_not_compared_and_ambiguous`.
- AC29. Given `rotation_deg` values that differ by a full turn, then the property is reported as changed (no
  normalization, §4.7 D6). Test: `test_calcs_golden.py::test_case[diff-angle-full-turn]`.

### 3.6 Read-back check (§4.8)

- AC30. Given expected effects and a before and after read set in which every effect is present within tolerance and
  nothing else changed, then status `PASS`. Test: `test_calcs_golden.py::test_case[readback-pass]`.
- AC31. Given a written value that differs by more than the tolerance, an object the effects add that is missing, or a
  change that no effect explains (an unexpected change), then status `FAIL` with each item listed. Tests:
  `test_calcs_golden.py::test_case[readback-mismatch]`, `::test_case[readback-unexpected]`.
- AC32. Given an effect on a section the after read set does not hold (a read-back gap, S12-G8), then that item is
  `not_read` and the status is `NEEDS_ENGINEER`, unless another item fails. Test:
  `tests/unit/calcs/test_readback.py::test_not_read`.
- AC33. Given after records whose model revision is not greater than the before records' revision, after records that
  are the before records, or expected effects that have an after record among their parents, then `INVALID_ARGUMENT`.
  The check never compares a value with its own source (ب5). Test: `test_readback.py::test_circular_inputs_refused`.
- AC34. Given a thickness written as 0.2 and read back as 200 (a unit-scale error, د6), then `FAIL`. Test:
  `test_calcs_golden.py::test_case[readback-unit-scale]`.

### 3.7 Design results summary (§4.9)

- AC35. Given host verdicts, then the summary lists the governing verdict (highest ratio; ties by subject kind,
  subject id, check id, station and case, ascending, null first, S2), every failing member, all `NEEDS_ENGINEER` and `ERROR` verdicts, and a
  list stated as "top N of M" with N from the basis. Test: `test_calcs_golden.py::test_case[summary-basic]`.
- AC36. Given frames without any verdict (for example concrete columns, which the CSI design results do not cover,
  S-12 §1 step 13), then they are listed in `not_designed` and the status is not `PASS`. Test:
  `test_calcs_golden.py::test_case[summary-not-designed]`.
- AC37. Given a previous summary, then each member (subject kind, subject id, check id) whose member status changed is
  listed once, in `newly_failing`, `newly_passing` or `other_changes` by the S5 table, with both statuses and both
  member ratios; members on one side only are in `appeared` or `disappeared`. Test:
  `test_calcs_golden.py::test_case[summary-previous]`.
- AC50. Given one member with two verdicts of one check (two stations, or two cases), one `PASS` and one `FAIL`, then
  the member's status is `FAIL` and its member ratio is the larger ratio (S5), both verdicts are kept in the verdict
  lists, and the member appears once in `members` and `failing_members`. Test:
  `test_calcs_golden.py::test_case[summary-member-worst]`.
- AC38. Given an empty verdict set, then the status is `NEEDS_ENGINEER` with the message "no design results". Test:
  `tests/unit/calcs/test_summary.py::test_empty`.

### 3.8 Section size rounding (§4.10)

- AC39. Given a required size and a basis increment, then the result is the smallest multiple of the increment not
  below the required size. An exact multiple stays the same. A required size above a multiple by any amount, however
  small, gives the next multiple (never a smaller size). Test: `test_calcs_golden.py::test_case[round-up]`,
  `::test_case[round-exact]`, `::test_case[round-just-above]`.
- AC40. Given a rule other than `up`, then `NotImplementedGap` CG-2. Given a required size that is not positive, then
  `OUT_OF_RANGE` (§5 bounds). The calc reads no `compare.*` field. Never a clamped value. Test:
  `tests/unit/calcs/test_rounding.py::test_edge_cases`.
- AC41. Over generated inputs (exact fractions), the result is a multiple of the increment, at least the required size,
  and less than the required size plus the increment. Test: `tests/property/test_rounding.py::test_rounding_properties`.

### 3.9 Element count and position comparison (§4.11)

- AC42. Given two placement sets, then counts per element type and per story are reported for each side with their
  difference. Test: `test_calcs_golden.py::test_case[placement-counts]`.
- AC43. Given a frame with the same id whose ends are swapped, then `reversed`. Given one moved by exactly the
  tolerance (a 3-4-5 offset), then `same`. Given one moved by more, then `moved` with the distance. Test:
  `test_calcs_golden.py::test_case[placement-frames]`.
- AC44. Given an area with the same points starting at another vertex, then `same`. In the reverse order, then
  `reversed`. With another point count, then `reshaped`. Test: `test_calcs_golden.py::test_case[placement-areas]`.
- AC45. Given unmatched ids with exactly one geometric partner each way, then a `renamed` pair. Given several
  candidates, then `ambiguous` with every candidate listed, never a silent choice. Test:
  `test_calcs_golden.py::test_case[placement-renames]`.
- AC46. Every golden data file has a non-empty `source`, `method_ref` naming a rule of this spec, `synthetic: true`,
  and no field outside its schema. Test: `tests/golden/test_golden_files.py::test_sources_present`.

### 3.10 Kinds

- AC47. Given each kind of §4.6 to §4.11 and `harness.expected_effects/1`, when a valid fixture and one invalid fixture
  per rule (counts that do not match rows, an unsorted list, a `fingerprint` not of the form `fp1:<64 hex>`, a `top`
  label that does not state N and M, an unknown field) are validated, then the valid one passes and each invalid one
  fails on its rule. Registering a calc kind in a neutral family is refused (contract §4.10.1). Test:
  `tests/contract/test_calc_kinds.py::test_fixtures`.

## 4. Design

### 4.1 Package layout and public API

| Module | Public names | Who may import |
|---|---|---|
| `eng_harness.calc` | `calc` (decorator), `CalcDef`, `CalcInput`, `InputMeta`, `RefMeta`, `TraceBuilder`, `CalcStatus`, `CalcRegistry`, `CalcRegistryError`, `NotImplementedGap` (re-exported from `eng_harness.errors`) | calc modules, CalcPort, tests |
| `eng_harness.kinds.calcs` | the payload models of §4.6 to §4.11, `harness.expected_effects/1`, `CalcMeta` | calc modules, spec 0006 (page, report), spec 0007 |
| `eng_harness.calcs` | `REGISTRY` (the `CalcRegistry` of the shipped calcs), `same_state` | CalcPort, spec 0002 (fingerprint comparison), tests |

Internal modules: `_calc/_hash.py` (import closure and content hash), `_calc/_approvals.py` (file loader, status
resolution, `check_approvals`), `_calc/_port.py` (`HarnessCalcPort`, `CalcSettings`), and the calc modules
`calcs/_state.py` (section keys and canonical form, §4.6), `calcs/_compare.py` (tolerance comparison, §4.7),
`calcs/model_fingerprint.py`, `calcs/model_diff.py`, `calcs/readback_check.py`, `calcs/design_summary.py`,
`calcs/section_round.py`, `calcs/placement_compare.py`, plus `calcs/approvals.yaml` and `calcs/calcs.lock.json`.
`src/eng_harness/calcs/**` is a protected path (CODEOWNERS) and R1 (`.gate/risk-map.yml`). The engine plan T1
already declares it in `calc_modules`, so gate FB005 applies.

### 4.2 Calcs and the registry

```python
@calc(
    id="harness.model_diff",
    version=1,
    output_kind="harness.model_diff/1",
    title="Difference report between two model states",
    method_source="eng-harness spec 0003 §4.7 (D1 to D7); 18 §4 step 4",
    verification="draft",
)
def model_diff(inp: DiffInput, meta: InputMeta, trace: TraceBuilder) -> ModelDiff: ...
```

- **Stable ids.** An id names one method. Registration is explicit: `calcs/__init__.py` imports each calc module and
  builds `REGISTRY`. There is no discovery or global registration. A change of output for the same input is a new
  version, with a golden diff report (process/10 §5). A calc is never renamed. A removed calc keeps its id in the lock
  file (AC2).
- **Pure functions.** Arguments: the validated input model (`CalcInput`, a contract `ParamModel`, frozen,
  `extra="forbid"`), `InputMeta` (per input field a `RefMeta`: `result_id`, `kind`, `complete`, `model_id`,
  `model_revision`, `parents`, `producer_tool`; built by the CalcPort from the records, so the function never reads the
  store) and the `TraceBuilder`. Return: the payload model without `calc`, `draft` and `trace`, which the framework
  adds. No I/O, clock, randomness or global state. All arithmetic that decides a comparison is exact (`Fraction`). A
  float is produced only for display values, and the payload says which fields those are.
- **Bounded inputs.** Kind payloads are bounded by the contract. In addition, the total of list items over all
  referenced records is at most `CalcSettings.max_items` (a resource limit in `harness.toml`, spec 0006; not
  engineering content), else `LIMIT_EXCEEDED` (AC15). Scalar inputs use Pydantic's constrained types
  (`PositiveFloat`, `NonNegativeFloat`, `PositiveInt`), so calc modules hold no literal bound (FB005).
- **Constants.** Only `Cited` values or design-basis fields. The six calcs of this spec have **no** constant. Every
  tolerance, increment and count comes from the design basis (§4.4). A future calc constant is a `Cited` recorded in
  the trace as a `TraceConstant`.
- **Statuses** (`CalcStatus`): `draft`, `verified`, `approved`, `withdrawn` (10 §4, process/10 §7). The decorator
  declares `verification` (`draft` or `verified`), which is part of the hash. `approved` and `withdrawn` come only from
  `approvals.yaml` (§4.5).
- **Errors in a calc.** A calc raises `ContractError` `INVALID_ARGUMENT` (with `field`) for an input it cannot use, and
  `NotImplementedGap` for a gap of §11. Every other exception is a defect, reported as `INTERNAL` with an incident id
  by the CalcPort. Engineering outcomes (a failing read-back, missing results) are payload statuses, never exceptions.

### 4.3 What calc modules may import

`eng_harness.calc`, `eng_harness.kinds.calcs`, other modules under `eng_harness.calcs` (helpers), `eng_contract.quantity`,
`eng_contract.cited`, `eng_contract.trace`, `eng_contract.canonical`, `eng_contract.units` (`kind_for_field`, `unit`),
`eng_contract.refs` (`RefString`, `JsonPointer`), `eng_contract.errors` (`ContractError`, `ErrorCode`),
`eng_contract.kinds` and its submodules, `eng_contract.verdicts`, `pydantic`, `fractions`, `math`, `hashlib`,
`enum`, `typing`, `collections.abc`, `itertools`, `functools`, `operator`, `__future__`, `eng_contract.params`
(`eng_param`, for ref-capable inputs) and `eng_harness.kinds.footing` (footing calcs). `calcs/__init__.py` may import
`read_lock` and `removed_ids` through `eng_harness.calc`, which re-exports them from `eng_harness._calc._hash`.
Everything else is refused by the rules test (AC3). Imports are top level only (AC7).

The rules test covers every module under `calcs/`, subpackages included (`calcs/footing/`), and mirrors FB005,
including form A4 of amendment B-438 (an integer literal as the `version=` keyword of `calc(...)`). Amendment (B-437).

### 4.4 Design-basis fields

A calc that needs basis values takes the run's basis as an input field `basis` (a reference to the
`basis.design_basis/1` result). It reads the named paths of the table below, never any other path. It checks each
field's `unit`, `confirmed: true` and bounds, and records each as a `TraceInput` with `ref`
`<basis result>#/fields/<path>`. `CalcInfo.basis_fields` lists these paths so the workflow (spec 0007) declares them
required and the engine refuses to start without them (engine invariant 5). Reading the field object, rather than a
`/value` pointer, avoids the unit-suffix conflict of Q1 **[added]**.

| Path | Unit | Bounds | Used by | Source of the value |
|---|---|---|---|---|
| `compare.length` | `mm` | ≥ 0 | §4.7, §4.8, §4.11 | Template or engineer (13 §3); no default |
| `compare.angle` | `deg` | ≥ 0 | §4.7, §4.8 | same |
| `compare.stress` | `MPa` | ≥ 0 | §4.7, §4.8 | same |
| `compare.unit_weight` | `kN/m3` | ≥ 0 | §4.7, §4.8 | same |
| `compare.line_load` | `kN/m` | ≥ 0 | §4.7, §4.8 | same |
| `compare.area_load` | `kPa` | ≥ 0 | §4.7, §4.8 | same |
| `compare.ratio` | `1` | ≥ 0 | §4.7, §4.8 (dimensionless properties such as `nu_ratio`, `scale_ratio`) | same |
| `modeling.section_increment` | `mm` | > 0 | §4.10 | 13 §2 `modeling` ("rounding increment for new section sizes") |
| `modeling.section_rounding` | — | enum `up` | §4.10 | same |
| `report.top_n` | — | integer ≥ 1 | §4.9 | Template or engineer |

The `compare.*` section is not in 13 §2. Q2 proposes it to spec 0004. These seven are exactly the quantity kinds that
occur in the neutral model kinds of contract §4.10.2.

### 4.5 Content hash and approvals

**Content hash** (10 §4, extended to imported helpers by د8). `content_sha256` is
`payload_sha256` (contract §4.3.1) of this object:

```
{"hash_version": "harness.calc_hash/1", "calc_id", "version", "title", "method_source", "verification",
 "output_kind", "input_schema": <CalcInput JSON Schema>, "output_schema": <kind payload JSON Schema>,
 "modules": {<dotted name>: <SHA-256 of the UTF-8 source, CRLF and CR normalized to LF>},
 "eng_contract_version": eng_contract.__version__}
```

`modules` holds the calc's module and every module of `eng_harness` it imports, transitively. This includes helpers,
`eng_harness.calc` and `eng_harness.kinds.calcs`. The closure is found statically with `ast` (relative imports
resolved, `if TYPE_CHECKING` blocks included), without importing anything new: modules are found by file lookup under
the `eng_harness` source root, not `importlib.util.find_spec`, which would run parent `__init__` modules. A parent
package's `__init__` is hashed only when an import names that package and takes an attribute from it, never as an
implicit parent (otherwise `calcs/__init__.py`, which imports every calc, would put every calc into every calc's
closure; amendment B-388, B-141 review). Third-party and standard-library
modules are not hashed: golden tests guard them (Q8). A framework change therefore invalidates every approval. This
is deliberate, so no change to a calc's behavior keeps an approval.

**`approvals.yaml`** (`src/eng_harness/calcs/approvals.yaml`; protected; changed by the owner only, process/06 §4;
never by an agent, ADR-0028 §4):

```yaml
schema: 1
approvals:   # calc_id, version, content_sha256, approver, date (YYYY-MM-DD), verification_record, pull_request
  []
withdrawn:   # calc_id, version, content_sha256 or "any", date, reason, advisory
  []
```

The loader uses a safe YAML parser, allows only this schema (Pydantic, `extra="forbid"`), and refuses tags, anchors
and duplicate keys (AC9). `verification_record` is a repository path under `docs/verification/calcs/`. Status
resolution: a matching `withdrawn` entry wins, then an exact `approvals` match (id, version, hash), else the declared
`verification`. `check_approvals()` reports `stale_approval` (hash differs; the calc returned to `verified` or `draft`
automatically, process/10 §5) and `unknown_calc`. It runs in a contract test (unknown ids fail; stale entries are
reported in the test output, not failed, because a stale entry is the intended effect of a change).

**Production runs.** The engine spec has no run class. This spec adds one: `HarnessCalcPort(..., run_class=TRIAL |
PRODUCTION)`, set by the command line (spec 0006) **[added]**. `preflight(calc_ids) -> list[CalcRefusal]` runs before
`Engine.start`, and a non-empty result refuses a production run. `run` checks again. In production only `approved`
calcs run (11 §4). `withdrawn` calcs never run. In a trial run, `draft` and `verified` calcs run with `draft: true`
(10 §4). `CalcRefused` is a `StepError` with the harness codes `CALC_NOT_APPROVED` and `CALC_WITHDRAWN`, which this
spec adds to `HarnessCode` (engine §6) **[added]**.

**Owner listing.** Each calc ships a verification record `docs/verification/calcs/<calc id>.md` (status draft: method
source, golden cases with their results, boundary and property tests, reviewer, findings) and a lock entry. The owner
queue lists every calc with its hash (§11 Q10).

### 4.6 Calc 1: model fingerprint `harness.model_fingerprint` v1

**Purpose.** Detect any change in the model state read (18 step 3), deep enough to see a moved column (ج9), for the
host-state check (engine §4.5.4, `HostModelState.fingerprint`) and approval bindings.

**Input** `FingerprintInput`: up to eight optional reference fields, one per neutral model kind: `stories`
(`model.stories/1`), `grids` (`model.grid_system/1`), `frames` (`model.frame_placements/1`), `areas`
(`model.area_placements/1`), `sections` (`model.sections/1`), `materials` (`model.materials/1`), `loads`
(`model.load_set/1`), `restraints` (`model.joint_restraints/1`). At least one is set. All are `engineering_quantity`
references (no literal). The read set the workflow supplies is fixed by spec 0002 from what S-12 §1 step 3 can read.

**Output kind** `harness.model_fingerprint/1`: `method: "harness.fp/1"`, `model_id`, `model_revision`, `sections`
(sorted by kind name: `kind`, `result_id`, `items`, `sha256`, `complete`), `covered` (kind names), `complete`,
`fingerprint` (`"fp1:"` followed by 64 hex digits; fits `ModelState.fingerprint`, contract §4.5.5).

**Method.**

- F1. Each record's normalized payload (contract §4.4) is the section's content.
- F2. Lists are put in canonical order. A named list is sorted by its key (table below), compared as UTF-16 code-unit
  sequences like RFC 8785 keys. A list of unnamed rows is sorted by the canonical JSON bytes of each row, so
  duplicates are kept. Ordered lists keep their order: stories (bottom to top, validated by the contract), area
  `points` and `joints` (vertex order carries orientation and local axes).
- F3. Section hash = SHA-256 of `canonical_json` of the reordered payload. Numbers are written by RFC 8785 rules
  (`-0.0` as `0`). **No rounding**: a change in the last bit is a change (Q3).
- F4. `fingerprint = "fp1:" + payload_sha256({"method": "harness.fp/1", "sections": {kind: sha256}})`, so a section
  that is left out changes it (AC20).
- F5. Every record must have the same `producer.host.model_id` and `model_revision`, else `INVALID_ARGUMENT` (AC23).
  `complete` is the conjunction of the records' `complete`.
- F6. `same_state(a, b)` (pure helper): `unknown` if either is incomplete or their `covered` lists differ, `same` if
  the fingerprints are equal, else `different`.

| Kind | List | Key |
|---|---|---|
| `model.grid_system/1` | `systems`, `systems[].lines` | `name`, `id` |
| `model.frame_placements/1` | `frames` | `id` |
| `model.area_placements/1` | `areas` | `id` (`points`, `joints` ordered) |
| `model.sections/1` | `frame_sections`, `area_sections` | `name` |
| `model.materials/1` | `materials` | `name` |
| `model.load_set/1` | `patterns`, `combinations`; `combinations[].items`, `frame_loads`, `area_loads` | `name`; canonical row bytes |
| `model.joint_restraints/1` | `joints` | `joint` |

**Trace.** Inputs (each section's ref with its `payload_sha256` as value), one step per section (`items`, `sha256`,
source "F2, F3") and the overall step (source "F4").

**Edge cases.** An empty list (zero frames) is hashed, not skipped. Mixed models or revisions are refused. A truncated
read (`complete: false`, S-12 §2 "no paging") gives an incomplete fingerprint, never `same`. The file save time is not
part of the content (Q4). The same model read in other host units gives the same canonical values only if the adapter
converts exactly (contract §4.7.4). Otherwise the fingerprint differs and the difference report shows changes within
tolerance. That outcome is safe.

**Verification cases** (method source: this section and RFC 8785; golden files `fingerprint-*.json`): (a) canonical
bytes of a two-frame, one-section read set written by hand from F2 and F3, with the hash computed by `hashlib` in the
test (AC21); (b) the same set with frames listed in reverse order gives the same fingerprint; (c) one frame end moved
by any amount changes the `frames` hash only (the moved-column case of ج9); (d) area points rotated by one vertex
change the hash (F2 keeps order); (e) properties: permutation invariance, change sensitivity (Hypothesis).

### 4.7 Calc 2: difference report `harness.model_diff` v1

**Purpose.** 18 step 4 and A5: show every engineer change since the last recorded revision, and the before and after
of a write (A1, §4.8).

**Input** `DiffInput`: `before` and `after` (each a `FingerprintInput`-shaped group of references) and `basis`.
`before` is `stale_ok`; `after` and `basis` are not (§4.13).

**Output kind** `harness.model_diff/1`: `before`, `after` (`model_id`, `model_revision`, `covered`), `tolerances`
(per quantity kind: `value`, `unit`, `ref`), `changes` (sorted by section and key: `section`, `key` (list of strings),
`change` `added` | `removed` | `changed` | `ambiguous`, `before`, `after` (the whole object for added, removed and
ambiguous), `properties` (for changed: `pointer`, `before`, `after`, `unit`, `quantity_kind`, `tolerance`, `rule`)),
`within_tolerance` (same property rows), `not_compared` (section kinds), `counts` (per section: added, removed,
changed, ambiguous, unchanged, within tolerance), `identical`, `complete`.

**Method.**

- D1. Sections are compared only when both sides hold them, with the same kind version and `units: canonical/1`.
  Otherwise the section goes to `not_compared` and `complete: false`.
- D2. Objects are matched by key: the §4.6 keys for named lists. Unnamed rows use these keys: `frame_loads` by
  (`frame`, `pattern`, `direction`), `area_loads` by (`area`, `pattern`, `direction`), combination `items` by
  (`case.case`, `case.case_type`, `case.step`), stories by `name`. A key that occurs more than once on a side is
  `ambiguous` (both object lists shown). It is counted as a change unless both sides are byte-identical. Keys are
  compared exactly: no case folding or trimming (Q5).
- D3. A numeric property's quantity kind comes from its field name (`kind_for_field`, contract §4.7.2). It is equal
  when `|Fraction(after) − Fraction(before)| <= Fraction(tolerance)`, exactly, and changed otherwise. Equal but not
  identical values go to `within_tolerance`.
- D4. Strings, booleans, enums and `null` compare exactly. A numeric field without a known suffix (none exists in the
  0.1 model kinds) compares exactly. A type change (number to `null`, one `shape.type` to another) is a change of the
  enclosing pointer.
- D5. Nested objects are compared member by member (pointer per leaf). Ordered lists (points, joints) are compared
  index by index. A length change reports the whole list as one changed property.
- D6. No normalization: angles are not wrapped, orientation is not canonicalized, and units are not converted (stored
  data is canonical). When in doubt the calc reports a change. A false change is shown to the engineer, and a hidden
  change would be overwritten (A5).
- D7. `identical` is true only when there are no changes and no ambiguous keys, nothing is in `not_compared`, and both
  sides are complete.

**Trace.** The tolerances as `TraceInput`s from the basis; per section a step with its counts (source "D1 to D5").
Property rows carry their rule id. The rows are the item-level trace.

**Edge cases.** Before and after may belong to different model ids (a working copy, `derived_from`). Both are
recorded. Records with `complete: false` make the report incomplete, and they are still compared. A tolerance is
required for every quantity kind of §4.4 even when no such property changed (AC26), because the calc does not know in
advance which properties differ. Sign and axis conventions are those of the neutral kinds (global coordinates for
points; `rotation_deg` as stored). Forces are out of scope, so `forces.member_end/1` convention G-3 does not apply.

**Verification cases** (method source: this section; golden files `diff-*.json`): a section change on one frame (one
`changed` row, pointer `/section`); a frame added and one removed; a coordinate that differs by exactly the synthetic
tolerance (within tolerance) and one by the next representable float above it (changed); a tolerance of zero; a full
turn on `rotation_deg` (changed, D6); a duplicate load-row key (ambiguous); properties: identity and symmetry (AC27).

### 4.8 Calc 3: read-back check `harness.readback_check` v1

**Purpose.** 18 step 9 and P7: every written value matches the change set, and nothing else changed (A1).

**Input** `ReadbackInput`: `effects` (reference to `harness.expected_effects/1`), `before` and `after` (read-set
groups as in §4.7; only `before` is `stale_ok`, §4.13), `basis`. `harness.expected_effects/1` is defined here and produced by spec 0007 from the
change set (Q6). Its fields: `change_set` (`RefString`), `model_id`, `effects` (list of `item_id`, `section` (a
neutral model kind), `key`, `op` `set` | `add` | `remove`, `pointer` (for `set`), `value` (for `set`: the value; for
`add`: the whole object), `unit`).

**Output kind** `harness.readback_check/1`: `status` (`VerdictStatus`: `PASS`, `FAIL`, `NEEDS_ENGINEER`), `items` (per
effect: `item_id`, `result` `match` | `mismatch` | `missing` | `not_read`, `expected`, `read`, `tolerance`, `rule`),
`unexpected` (difference rows not explained by any effect), `diff` (the `harness.model_diff/1` payload computed in R1,
embedded), `complete`.

**Method.**

- R0 (independence, ب5). Every `after` record has `producer.host.model_id` equal to that of `before` (or its working
  copy), and a `model_revision` greater than the before records' revision. No `after` result id is also a `before`
  result id. The effects record has no `after` record among its parents. Otherwise `INVALID_ARGUMENT`. Expected
  values come only from the effects; read values come only from the after read set.
- R1. Compute the difference report from `before` to `after` with the helpers of §4.7 (same tolerances).
- R2. For each effect: section not in the after read set gives `not_read`. For `set`: object absent gives `missing`.
  Otherwise the value at `pointer` is compared by D3 and D4, giving `match` or `mismatch`. For `add`: the object is
  present and every leaf matches gives `match`, else `missing` or `mismatch`. For `remove`: absent gives `match`.
- R3. Each change in R1 (each changed property, added or removed object) must be explained by an effect with the same
  section and key whose pointer equals or is a prefix of the property's pointer. Unexplained changes go to
  `unexpected`. An ambiguous key or a `not_compared` section in R1 makes the result `NEEDS_ENGINEER`.
- R4. Status: `FAIL` if any `mismatch` or `missing` or anything is `unexpected`. Otherwise `NEEDS_ENGINEER` if any
  `not_read`, an incomplete side, or R3's ambiguity. Otherwise `PASS`.

**Trace.** Basis tolerances, counts of each result, and the status step (source "R4").

**Edge cases.** An effect whose before value already equals the expected value is `match` (the write was a no-op). A
section-thickness change changes every area that uses the section (S-12 §2). The workflow expresses this as one `set`
effect on `model.sections/1`, never as per-area effects. The S-12 read-back gaps (frame distributed loads, pattern
definitions, area-section thickness, restraints) give `not_read` until spec 0002 supplies typed table reads (S12-G8).
Seismic parameters have no neutral kind and no tool (S12-G5), so there is no effect for them. A change set holding one
is refused by spec 0007 (gap CG-1).

**Verification cases** (method source: this section; golden files `readback-*.json`): all effects matched (`PASS`); a
load value read back beyond tolerance (`FAIL`, `mismatch`); a section change on a frame that no effect names
(`unexpected`); a thickness of 0.2 expected and 200 read (`FAIL`, the unit-scale case of د6); an effect on a section
not read (`NEEDS_ENGINEER`); before and after given the same records (refused, R0).

### 4.9 Calc 4: design results summary `harness.design_summary` v1

**Purpose.** 18 step 14: governing ratios, failing members and changes from the previous revision, for the engineer
turn and the run report.

**Input** `SummaryInput`: `verdicts` (reference to `verdicts.set/1` with `source: host` verdicts, as spec 0002 maps
`csi_design_results`, Q7), optional `frames` (`model.frame_placements/1`), optional `previous`
(`harness.design_summary/1`), `basis` (`report.top_n`).

**Output kind** `harness.design_summary/1`: `status`, `counts` (per `VerdictStatus`), `governing` (one verdict row:
subject, check id, case, ratio, ratio limit, status), `governing_by_group` (per subject kind and check id),
`failing` (all `FAIL` verdicts, ratio descending), `failing_members` (distinct subjects), `attention` (all
`NEEDS_ENGINEER` and `ERROR` verdicts), `top` (`n`, `of_total`, `rows`, `label: "top N of M by ratio"`),
`not_designed` (frame ids without any verdict), `members` (every member of S5, sorted by its key: subject kind,
subject id, check id, `status`, `ratio`), `changes` (`newly_failing`, `newly_passing`, `other_changes`, each row with
the member key, both statuses and both member ratios; `appeared` and `disappeared`, member rows), `complete`.

**Method.**

- S1. Verdict statuses and ratios are taken as the host reported them. The contract already enforces `PASS` with ratio
  ≤ limit and `FAIL` with ratio > limit (contract §4.9.1). The summary recomputes no ratio and applies no limit of its
  own (contract Q5, owner queue OQ-Q8).
- S2. Order key: ratio descending, then subject kind, subject id, check id, `station_mm`, `case` ascending (exact
  comparison; strings by code point). A null `station_mm` or `case` sorts before every non-null value. Verdicts
  without a ratio are ranked after all others and never count as governing. Two verdicts equal on the whole key keep
  no input order: they are compared by their canonical JSON bytes **[added]**.
- S3. `governing` is the first verdict by S2. `governing_by_group` applies S2 within each group. `failing` and
  `attention` list every verdict: they are never truncated. `top` is the first `report.top_n` verdicts by S2, stated
  as "top N of M" (contract §4.2.5 rule 4).
- S4. `not_designed`: frames of `frames` with no verdict whose subject is (`frame`, id).
- S5. Members. A member is the key (subject kind, subject id, check id); stations and cases are not part of it.
  Member status is the worst of its verdicts in the order `FAIL` > `ERROR` > `NEEDS_ENGINEER` > `PASS` >
  `NOT_APPLICABLE` **[added]**; the member ratio is the largest non-null ratio of its verdicts, or null. `changes`
  compares `members` with `previous.members` key by key, so every key is unique on each side:

  | Previous member status | Current member status | Listed in |
  |---|---|---|
  | present, anything but `FAIL` | present, `FAIL` | `newly_failing` |
  | present, `FAIL` | present, `PASS` | `newly_passing` |
  | any other pair of different statuses, member present on both sides (for example `FAIL` to `NEEDS_ENGINEER`, `PASS` to `ERROR`, `FAIL` to `NOT_APPLICABLE`) | | `other_changes` |
  | equal statuses | | not listed (a ratio change alone is not a status change) |
  | absent | present | `appeared` (only here, whatever its status) |
  | present | absent | `disappeared` (only here, whatever its status) |
- S6. Status: `FAIL` if any `FAIL`. Otherwise `NEEDS_ENGINEER` if any `NEEDS_ENGINEER` or `ERROR`, any
  `not_designed`, no verdicts at all (message "no design results"), or an incomplete input. Otherwise `PASS`.

**Edge cases.** Several verdicts per member (stations, cases) are all kept in `failing`, `attention` and `top`; member
status and member ratio follow S5. Ties are broken by S2, never by input order. A `previous` without `members` (another
kind version) is refused with `REF_KIND_MISMATCH` by its `ref_kinds`. `top_n` larger than M lists all, still labeled "top M of M". The summary
makes no engineering judgment beyond ordering and set membership.

**Verification cases** (method source: this section; golden files `summary-*.json`): three synthetic host verdicts on
three frames with distinct ratios on both sides of their own `ratio_limit` (governing, failing and top-2 by S2 and S3);
two equal ratios (tie broken by subject id); frames without verdicts (`not_designed`, S6); a previous summary in which
one member failed and now passes, one moves from `FAIL` to `NEEDS_ENGINEER` and one appears (S5); one member with a
`PASS` and a `FAIL` verdict at two stations (member `FAIL`, S5); an empty set (S6).

### 4.10 Calc 5: section size rounding `harness.section_round` v1

**Purpose.** 11 §4: a new section size is the output of this calc or an engineer input, never a decision.

**Input** `RoundInput`: `required` (reference to a length quantity in `mm`, > 0: a calc output or a
`basis.engineer_input/1` field; `engineering_quantity`), `basis` (`modeling.section_increment`,
`modeling.section_rounding`). No comparison tolerance is read: a `compare.*` field compares model states (§4.4) and is
no rounding allowance.

**Output kind** `harness.section_size/1`: `required`, `increment` (quantities), `multiple` (integer), `size`
(`Quantity` in `mm`), `status` (`PASS`).

**Method** (rule `up`, the only rule in v1; source: 13 §2 `modeling`, "rounding increment for new section sizes", and
11 §4).

- N1. With exact fractions `r` and `i` (required and increment, each `Fraction(float)`, so the stored binary value is
  used exactly): `n = ceil(r / i)`, by integer arithmetic on the fractions.
- N2. `size = n × i`, converted to float once. `multiple = n`. Hence `size >= r` and `size − r < i`: the size is never
  below the required size.
- N3. `r > 0` (input bound) gives `n >= 1`. The value is never clamped.
- N4. A rule other than `up` raises `NotImplementedGap` CG-2.

A required size that carries float noise just above a multiple (for example a computed value one unit in the last
place above it) rounds to the next multiple. That is conservative. An allowance for such noise would be engineering
content: it is not applied here and is Q14.

Multiples are counted from zero. The calc does not choose from a catalog, enforce a minimum dimension (13 §2
`limits`) or apply code limits. Those are separate checks.

**Trace.** `required` and `increment` as inputs; steps `r / i`, `n`, `size` with formulas and source "N1, N2".

**Verification cases** (method source: this section; golden files `round-*.json`): a required size between two
multiples (rounds to the upper); an exact multiple (unchanged); a required size above a multiple by the smallest
synthetic amount the fixture states (the next multiple, never the lower one); properties of AC41.

### 4.11 Calc 6: element count and position comparison `harness.placement_compare` v1

**Purpose.** A1 and A5 for geometry. It covers what the difference report cannot show for renamed or reversed objects.
It extends the count check of ب2.

**Input** `PlacementInput`: `a_frames`, `b_frames` (`model.frame_placements/1`), `a_areas`, `b_areas`
(`model.area_placements/1`; each side needs frames, areas or both, and the same on both sides), `basis`
(`compare.length`). `a_*` is the earlier side and is `stale_ok`; `b_*` and `basis` are not (§4.13).

**Output kind** `harness.placement_comparison/1`: `counts` (per element class and type, `frame` × {`column`, `beam`,
`brace`, `other`} and `area` × {`slab`, `wall`, `deck`, `other`}, and per story with `unassigned` for `null`: `a`,
`b`, `difference`), `by_id` (per common id: `result` `same` | `reversed` | `moved` | `reshaped`, `distance_mm` (display
float)), `renamed` (pairs), `ambiguous` (an id with its candidates), `only_in_a`, `only_in_b`, `equal`, `complete`.

**Method.**

- P1. Counts per side, and differences as `b − a` (integers).
- P2. Distance between points uses exact squared distance: `d² = Σ (Fraction(p) − Fraction(q))²`, and it is within
  tolerance when `d² <= t²`. `distance_mm` is `sqrt` of `d²` in float, for display only.
- P3. Frames with the same id: `same` if both ends are within tolerance of the same ends; else `reversed` if each end
  is within tolerance of the other frame's opposite end; else `moved`, with the larger end distance.
- P4. Areas with the same id: different point counts give `reshaped`. Otherwise `same` if some cyclic shift of b's
  points (the smallest such shift) puts every point within tolerance of a's in order; `reversed` if a shift of the
  reversed order does; else `moved`, with the largest point distance at shift zero.
- P5. Ids on one side only are paired by geometry within the same element class: candidates are objects whose P3 or P4
  result would be `same` or `reversed`. Exactly one candidate in each direction gives `renamed`. More than one gives
  `ambiguous` with all candidates listed. None gives `only_in_a` or `only_in_b`.
- P6. `equal` holds when every count difference is zero, every `by_id` result is `same`, and nothing is renamed,
  ambiguous or one-sided.

**Edge cases.** Coordinates are global (`Point3`, contract §4.10.2). Two models with different origins are out of
scope (no offset parameter; non-goal). A frame of zero length cannot occur (`i != j`, contract). Section and kind
changes are not reported here (the difference report covers them). P5 is quadratic in the number of unmatched
objects, so the size is bounded by `max_items`.

**Verification cases** (method source: this section; golden files `placement-*.json`): counts of a synthetic model
with one column and one beam fewer on side b; a frame with swapped ends (`reversed`); a frame end moved by a synthetic
(3, 4, 0) offset against a tolerance of 5 (`same`, `d² = t²`) and against a slightly smaller tolerance (`moved`); an
area with its points rotated by one vertex (`same`) and reversed (`reversed`); a renamed frame (one candidate) and two
coincident frames (`ambiguous`).

### 4.12 CalcPort and the engine

`HarnessCalcPort(registry, approvals, store, settings, run_class, clock, ids)` implements engine §4.8 `CalcPort`:

1. `describe` (AC13). `CalcInfo.ref_rules` is the only channel through which the engine learns each field's
   `RefRule`, `stale_ok` included.
2. `run(calc_id, args)`: status check (AC11). Then `validate_input(InputCls, args, source=store,
   current_revision=lambda _: None, policy=InputPolicy(require_refs=True))`. The engine already checked staleness
   (engine invariant 3) with the `RefRule` it takes from `CalcInfo.ref_rules` for each argument path (§4.13), so the
   CalcPort does not repeat it with a partial revision map. An argument path missing from `ref_rules` is resolved by
   the engine with `stale_ok` false. Engine invariant 3 and `CalcInfo` change accordingly (Q11). Then the record metadata
   (`InputMeta`), the item limit, the pure function, `CalcMeta` (`id`, `version`, `content_sha256`, `status`),
   `draft`, and the trace. The result is stored with `ResultStore.put` (kind, parents, provenance `tool: "harness"`,
   `tool_version` = the package version, `inputs` = references), and the return is `make_success` with a summary of
   at most the counts and status.
3. Contract errors become failure envelopes. `NotImplementedGap` and `CalcRefused` propagate as `StepError`s (engine
   §6). Any other exception is `INTERNAL`.
4. Code-pack checks (amendment B-405). The same port serves the checks of the `structural-codes` packs through one route
   and no other: `CodePackRoute` in `_calc/_code_packs.py`, defined by [spec 0010](0010-design-isolated-footing.md) §4.3
   and [spec 0013](0013-column-workflow.md) §4.5, which `HarnessCalcPort` consults for an id that does not start with
   `harness.` (every calc id of this spec does). The route runs only the ids of its fixed allowlist; any other id is
   `NOT_FOUND` (§6), and no exception of `structural_codes` reaches the engine as such. Its `CalcInfo` has the fields of
   item 1, with `status` the check's lifecycle state (the four values of a calc status) and `version` as spec 0010 Q20
   settles (open: a merged check has no integer version). The run-class rule of §4.5 applies unchanged: in `production`
   only `approved` checks run and any other is refused with `CalcRefused` before evaluation; a `withdrawn` check is
   refused in both run classes with `CalcRefused` `CALC_WITHDRAWN` before evaluation (so the pack's `CheckNotUsable` is
   never reached); in `trial` a check that is not `approved` runs with `draft: true`. Results are stored as
   `verdicts.set/1` with provenance `tool: "structural-codes"` (not `harness`, item 2). The code-pack checks themselves,
   their content hash and their approvals belong to the packs (CF), not to this spec's `approvals.yaml`. Criteria and
   tests: spec 0010 AC3, AC4 and spec 0013 AC13 (`tests/unit/calcs/test_code_pack_route.py`).

The kinds of §4.6 to §4.11 and `harness.expected_effects/1` are registered with `KindRegistry.extend` beside the
engine's harness kinds (engine plan T3, `_kinds.py`). The CalcPort stores calc results with `producer.host` null:
they are not read from a host model (contract §4.4), so they are never stale by revision (contract §4.6.2 step 6).

### 4.13 Older-revision inputs (`stale_ok`) **[added]**

The difference report, the read-back check and the placement comparison compare a model with an earlier state of the
same model by design: steps 4 and 9 of 18 §4 and A1, A5 cannot run otherwise. Engine invariant 3 refuses every host
reference below the model's current revision with `REF_STALE`, unless the parameter declares `stale_ok` (contract
§4.6.2 step 6, §5). These calcs therefore declare `stale_ok` on exactly the fields that name the earlier state, and on
no other field:

| Calc | `stale_ok` fields (every reference inside the group) | Never `stale_ok` |
|---|---|---|
| `harness.model_fingerprint` | none | all read-set fields |
| `harness.model_diff` | `before` | `after`, `basis` |
| `harness.readback_check` | `before` | `after`, `effects`, `basis` |
| `harness.design_summary` | none (`previous` is a calc result without `host`, never stale) | `verdicts`, `frames`, `basis` |
| `harness.section_round` | none | `required`, `basis` |
| `harness.placement_compare` | `a_frames`, `a_areas` | `b_frames`, `b_areas`, `basis` |

Why this is safe: the later side (`after`, `b_*`) must still be at the current revision, so a stale read-back cannot
pass (ب5). The read-back check's R0 also requires the after revision to be greater than the before revision, so the
two sides can never be swapped or equal. Why it departs from the architecture: 04 §3.4 says "a calculation never
mixes revisions of one model", and 11 §6 invariant 3 states no exception. Mixing two revisions is the purpose of
these three calcs, and each payload records both revisions. This is raised as Q13 for a hub amendment (AC48, AC49).

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| Read-set fields (§4.6) | `model.*` payloads | canonical | contract kinds | references only; `stale_ok` only as in §4.13 | Read tools, spec 0002 |
| `basis` | `basis.design_basis/1` | per field (§4.4) | §4.4 | reference only | Spec 0004 |
| `effects` | `harness.expected_effects/1` | canonical | §4.8 | reference only | Spec 0007 |
| `verdicts` | `verdicts.set/1` (host) | — | contract §4.9.1 | reference only | Spec 0002 |
| `required` | length quantity | `mm` | > 0 | reference only | Calc output or engineer input |
| `CalcSettings.max_items` | `int` | — | ≥ 1 | no | `harness.toml` (spec 0006) |
| Outputs | the six `harness.*` kinds | canonical | §4.6 to §4.11 | stored results | this spec |

## 6. Errors

| Condition | Code | Fields |
|---|---|---|
| Input shape, literal under `require_refs`, cross-field rule, mixed models, missing or unconfirmed basis field, circular read-back inputs | `INVALID_ARGUMENT` | `field`, `hint` |
| Reference failures | `REF_NOT_FOUND`, `REF_POINTER_INVALID`, `REF_KIND_MISMATCH`, `REF_UNIT_MISMATCH`; `REF_STALE` (raised by the engine, invariant 3, for a field not `stale_ok`, §4.13) | contract §4.6.2 |
| Out of bounds | `OUT_OF_RANGE` | `field`, `expected`, `received` |
| Item limit | `LIMIT_EXCEEDED` | `expected {max}`, `received` |
| Unknown calc id | `NOT_FOUND` | — |
| Code-pack check id outside the route's allowlist, or unknown to the pack registry (§4.12 item 4) | `NOT_FOUND` | `check_id` |
| Calc defect | `INTERNAL` | `incident_id` |
| Not approved in production; withdrawn | `CalcRefused` (`CALC_NOT_APPROVED`, `CALC_WITHDRAWN`) **[added]** | calc id, status |
| Gap of §11 | `NotImplementedGap` (`NOT_IMPLEMENTED`) | gap id |

## 7. Non-goals

- Code checks themselves (phase 2, `structural-codes`); the CalcPort only routes them (§4.12 item 4). Choosing a
  section from a catalog. Minimum dimensions and code limits.
- Comparing total weight, modal periods and reactions (ب2 proposes them). This needs analysis results and its own
  tolerances (gap CG-3).
- Comparing a model with a drawing (base-point offset, `geom.*` kinds, 18 §6).
- Force results and their sign convention (G-3). Seismic parameters (CG-1).
- Rounding rules other than `up` (CG-2). Any default tolerance, increment or count.
- Marking any calc `verified` or `approved` (owner only).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A hidden change: a diff that misses an engineer edit, which is then overwritten (A5) | R1 | Full-depth fingerprint (ج9); "when in doubt, report" (D6); incomplete reads never `same` (F6, AC22) |
| A circular read-back passes (ب5) | R1 | R0 independence rule and its test (AC33) |
| A tolerance invented in code | R1 | No constants; basis fields only; FB005; AC26 |
| An approval survives a helper change (د8) | R1 | Hash over the static import closure (AC6) |
| Float noise at a tolerance boundary flips a result between platforms | R1 | Exact `Fraction` comparisons (D3, P2, N1) |
| A rounded section below the required size | R1 | N1 rounds the exact required value up with no allowance (AC39, AC41); any allowance is an owner decision (Q14) |
| Kind payloads change and old results no longer read | R2 | Kinds frozen per version (contract §4.10.1) |
| Large models exceed time or memory | R2 | `max_items`; quadratic step only on unmatched objects |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1, AC4 to AC9, AC11 to AC16, AC18, AC22, AC23, AC26, AC28, AC32, AC33, AC38, AC40 | Unit | `tests/unit/calcs/` |
| AC2, AC10, AC47, AC49 | Contract | `tests/contract/test_calc_lock.py`, `tests/contract/test_calc_kinds.py` |
| AC3 | Unit (source rules) | `tests/rules/test_calc_modules.py` |
| AC17, AC48 | Fake-host workflow (real engine and CalcPort, fake tool ports, real store) | `tests/workflow/test_calc_step.py` |
| AC19 to AC21, AC24, AC25, AC29 to AC31, AC34 to AC37, AC39, AC42 to AC45, AC50 | Golden (hand checks, data in `tests/data/golden/calcs/`) | `tests/golden/test_calcs_golden.py` |
| AC46 | Golden data lint | `tests/golden/test_golden_files.py` |
| AC19, AC20, AC25, AC27, AC41 | Property (Hypothesis, `derandomize=True`) | `tests/property/` |

Replay of calc steps (a completed calc step is not run again) is engine AC35. No program comparison applies: no host
computes these quantities (10 §6 item 2). Coverage floors 85% line and 75% branch. Mutation score at least 80% on
`calcs/**` and `_calc/**` (R1). Live checks are in §11 and in the plan §4. Under mutation testing (environment
variable `MUTANT_UNDER_TEST` set) `tests/contract/test_calc_lock.py` skips the lock-versus-registry comparison with an
issue reference and an expiry (the B-369 pattern), because mutants change the hashed source by design. Amendment
(B-437).

## 10. Version impact

Part of `eng-harness` 0.1.0. Each calc starts at version 1. Each kind starts at `/1`. The lock file and
`approvals.yaml` start with schema 1.

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | Conflict: contract basis paths are lowercase (`^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$`, contract §4.10.2), but unit suffixes such as `_MPa` and `_kN_m` are not, while 13 §2 shows `fc_MPa`. A `/value` reference to such a field cannot pass the suffix unit check | Owner | Amend the contract to allow `[A-Za-z0-9_]` after the first segment (minor version). Until then calcs read the field object (§4.4) |
| Q2 | The `compare.*`, `report.top_n` and `modeling.section_rounding` basis fields are not in 13 §2 (a rounding allowance is Q14, not a `compare.*` field) | Owner, spec 0004 | Add a `compare` template section (one tolerance per quantity kind) and `report.top_n`. No shipped default: the owner sets the values |
| Q3 | Fingerprint without rounding (F3) may differ between two reads if the host returns unstable floats | Owner, S-04 | Keep exact. If S-04 shows instability, decide from its data (a basis field for digits, or adapter-side normalization), never a literal |
| Q4 | 06 §6 includes the file save time and only counts and names. This spec hashes full content (positions, ج9) and leaves out the save time (a save without changes is not a change) | Owner | Accept. Amend 06 §6 by a hub change after S-04 |
| Q5 | Host object names compared exactly (D2). ETABS may treat names case-insensitively | Owner, local test | Exact for v1 (a case-only rename shows as removed plus added, which is safe). Revisit after the first local run |
| Q6 | The projection from the change set to `harness.expected_effects/1` belongs to spec 0007 | Owner, B-066 | Make it a calc of spec 0007 (approved like these), so the expected effects are as rigorous as the check |
| Q7 | The design summary assumes spec 0002 maps `csi_design_results` to host verdicts in `verdicts.set/1`, with `ratio_limit` from the basis | Owner, B-061 | Confirm in spec 0002 |
| Q8 | The content hash covers `eng-contract`'s version but not third-party libraries (Pydantic) | Owner | Accept. Golden tests run on every dependency update. Including them would invalidate every approval on each patch release |
| Q9 | `approvals.yaml` needs a YAML parser, which is a runtime dependency (ADR needed) | Owner | One package ADR for a safe YAML parser shared with plan 0004 (templates). Whichever task lands first writes it |
| Q10 | All six calcs ship `draft`: `harness.model_fingerprint`, `harness.model_diff`, `harness.readback_check`, `harness.design_summary`, `harness.section_round`, `harness.placement_compare` | Owner | Review the verification records and approve by `approvals.yaml` entries after the local tests |
| Q11 | Additions to the engine spec: the production run class, `CalcRefused` with two harness codes, and `CalcInfo.basis_fields` and `CalcInfo.ref_rules` (path to `RefRule`), from which engine invariant 3 builds each argument's `RefRule` (`stale_ok` false for a path not listed) | Owner | Accept. Amend engine spec §4.8 and invariant 3 in the engine plan's next task; spec 0006 adds the `--production` option |
| Q12 | `HostPort.model_state` (spec 0002) needs the fingerprint. In a production run it must be approved | Owner, B-061 | Spec 0002 computes it through the CalcPort, and the command-line preflight includes it |
| Q13 | Conflict: 04 §3.4 ("a calculation never mixes revisions of one model") and 11 §6 invariant 3 allow no older-revision input to a calc, but the difference report, read-back check and placement comparison need one (§4.13) | Owner, hub | Accept §4.13: `stale_ok` only on the earlier-state fields, the later side always current, both revisions recorded. Amend 04 §3.4 and 11 §6 by a hub change: "a calc mixes revisions only through parameters declared `stale_ok` for an earlier state" |
| Q14 | A required section size with float noise just above a multiple rounds to the next multiple (§4.10 N1). No source allows a rounding allowance, and a comparison tolerance is not one | Owner, spec 0004 | Keep no allowance in v1 (conservative). If the owner wants one, add a separate basis field (for example `modeling.section_rounding_allowance`, `mm`, no default) and a new calc version |
| Q15 | Spec 0010 Q10 and C2: the CalcPort serves code-pack checks through the one code-pack route of spec 0010 §4.3 and spec 0013 §4.5 (§4.12 item 4), with the run-class rule of §4.5 and §4.12; `NOT_FOUND` (§6) covers an id outside the route's allowlist | Owner | Accept (amendment B-405; draft until the owner approves) |
| CG-1 | Seismic parameters: no neutral kind and no tool (S12-G5, OQ-G8). No read-back or diff | Owner | Gap. Spec 0007 refuses such edits until `harness.seismic_parameters/1` and a tool exist |
| CG-2 | Rounding rules other than `up` | Owner | `NotImplementedGap` until the owner defines one |
| CG-3 | Total weight, modal periods and reactions comparison (ب2) | Owner | A later calc with its own basis tolerances, after phase 1 |
| L-1 | Needs local test: the fingerprint is stable over repeated reads, save and reopen, and sees the S-04 hand edits E1 to E10 | Owner | Run S-04, then the fake-fidelity recordings |
| L-2 | Needs local test: read-back on real ETABS reads, including unit scale (د6), frame load directions (S12-G9) and the table reads of S12-G8 | Owner | Acceptance A1 with a hand edit in every B-1 project (A5) |
| L-3 | Needs local test: the design summary against the ETABS design display on a model with failing members | Owner | One B-1 project |
