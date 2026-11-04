---
id: plan-b060-engine
issue: "B-060"
spec: packages/eng-harness/docs/specs/0001-engine.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2, r3]       # binding for every pull request of this plan; r3 because T1 and later tasks touch pyproject.toml
tasks:
  - id: T1
    title: Package skeleton, gate configuration and workspace member
    files:
      - "pyproject.toml"
      - "uv.lock"
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/README.md"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/AGENTS.md"
      - "packages/eng-harness/CLAUDE.md"
      - "packages/eng-harness/.gate/agents.yml"
      - "packages/eng-harness/.gate/risk-map.yml"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/src/eng_harness/__init__.py"
      - "packages/eng-harness/src/eng_harness/py.typed"
      - "packages/eng-harness/tests/unit/test_package.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_package.py::test_version_matches_project"
      - "packages/eng-harness/tests/unit/test_package.py::test_public_modules_import"
      - "packages/eng-harness/tests/unit/test_package.py::test_private_modules_are_underscored"
    covers: [AC1]
    depends_on: []
  - id: T2
    title: Harness codes, EngineStop and StepError families
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/errors.py"
      - "packages/eng-harness/tests/unit/test_errors.py"
    max_changed_lines: 150
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/test_errors.py::test_engine_stop_is_not_exception"
      - "packages/eng-harness/tests/unit/test_errors.py::test_codes_per_exception"
    covers: [AC10]
    depends_on: [T1]
  - id: T3
    title: Journal schema, append-only writer, hash chain, durability, payloads by reference
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/journal/__init__.py"
      - "packages/eng-harness/src/eng_harness/journal/_schema.py"
      - "packages/eng-harness/src/eng_harness/journal/_events.py"
      - "packages/eng-harness/src/eng_harness/journal/_writer.py"
      - "packages/eng-harness/src/eng_harness/_kinds.py"
      - "packages/eng-harness/tests/unit/test_journal.py"
      - "packages/eng-harness/tests/conftest.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/test_journal.py::test_append_only"
      - "packages/eng-harness/tests/unit/test_journal.py::test_hash_chain_detects_tampering"
      - "packages/eng-harness/tests/unit/test_journal.py::test_durability_policy"
      - "packages/eng-harness/tests/unit/test_journal.py::test_large_payloads_by_reference"
      - "packages/eng-harness/tests/unit/test_journal.py::test_payload_models"
    covers: [AC20, AC21, AC22, AC24, AC26]
    depends_on: [T2]
  - id: T4
    title: Journal reader API and views
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/journal/__init__.py"
      - "packages/eng-harness/src/eng_harness/journal/_reader.py"
      - "packages/eng-harness/src/eng_harness/_runlock.py"
      - "packages/eng-harness/tests/unit/test_journal_reader.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_journal_reader.py::test_views_and_follow"
      - "packages/eng-harness/tests/unit/test_journal_reader.py::test_run_class_and_unreleased_tools"
    covers: [AC25, AC68]
    depends_on: [T3]
  - id: T5
    title: Blocks, workflows, registry, code hash and the block lock file
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/block.py"
      - "packages/eng-harness/src/eng_harness/blocks.lock.json"
      - "packages/eng-harness/tests/unit/test_block.py"
      - "packages/eng-harness/tests/contract/test_block_lock.py"
      - "packages/eng-harness/tests/data/blocks/**"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_block.py::test_registration_rules"
      - "packages/eng-harness/tests/unit/test_block.py::test_code_hash_is_stable"
      - "packages/eng-harness/tests/unit/test_block.py::test_check_lock"
      - "packages/eng-harness/tests/contract/test_block_lock.py::test_lock_matches_registry"
    covers: [AC2, AC3, AC4]
    depends_on: [T2]
  - id: T6
    title: Ports, port data types and in-memory fakes
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/ports.py"
      - "packages/eng-harness/tests/fakes/**"
      - "packages/eng-harness/tests/contract/test_ports_conformance.py"
    max_changed_lines: 380
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/contract/test_ports_conformance.py::test_fakes_conform"
    covers: [AC57]
    depends_on: [T3]
  - id: T7
    title: ctx types, basis view and the result codec
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/ctx.py"
      - "packages/eng-harness/src/eng_harness/engine/_codec.py"
      - "packages/eng-harness/tests/unit/test_codec.py"
      - "packages/eng-harness/tests/unit/test_ctx_basis.py"
    max_changed_lines: 350
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_codec.py::test_live_equals_replayed"
      - "packages/eng-harness/tests/unit/test_ctx_basis.py::test_basis_view"
    covers: [AC11, AC17]
    depends_on: [T6]
  - id: T8
    title: Step paths, scopes, op_id, overlap detection, parallel and attempts scopes
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/_steps.py"
      - "packages/eng-harness/tests/unit/test_steps.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_steps.py::test_paths_independent_of_completion_order"
      - "packages/eng-harness/tests/unit/test_steps.py::test_op_id"
      - "packages/eng-harness/tests/unit/test_steps.py::test_overlap_outside_parallel"
      - "packages/eng-harness/tests/unit/test_steps.py::test_parallel_error_choice"
    covers: [AC5, AC6, AC7, AC8]
    depends_on: [T7]
  - id: T9
    title: Engine start and resume, run lock, run header, replay index and divergence
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/__init__.py"
      - "packages/eng-harness/src/eng_harness/engine/_runner.py"
      - "packages/eng-harness/src/eng_harness/engine/_replay.py"
      - "packages/eng-harness/tests/unit/test_runner.py"
      - "packages/eng-harness/tests/unit/test_run_lock.py"
      - "packages/eng-harness/tests/windows/test_run_lock_windows.py"
      - "packages/eng-harness/tests/replay/test_resume.py"
      - "packages/eng-harness/tests/replay/test_divergence.py"
      - "packages/eng-harness/tests/workflows/**"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/test_runner.py::test_input_and_output_validation"
      - "packages/eng-harness/tests/unit/test_run_lock.py::test_one_engine_per_run"
      - "packages/eng-harness/tests/replay/test_resume.py::test_completed_run"
      - "packages/eng-harness/tests/replay/test_divergence.py::test_divergence_variants"
      - "packages/eng-harness/tests/replay/test_divergence.py::test_hash_change_warns"
      - "packages/eng-harness/tests/unit/test_runner.py::test_run_class_recorded_and_checked"
      - "packages/eng-harness/tests/unit/test_runner.py::test_unreleased_tools_recorded"
    covers: [AC16, AC23, AC28, AC29, AC35, AC65, AC68]
    depends_on: [T4, T5, T8]
  - id: T10
    title: ctx implementation of tool, read, calc, block, parallel, attempts, escalate
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"
      - "packages/eng-harness/src/eng_harness/engine/_runner.py"
      - "packages/eng-harness/tests/unit/test_ctx_tool.py"
      - "packages/eng-harness/tests/unit/test_ctx_read.py"
      - "packages/eng-harness/tests/unit/test_ctx_calc.py"
      - "packages/eng-harness/tests/unit/test_ctx_block.py"
      - "packages/eng-harness/tests/unit/test_ctx_attempts.py"
      - "packages/eng-harness/tests/unit/test_ctx_escalate.py"
      - "packages/eng-harness/tests/replay/test_resume.py"
      - "packages/eng-harness/tests/workflows/**"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/test_ctx_tool.py::test_tool_result_and_failure"
      - "packages/eng-harness/tests/unit/test_ctx_read.py::test_read"
      - "packages/eng-harness/tests/unit/test_ctx_calc.py::test_calc_step"
      - "packages/eng-harness/tests/unit/test_ctx_block.py::test_child_block"
      - "packages/eng-harness/tests/unit/test_ctx_attempts.py::test_attempts_rules"
      - "packages/eng-harness/tests/unit/test_ctx_escalate.py::test_escalate"
      - "packages/eng-harness/tests/replay/test_resume.py::test_pause_and_resume"
    covers: [AC9, AC11, AC12, AC13, AC14, AC15, AC27]
    depends_on: [T9]
  - id: T11
    title: Input requests (the x-eng-input marker, choice schemas, answer checks) and the escalation request
    # Amendment (B-342, documents only): the original T11 (440 lines) exceeded limits.max_task_lines (400, gate GC005);
    # lead decision D-12: split. T11 keeps the input-request builders of B-068 (`_inputs.py`, AC67); T11b keeps the
    # in-flight reconciliation and the host-state check, which present their requests through T11.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/_inputs.py"
      - "packages/eng-harness/src/eng_harness/engine/_runner.py"
      - "packages/eng-harness/tests/unit/test_inputs.py"
    max_changed_lines: 140
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/test_inputs.py::test_input_request_markers"
    covers: [AC67]
    depends_on: [T10]
  - id: T11b
    title: In-flight reconciliation and the host-state check before live execution
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/_inflight.py"
      - "packages/eng-harness/src/eng_harness/engine/_hoststate.py"
      - "packages/eng-harness/src/eng_harness/engine/_runner.py"
      - "packages/eng-harness/tests/replay/test_in_flight.py"
      - "packages/eng-harness/tests/replay/test_host_state.py"
      - "packages/eng-harness/tests/workflows/**"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/replay/test_in_flight.py::test_write_in_flight"
      - "packages/eng-harness/tests/replay/test_in_flight.py::test_read_in_flight"
      - "packages/eng-harness/tests/replay/test_host_state.py::test_three_choices"
      - "packages/eng-harness/tests/replay/test_host_state.py::test_host_crash_with_write_in_flight"
      - "packages/eng-harness/tests/replay/test_host_state.py::test_reopened_in_new_instance"
    covers: [AC31, AC32, AC34, AC63, AC64]
    depends_on: [T11]
  - id: T12
    title: Invariants 1, 2, 3 and 7 (check after write, references, staleness, save before analysis)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/_invariants.py"
      - "packages/eng-harness/src/eng_harness/engine/_steps.py"
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"
      - "packages/eng-harness/tests/unit/test_steps.py"
      - "packages/eng-harness/tests/workflow/test_invariants.py"
      - "packages/eng-harness/tests/property/test_check_after_write.py"
      - "packages/eng-harness/tests/replay/test_divergence.py"
      - "packages/eng-harness/tests/workflows/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/test_steps.py::test_sibling_model_conflict"
      - "packages/eng-harness/tests/workflow/test_invariants.py::test_check_after_write"
      - "packages/eng-harness/tests/property/test_check_after_write.py::test_no_unchecked_use_after_write"
      - "packages/eng-harness/tests/workflow/test_invariants.py::test_engineering_literal_rejected"
      - "packages/eng-harness/tests/workflow/test_invariants.py::test_stale_ref"
      - "packages/eng-harness/tests/workflow/test_invariants.py::test_save_before_analysis"
      - "packages/eng-harness/tests/replay/test_divergence.py::test_inserted_steps_are_replayed"
    covers: [AC5, AC37, AC38, AC39, AC43, AC47]
    depends_on: [T10, T11b]
  - id: T13
    title: Invariants 5, 6, 8, 9 and 10 (basis, honest outcomes, server checks, units, host leases)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/_hostsafety.py"
      - "packages/eng-harness/src/eng_harness/engine/_runner.py"
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"
      - "packages/eng-harness/tests/workflow/test_invariants.py"
      - "packages/eng-harness/tests/workflow/test_honest_outcomes.py"
      - "packages/eng-harness/tests/replay/test_in_flight.py"
      - "packages/eng-harness/tests/replay/test_resume.py"
      - "packages/eng-harness/tests/workflows/**"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/test_invariants.py::test_basis_incomplete_refused"
      - "packages/eng-harness/tests/workflow/test_honest_outcomes.py::test_unknown_outcome_reconciled_first"
      - "packages/eng-harness/tests/workflow/test_honest_outcomes.py::test_reconcile_before_next_step_on_host"
      - "packages/eng-harness/tests/workflow/test_invariants.py::test_server_check"
      - "packages/eng-harness/tests/workflow/test_invariants.py::test_units_after_reconnect"
      - "packages/eng-harness/tests/workflow/test_invariants.py::test_host_lease_and_close"
      - "packages/eng-harness/tests/replay/test_resume.py::test_close_started_after_resume"
      - "packages/eng-harness/tests/replay/test_in_flight.py::test_resume_order_guards_reconciliation"
    covers: [AC33, AC41, AC42, AC44, AC45, AC46, AC62]
    depends_on: [T11b, T12]
  - id: T14
    title: ctx.decide and ctx.decide_many over the DecisionPort, with engineer-tier requests (invariant 4)
    # Amendment (B-342, documents only): the original T14 (450 lines) exceeded limits.max_task_lines (400, gate GC005);
    # lead decision D-12: split. T14 keeps the DecisionPort, `decide`, `decide_many` and the engineer-tier request
    # (B-068); T14b keeps `ctx.ask` and the decision runtime record of amendment B-098.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/ports.py"
      - "packages/eng-harness/src/eng_harness/engine/_decide.py"
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"
      - "packages/eng-harness/src/eng_harness/engine/_runner.py"
      - "packages/eng-harness/tests/fakes/**"
      - "packages/eng-harness/tests/contract/test_ports_conformance.py"
      - "packages/eng-harness/tests/unit/test_ctx_decide.py"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_ctx_decide.py::test_decisions_cannot_produce_numbers"
      - "packages/eng-harness/tests/unit/test_ctx_decide.py::test_engineer_tier_through_input_port"
    covers: [AC40, AC66, AC67]
    depends_on: [T13]
  - id: T14b
    title: ctx.ask and the decision runtime record (run header and reader view)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/ports.py"
      - "packages/eng-harness/src/eng_harness/engine/_decide.py"
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"
      - "packages/eng-harness/src/eng_harness/engine/_runner.py"
      - "packages/eng-harness/src/eng_harness/journal/_events.py"
      - "packages/eng-harness/src/eng_harness/journal/_reader.py"
      - "packages/eng-harness/tests/fakes/**"
      - "packages/eng-harness/tests/contract/test_ports_conformance.py"
      - "packages/eng-harness/tests/unit/test_ctx_ask.py"
      - "packages/eng-harness/tests/unit/test_runner.py"
      - "packages/eng-harness/tests/unit/test_journal_reader.py"
    max_changed_lines: 120
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/test_ctx_ask.py::test_ask_stores_engineer_input"
      - "packages/eng-harness/tests/unit/test_ctx_ask.py::test_input_request_markers"
      - "packages/eng-harness/tests/unit/test_runner.py::test_decision_runtime_recorded"
      - "packages/eng-harness/tests/unit/test_journal_reader.py::test_decision_runtime_view"
    covers: [AC61, AC67, AC69]
    depends_on: [T14]
  - id: T15
    title: Approvals (binding, single use, re-check before the write, items, pause and re-presentation)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/_approvals.py"
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"
      - "packages/eng-harness/tests/unit/test_approvals.py"
      - "packages/eng-harness/tests/replay/test_resume.py"
      - "packages/eng-harness/tests/workflow/test_pause.py"
      - "packages/eng-harness/tests/workflows/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/test_approvals.py::test_binding_and_single_use"
      - "packages/eng-harness/tests/unit/test_approvals.py::test_recheck_before_write"
      - "packages/eng-harness/tests/unit/test_approvals.py::test_per_item_rejection_and_expiry"
      - "packages/eng-harness/tests/replay/test_resume.py::test_pending_requests_represented"
      - "packages/eng-harness/tests/workflow/test_pause.py::test_except_exception_cannot_swallow_pause"
    covers: [AC10, AC36, AC54, AC55, AC56]
    depends_on: [T12, T14b]
  - id: T16
    title: Permission modes, always-ask list, working copies and file-copy promotion
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/_modes.py"
      - "packages/eng-harness/src/eng_harness/engine/_promote.py"
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"
      - "packages/eng-harness/tests/workflow/test_modes.py"
      - "packages/eng-harness/tests/unit/test_promote.py"
      - "packages/eng-harness/tests/workflows/**"
      - "packages/eng-harness/docs/local-testing.md"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/test_modes.py::test_work_on_copy"
      - "packages/eng-harness/tests/workflow/test_modes.py::test_approve_each_write"
      - "packages/eng-harness/tests/workflow/test_modes.py::test_autonomous_logged"
      - "packages/eng-harness/tests/workflow/test_modes.py::test_always_ask_in_every_mode"
      - "packages/eng-harness/tests/unit/test_promote.py::test_file_copy_promotion"
      - "packages/eng-harness/tests/unit/test_promote.py::test_replay_promotion_is_a_gap"
      - "packages/eng-harness/tests/unit/test_promote.py::test_promotion_rechecks_approval"
    covers: [AC48, AC49, AC50, AC51, AC52, AC53]
    depends_on: [T15]
  - id: T17
    title: Runtime guard for block and rule code, and the block-module rules test
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/__init__.py"
      - "packages/eng-harness/src/eng_harness/engine/_guard.py"
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"
      - "packages/eng-harness/tests/unit/test_guard.py"
      - "packages/eng-harness/tests/rules/**"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_guard.py::test_guard_blocks_io_in_block_code"
      - "packages/eng-harness/tests/unit/test_guard.py::test_guard_covers_parallel_children_and_child_blocks"
      - "packages/eng-harness/tests/unit/test_guard.py::test_rule_guard_factory"
      - "packages/eng-harness/tests/rules/test_block_modules.py::test_rules_detect_violations"
      - "packages/eng-harness/tests/rules/test_block_modules.py::test_package_block_modules_pass"
    covers: [AC18, AC19]
    depends_on: [T16]
  - id: T18
    title: Resource limits, progress sink and the overhead benchmark
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/engine/_resources.py"
      - "packages/eng-harness/src/eng_harness/engine/_runner.py"
      - "packages/eng-harness/src/eng_harness/engine/_ctx_impl.py"
      - "packages/eng-harness/tests/unit/test_resources.py"
      - "packages/eng-harness/tests/unit/test_progress.py"
      - "packages/eng-harness/tests/perf/test_overhead.py"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_resources.py::test_limits"
      - "packages/eng-harness/tests/unit/test_progress.py::test_sink_order_and_failure"
      - "packages/eng-harness/tests/perf/test_overhead.py::test_engine_overhead_p95"
    covers: [AC58, AC59, AC60]
    depends_on: [T14b, T17]
  - id: T19
    title: Crash-matrix replay suite with a worker process
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/tests/replay/test_crash_matrix.py"
      - "packages/eng-harness/tests/replay/_worker.py"
      - "packages/eng-harness/tests/workflows/**"
      - "packages/eng-harness/docs/local-testing.md"
    max_changed_lines: 60
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/replay/test_crash_matrix.py::test_crash_matrix"
    covers: [AC30]
    depends_on: [T13, T15, T16]
---

# Implementation plan: eng-harness engine

## 1. Approach

The engine is built bottom-up in the order its own imports require: errors, the journal (the most safety-relevant
storage, built and tested before anything writes to it), the reader, blocks and the registry, ports with their fakes,
the ctx types and codec, step paths, then the run loop with replay and divergence, the ctx calls, the input-request
builders, in-flight reconciliation and the host-state check, the invariants, decisions and inputs, approvals, permission modes and
promotion, the runtime guard, resources and the benchmark, and last the crash matrix that exercises everything
together. Risky parts come early: the journal (T3), path identity (T8) and replay (T9) are the core S-10 proved, so a
defect there shows before the invariants are built on them. The tasks that edit `engine/_ctx_impl.py` are serialized
by `depends_on` (T10, T12, T13, T14, T14b, T15, T16, T17, T18 in that order), so no two of them run in parallel. T11b
shares `CHANGELOG.md` and `tests/workflows/**` with T12 and `_runner.py` with T13, so T12 depends on T11b and T13 on
both; T11b follows T11 (the input requests it presents), and T14b follows T14: the tasks from T10 to T18 run one after
another. Every task adds a `CHANGELOG.md` line, and some add `public_modules` entries
to `pyproject.toml`, so tasks that may run in parallel (T5 beside T3, T6 and T7; T19 beside T17 and T18) share those two
files only: their lines are merged in pull-request order, and they share no other file.

Every task is test-first: its first commit is `test:` with the tests in `tests_first`, failing on `build/v1`
([process/05](../../../../design/process/05-testing-and-verification.md) §9). Each task adds the public modules it
creates to `[tool.eng-gate] public_modules` (the gate checks that each listed module exists) and a `CHANGELOG.md`
line. Tests use the fakes of T6, the contract's `FixedClock` and `SeededIdSource`, and a real SQLite journal in a
temporary workspace.

Reuse (spec §2): the S-10 design (not its code), the standard library (`sqlite3`, `asyncio`, `fcntl`, `msvcrt`,
`sys.addaudithook`), and `eng-contract` 0.1 for canonical JSON, ids, envelopes, the store, references, `Quantity` and
kinds. Test workflows used by the workflow and replay tests live in `tests/workflows/` (test doubles, never shipped).

## 2. Tasks

**T1 Skeleton.** `packages/eng-harness/pyproject.toml` with `name = "eng-harness"`, `version = "0.1.0.dev0"`,
`requires-python = ">=3.14,<3.15"` ([ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §5),
`dependencies = ["eng-contract", "pydantic>=2.14,<3"]` with `[tool.uv.sources] eng-contract = { workspace = true }`,
the uv build backend, the tool configuration of [process/11](../../../../design/process/11-repository-standard.md) §3,
and the gate table in the format of the
[eng-dev-gate spec](../../../../tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md) §5 (profile `harness`,
layer 4):

```toml
[tool.eng-gate]
profile = "harness"
layer = 4
import_names = ["eng_harness"]
public_modules = ["eng_harness"]          # each later task adds the public modules it creates
coverage_line = 85                        # process/05 section 2
coverage_branch = 75
r1_modules = [
  "src/eng_harness/engine/_inflight.py", "src/eng_harness/engine/_hoststate.py",
  "src/eng_harness/engine/_invariants.py", "src/eng_harness/engine/_hostsafety.py",
  "src/eng_harness/engine/_approvals.py", "src/eng_harness/engine/_modes.py",
  "src/eng_harness/engine/_promote.py", "src/eng_harness/engine/_replay.py",
]
r2_modules = ["src/eng_harness/journal/**", "src/eng_harness/ctx.py", "src/eng_harness/block.py",
              "src/eng_harness/ports.py", "src/eng_harness/errors.py"]
mutation_min = 80                         # required when R1 or R2 globs exist (gate spec section 5)
block_modules = ["src/eng_harness/workflows/**", "src/eng_harness/blocks/**"]
rule_modules = ["src/eng_harness/rules/**"]
calc_modules = ["src/eng_harness/calcs/**"]
windows_tests = ["tests/windows", "tests/perf"]
```

The [eng-contract plan](../../../eng-contract/docs/plans/0001-eng-contract-0.1.md) T1 uses other key names
(`layer_name`, `risk_floor`, `may_import`, a `coverage` subtable); this plan follows the gate spec, which defines the
table, and T1's pull request notes any rename the merged gate requires. T1 also adds `"packages/eng-harness"` to
`[tool.uv.workspace] members` in the root `pyproject.toml` (lead decision D-10) and updates `uv.lock`; `README.md`
(purpose, `uv sync`, limits: no host program in CI); `CHANGELOG.md` (Unreleased); `.gate/agents.yml` and `AGENTS.md`
rendered from [AGENTS.template.md](../../../../design/process/templates/AGENTS.template.md) by `eng-gate agents render`
(filled by hand only if the renderer is not merged yet, then re-rendered by the first `agents-drift` run); `CLAUDE.md`
containing `@AGENTS.md`; `.gate/risk-map.yml` mapping the `r1_modules` globs to `r1` and the `r2_modules` globs to
`r2`; `docs/local-testing.md` with the items of §4; `src/eng_harness/py.typed`; and `__init__.py` with `__version__`.

**T2 Errors** (spec §6). `HarnessCode`, `EngineStop` (a `BaseException`) and its subclasses, `StepError` and its
subclasses, `RunRefused`, `RunLocked`, `JournalIntegrityError`. Imports `eng_contract.errors` only.

**T3 Journal writer** (spec §4.4.1 to §4.4.3). Schema and triggers (including the `BEFORE INSERT` triggers that close
the `REPLACE` path and enforce gap-free `seq`), the 20 event payload models (with the B-068 fields `run_class`,
`unreleased_tools`, `item_reasons`, `acknowledged_unreleased`, `decision_made.request_id`, `model_bound.file_names`,
`model_saved.origin_file_names` and the kind `engine.decision`), the writer with the
hash chain, per-event durability, the inline limit and `harness.journal_blob/1`, and the harness kinds module
(`_kinds.py`: `harness.run_input/1`, `harness.run_output/1`, `harness.approval_preview/1`,
`harness.journal_blob/1`, registered with `KindRegistry.extend`). AC22 is tested by wrapping the connection and
recording the `synchronous` value of each commit.

**T4 Journal reader** (spec §4.4.5). Read-only connection, chain verification, the views and `follow`, and
`is_locked` over the run-lock helper `_runlock.py` (`fcntl` and `msvcrt`), which T9's engine uses to hold the lock.
`RunView.run_class` (from `run_started`) and `RunView.unreleased_tools` (the union over `run_started` and every
`run_resumed`, AC68), and `RequestView` resolution per kind, an `engine.decision` request by the first `decision_made`
that names its `request_id` (AC25). The tests write the events through T3's writer, so no engine is needed.

**T5 Registry** (spec §4.2). Decorators, `BlockDef`, `WorkflowDef`, `Registry`, the code hash, `check_lock`, the
`--write-lock` entry point and an empty `blocks.lock.json` (no blocks exist yet). AC4's contract test runs on fixture
blocks in `tests/data/blocks/` and on the real (empty) registry.

**T6 Ports** (spec §4.8). Eight of the nine protocols and their data types (including `RunClass`,
`CalcPort.run_class`, `CalcInfo.basis_fields` and `ref_rules`, `ToolPort.unreleased_tools`, and the approval and input
request and answer models of spec §4.9, §4.9.1, with `ApprovalAnswer.acknowledged_unreleased`). `DecisionPort` is not
built here: its data types are owned by `eng_harness.decisions.interfaces` (spec §4.8 "Decision port types"), which
needs this task and T7 first, so T14 adds the protocol, its fake and its conformance case. Fakes in `tests/fakes/`: a
fake host with a ledger
of every call and `op_id` (S-10's reconciler stand-in), scripted outcomes per call (success, failure envelope,
`TIMEOUT_UNKNOWN_OUTCOME`, `HOST_WEDGED`, raise), model state with revision and fingerprint, units, a host crash (models reported not loaded), session epochs,
leases; fake CalcPort, BasisPort, ApprovalPort and InputPort with scripted answers; a recording
ProgressSink; a RunControlPort. The fakes count as tests for the budget.

**T7 ctx types and codec** (spec §4.3.2, §4.5.2 "Codec"). The result models, `Preview`, `Approval`, `ModelHandle`,
`BasisView` with `ref`, `quantity`, `count` and `choice`, `BasisCount`, and the codec that rebuilds `Quantity`
objects after the canonical round trip.

**T8 Steps** (spec §4.3.1). Scopes as context variables, the path grammar, inserted and housekeeping paths,
`op_id`, overlap detection, the parallel driver (all children finish; error choice by rank and index) and the attempts
iterator. Tested with a stub step executor, before the runner exists.

**T9 Runner and replay** (spec §4.5.1, §4.5.2, §4.4.4). `Engine.start` and `Engine.resume`, input and output
validation, holding the run lock of `_runlock.py` (with the Windows test under the `windows` marker), the run header and
the version rule, the run-class check at start and resume and the `unreleased_tools` record (AC65, AC68), the replay index, divergence (all S-10 variants) and the completed-run return. A minimal `ctx.tool`
is wired here so the divergence tests can run; T10 completes it.

**T10 ctx calls** (spec §4.3.2, §4.3.3). `tool` (with retries), `read`, `calc`, `block`, `parallel`, `attempts`,
`escalate`, and pause and resume through a test approval stub (the full approval rules come in T15); `CalcRefused`
from the CalcPort becomes a failed step (AC13).

**T11 Input requests** (spec §4.9.1, AC67; B-068). The first input requests the engine presents are built in
`engine/_inputs.py`: the `x-eng-input` marker, the choice-schema builder of spec §4.9.1, the refusal of a schema without
`data` or `choice` before `present`, and the answer-shape check (`values` against `choices`). The `engine.escalation`
request (from `_runner.py`) is built with it, and `tests/unit/test_inputs.py` covers the marker, the refusals, the
answer-shape check and that request. Budget 140 lines (the original T11 measured 440 and was split by B-342, D-12).

**T11b In-flight and host state** (spec §4.5.3, §4.5.4). Reconciliation at resume before the block runs, the engineer
request `engine.in_flight`, `step_rerun`, the host-state check with its three choices and the replay cut for
`restore`, the instance binding (`model_bound` at first use, after a restore and for a reopened model), and lost or
reopened models (no reconciliation, `model_not_loaded`, `model_reopened`, units read against the new binding, AC63,
AC64), with `model_bound.file_names` from `HostPort.model_files`. The `engine.in_flight` and `engine.host_state`
requests are built with T11's `_inputs.py`, and their tests assert the `choice` marker of AC67. Budget 300 lines (the
original 440 less T11's 140).

**T12 Invariants 1, 2, 3, 7** (spec §4.6, §4.3.1 "Models in parallel children"). The model tracker with per-child
dirty flags and the sibling model-conflict check, inserted `check_model` and `save` steps, the
engineering-parameter check, the staleness check with `resolve_ref` and each calc argument's `RefRule` from
`CalcInfo.ref_rules` (default `stale_ok` false), the property test over generated step programs,
and the test that inserted steps are replayed.

**T13 Invariants 5, 6, 8, 9, 10** (spec §4.6). Basis completeness before the run folder exists, per-host
reconciliation pending, server checks at start and resume, unit reads (first contact, every resume, after epoch
changes and observed timeouts), host leases, `host_started` journaling and `close_started` from the journal at run
end, and the resume order of spec §4.5.1 (preflight, leases and units before T11b's reconciliation, AC62).

**T14 Decisions** (spec §4.3.2, §4.6 item 4). `decide` and `decide_many` over the ports; option and answer validation;
`decision_made`; engineer-tier pauses; the `DecisionPort` protocol in `ports.py` over the types of
`eng_harness.decisions.interfaces`, its fake in `tests/fakes/` and its case in the conformance test (AC57); the
`DecisionCall` with `sensitive_values` (from the journal's `model_bound.file_names`, `model_saved.origin_file_names`
and `file_name`), the `engine.decision` request through T11's `_inputs.py` and `InputPort`, `decision_made.request_id`,
the `EngineerChoice` round trip (AC66), and the `choice` marker of `engine.decision` (AC67). `DecisionRequest` is the
frozen dataclass of spec §4.3.2. Budget 330 lines. Build order: T14 starts only
after decision plan T1, T4 and T5 are merged (they need this plan's T6 and T7), because `DecisionCall` and the other
port types live in `decisions.interfaces` (spec §4.8); it is the only task of this plan that waits for the decision
plan.

**T14b Ask and the decision runtime record** (spec §4.3.2, §4.6 item 4, AC61, AC67, AC69). `ask`: the `data` marker
(AC67), validation of the answer against `fields`, `input_requested` and the pause, and the answer stored as
`basis.engineer_input/1` (AC61). Amendment B-098: `DecisionPort.runtime_summary()` (protocol and fake), recorded as
`decision_runtime` in `run_started` and, when changed, in `run_resumed`, and shown as `RunView.decision_runtime`
(AC69); the field and the reader view follow the `unreleased_tools` pattern of T3, T4 and T9 (about 30 lines). Budget
120 lines. The original T14 (decisions and inputs: 280 lines at first, 420 with B-068, 450 with B-098) was split by
B-342 (D-12) so that neither part exceeds the 400-line cap.

**T15 Approvals** (spec §4.9). Request ids, previews as results, binding, single use, refusal and re-presentation,
re-check before the first write under an approval, revision continuity, expiry, items and `item_reasons`,
`acknowledged_unreleased` (journaled as given; the page decides when it is required, spec §4.9), `signed_off`, pause
and the
`except Exception` test.

**T16 Modes and promotion** (spec §4.7). Working copies (with `origin_sha256` and `origin_file_names`), approval
per write, mode-resolved approvals, the always-ask list, file-copy promotion over the internal `FileOps` port with its
fake (including the re-check of the `PROMOTION` approval's binding before copying), and the `REPLAY_WRITES` gap.

**T17 Guard and block rules** (spec §4.3.4, §4.1.2). The audit hook with its context variable, wired into every ctx
call so that it is off only during the engine's own step work and back on in parallel children, child blocks and
attempts bodies, the public `rule_guard()` factory for the decision layer (exported from `engine/__init__.py`;
budget 250 lines with it, B-068), and the AST rules test over fixture modules and over the package's block and rule globs (empty until later
specs add blocks).

**T18 Resources, progress, benchmark** (spec §4.10). Semaphores and host locks, sink delivery and detachment, and the
overhead benchmark (also listed in `windows_tests`).

**T19 Crash matrix** (spec AC30). A worker process (`tests/replay/_worker.py`) runs a mixed test workflow and calls
`os._exit` at each of S-10's four crash points for every step; the test resumes each and compares the fake host's
ledger and the outputs with an uninterrupted run. Almost all of it is test code.

## 3. Dependencies

- Runtime: `eng-contract` (workspace member) and `pydantic` (named by
  [ADR-0011](../../../../design/docs/adr/0011-harness-owns-workflow-engine.md); also required by `eng-contract`). No
  other runtime dependency; no package-local ADR is needed.
- Development: the root workspace's shared group (`pytest`, `pytest-cov`, `hypothesis`, `mypy`, `ruff`) and the
  gate's mutation tool; no new development dependency.
- Work items: `eng-contract` 0.1.0 merged (B-010 to B-025) before T1, because T2 onward import it; `eng-dev-gate`
  `agents render` (B-030 to B-055) if available at T1, otherwise as described there. Specs 0002 to 0007 implement the
  ports; their plans depend on this plan's T6 (ports) and, for workflows, on T19. T14 waits for decision plan T1, T4
  and T5 (the decision port types, spec §4.8), which wait for this plan's T6 and T7; decision plan T7 and T10 wait for
  T14 (T10 also for T14b, the run header's decision runtime), so the order has no cycle.

## 4. Verification

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` exists; until then, from `packages/eng-harness/`,
  `uv run ruff format --check`, `uv run ruff check`, `uv run mypy --strict src tests` and `uv run pytest` with
  coverage. The pull request links its CI run; local output is not evidence (process/05 §8).
- Windows: `tests/windows/` and `tests/perf/` run in the Windows CI job (run lock on NTFS, overhead on the Windows
  runner's disk).
- Needs local test (listed in `docs/local-testing.md` by T1, completed by T16 and T19; nothing here needs a host
  program, but these need the owner's machine): (1) the overhead benchmark and the fsync cost on the owner's
  workstation disk, with antivirus active, against the 20 ms target; (2) the run lock released after killing the engine
  from Task Manager; (3) a resume after a forced power-off of a virtual machine (power loss is not covered by tests);
  (4) file-copy promotion onto a folder the engineer uses, including a target file open in another program. Every
  step that drives a host program belongs to specs 0002 and 0007 (acceptance A2, A5, A6 of 18 §5).
- Review: each pull request is reviewed by a subagent that did not write it, with the correctness, Python,
  type-design, silent-failure and test lenses; T3, T9, T11b, T12, T13, T15 and T16 additionally against the invariant
  and replay rules of the spec (R1: model writes); T16 and T17 with the security lens (file paths, the audit hook).
  The second-family review and the owner's approvals are `awaiting owner` in bootstrap mode (ADR-0028 §4).

## 5. Rollback

Each task is one squash-merged pull request into `build/v1`, with no consumer outside this package until specs 0002
to 0007 build on it; reverting a task's commit removes it (later tasks depend on earlier ones, so a revert also
reverts its dependants). After a run has been journaled with schema version 1, a defect in the journal is fixed
forward with a reader that still reads version 1; journals are never rewritten.
