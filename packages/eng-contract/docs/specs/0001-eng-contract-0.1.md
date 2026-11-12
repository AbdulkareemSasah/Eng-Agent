---
id: spec-0001-eng-contract-0-1
issue: "B-003"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: r2
---

# Spec 0001: eng-contract 0.1

Package: `eng-contract` (import package `eng_contract`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-03

This spec implements [04-tool-contract](../../../../design/docs/architecture/04-tool-contract.md) (cited below as
"04 §n") as the contract version `eng-contract/1`, package version 0.1.0. It does not repeat 04's prose: where a rule
is stated in 04, this spec names the section and adds only what an implementer and a reviewer need to decide a case.
Where this spec adds a detail that 04 leaves open, the detail is marked **[added]** and listed in §11 for the owner.

## 1. Problem

Every Python package of the workspace (the harness and its server adapters, the code packs) must agree on envelopes,
references, units, errors, verdicts and kinds ([ADR-0004](../../../../design/docs/adr/0004-shared-tool-contract.md)).
Without one implementation each package re-implements them, and drift in units or references produces wrong numbers
that look right (16 §1). Today nothing exists: phase 1 (`eng-harness`) cannot start until this package exists, and
every later change to it needs a new version, so the first version must be right.

Consumers: `eng-harness` (engine, server adapters, calcs, design basis, journal), `structural-codes` (checks,
verdicts, traces, `Cited`). The Sasaah servers do not use it
([ADR-0024](../../../../design/docs/adr/0024-harness-on-existing-sasaah-servers.md)); the harness adapters wrap their
replies with §4.11.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| Pydantic 2 | Models, validation, JSON Schema output; already the one allowed runtime dependency (02 §1, ADR-0004) | Used |
| `pint` | Rejected for the contract by [ADR-0006](../../../../design/docs/adr/0006-canonical-units.md) (heavy, float factors) | Not used |
| `python-ulid`, `ulid-py` | Small, but a runtime dependency (needs an ADR) for about 60 lines of code; generation must be injectable anyway | Implemented here (§4.3) |
| `uuid.uuid7()` (Python 3.14 standard library) | Time-ordered, but 04 §2 mandates the ULID text form | Not used |
| `rfc8785` (RFC 8785 implementation) | Correct, Apache-2.0, but a runtime dependency | Not used; its published test vectors and RFC 8785 Appendix B are used as test data, with citations |
| `jsonpointer` | RFC 6901 is about 40 lines to implement, and we need exact error mapping | Implemented here (§4.6) |
| MCP Python SDK types | Version-dependent; the mapping must not depend on an SDK version (task 9) | Plain dicts (§4.11) |

No runtime dependency other than `pydantic` is added. No package-local ADR is needed for 0.1.

## 3. Acceptance criteria

Each criterion names its planned test (§9 lists the layer). Test paths are relative to `packages/eng-contract/`.

### 3.1 Canonical JSON and identifiers

- AC1. Given the RFC 8785 Appendix B number samples, when each is serialized by `canonical_json`, then the output
  equals the published string. Test: `tests/unit/test_canonical.py::test_rfc8785_number_samples`.
- AC2. Given an object with keys `"b"`, `"a"`, `"é"`, `"\U0001F600"` and `"דּ"`, when serialized, then keys
  are ordered by UTF-16 code units, there is no whitespace, non-ASCII is written as UTF-8, and only `"`, `\` and
  U+0000 to U+001F are escaped. Test: `test_canonical.py::test_key_order_and_escaping`.
- AC3. Given NaN, an infinity, a Python `int` outside ±(2^53 − 1) (including 2^53 and 10^16), a lone surrogate, a
  non-string key, or a value that is not a JSON type (for example `Decimal`, `bytes`, `datetime`), when serialized,
  then `CanonicalJsonError` is raised. Given the floats `2.0**53`, `1e16`, `1e20` and `1e21`, then they serialize as
  `9007199254740992`, `10000000000000000`, `100000000000000000000` and `1e+21`, and `canonical.loads` reads each back
  as that `float`. Given text with `NaN`, a duplicate key, a number literal that overflows float64 (for example
  `1e400` or `-1e400`), or an integer literal outside ±(2^53 − 1) that does not convert exactly to a finite float64
  (for example `9007199254740993`), when parsed with `canonical.loads`, then `CanonicalJsonError`. Test:
  `test_canonical.py::test_rejects_non_json_values`, `test_canonical.py::test_large_integral_floats`.
- AC4. Given any JSON value built by Hypothesis (floats drawn to include integral values at and above 2^53), when
  serialized, parsed with `canonical.loads` and serialized again, then the bytes are identical, and `payload_sha256`
  is the SHA-256 of those bytes in lowercase hex. Test:
  `tests/property/test_canonical_props.py::test_round_trip_is_stable`.
- AC5. Given a `SeededIdSource(seed=b"t", clock=FixedClock(...))`, when it generates three ids, then they equal the
  recorded fixture values, each matches `^res_[0-7][0-9A-HJKMNP-TV-Z]{25}$`, and they sort in generation order. Test:
  `tests/unit/test_ids.py::test_seeded_ids_are_deterministic`.
- AC6. Given `SystemIdSource` with an injected clock that returns the same millisecond twice, when two ids are
  generated, then the second is greater than the first (monotonic within a millisecond); when the 80-bit random part
  would overflow, then `IdOverflowError` is raised. Test: `test_ids.py::test_monotonic_within_millisecond`,
  `test_ids.py::test_overflow_raises`.

### 3.2 Envelopes, errors, warnings, records

- AC7. Given a success envelope whose `summary` serializes to more than 4096 bytes, or whose `data` serializes to more
  than 16384 bytes, when validated, then validation fails. Test: `tests/unit/test_envelope.py::test_size_limits`.
- AC8. Given a payload of at most 16384 canonical bytes, when `make_success` builds an envelope from its record, then
  `data` equals the payload; given a larger payload, then `data` is null. Test:
  `test_envelope.py::test_make_success_inlines_small_payloads`.
- AC9. Given JSON with `"ok": false` and an `error`, when parsed as `Envelope`, then a `FailureEnvelope` results; with
  `"ok": true`, a `SuccessEnvelope`; with `ok` missing or not a boolean, validation fails. Test:
  `test_envelope.py::test_discriminated_by_ok`.
- AC9a. Given an input `{"ref": ...}` whose pointer holds a newline, which `RefString` accepts, when parsed as
  `RefInput`, then it validates exactly as `RefString` does: `RefInput.ref` is a `RefString` (§4.6.1), not a local
  pattern (amendment B-391, B-017 review). Test: `test_envelope.py::test_ref_input_uses_ref_string`.
- AC10. For every error code of 04 §8.1, given an `ErrorDetail` with that code, when `retryable` contradicts the rule
  of §4.2.3, then validation fails; `PRECONDITION_FAILED` without `precondition`, `INTERNAL` without `incident_id`,
  and `precondition` on any other code fail too. Test: `tests/unit/test_errors.py::test_retry_rules_per_code`
  (parametrized over all 22 codes), `test_errors.py::test_code_specific_fields`.
- AC11. Given a success envelope with the warning `PARTIAL_DATA` and `complete: true`, or `complete: false` without
  `PARTIAL_DATA`, when validated, then validation fails. Test: `test_envelope.py::test_partial_data_consistency`.
- AC12. Given a result record whose `payload` and `payload_file` are both set or both absent, when validated, then
  validation fails. Test: `tests/unit/test_records.py::test_payload_location_exclusive`.

### 3.3 Result store

- AC13. Given `ENG_WORKSPACE` set to an absolute local path, when the workspace is resolved, then that path is used;
  given it unset and `LOCALAPPDATA` set, then `<LOCALAPPDATA>\eng\workspaces\default`; given neither, or a relative
  `ENG_WORKSPACE`, then `PRECONDITION_FAILED` with `precondition: local_workspace`; the process working directory is
  never used. Test: `tests/unit/test_workspace.py::test_resolution_order`, `test_workspace.py::test_never_cwd`.
- AC14. Given a location probe (fake) that classifies the workspace as `network`, `cloud_synced` or `unknown`, when
  the store opens, then `PRECONDITION_FAILED` (`local_workspace`) with a hint naming the classification. Test:
  `test_workspace.py::test_refuses_non_local`.
- AC15. Given the Windows probe on a Windows runner, when it classifies a local temporary folder (which exercises the
  real "not under a sync root" result of the Cloud Files API), a UNC path and a folder under the `OneDrive`
  environment folder, then it returns `local`, `network` and `cloud_synced`. Test (marked `windows`, runs in the
  Windows CI job): `tests/windows/test_windows_probe.py::test_classifications`.
- AC15a. Given the Windows probe rules over a fake Windows API (any OS), when the sync-root query returns success or
  `ERROR_MORE_DATA`, then `cloud_synced`; when it returns `ERROR_CLOUD_FILE_NOT_UNDER_SYNC_ROOT`, or `cldapi.dll` or
  its entry point is missing, then the remaining rules decide (`local` for a fixed drive without markers); when it
  returns any other code, or `GetDriveTypeW` or `GetFileAttributesW` fails, then `unknown`. Test:
  `tests/unit/test_windows_probe_rules.py::test_result_code_mapping`.
- AC16. Given a payload, when `ResultStore.put` returns, then
  `<workspace>/.eng/results/<yyyy>/<mm>/<dd>/<result_id>.json` exists (date from the ULID, UTC), its bytes are the
  canonical JSON of the record, no temporary file remains, and `get` returns an equal record. Test:
  `tests/unit/test_store.py::test_put_get_round_trip`.
- AC17. Given a file system fake whose rename raises `PermissionError` twice and then succeeds, when `put` runs, then
  it succeeds after the delays of §4.5.4 (from an injected sleeper); given four consecutive failures, then
  `StoreWriteError` and no record exists. Test: `test_store.py::test_rename_retries_with_backoff`,
  `test_store.py::test_rename_gives_up`.
- AC18. Given a final path that already exists, when `put` tries to commit there, then the existing file is unchanged
  and `StoreWriteError` (mapped to `INTERNAL`) is raised. Test: `test_store.py::test_exclusive_create`.
- AC19. Given a payload whose canonical form exceeds 8 388 608 bytes, when stored, then the record has
  `payload_file` and the gzip file holds the canonical payload; `get` returns the verified record with `payload_file`
  set and `payload` null, and `payload()` returns the loaded payload, whose hash is the recorded one (§4.5.3;
  amendment B-358). Test: `test_store.py::test_large_payload_split`.
- AC20. Given a stored record whose payload (inline or gzip) was altered on disk, or a record file rewritten on disk
  to hold a duplicate key, a `NaN` literal, or JSON that does not validate as a `ResultRecord`, when read, then
  `StoreIntegrityError` (mapped to `INTERNAL`, never `INVALID_ARGUMENT`) is raised. Test:
  `test_store.py::test_hash_verified_on_read`, `test_store.py::test_corrupt_record_is_integrity_error`.
- AC21. Given a payload that does not validate against its kind's schema, or a kind that is not in the store's kind
  registry, when `put` runs, then `INVALID_ARGUMENT` and nothing is written. Given a valid payload that omits fields
  with defaults (for example a `verdicts.set/1` verdict without `ratio_limit`), when `put` runs, then the stored and
  returned payload has every default written out (the normalized form of §4.4), and the same payload with the defaults
  written explicitly gives the same `payload_sha256`. Test: `test_store.py::test_payload_validated_against_kind`,
  `test_store.py::test_payload_stored_normalized`.
- AC21a. Given a `verdicts.set/1` payload whose code-pack verdict has `trace_ref: "#/traces/0"`, when it is stored with
  `put`, the verdict's reference is rebased onto the returned `result_id` with `rebase_local_ref`, and the result is
  resolved through `resolve_ref`, then the value equals the stored trace and the hash of the payload does not depend
  on the `result_id`. Test: `test_store.py::test_verdict_trace_ref_end_to_end`.
- AC22. Given a model state at revision 3, when `ModelStateStore.increment(model_id, expected_revision=3)` runs, then
  the state is revision 4; with `expected_revision=2`, then `CONFLICT` and the state is unchanged. Test:
  `tests/unit/test_model_state.py::test_increment_compare_and_set`.

### 3.4 References

- AC23. Given the strings `res_<id>`, `res_<id>#`, `res_<id>#/a~1b/0` and `res_<id>#/m~0n`, when parsed, then the
  pointer tokens are `[]`, `[]`, `["a/b", "0"]` and `["m~n"]`. Given `res_bad`, then `INVALID_ARGUMENT`; given
  `res_<id>#a`, `res_<id>#/x~2`, then `REF_POINTER_INVALID`. Test: `tests/unit/test_refs.py::test_parse`.
- AC24. Given a pointer to a missing key, an array index out of range, an index with a leading zero, `-`, or a token
  applied to a scalar, when resolved, then `REF_POINTER_INVALID`. Test: `test_refs.py::test_pointer_failures`.
- AC25. Given a reference to a result id not in the store, when resolved, then `REF_NOT_FOUND`. Test:
  `test_refs.py::test_not_found`.
- AC26. Given a parameter that accepts `model.sections/1` and a whole-payload reference to a `forces.member_end/1`
  result, when resolved, then `REF_KIND_MISMATCH`. Test: `test_refs.py::test_kind_mismatch`.
- AC27. Given a parameter `b_mm` and a pointer `.../h_mm` (bare number), or a quantity object with unit `kPa` for a
  parameter in `MPa`, or a bare number under no unit-suffixed key, when resolved, then `REF_UNIT_MISMATCH`. Test:
  `test_refs.py::test_unit_mismatch`.
- AC28. Given a result produced from model `mdl_A` at revision 4 while `mdl_A` is at revision 5, when resolved for a
  parameter without `stale_ok`, then `REF_STALE`; with `stale_ok`, then the value; for a result with no host (basis,
  file-based), then the value. Test: `test_refs.py::test_staleness_rule`.
- AC29. Given generated JSON payloads and generated pointers that exist in them (Hypothesis), when resolved, then the
  value equals the value reached by direct indexing; escaping then parsing any token returns the original token.
  Test: `tests/property/test_refs_props.py::test_pointer_round_trip`.

### 3.5 Units and quantities

- AC30. Given every named unit, when its factor is read, then it equals the exact rational value derived from the
  cited definitions of §4.7.3 (fixture table with sources). Test: `tests/unit/test_units.py::test_factors_exact`.
- AC31. Given 1 in, 1 ft, 1 lbf, 1 kip, 1 kgf, 1 psi, 1 kip·ft, when converted to canonical units, then the results
  are 25.4 mm, 304.8 mm, 0.0044482216152605 kN, 4.4482216152605 kN, 0.00980665 kN, 0.006894757293168362 MPa and
  1.3558179483314003 kN·m, each the correctly rounded float64 of the exact value (the test also recomputes each one
  with `Fraction` from the cited definitions). Test:
  `test_units.py::test_known_conversions`.
- AC32. Given a conversion between different dimensions, or an unknown unit symbol, when called, then `UnitError`
  (mapped to `UNIT_MISMATCH`). Test: `test_units.py::test_dimension_mismatch`.
- AC33. Given random finite floats and random pairs of units of one dimension (Hypothesis), when converted a → b → a
  with `convert_exact`, then the original value is returned exactly; with `convert`, then the result is the correctly
  rounded value of the exact conversion. Test: `tests/property/test_units_props.py::test_round_trip_exact`,
  `test_units_props.py::test_single_rounding`.
- AC34. Given `Quantity(450, "mm")`, when any arithmetic operator, `float()`, `int()`, `round()`, `abs()` or unary
  minus is applied, then `TypeError`. Test: `tests/unit/test_quantity.py::test_no_arithmetic`.
- AC35. Given `Quantity(1, "in")` and `Quantity(25.4, "mm")`, when compared, then they are equal, have equal hashes,
  and `<` is false both ways; given `Quantity(1, "kN")` and `Quantity(1, "mm")`, then `<`, `<=`, `>`, `>=` raise
  `TypeError` and `==` is `False`; a `Quantity` ordered against a plain number or `None` raises `TypeError`, and `==`
  against them is `False`; `bool(Quantity(...))` raises `TypeError`. Given `Quantity(180, "deg")` and
  `Quantity(math.pi, "rad")`, when they compare equal, then their hashes are equal. Test:
  `test_quantity.py::test_comparisons`, `test_quantity.py::test_hash_consistent_with_eq`.
- AC35a. Given two `Verdict`s that differ only in that one has `demand: null` and the other a `Quantity`, or whose
  demands have different dimensions, when compared with `==`, then the result is `False` and nothing is raised; two
  verdicts that differ only in holding `1 in` and `25.4 mm` compare equal. Test:
  `tests/unit/test_verdicts.py::test_model_equality`.
- AC36. Given random quantity pairs of one dimension (Hypothesis), when compared, then the ordering is total and
  consistent with exact conversion of each value's shortest round-trip decimal to the canonical unit. Test:
  `tests/property/test_quantity_props.py::test_order_consistent`.
- AC37. Given the field name `w_kN_m`, `Sx_mm3`, `drift_ratio` and `label`, when the suffix is looked up, then the
  quantity kinds are line load, section modulus, dimensionless and none. Test: `test_units.py::test_suffix_lookup`.
- AC38. Given each of the 16 CSI unit-system names, when looked up, then its force, length and temperature units are
  returned; for `Ton_*`, the lookup raises `UnitGapError` until gap G-1 (§11) is resolved. Test:
  `test_units.py::test_csi_unit_systems`.

### 3.6 Input validation

- AC39. Given an input model with a field `b_mm` declared with unit `MPa`, when the class is defined, then
  `ContractDefinitionError`. Given bounds without `bounds_source`, then the same. Test:
  `tests/unit/test_params.py::test_definition_checks`.
- AC40. Given the JSON Schema of an input model, when generated, then each parameter shows `minimum`, `maximum`,
  `enum` and `x-eng` with `unit`, `ref_capable`, `engineering_quantity`, `stale_ok`, `bounds_source`, and a
  ref-capable parameter is `anyOf` the literal schema and the reference schema. Test:
  `test_params.py::test_json_schema_metadata`.
- AC41. Given an input with an unknown field and an out-of-range value, when validated, then `INVALID_ARGUMENT`
  (shape comes first); given only a reference that fails and an out-of-range literal elsewhere, then the `REF_*` code;
  given only an out-of-range value, then `OUT_OF_RANGE` with `field`, `expected {min, max, unit}` and `received`;
  given only a failing cross-field validator, then `INVALID_ARGUMENT`. Test: `test_params.py::test_validation_order`.
- AC42. Given policy `require_refs=True` and a literal for an `engineering_quantity` parameter, when validated, then
  `INVALID_ARGUMENT` with a hint naming the parameter; the same literal without the policy is accepted and recorded as
  `literal` in provenance inputs. Test: `test_params.py::test_require_refs_policy`.
- AC43. Given a reference whose resolved value is out of bounds, when validated, then `OUT_OF_RANGE` (a reference
  does not bypass bounds, 04 §3.2). Test: `test_params.py::test_refs_do_not_bypass_bounds`.

### 3.7 Verdicts, issues, traces, kinds

- AC44. Given a verdict with `status: PASS` and `ratio > ratio_limit`, or `FAIL` and `ratio <= ratio_limit`, or
  `demand` and `capacity` of different dimensions, or `source: code_pack` without `trace_ref`, when validated, then
  validation fails; given a `verdicts.set/1` payload with a full `res_…` trace reference, or a local reference whose
  index is not less than the number of traces, then validation fails. Test:
  `tests/unit/test_verdicts.py::test_consistency_rules`, `tests/contract/test_kinds.py::test_verdict_set_trace_refs`.
- AC45. Given a `check_model` summary with `errors: 0` and `clean: false`, or an `issues.model_check/1` payload whose
  counts differ from its issues, when validated, then validation fails. Test: `tests/unit/test_issues.py::test_summary`.
- AC46. Given each neutral kind of §4.10, when a valid fixture and each invalid fixture of that kind (one per rule) are
  validated, then the valid one passes and each invalid one fails on the named rule. Test:
  `tests/contract/test_kinds.py::test_fixtures` (fixtures in `tests/data/kinds/`).
- AC47. Given a kind name, when parsed, then `family.name/N` is accepted, a neutral family name without a version or
  with version 0 is rejected, and a registry lookup of an unregistered kind raises `KindNotRegistered`. Test:
  `test_kinds.py::test_kind_names_and_registry`.
- AC48. Given a design basis field without `source`, with a malformed source, or a required-field check over a basis
  with an unconfirmed field, then validation fails or the unmet field paths are listed. Test:
  `test_kinds.py::test_basis_sources`.
- AC48a. Given the basis paths `compare.stress_MPa`, `bounds.w_kN_m` and `limits.drift_ratio` with the canonical unit
  of their suffix, or `compare._MPa` (empty part before the suffix) with unit `MPa`, when a design basis is validated,
  then it is accepted; given `compare.stress_MPa` with unit `kPa`, or a capital letter outside a §4.7.2 suffix at the
  end of the last segment (`Compare.stress_MPa`, `compare.stress_MPa.max`, `compare.stress_Mpa`), then validation fails (amendment B-463). Test:
  `test_kinds.py::test_basis_path_unit_suffixes`.

### 3.8 MCP mapping and schemas

- AC49. Given a success and a failure envelope, when mapped to a tool result, then `structuredContent` equals the
  envelope's JSON form, `isError` is `not ok`, and `content` is one text block holding the canonical JSON; mapping back
  returns an equal envelope. Test: `tests/unit/test_mcp.py::test_round_trip`.
- AC49a. Given `output_schema()`, when inspected, then its top level has `"type": "object"`, and the success and
  failure envelope examples of 04 §1 (their abbreviated ids such as `mdl_01JB6...` replaced by full 26-character
  ids, recorded in `tests/data/envelopes/`) validate against it with a Draft 2020-12 validator (test-only dependency
  `jsonschema`); an object with `"ok": "yes"` does not. Test: `test_mcp.py::test_output_schema_is_object`.
- AC50. Given a tool result without `structuredContent` (a server that does not speak the contract), when
  `extract_raw_reply` runs, then it returns `is_error`, the text blocks and any JSON parsed from them, and
  `tool_result_to_envelope` raises `NotAnEnvelope`. Test: `test_mcp.py::test_raw_reply`.
- AC51. Given the committed files in `docs/schema/`, when the schemas are regenerated in a temporary folder, then the
  files are byte-identical and no file is missing or extra. Test: `tests/contract/test_schema_snapshots.py::test_fresh`.

### 3.9 Package-level

- AC52. Given the package, when the gate runs, then line coverage is at least 95%, branch coverage at least 90%, and
  the mutation score of `eng_contract.units`, `eng_contract.quantity`, `eng_contract.refs` and
  `eng_contract.canonical` is at least 80% ([process/05](../../../../design/process/05-testing-and-verification.md)
  §2). Evidence: the CI run of the `gate` job.
- AC53. Given another workspace package that imports `eng_contract._anything`, when the gate's import check runs, then
  it fails (03 §3 rule 2). Evidence: a fixture in `eng-dev-gate`'s own tests; this package only declares its public
  modules (§4.1).

## 4. Design

### 4.1 Module layout and public API

`src/eng_contract/` with these **public** modules. Every other module starts with an underscore and is internal;
nothing outside this package imports it (03 §3 rule 2). The public list is also declared in
`pyproject.toml` `[tool.eng-gate] public_modules` so the gate can enforce it.

| Module | Public names |
|---|---|
| `eng_contract` | `CONTRACT_VERSION = "eng-contract/1"`, `UNITS_VERSION = "canonical/1"`, `__version__` |
| `eng_contract.canonical` | `canonical_json(value) -> bytes`, `loads(data) -> JsonValue`, `payload_sha256(value) -> str`, `CanonicalJsonError` |
| `eng_contract.ids` | `ResultId`, `ModelId` (annotated `str` types), `IdSource` (protocol), `SystemIdSource`, `SeededIdSource`, `Clock` (protocol), `SystemClock`, `FixedClock`, `new_result_id`, `new_model_id`, `ulid_timestamp_ms`, `IdOverflowError`, `Timestamp` |
| `eng_contract.errors` | `ErrorCode`, `WarningCode`, `Precondition`, `ErrorDetail`, `ContractWarning`, `ContractError`, `RETRY_RULES` |
| `eng_contract.envelope` | `Provenance`, `HostInfo`, `FileSource`, `RefInput`, `LiteralInput`, `SuccessEnvelope`, `FailureEnvelope`, `Envelope`, `make_success`, `make_failure`, `SUMMARY_LIMIT_BYTES`, `INLINE_DATA_LIMIT_BYTES` |
| `eng_contract.records` | `ResultRecord`, `PAYLOAD_SPLIT_BYTES` |
| `eng_contract.store` | `Workspace`, `resolve_workspace`, `LocationClass`, `LocationProbe` (protocol), `FakeLocationProbe`, `default_location_probe`, `ResultStore`, `ModelStateStore`, `ModelState`, `StoreWriteError`, `StoreIntegrityError` |
| `eng_contract.refs` | `Ref`, `RefString`, `LocalTraceRef`, `rebase_local_ref`, `parse_ref`, `JsonPointer`, `RefRule`, `RecordSource` (protocol), `resolve_ref`, `ResolvedRef` |
| `eng_contract.units` | `Dimension`, `Unit`, `QuantityKind`, `UNITS`, `QUANTITY_KINDS`, `unit`, `convert`, `convert_exact`, `kind_for_field`, `CsiUnitSystem`, `csi_unit_system`, `UnitError`, `UnitGapError` |
| `eng_contract.quantity` | `Quantity`, `LabeledQuantity` |
| `eng_contract.cited` | `Cited` |
| `eng_contract.params` | `eng_param`, `ParamSpec`, `ParamModel`, `InputPolicy`, `validate_input`, `ValidatedInput`, `ContractDefinitionError` |
| `eng_contract.verdicts` | `Verdict`, `VerdictSource`, `VerdictStatus`, `Subject`, `SubjectKind` |
| `eng_contract.issues` | `ModelIssue`, `Severity`, `CheckModelSummary` |
| `eng_contract.trace` | `Trace`, `TraceInput`, `TraceConstant`, `TraceStep` |
| `eng_contract.kinds` | `KindName`, `KindRegistry`, `NEUTRAL_KINDS`, `KindNotRegistered`, and the payload models in the submodules `kinds.model`, `kinds.forces`, `kinds.basis`, `kinds.verdicts`, `kinds.issues` (all public) |
| `eng_contract.mcp` | `envelope_to_tool_result`, `tool_result_to_envelope`, `RawToolReply`, `extract_raw_reply`, `output_schema`, `NotAnEnvelope` |

Internal modules (planned): `_ulid`, `_jcs`, `_fs` (atomic file operations, the file-system port and its fake),
`_probe_windows`, `_probe_posix`, `_pointer`, `_schema_export`. Tests may import internals; other packages may not.

General model rules: Pydantic v2 `BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True,
allow_inf_nan=False, strict=False)` unless stated; all floats are float64 and finite; `str` fields have a stated
maximum length; every model's JSON Schema is part of the snapshot (§4.12). `JsonValue` means Pydantic's `JsonValue`.
No module holds global mutable state; registries are immutable mappings built at import.

### 4.2 Envelope, provenance, errors, warnings (04 §1, §8)

#### 4.2.1 Shared types

| Type | Definition |
|---|---|
| `ResultId` | `str`, pattern `^res_[0-7][0-9A-HJKMNP-TV-Z]{25}$` |
| `ModelId` | `str`, pattern `^mdl_[0-7][0-9A-HJKMNP-TV-Z]{25}$` |
| `Timestamp` | `str`, RFC 3339 UTC with exactly three fraction digits and `Z`: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$`, and a valid date |
| `KindName` | `str`, pattern `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+/[1-9][0-9]{0,3}$` (§4.10.1) |
| `FieldPath` | `str` naming an input field: `name ( "." name | "[" index "]" )*`, `name` = `[A-Za-z_][A-Za-z0-9_]*`, `index` = `0` or `[1-9][0-9]*`; max 512 |
| `Sha256Hex` | `str`, pattern `^[0-9a-f]{64}$` |

Homes: `ResultId`, `ModelId` and `Timestamp` in `ids`; `FieldPath`, `Sha256Hex` and `KindName` in the internal
`_types` module (built with `errors`, plan T2, because envelopes need `KindName` before the kinds task); `kinds`
re-exports `KindName` as its public name.

#### 4.2.2 Provenance

| Field | Type | Rule |
|---|---|---|
| `tool` | `str`, max 200 | `<package>/<tool>` matching `^[a-z0-9][a-z0-9-]*/[a-z0-9_.-]+$`, or one of the producer words `engineer`, `template`, `harness` (04 §2) |
| `tool_version` | `str`, max 64 | Version of the tool's package or server build, as reported |
| `host` | `HostInfo` or null | Present for results read from a host model |
| `files` | list of `FileSource`, default `[]` | **[added]** Input files a file-based result was read from (04 §3.4: file results carry the file's content hash) |
| `inputs` | `dict[FieldPath, RefInput | LiteralInput]` | Every input: `{"ref": RefString}` or `{"literal": JsonValue}`; never a re-typed copy of a referenced value (04 §3.2) |
| `started_at` | `Timestamp` | |
| `duration_ms` | `int`, ≥ 0 | |

`HostInfo`: `program` (`str`, max 64, for example `ETABS`), `version` (`str`, max 64), `model_id` (`ModelId`),
`model_revision` (`int`, ≥ 0). `FileSource`: `name` (`str`, max 255, the base name only: no directory separators, so
records carry no personal paths), `sha256` (`Sha256Hex`), `size_bytes` (`int`, ≥ 0).

#### 4.2.3 Error codes and the retry rule

`ErrorCode` is a `StrEnum` with exactly the 22 codes of 04 §8.1. `RETRY_RULES` maps each code to a rule; the
`ErrorDetail` validator enforces it:

| Rule | Codes | `retryable` must be |
|---|---|---|
| `never` | `INVALID_ARGUMENT`, `OUT_OF_RANGE`, `UNIT_MISMATCH`, `REF_NOT_FOUND`, `REF_POINTER_INVALID`, `REF_KIND_MISMATCH`, `REF_UNIT_MISMATCH`, `REF_STALE`, `NOT_FOUND`, `CONFLICT`, `PRECONDITION_FAILED`, `CONFIRMATION_REQUIRED`, `LIMIT_EXCEEDED`, `HOST_LOCKED`, `NOT_SUPPORTED_BY_VERSION`, `INTERNAL` | `false` |
| `always` | `HOST_NOT_CONNECTED`, `HOST_BUSY`, `TIMEOUT_NO_EFFECT` | `true` |
| `after_wedge_clears` | `HOST_WEDGED` | `true` (the caller waits until the earlier call returns; 04 §8.1) |
| `reconcile_first` | `TIMEOUT_UNKNOWN_OUTCOME` | `false`: a plain retry is forbidden; only reconciliation with the same `op_id` (P9, ADR-0007) |
| `depends` | `HOST_ERROR` | either; the producer decides from `host_code` |

`ErrorDetail` fields:

| Field | Type | Rule |
|---|---|---|
| `code` | `ErrorCode` | |
| `message` | `str`, 1 to 2000 | Plain text; never contains secrets or full payloads (process/04 §5) |
| `field` | `FieldPath` or null | The failing input field |
| `expected` | `dict[str, JsonValue]` or null | For `OUT_OF_RANGE`: `{min, max, unit}` (either bound may be absent); for `UNIT_MISMATCH`: `{unit}`; for `REF_KIND_MISMATCH`: `{kinds: [...]}` |
| `received` | `JsonValue` or null | The offending value (for references: the resolved value) |
| `hint` | `str`, max 2000, or null | |
| `retryable` | `bool` | Per the table above |
| `precondition` | `Precondition` or null | Required for, and only allowed on, `PRECONDITION_FAILED`. `Precondition` = `model_saved`, `model_open`, `analysis_current`, `units_verified`, `local_workspace` |
| `host_code`, `host_method` | `str`, max 200, or null | Allowed on `HOST_ERROR` and `HOST_BUSY` (`host_code: MODAL_DIALOG`) only |
| `op_id` | `str`, max 200, or null | **[added]** Recommended on `TIMEOUT_UNKNOWN_OUTCOME`, `CONFLICT` |
| `incident_id` | `str`, max 64, or null | Required for, and only allowed on, `INTERNAL` |

`ContractError(Exception)` carries one `ErrorDetail` (`.detail`); its constructor takes the code and fields and fills
`retryable` from `RETRY_RULES` unless the rule is `depends`, where the caller must pass it. Library functions raise
`ContractError` (or a subclass listed in this spec, each with a fixed code); they never return `None` on failure.
Because every module raises these, `errors` is the first module built after the skeleton (plan T2) and imports only
the internal `_types` module of this package (for `FieldPath`); `_types` imports nothing from the package. The
subclasses and their fixed codes:

| Exception | Module | Code |
|---|---|---|
| `CanonicalJsonError` | `canonical` | `INVALID_ARGUMENT` (the value is not in the JSON data model of §4.3.1) |
| `IdOverflowError` | `ids` | `LIMIT_EXCEEDED` (the overflow case of the ULID monotonic rule, ulid/spec; not transient within the same millisecond) |
| `UnitError`, and its subclass `UnitGapError` | `units` | `UNIT_MISMATCH` |
| `StoreWriteError`, `StoreIntegrityError` | `store` | `INTERNAL` (§4.5.3; `incident_id` is passed by the raiser, a fresh ULID from its `IdSource`) |
| `NotAnEnvelope` | `mcp` | `INVALID_ARGUMENT` |
| `KindNotRegistered` | `kinds` | `INVALID_ARGUMENT` |

`ContractDefinitionError` (§5) is not a `ContractError`: it reports a programming error at class definition, never a
tool failure.

#### 4.2.4 Warnings

`WarningCode` is a `StrEnum` with exactly the five codes of 04 §8.2. `ContractWarning`: `code`, `message` (`str`, 1 to
2000), `field` (`FieldPath` or null).

#### 4.2.5 Envelopes

`SuccessEnvelope`: `contract` (`Literal["eng-contract/1"]`), `ok` (`Literal[True]`), `result_id`, `kind`
(`KindName`), `summary` (`dict[str, JsonValue]`), `data` (`JsonValue` or null), `complete` (`bool`), `warnings`
(list of `ContractWarning`, default `[]`), `provenance`.

`FailureEnvelope`: `contract`, `ok` (`Literal[False]`), `error` (`ErrorDetail`).

`Envelope = Annotated[SuccessEnvelope | FailureEnvelope, Discriminator(<function of ok>)]`, with tags `success` and
`failure`; input whose `ok` is missing or not a JSON boolean fails. JSON Schema: `oneOf` the two, each with `ok`
`const`. (A callable discriminator is used so the behavior does not depend on Pydantic's support for boolean literal
discriminators.)

Rules (validators):

1. `len(canonical_json(summary)) <= SUMMARY_LIMIT_BYTES` = 4096 **[added: "KB" read as 1024 bytes]**.
2. `data` is null or `len(canonical_json(data)) <= INLINE_DATA_LIMIT_BYTES` = 16384.
3. `PARTIAL_DATA` is in `warnings` if and only if `complete` is `false` (04 §1, §8.2).
4. A summary that lists "top N" says so: not machine-checkable; reviewed in each producer.

`make_success(record, summary, warnings=())` builds the envelope from a stored record: `result_id`, `kind`,
`complete` and `provenance` come from the record; `data` is the payload when within the limit, else null.
`make_failure(error)` wraps an `ErrorDetail` or `ContractError`.

### 4.3 Canonical JSON and identifiers

#### 4.3.1 Canonical JSON

`canonical_json(value)` implements RFC 8785 (JSON Canonicalization Scheme) over the JSON data model of Python values
(`dict` with `str` keys, `list`, `str`, `int`, `float`, `bool`, `None`; `tuple` is not accepted):

1. Output is UTF-8 bytes without a byte order mark and without any whitespace between tokens.
2. Object members are sorted by their keys compared as sequences of UTF-16 code units (RFC 8785 §3.2.3); duplicate
   keys cannot occur in a `dict`.
3. Strings: `"` and `\` are escaped as `\"` and `\\`; U+0008, U+0009, U+000A, U+000C, U+000D as `\b`, `\t`, `\n`,
   `\f`, `\r`; every other code point below U+0020 as `\u00xx` with lowercase hex; every other code point is written
   as itself in UTF-8 (including U+007F, U+2028, U+2029 and non-BMP characters). No Unicode normalization is applied.
   A string containing a lone surrogate is rejected.
4. Numbers: `bool` is `true`/`false` (checked before `int`). An `int` with absolute value at most 2^53 − 1 is written
   in decimal without leading zeros or a plus sign; a larger `int` is rejected (I-JSON range, RFC 8785 §3.2.2.3). A
   `float` must be finite; `-0.0` is written `0`; otherwise the shortest round-trip digits (Python `repr`) are laid out
   by the ECMAScript `Number.prototype.toString` rules that RFC 8785 §3.2.2.3 requires: with digits `d` (count `k`) and
   decimal exponent `n`, if `k <= n <= 21` write `d` followed by `n − k` zeros; if `0 < n <= 21` put the point after
   `n` digits; if `−6 < n <= 0` write `0.`, `−n` zeros, then `d`; otherwise exponent form `d₁[.d₂…]e±(n − 1)`.
   A float with an integral value is therefore written without a fraction (`1.0` → `1`).
5. Anything else (NaN, infinities, `Decimal`, `Fraction`, `bytes`, `datetime`, non-`str` keys) raises
   `CanonicalJsonError`.

Models are serialized with `model.model_dump(mode="json", by_alias=True, exclude_none=False)` and then
`canonical_json`. `payload_sha256(payload)` is `hashlib.sha256(canonical_json(payload)).hexdigest()`.

`canonical.loads(data: bytes) -> JsonValue` is the only parser used on canonical bytes (the store, references and
tests use it; never `json.loads` directly or Pydantic's `model_validate_json`) **[added]**. It is `json.loads` over
UTF-8 with these hooks: `parse_constant` rejects `NaN`, `Infinity` and `-Infinity`; `object_pairs_hook` rejects a
duplicate key; `parse_int` returns an `int` when the literal is within ±(2^53 − 1), and otherwise a `float` when
`float(n) == n` exactly (rule 4 writes an integral float of 2^53 or more in this form), else raises
`CanonicalJsonError`; `parse_float` converts with `float` (shortest round-trip digits read back exactly) and raises
`CanonicalJsonError` when the result is not finite (a literal such as `1e400` overflows to an infinity). So for every
value `v` that `canonical_json` accepts, `canonical_json(loads(canonical_json(v))) == canonical_json(v)` (AC4), and a
record read from disk re-hashes to the stored `payload_sha256`. A Python `int` of 2^53 or more passed to
`canonical_json` is still rejected (rule 4): producers that hold such a number as an integer have a bug.

#### 4.3.2 ULIDs

The ULID text form (ulid/spec, github.com/ulid/spec): 26 Crockford base32 characters (alphabet
`0123456789ABCDEFGHJKMNPQRSTVWXYZ`), the first 10 encoding a 48-bit Unix time in milliseconds, the last 16 an 80-bit
random part. `res_` or `mdl_` is prefixed.

- `Clock` protocol: `now_ms() -> int` (Unix ms, UTC) and `now() -> Timestamp`. `SystemClock` uses `time.time_ns()`;
  `FixedClock(start_ms, step_ms=0)` returns `start_ms + i * step_ms` on the i-th call.
- `IdSource` protocol: `new_ulid() -> str`. `new_result_id(ids)` and `new_model_id(ids)` add the prefix.
- `SystemIdSource(clock, random_bytes=os.urandom)`: per the ULID monotonic rule, when the clock returns the same
  millisecond as the previous id (or an earlier one), the previous random part plus one is used with the previous
  timestamp; overflow of 80 bits raises `IdOverflowError`. It holds per-instance state only.
- `SeededIdSource(seed: bytes, clock)`: the random part of the i-th id is the first 10 bytes of
  `sha256(seed + i.to_bytes(8, "big"))`, with the same monotonic rule. Used by tests and replay; never by default in
  production code paths.
- `ulid_timestamp_ms(id)` decodes the time; the store derives the date folder from it (UTC).

### 4.4 Result records (04 §2)

`ResultRecord`: `contract`, `result_id`, `kind`, `created_at` (`Timestamp`), `units` (`Literal["canonical/1"]`),
`complete`, `producer` (`Provenance`), `parents` (list of `ResultId`, unique, order kept), `payload_sha256`,
`payload` (`dict[str, JsonValue]` or null), `payload_file` (`str` or null) **[added]**.

Rules: exactly one of `payload` and `payload_file` is set; `payload_file`, when set, equals
`<result_id>.payload.json.gz`; `payload_sha256` is over the canonical payload in both cases. The result store
enforces both rules: it computes `payload_sha256` itself when it writes, raises `CanonicalJsonError` for a payload that
cannot be written as canonical JSON, and checks the hash on every read (`StoreIntegrityError`); `ResultRecord` itself
checks neither, and `make_success` raises `CanonicalJsonError` for such a record (amendment B-391, B-016 review). The record file on disk
is the canonical JSON of the record. The stored payload is the normalized form
`kinds[kind].model_validate(payload).model_dump(mode="json", by_alias=True, exclude_none=False)`: every default is
written out and every lax-coerced value is replaced by its validated value, so the record always validates against its
kind, `payload_sha256` is the same for one semantic payload with or without its defaults, and JSON Pointers (§4.6) to
defaulted fields resolve.

### 4.5 Result store (04 §3.1)

#### 4.5.1 Workspace resolution

`resolve_workspace(env: Mapping[str, str], probe: LocationProbe) -> Workspace`; callers pass `os.environ` at the edge.

1. If `ENG_WORKSPACE` is set and non-empty: it must be an absolute path, else `PRECONDITION_FAILED`
   (`local_workspace`, hint "ENG_WORKSPACE must be absolute"). It is used as given (no symlink resolution beyond
   `os.path.abspath`; no expansion of `~` or variables).
2. Else, if `LOCALAPPDATA` is set and absolute: `<LOCALAPPDATA>\eng\workspaces\default` (built with `pathlib`, so the
   separator is the platform's).
3. Else `PRECONDITION_FAILED` (`local_workspace`, hint "set ENG_WORKSPACE"). The process working directory is never
   used, and no relative path is ever joined to it.
4. The folder is created if missing (`mkdir(parents=True, exist_ok=True)`), then `probe.classify(path)` must return
   `LocationClass.LOCAL`; `NETWORK`, `CLOUD_SYNCED` and `UNKNOWN` give `PRECONDITION_FAILED` (`local_workspace`) with
   the class in `received` and a hint.

`Workspace` (frozen): `root` (`Path`, absolute), `results_dir` (`root/.eng/results`), `models_dir`
(`root/.eng/state/models`), `classification` (`LocationClass`). Layout under the workspace: `.eng/results/<yyyy>/<mm>/<dd>/`, `.eng/state/models/`, and `runs/<run_id>/` (created by
the harness, not by this package).

#### 4.5.2 Location probes

`LocationProbe` protocol: `classify(path: Path) -> LocationClass` (`LOCAL`, `NETWORK`, `CLOUD_SYNCED`, `UNKNOWN`).
`default_location_probe()` returns the Windows probe on Windows and the POSIX probe elsewhere. `FakeLocationProbe`
(public, for consumers' tests) returns a configured class per path prefix.

Windows probe (`_probe_windows`, standard library `ctypes` only). The rules are a pure function over a small
internal `WinApi` port (`drive_type(root)`, `file_attributes(path)`, `sync_root_status(path)`); the real port calls
`ctypes`, and a fake port lets AC15a test every rule on any OS. Rules, in order, first match wins:

1. A UNC path (`\\server\share`, including `\\?\UNC\`) is `NETWORK`.
2. `GetDriveTypeW` of the path's root: `DRIVE_REMOTE` is `NETWORK`; `DRIVE_FIXED` and `DRIVE_RAMDISK` continue;
   anything else (removable, CD-ROM, `DRIVE_UNKNOWN`, `DRIVE_NO_ROOT_DIR`) is `UNKNOWN`.
3. The path is inside a folder named by the environment variable `OneDrive`, `OneDriveCommercial` or
   `OneDriveConsumer`: `CLOUD_SYNCED`.
4. `GetFileAttributesW` of the folder: `INVALID_FILE_ATTRIBUTES` (the call failed) is `UNKNOWN`; any of
   `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`, `FILE_ATTRIBUTE_RECALL_ON_OPEN`, `FILE_ATTRIBUTE_PINNED` or
   `FILE_ATTRIBUTE_UNPINNED` set is `CLOUD_SYNCED`.
5. Sync-root query: `CfGetSyncRootInfoByPath` (Windows Cloud Files API, `cldapi.dll`) for the folder, with
   `CF_SYNC_ROOT_INFO_BASIC` and a buffer of `sizeof(CF_SYNC_ROOT_BASIC_INFO)`. The result maps as follows:
   - `S_OK`, or `HRESULT_FROM_WIN32(ERROR_MORE_DATA)` (the buffer is too small, which still means the folder is under a
     sync root): `CLOUD_SYNCED`.
   - `HRESULT_FROM_WIN32(ERROR_CLOUD_FILE_NOT_UNDER_SYNC_ROOT)`: not a sync root; continue to rule 6.
   - `cldapi.dll` cannot be loaded, or it has no `CfGetSyncRootInfoByPath` export: the Cloud Files API is absent, so
     no Cloud Files sync root can exist on the machine; continue to rule 6 (rules 3 and 4 still caught OneDrive).
   - Any other `HRESULT`: `UNKNOWN`.
6. Otherwise `LOCAL`. No other failure ever yields `LOCAL`.

The numeric values of these constants (drive types, file attributes, `S_OK`, the two Win32 error codes and the
`HRESULT_FROM_WIN32` mapping) are taken from the Windows SDK headers (`winbase.h`, `winnt.h`, `winerror.h`) and the
Microsoft Win32 documentation pages "GetDriveTypeW", "File Attribute Constants", "CfGetSyncRootInfoByPath" and "System
Error Codes", cited next to each definition in code; they are software constants, not engineering values. This spec
deliberately does not state them: the T13 author copies them from the headers, and AC15 on a real Windows runner
proves the "not under a sync root" code (a wrong value classifies the local temporary folder as `UNKNOWN` and fails
the test).

POSIX probe (`_probe_posix`, for development and Linux CI): reads `/proc/self/mountinfo` when present and classifies
mounts of type `nfs`, `nfs4`, `cifs`, `smb3`, `smbfs`, `afs`, `fuse.sshfs`, `9p` as `NETWORK`; otherwise `LOCAL`; if
the file cannot be read, `LOCAL` (POSIX is used for development and CI only; the platform is tested on the owner's
Windows machine, ADR-0028).

#### 4.5.3 ResultStore API

`ResultStore(workspace, kinds: KindRegistry, ids: IdSource, clock: Clock, fs: FileSystem = RealFileSystem(),
sleep: Callable[[float], None] = time.sleep)`.

| Method | Behavior |
|---|---|
| `put(kind, payload, producer, parents=(), complete=True) -> ResultRecord` | Validates `payload` against `kinds[kind]` (else `INVALID_ARGUMENT`; unregistered kind: `INVALID_ARGUMENT`); replaces it with the normalized form of §4.4 (`kinds[kind].model_validate(payload).model_dump(mode="json", by_alias=True, exclude_none=False)`), which is what is hashed, stored and returned; checks every parent exists (else `REF_NOT_FOUND`); assigns `result_id` and `created_at`; computes the hash; writes per §4.5.4 |
| `get(result_id) -> ResultRecord` | Reads the bytes, parses them with `canonical.loads` (§4.3.1), validates the record model, loads the gzip payload if split (also with `canonical.loads`), verifies `payload_sha256` by re-serializing the parsed payload (else `StoreIntegrityError`); a `CanonicalJsonError`, a gzip error or a record validation error raised on stored bytes is wrapped as `StoreIntegrityError` (`INTERNAL`), never surfaced as `INVALID_ARGUMENT`; `REF_NOT_FOUND` if missing |
| `exists(result_id) -> bool` | |
| `payload(result_id) -> dict` | `get(...).payload` with the split payload loaded |

The store implements `RecordSource` (§4.6). There is no delete and no update; cleanup is a later command (non-goal).
`StoreWriteError` and `StoreIntegrityError` are `ContractError`s with code `INTERNAL` **[added: 04 names no code for
store failures]**.

#### 4.5.4 Atomic write protocol

For each file (the gzip payload first, then the record; the record's presence commits the result):

1. Serialize fully in memory (canonical JSON; gzip with `mtime=0` and compression level 6 so the bytes are
   reproducible).
2. Create `<final name>.<16 hex random>.tmp` in the **same folder** with `O_CREAT | O_EXCL | O_WRONLY` (binary).
3. Write all bytes, `flush`, `os.fsync(fd)`, close.
4. Commit with exclusive create: on Windows `os.rename(tmp, final)` (fails if `final` exists); on POSIX
   `os.link(tmp, final)` then `os.unlink(tmp)` (`link` fails if `final` exists); then, on POSIX, `fsync` the folder.
   `os.replace` is never used for records. Once `os.link` has succeeded the record is committed: a failure of the
   `unlink` or of the folder `fsync` after it is logged as a warning and does not fail the write (amendment B-358).
5. `PermissionError` (Windows sharing violations from scanners, 04 §3.1) on step 4 is retried after 0.05, 0.1 and
   0.2 s (three retries, four attempts; delays from the injected `sleep`) **[added: values are a software decision,
   not engineering values]**; after the last failure the temporary file is removed and `StoreWriteError` is raised.
   `FileExistsError` is not retried: the temporary file is removed and `StoreWriteError` is raised (a result id
   collision is a bug).
6. On any failure before commit, the temporary file is removed (best effort, logged).

Payload split: when `len(canonical_json(payload)) > PAYLOAD_SPLIT_BYTES` = 8 388 608 **[added: 8 MB read as 8 MiB]**,
the payload goes to `<result_id>.payload.json.gz` next to the record and the record carries `payload_file`.

`FileSystem` is an internal port (`_fs`) with a real implementation and a fake that can inject `PermissionError`,
`FileExistsError` and partial writes; it is the only place that touches the disk.

#### 4.5.5 Model identity and revision state (04 §3.3, §3.4)

`ModelState`: `contract`, `model_id`, `revision` (`int`, ≥ 0), `derived_from` (`ModelId` or null),
`promoted_from` (list of `ModelId`, default `[]`), `fingerprint` (`str`, max 200, or null), `file_sha256`
(`Sha256Hex` or null), `updated_at` (`Timestamp`).

`ModelStateStore(workspace, clock, fs)` stores one file per model at `.eng/state/models/<model_id>.json` (canonical
JSON). Methods: `get(model_id) -> ModelState | None`; `create(model_id, derived_from=None) -> ModelState` (revision
0; `CONFLICT` if it exists; exclusive create as §4.5.4); `increment(model_id, expected_revision, fingerprint=None,
file_sha256=None) -> ModelState` (compare-and-set: `CONFLICT` if the stored revision differs; written as a temporary
file then `os.replace`, with the retries of §4.5.4 step 5, because the state file is mutable, unlike records);
`record_promotion(target, source)`. Stamping the identity into the host model is the adapter's job, not this
package's. Single-writer discipline per host instance is the engine's (11 §6 item 10); the compare-and-set detects a
lost update but does not lock.

### 4.6 References (04 §3.2, §3.4)

#### 4.6.1 Syntax

`Ref` model: exactly one key `"$ref"` (alias of `ref`) with a `RefString`. `RefString` = `ResultId` optionally
followed by `#` and a pointer. The pointer is the **JSON string representation** of RFC 6901 (§5 of the RFC), not the
URI fragment representation: there is no percent-decoding. `res_X` and `res_X#` both mean the whole payload.

`JsonPointer.parse(text)`: empty text is the whole document; otherwise it must start with `/`; tokens are split on `/`
and unescaped `~1` → `/` then `~0` → `~`; a `~` followed by anything other than `0` or `1` is invalid. Errors:
malformed result id → `INVALID_ARGUMENT`; malformed pointer → `REF_POINTER_INVALID`. `JsonPointer.format(tokens)`
escapes `~` → `~0` then `/` → `~1`.

Evaluation (RFC 6901 §4): on an object, the token is a member name; on an array, the token must be `0` or match
`[1-9][0-9]*` and be less than the length (`-` and leading zeros are invalid); on a scalar, any token is invalid. Each
failure is `REF_POINTER_INVALID` with `field` and the failing token in `received`. Pointers address the record's
**payload**, never the record envelope.

#### 4.6.2 Resolution

`resolve_ref(ref, rule: RefRule, source: RecordSource, current_revision: Callable[[ModelId], int | None]) ->
ResolvedRef`.

`RefRule` (built from the parameter's metadata, §5): `kinds` (set of accepted `KindName`, may be empty = any),
`unit` (the parameter's canonical unit symbol, or null), `stale_ok` (`bool`).

Steps, first failure wins:

1. Parse (§4.6.1).
2. `source.get(result_id)`: missing → `REF_NOT_FOUND`; integrity failure propagates (`INTERNAL`).
3. Kind: if `rule.kinds` is non-empty and the record's `kind` is not in it → `REF_KIND_MISMATCH` with
   `expected.kinds`. This applies with and without a pointer **[added: 04 states it for whole-payload references]**.
4. Pointer evaluation → value.
5. Unit (only if `rule.unit` is set):
   - value is a quantity object (`{"value": number, "unit": str, ...labels}`): its `unit` must equal `rule.unit`
     exactly, else `REF_UNIT_MISMATCH`. Stored data is canonical, so no conversion happens here (validation never
     fixes an input, 04 §7).
   - value is a bare number: its unit is the canonical unit of the nearest pointer token, walking from the last token
     back, that is an object member name with a known suffix (§4.7.2); none found, or a different unit →
     `REF_UNIT_MISMATCH`.
   - any other value is left to the parameter's shape validation (an object or array parameter carries units in its
     own field names).
6. Staleness: if `record.producer.host` is set, `current_revision(host.model_id)` is consulted: `None` means the model
   is not tracked by the caller and the reference is accepted; a value greater than the record's `model_revision`
   gives `REF_STALE` unless `rule.stale_ok`; a value lower than the record's revision is an integrity failure
   (`INTERNAL`). Records without `host` (basis, engineer input, file-based results) are never stale by revision.

`ResolvedRef`: `ref` (`RefString`), `value` (`JsonValue`), `record_kind`, `result_id`, `model_id` and
`model_revision` (or null). Provenance records `ref`, never `value`.

#### 4.6.3 Local trace references **[added]**

A payload cannot contain its own `result_id`: `ResultStore.put` assigns the id after the payload is validated and
hashed (§4.5.3). A reference from inside a payload to another part of the same payload is therefore written as a
`LocalTraceRef`: `str`, pattern `^#/traces/(0|[1-9][0-9]*)$`, an RFC 6901 pointer (JSON string form, §4.6.1) into
the containing payload. `rebase_local_ref(result_id, local) -> RefString` returns `f"{result_id}{local}"`, which
`resolve_ref` then handles like any reference. `resolve_ref` itself never accepts a `LocalTraceRef` (it is not a
`RefString`): a consumer reading a verdict out of record `R` rebases its `trace_ref` onto `R` first. Producers that
surface a verdict in an envelope summary rebase it the same way, so callers only ever see the 04 §5.1 form. This keeps
`payload_sha256` independent of the `result_id`, and `put` needs no pre-allocated id.

### 4.7 Units (`canonical/1`, 04 §4)

#### 4.7.1 Dimensions

`Dimension` is a frozen tuple of integer exponents over (length L, mass M, time T, temperature Θ, plane angle A).
Plane angle is kept as its own dimension so an angle never compares equal in dimension to a ratio.

#### 4.7.2 Quantity kinds of canonical/1

| Quantity kind | Dimension (L, M, T, Θ, A) | Canonical unit symbol | Field suffix |
|---|---|---|---|
| `length` | (1, 0, 0, 0, 0) | `mm` | `_mm` |
| `area` | (2, 0, 0, 0, 0) | `mm2` | `_mm2` |
| `section_modulus` | (3, 0, 0, 0, 0) | `mm3` | `_mm3` |
| `second_moment` | (4, 0, 0, 0, 0) | `mm4` | `_mm4` |
| `force` | (1, 1, −2, 0, 0) | `kN` | `_kN` |
| `moment` | (2, 1, −2, 0, 0) | `kN.m` | `_kNm` |
| `stress` | (−1, 1, −2, 0, 0) | `MPa` | `_MPa` |
| `line_load` | (0, 1, −2, 0, 0) | `kN/m` | `_kN_m` |
| `area_load` | (−1, 1, −2, 0, 0) | `kPa` | `_kPa` |
| `unit_weight` | (−2, 1, −2, 0, 0) | `kN/m3` | `_kN_m3` |
| `mass` | (0, 1, 0, 0, 0) | `kg` | `_kg` |
| `angle` | (0, 0, 0, 0, 1) | `deg` | `_deg` |
| `time` | (0, 0, 1, 0, 0) | `s` | `_s` |
| `temperature` | (0, 0, 0, 1, 0) | `degC` | `_C` |
| `acceleration` | (1, 0, −2, 0, 0) | `m/s2` | `_m_s2` |
| `dimensionless` | (0, 0, 0, 0, 0) | `1` | `_ratio` or none |

Stress and area load share a dimension but are different quantity kinds with different canonical units: a parameter
declares its quantity kind (by suffix), and a value in the other unit is a unit mismatch, not a conversion. Unit
symbols are ASCII **[added: 04 shows `kN·m`; the wire symbol is `kN.m`]**.

`kind_for_field(name)` matches the longest known suffix at the end of `name` (so `_kN_m3` wins over `_kN_m`, which
wins over `_kN`); `_ratio` and names without a known suffix return `dimensionless` and `None` respectively.

#### 4.7.3 Named units and their cited definitions

Each `Unit` has a symbol, a dimension, an exact factor to the coherent SI unit of its dimension (m, kg, s, rad; K
intervals for temperature) as a `Fraction`, a power of π (0 except for `rad`-based factors), and an offset (temperature
only). Base entries are defined from the cited documents; every other entry is a product of base entries with integer
exponents, computed exactly at import (no hand-typed derived factors). The implementer of T5 checks each citation
against the document and records edition and page in `docs/verification/units.md`; an entry whose definition cannot be
confirmed in the cited document is removed and reported as a gap, never guessed. The defining values below are the
well-known exact definitions; the table and section numbers were written from the documents' structure, not checked
line by line, and are confirmed in T5 (gap G-4).

| Entry | Definition | Source |
|---|---|---|
| `m`, `kg`, `s` | SI base units | BIPM, *The International System of Units (SI Brochure)*, 9th edition (2019), Table 2 |
| `rad`, `N` (kg·m/s²), `Pa` (N/m²) | SI derived units with special names | SI Brochure, 9th ed., Table 4 |
| prefixes `m` (10⁻³), `c` (10⁻²), `k` (10³), `M` (10⁶) | SI prefixes | SI Brochure, 9th ed., Table 7 |
| `t` (tonne) = 1000 kg; `deg` = (π/180) rad; `min` = 60 s; `h` = 3600 s | Non-SI units accepted for use with the SI | SI Brochure, 9th ed., Table 8 |
| `degC`: t/°C = T/K − 273.15 | Celsius temperature | SI Brochure, 9th ed., §2.3.1 (definition of the degree Celsius); NIST SP 811 (2008) §4.2.1.1 |
| `in` = 0.0254 m (exact) | International inch | NIST Special Publication 811 (2008 edition), Appendix B.8 (exact factor) |
| `ft` = 0.3048 m (exact) | International foot | NIST SP 811 (2008), Appendix B.8 |
| `lb` = 0.45359237 kg (exact) | Pound (avoirdupois) | NIST SP 811 (2008), Appendix B.8 |
| `g_n` = 9.80665 m/s² (exact) | Standard acceleration of gravity, declared by the 3rd CGPM (1901) | NIST SP 811 (2008), Appendix B.8 (entries for kilogram-force and pound-force) |
| `kgf` = 1 kg × g_n = 9.80665 N (exact) | Kilogram-force | NIST SP 811 (2008), Appendix B.8 |
| `lbf` = 1 lb × g_n = 4.4482216152605 N (exact product of two exact definitions) | Pound-force | NIST SP 811 (2008), Appendix B.8 (which lists the rounded 4.448 222 N) |
| `kip` = 1000 lbf | Kip | NIST SP 811 (2008), Appendix B.8 |
| `tonf` = 1 t × g_n = 9806.65 N (metric tonne-force) | Derived from `t` and `g_n` | Composition of the two rows above; **its use for CSI `Ton` is gap G-1** |
| `degF`: t/°C = (t/°F − 32)/1.8 | Fahrenheit temperature | NIST SP 811 (2008), Appendix B.8 (degree Fahrenheit) |

Named units built from these (all by composition): lengths `mm`, `cm`, `m`, `in`, `ft`; areas and volumes and
fourth powers of each length (`mm2`, `cm2`, `m2`, `in2`, `ft2`, …, `in4`, `ft4`); forces `N`, `kN`, `MN`, `kgf`,
`tonf`, `lbf`, `kip`; moments as every force times every length (`kN.m`, `kN.mm`, `N.mm`, `kgf.m`, `tonf.m`,
`lbf.in`, `lbf.ft`, `kip.in`, `kip.ft`, …); stresses `Pa`, `kPa`, `MPa`, `GPa`, `N/mm2`, `kN/m2`, `kgf/cm2`,
`psi` (= lbf/in2), `ksi` (= kip/in2), `psf` (= lbf/ft2), `ksf` (= kip/ft2); line loads `kN/m`, `N/mm`, `kgf/m`,
`tonf/m`, `lbf/ft`, `kip/ft`, `kip/in`; unit weights `kN/m3`, `N/mm3`, `kgf/m3`, `tonf/m3`, `pcf` (= lbf/ft3),
`kip/ft3`, `kip/in3`; masses `kg`, `t`, `lb`; time `s`, `min`, `h`; angles `deg`, `rad`; temperatures `degC`,
`degF`, `K`; acceleration `m/s2`, `mm/s2`, `ft/s2`, `in/s2`; dimensionless `1`. The full list with symbols is the
`UNITS` mapping; its snapshot is part of `docs/schema/units.json` (§4.12) and each entry is reviewed against this
table.

#### 4.7.4 Conversion API

- `unit(symbol) -> Unit`; unknown symbol → `UnitError` (`UNIT_MISMATCH`).
- `convert_exact(value: int | Fraction | Decimal | float, src, dst) -> Fraction`: same dimension required (else
  `UnitError`); both π powers equal (else `UnitError` with hint to use `convert`); `float` input is converted with
  `Fraction(value)` (exact); non-finite input → `UnitError`. Affine (temperature) conversions go through kelvin.
- `convert(value: float | int, src, dst) -> float`: when π powers match, `float(convert_exact(...))` (one correctly
  rounded result, no drift); otherwise (only `deg` ↔ `rad` today) the rational part is exact and the multiplication
  by `math.pi` is the single float64 step, documented on the function.
- `CsiUnitSystem`: `name`, `force`, `length`, `temperature`, and derived `moment`, `stress`, `line_load`,
  `unit_weight`, `area`, `section_modulus`, `second_moment` unit symbols. `csi_unit_system(name)` covers the 16 CSI
  `eUnits` names (`lb_in_F`, `lb_ft_F`, `kip_in_F`, `kip_ft_F`, `kN_mm_C`, `kN_m_C`, `kgf_mm_C`, `kgf_m_C`, `N_mm_C`,
  `N_m_C`, `Ton_mm_C`, `Ton_m_C`, `kN_cm_C`, `kgf_cm_C`, `N_cm_C`, `Ton_cm_C`; the list matches the Sasaah CSI
  engine's mirror of the CSI API enumeration). The four `Ton_*` systems raise `UnitGapError` until G-1 is resolved.
  CSI mass and time units are not mapped in 0.1 (gap G-2).

### 4.8 Quantity, Cited

`Quantity` (frozen model): `value` (finite `float`), `unit` (`str`, a symbol in `UNITS`; validated). JSON:
`{"value": 450.0, "unit": "mm"}` (04 §4 rule 2). `LabeledQuantity(Quantity)` additionally allows extra members whose
values are strings, integers or booleans (for example `member`, `combo`, `end` in 04 §1's summary); they do not take
part in comparison.

Rules (11 §3 rule 2):

1. No arithmetic: `__add__`, `__radd__`, `__sub__`, `__rsub__`, `__mul__`, `__rmul__`, `__truediv__`,
   `__rtruediv__`, `__floordiv__`, `__mod__`, `__pow__`, `__neg__`, `__pos__`, `__abs__`, `__round__` raise
   `TypeError`; `__float__`, `__int__`, `__index__` and `__bool__` are not usable (raise `TypeError`), so a quantity
   cannot silently become a number. The value is reachable only as `.value`, which code-pack and calc code use
   explicitly. Validators test an optional quantity with `is not None`, never by truth value.
2. Ordering (`<`, `<=`, `>`, `>=`) only with another `Quantity` of the same dimension; against anything else
   (a number, `None`, a `Quantity` of another dimension) `TypeError`, never `False` or `NotImplemented`, so a threshold
   mistake cannot pass silently (11 §3 rule 2).
3. Equality (`==`, `!=`) is physical between two `Quantity` objects of the same dimension. A `Quantity` of another
   dimension is unequal (`False`, no exception), and any other object (a number, `None`) returns `NotImplemented`, so
   Python's fallback gives `False`. Reason: Pydantic model equality compares field values with `==`, so two `Verdict`
   or kind payloads holding `None` against a `Quantity`, or a force against a moment, must compare unequal rather
   than raise (AC35a). Comparing a quantity with a bare number in block or calc code is still a defect: the
   `eng-dev-gate` lint rejects it (owner queue item, not this package's code).
4. Comparison key: each side is converted to its coherent SI value `r = Fraction(repr(value)) × factor + offset` with
   its π power `p`, where `repr(value)` is the shortest decimal that round-trips to the float. The binary value
   `Fraction(value)` would make AC35 false (`25.4 mm` is not exactly `1 in` in binary); the shortest round-trip decimal
   is monotonic in the float, so ordering within a unit is unchanged (amended by B-069). When both π powers are equal, the keys `r` are compared as fractions (exact). When they differ (only
   `deg` against `rad` today), both are compared as `sifloat = float(r) * math.pi ** p`, the single float64 step of
   §4.7.4.
5. `__hash__` is `hash((dimension, sifloat))` for every unit, π power 0 included. It is consistent with rule 3:
   exactly equal fractions with equal π powers give the same `sifloat`, and the cross-π case compares `sifloat`
   itself. Equality across π powers is not transitive at the last float64 bit; this is documented on the class, and
   canonical stored data never mixes `deg` and `rad` (angles are canonical `deg`).
6. `Quantity.to(symbol) -> Quantity` converts through `units.convert`; `Quantity.canonical(kind)` converts to the
   canonical unit of a quantity kind. Both convert the float's binary value with one rounding, so `q.to(u)` need not
   compare equal to `q` (for example `25.4 mm` to `in` gives `0.9999999999999999 in`; amendment B-391, B-069 review).

`Cited` (frozen model): `value` (finite `float` or `int`), `unit` (`str` in `UNITS`; `"1"` for dimensionless),
`source` (`str`, 8 to 500 characters, non-blank: document, edition and clause, table or page, for example
`"ACI 318-14 Table 21.2.1(b)"`), `note` (`str`, max 500, or null). It has no arithmetic or comparison operators
either; code reads `.value` and the trace records the `Cited` object. `Cited(0.75, "ACI 318-14 …")` from 10 §3 becomes
`Cited(value=0.75, unit="1", source="…")`.

Why `Cited` is in the contract (03 §3 rule 3): code packs (layer 3) and harness calcs (layer 4) both need it, and it
is serialized inside calculation traces (§4.9.3), which are stored results that cross packages. A shared serialized
type is contract by definition; putting it in a code-pack library would make the harness depend on `structural-codes`
for a data type, and a separate library would need an ADR for one model. The lint that rejects bare literals is
`eng-dev-gate`'s, not this package's.

### 4.9 Verdicts, model issues, traces (04 §5)

#### 4.9.1 Verdict

| Field | Type | Rule |
|---|---|---|
| `source` | `VerdictSource` = `code_pack`, `host` | |
| `check_id` | `str`, max 200 | `code_pack`: `^[a-z][a-z0-9_]*\.[0-9a-z_]+\.[a-z][a-z0-9_]*$` (10 §3); `host`: `^[a-z0-9_.:-]+$` (the adapter's id of the host check) |
| `code` | `str`, 1 to 100 | For example `ACI 318-14` |
| `clause` | `str`, max 100, or null | Required for `code_pack` |
| `subject` | `Subject` | |
| `demand`, `capacity` | `Quantity` or null | Same dimension when both present |
| `ratio` | `float`, ≥ 0, or null | `demand / capacity`, computed by the producer (04 §5.1); not recomputed here |
| `ratio_limit` | `float`, > 0, default 1.0 | 04 §5.1 (1.0 unless the design basis sets a stricter limit) |
| `status` | `VerdictStatus` = `PASS`, `FAIL`, `NOT_APPLICABLE`, `NEEDS_ENGINEER`, `ERROR` | |
| `governing` | `bool`, default `false` | |
| `trace_ref` | `RefString`, `LocalTraceRef` or null | Required for `code_pack`. Inside a `verdicts.set/1` payload it must be a `LocalTraceRef` (§4.10.2); a verdict carried outside a stored payload (for example in an envelope summary) uses the full `RefString` form of 04 §5.1 |
| `assumptions` | list of `str` (each max 500), default `[]` | |

Consistency: `PASS` requires `ratio` set and `ratio <= ratio_limit`; `FAIL` requires `ratio` set and
`ratio > ratio_limit`; for `code_pack`, `PASS` and `FAIL` also require `demand` and `capacity`. Host verdicts may omit
`demand` and `capacity` when the host reports only a ratio.

`Subject`: `kind` (`SubjectKind` = `joint`, `frame`, `area`, `link`, `story`, `grid_line`, `section`, `material`,
`load_pattern`, `load_combination`, `footing`, `model`; new values are additive), `id` (`str`, 1 to 200),
`station_mm` (`float`, ≥ 0, or null), `case` (`str`, max 200, or null) **[added: the governing load case or
combination, needed by force-based checks]**.

#### 4.9.2 Model issue and `check_model` summary

`ModelIssue`: `severity` (`error`, `warning`, `info`), `code` (`str`, `^[A-Z][A-Z0-9_]{1,63}$`, defined by the
producer; codes are listed in the producer's documentation), `subject` (`Subject`), `message` (`str`, 1 to 2000).
`CheckModelSummary`: `errors`, `warnings`, `infos` **[added]** (`int`, ≥ 0), `clean` (`bool`, must equal
`errors == 0`).

#### 4.9.3 Calculation trace (shared by code packs and harness calcs)

`Trace`: `calc_id` (`str`: a code-pack `check_id` or a harness calc id `^harness\.[a-z0-9_.]+$`), `calc_version`
(`str`, max 64), `content_sha256` (`Sha256Hex`: the hash its approval is bound to, 10 §4), `subject` (`Subject` or
null), `inputs` (list of `TraceInput`), `constants` (list of `TraceConstant` = `{name, cited: Cited}`), `steps` (list of `TraceStep`), `outputs` (list of step or input names), `status`
(`VerdictStatus` or null), `messages` (list of `str`).

`TraceInput`: `name` (`^[A-Za-z_][A-Za-z0-9_]*$`), `value` (`JsonValue`), `unit` (`str` in `UNITS` or null), `ref`
(`RefString` or null: where the value came from). `TraceStep`: `name`, `value` (number, boolean or string), `unit`,
`formula` (`str`, max 1000: the expression in plain notation, for example `"phi * Vc"`), `source` (`str`, max 500: the
clause or method reference), `uses` (list of names of earlier inputs, constants or steps; each must exist earlier in
the trace). Names are unique within a trace. Traces travel inside payloads (`verdicts.set/1` and harness calc kinds),
never as free text.

### 4.10 Neutral kinds and the registry (04 §6, §11)

#### 4.10.1 Kind names, versions, registry

- A kind name is `<family>.<name>/<version>` (`KindName`). Neutral families, reserved for this package: `geom`,
  `model`, `forces`, `basis`, `verdicts`, `issues`. Any other package's kinds start with its own prefix (for example
  `harness.model_diff/1`, `sasaah_csi.analysis_messages/1`).
- Each released kind version is frozen: any change to its payload schema, additive or not, is a new kind version.
  Producers write one version; consumers declare the versions they accept (`RefRule.kinds`).
- Adding a kind or a kind version is a minor version of the package. Changing or removing a released kind version, or
  changing the envelope or record incompatibly, needs an ADR and a new contract major (04 §11).
- `KindRegistry` is an immutable mapping `KindName → type[BaseModel]`. `NEUTRAL_KINDS` holds the kinds below.
  `KindRegistry.extend(mapping)` returns a new registry; it rejects names in a neutral family and duplicates. No
  global registration.
- All payload models use `extra="forbid"`; every unit-bearing field carries its suffix (04 §4 rule 1) and the
  `x-eng-unit` schema annotation; every `id`/`name` string is 1 to 200 characters; lists of named items have unique
  names (validator).

#### 4.10.2 Kinds defined in 0.1

Common sub-models: `Point3` (`x_mm`, `y_mm`, `z_mm`); `CaseRef` (`case`: `str`; `case_type`: `load_pattern`,
`load_case`, `load_combination`; `step`: `str` or null, for envelope `Max`/`Min` or step numbers as the host reports
them).

| Kind | Payload |
|---|---|
| `model.stories/1` | `base_elevation_mm`; `stories`: list (bottom to top) of `{name, elevation_mm, height_mm (> 0), master_story: bool, similar_to: str or null}`; elevations strictly increasing and above `base_elevation_mm`; `similar_to` names a story in the list (heights are not recomputed here: that needs a tolerance) |
| `model.grid_system/1` | `systems`: list of `{name, origin_x_mm, origin_y_mm, rotation_deg, lines: list of {id, axis: "x" or "y", coordinate_mm, visible: bool}}`; Cartesian systems only (other grid types are a later kind version) |
| `model.frame_placements/1` | `frames`: list of `{id, kind: column, beam, brace, other; section; i_joint, j_joint: str or null; i, j: Point3; story: str or null; rotation_deg}`; `i != j` |
| `model.area_placements/1` | `areas`: list of `{id, kind: slab, wall, deck, other; section; points: list of Point3 (at least 3); joints: list of str or null; story: str or null}` |
| `model.sections/1` | `frame_sections`: list of `{name, material, shape}` with `shape` discriminated by `type`: `rectangular {b_mm, h_mm}`, `circular {D_mm}`, `other {host_shape: str}`; `area_sections`: list of `{name, material, kind: slab, wall, deck; thickness_mm}`; all dimensions > 0 |
| `model.materials/1` | `materials`: list of `{name, type: concrete, rebar, steel, other; E_MPa (> 0); nu_ratio (≥ 0, < 0.5); gamma_kN_m3 (≥ 0); fc_MPa, fy_MPa, fu_MPa: > 0 or null}`; `concrete` requires `fc_MPa`; `rebar` and `steel` require `fy_MPa` |
| `model.load_set/1` | `patterns`: list of `{name, type: dead, superimposed_dead, live, roof_live, wind, seismic, snow, other; self_weight_ratio (≥ 0)}`; `combinations`: list of `{name, type: linear_add, envelope, absolute_add, srss, range; items: list of {case: CaseRef, scale_ratio}}` (at least one item; a combination may not reference itself); `frame_loads`: list of `{frame, pattern, direction: gravity, global_x, global_y, global_z, local_1, local_2, local_3; w_kN_m}` (uniform over the full length); `area_loads`: list of `{area, pattern, direction (same enum), q_kPa}` (uniform). Every referenced pattern exists in `patterns` |
| `model.joint_restraints/1` | `joints`: list of `{joint, ux, uy, uz, rx, ry, rz: bool}` (true = restrained; neutral of any preset name) |
| `forces.joint_reactions/1` | `rows`: list of `{joint, case: CaseRef, FX_kN, FY_kN, FZ_kN, MX_kNm, MY_kNm, MZ_kNm}` in global axes; `axes: "global"` |
| `forces.member_end/1` | `sign_convention: "host_local/1"` (gap G-3); `rows`: list of `{member, case: CaseRef, end: "i" or "j" or null, station_mm (≥ 0), P_kN, V2_kN, V3_kN, T_kNm, M2_kNm, M3_kNm}` |
| `forces.story_drifts/1` | `rows`: list of `{story, case: CaseRef, direction: "X" or "Y", drift_ratio (≥ 0), point: str or null, x_mm, y_mm, z_mm: float or null}` |
| `basis.design_basis/1` | `template`: `{name, version, sha256}` or null; `fields`: `dict[str, BasisField]` keyed by dotted path: lowercase segments (`^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$`), except that the last segment may end with one field suffix of §4.7.2 written exactly as that table writes it, the single source of the suffixes; the part before the suffix may be empty, as `[a-z0-9_]+` already allows `compare._mm` (for example `limits.drift_ratio`, `compare.stress_MPa`; amendment B-463, owner decision OQ-Q44). `BasisField`: `value` (`JsonValue`), `unit` (`str` in `UNITS` or null; must match the suffix of the last path segment when it has one), `source` (13 §3: `template:<name>@<version>`, `engineer:<name>@<Timestamp>` or `model:<RefString>`), `confirmed` (`bool`), `citation` (`str` or null; required when `source` is `template:*`, 13 §2) |
| `basis.engineer_input/1` | `step`: `str` (the step path that asked); `fields`: `dict[str, {value, unit, entered_by: str, entered_at: Timestamp}]` |
| `verdicts.set/1` | `verdicts`: list of `Verdict`; `traces`: list of `Trace`; every non-null `trace_ref` is a `LocalTraceRef` `#/traces/<n>` with `n` less than the number of traces (§4.6.3; a full `res_…` reference is rejected, so the set is self-contained); `counts`: per `VerdictStatus` (must match); `draft: bool` (outputs of draft checks are watermarked, 10 §4) |
| `issues.model_check/1` | `summary`: `CheckModelSummary`; `issues`: list of `ModelIssue`; counts must match |

The design-basis pointer rule: `ctx.basis.ref("limits.drift_ratio")` is `res_<basis id>#/fields/limits.drift_ratio/value`
(the dot is a plain character in a JSON Pointer token). A helper `DesignBasis.missing(required: Iterable[str]) ->
list[str]` returns every required path that is absent or not confirmed (11 §6 item 5); the engine refuses to start
when it is non-empty.

`geom.*` (`geom.polylines/1`, `geom.outlines/1`, `geom.line_families/1`, `geom.texts/1`) are defined in a later minor
version, when the optional DXF start is built (18 §6). The edit cycle's own results (difference report, analysis
messages, design summaries) are harness kinds (`harness.*`), defined by `eng-harness`.

### 4.11 MCP mapping helpers (04 §10)

Plain dicts only; no import of the MCP SDK.

- `envelope_to_tool_result(env) -> dict`: `{"content": [{"type": "text", "text": canonical_json(env).decode()}],
  "structuredContent": env.model_dump(mode="json", by_alias=True), "isError": not env.ok}`.
- `tool_result_to_envelope(result: Mapping) -> Envelope`: validates `result["structuredContent"]` as `Envelope`; if it
  is absent or invalid, raises `NotAnEnvelope` (with the validation errors); if `isError` disagrees with `ok`, raises
  `NotAnEnvelope`.
- `extract_raw_reply(result: Mapping) -> RawToolReply`: `is_error` (`bool`, from `isError`, default `false`),
  `structured` (`dict` or null), `texts` (list of the `text` of every `type: text` block), `json_texts` (each text that
  parses as JSON, parsed; others skipped). Non-text blocks are counted in `other_blocks`. Adapters build envelopes from
  it; this package never interprets server-specific content.
- `output_schema() -> dict`: for tools' `outputSchema`, which MCP requires to be an object schema. The result is
  `{"type": "object", "required": ["contract", "ok"], "properties": {"contract": {"const": "eng-contract/1"}, "ok":
  {"type": "boolean"}}, "oneOf": [{"$ref": "#/$defs/SuccessEnvelope"}, {"$ref": "#/$defs/FailureEnvelope"}],
  "$defs": {...}}`, where `$defs` holds Pydantic's schemas of both envelopes and everything they reference (each
  envelope schema has `"type": "object"` and its `ok` `const`), and the `$schema` keyword is
  `https://json-schema.org/draft/2020-12/schema`. AC49a validates both 04 §1 examples against it.

Annotations and timeout classes (04 §10) are the publishing server's concern; not in 0.1.

### 4.12 JSON Schema snapshots

`_schema_export.write_all(folder)` writes one file per public model and kind into `docs/schema/`:
`envelope.schema.json`, `result-record.schema.json`, `error-detail.schema.json`, `ref.schema.json`,
`quantity.schema.json`, `cited.schema.json`, `verdict.schema.json`, `model-issue.schema.json`, `trace.schema.json`,
`model-state.schema.json`, `kinds/<kind name with "/" replaced by "-">.schema.json` (for example
`kinds/model.stories-1.schema.json`), plus `units.json` (every unit: symbol, dimension, exact factor as a fraction
string, π power, offset, source) and `error-codes.json` (codes and retry rules). Files are JSON with sorted keys,
two-space indentation and a final newline. `uv run python -m eng_contract._schema_export docs/schema` regenerates
them; AC51 fails if they are stale. The folder is a protected path (the whole package is, process/06 §4).

## 5. Inputs and outputs

This package defines types rather than tool parameters; its inputs and outputs are the models of §4. The parameter
metadata that tools use:

| Metadata (`eng_param`) | Type | Rule | JSON Schema |
|---|---|---|---|
| `unit` | unit symbol or null | Must equal the canonical unit of the field name's suffix; required when the name has a suffix | `x-eng.unit` |
| `ge`, `le`, `gt`, `lt` | `float` | Physical bounds (not code limits, 04 §7); require `bounds_source` | `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `x-eng.bounds_source` |
| `bounds_source` | `str`, 8 to 500 | Why the bounds are physical limits | `x-eng.bounds_source` |
| enum | the field's `Literal` or `StrEnum` type | | `enum` |
| `ref_capable` | `bool`, default `false` | The field also accepts `Ref` | `anyOf: [<literal>, {"$ref": "#/$defs/Ref"}]`, `x-eng.ref_capable` |
| `ref_kinds` | set of `KindName` | Accepted kinds for references | `x-eng.ref_kinds` |
| `engineering_quantity` | `bool`, default `false` | Requires `ref_capable`; under `InputPolicy(require_refs=True)` a literal is rejected | `x-eng.engineering_quantity` |
| `stale_ok` | `bool`, default `false` | Requires `ref_capable` | `x-eng.stale_ok` |

`ParamModel` is the base class for tool input models (`extra="forbid"`); `__pydantic_init_subclass__` checks the
definition rules (suffix and unit, bounds and source, flag dependencies) and raises `ContractDefinitionError` (a
programming error, not an `ErrorCode`).

`validate_input(model_cls, raw: Mapping, *, source: RecordSource, current_revision, policy: InputPolicy) ->
ValidatedInput` (`ValidatedInput`: the model instance and the provenance `inputs` map). Order (04 §7), first failure
returned as `ContractError`:

1. **Shape**: `raw` against the model's shape schema (types, required fields, enums, no extra fields, `Ref` objects
   well-formed), bounds not yet applied → `INVALID_ARGUMENT` with `field`.
2. **Policy**: a literal for an `engineering_quantity` field under `require_refs` → `INVALID_ARGUMENT`
   **[added: 04 §3.5 names no code]**.
3. **References**: each `Ref`, in field order, through `resolve_ref` with the field's `RefRule` → `REF_*`.
4. **Units**: literal quantity objects must carry the field's unit exactly → `UNIT_MISMATCH`.
5. **Bounds** on literal and resolved values → `OUT_OF_RANGE` with `field`, `expected {min, max, unit}` (exclusive
   bounds as `exclusive_min`/`exclusive_max`), `received`.
6. **Cross-field rules**: the model's own `model_validator`s → `INVALID_ARGUMENT`.
7. Host preconditions are the caller's (`PRECONDITION_FAILED`), after this function.

Validation never changes a value: no clamping, rounding or unit conversion.

## 6. Errors

| Condition | Contract error code | Fields |
|---|---|---|
| Workspace not configured, relative, network, cloud-synchronized or unknown | `PRECONDITION_FAILED` | `precondition: local_workspace`, `received` (classification), `hint` |
| Payload does not match its kind, unregistered kind | `INVALID_ARGUMENT` | `field` (path inside payload), `expected.kind` |
| Parent result missing on `put` | `REF_NOT_FOUND` | `received` (the id) |
| Record write failed after retries, id collision | `INTERNAL` (`StoreWriteError`) | `incident_id`, `hint` |
| Hash mismatch, unreadable record, revision regression | `INTERNAL` (`StoreIntegrityError`) | `incident_id`, `received` (result id) |
| Model state compare-and-set failed, state exists on create | `CONFLICT` | `expected.revision`, `received` |
| Malformed reference id | `INVALID_ARGUMENT` | `field` |
| Malformed or unresolvable pointer | `REF_POINTER_INVALID` | `field`, `received` (token) |
| Result not in the workspace | `REF_NOT_FOUND` | `field`, `received` |
| Kind not accepted | `REF_KIND_MISMATCH` | `field`, `expected.kinds`, `received` (kind) |
| Unit of a referenced value incompatible | `REF_UNIT_MISMATCH` | `field`, `expected.unit`, `received` |
| Older revision of the same model | `REF_STALE` | `field`, `expected.model_revision`, `received` |
| Input shape, literal under `require_refs`, cross-field rule | `INVALID_ARGUMENT` | `field`, `hint` |
| Literal quantity in the wrong unit; unknown unit; conversion across dimensions | `UNIT_MISMATCH` | `field`, `expected.unit`, `received` |
| Value outside bounds | `OUT_OF_RANGE` | `field`, `expected`, `received` |

## 7. Non-goals

- Standard-tool implementations (`get_server_info`, `read_result`, …, 04 §9) and tool annotations: no server is built
  here (ADR-0024); helpers come with the first server that needs them.
- Store cleanup command, archive, retention (04 §3.1 last bullet): a later minor version.
- The op ledger and reconciliation (ADR-0007): server or harness concern.
- `geom.*` kinds (a later minor version), seismic load parameters in `model.load_set` (open question Q6), grid
  types other than Cartesian, non-uniform member loads, section property modifiers.
- Temperature differences (intervals) as a quantity kind; mass and time units of CSI unit systems (G-2).
- Any engineering logic: no calcs, checks, rounding of sizes, combinations generation.
- A JSON Schema code generator for other languages (ADR-0004 alternative).
- Python versions other than 3.14 (ADR-0028 §5).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A wrong unit factor silently scales every value | R1 (units are engineering content, process/01 §3) and R2 | Only base definitions are typed, each cited and verified against the document (§4.7.3); derived factors are computed; exact tests (AC30, AC31), property tests, mutation score ≥ 80%; owner review of `docs/verification/units.md` |
| Canonical JSON differs between producers, so hashes mismatch | R2 | RFC 8785 test vectors (AC1); one implementation for every package |
| A stale reference is accepted because the caller does not track the model | R2 | `current_revision` returning `None` is explicit at the call site; the engine passes every model it attached (11 §6 item 3); open question Q4 |
| Workspace on OneDrive or a share corrupts records | R2, R3 | Refusal with `local_workspace` (AC14, AC15); unknown classification refused |
| Path handling from `ENG_WORKSPACE` (file paths from input) | R3 | Absolute path required; no expansion; records hold base names only; security-reviewer lens on T13 and T14 |
| Pydantic behavior changes the JSON Schema between versions | R2 | Snapshot test (AC51); `uv.lock` pins Pydantic |
| Additive fields marked **[added]** diverge from 04 | R2 | Listed in §11 for the owner; recommendation to record them in the hub by ADR |

## 9. Test strategy

| Criteria | Test layer | Location |
|---|---|---|
| AC1 to AC3, AC5 to AC28 (with AC15a and AC21a), AC30 to AC32, AC34, AC35, AC35a, AC37 to AC45, AC49, AC49a, AC50 | Unit | `tests/unit/` |
| AC4, AC29, AC33, AC36 | Property (Hypothesis, CI profile `derandomize=True`) | `tests/property/` |
| AC46 to AC48 (with AC48a), AC51 | Contract | `tests/contract/`, fixtures `tests/data/kinds/` |
| AC15 | Unit, marker `windows` (runs only in the Windows CI job) | `tests/windows/` |
| AC52 | Mutation and coverage, in the gate | CI `gate` job |
| AC53 | Gate import rule | `eng-dev-gate` tests |

Tests use no network, no clock and no randomness except through the injected `Clock`, `IdSource` and Hypothesis's
seeded profile (process/05 §3). Float comparisons in tests are exact unless a test states a tolerance; the only float
tolerance in this spec is the `deg` ↔ `rad` step (one float64 multiplication, compared with `math.isclose(rel_tol=4 *
sys.float_info.epsilon)`).

## 10. Version impact

New package, version 0.1.0, contract `eng-contract/1`, units `canonical/1`. Every later change follows §4.10.1 and
04 §11; the changelog states the impact of each.

Amendment B-463 (AC48a) widens the `basis.design_basis/1` path rule of §4.10.2: every path valid before stays valid,
and the kind's JSON Schema snapshot (`docs/schema/kinds/basis.design_basis-1.schema.json`, the `fields` pattern) changes
(§4.12, AC51). The package is unreleased (`0.1.0.dev0`), so the kind version is not yet frozen (§4.10.1): it stays
`basis.design_basis/1`, the change ships in 0.1.0 with a changelog line, and no ADR or contract major is needed. Once
0.1.0 is released, the same change would be a new kind version `basis.design_basis/2` in a minor version (§4.10.1).

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| G-1 | Meaning of `Ton` in the CSI `eUnits` names (`Ton_mm_C`, `Ton_m_C`, `Ton_cm_C`): metric tonne-force (1000 kgf) or the 2000 lbf short ton-force | Owner (from CSI documentation or a live check) | Treat as metric tonne-force only after confirmation from the CSI API documentation or a local test; until then the four systems raise `UnitGapError` and the CSI adapter refuses a model in those units |
| G-2 | CSI mass and time units per unit system (mass as force·s²/length) | Owner, CSI adapter work | Map when the adapter reads masses; not needed by the edit cycle |
| G-3 | Sign and axis convention of `forces.member_end/1` (host local axes 1-2-3, sign of `P`) | Owner | Record `host_local/1` = the CSI local-axis convention as documented by CSI, confirmed during S-12 and the first local run; consumers must check `sign_convention` |
| G-4 | The table and section numbers cited in §4.7.3 (SI Brochure 9th edition Tables 2, 4, 7, 8 and §2.3.1; NIST SP 811 (2008) Appendix B.8 and §4.2.1.1) were not checked against the documents in this spec | Owner, T5 author and reviewer | T5 records page and entry for every row in `docs/verification/units.md`; a row that cannot be confirmed is removed and reported, never kept on memory |
| Q1 | The **[added]** details (1024-byte KB, `payload_file`, `files` provenance, `op_id` on errors, `infos` count, `Subject.case`, `INTERNAL` for store failures, `INVALID_ARGUMENT` for literals under `require_refs`, ASCII unit symbols, `canonical.loads` and its integer rule, local trace references in `verdicts.set/1`) are not in 04 | Owner | Record them in 04 through a hub ADR ("eng-contract 0.1 details"), so 04 stays the single source |
| Q2 | `UNKNOWN` location classification is refused; this can block a valid local workspace whose drive type cannot be read | Owner | Keep refusing (safe); the hint names `ENG_WORKSPACE`; revisit after the local tests |
| Q3 | Envelope and record models forbid unknown fields, so an older reader rejects a newer minor version's additive field | Owner | Acceptable while all packages are in one workspace and upgrade together; before the first public release, decide by ADR whether readers ignore unknown fields |
| Q4 | `current_revision` returning `None` accepts a host reference from an untracked model | Owner | Keep, and require the engine to pass a function that knows every attached model (engine spec); untracked models are then only those never attached in the run |
| Q5 | Should verdicts recompute `ratio = demand / capacity` as a consistency check | Owner | No: the check needs a tolerance, which is engineering content; code-pack tests own it |
| Q6 | The phase 1 edit cycle changes seismic load parameters through a dedicated tool (18 §2), but `model.load_set/1` carries none | Owner | Define them as a harness kind (`harness.seismic_parameters/1`, owned by `eng-harness`) before phase 1's seismic step: the parameters are code- and host-specific (the host's automatic seismic load per code edition), so a neutral kind would freeze one code's fields into the contract. Promote to a neutral `model.load_set/2` or `model.seismic_*` kind only when a second host or code needs the same shape |
