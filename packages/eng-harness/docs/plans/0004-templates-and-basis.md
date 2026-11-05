---
id: plan-b063-templates-and-basis
issue: "B-063"
spec: packages/eng-harness/docs/specs/0004-templates-and-basis.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2, r3]       # r3 because T2 and T9 touch pyproject.toml
tasks:
  - id: T1
    title: "Template model, entries, citations, canonical units and bounds"
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.templates (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/templates/__init__.py"
      - "packages/eng-harness/src/eng_harness/templates/_model.py"
      - "packages/eng-harness/tests/unit/test_template_model.py"
      - "packages/eng-harness/tests/fixtures/templates/**"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_template_model.py::test_valid_template_loads"
      - "packages/eng-harness/tests/unit/test_template_model.py::test_citation_required"
      - "packages/eng-harness/tests/unit/test_template_model.py::test_extra_keys_forbidden"
      - "packages/eng-harness/tests/unit/test_template_model.py::test_canonical_units_only"
      - "packages/eng-harness/tests/unit/test_template_model.py::test_values_and_bounds"
      - "packages/eng-harness/tests/unit/test_template_model.py::test_meta_rules"
    covers: [AC1, AC2, AC3, AC4, AC5, AC6]
    depends_on: []
  - id: T2
    # Amendment (B-374, documents only): the YAML dependency's ADR (spec Q2, A10) is written in this task, as the
    # dependency ADRs of mcp, pydantic-ai-slim, keyring and httpx2 were; it stays Proposed for the owner.
    title: "Strict YAML 1.2 loader and the YAML dependency"
    files:
      - "packages/eng-harness/pyproject.toml"
      - "uv.lock"
      - "packages/eng-harness/docs/adr/0004-ruamel-yaml.md"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/templates/_yaml.py"
      - "packages/eng-harness/tests/unit/test_template_yaml.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_template_yaml.py::test_strict_loader"
    covers: [AC7]
    depends_on: [T1]
  - id: T3
    title: "Inheritance, merge rules, ask paths and the resolved content hash"
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.templates (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/templates/_resolve.py"
      - "packages/eng-harness/tests/unit/test_template_resolve.py"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_template_resolve.py::test_merge_rules"
      - "packages/eng-harness/tests/unit/test_template_resolve.py::test_extends_errors"
      - "packages/eng-harness/tests/unit/test_template_resolve.py::test_ask_paths_carry_no_value"
      - "packages/eng-harness/tests/unit/test_template_resolve.py::test_content_hash_stable"
    covers: [AC8, AC9, AC10, AC11]
    depends_on: [T2]
  - id: T4
    title: "Template repository (shipped and user folders) and check_template"
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.templates (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/templates/_repository.py"
      - "packages/eng-harness/src/eng_harness/templates/_check.py"
      - "packages/eng-harness/src/eng_harness/templates/__init__.py"
      - "packages/eng-harness/tests/unit/test_template_repository.py"
      - "packages/eng-harness/tests/unit/test_template_check.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_template_repository.py::test_lookup_rules"
      - "packages/eng-harness/tests/unit/test_template_check.py::test_report_lists_all_errors"
    covers: [AC12, AC13]
    depends_on: [T3]
  - id: T5
    title: "FieldSpec and the workflow declaration rules"
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.basis (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/basis/__init__.py"
      - "packages/eng-harness/src/eng_harness/basis/_fields.py"
      - "packages/eng-harness/tests/unit/test_basis_fields.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_basis_fields.py::test_field_spec_rules"
    covers: [AC21]
    depends_on: [T4]
  - id: T6
    title: "Basis draft: precedence, sources, citations, pending list and draft hash"
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.basis (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/basis/__init__.py"
      - "packages/eng-harness/src/eng_harness/basis/_build.py"
      - "packages/eng-harness/tests/unit/test_basis_build.py"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/test_basis_build.py::test_precedence_and_pending"
      - "packages/eng-harness/tests/unit/test_basis_build.py::test_sources_and_citations"
      - "packages/eng-harness/tests/unit/test_basis_build.py::test_detected_differs_warning"
      - "packages/eng-harness/tests/unit/test_basis_build.py::test_value_file_rules"
      - "packages/eng-harness/tests/unit/test_basis_build.py::test_asked_and_undeclared_fields"
      - "packages/eng-harness/tests/unit/test_basis_build.py::test_draft_hash"
      - "packages/eng-harness/tests/unit/test_basis_build.py::test_confirmation_never_carried"
    covers: [AC14, AC15, AC16, AC17, AC18, AC19, AC20]
    depends_on: [T5]
  - id: T7
    title: "Setup view, answer model and BasisSetupPort"
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.basis (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/basis/__init__.py"
      - "packages/eng-harness/src/eng_harness/basis/_setup.py"
      - "packages/eng-harness/tests/unit/test_basis_setup.py"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_basis_setup.py::test_view_rows"
      - "packages/eng-harness/tests/unit/test_basis_setup.py::test_answer_cannot_carry_values"
    covers: [AC26, AC27]
    depends_on: [T6]
  - id: T8
    title: "Freeze, storage as basis.design_basis/1 and StoreBasisPort"
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.basis (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/basis/__init__.py"
      - "packages/eng-harness/src/eng_harness/basis/_freeze.py"
      - "packages/eng-harness/src/eng_harness/basis/_port.py"
      - "packages/eng-harness/tests/contract/test_basis_freeze.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/contract/test_basis_freeze.py::test_refusals"
      - "packages/eng-harness/tests/contract/test_basis_freeze.py::test_incomplete_lists_paths"
      - "packages/eng-harness/tests/contract/test_basis_freeze.py::test_freeze_stores_result"
      - "packages/eng-harness/tests/contract/test_basis_freeze.py::test_stored_basis_immutable"
    covers: [AC22, AC23, AC24, AC25]
    depends_on: [T7]
  - id: T9
    title: "Shipped blank template, package data and golden pin"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/src/eng_harness/templates/shipped/blank-0.1.0.template.yaml"
      - "packages/eng-harness/tests/golden/test_shipped_templates.py"
      - "packages/eng-harness/tests/data/golden/shipped_templates.json"
    max_changed_lines: 120
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/test_shipped_templates.py::test_shipped_templates_pinned"
    covers: [AC29]
    depends_on: [T4]
  - id: T10
    title: "Property tests and the fake-host workflow with replay"
    files:
      - "packages/eng-harness/tests/property/test_template_basis_props.py"
      - "packages/eng-harness/tests/workflow/test_basis_workflow.py"
      - "packages/eng-harness/tests/fixtures/workflows/**"
    max_changed_lines: 300
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/property/test_template_basis_props.py"
      - "packages/eng-harness/tests/workflow/test_basis_workflow.py::test_basis_reaches_ctx_and_replays"
    covers: [AC28, AC30]
    depends_on: [T8]
---

# Implementation plan: eng-harness templates and the design basis

## 1. Approach

Implements [spec 0004](../specs/0004-templates-and-basis.md) in two layers: `eng_harness.templates` (T1 to T4: schema,
strict loading, inheritance, repository), then `eng_harness.basis` (T5 to T8: field declaration, draft, page
interface, freeze and storage), then shipped content and cross-cutting tests (T9, T10). Risky parts first: the schema
and unit rules (T1) carry the most R1 risk; the YAML dependency (T2) needs an ADR before it starts. Reuse: the contract
supplies `Cited`, units, `Timestamp`, `ResultStore`, the `basis.design_basis/1` kind and `DesignBasis.missing`; the
engine supplies `BasisPort`, `ctx.basis` and the invariant that refuses an incomplete basis. Nothing is copied from
other packages.

Cross-plan dependencies, which `depends_on` cannot express: T1 needs engine T1 (skeleton) and the merged
`eng-contract` 0.1.0 (plan B-003); T8 needs engine T6 (ports) and contract T12 and T14 (kinds, result store); T9 needs
the field list of spec 0007; T10 needs engine T7, T13 and T19 (basis view, invariant 5, replay suite). T1, T3, T4 and T5
start only after the contract path-rule question (spec Q1) is decided, since template keys follow the contract path-segment
rule and suffixed names such as `fc_MPa` do not pass the 0.1 basis path rule.

## 2. Tasks

**T1 Template model.** Pydantic models for `Template`, `Meta`, `Entry`, `Bounds`, `AskItem`; citation, canonical-unit,
finiteness and bounds rules; synthetic fixtures. No YAML yet (tests build models from dictionaries).
**T2 Strict YAML loader.** Adds the parser dependency (needs the ADR of spec Q2) and the loader that refuses
duplicates, aliases, tags and oversize files; touches `pyproject.toml` and `uv.lock`.
**T3 Inheritance and identity.** `extends`, merge rules, the ask-path rule and the resolved content hash.
**T4 Repository and `check_template`.** Shipped and user folders, ambiguity, synthetic refusal, the all-errors report.
**T5 FieldSpec.** The workflow's declaration and its coherence rules.
**T6 Draft.** Precedence, sources, citations, pending list, warnings and the draft hash. Largest R1 task: it is where a
wrong source or default would leak, so it is reviewed against spec §4.4 line by line.
**T7 Setup interface.** `BasisSetupView`, `BasisSetupAnswer`, `BasisSetupPort`, `build_setup_view`. Spec 0006 implements
the page against this; no HTML here.
**T8 Freeze and storage.** `freeze`, `StoreBasisPort`, immutability and refusals against the real contract
`ResultStore`.
**T9 Shipped content.** The `blank` template, package data inclusion and the golden pin. No values.
**T10 Cross-cutting tests.** Hypothesis round trips and the fake-host workflow with journal replay (process/05 §2:
every workflow path has a fake-host and a replay test).

## 3. Dependencies

- Runtime: `eng-contract` and `pydantic` (already in the engine plan). New: one YAML parser, proposed `ruamel.yaml`,
  only after an ADR approves it (A10; spec Q2). If the ADR is refused, T2 changes to JSON templates by a plan amendment.
- Development: none new (`hypothesis`, `pytest`, `mypy`, `ruff` are in the workspace group).

## 4. Verification

Local gate per task as in the engine plan §4; the pull request links its CI run. Fake-host workflow and replay in T10.
Review lenses: correctness, type design, silent failure, tests; T1, T3, T6 and T8 also against the R1 rules of
process/10 (no invented value, every value cited, owner queue for engineering content). Second-family review and owner
approvals are `awaiting owner` in bootstrap mode.
Needs local test (list in `docs/local-testing.md`, completed by T9): (1) a values file and the approval page of spec 0006
used by the owner on a real template once that page exists; (2) a template written by hand in the user folder on the
owner's machine (path, encoding and line endings on Windows). Nothing in this plan needs a host program.

## 5. Rollback

Each task is one squash-merged pull request with no consumer outside the package until spec 0006 and 0007 use it;
reverting a task's commit removes it together with its dependants. A stored `basis.design_basis/1` result is never
rewritten; a defect in the builder is fixed forward, and affected runs are re-run with a new basis.
