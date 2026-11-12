---
id: plan-b064-decisions
issue: "B-064"
spec: packages/eng-harness/docs/specs/0005-decisions.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r3]           # binding for every pull request of this plan; r3 because T1 touches packages/eng-harness/pyproject.toml
tasks:
  - id: T1
    title: Types, policy, settings, public modules
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/__init__.py"
      - "packages/eng-harness/src/eng_harness/decisions/types.py"
      - "packages/eng-harness/src/eng_harness/decisions/interfaces.py"
      - "packages/eng-harness/src/eng_harness/decisions/_policy.py"
      - "packages/eng-harness/tests/unit/decisions/test_policy.py"
      - "packages/eng-harness/tests/data/golden/decision_policy_defaults.json"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/decisions/test_policy.py::test_defaults_match_golden"
      - "packages/eng-harness/tests/unit/decisions/test_policy.py::test_policy_bounds"
    covers: [AC6, AC7]
    depends_on: []
  - id: T2
    # Amendment (B-411, documents only): decisions._points.discover() over eng_harness.workflows feeds the lock test and --write-lock (spec 4.2); budget 380 to 400.
    title: Decision points, state field rules, point registry and lock
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.decisions, eng_harness.decisions.types (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/__init__.py"
      - "packages/eng-harness/src/eng_harness/decisions/types.py"
      - "packages/eng-harness/src/eng_harness/decisions/__main__.py"
      - "packages/eng-harness/src/eng_harness/decisions/_points.py"
      - "packages/eng-harness/src/eng_harness/decisions.lock.json"
      - "packages/eng-harness/tests/unit/decisions/test_points.py"
      - "packages/eng-harness/tests/contract/test_decision_lock.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/decisions/test_points.py::test_definition_rules"
      - "packages/eng-harness/tests/unit/decisions/test_points.py::test_state_field_types"
      - "packages/eng-harness/tests/unit/decisions/test_points.py::test_state_size_limit"
      - "packages/eng-harness/tests/unit/decisions/test_points.py::test_check_lock"
      - "packages/eng-harness/tests/contract/test_decision_lock.py::test_lock_matches_registry"
    covers: [AC1, AC2, AC3, AC4]
    depends_on: [T1]
  - id: T3
    # Amendment (B-411, documents only): scoped to the pure check (findings, Ref omission); the cascade side of AC33 is T8, the screen side of AC34 is T7.
    title: Redaction check (by construction and at runtime)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.decisions (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/_redaction.py"
      - "packages/eng-harness/src/eng_harness/decisions/_points.py"
      - "packages/eng-harness/tests/unit/decisions/test_redaction.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/decisions/test_redaction.py::test_by_construction"
      - "packages/eng-harness/tests/unit/decisions/test_redaction.py::test_runtime_check_blocks_send"
      - "packages/eng-harness/tests/unit/decisions/test_redaction.py::test_refs_not_sent"
    covers: [AC32, AC34]
    depends_on: [T2]
  - id: T4
    # Amendment (B-411, documents only): decisions._rules.discover(), missing_rule_tests() and --write-lock for rules.lock.json in __main__.py (spec 4.4); budget 380 to 400.
    title: Rule definitions, restricted basis view, registry, lock and review table
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.decisions, eng_harness.decisions.types (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/__init__.py"
      - "packages/eng-harness/src/eng_harness/decisions/types.py"
      - "packages/eng-harness/src/eng_harness/decisions/__main__.py"
      - "packages/eng-harness/src/eng_harness/decisions/_rules.py"
      - "packages/eng-harness/src/eng_harness/rules.lock.json"
      - "packages/eng-harness/tests/unit/decisions/test_rules.py"
      - "packages/eng-harness/tests/rules/fixtures/**"
      - "packages/eng-harness/tests/contract/test_rule_lock.py"
      - "packages/eng-harness/tests/contract/test_rule_tests_exist.py"
      - "packages/eng-harness/tests/rules/test_decision_imports.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/decisions/test_rules.py::test_registration_rules"
      - "packages/eng-harness/tests/unit/decisions/test_rules.py::test_code_hash_is_stable"
      - "packages/eng-harness/tests/unit/decisions/test_rules.py::test_rule_basis_is_restricted"
      - "packages/eng-harness/tests/unit/decisions/test_rules.py::test_review_table"
      - "packages/eng-harness/tests/contract/test_rule_lock.py::test_lock_matches_registry"
      - "packages/eng-harness/tests/contract/test_rule_tests_exist.py::test_every_rule_has_typical_and_boundary_tests"
      - "packages/eng-harness/tests/contract/test_rule_tests_exist.py::test_missing_rule_tests_reports_a_fixture_gap"
      - "packages/eng-harness/tests/rules/test_decision_imports.py::test_types_module_is_block_safe"
    covers: [AC9, AC10, AC11, AC12, AC13, AC42]
    depends_on: [T2]
  - id: T5
    # Amendment (B-411, documents only): depends on T2 and T4 (port field types); builds the provider error types of spec 4.7 and DecisionCall.sensitive_values.
    title: Provider interfaces, suggestion and port models, fake providers
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.decisions, eng_harness.decisions.interfaces (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/interfaces.py"
      - "packages/eng-harness/src/eng_harness/decisions/_record.py"
      - "packages/eng-harness/tests/fakes/decision_providers.py"
      - "packages/eng-harness/tests/contract/test_decision_providers.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_decision_providers.py::test_fake_providers_conform"
      - "packages/eng-harness/tests/contract/test_decision_providers.py::test_provider_error_shape"
    covers: [AC41]
    depends_on: [T2, T4]
  - id: T6
    # Amendment (B-411, documents only): pending API open_pending/get_pending/close_pending with batch_id and outcomes (spec 4.11, AC44); append(label, findings) stores hash-only on passed findings.
    title: Label store, pending store, override and opt-in export
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.decisions (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/__init__.py"
      - "packages/eng-harness/src/eng_harness/decisions/_labels.py"
      - "packages/eng-harness/tests/unit/decisions/test_labels.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/decisions/test_labels.py::test_append_only"
      - "packages/eng-harness/tests/unit/decisions/test_labels.py::test_unredactable_state_hash_only"
      - "packages/eng-harness/tests/unit/decisions/test_labels.py::test_write_failure_is_loud"
      - "packages/eng-harness/tests/unit/decisions/test_labels.py::test_override_label"
      - "packages/eng-harness/tests/unit/decisions/test_labels.py::test_export_is_opt_in"
      - "packages/eng-harness/tests/unit/decisions/test_labels.py::test_pending_round_trip"
    covers: [AC35, AC36, AC37, AC38, AC39, AC44]
    depends_on: [T3, T5]
  - id: T7
    # Amendment (B-411, documents only): redaction findings over settings and call sensitive values (spec 4.5 step 1), passed to append(label, findings); Ref fields on the screen (AC34).
    title: Cascade core (validation, tier 1, engineer tier, pending, record)
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.decisions (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/__init__.py"
      - "packages/eng-harness/src/eng_harness/decisions/_cascade.py"
      - "packages/eng-harness/src/eng_harness/decisions/_record.py"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_call_validation"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_first_matching_rule_wins"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_bad_rule_fails_the_step"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_phase1_rules_then_engineer"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_invalid_engineer_choice"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_pending_is_idempotent"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_rule_entry_has_hash"
    covers: [AC5, AC14, AC15, AC17, AC18, AC19, AC31, AC34]
    depends_on: [T4, T6]
  - id: T8
    # Amendment (B-411, documents only): test_redaction_skip carries the cascade side of AC33; the property test adds a call-supplied sensitive value.
    title: Tiers 2 and 3, shadow mode, timeouts, policy switches, local_only
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.decisions (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/_cascade.py"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py"
      - "packages/eng-harness/tests/property/test_decision_properties.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_shadow_needs_release"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_tier2_threshold"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_provider_failures_fall_through"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_tier3_rationale_and_option"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_shadow_mode"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_policy_switches"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_local_only"
      - "packages/eng-harness/tests/unit/decisions/test_cascade.py::test_redaction_skip"
      - "packages/eng-harness/tests/property/test_decision_properties.py::test_sensitive_text_never_reaches_a_provider"
    covers: [AC8, AC21, AC22, AC23, AC24, AC25, AC26, AC33]
    depends_on: [T7]
  - id: T9
    title: decide_many batching and one batched screen
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.decisions (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/_batch.py"
      - "packages/eng-harness/src/eng_harness/decisions/_cascade.py"
      - "packages/eng-harness/tests/unit/decisions/test_batch.py"
    max_changed_lines: 330
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/decisions/test_batch.py::test_batching_and_order"
      - "packages/eng-harness/tests/unit/decisions/test_batch.py::test_one_screen_all_or_nothing"
      - "packages/eng-harness/tests/unit/decisions/test_batch.py::test_resume_does_not_requery"
    covers: [AC27, AC28, AC29]
    depends_on: [T8]
  - id: T10
    title: Engine wiring, workflow, replay, conformance and performance tests, local-testing notes
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.decisions, eng_harness.engine (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/src/eng_harness/engine/_decide.py"
      - "packages/eng-harness/src/eng_harness/decisions/_cascade.py"
      - "packages/eng-harness/tests/workflow/decisions/test_engine_decisions.py"
      - "packages/eng-harness/tests/replay/test_decision_replay.py"
      - "packages/eng-harness/tests/contract/test_decision_port.py"
      - "packages/eng-harness/tests/perf/test_rule_latency.py"
    max_changed_lines: 170
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/decisions/test_engine_decisions.py::test_rules_run_under_the_guard"
      - "packages/eng-harness/tests/workflow/decisions/test_engine_decisions.py::test_engineer_decision_pauses_and_resumes"
      - "packages/eng-harness/tests/workflow/decisions/test_engine_decisions.py::test_decision_made_record"
      - "packages/eng-harness/tests/replay/test_decision_replay.py::test_replay_does_not_requery"
      - "packages/eng-harness/tests/replay/test_decision_replay.py::test_crash_while_pending"
      - "packages/eng-harness/tests/contract/test_decision_port.py::test_cascade_conforms"
      - "packages/eng-harness/tests/perf/test_rule_latency.py::test_rule_decision_p95"
      - "packages/eng-harness/tests/workflow/decisions/test_engine_decisions.py::test_runtime_summary_in_run_header"
    covers: [AC16, AC17, AC20, AC30, AC40, AC41, AC43]
    depends_on: [T9]
---

# Implementation plan: eng-harness decision layer (spec 0005)

## 1. Approach

Build bottom-up, risky and R1 parts early: policy and types first (they fix the defaults of 12 §3 in a golden file),
then points, redaction and rules (the surfaces blocks and the owner see), then the interfaces and fakes, the label
store, and the cascade in three steps (tier 1 and 4; tiers 2 and 3 and shadow; batching). The last task wires the
cascade into the engine and adds the workflow, replay, conformance and performance tests. Nothing here needs a host
program. Tiers 2 and 3 are built and tested against fake providers only; no provider implementation, network code or
key handling is written (phase 2, ADR-0012, ADR-0013).

Reuse (spec §2): the registry-and-lock pattern, `Ctx` types and guard of the engine; the contract's canonical JSON,
`Ref`, `Quantity`, `Timestamp`, `Clock`, `ContractError`; standard-library `sqlite3`, `asyncio` and `hashlib`. Tests
use fakes from engine plan T6 and a real SQLite store in a temporary workspace. T1 adds the public modules
`eng_harness.decisions`, `eng_harness.decisions.types` and `eng_harness.decisions.interfaces` to
`[tool.eng-gate] public_modules`, and `src/eng_harness/decisions/_cascade.py`, `_batch.py`, `_policy.py`,
`_redaction.py` and `_rules.py` to `r1_modules` (mutation score at least 80%); the gate profile keys follow the merged
gate spec, as in engine plan T1.

## 2. Tasks

**T1 Types and policy** (spec §4.2, §4.3). `Label`, `Rationale`, `DecisionPolicy` with the 12 §3 defaults,
`DecisionSettings`, `ShadowRelease`, `Pick`, `DecisionDefinitionError`, and empty public modules. The golden file cites
12 §3. The only task that touches `pyproject.toml` (risk floor r3).

**T2 Points** (spec §4.2). `DecisionPoint`, `decision_point`, `PointRegistry`, the state-type rules, size check,
`schema_sha256`, `check_lock` and the `--write-lock` entry point, with a lock for the (empty) real registry.
Amendment B-411: the real registry is `decisions._points.discover()` (spec §4.2: every module under
`eng_harness.workflows`, private modules included, imported inside the function, module-level `DecisionPoint` objects
deduplicated by identity and sorted by name, empty when the package is absent); `test_lock_matches_registry` and
`--write-lock` use it, so later plans add points without editing `_points.py`. Budget raised from 380 to 400 for it.

**T3 Redaction** (spec §4.10). Field-name check wired into point creation, the value check as a pure function, the
finding model (paths and reasons only), omission of `Ref` fields from the outgoing state. Amendment B-411: T3 tests the
pure functions only, since no cascade exists at its base: `test_runtime_check_blocks_send` asserts the findings
(`field_path` and `reason`, no value) for a path, a URL, an address, a sensitive value and an over-long string, and
`test_refs_not_sent` asserts that `Ref` fields are absent from the outgoing mapping. The value check takes the
sensitive values as an argument (the cascade passes the union of spec §4.5 step 1). The cascade side of AC33 is T8's
`test_redaction_skip`; the screen side of AC34 is T7's `test_phase1_rules_then_engineer`.

**T4 Rules** (spec §4.4). `Rule`, `rule`, `RuleBasis` over the engine's `BasisView` type, `RuleRegistry`,
`rules.lock.json`, `review_table()` (reads `approvals.yaml` through a passed mapping, no file I/O in the registry), and
the contract tests, including the typical-and-boundary convention and the import test of `types`. Fixture rules in
`tests/rules/fixtures/` (test doubles). Amendment B-411: the real registry is `decisions._rules.discover()` (spec §4.4:
every module under `eng_harness.rules`, imported inside the function, module-level `Rule` objects sorted by id, empty
when the package is absent); the AC12 check is the pure function `missing_rule_tests(registry, tests_dir)`, run over
the discovered registry and `tests/rules/` by `test_every_rule_has_typical_and_boundary_tests`, and on a fixture rule
with a `tmp_path` folder by `test_missing_rule_tests_reports_a_fixture_gap`, so no `tests/rules/test_<fixture>.py` is
committed. T4 extends `decisions/__main__.py` so `--write-lock` writes `rules.lock.json` too and refuses, writing
neither lock, a changed hash under an unchanged version. Budget raised from 380 to 400 for it.

**T5 Interfaces** (spec §4.7). `ProviderInfo`, request and answer models, `DecisionProvider`, `LLMProvider`,
`Suggestion`, `DecisionAnswer`, `PendingAnswer`, `DecisionScreen`, `DecisionCall`, `EngineerChoice`; fake providers
with scripted answers, delays and failures (tests, not shipped). Amendment B-411: T5 depends on T2 (`DecisionPoint`)
and T4 (`Rule`, and `DecisionPolicy` of T1), the field types of `DecisionCall`. It also builds `ProviderErrorCode`,
`OutgoingPlace`, `ProviderError` (`str()` is the code value only; attributes `code`, `gap`, `where`) and
`ProviderFailure` exactly as spec §4.7 (plan 0009 T1 no longer adds them), with a shape assertion in
`test_provider_error_shape`, and `DecisionCall.sensitive_values: tuple[str, ...]` (default empty, spec §4.5; engine
spec §4.9.1 and Q19). About 40 more lines; the budget of 300 holds.

**T6 Label store** (spec §4.11). `decisions.sqlite` with append-only triggers, `labels` and `pending` tables,
idempotent insert by `request_id`, override and opt-in export. A write failure raises `StoreWriteError`. Amendment
B-411: the pending API is fixed here so T9 needs no change to `_labels.py`: `open_pending(request_id, batch_id, screen,
outcomes)` (idempotent by `request_id`), `get_pending(request_id)` returning `None` or `screen`, `batch_id`, `outcomes`
and `created_at`, and `close_pending(request_id, closed_at)`; `test_pending_round_trip` (AC44) asserts that `batch_id`
and a non-empty `outcomes` object round-trip unchanged and that only `closed_at` changes on close. The label append is
fixed here too, so T7 needs no change to `_labels.py`: `append(label, findings)` takes the findings of T3's check as
the cascade computed them (spec §4.5 step 1, over the union of §4.10) and does not re-run the value check; when the
findings are non-empty it keeps `state_sha256` and stores `state` as null (AC36). `test_unredactable_state_hash_only`
builds its findings with T3's check over a value supplied only as a call's sensitive value (absent from the store's
`DecisionSettings`) and asserts the hash-only label. `record_override` stores `state` as null always (AC38); where it
finds the overridden decision's identity is spec Q14: build it against the store's labels and pending rows and leave
the rest as the recorded gap.

**T7 Cascade core** (spec §4.5 steps 1 to 4 and 6). Call validation, rule evaluation under `rule_guard`, pending and
answered flow, label append, record building. Provider tiers are absent here, which is the phase 1 deployment (AC17).
Amendment B-411: step 1 computes the redaction findings once over `settings.sensitive_values ∪ call.sensitive_values`
(T8 consumes them for the tier skips; here they are passed to T6's `append(label, findings)`, which makes the label
hash-only, AC36), and
`test_phase1_rules_then_engineer` also asserts that `Ref` fields appear on the screen as references (AC34).

**T8 Tiers 2 and 3** (spec §4.5 step 5, §4.6). Effective shadow, concurrent shadow calls, acceptance rules,
timeouts, failure capture, `local_only`, redaction skips; property tests over random provider answers and sensitive
strings. Amendment B-411: `test_redaction_skip` carries the cascade side of AC33 (provider not called, outcome
`skipped_redaction` with the field paths, engineer asked), and the property test also asserts one value supplied only
through `DecisionCall.sensitive_values`.

**T9 `decide_many`** (spec §4.8). Per-provider batching with fallback, one batch id and screen, stored outcomes for
resume, all-or-nothing engineer answers.

**T10 Wiring and acceptance** (spec §4.12). Small changes to the engine's `_decide` (the engine plan T14 may already
call the port; if so this task is tests, documents and the `engine.decision` request kind only), the workflow, replay
(crash while pending) and conformance tests, the p95 test, and the items of §4 in `docs/local-testing.md`. If T14 of
the engine plan has not merged, this task waits. Amendment B-098: the cascade's `runtime_summary()` (spec §4.12,
AC43; `_cascade.py` gains the constructor argument and the getter, about 20 lines, which raised the budget from 150 to
170), tested through the real engine's run header (engine AC69, engine plan T14b).

## 3. Dependencies

- Runtime: none new (`eng-contract`, `pydantic` from engine plan T1; standard library otherwise). No ADR is needed.
- Development: none new.
- Work items: the engine plan (B-060) T2 (errors), T6 (ports and fakes), T7 (ctx types, `BasisView`), T14 (`_decide`), T14b (`decision_runtime` in the run header, before T10 only),
  T17 (guard) merged before T7 and T10 here; T1 to T6 here need engine T1, T2, T6 and T7 (`BasisView`, already merged;
  amendment B-411, engine spec Q19). The amendments
  of spec Q1 are made in the engine spec's own pull request before T10. Specs 0006 and 0007 depend on T10.
- Command line (amendment B-412 sixth review): spec 0006 §4.2.2 step 5 builds the `Cascade` in the command line through
  the `CliDeps` field `decision_port_factory` (plan 0006 T14b defines it with the default `None`; plan 0006 T18a, split from
  T18 by B-471, binds it once T7 and T10 here have merged). No task here touches `src/eng_harness/cli/__init__.py`.

## 4. Verification

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` exists; until then, from `packages/eng-harness/`,
  `uv run ruff format --check`, `uv run ruff check`, `uv run mypy --strict src tests`, `uv run pytest` with coverage.
  The pull request links its CI run; local output is not evidence (process/05 §8).
- Windows CI job: `tests/perf/test_rule_latency.py` and the SQLite store tests.
- Needs local test (listed in `docs/local-testing.md` by T10; no host program is involved): (1) the rule-decision p95
  and the cost of a label write on the owner's workstation disk with antivirus active; (2) a decision pending across a
  forced engine kill and a resume on the owner's machine; (3) with phase 2, the provider checks (spike S-07, Jev,
  PydanticAI), which this plan does not cover.
- Engineering content: no rule ships here; the first real rules (spec 0007) go to the owner for review. The policy
  defaults golden file is R1 and goes to the owner queue.
- Review: each pull request by a subagent that did not write it, with the correctness, Python, type-design,
  silent-failure and test lenses; T3, T6 and T8 also with the security lens (what leaves the machine, label content);
  T4, T7 and T8 against the R1 rules of the spec. Second-family review and owner approvals are `awaiting owner`.

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; a revert removes it and its dependants (T7 to T10 depend
on earlier tasks). Before T10 nothing in the engine calls the cascade. After runs have recorded labels, a defect in the
store is fixed forward: `decisions.sqlite` rows are never rewritten, and the table schema carries a `schema_version`
in a `meta` table that a reader must still read.
