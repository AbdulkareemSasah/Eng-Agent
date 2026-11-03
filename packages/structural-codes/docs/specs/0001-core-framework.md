---
id: spec-0001-structural-codes-core
issue: "B-070"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2]
---

# Spec 0001: structural-codes core framework

Package: `structural-codes-core` (import package `structural_codes`), in `packages/structural-codes/core/` · Author:
agent identity (bootstrap mode, [ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) ·
Date: 2026-11-03

This spec implements the framework half of [10-structural-codes](../../../../design/docs/architecture/10-structural-codes.md)
(cited below as "10 §n") and [ADR-0016](../../../../design/docs/adr/0016-code-packs-lifecycle-and-overlays.md), on top
of the contract API of the [eng-contract 0.1 spec](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) (cited as
"EC §n"). It does not repeat those documents: where a rule is stated there, this spec names the section and adds only
what an implementer and a reviewer need to decide a case. Details this spec adds are marked **[added]** and listed in
§11. The ACI 318-14 and SBC 304-2018 packs have their own specs (B-071, B-072).

## 1. Problem

Code-pack checks turn design-code clauses into verdicts that the harness and the engineer rely on (P4). Without one
framework, every check would re-implement input bounds, applicability, tracing, verdict construction, lifecycle and
verification, and a mistake in any of them gives a wrong verdict that looks right (16 §1). The framework is the one place
where these rules are enforced, so each check is only its clause logic, and a reviewer compares that logic with the
clause spec alone.

Consumers: the packs `aci318_14` and `sbc304_2018` (layer 3, 10 §2); `eng-harness` through `ctx.calc`
([11](../../../../design/docs/architecture/11-harness-engine.md) §3, spec B-062); anyone through the plain API (10 §7).

The framework holds **no engineering numbers**. Its only numeric policy values are the contract's default
`ratio_limit` (04 §5.1) and the default verification tolerance (10 §6), each a `Cited` value naming that section
(AC36).

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| `eng-contract` 0.1 | `ParamModel`, `eng_param`, `validate_input` (EC §5), `Cited`, `Quantity` (EC §4.8), `Verdict`, `Trace` (EC §4.9), `verdicts.set/1` (EC §4.10.2), `canonical_json` and `payload_sha256` (EC §4.3), `ContractError` (EC §4.2.3) | Used for every shared shape; nothing is redefined here |
| Pydantic 2 | Through the contract; imported directly for check metadata models | Used (declared dependency, IM006) |
| PyYAML | `approvals.yaml` (10 §4) and the verification case files are YAML; `safe_load` only | Used: runtime dependency, package ADR-0001 (T1, owner queue) |
| `pint`, `forallpeople`, `handcalcs` | Unit-aware or traced arithmetic; rejected for the contract by [ADR-0006](../../../../design/docs/adr/0006-canonical-units.md); `handcalcs` renders from source text, not from a recorded trace | Not used |
| Jinja2 and similar | HTML templates for notes; a dependency for one fixed layout | Not used: the renderer builds HTML with `html.escape` (§4.10) |
| `importlib.metadata` entry points (standard library) | Lets packs register without the core importing them (layer rule IM001) | Used (§4.6) |
| Sasaah | Contains no code-check framework | Nothing reused |

## 3. Acceptance criteria

Test paths are relative to `packages/structural-codes/core/`. Tests use synthetic packs (`synthbase`, `synthover`)
under `tests/fixtures/`, whose checks have no engineering meaning: their constants cite `"synthetic test fixture, no
engineering meaning"`.

### 3.1 Check definition

- AC1. Given check metadata whose `check_id` does not match the contract pattern (EC §4.9.1), whose first segment is
  not the pack name, or whose clause segment differs from `clause_token(clauses[0])`, when the check is defined, then
  `CheckDefinitionError`. Given `"22.6.5.2"` and `"21.2.1(b)"`, `clause_token` returns `"22_6_5_2"` and `"21_2_1_b"`.
  Test: `tests/unit/test_meta.py::test_check_id_rule`.
- AC2. Given metadata missing `code`, `edition`, `clauses`, `title` or `members`, with a member type that is not a
  `SubjectKind`, or with a `spec` path that is not a relative POSIX path ending in `.md`, when defined, then
  `CheckDefinitionError`. Test: `tests/unit/test_meta.py::test_metadata_fields`.
- AC3. Given an input model that is not a `CheckInputs` subclass, has a field that is not a scalar (float, int, bool,
  `StrEnum`/`Literal`), or a numeric field without physical bounds and `bounds_source`, when a check uses it, then
  `CheckDefinitionError`. Test: `tests/unit/test_inputs.py::test_definition_rules`.
- AC4. Given a field declared with `bounded(ge=Cited(...), le=Cited(...))`, when the JSON Schema is generated, then it
  carries the bounds and a `bounds_source` joined from the two citations; when a value outside them is evaluated, then
  `OUT_OF_RANGE` from `validate_input` (EC §5) and nothing is clamped. Test:
  `tests/unit/test_inputs.py::test_bounded_helper_and_out_of_range`.
- AC5. Given a check whose preconditions are `[P1 → NOT_APPLICABLE, P2 → NEEDS_ENGINEER]`, when P1 fails, then one
  verdict `NOT_APPLICABLE` with `demand`, `capacity` and `ratio` null, the body is not run, and the trace messages name
  `P1` and its clause; when only P2 fails, then `NEEDS_ENGINEER` likewise; when both fail, P1 wins (declared order).
  Test: `tests/unit/test_applicability.py::test_outcomes_and_order`.
- AC6. Given a body that raises `NotImplementedGap("G-3", clause="22.6.5.2", reason=...)` with `G-3` declared in the
  metadata's `gaps`, when evaluated, then one verdict `NEEDS_ENGINEER` whose trace messages contain `G-3`, the clause and
  the reason; an undeclared gap id raises `CheckDefinitionError`. Test: `tests/unit/test_runner.py::test_not_implemented_gap`.
- AC7. Given the same inputs, when a check is evaluated twice in one process and once in each of two subprocesses with
  `PYTHONHASHSEED` 0 and 1, then the canonical JSON of the four payloads is byte-identical. Test:
  `tests/replay/test_determinism.py::test_identical_across_runs_and_hash_seeds`.

### 3.2 Trace recorder

- AC8. Given a recorder, when `const("phi", Cited(...))` is called, then it returns the cited value and records a
  `TraceConstant`; when a name is reused, a step's `uses` names something not recorded earlier, or a step value is NaN
  or infinite, then `CheckDefinitionError` for the first two and `TraceValueError` for the third. Test:
  `tests/unit/test_trace.py::test_recording_rules`.
- AC9. Given an evaluation, when its trace is built, then every input field is a `TraceInput` with the unit of its
  field metadata and the `ref` of its provenance (null for literals), `calc_id` is the `check_id`, `calc_version` is
  the pack version, `content_sha256` is the check's content hash (§4.7), and the trace validates as the contract's
  `Trace`. Test: `tests/unit/test_trace.py::test_inputs_and_contract_shape`.
- AC10. Given a step whose name ends in a known unit suffix (EC §4.7.2) and whose unit differs from that suffix's
  canonical unit, or a unit not in `UNITS`, when recorded, then `CheckDefinitionError`. Test:
  `tests/unit/test_trace.py::test_step_units`.

### 3.3 Verdict builder

- AC11. Given steps `demand_kN` and `capacity_kN`, when `t.verdict(demand="demand_kN", capacity="capacity_kN")` runs,
  then a step `ratio` (`formula "demand / capacity"`, `source "04-tool-contract §5.1"`) is recorded and the status is
  `PASS` when `ratio <= ratio_limit` and `FAIL` otherwise, compared in float64 with no tolerance (ratio equal to the
  limit is `PASS`; `math.nextafter(limit, inf)` is `FAIL`). Demand and capacity of different dimensions, or names not
  recorded, raise `CheckDefinitionError`. Test: `tests/unit/test_verdict.py::test_status_from_ratio`.
- AC12. Given a capacity `<= 0` or a demand `< 0`, when the verdict is built, then status `ERROR`, `ratio` null, and a
  trace message names the value; no exception escapes. Test: `tests/unit/test_verdict.py::test_invalid_capacity_gives_error`.
- AC13. Given the reserved input `ratio_limit` set to 0.95, when evaluated, then the verdict uses 0.95; when absent,
  the contract default; when above the contract default or `<= 0`, then `OUT_OF_RANGE`. Test:
  `tests/unit/test_verdict.py::test_ratio_limit`.
- AC14. Given a batch with several verdicts per subject, when the payload is built, then for each subject exactly the
  `PASS`/`FAIL` verdict with the largest ratio is `governing` (the first in order on a tie) and no verdict is governing
  for a subject without one; a body cannot set `governing`. Tests: `tests/unit/test_verdict.py::test_governing_selection`,
  `tests/property/test_governing_props.py::test_one_governing_per_subject`.
- AC15. Given any verdict produced, when validated, then it is a contract `Verdict` with `source: code_pack`, `code`
  from the metadata, `clause` from the builder argument (which must be one of the metadata's `clauses`) or the first
  clause, the evaluated subject, and the check's assumptions. Test: `tests/contract/test_verdict_shape.py::test_verdict_fields`.

### 3.4 Packs, registry, overlays

- AC16. Given packs registered under the entry-point group `structural_codes.packs`, when `Registry.discover()` runs,
  then packs and checks are loaded in sorted order; a duplicate pack name or `check_id` raises `CheckDefinitionError`;
  `registry.get("x.y.z")` for an unknown id raises `ContractError(NOT_FOUND)` with `field: "check_id"`. Test:
  `tests/unit/test_registry.py::test_discovery_and_lookup`.
- AC17. Given an overlay pack, when its registry entry is resolved, then every check of the base pack has exactly one
  overlay entry (inherited, overridden or removed); a missing or duplicate entry, or an entry naming an unknown base
  check, raises `CheckDefinitionError`. Test: `tests/unit/test_overlay.py::test_completeness`.
- AC18. Given an inherited entry, when the overlay check is evaluated, then it runs the base body and preconditions; its
  verdicts carry the overlay's `code` and mapped clause; trace constants keep their base citations unchanged; a trace
  message names the base `check_id` and the clause mapping; its content hash includes the base check's hash. Test:
  `tests/unit/test_overlay.py::test_inherited_evaluation`.
- AC19. Given overridden and added entries, when evaluated, then each runs its own body; an inherited or overridden
  entry whose overlay clause is not in the clause map, or maps to a clause other than the base check's first clause,
  raises `CheckDefinitionError`. Test: `tests/unit/test_overlay.py::test_overridden_added_and_clause_map`.
- AC20. Given a removed entry, when the overlay id is looked up, then `ContractError(NOT_FOUND)` whose hint names the
  removal reason; the base check stays usable under its own pack. Test: `tests/unit/test_overlay.py::test_removed`.

### 3.5 Content hash and lifecycle

- AC21. Given a check, when its content hash is computed twice, then equal; after changing one byte of its module, of a
  pack module it imports (directly or transitively), of a core module, of its metadata or of its input model, then
  different; with CRLF line endings in place of LF, or after changing a pack module it does not import, then unchanged.
  Test: `tests/unit/test_content_hash.py::test_hash_inputs`.
- AC22. Given a check module (or a module in its closure) that imports `importlib` or calls `__import__`, when hashed,
  then `CheckDefinitionError`. Test: `tests/unit/test_content_hash.py::test_dynamic_import_rejected`.
- AC23. Given `approvals.yaml` files, when loaded, then an empty file (`approvals: []`, `withdrawn: []`) is valid; a
  missing field, an unknown key, a malformed hash or date, a `kind: approved` entry for an inherited check, or a
  `kind: inherited-confirmed` entry for a non-inherited check raises `ApprovalsFileError`. Test:
  `tests/unit/test_lifecycle.py::test_approvals_file`.
- AC24. Given combinations of withdrawal, approvals entries, verification review blocks and case results, when the
  state is resolved, then `withdrawn` wins; `approved` requires an entry with the current content hash and the
  `verified` conditions; `verified` requires the §4.9.4 conditions; otherwise `draft`; an inherited check is `approved`
  only when its base check is also `approved`; a hash change turns `approved` into `verified` or `draft`. Test:
  `tests/unit/test_lifecycle.py::test_state_resolution`.
- AC25. Given mode `production`, when a check that is not `approved` is evaluated, then `CheckNotUsable`
  (`INVALID_ARGUMENT`, `field: "check_id"`, interim code, §11 Q1); given mode `trial`, `draft` and `verified` checks run
  and the payload has `draft: true`; a `withdrawn` check is refused in both modes. Test:
  `tests/unit/test_lifecycle.py::test_mode_usability`.

### 3.6 Evaluate and batch

- AC26. Given literal inputs, when `evaluate(check_id, inputs, subject=...)` runs, then the result's payload validates
  as `verdicts.set/1` (EC §4.10.2) with local `trace_ref` values, matching counts and one trace. Test:
  `tests/contract/test_verdict_set.py::test_evaluate_payload`.
- AC27. Given inputs containing references and a `RecordSource`, when evaluated, then values are resolved through
  `validate_input` and each `TraceInput.ref` holds the reference; given references and no source, then
  `INVALID_ARGUMENT`; `REF_*` errors propagate unchanged. Test: `tests/unit/test_runner.py::test_references`.
- AC28. Given a batch of N items, when `evaluate_batch` runs, then the payload has N traces in item order and the
  verdicts in item order, each pointing to its item's trace; when item k fails validation, then the `ContractError` of
  that item with `field` prefixed `items/<k>/` is raised and nothing is evaluated; when item k's body raises
  `ZeroDivisionError`, `OverflowError`, `TraceValueError` or a math domain `ValueError`, then item k gets one `ERROR`
  verdict and the others are unaffected; any other exception propagates. Test: `tests/unit/test_runner.py::test_batch`.
- AC29. Given a body that records no verdict, when evaluated, then `CheckDefinitionError`. Test:
  `tests/unit/test_runner.py::test_no_verdict`.

### 3.7 Verification

- AC30. Given case files, when loaded, then a `hand_check` case needs a `derivation`; a `worked_example` needs either
  `book` (title, edition, page, example) or `code_example` (document, edition, example); a `program_comparison` needs
  `program`, `program_version` and either a `record` path or `status: needs_local_test`; every expected quantity needs
  `abs_tol`; anything else raises `VerificationDataError`. Test: `tests/unit/test_verification.py::test_case_file_schema`.
- AC31. Given an expected value `e`, an actual `a`, `rel_tol` (default from 10 §6) and `abs_tol`, when compared, then
  the case passes iff `abs(a - e) <= max(rel_tol * abs(e), abs_tol)`; an expected status must match exactly. Tests:
  `tests/unit/test_verification.py::test_tolerance`, `tests/property/test_tolerance_props.py::test_symmetric_and_monotone`.
- AC32. Given a check's cases, when the verification runner runs, then each case is `pass`, `fail` or `pending`
  (program comparisons marked `needs_local_test`); hand checks are reported but never satisfy the worked-example
  requirement; the report lists every unmet requirement of §4.9.4. Test:
  `tests/unit/test_verification.py::test_report_and_requirements`.
- AC33. Given a pack, when `python -m structural_codes verify --pack P` runs, then it exits 0 if no case fails
  (pending is not a failure), 1 if any case fails, 2 on a data or definition error, and prints the report. Test:
  `tests/unit/test_cli.py::test_verify_exit_codes`.

### 3.8 Calculation notes

- AC34. Given a fixed `verdicts.set/1` payload, when `render_html` runs, then the output equals the committed golden
  file byte for byte; it shows per trace the inputs (with references), constants with their sources, steps with formula,
  source and uses, and the verdicts; framework labels appear in English with Arabic labels in `<span lang="ar"
  dir="rtl">`; a `DRAFT` watermark appears when `draft` is true. Test: `tests/golden/test_notes.py::test_golden`
  (golden file under `tests/data/golden/notes/`).
- AC35. Given a payload whose step formula contains `<script>` and a payload with `draft: false`, when rendered, then
  the formula is escaped, the output has no `<script>` element and no external URL, there is no watermark, and every
  number in the output occurs in the payload. Test: `tests/unit/test_notes.py::test_escaping_watermark_and_values`.

### 3.9 Package-level

- AC36. Given the core source, when scanned, then every `Cited(...)` source starts with `04-tool-contract` or
  `10-structural-codes`, and no module defines a check. Test: `tests/unit/test_package.py::test_no_engineering_constants`.
- AC37. Given the package, when the gate runs, then line coverage ≥ 95%, branch coverage ≥ 90% and the mutation score
  of the R1 modules (§4.1) ≥ 80% ([process/05](../../../../design/process/05-testing-and-verification.md) §2). Evidence:
  the CI `gate` job.
- AC38. Given the package, when the gate's import check runs, then it imports only `eng_contract`, `pydantic`, `yaml`
  and the standard library, and other packages import only the public modules of §4.1. Evidence: the CI `gate` job;
  `tests/unit/test_package.py::test_public_modules`.

## 4. Design

### 4.1 Layout and public API

Workspace layout (task statement of B-070; 10 §2): `packages/structural-codes/` holds one `AGENTS.md`, `CLAUDE.md`,
`.gate/` and the shared `docs/` (specs, plans, ADRs, clause specs under `docs/clause-specs/<pack>/<check_id>.md`,
verification records under `docs/verification/<pack>/<check_id>.md`); the packages are `core/`, `aci318-14/` and
`sbc304-2018/`, each a uv workspace member added by its own skeleton task (D-10).

`core/src/structural_codes/` public modules; every other module starts with an underscore.

| Module | Public names |
|---|---|
| `structural_codes` | `evaluate`, `evaluate_batch`, `BatchItem`, `Evaluation`, `Mode`, `__version__` |
| `structural_codes.errors` | `CheckDefinitionError`, `NotImplementedGap`, `TraceValueError`, `CheckNotUsable`, `ApprovalsFileError`, `VerificationDataError` |
| `structural_codes.meta` | `CheckMeta`, `GapDecl`, `clause_token` |
| `structural_codes.inputs` | `CheckInputs`, `bounded` |
| `structural_codes.applicability` | `Precondition`, `Outcome` |
| `structural_codes.trace` | `TraceRecorder` |
| `structural_codes.check` | `check` (decorator), `Check` |
| `structural_codes.pack` | `Pack`, `Registry`, `ENTRY_POINT_GROUP` |
| `structural_codes.overlay` | `Overlay`, `Inherited`, `Overridden`, `Added`, `Removed` |
| `structural_codes.lifecycle` | `State`, `ApprovalsFile`, `resolve_state` |
| `structural_codes.content_hash` | `content_hash` |
| `structural_codes.verification` | `CaseFile`, `Case`, `compare`, `verify_check`, `verify_pack`, `VerificationReport` |
| `structural_codes.notes` | `render_html` |

R1 modules (mutation ≥ 80%): `trace`, `check` (verdict builder in `_verdict`), `applicability`, `overlay`,
`lifecycle`, `content_hash`, `verification`, and the runner (`_runner`). R2: the rest of `src/`.

### 4.2 Check metadata and identifiers (10 §3)

`CheckMeta` (frozen Pydantic model, `extra="forbid"`): `check_id`; `pack` (import name); `code` (for example
`"ACI 318-14"`, 1 to 100); `edition` (1 to 20); `clauses` (non-empty tuple of clause numbers as printed in the code,
each 1 to 40); `title` and optional `title_ar` (our own words, 1 to 200; no clause text, 10 §8); `members` (non-empty
set of `SubjectKind`); `spec` (relative path of the clause spec under `docs/clause-specs/`); `gaps` (tuple of
`GapDecl{id: ^G-[0-9]+$, clause, reason}`); `assumptions` (tuple of `str`, each max 500).

`clause_token(clause)`: lower-case, each run of characters outside `[0-9a-z]` replaced by `_`, leading and trailing
`_` removed **[added: 10 §3 shows only the dotted case]**. `check_id` must equal
`f"{pack}.{clause_token(clauses[0])}.{short_name}"` with `short_name` matching `^[a-z][a-z0-9_]*$` and the whole id
the contract pattern (AC1).

### 4.3 Inputs (10 §3, 04 §7)

`CheckInputs` subclasses `eng_contract.params.ParamModel`. Fields are flat scalars **[added]** so every input is one
`TraceInput`; nested or list inputs are a later version (§7). Every numeric field has physical bounds with
`bounds_source` (they are not code limits; code limits are preconditions giving `NEEDS_ENGINEER`, 04 §7). Fields that
are engineering quantities are `ref_capable` and `engineering_quantity` (EC §5).

`bounded(*, ge=None, gt=None, le=None, lt=None, **eng_param_kwargs)` takes `Cited` bounds (so pack check modules write
no bare literal, the gate's FB005 rule A1) and returns `eng_param(...)` with the numeric bounds and `bounds_source`
joined from the citations.

Reserved field on `CheckInputs`: `ratio_limit: float | None` (ref-capable, from the design basis), bounded `> 0` and
`<= ` the contract default (04 §5.1) **[added]**.

### 4.4 Applicability (10 §3)

`Precondition(id: ^[A-Z][A-Z0-9_]*$, outcome: Outcome, clause: str, description: str, test: Callable[[I,
TraceRecorder], bool])`; `Outcome` = `NOT_APPLICABLE` or `NEEDS_ENGINEER`. The check's preconditions are evaluated in
declared order before the body; a test records any value it compares (constants through `t.const`) and the first test
returning `False` ends the evaluation with one verdict of its outcome and a trace message
`"<id> (<clause>): <description>"`. Nothing is clamped. `NotImplementedGap(gap_id, clause, reason)` raised by the body
or a precondition test is the explicit gap of R1 (process/10 §2): the runner gives `NEEDS_ENGINEER` with the gap in the
messages (AC6).

### 4.5 Trace recorder and verdict builder (10 §3, EC §4.9)

`TraceRecorder` is created by the runner per evaluation; the body never builds traces itself.

| Call | Effect |
|---|---|
| inputs (automatic) | One `TraceInput` per field, value, unit from field metadata, `ref` from the `ValidatedInput` provenance |
| `t.const(name, cited) -> float` | Records `TraceConstant{name, cited}`; returns `cited.value` as `float` |
| `t.step(name, value, *, unit, formula, source, uses) -> float` | Records a `TraceStep`; `value` must be a finite `float` (or `bool` for logical steps); `uses` must name earlier inputs, constants or steps |
| `t.value(name) -> float` | Reads a recorded value |
| `t.note(text)` | Adds a trace message |
| `t.verdict(*, demand, capacity, clause=None, assumptions=())` | Builds one verdict from two recorded names |

Rules: names are unique and match the contract's name pattern; a unit suffix in a name fixes the unit (AC10); NaN or
infinity raises `TraceValueError` (AC8).

Verdict builder: demand and capacity are recorded names of the same dimension. It records step `ratio` (`ratio_2`,
`ratio_3`, ... for later verdicts of the same evaluation, so names stay unique), then status
`PASS` iff `ratio <= ratio_limit` (exact float64, AC11). Capacity `<= 0` or demand `< 0` gives `ERROR` with a message
(AC12) **[added: 04 §5.1 does not define them]**. Demand and capacity become `Quantity` values in the step's unit;
`trace_ref` is the local `#/traces/<n>` of the item (EC §4.6.3). `governing` is assigned by the runner (AC14). Check
assumptions plus verdict assumptions go into `assumptions`.

The body signature is `def body(inp: I, t: TraceRecorder) -> None`; pure, float64, no I/O, globals, time or randomness
(10 §3). The gate's FB005 rejects bare literals in pack check modules; purity of imports is §11 Q3.

### 4.6 Checks, packs and registry

`@check(meta=CheckMeta(...), inputs=I, preconditions=(...))` wraps a body into a `Check` (meta, input model,
preconditions, body, module name). `Pack(name, code, edition, version, checks, approvals, base=None, overlay=None)`
where `approvals` is the package resource path of the pack's `approvals.yaml`. A pack exposes `PACK` and registers it
under `[project.entry-points."structural_codes.packs"]`. `Registry.discover()` loads every entry point (sorted by name);
`Registry.of(packs)` builds one explicitly (tests). The core never imports a pack by name (IM001).

### 4.7 Content hash (10 §4) **[added: exact inputs]**

`content_hash(check) -> Sha256Hex` = `payload_sha256` (EC §4.3) of

```json
{"format": "structural-codes-content/1", "meta": <CheckMeta JSON>, "inputs_schema": <input model JSON Schema>,
 "preconditions": [<id, outcome, clause>], "modules": {"<dotted name>": "<sha256 of source, LF-normalized>"},
 "eng_contract": "<eng_contract.__version__>", "base": "<base content hash or null>"}
```

`modules` is the static import closure of the check's module restricted to modules whose top-level package is the
check's pack or `structural_codes` (AST of each source, relative imports resolved). An `importlib` import or an
`__import__` call in the closure is a `CheckDefinitionError` (AC22). Sources are read with `importlib.util.find_spec`;
wheels ship them. The core sources are in the closure, so a core change resets approvals (§11 Q2).

### 4.8 Lifecycle and approvals (10 §4, process/10 §6 and §7)

`State` = `draft`, `verified`, `approved`, `withdrawn`. The state is **computed**, never declared in code:

1. `withdrawn` if the pack's `approvals.yaml` lists the check under `withdrawn`;
2. `approved` if an `approvals` entry has the current content hash, the `verified` conditions hold, and for an
   inherited check its entry is `inherited-confirmed` and its base check is `approved`;
3. `verified` if the conditions of §4.9.4 hold for the current content hash;
4. `draft` otherwise.

`approvals.yaml` (one per pack, shipped as package data; a protected path):

```yaml
format: structural-codes-approvals/1
approvals: []      # {check_id, content_sha256, kind: approved | inherited-confirmed, approver, date (YYYY-MM-DD),
                   #  verification_record (path), pull_request (URL)}
withdrawn: []      # {check_id, reason, issue, date}
```

Only the owner adds entries (CODEOWNERS); the core validates shape and kind (AC23), not identity. In this build every
file is empty and every check is `draft`.

`Mode` = `trial` (draft, verified, approved run; payload `draft` is true unless approved) or `production` (approved
only). `withdrawn` is refused in both (AC25).

### 4.9 Verification runner (10 §6, process/10 §3)

#### 4.9.1 Case files

One YAML file per check at `<pack package>/tests/data/golden/verification/<check_id>.yaml` (a protected test-oracle
path and an R1 floor):

```yaml
format: structural-codes-verification/1
check_id: <id>
program_comparison: null   # or {not_available: "<reason no host computes this quantity>"}
cases:
  - id: HC-1
    kind: hand_check | worked_example | program_comparison | boundary
    source: {derivation: "..."}             # hand_check: which equations of the clause spec, evaluated by hand
    # worked_example: {book: {title, edition, page, example}} or {code_example: {document, edition, example}}
    # program_comparison: {program, program_version, record: <acceptance record path> | status: needs_local_test,
    #                      assumption_differences: [...]}
    subject: {kind, id}
    inputs: {<field>: <value>}
    expected:
      status: PASS
      values: {<trace name or demand | capacity | ratio>: {value, unit, abs_tol, rel_tol (optional)}}
review: null       # or {content_sha256, author, reviewer, date, boundary_tests: [...], property_tests: [...]}
```

Only numbers and citations are stored (10 §8). A hand check derived from the clause spec's own equations is labeled
`hand_check` and is not independent evidence.

#### 4.9.2 Tolerance

`compare(actual, expected, *, rel_tol, abs_tol)`: pass iff `abs(a - e) <= max(rel_tol * abs(e), abs_tol)`. `rel_tol`
defaults to `Cited(0.005, "10-structural-codes §6 default relative tolerance")`; `abs_tol` has no default and is given per
quantity in the case (10 §6). Units must match exactly (no conversion).

#### 4.9.3 Runner

`verify_check(check, cases) -> VerificationReport` evaluates each case in `trial` mode and reports `pass`, `fail` or
`pending` per case; `verify_pack(pack)` does all checks; `python -m structural_codes verify --pack P` prints the
report (AC33). `python -m structural_codes hash --pack P` prints each check's content hash (for approvals).

#### 4.9.4 Conditions for `verified` (10 §6)

All of: (1) at least one passing `worked_example` case; (2) every `program_comparison` case passes with its assumption
differences listed, or the case file states `program_comparison.not_available` with a reason; (3) at least one
`boundary` case or listed boundary test per precondition and per `NOT_APPLICABLE`/`NEEDS_ENGINEER` path;
(4) at least one listed property test; (5) a `review` block whose `content_sha256` is the current hash and whose
`reviewer` differs from `author`; (6) no failing case. The runner checks (1), (2), (5), (6) and that (3) and (4) are
listed; whether the listed tests pass is CI's job.

### 4.10 Calculation notes (10 §7, 04 §5.1)

`render_html(payload: VerdictSet, *, registry: Registry, result_id: str | None = None) -> str`: one self-contained
HTML5 document (inline CSS, no script, no external resource), `lang="en"`. Every engineering value comes from the
payload only; the registry supplies titles and clause numbers. Per trace: header (check id, title, code, clauses,
subject, state watermark), inputs table (name, value, unit, reference), constants (name, value, unit, source), steps
(name, value, unit, formula, source, uses), verdicts (status, demand, capacity, ratio, ratio limit, governing,
assumptions), messages. Numbers are shown with Python's shortest round-trip `repr` (no rounding, §11 Q8). Text is
escaped with `html.escape(quote=True)`. Output is deterministic (golden test, AC34).

Framework labels (proposed Arabic, owner review §11 Q7): Inputs المدخلات · Constants الثوابت · Calculation steps خطوات
الحساب · Verdicts النتائج · Status الحالة · Demand الطلب · Capacity المقاومة · Ratio النسبة · Clause البند ·
Source المصدر · Assumptions الافتراضات · Subject العنصر · Draft مسودة · Pass مقبول · Fail غير مقبول · Not applicable
غير منطبق · Needs engineer يحتاج إلى مهندس · Error خطأ. A check's `title_ar` is shown when present.

### 4.11 Overlays (10 §5)

`Overlay(base: str, clause_map: Mapping[str, str | None], entries: tuple[Entry, ...])`, where the map is overlay clause
→ base clause (null for an overlay-only clause) and an entry is one of:

| Entry | Fields | Result |
|---|---|---|
| `Inherited` | `base_check_id`, `clause` (overlay), `short_name` (default the base's) | A derived `Check`: base body, inputs and preconditions; `CheckMeta` with the overlay's pack, code, edition and `clauses=(clause,)`; `base` set for the hash; a trace message `"inherited from <base id>: <overlay code> <clause> mapped to <base code> <base clause>"` |
| `Overridden` | `base_check_id`, `check` | The overlay's own `Check` |
| `Added` | `check` | The overlay's own `Check`; its clause maps to null or is absent from the map |
| `Removed` | `base_check_id`, `reason` | No overlay check; lookup gives `NOT_FOUND` with the reason (AC20) |

Completeness (AC17): every base check appears in exactly one of `Inherited`, `Overridden` or `Removed`; inheritance is
never implicit. Base citations in constants are never rewritten (AC18). Approval of an inherited check needs
`inherited-confirmed` (§4.8).

### 4.12 Public evaluate API (10 §7)

```python
evaluate(check_id, inputs, *, subject, mode="trial", registry=None, source=None, current_revision=None,
         policy=InputPolicy()) -> Evaluation
evaluate_batch(check_id, items: Sequence[BatchItem], *, mode="trial", registry=None, source=None,
               current_revision=None, policy=InputPolicy()) -> Evaluation
```

`inputs` is a mapping (raw JSON form, may hold `Ref` objects) or an instance of the input model. `BatchItem(subject,
inputs)`. `registry=None` uses `Registry.discover()`. Order: look up the check (NOT_FOUND) → resolve the state and
refuse by mode (AC25) → validate every item with `validate_input` (EC §5; references need `source`, AC27) → per item:
preconditions, body, verdicts, trace → governing (AC14) → payload. `Evaluation`: `payload` (`verdicts.set/1` model),
`state`, `content_sha256`, `inputs_provenance` (per item, for the caller's envelope). The core stores nothing; the
harness stores the payload as a result (spec B-062).

## 5. Inputs and outputs

The core defines no tool. Its inputs are a check id, inputs per §4.3 and a mode; its output is a `verdicts.set/1`
payload (EC §4.10.2) and HTML notes. Inputs of each check are defined in its clause spec.

## 6. Errors

| Condition | Error | Contract code and fields |
|---|---|---|
| Unknown or removed check id | `ContractError` | `NOT_FOUND`, `field: check_id`, `hint` |
| Check not usable in the mode, or withdrawn | `CheckNotUsable` | `INVALID_ARGUMENT`, `field: check_id`, `hint` naming the state (interim, §11 Q1) |
| Input shape, policy, references, units, bounds | from `validate_input` | `INVALID_ARGUMENT`, `REF_*`, `UNIT_MISMATCH`, `OUT_OF_RANGE` (EC §5), `field` prefixed `items/<k>/` in a batch |
| References without a `source` | `ContractError` | `INVALID_ARGUMENT`, `field` |
| Gap in a check | `NotImplementedGap` → verdict | `NEEDS_ENGINEER` verdict, not an error |
| Arithmetic failure in a body | → verdict | `ERROR` verdict for that item |
| Definition mistakes (metadata, inputs, trace misuse, overlay, dynamic import) | `CheckDefinitionError` | not a `ContractError`; a programming error |
| Invalid `approvals.yaml` or case file | `ApprovalsFileError`, `VerificationDataError` | not a `ContractError` |

## 7. Non-goals

- Any engineering check or constant (packs, B-071 and B-072); worked examples from books or code examples (owner-supplied).
- `ctx.calc` integration, storing results and provenance (harness spec B-062).
- PDF notes (10 §7 names HTML and PDF; PDF needs a dependency ADR, §11 Q6); full Arabic translation of notes.
- Nested or list inputs; unit conversion of inputs (inputs arrive canonical); load-combination generation.
- An MCP front end (10 §7, by ADR later); parallel or cached evaluation; a batch size limit (the caller bounds it).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A framework bug changes every verdict (status, ratio, governing) | R1 | Exact boundary tests (AC11 to AC14), property tests, mutation ≥ 80% on R1 modules, golden notes |
| An approval survives a change to the implementation | R1 | Hash over sources, imported helpers, core, metadata, input schema (AC21); dynamic imports rejected (AC22) |
| An inherited SBC check is used as if confirmed | R1 | Completeness (AC17); `inherited-confirmed` plus base approval (AC24) |
| A gap is silently computed | R1 | `NotImplementedGap` must be declared and yields `NEEDS_ENGINEER` (AC6) |
| Verdict shape drifts from the contract | R2 | Contract tests against eng-contract models (AC15, AC26) |
| Notes leak markup or show values not in the trace | R2, R3 | Escaping and values-only-from-payload test (AC35) |
| Non-determinism (hash seed, set order) | R2 | Replay test across processes (AC7); sorted registry |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1 to AC6, AC8 to AC14, AC16 to AC25, AC27 to AC33, AC35, AC36, AC38 | Unit | `tests/unit/` |
| AC15, AC26 | Contract (against eng-contract models) | `tests/contract/` |
| AC7 | Replay (determinism across runs and processes) | `tests/replay/` |
| AC34 | Golden | `tests/golden/`, `tests/data/golden/notes/` |
| AC14, AC31 | Property (Hypothesis, CI profile `derandomize=True`) | `tests/property/` |
| AC37 | Coverage and mutation | CI `gate` job |

No fake-host workflow test applies: the core touches no host. Tests use no network, clock or randomness.

## 10. Version impact

New package `structural-codes-core` 0.1.0. Any change to verdict construction, governing, tolerance comparison or the
content-hash format is a major change of the core and resets every approval (17 §1, process/10 §5).

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | The contract has no `Precondition` for "check not approved or withdrawn"; the core uses `INVALID_ARGUMENT` | Owner | Add `check_approved` to `Precondition` in an eng-contract minor (ADR), then switch to `PRECONDITION_FAILED` |
| Q2 | Core sources are in every check's hash, so any core change resets all approvals | Owner | Keep (safe); revisit if re-approvals become a burden |
| Q3 | The gate's FB004 (I/O imports) covers block and rule modules, not check modules | Owner | Extend FB004 to `check_modules` in eng-dev-gate |
| Q4 | The gate assumes `<package>/docs/plans/` and `<package>/.gate/` per workspace member; `packages/structural-codes/` is a group folder, not a member | Owner, gate author | Let the gate treat a folder holding `.gate/agents.yml` as a repository root whose plans govern its members |
| Q5 | process/03 places clause specs at `structural-codes/packages/<pack>/specs/<check_id>.md`; this workspace uses `packages/structural-codes/docs/clause-specs/<pack>/` | Owner | Amend process/03 to the shared `docs/` folder |
| Q6 | PDF notes (10 §7) | Owner | Defer; add by package ADR when a dependency is chosen |
| Q7 | Arabic framework labels of §4.10 | Owner | Review the wording before any note leaves trial use |
| Q8 | Display precision of numbers in notes | Owner | Full round-trip values until the owner sets a rule; rounding would be an engineering decision |
| Q9 | `ratio_limit` above the contract default is refused | Owner | Keep (04 §5.1 allows only stricter limits) |
| Q10 | Capacity ≤ 0 or demand < 0 gives `ERROR`, not `NEEDS_ENGINEER` | Owner | Keep: it signals a defect in inputs or the check, not a clause scope limit |
| Q11 | Governing rule (largest ratio among `PASS`/`FAIL` per subject, first on a tie) | Owner | Accept |
| Q12 | PyYAML as a runtime dependency (package ADR-0001, Proposed) | Owner | Approve (MIT, `safe_load` only) |
| Q13 | 10 §6 default tolerance 0.5% comes from a `Proposed` document | Owner | Accept with 10; until then it is the documented default |
| G-1 | No worked examples from books or code examples exist here for any check; every case in this build is a labeled hand check | Owner | Owner supplies book, edition, page and example per check (pack specs list them) |
