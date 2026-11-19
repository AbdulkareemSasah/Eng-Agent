---
id: plan-b070-structural-codes-core
issue: "B-070"
spec: packages/structural-codes/docs/specs/0001-core-framework.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2, r3]       # binding for every pull request of this plan; r3 from T1 (pyproject.toml, uv.lock, .gate/)
tasks:
  - id: T1
    title: Core package skeleton, shared folder files, dependency ADR, workspace member
    files:
      - "pyproject.toml"
      - "uv.lock"
      - "packages/structural-codes/AGENTS.md"
      - "packages/structural-codes/CLAUDE.md"
      - "packages/structural-codes/.gate/agents.yml"
      - "packages/structural-codes/.gate/risk-map.yml"
      - "packages/structural-codes/docs/local-testing.md"
      - "packages/structural-codes/docs/adr/0001-core-runtime-dependencies.md"
      - "packages/structural-codes/core/pyproject.toml"
      - "packages/structural-codes/core/README.md"
      - "packages/structural-codes/core/CHANGELOG.md"
      - "packages/structural-codes/core/src/structural_codes/__init__.py"
      - "packages/structural-codes/core/src/structural_codes/py.typed"
      - "packages/structural-codes/core/tests/unit/test_package.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first: ["packages/structural-codes/core/tests/unit/test_package.py::test_version_constant"]
    covers: []
    depends_on: []
  - id: T2
    title: Errors, check metadata and the check_id rule
    files:
      - "packages/structural-codes/core/src/structural_codes/errors.py"
      - "packages/structural-codes/core/src/structural_codes/meta.py"
      - "packages/structural-codes/core/tests/unit/test_meta.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_meta.py::test_check_id_rule"
      - "packages/structural-codes/core/tests/unit/test_meta.py::test_metadata_fields"
    covers: [AC1, AC2]
    depends_on: [T1]
  - id: T3
    title: Check inputs, bounded helper and preconditions
    files:
      - "packages/structural-codes/core/src/structural_codes/inputs.py"
      - "packages/structural-codes/core/src/structural_codes/applicability.py"
      - "packages/structural-codes/core/tests/unit/test_inputs.py"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_inputs.py::test_definition_rules"
      - "packages/structural-codes/core/tests/unit/test_inputs.py::test_bounded_helper_and_out_of_range"
      - "packages/structural-codes/core/tests/unit/test_inputs.py::test_unbounded_helper"
    covers: [AC3, AC4, AC4a]
    depends_on: [T2]
  - id: T4
    title: Trace recorder
    files:
      - "packages/structural-codes/core/src/structural_codes/trace.py"
      - "packages/structural-codes/core/tests/unit/test_trace.py"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_trace.py::test_recording_rules"
      - "packages/structural-codes/core/tests/unit/test_trace.py::test_inputs_and_contract_shape"
      - "packages/structural-codes/core/tests/unit/test_trace.py::test_step_units"
      - "packages/structural-codes/core/tests/unit/test_trace.py::test_unbounded_reason_message"
    covers: [AC4b, AC8, AC9, AC10]
    depends_on: [T3]
  - id: T5
    title: Verdict builder and governing selection
    files:
      - "packages/structural-codes/core/src/structural_codes/_verdict.py"
      - "packages/structural-codes/core/src/structural_codes/trace.py"
      - "packages/structural-codes/core/tests/unit/test_verdict.py"
      - "packages/structural-codes/core/tests/property/test_governing_props.py"
      - "packages/structural-codes/core/tests/contract/test_verdict_shape.py"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_verdict.py::test_status_from_ratio"
      - "packages/structural-codes/core/tests/unit/test_verdict.py::test_invalid_capacity_gives_error"
      - "packages/structural-codes/core/tests/unit/test_verdict.py::test_ratio_limit"
      - "packages/structural-codes/core/tests/unit/test_verdict.py::test_governing_selection"
      - "packages/structural-codes/core/tests/property/test_governing_props.py::test_one_governing_per_subject"
      - "packages/structural-codes/core/tests/contract/test_verdict_shape.py::test_verdict_fields"
    covers: [AC11, AC12, AC13, AC14, AC15]
    depends_on: [T4]
  - id: T6
    title: Check decorator, packs and registry
    files:
      - "packages/structural-codes/core/src/structural_codes/check.py"
      - "packages/structural-codes/core/src/structural_codes/pack.py"
      - "packages/structural-codes/core/tests/unit/test_registry.py"
      - "packages/structural-codes/core/tests/unit/test_check.py"
      - "packages/structural-codes/core/tests/fixtures/synthbase/**"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_registry.py::test_discovery_and_lookup"
      - "packages/structural-codes/core/tests/unit/test_check.py::test_applicability_declared"
    covers: [AC5b, AC16]
    depends_on: [T5]
  - id: T7
    title: Content hash over sources, imported helpers, metadata and inputs
    files:
      - "packages/structural-codes/core/src/structural_codes/content_hash.py"
      - "packages/structural-codes/core/src/structural_codes/_closure.py"
      - "packages/structural-codes/core/tests/unit/test_content_hash.py"
      - "packages/structural-codes/core/tests/fixtures/hashpack/**"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_content_hash.py::test_hash_inputs"
      - "packages/structural-codes/core/tests/unit/test_content_hash.py::test_dynamic_import_rejected"
      - "packages/structural-codes/core/tests/unit/test_content_hash.py::test_closure_within_check_modules"
    covers: [AC21, AC22, AC22a]
    depends_on: [T6]
  - id: T8
    title: Runner, evaluate and evaluate_batch
    files:
      - "packages/structural-codes/core/src/structural_codes/_runner.py"
      - "packages/structural-codes/core/src/structural_codes/__init__.py"
      - "packages/structural-codes/core/tests/unit/test_applicability.py"
      - "packages/structural-codes/core/tests/unit/test_runner.py"
      - "packages/structural-codes/core/tests/contract/test_verdict_set.py"
      - "packages/structural-codes/core/tests/replay/test_determinism.py"
      - "packages/structural-codes/core/tests/fixtures/synthbase/**"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_applicability.py::test_outcomes_and_order"
      - "packages/structural-codes/core/tests/unit/test_applicability.py::test_member_scope_first"
      - "packages/structural-codes/core/tests/unit/test_runner.py::test_not_implemented_gap"
      - "packages/structural-codes/core/tests/unit/test_runner.py::test_references"
      - "packages/structural-codes/core/tests/unit/test_runner.py::test_batch"
      - "packages/structural-codes/core/tests/unit/test_runner.py::test_no_verdict"
      - "packages/structural-codes/core/tests/contract/test_verdict_set.py::test_evaluate_payload"
      - "packages/structural-codes/core/tests/replay/test_determinism.py::test_identical_across_runs_and_hash_seeds"
    covers: [AC5, AC5a, AC6, AC7, AC26, AC27, AC28, AC29]
    depends_on: [T7]
  - id: T9
    title: Verification case files, tolerance and verification runner
    files:
      - "packages/structural-codes/core/src/structural_codes/verification.py"
      - "packages/structural-codes/core/src/structural_codes/_yaml.py"
      - "packages/structural-codes/core/tests/unit/test_verification.py"
      - "packages/structural-codes/core/tests/property/test_tolerance_props.py"
      - "packages/structural-codes/core/tests/data/verification/**"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_verification.py::test_case_file_schema"
      - "packages/structural-codes/core/tests/unit/test_verification.py::test_tolerance"
      - "packages/structural-codes/core/tests/unit/test_verification.py::test_report_and_requirements"
      - "packages/structural-codes/core/tests/property/test_tolerance_props.py::test_symmetric_and_monotone"
    covers: [AC30, AC31, AC32]
    depends_on: [T8]
  - id: T10
    title: Overlay mechanism (inherited, overridden, added, removed)
    files:
      - "packages/structural-codes/core/src/structural_codes/overlay.py"
      - "packages/structural-codes/core/src/structural_codes/pack.py"
      - "packages/structural-codes/core/src/structural_codes/content_hash.py"
      - "packages/structural-codes/core/tests/unit/test_overlay.py"
      - "packages/structural-codes/core/tests/fixtures/synthover/**"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_overlay.py::test_completeness"
      - "packages/structural-codes/core/tests/unit/test_overlay.py::test_inherited_evaluation"
      - "packages/structural-codes/core/tests/unit/test_overlay.py::test_overridden_added_and_clause_map"
      - "packages/structural-codes/core/tests/unit/test_overlay.py::test_removed"
    covers: [AC17, AC18, AC19, AC20]
    depends_on: [T8]
  - id: T11
    title: Lifecycle, approvals.yaml and mode usability
    files:
      - "packages/structural-codes/core/src/structural_codes/lifecycle.py"
      - "packages/structural-codes/core/src/structural_codes/_runner.py"
      - "packages/structural-codes/core/tests/unit/test_lifecycle.py"
      - "packages/structural-codes/core/tests/data/approvals/**"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_lifecycle.py::test_approvals_file"
      - "packages/structural-codes/core/tests/unit/test_lifecycle.py::test_state_resolution"
      - "packages/structural-codes/core/tests/unit/test_lifecycle.py::test_mode_usability"
      - "packages/structural-codes/core/tests/unit/test_lifecycle.py::test_installed_layout"
    covers: [AC23, AC24, AC24a, AC25]
    depends_on: [T9, T10]
  - id: T12
    title: Command line (verify and hash)
    # Amendment (B-419, documents only): `--pack P` is the pack project root (spec 4.9.3); an overlay pack's check set includes its inherited checks (verify_check per check, not verify_pack); test_cli.py builds its pack roots in tmp_path, so no fixture file is committed.
    files:
      - "packages/structural-codes/core/src/structural_codes/__main__.py"
      - "packages/structural-codes/core/src/structural_codes/_cli.py"
      - "packages/structural-codes/core/tests/unit/test_cli.py"
    max_changed_lines: 150
    max_sessions: 2
    tests_first: ["packages/structural-codes/core/tests/unit/test_cli.py::test_verify_exit_codes"]
    covers: [AC33]
    depends_on: [T11]
  - id: T13
    title: Calculation-note renderer (HTML, English with Arabic labels)
    files:
      - "packages/structural-codes/core/src/structural_codes/notes.py"
      - "packages/structural-codes/core/src/structural_codes/_labels.py"
      - "packages/structural-codes/core/tests/golden/test_notes_golden.py"
      - "packages/structural-codes/core/tests/unit/test_notes.py"
      - "packages/structural-codes/core/tests/data/golden/notes/**"
    # Amendment (B-385, documents only): the golden test was tests/golden/test_notes.py, the same basename as the unit
    # test; the core tests have no __init__.py, so pytest stopped with an import file mismatch and mypy with a duplicate
    # module (B-267). The golden test is renamed; no test package marker is added.
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/core/tests/golden/test_notes_golden.py::test_golden"
      - "packages/structural-codes/core/tests/unit/test_notes.py::test_escaping_watermark_and_values"
    covers: [AC34, AC35]
    depends_on: [T8]
  - id: T14a
    title: Public API declaration of the public modules that exist (packs import them)
    # Amendment (B-381): the ACI pack's T2 (PR 188) failed the gate's import check (IM002) because no core module was in
    # public_modules yet; T14 declares them only after T12 and T13. T14a declares the section 4.1 modules that exist after
    # T10 (structural_codes, errors, meta, inputs, applicability, trace, check, pack, overlay, content_hash,
    # verification); T14 adds lifecycle and notes whenever T11 and T13 land; the T14a test is one-directional. Pack tasks wait for T14a (the registry orders them across plans).
    files:
      - "packages/structural-codes/core/pyproject.toml"
      - "packages/structural-codes/core/CHANGELOG.md"
      - "packages/structural-codes/core/tests/unit/test_package.py"
    max_changed_lines: 40
    max_sessions: 1
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_package.py::test_public_modules_declared"
    covers: [AC38]
    depends_on: [T10]
  - id: T14b
    title: Declare structural_codes.lifecycle public (pack tests import it)
    # Amendment (B-419, documents only): new task; the packs' test_all_draft tests import structural_codes.lifecycle (IM002) before T14 can land.
    files:
      - "packages/structural-codes/core/pyproject.toml"
      - "packages/structural-codes/core/CHANGELOG.md"
      - "packages/structural-codes/core/tests/unit/test_package.py"
    max_changed_lines: 20
    max_sessions: 1
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_package.py::test_lifecycle_declared"
    covers: [AC38]
    depends_on: [T11]
  - id: T14
    title: Public API declaration, package-level checks, README usage
    # Amendment (B-419, documents only): adds __init__.py (completes __all__); test_no_engineering_constants leaves tests_first (passes at the base); depends on T14b.
    files:
      - "packages/structural-codes/core/pyproject.toml"
      - "packages/structural-codes/core/README.md"
      - "packages/structural-codes/core/CHANGELOG.md"
      - "packages/structural-codes/core/src/structural_codes/__init__.py"
      - "packages/structural-codes/core/tests/unit/test_package.py"
    max_changed_lines: 120
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_package.py::test_public_modules"
      - "packages/structural-codes/core/tests/unit/test_package.py::test_version_constant"
    covers: [AC36, AC37, AC38]
    depends_on: [T12, T13, T14a, T14b]
  - id: T15
    title: CheckMeta.version
    # Amendment (B-442, documents only): new task; eng-harness spec 0010 Q20 and spec 0013 Q13 need a check's integer CalcInfo.version.
    files:
      - "packages/structural-codes/core/src/structural_codes/meta.py"
      - "packages/structural-codes/core/tests/unit/test_meta.py"
      - "packages/structural-codes/core/CHANGELOG.md"
    max_changed_lines: 60
    max_sessions: 1
    tests_first:
      - "packages/structural-codes/core/tests/unit/test_meta.py::test_check_version"
    covers: [AC2a]
    depends_on: [T14b]
---

# Implementation plan: structural-codes core framework

Spec: [0001-core-framework.md](../specs/0001-core-framework.md) (draft). File paths in the front matter are relative
to the workspace root (not to `packages/eng-harness/`); `max_changed_lines` counts non-test, non-generated lines
([process/04](../../../../design/process/04-implementation-rules.md) §4).

## 1. Approach

The core is built bottom-up in the order its own imports require: errors and metadata, inputs and preconditions, the
trace recorder, then the verdict builder (the code that decides `PASS` and `FAIL`, so it is built and mutation-tested
before anything uses it), checks and the registry, the content hash, the runner, verification, overlays, the lifecycle
(which needs both verification and overlays), the command line, and the note renderer. Every task is test-first: its
first commit is `test:` with the tests named in `tests_first`, failing on `build/v1`
([process/05](../../../../design/process/05-testing-and-verification.md) §9).

No engineering content enters this plan. Test fixtures are synthetic packs (`synthbase`, `synthover`, `hashpack`)
whose constants cite `"synthetic test fixture, no engineering meaning"`; no fixture resembles a real clause.

Start condition: the eng-contract modules this package imports (`params`, `cited`, `quantity`, `verdicts`, `trace`,
`kinds.verdicts`, `canonical`, `errors`, `refs`) are merged (B-010 to B-025), and phase 2 code may start (lead
decision D-9). T1 needs neither and may start once this plan is merged.

## 2. Tasks

**T1 Skeleton (core only).** Creates `packages/structural-codes/core/` as a uv workspace member: `pyproject.toml` with
`name = "structural-codes-core"`, `version = "0.1.0.dev0"`, `requires-python = ">=3.14,<3.15"`
([ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §5), dependencies `eng-contract`
(workspace source), `pydantic`, `pyyaml`; the uv build backend; the tool configuration of
[process/11](../../../../design/process/11-repository-standard.md) §3; and `[tool.eng-gate]` with `profile = "codes"`,
`layer = 3`, `import_names = ["structural_codes"]`, `coverage_line = 95`, `coverage_branch = 90`, `mutation_min = 80`,
`r1_modules` as in spec §4.1, and no `check_modules` (the core defines no check). It adds
`"packages/structural-codes/core"` to the root `[tool.uv.workspace] members` (D-10) and updates `uv.lock`. It creates
the shared folder files: `AGENTS.md` and `CLAUDE.md` (rendered from `.gate/agents.yml` with the hub template; one file
for the three packages), `.gate/risk-map.yml` (core R1 modules as `r1`, the rest of `core/src/**` as `r2`),
`docs/local-testing.md` (the core needs no host: "none"), and `docs/adr/0001-core-runtime-dependencies.md`
(`Proposed`: PyYAML, spec §11 Q12). Why core only: the two pack skeletons need decisions that belong to their own
specs (B-071, B-072): their `check_modules`, `r1_modules`, entry points and package data; an empty pack would carry
gate configuration for checks that do not exist yet. Each pack plan's T1 adds its own member (D-10).

**T2 Errors and metadata.** `errors.py` (the six exceptions of spec §4.1; `CheckNotUsable` is a `ContractError` with
`INVALID_ARGUMENT`), `meta.py` (`CheckMeta`, `GapDecl`, `clause_token`). First because every later module raises these.

**T3 Inputs and preconditions.** `CheckInputs`, `bounded`, the reserved `ratio_limit`; `Precondition` and `Outcome`.
Out-of-range behavior is tested through `eng_contract.params.validate_input`, not re-implemented.

**T4 Trace recorder.** `TraceRecorder` with the rules of spec §4.5 and conversion to the contract's `Trace`; the content
hash is passed in as a value (T7 computes it), so the recorder has no dependency on hashing.

**T5 Verdict builder.** `t.verdict(...)`, the ratio step, status, `ERROR` paths and the governing rule; R1 module,
reviewed with the source-check lens. Exact boundary tests at `ratio == limit` and the next float above.

**T6 Checks and registry.** `@check`, `Check`, `Pack`, `Registry.discover()` (entry points, sorted) and `Registry.of()`.
`@check` enforces the applicability declaration (non-empty preconditions or `unconditional`, spec §4.4). The
`synthbase` fixture pack starts here.

**T7 Content hash.** The static import closure (`_closure.py`, AST only, no import side effects) and the hash document
of spec §4.7 (closure over the pack, `structural_codes` and `eng_contract`), and `lint_scope_violations` (spec §4.5).
Fixtures are copied into a temporary folder so tests can change single bytes.

**T8 Runner.** `evaluate`, `evaluate_batch`, validation through `validate_input`, the member-scope step, preconditions,
gaps, error isolation per item, governing, the `verdicts.set/1` payload. Until T11, the runner treats every check as
`draft` in `trial` mode and refuses `production` (the safe default). The replay test runs two subprocesses through
`sys.executable`.

**T9 Verification.** Case-file models, `compare`, `verify_check` and `verify_pack`, the report and the requirement list
of spec §4.9.4. YAML loading uses `yaml.safe_load` only (`_yaml.py`), with duplicate keys rejected.

**T10 Overlays.** `Overlay` and its entries, completeness, clause-map rules, derived inherited checks and their hash
(adds the `base` member to the hash document). Can run in parallel with T9 (disjoint files) once T8 is merged.

**T11 Lifecycle.** `approvals.yaml` model, the runtime `resolve_state` (approvals and hash only, no case files; spec
§4.8), mode usability wired into the runner (replacing T8's default). Tests use temporary approvals files and an
installed-layout copy of `synthbase` (its `src/` package and `approvals.yaml` only); no shipped `approvals.yaml` has
entries.

**T12 Command line.** `python -m structural_codes verify --pack P` and `hash --pack P`; exit codes 0, 1, 2; `verify`
also reads the pack's `check_modules` with `tomllib` and exits 2 on a lint-scope violation; output to an injected stream
(no `print`, FB007). Amendment B-419: `P` is the filesystem path of a pack project root (the folder holding its
`pyproject.toml`), resolved as spec §4.9.3 states: the single entry-point name under
`[project.entry-points."structural_codes.packs"]` and `[tool.eng-gate] check_modules` are read from that
`pyproject.toml`, the `Pack` of that name is taken from `Registry.discover().packs`, and `verify` calls
`verify_pack(pack, P / "tests/data/golden/verification")` for a pack without an overlay. For an overlay pack (review of
#234) the check set is every discovered check whose `meta.pack` is the pack's name, which includes the inherited checks
the registry derives; `verify` calls `verify_check(check, CaseFile.load(...), registry=registry)` with the discovered
registry for each of them (a missing case file gives `verify_pack`'s not-verified report), because `verify_pack` builds
`Registry.of([pack])`, which rejects an overlay without its base, and loops over `pack.checks` only; `hash` prints the
content hash of that same check set, and the lint-scope check covers `pack.checks`. The output lines and every exit-2 case (resolution errors,
`CheckDefinitionError`, `VerificationDataError`, lint-scope violations, argparse usage errors; `hash` exits 0 or 2 and
skips the lint-scope check) are those of spec §4.9.3. `tests/unit/test_cli.py` builds each pack root in pytest's
`tmp_path` at run time (a `pyproject.toml` with the entry point and `check_modules`, and the case YAML under
`tests/data/golden/verification/`), points `sys.path` at `tests/fixtures/synthbase/src` and monkeypatches the entry
points as `tests/unit/test_registry.py` does; it builds one root each for exit 0, exit 1 (a failing case) and exit 2 (a
lint-scope violation, bad case data, an unknown pack), and one overlay root on `tests/fixtures/synthover/src` (with
`synthbase` also registered) for `test_overlay_includes_inherited`, which expects the inherited check
`synthover.s4_1.two_pre` in both the `verify` report and the `hash` output, and exit 0. No fixture file is committed, so
the task stays inside its three files. The 150-line budget covers `_cli.py` and `__main__.py` only (argument parsing,
the `pyproject.toml` resolution, the check-set selection with its overlay branch of a few lines, two commands and their
output); the test lines do not count, so 150 lines remain enough.

**T13 Notes.** `render_html` and the label table; golden file committed under `tests/data/golden/notes/` (a protected
test oracle; the owner reviews it). Can run in parallel with T9 to T12 once T8 is merged.

**T14a Public API, early.** `public_modules` in `[tool.eng-gate]` lists the modules of §4.1 that exist after T10, so the
packs can import them (gate import check IM002). The test checks one direction only: the 11 named modules are declared, and
every declared module exists in `src/` and is a §4.1 module. It does not require every §4.1 module in `src/` to be declared,
so T11 (`lifecycle`) and T13 (`notes`) may merge before or after T14a without breaking it; they never touch
`pyproject.toml`. T14b declares `lifecycle`; T14 declares `notes` and owns the full-equality check (`test_public_modules`).

**T14b Lifecycle public (amendment B-419).** Adds `structural_codes.lifecycle` to `public_modules` with a changelog line,
so the packs' `tests/unit/test_pack.py::test_all_draft` (plans 0002 and 0003) and
`tests/unit/test_pack_columns.py::test_all_draft` (plan 0004) can import `State` and `resolve_state` without failing
the gate's import check (IM002, which reads `tests/` as well as `src/`). Its first commit adds
`test_package.py::test_lifecycle_declared`, which asserts `structural_codes.lifecycle` is in `public_modules` and fails
until the implementation commit declares it; `test_public_modules_declared` (T14a) keeps passing, because `lifecycle`
exists in `src/` after T11. It does not touch T11's files.

**T14 Package-level.** Adds `structural_codes.notes` (T13) to `public_modules` (`structural_codes.lifecycle` comes with
T14b), the package-level tests, README usage of `structural_codes.evaluate`, and a changelog entry under an
"Unreleased / 0.1.0" heading. Amendment B-419: T14 also sets `__all__` in `structural_codes/__init__.py` to the §4.1
names in sorted order (`["BatchItem", "Evaluation", "Mode", "__version__", "evaluate", "evaluate_batch"]`), replaces the
explicit-alias imports and the B-262 comment with plain imports, and rewrites `test_version_constant` to assert that
`__all__`. T14 does not change the version: `__version__` and the `pyproject.toml` version stay `0.1.0.dev0`, because
the release bump belongs to the release lane. Test order: the first commit holds `test_public_modules` (full equality,
fails while `notes` is undeclared) and the rewritten `test_version_constant` (fails while `__all__` is
`["__version__"]`); `test_no_engineering_constants` (AC36) comes in a later commit of the same task as a regression
guard, because the core source already meets AC36 and the test would pass at the base (test-first rule TF004).

**T15 `CheckMeta.version` (amendment B-442).** Adds `version: int = 1` (≥ 1) to `CheckMeta` (spec §4.2) with a
changelog line. Its first commit adds `test_meta.py::test_check_version`: the default is 1 and a version of 0 or less
is refused with `CheckDefinitionError` (AC2a).

## 3. Dependencies

- Runtime: `eng-contract` (workspace), `pydantic` (imported directly, IM006), `pyyaml` (package ADR-0001, `Proposed`,
  owner queue). No other runtime dependency.
- Development: the root dependency group (`ruff`, `mypy`, `pytest`, `pytest-cov`, `hypothesis`); `types-PyYAML` for
  `mypy --strict` (T1, justified in its pull request); the mutation tool chosen by `eng-dev-gate`.
- Workspace: eng-contract tasks B-010 to B-025 before T2 (see §1); eng-dev-gate `[tool.eng-gate]` keys and
  `agents render` before T1 if available, otherwise T1 writes the table as specified and renders `AGENTS.md` by hand from
  the template, to be checked once the gate exists.
- External amendments of this plan's files by tasks of other plans (amendment B-579, from the B-326 findings): plan 0003
  T2 ("Clause map module (footing rows), row validation and overlay builder with the unconfirmed gap check"; spec 0001
  AC18, spec 0003 AC8) amends `packages/structural-codes/core/src/structural_codes/_runner.py` and
  `packages/structural-codes/core/tests/unit/test_overlay.py` so that for inherited body verdicts, the runner validates
  explicit draft clauses against the base check metadata, then emits the inherited check's mapped clause, code and check
  id, and preserves the base trace citations.

## 4. Verification

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` exists; until then `uv run ruff format --check`,
  `uv run ruff check`, `uv run mypy --strict src tests` and `uv run pytest` with coverage, from
  `packages/structural-codes/core/`. The pull request links its CI run.
- No host program is involved; no live acceptance is needed for the core. Program comparisons belong to the pack plans.
- Review: each pull request is reviewed by a subagent that did not write it (correctness, Python, type design, silent
  failures, tests); T5, T7, T10 and T11 also with the R1 source-check lens; T13 with the security lens (HTML
  escaping). The owner's R1 approvals are `awaiting owner` in bootstrap mode (ADR-0028 §4).

## 5. Rollback

Each task is one squash-merged pull request on `build/v1` with no consumer until the pack plans start; reverting a
task's commit removes it (with its dependants). After a pack uses the core, a defect is fixed forward with a regression
test; a change to verdict construction or the hash format is a major version of the core and resets approvals
([process/10](../../../../design/process/10-engineering-verification.md) §5 and §7).
