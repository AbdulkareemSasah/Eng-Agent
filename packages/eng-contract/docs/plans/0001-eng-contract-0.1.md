---
id: plan-b003-eng-contract-0-1
issue: "B-003"
spec: packages/eng-contract/docs/specs/0001-eng-contract-0.1.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: r2                 # binding for every pull request of this plan; never below the path risk floor
tasks:
  - id: T1
    title: Package skeleton and gate configuration
    files:
      - "packages/eng-contract/pyproject.toml"
      - "packages/eng-contract/README.md"
      - "packages/eng-contract/CHANGELOG.md"
      - "packages/eng-contract/AGENTS.md"
      - "packages/eng-contract/CLAUDE.md"
      - "packages/eng-contract/.gate/agents.yml"
      - "packages/eng-contract/.gate/risk-map.yml"
      - "packages/eng-contract/.gate/ratchet.json"
      - "packages/eng-contract/docs/local-testing.md"
      - "packages/eng-contract/src/eng_contract/__init__.py"
      - "packages/eng-contract/src/eng_contract/py.typed"
      - "packages/eng-contract/tests/unit/test_package.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first: ["packages/eng-contract/tests/unit/test_package.py::test_version_constants"]
    covers: []
    depends_on: []
  - id: T2
    title: Error codes, retry rules, warnings and ContractError
    files:
      - "packages/eng-contract/src/eng_contract/errors.py"
      - "packages/eng-contract/src/eng_contract/_types.py"
      - "packages/eng-contract/tests/unit/test_errors.py"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-contract/tests/unit/test_errors.py::test_retry_rules_per_code"
      - "packages/eng-contract/tests/unit/test_errors.py::test_code_specific_fields"
    covers: [AC10]
    depends_on: [T1]
  - id: T3
    title: Canonical JSON (RFC 8785) and payload hash
    files:
      - "packages/eng-contract/src/eng_contract/canonical.py"
      - "packages/eng-contract/src/eng_contract/_jcs.py"
      - "packages/eng-contract/tests/unit/test_canonical.py"
      - "packages/eng-contract/tests/property/test_canonical_props.py"
      - "packages/eng-contract/tests/data/jcs/**"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-contract/tests/unit/test_canonical.py::test_rfc8785_number_samples"
      - "packages/eng-contract/tests/unit/test_canonical.py::test_key_order_and_escaping"
      - "packages/eng-contract/tests/unit/test_canonical.py::test_rejects_non_json_values"
      - "packages/eng-contract/tests/unit/test_canonical.py::test_large_integral_floats"
      - "packages/eng-contract/tests/property/test_canonical_props.py::test_round_trip_is_stable"
    covers: [AC1, AC2, AC3, AC4]
    depends_on: [T2]
  - id: T4
    title: ULID identifiers, clocks and id sources
    files:
      - "packages/eng-contract/src/eng_contract/ids.py"
      - "packages/eng-contract/src/eng_contract/_ulid.py"
      - "packages/eng-contract/tests/unit/test_ids.py"
      - "packages/eng-contract/tests/data/ids/**"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-contract/tests/unit/test_ids.py::test_seeded_ids_are_deterministic"
      - "packages/eng-contract/tests/unit/test_ids.py::test_monotonic_within_millisecond"
      - "packages/eng-contract/tests/unit/test_ids.py::test_overflow_raises"
    covers: [AC5, AC6]
    depends_on: [T3]
  - id: T5
    title: Units of canonical/1 with cited exact factors and CSI unit systems
    files:
      - "packages/eng-contract/src/eng_contract/units.py"
      - "packages/eng-contract/src/eng_contract/_unit_table.py"
      - "packages/eng-contract/docs/verification/units.md"
      - "packages/eng-contract/tests/unit/test_units.py"
      - "packages/eng-contract/tests/property/test_units_props.py"
      - "packages/eng-contract/tests/data/units/**"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-contract/tests/unit/test_units.py::test_factors_exact"
      - "packages/eng-contract/tests/unit/test_units.py::test_known_conversions"
      - "packages/eng-contract/tests/unit/test_units.py::test_dimension_mismatch"
      - "packages/eng-contract/tests/unit/test_units.py::test_suffix_lookup"
      - "packages/eng-contract/tests/unit/test_units.py::test_csi_unit_systems"
      - "packages/eng-contract/tests/property/test_units_props.py::test_round_trip_exact"
      - "packages/eng-contract/tests/property/test_units_props.py::test_single_rounding"
    covers: [AC30, AC31, AC32, AC33, AC37, AC38]
    depends_on: [T4]
  - id: T6
    title: Quantity and Cited
    files:
      - "packages/eng-contract/src/eng_contract/quantity.py"
      - "packages/eng-contract/src/eng_contract/cited.py"
      - "packages/eng-contract/tests/unit/test_quantity.py"
      - "packages/eng-contract/tests/unit/test_cited.py"
      - "packages/eng-contract/tests/property/test_quantity_props.py"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-contract/tests/unit/test_quantity.py::test_no_arithmetic"
      - "packages/eng-contract/tests/unit/test_quantity.py::test_comparisons"
      - "packages/eng-contract/tests/unit/test_quantity.py::test_hash_consistent_with_eq"
      - "packages/eng-contract/tests/property/test_quantity_props.py::test_order_consistent"
    covers: [AC34, AC35, AC36]
    depends_on: [T5]
  - id: T7
    title: Provenance, envelopes and result records
    files:
      - "packages/eng-contract/src/eng_contract/envelope.py"
      - "packages/eng-contract/src/eng_contract/records.py"
      - "packages/eng-contract/tests/unit/test_envelope.py"
      - "packages/eng-contract/tests/unit/test_records.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-contract/tests/unit/test_envelope.py::test_size_limits"
      - "packages/eng-contract/tests/unit/test_envelope.py::test_make_success_inlines_small_payloads"
      - "packages/eng-contract/tests/unit/test_envelope.py::test_discriminated_by_ok"
      - "packages/eng-contract/tests/unit/test_envelope.py::test_partial_data_consistency"
      - "packages/eng-contract/tests/unit/test_records.py::test_payload_location_exclusive"
    covers: [AC7, AC8, AC9, AC11, AC12]
    depends_on: [T6]
  - id: T8
    title: References, JSON Pointer and resolution rules
    files:
      - "packages/eng-contract/src/eng_contract/refs.py"
      - "packages/eng-contract/src/eng_contract/_pointer.py"
      - "packages/eng-contract/tests/unit/test_refs.py"
      - "packages/eng-contract/tests/property/test_refs_props.py"
    max_changed_lines: 300
    max_sessions: 3
    tests_first:
      - "packages/eng-contract/tests/unit/test_refs.py::test_parse"
      - "packages/eng-contract/tests/unit/test_refs.py::test_pointer_failures"
      - "packages/eng-contract/tests/unit/test_refs.py::test_not_found"
      - "packages/eng-contract/tests/unit/test_refs.py::test_kind_mismatch"
      - "packages/eng-contract/tests/unit/test_refs.py::test_unit_mismatch"
      - "packages/eng-contract/tests/unit/test_refs.py::test_staleness_rule"
      - "packages/eng-contract/tests/property/test_refs_props.py::test_pointer_round_trip"
    covers: [AC23, AC24, AC25, AC26, AC27, AC28, AC29]
    depends_on: [T7]
  - id: T9
    title: Input-parameter metadata and the validation pipeline
    files:
      - "packages/eng-contract/src/eng_contract/params.py"
      - "packages/eng-contract/src/eng_contract/_validation.py"
      - "packages/eng-contract/tests/unit/test_params.py"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-contract/tests/unit/test_params.py::test_definition_checks"
      - "packages/eng-contract/tests/unit/test_params.py::test_json_schema_metadata"
      - "packages/eng-contract/tests/unit/test_params.py::test_validation_order"
      - "packages/eng-contract/tests/unit/test_params.py::test_require_refs_policy"
      - "packages/eng-contract/tests/unit/test_params.py::test_refs_do_not_bypass_bounds"
    covers: [AC39, AC40, AC41, AC42, AC43]
    depends_on: [T8]
  - id: T10
    title: Verdicts, model issues and calculation traces
    files:
      - "packages/eng-contract/src/eng_contract/verdicts.py"
      - "packages/eng-contract/src/eng_contract/issues.py"
      - "packages/eng-contract/src/eng_contract/trace.py"
      - "packages/eng-contract/tests/unit/test_verdicts.py"
      - "packages/eng-contract/tests/unit/test_issues.py"
      - "packages/eng-contract/tests/unit/test_trace.py"
    max_changed_lines: 280
    max_sessions: 2
    tests_first:
      - "packages/eng-contract/tests/unit/test_verdicts.py::test_consistency_rules"
      - "packages/eng-contract/tests/unit/test_verdicts.py::test_model_equality"
      - "packages/eng-contract/tests/unit/test_issues.py::test_summary"
    covers: [AC35a, AC44, AC45]
    depends_on: [T9]
  - id: T11
    title: Kind names, the kind registry and the model.* kinds
    files:
      - "packages/eng-contract/src/eng_contract/kinds/__init__.py"
      - "packages/eng-contract/src/eng_contract/kinds/_registry.py"
      - "packages/eng-contract/src/eng_contract/kinds/_common.py"
      - "packages/eng-contract/src/eng_contract/kinds/model.py"
      - "packages/eng-contract/tests/contract/test_kinds.py"
      - "packages/eng-contract/tests/data/kinds/model.*/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-contract/tests/contract/test_kinds.py::test_kind_names_and_registry"
      - "packages/eng-contract/tests/contract/test_kinds.py::test_fixtures"
    covers: [AC46, AC47]
    depends_on: [T10]
  - id: T12
    title: forces.*, basis.*, verdicts.set and issues.model_check kinds
    files:
      - "packages/eng-contract/src/eng_contract/kinds/__init__.py"
      - "packages/eng-contract/src/eng_contract/kinds/forces.py"
      - "packages/eng-contract/src/eng_contract/kinds/basis.py"
      - "packages/eng-contract/src/eng_contract/kinds/verdicts.py"
      - "packages/eng-contract/src/eng_contract/kinds/issues.py"
      - "packages/eng-contract/tests/contract/test_kinds.py"
      - "packages/eng-contract/tests/data/kinds/forces.*/**"
      - "packages/eng-contract/tests/data/kinds/basis.*/**"
      - "packages/eng-contract/tests/data/kinds/verdicts.*/**"
      - "packages/eng-contract/tests/data/kinds/issues.*/**"
    max_changed_lines: 320
    max_sessions: 2
    tests_first:
      - "packages/eng-contract/tests/contract/test_kinds.py::test_fixtures"
      - "packages/eng-contract/tests/contract/test_kinds.py::test_basis_sources"
      - "packages/eng-contract/tests/contract/test_kinds.py::test_verdict_set_trace_refs"
    covers: [AC44, AC46, AC48]
    depends_on: [T11]
  - id: T13
    title: Workspace resolution and location probes (POSIX, Windows, fake)
    files:
      - "packages/eng-contract/src/eng_contract/store/__init__.py"
      - "packages/eng-contract/src/eng_contract/store/_workspace.py"
      - "packages/eng-contract/src/eng_contract/store/_probe_posix.py"
      - "packages/eng-contract/src/eng_contract/store/_probe_windows.py"
      - "packages/eng-contract/tests/unit/test_workspace.py"
      - "packages/eng-contract/tests/unit/test_windows_probe_rules.py"
      - "packages/eng-contract/tests/windows/test_windows_probe.py"
      - "packages/eng-contract/docs/local-testing.md"
    max_changed_lines: 300
    max_sessions: 3
    tests_first:
      - "packages/eng-contract/tests/unit/test_workspace.py::test_resolution_order"
      - "packages/eng-contract/tests/unit/test_workspace.py::test_never_cwd"
      - "packages/eng-contract/tests/unit/test_workspace.py::test_refuses_non_local"
      - "packages/eng-contract/tests/unit/test_windows_probe_rules.py::test_result_code_mapping"
      - "packages/eng-contract/tests/windows/test_windows_probe.py::test_classifications"
    covers: [AC13, AC14, AC15, AC15a]
    depends_on: [T12]
  - id: T14
    title: Result store, atomic writes, payload split and model state
    files:
      - "packages/eng-contract/src/eng_contract/store/__init__.py"
      - "packages/eng-contract/src/eng_contract/store/_results.py"
      - "packages/eng-contract/src/eng_contract/store/_model_state.py"
      - "packages/eng-contract/src/eng_contract/_fs.py"
      - "packages/eng-contract/tests/unit/test_store.py"
      - "packages/eng-contract/tests/unit/test_model_state.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-contract/tests/unit/test_store.py::test_put_get_round_trip"
      - "packages/eng-contract/tests/unit/test_store.py::test_rename_retries_with_backoff"
      - "packages/eng-contract/tests/unit/test_store.py::test_rename_gives_up"
      - "packages/eng-contract/tests/unit/test_store.py::test_exclusive_create"
      - "packages/eng-contract/tests/unit/test_store.py::test_large_payload_split"
      - "packages/eng-contract/tests/unit/test_store.py::test_hash_verified_on_read"
      - "packages/eng-contract/tests/unit/test_store.py::test_corrupt_record_is_integrity_error"
      - "packages/eng-contract/tests/unit/test_store.py::test_payload_validated_against_kind"
      - "packages/eng-contract/tests/unit/test_store.py::test_payload_stored_normalized"
      - "packages/eng-contract/tests/unit/test_store.py::test_verdict_trace_ref_end_to_end"
      - "packages/eng-contract/tests/unit/test_model_state.py::test_increment_compare_and_set"
    covers: [AC16, AC17, AC18, AC19, AC20, AC21, AC21a, AC22]
    depends_on: [T13]
  - id: T15
    title: MCP mapping helpers
    files:
      - "packages/eng-contract/src/eng_contract/mcp.py"
      - "packages/eng-contract/tests/unit/test_mcp.py"
      - "packages/eng-contract/tests/data/envelopes/**"
    max_changed_lines: 150
    max_sessions: 1
    tests_first:
      - "packages/eng-contract/tests/unit/test_mcp.py::test_round_trip"
      - "packages/eng-contract/tests/unit/test_mcp.py::test_raw_reply"
      - "packages/eng-contract/tests/unit/test_mcp.py::test_output_schema_is_object"
    covers: [AC49, AC49a, AC50]
    depends_on: [T14]
  - id: T16
    title: JSON Schema snapshots, freshness test and 0.1.0 changelog
    files:
      - "packages/eng-contract/src/eng_contract/_schema_export.py"
      - "packages/eng-contract/docs/schema/**"
      - "packages/eng-contract/tests/contract/test_schema_snapshots.py"
      - "packages/eng-contract/CHANGELOG.md"
      - "packages/eng-contract/README.md"
    max_changed_lines: 200
    max_sessions: 2
    tests_first: ["packages/eng-contract/tests/contract/test_schema_snapshots.py::test_fresh"]
    covers: [AC51, AC52, AC53]
    depends_on: [T15]
---

# Implementation plan: eng-contract 0.1

Spec: [0001-eng-contract-0.1.md](../specs/0001-eng-contract-0.1.md) (draft). File paths in the front matter are
relative to the workspace root; `max_changed_lines` counts non-test, non-generated lines
([process/04](../../../../design/process/04-implementation-rules.md) §4).

## 1. Approach

The package is built bottom-up, one module family per pull request, in the order its own imports require: errors
first (every other module raises `ContractError` subclasses with fixed codes, spec §4.2.3), canonical JSON and ids,
then units and quantities (the most dangerous code, so it is built and mutation-tested before
anything uses it), then envelopes and records, references, input validation, verdicts and traces, kinds, the
store, and finally the MCP helpers and the schema snapshots. Every task is test-first: its first commit is `test:` with
the tests named in `tests_first`, failing on `build/v1`
([process/05](../../../../design/process/05-testing-and-verification.md) §9).

The tasks are serialized (each depends on the one before) because every package of the workspace depends on this one
and because most tasks import the previous task's modules; parallel branches would conflict in `__init__.py` files and
in the public API list.

Reuse (spec §2): Pydantic 2 for models and JSON Schema; RFC 8785 Appendix B and the RFC 6901 examples as test data;
the CSI `eUnits` names from the Sasaah CSI engine's mirror of the CSI API (read-only, names only). No code is copied.

## 2. Tasks

**T1 Skeleton.** Creates the package as a uv workspace member: `pyproject.toml` with `name = "eng-contract"`,
`version = "0.1.0.dev0"`, `requires-python = ">=3.14,<3.15"`
([ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §5), `dependencies = ["pydantic>=2.14,<3"]`,
the uv build backend (`build-backend = "uv_build"`; hatchling is the fallback if the backend cannot express the
layout), the tool configuration of [process/11](../../../../design/process/11-repository-standard.md) §3 (ruff strict
rule set, `mypy --strict`, pytest with coverage `fail_under` 95 and branch coverage, the Hypothesis CI profile with
`derandomize=True`, the `windows` marker), and this table:

```toml
[tool.eng-gate]
layer = 1
layer_name = "contract"
risk_floor = "r2"
may_import = []                     # no workspace package (03 §3 rule 2)
public_modules = [
  "eng_contract", "eng_contract.canonical", "eng_contract.ids", "eng_contract.errors",
  "eng_contract.envelope", "eng_contract.records", "eng_contract.store", "eng_contract.refs",
  "eng_contract.units", "eng_contract.quantity", "eng_contract.cited", "eng_contract.params",
  "eng_contract.verdicts", "eng_contract.issues", "eng_contract.trace", "eng_contract.kinds",
  "eng_contract.kinds.model", "eng_contract.kinds.forces", "eng_contract.kinds.basis",
  "eng_contract.kinds.verdicts", "eng_contract.kinds.issues", "eng_contract.mcp",
]

[tool.eng-gate.coverage]
line = 95
branch = 90

[tool.eng-gate.mutation]
min_score = 80
modules = ["eng_contract.units", "eng_contract.quantity", "eng_contract.refs", "eng_contract.canonical"]
```

The key names follow the `eng-dev-gate` spec (B-004); if that spec names them differently, T1 follows B-004 and this
plan is amended in T1's pull request description. T1 also adds `README.md` (purpose, install with `uv sync`, limits),
`CHANGELOG.md` (Unreleased section), `.gate/agents.yml` in the format of the root `.gate/agents.yml` (B-002), with
`AGENTS.md` rendered from [AGENTS.template.md](../../../../design/process/templates/AGENTS.template.md) by
`eng-gate agents render` (filled from the template by hand only if the renderer is not merged yet, and then re-rendered
by the first `agents-drift` run), `CLAUDE.md` containing `@AGENTS.md`, `.gate/risk-map.yml` (`"**": r2`; the unit
factors are also engineering content, [process/01](../../../../design/process/01-lifecycle.md) §3, which T5's review
handles, because the map holds one floor per path), an empty `.gate/ratchet.json`, `docs/local-testing.md`
(the Windows-only steps, filled in T13), `src/eng_contract/py.typed` and `__init__.py` with the version constants.
T1 starts after B-002 (workspace root) is merged.

**T2 Errors** (spec §4.2.3, §4.2.4). Enums, `RETRY_RULES`, `ErrorDetail` validators, `ContractError`, and the
internal `_types` module (`FieldPath`, `Sha256Hex`, `KindName`). `errors` imports only `_types`, and `_types` imports
nothing from the package, so every later task can raise `ContractError` subclasses with their fixed codes (spec
§4.2.3).

**T3 Canonical JSON** (spec §4.3.1). The serializer, the number formatter, `loads` with its integer rule and its
non-finite float rejection, and the hash, with the RFC 8785 sample numbers and strings as data files citing the RFC
section. `CanonicalJsonError` is a T2 `ContractError`.

**T4 Identifiers** (spec §4.3.2). ULID encoding and decoding, `SystemIdSource`, `SeededIdSource`, `FixedClock`,
timestamps, `IdOverflowError`. Serialized after T3 like every task; it uses no T3 code.

**T5 Units** (spec §4.7). The dimension table, quantity kinds and suffixes, the base entries with citations, the
composition of every named unit, `convert` and `convert_exact`, and the CSI unit systems (with `Ton_*` raising
`UnitGapError`, gap G-1). `docs/verification/units.md` records, for every base entry, the document, edition, page and
entry checked (gap G-4); an entry that cannot be confirmed is removed and reported, never kept. This task is treated
as R1 for review: the reviewer checks every base entry against the cited document, and the factor table goes to the
owner queue for confirmation.

**T6 Quantity and Cited** (spec §4.8). No-arithmetic, ordering, equality and hash rules; exact comparison through
`Fraction`.

**T7 Envelopes and records** (spec §4.2.5, §4.4). Provenance, envelopes with the callable discriminator, size limits,
`make_success` and `make_failure`, `ResultRecord`.

**T8 References** (spec §4.6). Pointer parsing and evaluation, `resolve_ref` against a `RecordSource` protocol (tests
use an in-memory source, so the store is not needed yet), kind, unit and staleness rules.

**T9 Input validation** (spec §5). `eng_param`, `ParamModel` definition checks, JSON Schema annotations and the
six-step pipeline with error mapping.

**T10 Verdicts, issues, traces** (spec §4.9), including `Verdict` equality with optional quantities (AC35a).

**T11 Kinds I** (spec §4.10.1, the `model.*` rows of §4.10.2). Registry, kind names, common sub-models and the eight
`model.*` kinds with one valid and several invalid fixtures each.

**T12 Kinds II** (the remaining rows of §4.10.2). `forces.*`, `basis.*` with `DesignBasis.missing`, `verdicts.set/1`,
`issues.model_check/1`, with the local trace-reference rule of `verdicts.set/1` (spec §4.6.3).

**T13 Workspace** (spec §4.5.1, §4.5.2). Resolution, `FakeLocationProbe`, the POSIX probe, and the Windows probe with
`ctypes` behind the `WinApi` port, whose rule tests (AC15a) run on every OS; the real-API tests carry the `windows`
marker and run in the Windows CI job. `docs/local-testing.md` lists what the owner checks on a real machine: a
workspace on a OneDrive folder (including a Files On-Demand sync root) and on a mapped network drive is refused.

**T14 Store** (spec §4.5.3 to §4.5.5). The file-system port and its fake, the atomic write protocol, retries, payload
split, payload normalization (spec §4.4), hash verification with `canonical.loads` and the wrapping of read errors
as `StoreIntegrityError`, `ModelStateStore`, and the end-to-end trace-reference test (AC21a).

**T15 MCP mapping** (spec §4.11), with `output_schema()` as an object schema (AC49a).

**T16 Schema snapshots** (spec §4.12). The exporter, the generated `docs/schema/` files, the freshness test, the
0.1.0 changelog entry and the version bump to `0.1.0`. AC52 is proven by this task's CI run (coverage and the
mutation score over the whole package); AC53 by the gate's import check once `eng-dev-gate` is in CI.

## 3. Dependencies

- Runtime: `pydantic` only (spec §2; [ADR-0004](../../../../design/docs/adr/0004-shared-tool-contract.md)). No
  package-local ADR is needed; `packages/eng-contract/docs/adr/` is created only if a later task needs another runtime
  dependency, and that task then stops for the owner.
- Development (one-line justifications in T1's pull request): `pytest` (tests), `pytest-cov` (coverage thresholds),
  `hypothesis` (property tests), `jsonschema` (AC49a validates `output_schema()`; test only), `mypy` and `ruff`
  (process/11 §3), and the mutation tool chosen by `eng-dev-gate`
  (B-004). If the workspace root declares them as shared development dependencies (B-002), T1 uses those.
- Workspace: B-002 (root `pyproject.toml`, `.gate/agents.yml` format) before T1; B-004 (`[tool.eng-gate]` key names,
  `agents render`) before T1 if available, otherwise as described in T1.

## 4. Verification

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` exists; until then `uv run ruff format --check`,
  `uv run ruff check`, `uv run mypy --strict src tests`, `uv run pytest` with coverage, from `packages/eng-contract/`.
  The pull request links its CI run; local output is not evidence (process/05 §8).
- Windows: T13's `windows` tests run in the Windows CI job with the real probe; the owner's checks on a OneDrive folder
  and a network drive are listed in `docs/local-testing.md` (needs local test).
- No host program is involved; no live acceptance is needed for this package.
- Review: each pull request is reviewed by a subagent that did not write it, with the correctness, Python, type-design,
  silent-failure and test lenses; T5 and T8 additionally with the R1-style source check; T13 and T14 with the security
  lens (file paths from input, process/01 §3). The second-family review and the owner's R2 approval are
  `awaiting owner` in bootstrap mode (ADR-0028 §4).

## 5. Rollback

Every task is one squash-merged pull request on `build/v1` with no consumer until T16; reverting a task's commit
removes it cleanly (later tasks depend on earlier ones, so a revert also reverts its dependants). After 0.1.0 is used by
`eng-harness`, a defect is fixed forward in a patch release with a regression test; a wrong unit factor or reference
rule is handled as a wrong engineering result
([process/10](../../../../design/process/10-engineering-verification.md) §7).
