---
id: plan-b062-calcs
issue: "B-062"
spec: packages/eng-harness/docs/specs/0003-calcs.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2, r3]       # binding for every pull request of this plan; r3 because T3 touches pyproject.toml and uv.lock
tasks:
  - id: T1
    title: Calc decorator, registry, inputs, input metadata, trace builder, statuses and harness codes
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/.gate/risk-map.yml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/calc.py"
      - "packages/eng-harness/src/eng_harness/errors.py"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/tests/unit/calcs/__init__.py"
      - "packages/eng-harness/tests/unit/calcs/test_registry.py"
      - "packages/eng-harness/tests/unit/calcs/test_framework.py"
      - "packages/eng-harness/tests/data/calcs/**"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/calcs/test_registry.py::test_registration_rules"
      - "packages/eng-harness/tests/unit/calcs/test_framework.py::test_trace_records_inputs_and_rules"
    covers: [AC1, AC5]
    depends_on: []
  - id: T2
    title: Content hash over the static import closure and the calc lock file
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/.gate/risk-map.yml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/_calc/__init__.py"
      - "packages/eng-harness/src/eng_harness/_calc/_hash.py"
      - "packages/eng-harness/src/eng_harness/calc.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/unit/calcs/test_hash.py"
      - "packages/eng-harness/tests/unit/calcs/test_registry.py"
      - "packages/eng-harness/tests/contract/test_calc_lock.py"
      - "packages/eng-harness/tests/data/calcs/**"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/calcs/test_hash.py::test_hash_covers_helpers_and_metadata"
      - "packages/eng-harness/tests/unit/calcs/test_hash.py::test_unhashable_calc_refused"
      - "packages/eng-harness/tests/unit/calcs/test_registry.py::test_removed_id_not_reused"
      - "packages/eng-harness/tests/contract/test_calc_lock.py::test_lock_matches_registry"
    covers: [AC2, AC6, AC7]
    depends_on: [T1]
  - id: T3
    title: approvals.yaml schema, loader, status resolution and the YAML parser ADR
    files:
      - "pyproject.toml"
      - "uv.lock"
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/adr/*-yaml-parser.md"
      - "packages/eng-harness/src/eng_harness/_calc/_approvals.py"
      - "packages/eng-harness/src/eng_harness/calcs/approvals.yaml"
      - "packages/eng-harness/tests/unit/calcs/test_approvals.py"
      - "packages/eng-harness/tests/contract/test_calc_lock.py"
      - "packages/eng-harness/tests/data/calcs/**"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/calcs/test_approvals.py::test_status_resolution"
      - "packages/eng-harness/tests/unit/calcs/test_approvals.py::test_file_validation"
      - "packages/eng-harness/tests/contract/test_calc_lock.py::test_shipped_calcs_are_draft"
    covers: [AC8, AC9, AC10]
    depends_on: [T2]
  - id: T4
    title: Calc kinds part 1 (CalcMeta, model fingerprint and diff payloads, expected effects) and their registration
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/.gate/risk-map.yml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/kinds/__init__.py"
      - "packages/eng-harness/src/eng_harness/kinds/calcs.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/contract/test_calc_kinds.py"
      - "packages/eng-harness/tests/data/kinds/calcs/**"
    max_changed_lines: 380
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_calc_kinds.py::test_fixtures"
    covers: [AC47]
    depends_on: [T1]
  - id: T4b
    title: Calc kinds part 2 (design summary, section size, placement comparison, readback check payloads)
    # Split (B-379): the B-143 writer measured 531 changed non-test lines for the former T4 (kinds/calcs.py 520), above
    # the 400-line task cap; the four report payloads move here.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/kinds/calcs.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/contract/test_calc_kinds.py"
      - "packages/eng-harness/tests/data/kinds/calcs/**"
    max_changed_lines: 340
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_calc_kinds.py::test_report_fixtures"
    covers: [AC47]
    depends_on: [T4]
  - id: T5
    title: HarnessCalcPort (describe, run, preflight, run class, limits, storage) and the calc step workflow test
    # Amendment (B-416, documents only): engine plan T10 (and so T9) is merged before this task; see section 3.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/_calc/_port.py"
      - "packages/eng-harness/src/eng_harness/_calc/__init__.py"
      - "packages/eng-harness/tests/unit/calcs/test_port.py"
      - "packages/eng-harness/tests/unit/calcs/test_framework.py"
      - "packages/eng-harness/tests/workflow/test_calc_step.py"
      - "packages/eng-harness/tests/workflows/calc_test_blocks.py"
      - "packages/eng-harness/tests/data/calcs/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/calcs/test_port.py::test_describe"
      - "packages/eng-harness/tests/unit/calcs/test_port.py::test_input_validation_codes"
      - "packages/eng-harness/tests/unit/calcs/test_port.py::test_item_limit"
      - "packages/eng-harness/tests/unit/calcs/test_port.py::test_result_record"
      - "packages/eng-harness/tests/unit/calcs/test_port.py::test_production_and_withdrawn_refusal"
      - "packages/eng-harness/tests/unit/calcs/test_port.py::test_draft_marking"
      - "packages/eng-harness/tests/unit/calcs/test_port.py::test_not_implemented_gap"
      - "packages/eng-harness/tests/unit/calcs/test_framework.py::test_deterministic_across_processes"
      - "packages/eng-harness/tests/workflow/test_calc_step.py::test_calc_step_end_to_end"
    covers: [AC4, AC11, AC12, AC13, AC14, AC15, AC16, AC17, AC18]
    depends_on: [T3, T4b]
  - id: T6
    title: Calc-module rules test, golden data loader and golden file lint, verification record template
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/tests/rules/test_calc_modules.py"
      - "packages/eng-harness/tests/golden/__init__.py"
      - "packages/eng-harness/tests/golden/_golden.py"
      - "packages/eng-harness/tests/golden/test_golden_files.py"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py"
      - "packages/eng-harness/tests/data/golden/calcs/README.md"
      - "packages/eng-harness/docs/verification/calcs/README.md"
    max_changed_lines: 120
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/rules/test_calc_modules.py::test_calc_module_rules"
      - "packages/eng-harness/tests/golden/test_golden_files.py::test_sources_present"
    covers: [AC3, AC46]
    depends_on: [T1]
  - id: T7
    title: Calc 1, model fingerprint, with the canonical-state helper
    # Amendment (B-437, documents only): rules test, lock test, calc.py re-export (spec 4.3, 9); budget 250 -> 270.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.model_fingerprint (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/docs/verification/calcs/harness.model_fingerprint.md"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/_state.py"
      - "packages/eng-harness/src/eng_harness/calcs/model_fingerprint.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/unit/calcs/test_fingerprint.py"
      - "packages/eng-harness/tests/property/test_fingerprint.py"
      - "packages/eng-harness/tests/data/golden/calcs/fingerprint-*.json"
      - "packages/eng-harness/tests/rules/test_calc_modules.py"
      - "packages/eng-harness/tests/contract/test_calc_lock.py"
      - "packages/eng-harness/src/eng_harness/calc.py"  # re-export of read_lock and removed_ids (spec 4.3)
    max_changed_lines: 270
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/property/test_fingerprint.py::test_order_independent"
      - "packages/eng-harness/tests/property/test_fingerprint.py::test_any_change_changes_fingerprint"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[fingerprint-point-order]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[fingerprint-moved-column]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[fingerprint-canonical-bytes]"
      - "packages/eng-harness/tests/unit/calcs/test_fingerprint.py::test_incomplete_read"
      - "packages/eng-harness/tests/unit/calcs/test_fingerprint.py::test_mixed_models_refused"
    covers: [AC19, AC20, AC21, AC22, AC23]
    depends_on: [T5, T6]
  - id: T8
    title: Calc 2, difference report, with the tolerance-comparison helper
    # Amendment (B-416, documents only): engine plan T12 is merged before this task (section 3); adds T5's test block file.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.model_diff (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.model_diff.md"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/_compare.py"
      - "packages/eng-harness/src/eng_harness/calcs/_state.py"
      - "packages/eng-harness/src/eng_harness/calcs/model_diff.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/unit/calcs/test_diff.py"
      - "packages/eng-harness/tests/property/test_diff.py"
      - "packages/eng-harness/tests/workflow/test_calc_step.py"
      - "packages/eng-harness/tests/workflows/calc_test_blocks.py"
      - "packages/eng-harness/tests/contract/test_calc_lock.py"
      - "packages/eng-harness/tests/data/calcs/stale_ok.json"
      - "packages/eng-harness/tests/data/golden/calcs/diff-*.json"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[diff-section-changed]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[diff-boundary]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[diff-angle-full-turn]"
      - "packages/eng-harness/tests/property/test_diff.py::test_boundary_exact"
      - "packages/eng-harness/tests/property/test_diff.py::test_identity_and_symmetry"
      - "packages/eng-harness/tests/unit/calcs/test_diff.py::test_basis_tolerances_required"
      - "packages/eng-harness/tests/unit/calcs/test_diff.py::test_not_compared_and_ambiguous"
      - "packages/eng-harness/tests/workflow/test_calc_step.py::test_older_revision_inputs"
      - "packages/eng-harness/tests/contract/test_calc_lock.py::test_stale_ok_fields_match_spec"
    covers: [AC24, AC25, AC26, AC27, AC28, AC29, AC48, AC49]
    depends_on: [T7]
  - id: T9
    title: Calc 3, read-back check
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.readback_check (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/docs/verification/calcs/harness.readback_check.md"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/readback_check.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/unit/calcs/test_readback.py"
      - "packages/eng-harness/tests/data/calcs/stale_ok.json"
      - "packages/eng-harness/tests/data/golden/calcs/readback-*.json"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[readback-pass]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[readback-mismatch]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[readback-unexpected]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[readback-unit-scale]"
      - "packages/eng-harness/tests/unit/calcs/test_readback.py::test_not_read"
      - "packages/eng-harness/tests/unit/calcs/test_readback.py::test_circular_inputs_refused"
    covers: [AC30, AC31, AC32, AC33, AC34]
    depends_on: [T8]
  - id: T10
    title: Calc 4, design results summary
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.design_summary (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/docs/verification/calcs/harness.design_summary.md"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/design_summary.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/unit/calcs/test_summary.py"
      - "packages/eng-harness/tests/data/calcs/stale_ok.json"
      - "packages/eng-harness/tests/data/golden/calcs/summary-*.json"
    max_changed_lines: 280
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[summary-basic]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[summary-not-designed]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[summary-previous]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[summary-member-worst]"
      - "packages/eng-harness/tests/unit/calcs/test_summary.py::test_empty"
    covers: [AC35, AC36, AC37, AC38, AC50]
    depends_on: [T9]
  - id: T11
    title: Calc 5, section size rounding
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.section_round (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.section_round.md"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/section_round.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/unit/calcs/test_rounding.py"
      - "packages/eng-harness/tests/property/test_rounding.py"
      - "packages/eng-harness/tests/data/calcs/stale_ok.json"
      - "packages/eng-harness/tests/data/golden/calcs/round-*.json"
    max_changed_lines: 150
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[round-up]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[round-exact]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[round-just-above]"
      - "packages/eng-harness/tests/unit/calcs/test_rounding.py::test_edge_cases"
      - "packages/eng-harness/tests/property/test_rounding.py::test_rounding_properties"
    covers: [AC39, AC40, AC41]
    depends_on: [T10]
  - id: T12
    title: Calc 6, element count and position comparison
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.calcs, eng_harness.calcs.placement_compare (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/verification/calcs/harness.placement_compare.md"
      - "packages/eng-harness/src/eng_harness/calcs/__init__.py"
      - "packages/eng-harness/src/eng_harness/calcs/placement_compare.py"
      - "packages/eng-harness/src/eng_harness/calcs/calcs.lock.json"
      - "packages/eng-harness/tests/unit/calcs/test_placement.py"
      - "packages/eng-harness/tests/data/calcs/stale_ok.json"
      - "packages/eng-harness/tests/data/golden/calcs/placement-*.json"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[placement-counts]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[placement-frames]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[placement-areas]"
      - "packages/eng-harness/tests/golden/test_calcs_golden.py::test_case[placement-renames]"
    covers: [AC42, AC43, AC44, AC45]
    depends_on: [T11]
---

# Implementation plan: eng-harness calcs

## 1. Approach

The framework comes first, in the order its own imports need: the decorator and registry (T1), the content hash and
lock file (T2), approvals (T3), the kinds (T4) and the CalcPort (T5). The rules test and golden harness (T6) are in
place before any calc exists, so every calc lands under them. Then the six calcs follow, in the order the edit cycle
depends on them. The fingerprint (T7) comes first because the difference report reuses its canonical-state helper.
The difference report (T8) is the riskiest part (A5) and is built before the read-back check (T9), which embeds it.
The summary (T10), rounding (T11) and placement comparison (T12) follow. T7 to T12 all edit `calcs/__init__.py`,
`calcs.lock.json` and `CHANGELOG.md`, so they run one after another (`depends_on`). T4 and T6 may run beside T2 and T3.
They share only `CHANGELOG.md` and `pyproject.toml` (`public_modules` lines), which are merged in pull-request order.

Every task is test-first ([process/05](../../../../design/process/05-testing-and-verification.md) §9). Its first
commit holds the tests of `tests_first` and, for T7 to T12, the golden data files. Those tests fail on `build/v1`. Golden
files are JSON (`source`, `method_ref`, `synthetic: true`, `inputs`, `expected`), with expected values derived by hand
from the spec's method rules. The hand derivation is written in the file's `derivation` field, never computed by the
implementation. All golden inputs are synthetic, and no value in them is a proposed project value. `tests/data/golden/`
and `src/eng_harness/calcs/` are protected paths: each pull request touching them is R1 and lists them for the owner.

R1 content in bootstrap mode ([ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4): every
calc is registered with `verification="draft"`. `approvals.yaml` ships empty. No task adds an approval or sets
`verified`. Each calc task writes the calc's verification record (draft) in `docs/verification/calcs/`, and its pull
request lists the calc id and content hash for the owner queue (spec Q10).

Reuse (spec §2): `eng-contract` 0.1 for canonical JSON, references, validation, `Quantity`, `Cited`, `Trace` and kinds.
The standard library covers `fractions`, `math`, `hashlib` and `ast`. The matching ideas of the Sasaah comparer are
reused (reversed ends, rename pairing), without its code or tolerances.

## 2. Tasks

**T1 Framework core** (spec §4.2, §4.3). `eng_harness.calc` holds `calc`, `CalcDef`, `CalcInput` (a contract
`ParamModel`), `InputMeta`, `RefMeta`, `TraceBuilder` (builds a contract `Trace`, checks that every `uses` name exists
earlier), `CalcStatus` and `CalcRegistry`. It also adds `CalcRefused` and the codes `CALC_NOT_APPROVED` and
`CALC_WITHDRAWN` to `errors.py` (spec Q11). `calcs/__init__.py` starts with an empty `REGISTRY`. Test calcs live in
`tests/data/calcs/` (test doubles, never registered in `REGISTRY`). The content hash is a stub raising
`NotImplementedError` until T2, and registration tests use the fixture hash.

**T2 Content hash and lock** (spec §4.5). `_calc/_hash.py` builds the static import closure with `ast` and a
file lookup under the `eng_harness` source root (no import executed; `find_spec` would run parent `__init__` modules,
amendment B-388). It hashes the LF-normalized sources, the metadata and both schemas,
with `payload_sha256` over the object of spec §4.5. `calcs.lock.json` starts empty, and the contract test compares it
with `REGISTRY`. The lock writer is a module entry point (`uv run python -m eng_harness._calc._hash --write-lock`).

**T3 Approvals** (spec §4.5). It adds the dependency ADR for a safe YAML parser (spec Q9; if plan 0004 has already
merged one, this task links it and adds no ADR), adds the dependency with `uv add`, and updates `uv.lock`. It also adds
the loader with the schema, refusal of tags, anchors and duplicate keys, status resolution and `check_approvals`, and
the shipped `approvals.yaml` with empty lists.

**T4 Kinds, part 1** (spec §4.6, §4.7, §4.8 effects). This task adds `CalcMeta`, the payload models of
`model_fingerprint` and `model_diff`, and `harness.expected_effects/1`, with their validators (counts match rows,
sorted lists, fingerprint form). The models live in `eng_harness.kinds.calcs` (R2 path `**/kinds/**`). They are
registered in the engine's `_kinds.py` with `KindRegistry.extend`. Fixtures go in `tests/data/kinds/calcs/`.

**T4b Kinds, part 2** (spec §4.9 to §4.11). This task adds the payload models of `design_summary`, `section_size`,
`placement_comparison` and `readback_check` (validators: counts match rows, sorted and unique lists, top-N label,
trace identity) to the same module and registers them. Split (B-379): the B-143 writer measured 531 changed non-test
lines for the former T4, above the 400-line task cap; T5 depends on T4b.

**T5 CalcPort** (spec §4.12). `HarnessCalcPort` and `CalcSettings` go in `_calc/_port.py`. The port validates with
`validate_input` under `require_refs`, builds `InputMeta` from the records, applies the item limit, runs the pure
function, adds `CalcMeta`, `draft` and the trace, stores the result and returns the envelope. It also implements
`preflight` and the run class. `describe` builds `CalcInfo.ref_rules` (path to `RefRule`, `stale_ok` included) from
the input model's `x-eng` metadata (spec AC13). The workflow test runs a test block through the real engine (engine plan T10) with the
real CalcPort and a fixture calc.

**T6 Rules and golden harness** (spec AC3, AC46). The AST rules test covers every module under `calcs/`: allowed
imports, top-level imports only, no I/O names, no `global`, no mutable module-level state, and FB005's literal rule,
checked locally so it runs before the gate is merged. The golden loader parametrizes `test_case[<file stem>]` over
`tests/data/golden/calcs/*.json`. The golden file lint checks `source`, `method_ref`, `synthetic` and the schema. The
verification record template goes in `docs/verification/calcs/README.md`. Almost everything here is test code.

**T7 to T12 The calcs** (spec §4.6 to §4.11). One calc per task, each with its golden files, unit and property tests,
verification record, lock entry and `REGISTRY` line. T7 adds `_state.py` (section keys and canonical order, spec §4.6
table) and builds `REGISTRY` with `removed=removed_ids(read_lock())`, so a removed id is refused at import time as
well as by the contract test (spec AC2; amendment B-388, B-141 review). T8 adds `_compare.py` (D3 and D4, exact `Fraction` comparison) and extends `_state.py` with the unnamed-row
keys of D2. T8 also adds the older-revision workflow test (spec AC48, a test block that reads, writes and reads
again through fake tool ports; its test block goes in `tests/workflows/calc_test_blocks.py`, next to T5's, amendment
B-416) and the `stale_ok` contract test (spec AC49), which compares each registered calc's
input schema with `tests/data/calcs/stale_ok.json`, the spec §4.13 table; T9 to T12 add their calc's row to that
file. T9 reuses `_compare.py` and the diff function (no copy). T7, T9 and T10 add the live items of §4 to
`docs/local-testing.md`.

## 3. Dependencies

- Runtime: a safe YAML parser, through a package ADR (T3, spec Q9), shared with plan 0004. Nothing else beyond the
  engine's `eng-contract` and `pydantic`.
- Development: the shared group (`pytest`, `pytest-cov`, `hypothesis`, `mypy`, `ruff`). No new development dependency.
- Other plans: engine plan T2 (errors) is merged before T1; engine T3 (`_kinds.py`) before T4; engine T6 (ports and
  fakes) and engine T10 (`ctx.calc`, and so engine T9) before T5. T7 to T12 inherit this through `depends_on`.
  The engine-spec amendment of spec Q11 is merged (engine spec section 4.6 invariant 3, Q17, Q18). Engine plan T12
  (invariant 3 with `CalcInfo.ref_rules`) is merged before T8, whose workflow test (spec AC48) needs the staleness
  check. Amendment (B-416).
  The gate's T39 (B-439, FB005 form A4, the `version=` keyword of `calc(...)`) is merged before T7. Amendment (B-437).
  `eng-contract` 0.1 is merged (B-010 to B-025). Spec 0002 (B-061) supplies the read set
  and host verdicts that the workflow passes. Spec 0007 (B-066) supplies `harness.expected_effects/1`. Neither blocks
  this plan: its tests use synthetic records of the neutral kinds.

## 4. Verification

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` exists. Until then, run these from
  `packages/eng-harness/`: `uv run ruff format --check`, `uv run ruff check`, `uv run mypy --strict src tests` and
  `uv run pytest` with coverage. The pull request links its CI run.
- Mutation: `calcs/**` and `_calc/**` are added to `r1_modules`, and `kinds/**` to `r2_modules`, in
  `packages/eng-harness/pyproject.toml` and `.gate/risk-map.yml`. T1 adds `calcs/**` (both files are protected; the
  owner sees the change), T2 adds `_calc/**` and T4 adds `kinds/**`. Score at least 80%.
- Needs local test (added to `packages/eng-harness/docs/local-testing.md` by T7, T9 and T10; nothing here drives a
  host program in CI): (1) fingerprint stability over repeated reads, save and reopen, and detection of the S-04 hand
  edits E1 to E10 (spec L-1); (2) the read-back check on real ETABS reads, including unit scale, frame load directions
  (S12-G9) and the table reads of S12-G8 (spec L-2, acceptance A1 and A5); (3) the design summary against the ETABS
  design display (spec L-3).
- Review: a subagent that did not write the task reviews it with the correctness, Python, type-design,
  silent-failure and test lenses. T7 to T12 are also reviewed against the method rules of the spec (R1: the reviewer
  re-derives each golden case by hand), and T2 and T3 with the security lens (file parsing, hash coverage). Owner
  approvals and the second-family review are `awaiting owner` (ADR-0028 §4).

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`. Reverting a calc task removes the calc and its
golden files. Its id stays reserved: the revert pull request sets the lock entry to `removed: true` instead of
deleting it (spec AC2). Results already stored keep their kind and stay readable, because kinds are frozen per
version. An approval is never carried over a revert: the hash changes, so the calc returns to `draft`.
