---
id: plan-b074-providers
issue: "B-074"
spec: packages/eng-harness/docs/specs/0009-providers.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r3]           # binding for every pull request of this plan; r3 for providers/** and pyproject.toml, r1 for the golden files
tasks:
  - id: T1
    title: Dependencies, provider errors, configuration, network guard
    files:
      - "packages/eng-harness/pyproject.toml"
      - "uv.lock"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/interfaces.py"
      - "packages/eng-harness/src/eng_harness/providers/__init__.py"
      - "packages/eng-harness/src/eng_harness/providers/_config.py"
      - "packages/eng-harness/tests/conftest.py"
      - "packages/eng-harness/tests/unit/providers/test_config.py"
      - "packages/eng-harness/tests/unit/providers/test_errors.py"
      - "packages/eng-harness/tests/contract/test_no_network.py"
      - "packages/eng-harness/tests/contract/test_provider_dependencies.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/providers/test_config.py::test_valid_tables_and_refusals"
      - "packages/eng-harness/tests/unit/providers/test_config.py::test_endpoint_rules"
      - "packages/eng-harness/tests/unit/providers/test_config.py::test_secret_keys_refused"
      - "packages/eng-harness/tests/unit/providers/test_config.py::test_timeout_ceiling"
      - "packages/eng-harness/tests/unit/providers/test_errors.py::test_error_shape"
      - "packages/eng-harness/tests/contract/test_no_network.py::test_non_loopback_connect_is_refused"
      - "packages/eng-harness/tests/contract/test_provider_dependencies.py::test_declared_and_locked"
    covers: [AC1, AC2, AC3, AC4, AC5, AC36, AC46]
    depends_on: []
  - id: T2
    title: Credential store, backend allow-list, key management entry point
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/providers/__init__.py"
      - "packages/eng-harness/src/eng_harness/providers/_credentials.py"
      - "packages/eng-harness/src/eng_harness/providers/__main__.py"
      - "packages/eng-harness/tests/fakes/credential_stores.py"
      - "packages/eng-harness/tests/unit/providers/test_credentials.py"
      - "packages/eng-harness/tests/unit/providers/test_credentials_cli.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/providers/test_credentials.py::test_store_only_no_environment"
      - "packages/eng-harness/tests/unit/providers/test_credentials.py::test_backend_allow_list"
      - "packages/eng-harness/tests/unit/providers/test_credentials_cli.py::test_set_key_status_delete"
    covers: [AC6, AC7, AC8]
    depends_on: [T1]
  - id: T3
    title: Shared HTTP client, error mapping, outgoing guard
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/providers/_http.py"
      - "packages/eng-harness/src/eng_harness/providers/_outgoing.py"
      - "packages/eng-harness/tests/unit/providers/test_http.py"
      - "packages/eng-harness/tests/unit/providers/test_outgoing.py"
      - "packages/eng-harness/tests/property/test_provider_properties.py"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/providers/test_http.py::test_key_only_in_authorization_header"
      - "packages/eng-harness/tests/unit/providers/test_http.py::test_error_mapping"
      - "packages/eng-harness/tests/unit/providers/test_http.py::test_one_request_no_retry_no_redirect"
      - "packages/eng-harness/tests/unit/providers/test_http.py::test_no_secret_or_body_in_logs_or_errors"
      - "packages/eng-harness/tests/unit/providers/test_http.py::test_missing_key"
      - "packages/eng-harness/tests/unit/providers/test_outgoing.py::test_final_body_scan"
      - "packages/eng-harness/tests/unit/providers/test_outgoing.py::test_adapter_rechecks_state"
      - "packages/eng-harness/tests/property/test_provider_properties.py::test_sensitive_text_never_reaches_the_transport"
    covers: [AC9, AC10, AC11, AC12, AC13, AC14, AC15]
    depends_on: [T2]
  - id: T4
    title: Jev adapter over a format boundary; formats not implemented until S-07
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/providers/_jev.py"
      - "packages/eng-harness/src/eng_harness/providers/_jev_format.py"
      - "packages/eng-harness/tests/unit/providers/test_jev.py"
      - "packages/eng-harness/tests/fakes/jev_formats.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/providers/test_jev.py::test_formats_not_implemented_until_s07"
      - "packages/eng-harness/tests/unit/providers/test_jev.py::test_operations_go_through_the_format"
      - "packages/eng-harness/tests/unit/providers/test_jev.py::test_second_format_needs_no_adapter_change"
      - "packages/eng-harness/tests/unit/providers/test_jev.py::test_wire_knowledge_is_in_one_module"
      - "packages/eng-harness/tests/unit/providers/test_jev.py::test_answer_validation"
      - "packages/eng-harness/tests/unit/providers/test_jev.py::test_batch_single_request"
      - "packages/eng-harness/tests/unit/providers/test_jev.py::test_provider_info"
    covers: [AC16, AC17, AC18, AC19, AC20]
    depends_on: [T3]
  - id: T5
    title: Strict output type and prompt for the language-model tier
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/providers/_llm_types.py"
      - "packages/eng-harness/src/eng_harness/providers/_prompts.py"
      - "packages/eng-harness/tests/unit/providers/test_llm_types.py"
      - "packages/eng-harness/tests/unit/providers/test_prompts.py"
      - "packages/eng-harness/tests/data/golden/llm_prompt_v1.txt"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/providers/test_llm_types.py::test_output_type_is_strict"
      - "packages/eng-harness/tests/unit/providers/test_prompts.py::test_prompt_matches_golden"
      - "packages/eng-harness/tests/unit/providers/test_prompts.py::test_injected_label_stays_in_data"
    covers: [AC21, AC22]
    depends_on: [T1]
  - id: T6
    title: PydanticAI adapter (the only importer), conformance of both adapters
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/providers/_llm.py"
      - "packages/eng-harness/tests/unit/providers/test_llm.py"
      - "packages/eng-harness/tests/contract/test_decision_providers.py"
      - "packages/eng-harness/tests/fakes/recorded_providers.py"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/providers/test_llm.py::test_valid_and_invalid_outputs"
      - "packages/eng-harness/tests/unit/providers/test_llm.py::test_agent_is_closed"
      - "packages/eng-harness/tests/unit/providers/test_llm.py::test_cancellation_and_ceiling"
      - "packages/eng-harness/tests/unit/providers/test_llm.py::test_local_and_remote_endpoints"
      - "packages/eng-harness/tests/contract/test_decision_providers.py::test_adapters_conform"
    covers: [AC23, AC24, AC25, AC26, AC27]
    depends_on: [T3, T4, T5]
  - id: T7
    title: Provider factory, local_only, run summary
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/providers/__init__.py"
      - "packages/eng-harness/src/eng_harness/providers/_factory.py"
      - "packages/eng-harness/tests/unit/providers/test_factory.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/providers/test_factory.py::test_local_only_builds_nothing_remote"
      - "packages/eng-harness/tests/unit/providers/test_factory.py::test_summary_has_no_secrets"
      - "packages/eng-harness/tests/unit/providers/test_factory.py::test_absent_provider_is_phase1_behavior"
    covers: [AC28, AC29, AC30]
    depends_on: [T2, T4, T6]
  - id: T8
    title: Evaluation core (thresholds, metrics, eligibility)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/evaluation.py"
      - "packages/eng-harness/tests/unit/decisions/test_evaluation.py"
      - "packages/eng-harness/tests/data/golden/evaluation_thresholds_defaults.json"
      - "packages/eng-harness/tests/data/golden/evaluation_fixture_report.json"
    max_changed_lines: 350
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/decisions/test_evaluation.py::test_thresholds_defaults_and_bounds"
      - "packages/eng-harness/tests/unit/decisions/test_evaluation.py::test_metrics_match_fixture"
      - "packages/eng-harness/tests/unit/decisions/test_evaluation.py::test_eligibility_and_boundaries"
      - "packages/eng-harness/tests/unit/decisions/test_evaluation.py::test_override_counts_as_disagreement"
    covers: [AC37, AC38, AC39, AC40]
    depends_on: [T1]
  - id: T9
    title: Evaluation store, release verification, evaluate command
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/decisions/evaluation.py"
      - "packages/eng-harness/src/eng_harness/decisions/_evalstore.py"
      - "packages/eng-harness/tests/unit/decisions/test_evalstore.py"
      - "packages/eng-harness/tests/unit/decisions/test_evaluation_cli.py"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/decisions/test_evalstore.py::test_append_only_and_reproducible"
      - "packages/eng-harness/tests/unit/decisions/test_evalstore.py::test_verify_releases"
      - "packages/eng-harness/tests/unit/decisions/test_evaluation_cli.py::test_evaluate_writes_record_only"
      - "packages/eng-harness/tests/unit/decisions/test_evaluation_cli.py::test_evaluate_from_export"
    covers: [AC41, AC42, AC43, AC44]
    depends_on: [T8]
  - id: T10
    title: Runtime assembly, shadow-mode workflow, replay and isolation tests, local-testing notes
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/src/eng_harness/providers/__init__.py"
      - "packages/eng-harness/src/eng_harness/providers/_runtime.py"
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py"
      - "packages/eng-harness/tests/replay/test_provider_replay.py"
      - "packages/eng-harness/tests/rules/test_provider_imports.py"
      - "packages/eng-harness/tests/data/recordings/**"
    max_changed_lines: 200
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py::test_timeouts_fall_through"
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py::test_one_screen_with_both_suggestions"
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py::test_decide_many_one_batched_screen"
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py::test_provider_outage"
      - "packages/eng-harness/tests/replay/test_provider_replay.py::test_resume_does_not_requery_providers"
      - "packages/eng-harness/tests/rules/test_provider_imports.py::test_isolation"
    covers: [AC31, AC32, AC33, AC34, AC35, AC45]
    depends_on: [T7, T9]
---

# Implementation plan: eng-harness provider layer (spec 0009)

## 1. Approach

Build the safety surfaces first and the adapters on top of them, so that no adapter ever exists without its guards:
configuration, the error type and the no-network fixture (T1); the credential store (T2); the shared HTTP client with
the key placement, error mapping and outgoing guard (T3); then the two adapters (T4 Jev behind a format boundary, T5 and
T6 the language-model tier); the factory with `local_only` (T7); and, independent of the adapters, the evaluation that
gates the exit from shadow mode (T8, T9). T10 assembles the runtime, runs the shadow-mode workflow, replay and isolation
tests, and writes the local-testing notes. Nothing here needs a host program, the network, a key or a real credential
store; the first commit of every task holds the failing tests, run against recorded transports and fake providers.

The Jev wire format is deliberately not written: spike S-07 decides it and needs the owner's network and key (spec §4.6,
gap J-G1). T4 builds the whole adapter against test-double formats and makes both real backends raise
`NOT_IMPLEMENTED` with a test that expects it. When the S-07 report is merged, this plan is amended with one more task
(the format module for the chosen backend, its recordings, and an ADR if `typesafe-sdk` is used); no other module changes.

Reuse (spec §2): the cascade, `ProviderRequest`, redaction function, label store and `ShadowRelease` of plan 0005; the
engine's ports and the recorded-fake pattern; the contract's `payload_sha256`, `Clock`, `Timestamp` and `ContractError`;
the standard-library `sqlite3`; PydanticAI's `FunctionModel`/`TestModel` and `httpx2.MockTransport` for doubles. T1 adds
the public modules `eng_harness.providers` and `eng_harness.decisions.evaluation` to `[tool.eng-gate] public_modules`,
and `_outgoing.py`, `_credentials.py`, `_http.py`, `evaluation.py` and `_evalstore.py` to the mutation module list
(score at least 80%); the gate profile keys follow the merged gate spec, as in plan 0005 T1.

## 2. Tasks

**T1 Dependencies, errors, configuration, network guard** (spec §4.2, §4.3, §4.11). Adds the three runtime dependencies
with their package ADRs (`docs/adr/0001` to `0003`, status Proposed, owner review), `ProviderErrorCode`, `ProviderError`
and `ProviderFailure` to `decisions/interfaces.py`, the `[providers.*]` models with endpoint, secret-key and timeout
rules, and the autouse fixture that refuses non-loopback connections and PydanticAI model requests for the whole test
tree. The only task that touches `pyproject.toml` and `uv.lock` (risk floor r3). The lock must show `pydantic-ai-slim`
at an exact version; the HTTP library is the one the pinned `pydantic-ai-slim` and `openai` resolve to (ADR-0003 names
`httpx2`; if the lock differs, the ADR is amended in this pull request).

**T2 Credentials** (spec §4.4). `CredentialStore`, `KeyringCredentialStore` with the allow-list and the direct use of
one concrete backend (class names confirmed against the pinned `keyring`), `FakeCredentialStore` in `tests/fakes/`,
and `python -m eng_harness.providers` with `set-key`, `delete-key` and `status` (`check` arrives with T7). No key is
ever accepted as an argument.

**T3 Shared HTTP client and outgoing guard** (spec §4.5). The `httpx2` client with redirects off and a bearer auth hook,
the error mapping table, the one-request rule, the final-body scan and the direct-call state recheck, plus the log and
exception tests with the real stack and the property test with sensitive strings. R3 and the security lens apply.

**T4 Jev adapter** (spec §4.6). `JevFormat`, `HttpCall`, `JevProvider` and `select_format`, which raises
`NOT_IMPLEMENTED` for both backends, in `_jev_format.py`; test-double formats in `tests/fakes/jev_formats.py` with
different wire shapes; answer validation, batching, `info`.

**T5 Output type and prompt** (spec §4.7). The per-request strict output model and the rendered messages with the
golden prompt file (R1: it shapes decisions; owner review), `PROMPT_VERSION`, the injection test.

**T6 PydanticAI adapter** (spec §4.7). The only importer of PydanticAI: agent with no tools, strict tool output, zero
output retries, no instrumentation, over the shared client; cancellation and ceiling; the recorded providers of
`tests/fakes/recorded_providers.py`; the conformance suite for fakes and both adapters.

**T7 Factory** (spec §4.1, §4.4, §4.8). `build_providers`: config to providers, `local_only` builds nothing remote and
reads no key, absent or failing providers become `None` with a warning, the summary for the run header, the `check`
subcommand; sets the third-party logger levels.

**T8 Evaluation core** (spec §4.10). `EvalThresholds` with the 12 §6 and 12 §3 values (golden file citing them),
`evaluate_point` (pure), eligibility with the explicit calibration gap, override handling. R1: the thresholds and the
fixture report go to the owner queue.

**T9 Evaluation store and release** (spec §4.10). `evaluations.sqlite` with append-only triggers, `verify_releases` and
`ReleaseFinding`, the `evaluate` command with `--from-export`; it writes no configuration.

**T10 Assembly and acceptance** (spec §4.9, §4.11). `assemble_decision_runtime` (providers, verified releases, summary),
the fake-host workflow tests with the real engine and cascade (one screen, batching, outage, timeouts), the replay test,
the import-isolation test (not vacuous: it requires the modules), recordings, and the items of spec §9 in
`docs/local-testing.md`. Waits for the engine's `_decide` wiring (plan 0005 T10).

## 3. Dependencies

- Runtime (new, each with a package ADR in this pull request, status Proposed, for the owner to accept before T1 merges
  its lock change): `pydantic-ai-slim` with the `openai` extra ([ADR-0001](../adr/0001-pydantic-ai-slim.md)), `keyring`
  ([ADR-0002](../adr/0002-keyring.md)), `httpx2` ([ADR-0003](../adr/0003-httpx2.md)). Licenses: MIT, MIT, BSD-3-Clause
  (allowed, process/04 §7). Transitive licenses are checked by the gate's license step.
- Development: none new (Hypothesis, pytest and the coverage plugin from engine plan T1; PydanticAI's test models and
  `httpx2.MockTransport` ship with the runtime dependencies).
- Work items: plan 0005 (B-064) T3 (redaction), T5 (interfaces, fakes), T6 (label store), T8 (cascade tiers), T9
  (`decide_many`) and T10 (engine wiring) merged before the tasks that need them (T1 needs T5 for `interfaces.py`; T8
  needs T6; T10 needs T9 and T10 there); engine plan T1, T2 and T6; spec 0006 to read `[providers.*]` and to call
  `assemble_decision_runtime` (its amendment, spec Q7). Spike S-07 is not a dependency of this plan; it gates the later
  format task.
- Amendments requested in other documents (spec Q7) are made in their own pull requests, not here.

## 4. Verification

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` exists; until then, from `packages/eng-harness/`,
  `uv run ruff format --check`, `uv run ruff check`, `uv run mypy --strict src tests`, `uv run pytest` with coverage. The
  pull request links its CI run; local output is not evidence (process/05 §8).
- Windows CI job: the credential-store tests with the in-memory backend double and the evaluation store tests. The real
  Windows Credential Manager is not exercised in CI.
- Needs local test (spec §9, listed in `docs/local-testing.md` by T10; no host program is involved): (1) spike S-07 (Jev
  access, format, batching, latency, confidence, data terms); (2) set a key with `set-key`, run, `status`, `delete-key`,
  and search the workspace and logs for the key on the owner's machine; (3) one live structured-output call through
  OpenRouter with the chosen model, and with a local OpenAI-compatible server; (4) a run with the network disconnected;
  (5) a shadow-mode run showing one engineer screen with both suggestions; (6) the first `evaluate` over real labels.
- Engineering content: the golden prompt (T5) and the evaluation thresholds and fixture report (T8) are R1 and go to the
  owner queue with the calibration metric (spec Q4); no release exists, and none can be made by `evaluation` basis until
  calibration is defined.
- Review: each pull request by a subagent that did not write it, with the correctness, Python, type-design,
  silent-failure and test lenses; T1 to T3, T6, T7 and T10 also with the security lens (what leaves the machine, where a
  key can appear); T5, T8 and T9 against the R1 rules. Second-family review and owner approvals are `awaiting owner`.

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`; a revert removes it and its dependants. Before T10 nothing
in the engine constructs a provider, and with no `[providers.*]` table the harness behaves as in phase 1 (spec AC1), so
reverting the whole plan changes no run. Keys live in the operating system's credential store, outside the repository:
a revert does not remove them, and `python -m eng_harness.providers delete-key` (T2) does. `evaluations.sqlite` rows are
never rewritten; a defect in evaluation is fixed forward and the affected records are superseded by new ones, so a
release that depended on one fails verification and the point returns to shadow mode.
