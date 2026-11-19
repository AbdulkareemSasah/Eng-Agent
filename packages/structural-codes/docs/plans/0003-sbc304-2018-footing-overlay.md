---
id: plan-b072-sbc304-2018-footing-overlay
issue: "B-072"
spec: packages/structural-codes/docs/specs/0003-sbc304-2018-footing-overlay.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: standard
risk: [r1, r3]           # binding for every pull request of this plan; r3 from T1 (pyproject.toml, uv.lock, .gate/)
tasks:
  - id: T1
    title: Pack skeleton, empty approvals file, workspace member, local-testing section
    files:
      - "pyproject.toml"
      - "uv.lock"
      - "packages/structural-codes/.gate/agents.yml"
      - "packages/structural-codes/.gate/risk-map.yml"
      - "packages/structural-codes/AGENTS.md"
      - "packages/structural-codes/docs/local-testing.md"
      - "packages/structural-codes/sbc304-2018/pyproject.toml"
      - "packages/structural-codes/sbc304-2018/README.md"
      - "packages/structural-codes/sbc304-2018/CHANGELOG.md"
      - "packages/structural-codes/sbc304-2018/src/sbc304_2018/__init__.py"
      - "packages/structural-codes/sbc304-2018/src/sbc304_2018/py.typed"
      - "packages/structural-codes/sbc304-2018/src/sbc304_2018/approvals.yaml"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_package.py"
    max_changed_lines: 150
    max_sessions: 2
    tests_first: ["packages/structural-codes/sbc304-2018/tests/unit/test_package.py::test_version_and_empty_approvals"]
    covers: [AC11]
    depends_on: []
  - id: T2
    title: Clause map module (footing rows), row validation and overlay builder with the unconfirmed gap check
    files:
      - "packages/structural-codes/core/src/structural_codes/_runner.py"  # amendment B-579
      - "packages/structural-codes/core/tests/unit/test_overlay.py"  # amendment B-579
      - "packages/structural-codes/sbc304-2018/src/sbc304_2018/clause_map.py"
      - "packages/structural-codes/sbc304-2018/src/sbc304_2018/_overlay.py"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_clause_map.py"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_overlay_builder.py"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_unconfirmed.py"
      - "packages/structural-codes/sbc304-2018/tests/property/test_unconfirmed_props.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/sbc304-2018/tests/unit/test_clause_map.py::test_rows_match_clause_map_doc"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_clause_map.py::test_column_rows_explicit"  # amendment B-579
      - "packages/structural-codes/sbc304-2018/tests/unit/test_clause_map.py::test_row_rules"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_overlay_builder.py::test_missing_row_default"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_overlay_builder.py::test_inherited_row"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_overlay_builder.py::test_row_changes_change_hash"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_unconfirmed.py::test_needs_engineer_with_gap"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_unconfirmed.py::test_member_scope_copied"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_unconfirmed.py::test_inputs_match_base"
      - "packages/structural-codes/sbc304-2018/tests/property/test_unconfirmed_props.py::test_never_pass_or_fail"
      # amendment B-579: core regression for inherited body verdicts with an explicit base clause (both cases in T2 prose)
      - "packages/structural-codes/core/tests/unit/test_overlay.py::test_inherited_explicit_base_clause"
    covers: [AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC10]  # and core spec 0001 AC18 (amendment B-579)
    depends_on: [T1]
  - id: T3
    title: Pack assembly, registration, check_id_for, boundary case files, pack-level tests, README usage
    files:
      - "packages/structural-codes/sbc304-2018/src/sbc304_2018/__init__.py"
      - "packages/structural-codes/sbc304-2018/pyproject.toml"
      - "packages/structural-codes/sbc304-2018/README.md"
      - "packages/structural-codes/sbc304-2018/CHANGELOG.md"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_pack.py"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_verify_cli.py"
      - "packages/structural-codes/sbc304-2018/tests/contract/test_pack_payloads.py"
      - "packages/structural-codes/sbc304-2018/tests/replay/test_pack_determinism.py"
      - "packages/structural-codes/sbc304-2018/tests/data/golden/verification/sbc304_2018.*.yaml"
    max_changed_lines: 150
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/sbc304-2018/tests/unit/test_pack.py::test_check_id_for"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_pack.py::test_registry_and_specs"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_pack.py::test_all_draft"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_pack.py::test_no_engineering_numbers"
      - "packages/structural-codes/sbc304-2018/tests/contract/test_pack_payloads.py::test_needs_engineer_payloads"
      - "packages/structural-codes/sbc304-2018/tests/replay/test_pack_determinism.py::test_identical_across_hash_seeds"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_verify_cli.py::test_verify_reports_unverified"
    covers: [AC9, AC12, AC13, AC14, AC15, AC16, AC17]
    depends_on: [T2]
  - id: T4
    title: Column rows G-7 to G-9 in the clause map and their boundary case files (dropped, amendment B-579)
    files:
      - "packages/structural-codes/sbc304-2018/src/sbc304_2018/clause_map.py"
      - "packages/structural-codes/sbc304-2018/CHANGELOG.md"
      - "packages/structural-codes/sbc304-2018/tests/unit/test_clause_map.py"
      - "packages/structural-codes/sbc304-2018/tests/data/golden/verification/sbc304_2018.*.yaml"
    max_changed_lines: 60
    max_sessions: 1
    tests_first: ["packages/structural-codes/sbc304-2018/tests/unit/test_clause_map.py::test_column_rows_explicit"]
    covers: [AC1]
    depends_on: [T3]
---

# Implementation plan: SBC 304-2018 overlay for the footing checks

Package: `structural-codes-sbc304-2018` (import package `sbc304_2018`), in `packages/structural-codes/sbc304-2018/`,
layer 3 ([10](../../../../design/docs/architecture/10-structural-codes.md) §2). Spec:
[0003](../specs/0003-sbc304-2018-footing-overlay.md) ("SP"); clause map:
[clause-map.md](../clauses/sbc304_2018/clause-map.md) ("CM"); framework: [core spec 0001](../specs/0001-core-framework.md)
("CF"). File paths in the front matter are relative to the workspace root; `max_changed_lines` counts non-test,
non-generated lines ([process/04](../../../../design/process/04-implementation-rules.md) §4). Bootstrap mode
([ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4): this plan is `draft`, every check
ships `draft`, `approvals.yaml` stays empty, and no row of the clause map is `inherited`.

## 1. Approach

The pack evaluates no SBC equation. It maps every ACI 318-14 check to an explicit status and, because no SBC text was
available, every row is `unconfirmed`: its check validates the base inputs, applies the base member scope and returns
`NEEDS_ENGINEER` with a typed gap (SP §4.3). The risky part is the builder (T2): it decides what runs under an SBC
label, so it comes first after the skeleton and its tests pin that no unconfirmed check can give `PASS` or `FAIL`
(SP AC5) and that a base check without a row never runs the base body (SP AC3).

Reuse: the core overlay entries (`Overridden`, `Inherited`), `NotImplementedGap` and the lifecycle (CF §4.4, §4.8,
§4.11); the base input models from `aci318_14`. Nothing is copied from the ACI pack.

Start condition: core plan 0001 T10 (overlay), T11 (lifecycle), T12 (command line), T14a (public modules declared;
amendment B-385) and T14b (`structural_codes.lifecycle` in public_modules, without which
`tests/unit/test_pack.py::test_all_draft` fails IM002; amendment B-419) merged; ACI plan 0002 T1 (shared
folder files) before T1, and plan 0002 T9 (ACI pack registered) before T2. B-334 (ACI plan 0004 T5) already registered
the ACI column checks before T2 started, so plan 0003 folds G-7 to G-9 and the column-row test
(`test_clause_map.py::test_column_rows_explicit`) into T2, T3 adds the three column case files, and T4 is dropped as
planned (amendment B-579); the three extra rows fit T2's budget. Ordering: SP AC1 compares the module with the CM §3
rows of every *registered* base check, so T2 writes G-1 to G-9. Each task is test-first: its first commit is `test:` with the tests of `tests_first`, failing on `build/v1`
([process/05](../../../../design/process/05-testing-and-verification.md) §9).

## 2. Tasks

**T1 Skeleton.** Creates `packages/structural-codes/sbc304-2018/` as a uv workspace member (D-10):
`name = "structural-codes-sbc304-2018"`, `version = "0.1.0.dev0"`, `requires-python = ">=3.14,<3.15"`, dependencies
`structural-codes-core`, `structural-codes-aci318-14` and `eng-contract` (workspace sources, no third-party
dependency); `[tool.eng-gate]` with `profile = "codes"`, `layer = 3`, `import_names = ["sbc304_2018"]`,
`check_modules = ["src/sbc304_2018/**/*.py"]`, `r1_modules` = every module under `src/sbc304_2018/`, thresholds line
95, branch 90, mutation 80 (process/05 §2); `approvals.yaml` as package data with `approvals: []` and `withdrawn: []`.
Adds the pack's paths to the shared `.gate/risk-map.yml` as `r1`, renders the shared `AGENTS.md` again, and adds an
SBC section to `docs/local-testing.md` stating that no item needs a host in this version (§4).

**T2 Clause map and builder.** `clause_map.py` holds `CLAUSE_MAP` with rows G-1 to G-9 of CM §3 (B-334 merged, §1), exactly as the table. `_overlay.py` holds `MapStatus`, `MapRow`, `GapReason`, the row validation (SP AC2), the missing-row default
(SP AC3) and `build_overlay(rows, base_pack) -> (checks, Overlay)` producing `Inherited` entries for `inherited` rows
and the gap check of SP §4.3 as `Overridden` entries. The doc-match test parses the table between the
`clause-map-rows` markers of CM §3. R1 modules, reviewed with the source-check lens: the reviewer confirms the module
states no SBC clause number and no number at all. The row validation has no numeric length limit; limits come from
the core when the builder creates `CheckMeta` and `GapDecl` (CM §2), so T3's `test_no_engineering_numbers` holds.
Amendment B-579: covers core spec 0001 AC18 (runner behavior for inherited verdicts). For inherited body verdicts,
the runner validates explicit draft clauses against the base check metadata, then emits the inherited check's
mapped clause, code and check id, and preserves the base trace citations. T2's `tests_first` includes the core
regression `test_overlay.py::test_inherited_explicit_base_clause`: a valid explicit base clause produces the mapped
overlay identity and retains base citations; an invalid explicit base clause raises `CheckDefinitionError`.

**T3 Assembly.** `PACK` with `base="aci318_14"` and the built overlay, the entry point
`[project.entry-points."structural_codes.packs"] sbc304_2018 = "sbc304_2018:PACK"`, `check_id_for`; one case file per
check with one `boundary` case expecting `NEEDS_ENGINEER` and `program_comparison.not_available` (SP §9); README usage
with `check_id_for` and `structural_codes.evaluate`; changelog entry for 0.1.0.

**T4 Column rows.** Dropped (amendment B-579): B-334 already registered the column checks, so rows G-7 to G-9 and their
test fold into T2 and the case files into T3 (§1).

## 3. Dependencies

- Runtime: `structural-codes-core`, `structural-codes-aci318-14`, `eng-contract` (workspace). No new third-party
  dependency, so no ADR.
- Development: the root dependency group (`pytest`, `hypothesis`, `ruff`, `mypy`, `pytest-cov`).

## 4. Verification

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` exists; until then `uv run ruff format --check`,
  `uv run ruff check`, `uv run mypy --strict src tests` and `uv run pytest` with coverage, from
  `packages/structural-codes/sbc304-2018/`. T2 verification includes the `structural-codes-core` gate for its core runner
  edits (amendment B-579).
- Review: each pull request by a subagent that did not write it, with the R1 source-check lens (no SBC claim, no
  number, no implicit inheritance). C3 and the owner's confirmation of each row are `awaiting owner`.
- Fake-host scenarios: none (no host). Needs local test: none in this version; once a row is `inherited`, its check
  reuses the base check's program-comparison rows (plan 0002 §4) under the SBC id, added by that row's pull request.

## 5. Rollback

Each task is one squash-merged pull request on `build/v1`. The pack has no consumer until B-075; a task is reverted by
reverting its commit (with T3 if registered). After B-075 uses it, defects are fixed forward with a regression test;
a row turning `inherited` is a major version with a golden diff report (process/10 §5).

## 6. Owner queue

Questions SP §11 Q1 to Q8 with their recommendations; gaps CM §3 G-1 to G-9 (each: confirm SBC 304-2018 against the
base check, with the common items and the row's items) and G-WE; additions SP §11 A1.

## 7. Non-goals

As SP §7: no SBC-specific check, no SBC clause number or content, no load combinations, no footing workflow.
