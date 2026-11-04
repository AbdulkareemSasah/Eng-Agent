---
id: spec-0005-decisions
issue: "B-064"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: r1
---

# Spec 0005: eng-harness decision layer (points, policy, rules, cascade, labels)

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-04

This spec implements the `DecisionPort` of the engine ([spec 0001](0001-engine.md) §4.8) for
[12-decision-layer](../../../../design/docs/architecture/12-decision-layer.md) ("12 §n"), with the phasing of
[ADR-0025](../../../../design/docs/adr/0025-first-workflow-edit-cycle.md) decision 5: **phase 1 decides with rules
(tier 1) and the engineer (tier 4) only.** The decision-model and language-model tiers (2 and 3) are specified here as
interfaces and semantics, with no implementation and no network code; their implementations (Jev in shadow mode,
PydanticAI behind `LLMProvider`, [ADR-0012](../../../../design/docs/adr/0012-decision-cascade-and-provider-layer.md),
[ADR-0013](../../../../design/docs/adr/0013-pydanticai-behind-interface.md)) come in phase 2. It does not repeat 12 or
the engine spec: it names the section and adds what an implementer and a reviewer need. Details that 12 leaves open are
marked **[added]** and listed in §11. The contract API it uses is
[eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract §n"); the redaction rules
come from [16 §2](../../../../design/docs/architecture/16-security-safety-privacy.md) and the evaluation rules from
[process/05 §7](../../../../design/process/05-testing-and-verification.md).

## 1. Problem

Workflows reach points where the next step depends on a judgment: which fix to try after a failed design check, which
candidate matches. Without a decision layer each block either hard-codes the choice, asks the engineer every time, or
(the failure of the earlier project) calls a language model for everything. The engine already fixes the contract
(`ctx.decide`, `ctx.decide_many`, invariant 4: a decision returns an enum member or an index, never a number); nothing
yet resolves a decision, records who decided it, keeps the engineer's answers for later evaluation, or stops project
data from leaving the machine. Every workflow of phase 1 onward depends on it, and the rules it evaluates are
engineering content (R1) that the owner reviews.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| PydanticAI, Jev, OpenRouter clients | Needed only for tiers 2 and 3 (phase 2, ADR-0013, spike S-07) | Not used here; interfaces only, so phase 2 adds adapters without touching the cascade |
| Rules engines (`durable-rules`, `business-rules`, `experta`) | Rules here are ordered pure Python functions with an id and a rationale (12 §1); a rules language adds a dependency and hides the code the owner must review | Not used |
| `sqlite3`, `asyncio`, `hashlib` (standard library) | Enough for the label store, timeouts and hashing; the journal already uses SQLite | Used; no new runtime dependency |
| Engine spec 0001: registry with lock file, code hash, guard, `Ctx` types | Same pattern fits points and rules | Reused (§4.2, §4.4) |
| Contract: `canonical_json`, `payload_sha256`, `Ref`, `Quantity`, `Timestamp`, `ContractError` | State hashing, references, threshold comparison | Reused |

## 3. Acceptance criteria

Test files are under `packages/eng-harness/tests/`. "Fake provider" is a test double implementing the interfaces of §4.7
(lead decision D-5: test doubles live in `tests/`, never shipped).

### 3.1 Decision points and state

- AC1. Given a point definition, when it is created, then it is refused with `DecisionDefinitionError` naming the rule
  unless: `name` matches `^[a-z][a-z0-9_]{2,63}$`; `version` matches `^[1-9][0-9]{0,3}$`; options are a `StrEnum`
  with 1 to `max_options` members whose values match `^[a-z][a-z0-9_]*$`, or `refs` with a `labels_field`; `state` is a
  frozen Pydantic model with `extra="forbid"`; and, in a registry, the name is unique. Test:
  `tests/unit/decisions/test_points.py::test_definition_rules`.
- AC2. Given a state model, when the point is created, then every field type must be `bool`, `int`, a finite `float`,
  a `StrEnum`, `Label`, `Quantity`, `Ref`, or a tuple of these, or a nested state model of these; `str`, `bytes`,
  `Path`, `dict`, `Any` and unbounded collections are refused. Test: `test_points.py::test_state_field_types`.
- AC3. Given a call whose canonical state exceeds `max_state_bytes`, then `BlockRuleViolation`. Test:
  `test_points.py::test_state_size_limit`.
- AC4. Given a lock entry `{name, version, schema_sha256}` and a point with the same name and version but another
  options or state schema, when `check_lock` runs, then it reports `VERSION_BUMP_REQUIRED`; and the committed
  `src/eng_harness/decisions.lock.json` matches the real registry. Tests: `test_points.py::test_check_lock`,
  `tests/contract/test_decision_lock.py::test_lock_matches_registry`.
- AC5. Given a `ctx.decide` call whose `question` is not a registered point, whose options differ from the point's, whose
  state is not an instance of the point's state model, or (refs) whose options count is 0 or above `max_options` or does
  not equal the length of the `labels_field`, then `BlockRuleViolation` and nothing is evaluated or sent. Test:
  `tests/unit/decisions/test_cascade.py::test_call_validation`.

### 3.2 Policy

- AC6. Given `DecisionPolicy()`, then `model=True`, `llm=False`, `min_confidence=0.85`, `shadow=True`,
  `timeout_ms_model=1500`, `timeout_ms_llm=20000`, `require_engineer=False`, equal to the golden file
  `tests/data/golden/decision_policy_defaults.json`, whose source is 12 §3 (cited in the file). Test:
  `tests/unit/decisions/test_policy.py::test_defaults_match_golden`.
- AC7. Given `min_confidence` below 0.85 or above 1.0, a timeout below 1, an unknown field, or a mutation after
  construction, then `ValidationError`. Test: `test_policy.py::test_policy_bounds`.
- AC8. Given `policy.shadow=False` for a point that has no `ShadowRelease` for its current name and version in
  `DecisionSettings.shadow_released`, then tiers 2 and 3 still run in shadow mode (never decide). Test:
  `tests/unit/decisions/test_cascade.py::test_shadow_needs_release`.

### 3.3 Rules and the registry

- AC9. Given `@rule(...)`, then registration is refused with `DecisionDefinitionError` unless: `id` matches
  `^[a-z][a-z0-9_]{2,63}\.[a-z][a-z0-9_]*$` and its prefix equals `point`; `rationale` is a `Rationale` (no digit in
  any script); every `thresholds` entry is a basis path of contract §4.10.2; `fn` is a plain synchronous function whose
  first parameter is annotated with the point's state model; ids are unique; and the module source is readable. Test:
  `tests/unit/decisions/test_rules.py::test_registration_rules`.
- AC10. Given a registered rule, then its `code_sha256` is the SHA-256 of its module source with LF line endings
  (engine spec §4.2), stable across two interpreter runs; and `check_lock` against `src/eng_harness/rules.lock.json`
  reports `VERSION_BUMP_REQUIRED` for a changed hash with an unchanged version. Tests:
  `test_rules.py::test_code_hash_is_stable`, `tests/contract/test_rule_lock.py::test_lock_matches_registry`.
- AC11. Given a rule that reads a basis path not in its `thresholds`, then `BlockRuleViolation`; given a declared path,
  then `RuleBasis.quantity(path)` returns the basis `Quantity` and two quantities of one dimension compare. Test:
  `test_rules.py::test_rule_basis_is_restricted`.
- AC12. Given every registered rule, then `tests/rules/test_<module>.py` contains `test_<name>_typical` and
  `test_<name>_boundary` (process/10 §4: "tests with typical and boundary states"); a rule without both fails the
  contract test. Test: `tests/contract/test_rule_tests_exist.py::test_every_rule_has_typical_and_boundary_tests`.
- AC13. Given `RuleRegistry.review_table()`, then it returns one row per rule with `id`, `point`, `version`,
  `rationale`, `thresholds`, `code_sha256` and the approval state read from `approvals.yaml` (`draft` when absent), for
  the owner's review. Test: `test_rules.py::test_review_table`.

### 3.4 The cascade (single decision)

- AC14. Given rules `[r1, r2]` and a state both match, when `decide` runs, then the answer is `r1`'s, `decided_by` is
  `rule:<id>`, `confidence` is `None`, `r2` and every provider are not called, and no engineer screen is created. Test:
  `tests/unit/decisions/test_cascade.py::test_first_matching_rule_wins`.
- AC15. Given a rule that returns an option outside the options, returns something other than `Pick` or `None`, or
  raises, then `DecisionInvalid` (`DECISION_INVALID`, with the rule id), later rules are not tried, and nothing falls
  through silently. Test: `test_cascade.py::test_bad_rule_fails_the_step`.
- AC16. Given a rule that opens a file, opens a socket or imports a module, when it runs under the real engine, then
  `BlockRuleViolation`; the rules run inside the engine's guard (engine spec §4.3.4 rule 1). Test:
  `tests/workflow/decisions/test_engine_decisions.py::test_rules_run_under_the_guard`.
- AC17. Given no rule matches and no provider is configured (the phase 1 deployment, whatever the policy), when
  `decide` runs, then a `PendingAnswer` is returned with a screen holding the options, the redacted state fields and
  no suggestions; no socket is opened; when the call is repeated with an `EngineerChoice` that is one of the options,
  then the answer has `decided_by` `engineer:<name>` and a label is stored. Test:
  `test_cascade.py::test_phase1_rules_then_engineer`; with the real engine,
  `test_engine_decisions.py::test_engineer_decision_pauses_and_resumes`.
- AC18. Given an `EngineerChoice` that is not one of the options, then the same `PendingAnswer` (same `request_id`) is
  returned with `rejected="not_an_option"`, and nothing is stored. Test: `test_cascade.py::test_invalid_engineer_choice`.
- AC19. Given a `PendingAnswer` already stored for the `request_id`, when `decide` is called again, then the stored
  screen is returned and no rule or provider is called again; once answered, a further call returns the same answer
  without a second label. Test: `test_cascade.py::test_pending_is_idempotent`.
- AC20. Given a decision recorded in the journal, when the run is resumed and replayed, then the recorded answer is
  returned without evaluating rules or calling providers, and an engineer decision pending at a crash is presented
  again with the same `request_id`. Tests: `tests/replay/test_decision_replay.py::test_replay_does_not_requery`,
  `::test_crash_while_pending`.

### 3.5 Tiers 2 and 3 and shadow mode (behavior against fake providers)

- AC21. Given a fake `DecisionProvider`, `policy.model=True`, effective shadow off (AC8) and a confidence at least
  `min_confidence` for an option in the options, then the answer is the provider's, `decided_by` is
  `model:<provider>/<model>@<version>`, `confidence` is set; given a confidence below the threshold, then the answer
  is not taken, the suggestion is recorded with outcome `below_threshold`, and the cascade moves on. Test:
  `test_cascade.py::test_tier2_threshold`.
- AC22. Given a provider that times out (after `timeout_ms_model`), raises, returns a choice outside the options, or a
  confidence that is not a finite number in [0, 1], then the suggestion is recorded with outcome `timeout`, `error` or
  `invalid`, nothing is raised, and the cascade moves on. The recorded error is the exception class name and the
  provider's code, never its message. Test: `test_cascade.py::test_provider_failures_fall_through`.
- AC23. Given a fake `LLMProvider`, `policy.llm=True`, effective shadow off, tier 2 not accepted, and an answer with a
  valid option and a `Rationale`, then the answer is the LLM's with `decided_by` `llm:<...>`; an answer whose rationale
  contains a digit, or an option outside the options, is `invalid` and the engineer is asked. Test:
  `test_cascade.py::test_tier3_rationale_and_option`.
- AC24. Given effective shadow on, `policy.model` and `policy.llm` true and both fakes present, when no rule matches,
  then both providers are called, their suggestions are recorded with outcome `shadow` and shown on the screen, the
  answer is the engineer's, and exactly one engineer prompt is created. Test: `test_cascade.py::test_shadow_mode`.
- AC25. Given `policy.require_engineer=True`, when no rule matches, then no provider is called and the engineer is
  asked; given `policy.model=False` or `policy.llm=False`, then that tier is not called. Test:
  `test_cascade.py::test_policy_switches`.
- AC26. Given `DecisionSettings.local_only=True` and a provider whose `info.is_local` is false, then it is not called
  and the suggestion is recorded with outcome `skipped_local_only`; a local provider is called normally. Test:
  `test_cascade.py::test_local_only`.

### 3.6 `decide_many`

- AC27. Given N calls of which some match rules, when `decide_many` runs with a batching provider, then rules run per
  call, the unresolved calls go to the provider in one `batch` request (a provider without `supports_batch` gets
  concurrent `choose` calls, at most `max_concurrent_decisions`), and the answers come back in call order. Test:
  `tests/unit/decisions/test_batch.py::test_batching_and_order`.
- AC28. Given unresolved calls after the tiers, then exactly one screen with all of them is created (one `batch_id`, one
  engineer prompt), the engine pauses once, and a resume with `EngineerChoice` for every call returns all answers; an
  answer set that misses a call, or has an invalid one, is refused and the whole screen presented again. Test:
  `test_batch.py::test_one_screen_all_or_nothing`.
- AC29. Given a pause in a batch, when the call is repeated, then resolved members are returned from the stored
  outcomes and no provider is called again for any `request_id`. Test: `test_batch.py::test_resume_does_not_requery`.

### 3.7 The record

- AC30. Given any answer, then the `decision_made` payload of 12 §5 is complete: `point`, `options` (the option values,
  or `"0"` to `"n-1"` for refs), `choice`, `decided_by` (`rule:<id>`, `model:...`, `llm:...`, `engineer:<name>`),
  `confidence`, `latency_ms`, `state_sha256` (`payload_sha256` of the state's canonical JSON), and `suggestions` as in §4.9;
  no state value appears in it. Test: `tests/workflow/decisions/test_engine_decisions.py::test_decision_made_record`.
- AC31. Given a decision by a rule, then `suggestions` holds its entry with `rule_sha256` and the rule `version`, so a
  later change of the rule is visible in the journal. Test: `test_cascade.py::test_rule_entry_has_hash`.

### 3.8 Redaction

- AC32. Given a state model with a field whose name has a token of the deny list of §4.10 (for example `project_name`,
  `client`, `file_path`), or a `Label` annotation weakened to `str`, when the point is created, then
  `DecisionDefinitionError`. Test: `tests/unit/decisions/test_redaction.py::test_by_construction`.
- AC33. Given a state value that looks like a path, a URL or an email address, that contains a value of
  `DecisionSettings.sensitive_values`, or that is longer than the label bound, when a tier 2 or 3 would receive it, then
  the provider is not called, the suggestion is recorded with outcome `skipped_redaction` and the field paths, and the
  engineer is asked; the findings contain paths and reasons, never values. Test:
  `test_redaction.py::test_runtime_check_blocks_send`; property test
  `tests/property/test_decision_properties.py::test_sensitive_text_never_reaches_a_provider`.
- AC34. Given `Ref` fields, then they are omitted from the outgoing state and shown on the engineer screen as
  references. Test: `test_redaction.py::test_refs_not_sent`.

### 3.9 Labeled examples

- AC35. Given an engineer answer, then a label row `{label_id, request_id, point, point_version, run_id, step_path,
  options, state, state_sha256, label, engineer, suggestions, source, created_at}` is appended to
  `<workspace>/decisions/decisions.sqlite` before the answer is returned; `UPDATE` and `DELETE` on `labels` fail; a
  second insert with the same `request_id` is ignored. Test: `tests/unit/decisions/test_labels.py::test_append_only`.
- AC36. Given a state that fails the redaction check, then the label stores `state_sha256` only and `state` is null.
  Test: `test_labels.py::test_unredactable_state_hash_only`.
- AC37. Given a failed label write, then the step fails with `ContractError` `INTERNAL` and the pending request stays
  presented, so no engineer decision is lost or unrecorded. Test: `test_labels.py::test_write_failure_is_loud`.
- AC38. Given `record_override(request_id, new_choice, by)` for a decision taken by a rule, model or LLM, then a label
  with `source="engineer_override"` is appended; for an unknown `request_id`, `NOT_FOUND`. Test:
  `test_labels.py::test_override_label`.
- AC39. Given `export_labels(point, folder)`, then it is refused (`INVALID_ARGUMENT`, field `export_enabled`) unless
  `DecisionSettings.export_enabled`; when enabled it writes one canonical-JSON line per label with `state` only where
  the redaction check passed, and never `engineer`, `run_id` or `step_path`. Test: `test_labels.py::test_export_is_opt_in`.

### 3.10 Package-level

- AC40. Given 1,000 rule decisions through the cascade (no journal, no store), then p95 is under 1 ms (12 §1). Test:
  `tests/perf/test_rule_latency.py::test_rule_decision_p95` (also in the Windows CI job).
- AC41. Given the interfaces of §4.7, then one conformance test runs against the fake providers; and the cascade passes
  the engine's shared `DecisionPort` conformance test (engine spec AC57). Tests:
  `tests/contract/test_decision_providers.py::test_fake_providers_conform`,
  `tests/contract/test_decision_port.py::test_cascade_conforms`.
- AC42. Given `eng_harness.decisions.types`, then it imports nothing from `engine`, `journal`, `ports`, a network or
  database module, and block and rule modules may import it (amendment of engine spec §4.1.2, Q1). Test:
  `tests/rules/test_decision_imports.py::test_types_module_is_block_safe`.

## 4. Design

Follows 12 and the engine spec; flow of one decision: engine `_decide` validates options and answer (invariant 4,
engine AC40) and calls `DecisionPort`; the cascade of this spec resolves it.

### 4.1 Modules

`src/eng_harness/decisions/`. Public: `eng_harness.decisions` (cascade, stores, settings; for the engine, the command
line and tests), `eng_harness.decisions.types` (block-safe: `DecisionPolicy`, `Rule`, `rule`, `Pick`, `RuleBasis`,
`Rationale`, `Label`, `DecisionPoint`, `decision_point`), `eng_harness.decisions.interfaces` (`DecisionProvider`,
`LLMProvider`, request and answer models). Private: `_policy.py`, `_points.py`, `_rules.py`, `_redaction.py`,
`_labels.py` (labels and pending), `_cascade.py`, `_batch.py`, `_record.py`. Rule modules of workflows live in
`src/eng_harness/rules/` and policy constants in `src/eng_harness/policies/` (later specs; both are R1 paths in
`.gate/risk-map.yml`). The framework is not in `rules/`, because that glob is subject to the rule-module lint (FB004,
FB005). The directory `src/eng_harness/providers/` (phase 2 implementations) is not created here.

### 4.2 Decision points

```python
@decision_point(
    name="footing_fix_strategy",
    version=1,
    title="Footing fix strategy",
    options=FootingAction,
    state=FootingFailureState,
)
class FootingFixStrategy: ...  # builds an immutable DecisionPoint; no global registration
```

- `DecisionPoint` (frozen): `name`, `version`, `title` (`Label`), `options` (`StrEnum` type, or `Refs(labels_field=...)`),
  `state` (model), `yes_no` (`(yes_value, no_value)` or `None`; only for two-member enums), `schema_sha256`.
- `schema_sha256` is the SHA-256 of the canonical JSON of the option values and the state's JSON schema. A change of
  either without a `version` bump fails the lock check (AC4), like blocks (engine §4.2). `decisions.lock.json` is written
  by `uv run python -m eng_harness.decisions --write-lock`, which refuses to write an entry whose hash changed while its
  version did not.
- `PointRegistry(points)` is immutable (`.with_(...)` returns a new one); the cascade is constructed with one.
- Options: an enum yields option values; refs yield `"0"` to `"n-1"`, labelled by the state's `labels_field` (a tuple of
  `Label` of equal length). The engine maps the chosen value to the member or the `Ref` (engine §4.6 item 4). A
  decision never carries a number (P10).
- State types: AC2. `Label` = `str`, 1 to 80 characters, no control character and none of `/ \ @ :` (so a path, URL or
  address cannot be a label). `Rationale` = `str`, 1 to 300 characters, matching `^\D+$` (no digit in any script: the
  form the gate rule FB006 probes, [gate spec](../../../../tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md)
  §4.8).
- Limits (`DecisionSettings`, software settings, not engineering values): `max_options` 32, `max_state_bytes` 4096.

### 4.3 Policy and settings

`DecisionPolicy` (frozen, `extra="forbid"`): the fields and defaults of 12 §3.

| Field | Default | Source and note |
|---|---|---|
| `model` | `True` | 12 §3. Allows tier 2 |
| `llm` | `False` | 12 §3. Allows tier 3 |
| `min_confidence` | `0.85` | 12 §3. Bounds [0.85, 1.0]: raised per point, never lowered below the default **[added: reading of 12 §6 "thresholds can only be raised"]** |
| `shadow` | `True` | 12 §3. Effective shadow also needs a release (below) |
| `timeout_ms_model` | `1500` | 12 §3 "1500 for tier 2" (12 writes one `timeout_ms` field; split per tier **[added]**) |
| `timeout_ms_llm` | `20000` | 12 §3 "20000 for tier 3" |
| `require_engineer` | `False` | 12 §1 "when the policy requires the engineer" **[added]**: no provider is consulted when no rule matches |

`DecisionSettings` (frozen; read from `harness.toml` by spec 0006): `max_options`, `max_state_bytes`, `local_only`
(16 §2), `sensitive_values` (strings that must never leave the machine: names the engineer or the CLI supplies; the
engine adds the base names of model files the run touches), `extra_denied_tokens` (extends §4.10), `shadow_released`
(`{point name: ShadowRelease(point_version, basis: "evaluation" | "owner", record: str)}`), `export_enabled` (default
`False`).

**Effective shadow** = `policy.shadow or no ShadowRelease for (point.name, point.version)`. A tier 2 or 3 answer can
be accepted only when effective shadow is off. Creating a `ShadowRelease` after an evaluation (12 §6: at least 50
labeled cases, at least 95% agreement above the threshold, acceptable calibration) or by an explicit owner decision for
a low-risk point is phase 2 work; no release exists in phase 1.

### 4.4 Rules and the registry

```python
@rule(
    id="footing_fix_strategy.bearing_only",
    version=1,
    point="footing_fix_strategy",
    rationale="Only the bearing check fails, and a larger plan lowers the bearing pressure.",
    thresholds=("limits.bearing_ratio",),
)
def bearing_only(state: FootingFailureState, basis: RuleBasis) -> Pick[FootingAction] | None: ...
```

- A rule is a pure, synchronous function `(state, basis) -> Pick | None`. `Pick(option)` holds an enum member or an
  `int` index. `None` means no match; the next rule runs. The rules of one call run in the order of the `rules`
  argument of `ctx.decide`, which is the order the workflow spec gives (12 §1).
- Rules follow the rules for block and rule code (11 §3; engine §4.3.4): no I/O, no arithmetic on `Quantity`, no
  numeric literal (thresholds only through `RuleBasis`, FB005), deterministic. `RuleBasis` wraps the call's `BasisView`
  and permits only the paths in `thresholds`; the paths are required basis fields of the workflow (engine invariant 5).
- `rule` builds an immutable `Rule`; `RuleRegistry(rules)` is immutable, checks AC9 and holds `review_table()` (AC13).
  `rules.lock.json` (`[{id, version, code_sha256}]`, sorted by id) mirrors the block lock (AC10).
- Rules are R1 engineering content (process/10 §4): the owner reviews each rule's id, rationale, thresholds and tests. An
  approval is an entry in `approvals.yaml` bound to `code_sha256` (kind `rule`; Q7). In bootstrap mode no agent adds one
  (ADR-0028 §4); every rule is `draft`.
- No rule ships with this spec. Rules for the edit cycle come with spec 0007; tests use rule modules in
  `tests/rules/fixtures/`.

### 4.5 The cascade

`Cascade` implements `DecisionPort`. Construction takes: the `PointRegistry`, `DecisionSettings`, optional
`DecisionProvider` and `LLMProvider` (both `None` in phase 1), a `LabelStore`, a monotonic clock, the contract `Clock`,
`max_concurrent_decisions` (from `EngineSettings`) and a `rule_guard` (a context-manager factory the engine supplies so
rules run in the audit-hook guard; a no-op in unit tests; engine Q in Q1).

Port data (frozen models; engine spec §4.8 names `DecisionPort.decide(request)`, here `request` is a `DecisionCall`):

- `DecisionCall`: `request_id` (engine-derived and stable per step path, as for approvals), `run_id`, `step_path`,
  `point` (the question), `options` (enum type or the refs sequence), `state`, `rules`, `policy`, `basis`,
  `engineer_choice: EngineerChoice | None`.
- `EngineerChoice`: `choice` (option value), `by` (engineer name), `answered_at` (contract `Timestamp`).
- `DecisionAnswer`: `choice`, `decided_by`, `confidence`, `latency_ms`, `options`, `state_sha256`, `suggestions`. The
  engine builds `decision_made` from it.
- `PendingAnswer`: `request_id`, `batch_id`, `screen: DecisionScreen`, `rejected` (`None` or `not_an_option`,
  `incomplete`). `DecisionScreen` is data for spec 0006 to render: per item the point `title`, option values with
  labels, the state as labeled fields, the `Ref` fields, and every suggestion with its tier, source, choice, confidence
  and rationale.

`decide(call)`:

1. Validate the call (AC5); compute `state_sha256` and the redaction findings (§4.10) once.
2. If a pending record exists for `request_id`, go to 6 (AC19).
3. **Tier 1.** For each rule in order: run it under `rule_guard`; `Pick` of a valid option answers
   `rule:<id>` (confidence `None`); an invalid result raises `DecisionInvalid` (AC15); `None` continues.
4. If `policy.require_engineer`, go to 6.
5. **Tiers 2 and 3** (providers present, allowed by the policy, not skipped by §4.10 or `local_only`; every skip is a
   suggestion entry). Effective shadow on: run the allowed tiers concurrently, record outcome `shadow`, accept nothing.
   Effective shadow off: tier 2 first, accepted if the choice is valid and `confidence >= min_confidence` (else
   `below_threshold` and its suggestion goes on); then tier 3, accepted if the choice is valid and the rationale is a
   `Rationale`. Each call runs under `asyncio.timeout` of the policy's timeout and catches `Exception` only (the engine's
   stops and cancellation pass through); failures are recorded, never raised (AC22).
6. **Tier 4.** Without an `EngineerChoice`, store the pending record (with the screen and the suggestions) and return
   `PendingAnswer`. With one, validate it (AC18), append the label (AC35) and answer `engineer:<by>`.

`latency_ms`: monotonic time from step 1 to the answer; for the engineer, `answered_at` minus the pending record's
creation time **[added]** (the wait spans pauses and processes, so a monotonic clock cannot measure it).

### 4.6 Shadow-mode semantics

Shadow mode decides nothing: tier 2 and 3 answers are suggestions, recorded and shown, and the engineer decides, so
evaluation data accumulates without risk (12 §3, ADR-0012). Rules are not shadowed: a matching rule still decides
without asking. The suggestions and the engineer's label are the pairs that a later evaluation compares (§4.11). In
phase 1 there are no providers, so no suggestion exists and the policy flags only take effect from phase 2.

### 4.7 Provider interfaces (no implementation in this spec)

```python
class ProviderInfo(BaseModel):  # frozen
    provider: str
    model: str
    version: str
    is_local: bool
    supports_batch: bool


class ProviderRequest(BaseModel):  # frozen; the only data a provider receives
    request_id: str
    point: str
    point_version: int
    options: tuple[ProviderOption, ...]  # value, label
    state: Mapping[str, JsonValue]  # redaction-checked; no Ref fields


class ChoiceAnswer(BaseModel):
    choice: str
    confidence: float


class YesNoAnswer(BaseModel):
    answer: bool
    confidence: float


class DecisionProvider(Protocol):  # tier 2, 12 §4
    info: ProviderInfo

    async def choose(self, request: ProviderRequest) -> ChoiceAnswer: ...
    async def yes_no(self, request: ProviderRequest) -> YesNoAnswer: ...
    async def score(self, request: ProviderRequest) -> Mapping[str, float]: ...
    async def batch(self, requests: Sequence[ProviderRequest]) -> Sequence[ChoiceAnswer | ProviderFailure]: ...


class LLMAnswer(BaseModel):
    choice: str
    rationale: Rationale


class LLMProvider(Protocol):  # tier 3
    info: ProviderInfo

    async def decide(self, request: ProviderRequest) -> LLMAnswer: ...
```

- `yes_no` is used only for points with `yes_no` set; `choose` otherwise. `score` returns a value per option and is
  used only to order options on the engineer screen, never to choose **[added]**: a score is a number and a decision
  never produces one (P10).
- A provider returns typed answers only; it never calls tools. State text reaches it only as `Label` fields (16 §4).
  Keys, endpoints and credential-store access belong to the implementations (phase 2, 16 §3); the interface has none.
- The cascade, not the provider, enforces timeouts, option validity, the confidence bound, the rationale rule and
  `local_only`.

### 4.8 `decide_many`

`decide_many(calls)` validates all calls, runs tier 1 per call, then tiers 2 and 3 for the unresolved calls: one
`batch` request per provider when `supports_batch`, else concurrent single calls bounded by `max_concurrent_decisions`.
All calls still unresolved share one `batch_id` (`"batch_" + sha256(sorted request ids)[:16]`) and one screen, so the
engine creates one engineer prompt (12 §1, §3). Each pending record also stores the resolved outcomes of the other
calls of the batch, so a resume reuses them and queries no provider twice (AC29). The engineer answers all calls or none
(AC28). Answers return in call order; `decision_made` is appended per call, in call order.

### 4.9 The record

`decision_made` is the payload of engine spec §4.4.2 (`point`, `options`, `choice`, `decided_by`, `confidence`,
`latency_ms`, `state_sha256`, `suggestions`). `suggestions` is a list, in tier order, of the tiers that ran, **including
the one that decided [added]**: `{tier: 1|2|3, by, outcome, choice, confidence, rationale, latency_ms, shadow,
code: {rule_version, rule_sha256}}`. `outcome` is one of `accepted`, `below_threshold`, `shadow`, `invalid`, `error`,
`timeout`, `skipped_local_only`, `skipped_redaction`; unmatched rules and tiers without a provider are not listed.
`by` is `rule:<id>`, `model:<provider>/<model>@<version>` or `llm:<provider>/<model>@<version>`. The payload holds hashes
and option values, never state values (the state is kept only in the label store).

### 4.10 Redaction (16 §2)

By construction (AC32) and at runtime (AC33):

- **Field names.** Tokens of a field name (split on `_`) may not be in: `project`, `client`, `address`, `location`,
  `person`, `author`, `engineer`, `owner`, `user`, `email`, `phone`, `path`, `file`, `folder`, `directory`; settings may
  add tokens, never remove one. These are the "known sensitive fields" of 16 §2.
- **Values**, checked on the serialized state before any tier 2 or 3 call and before a label stores a state: a string
  that matches a drive-letter or rooted path, contains `/` or `\`, a URL scheme or `@`; a string containing a
  `sensitive_values` entry (case-insensitive, length at least 3); a string over the label bound. A finding is
  `{field_path, reason}`; it never carries the value.
- A failing state is never sent (the tier is skipped, AC33) and is stored hash-only (AC36). The check is a pure
  function over JSON values, applied to every outgoing state with no exception.
- `local_only` skips every provider whose `is_local` is false (16 §2).

### 4.11 Labeled examples and pending requests

One SQLite file `<workspace>/decisions/decisions.sqlite` (`STRICT` tables, the contract's `Workspace`; the contract
already refuses a synchronized folder), with the journal's append-only trigger pattern:

- `labels`: columns of AC35; `request_id` unique; triggers forbid `UPDATE` and `DELETE`. `source` is
  `engineer_decision` or `engineer_override`. Labels are the engineer's answers (shadow or not) with the suggestions of
  the other tiers, the pairs an evaluation compares.
- `pending`: `request_id`, `batch_id`, `screen_json`, `outcomes_json`, `created_at`, `closed_at`. Rows are inserted
  and closed (only `closed_at` may change).
- `LabelStore` API: `append`, `record_override`, `read(point, point_version)`, `export_labels(point, folder)`. The
  evaluation itself (agreement above threshold, calibration, abstention rate, latency per provider and model;
  process/05 §7) and the release of a point from shadow mode are phase 2 work (non-goals).
- Export is opt-in (12 §6) and writes anonymized lines for the owner to commit to the harness's `evals/` (Q3).

### 4.12 Engine wiring

The engine's `_decide` ([plan 0001](../plans/0001-engine.md) T14) validates and maps options, journals `decision_made`
from the `DecisionAnswer`, and presents a `PendingAnswer` through the `InputPort` with a request of kind
`engine.decision` (a kind added to engine spec §4.4.2, Q1). `ctx.decide` and `ctx.decide_many` keep the signatures of
engine spec §4.3.2. `DecisionPolicy` and `Rule` are the types of those signatures.

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `DecisionPoint.name` | `str` | — | AC1 | no | workflow code |
| Options | `StrEnum` or refs | — | 1 to `max_options` | refs only | workflow code |
| State fields | AC2 types | per `Quantity` | `max_state_bytes` | `Ref` fields | block (summaries only) |
| `DecisionPolicy.*` | AC6 | ms for timeouts | §4.3 | no | workflow code (`policies/`) |
| `min_confidence` | `float` | ratio | [0.85, 1.0] | no | 12 §3 |
| Rule `thresholds` | basis paths | per basis field | contract §4.10.2 | yes (basis refs) | design basis |
| `EngineerChoice` | option value | — | one of the options | no | spec 0006 page |
| `DecisionAnswer.confidence` | `float` or `None` | ratio | [0, 1] | no | tier 2 only |
| Output choice | option value or index string | — | one of the options | no | cascade |

## 6. Errors

| Condition | Error | Fields |
|---|---|---|
| Unregistered point, options or state mismatch, oversize state, rule reading an undeclared path | `BlockRuleViolation` (`BLOCK_RULE_VIOLATION`) | point, rule id |
| Rule returns an invalid result or raises | `DecisionInvalid` (`DECISION_INVALID`) | rule id |
| Invalid point, rule or policy definition | `DecisionDefinitionError` (a `ValueError`, raised at import or registration) | rule of AC1, AC2, AC9, AC32 |
| Policy field out of bounds | pydantic `ValidationError` | field |
| Label write failure | `ContractError` `INTERNAL` (`StoreWriteError`) | `incident_id` |
| Unknown `request_id` for an override | `ContractError` `NOT_FOUND` | `request_id` |
| Export while disabled | `ContractError` `INVALID_ARGUMENT` | `field: export_enabled` |
| Provider failure, timeout, redaction skip | none: a suggestion with an outcome (AC22, AC33) | — |

## 7. Non-goals

- Any provider implementation, network code, key storage or prompts: Jev (spike S-07) and PydanticAI are phase 2.
- Running evaluations, calibration, and creating or checking a `ShadowRelease`.
- Learning new rules from labels: rules are written and approved by a human, and the system never edits them (12 §6).
- The engineer screen and page (spec 0006), the edit-cycle decision points and rules (spec 0007).
- Decisions that return numbers; engineering arithmetic; DXF layer classification (left phase 1, ADR-0025).
- Telemetry of any kind (16 §2).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A rule encodes a wrong engineering judgment | R1 | Owner review of each rule (id, rationale, thresholds, typical and boundary tests); thresholds only from the basis; `draft` until approved; the rule hash is in every `decision_made` |
| Project data leaves the machine through a decision state | R2 | By-construction field types, runtime check on every outgoing state, `local_only`, hash-only labels, property test |
| A tier 2 or 3 answer is taken before it is evaluated | R1 | Effective shadow needs a recorded release; none exists in phase 1; AC8 |
| A bad rule is skipped silently | R1 | A failing rule fails the step (AC15) |
| Label loss weakens the later evaluation | R2 | A failed write fails the step (AC37); append-only table |
| The cascade changes engine behavior on replay | R2 | Recorded answers are returned on replay without re-querying (AC20, AC29) |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1 to AC3, AC5 to AC15, AC17 to AC19, AC21 to AC39 | Unit (with fake providers and a temporary workspace) | `tests/unit/decisions/` |
| AC4, AC10 (lock), AC12, AC41 | Contract | `tests/contract/` |
| AC16, AC17 (engine), AC30 | Fake-host workflow (real engine, real cascade, fake ports) | `tests/workflow/decisions/` |
| AC20, AC29 | Replay (process/05 §1) | `tests/replay/` |
| AC33 (any text), AC21/AC22 (random provider answers never reach the block unvalidated) | Property (Hypothesis, `derandomize=True`) | `tests/property/` |
| AC6 | Golden (source 12 §3) | `tests/data/golden/` |
| AC40 | Performance | `tests/perf/` |
| AC42 | Unit (source rules) | `tests/rules/` |

Tests use the contract's `FixedClock` and `SeededIdSource` and an injected monotonic clock; no network, no host program.
Coverage floors 85% line and 75% branch (process/05 §2); mutation score at least 80% on the R1 modules `_rules.py`,
`_cascade.py`, `_batch.py`, `_policy.py`, `_redaction.py` (listed in the plan). The workflow tests add the replay test
and fake-host test that process/05 §2 asks of every workflow.

## 10. Version impact

New modules of `eng-harness` 0.1.0 (phase 1). `decisions.lock.json` and `rules.lock.json` are new committed files. A
change of a point's options or state, or of a rule, needs a version bump (AC4, AC10). The `decision_made` payload
gains the `suggestions` shape of §4.9; the engine's journal schema stays at version 1 because the field is already
`suggestions` (engine spec §4.4.2).

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | Amendments to engine spec 0001: (a) §4.1.2 allow-list gains `eng_harness.decisions.types`; (b) the field lists of `DecisionRequest` (block level) and `DecisionCall` (port level), and the name `DecisionCall` for the port argument; (c) input request kind `engine.decision` and `PendingAnswer` handling in `_decide`; (d) the engine supplies `rule_guard` and `sensitive_values`; (e) the `Rule` and `DecisionPolicy` names of the `ctx.decide` signature are these types | Owner | Accept; engine plan T14 follows this spec, and the engine spec is amended in its own pull request |
| Q2 | Phasing conflict in older text: the Decision bullet "Phasing" of ADR-0012 and the Phase 1 tag in 12's header still describe a decision model for DXF layer classification in phase 1; ADR-0025 decision 5 (accepted) moves tier 2 and 3 to phase 2 and drops layer classification from phase 1. This spec follows ADR-0025 | Owner | Update ADR-0012's phasing sentence when it is accepted; 12 §6 keeps the layer-classification example as a later use |
| Q3 | Where labeled sets live: 12 §6 says in the workspace, process/05 §7 says in the harness repository's `evals/` | Owner | Both: the runtime store is the workspace (AC35); an opt-in anonymized export (AC39) is what the owner commits to `evals/` |
| Q4 | "Acceptable calibration" (12 §6) has no metric or threshold | Owner | Owner chooses the metric (for example expected calibration error with fixed bins) and threshold before phase 2; until then no `ShadowRelease` with basis `evaluation` is created. Gap D-G1 (evaluation); nothing in this spec depends on it |
| Q5 | `min_confidence` bounded below by 0.85 is a reading of 12 §6 ("thresholds can only be raised per point") | Owner | Accept |
| Q6 | The deny-list tokens and value patterns of §4.10 are a privacy control, not engineering content, but they are a security surface | Owner | Review with the security lens; extend from experience, never shrink |
| Q7 | Rule approval: process/10 §4 says rules are "reviewed by the owner" and puts calcs, not rules, in `approvals.yaml`. Should production runs refuse unapproved rules? | Owner | Yes: same file, kind `rule`, bound to `code_sha256`; a run with draft rules is labeled draft in the run report (spec 0006) and refused outside bootstrap mode. Enforcement point: run start (engine) with the registry's `review_table()` |
| Q8 | Engineer latency is the time between the pending record and the answer | Owner | Accept |
| Q9 | A failed label write fails the decision step (AC37) instead of continuing | Owner | Accept: the labels are the point of phase 1 shadow data, and the failure is rare |
| Q10 | A matching rule does not trigger shadow runs of tiers 2 and 3, so rule-decided cases give no evaluation data | Owner | Accept for v1; revisit after the first evaluation shows the volume of engineer-decided cases |
| Q11 | Floor of `max_options` 32 and `max_state_bytes` 4096 are software limits chosen here | Owner | Accept as settings; raise on need |
