---
id: plan-B-004-eng-dev-gate-0-1
issue: "B-004"
spec: tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: r3                 # binding for every pull request of this plan; never below the path risk floor
tasks:
  - id: T1
    title: Package skeleton, dependency ADR, CLI shell
    files:
      - "tools/eng-dev-gate/pyproject.toml"
      - "tools/eng-dev-gate/README.md"
      - "tools/eng-dev-gate/CHANGELOG.md"
      - "tools/eng-dev-gate/AGENTS.md"
      - "tools/eng-dev-gate/CLAUDE.md"
      - "tools/eng-dev-gate/.gate/agents.yml"
      - "tools/eng-dev-gate/docs/local-testing.md"
      - "tools/eng-dev-gate/docs/adr/0001-runtime-dependencies.md"
      - "tools/eng-dev-gate/src/eng_dev_gate/__init__.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/__main__.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/results.py"
      - "tools/eng-dev-gate/tests/**"
      - "uv.lock"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_cli.py::test_exit_codes"
      - "tools/eng-dev-gate/tests/unit/test_cli.py::test_version_option"
    covers: [AC1]
    depends_on: []
  - id: T2a
    title: Foundations A (reporting, globs, event file, repository fixture)
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/report.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/globs.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/event.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 340
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_report.py::test_awaiting_owner_notice_and_summary"
      - "tools/eng-dev-gate/tests/unit/test_report.py::test_json_result_schema"
      - "tools/eng-dev-gate/tests/unit/test_globs.py::test_full_match_semantics"
    covers: [AC1, AC2]
    depends_on: [T1]
  - id: T2b
    title: Foundations B (git port, workspace discovery)
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/gitio.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/workspace.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/integration/test_gitio.py::test_name_status_with_rename"
      - "tools/eng-dev-gate/tests/integration/test_workspace.py::test_discovers_members"
    covers: [AC1, AC2]
    depends_on: [T2a]
  - id: T3
    title: Configuration models, floors and bootstrap mode (root gate.yml)
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/config/__init__.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/config/gate_config.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/config/package_config.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/config/floors.py"
      - ".gate/gate.yml"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 380
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_modes.py::test_mode_only_from_gate_yml"
      - "tools/eng-dev-gate/tests/unit/test_modes.py::test_normal_mode_never_awaits"
      - "tools/eng-dev-gate/tests/unit/test_modes.py::test_bootstrap_off_needs_identities"
      - "tools/eng-dev-gate/tests/unit/test_config.py::test_floors"
    covers: [AC3, AC4, AC5, AC48]
    depends_on: [T2b]
  - id: T4
    title: agents render, keys and drift (and re-render of drifting AGENTS.md files)
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/agents.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/AGENTS.md"
      - "AGENTS.md"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_agents.py::test_render_byte_exact"
      - "tools/eng-dev-gate/tests/unit/test_agents.py::test_placeholder_errors"
      - "tools/eng-dev-gate/tests/unit/test_agents.py::test_template_version"
      - "tools/eng-dev-gate/tests/integration/test_agents_drift.py::test_drift_unmanaged_and_pointer"
      - "tools/eng-dev-gate/tests/unit/test_agents.py::test_keys_skeleton"
    covers: [AC55, AC56, AC57, AC58]
    depends_on: [T2b, T3]
  - id: T5
    title: check orchestrator with the lock, format, lint and types steps
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/toolrun.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/__init__.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/check.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/registry.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/tool_steps.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 360
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_check.py::test_step_order_and_aggregate"
      - "tools/eng-dev-gate/tests/integration/test_tool_steps.py::test_ruff_mypy_on_toy_package"
      - "tools/eng-dev-gate/tests/integration/test_tool_steps.py::test_stale_lock_is_st001"
    covers: [AC47, AC54]
    depends_on: [T2b, T3]
  - id: T6
    title: "CI part 1: setup action and the gate, agents-drift and build jobs"
    files:
      - ".github/workflows/ci.yml"
      - ".gitignore"
      - "tools/eng-dev-gate/actions/setup/action.yml"
      - "tools/eng-dev-gate/actions/gate/action.yml"
      - "tools/eng-dev-gate/actions/agents-drift/action.yml"
      - "tools/eng-dev-gate/actions/build/action.yml"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/docs/local-testing.md"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_ci_files.py::test_jobs_triggers_and_local_actions"
      - "tools/eng-dev-gate/tests/unit/test_ci_files.py::test_security_and_build_commands"
      - "tools/eng-dev-gate/tests/unit/test_workspace.py::test_packages_names"
      - "tools/eng-dev-gate/tests/unit/test_ci_files.py::test_pr_jobs_base_first_steps"
    covers: [AC59, AC62]
    depends_on: [T4, T5, T26]
  - id: T7
    title: tests step with separate line and branch coverage and the pytest plugin
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/tests_step.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/registry.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/pytest_plugin.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_coverage.py::test_line_and_branch_separate"
      - "tools/eng-dev-gate/tests/integration/test_coverage.py::test_deselection_fails"
    covers: [AC50]
    depends_on: [T5]
  - id: T8
    title: config step (weakening rules, override files, rerun plugins, member table)
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/config_step.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/registry.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_config.py::test_weakening_rules"
      - "tools/eng-dev-gate/tests/integration/test_workspace.py::test_member_without_table"
    covers: [AC49, AC54]
    depends_on: [T3, T5]
  - id: T9
    title: ratchet command and step
    # Amendment (B-038, documents only): T9 also writes the initial baseline of the root .gate/ratchet.json. The
    # ratchet must start from the suppressions that already exist in the workspace, and the file's format must be
    # the one this command reads; a protected path, so the change is an awaiting-owner notice in bootstrap mode.
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/ratchet.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/registry.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/tests/**"
      - ".gate/ratchet.json"
    max_changed_lines: 350
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_ratchet.py::test_counts_and_rise"
      - "tools/eng-dev-gate/tests/unit/test_ratchet.py::test_skip_xfail_reasons"
      - "tools/eng-dev-gate/tests/integration/test_ratchet.py::test_json_raise_vs_base"
      - "tools/eng-dev-gate/tests/unit/test_ratchet.py::test_suppression_issue_reference"
    covers: [AC38, AC39, AC40, AC41]
    depends_on: [T3, T5]
  - id: T10
    title: "forbidden part 1: engine, scope, FB001, FB002, FB003, FB007"
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/forbidden/__init__.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/forbidden/engine.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/forbidden/rules_a.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/registry.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - ".gate/forbidden.yml"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 380
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_forbidden_fb001.py::test_flags_name_and_pattern"
      - "tools/eng-dev-gate/tests/unit/test_forbidden_fb002.py::test_flags_dynamic_execution"
      - "tools/eng-dev-gate/tests/unit/test_forbidden_fb003.py::test_flags_host_sdk_outside_host"
      - "tools/eng-dev-gate/tests/unit/test_forbidden_fb007.py::test_flags_print"
      - "tools/eng-dev-gate/tests/unit/test_forbidden_scope.py::test_spikes_tests_and_waivers"
    covers: [AC29, AC30, AC31, AC35, AC37]
    depends_on: [T3, T5]
  - id: T11
    title: "forbidden part 2: FB004, FB005, FB006, FB008"
    # Amendment (B-094, documents only): T11 also edits the package __init__.py, where the step's rule tuple is
    # assembled (T10 put RULES = RULES_A there for a later task to extend); without it the new rules are never run.
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/forbidden/__init__.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/forbidden/rules_b.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/forbidden/engine.py"
      - ".gate/forbidden.yml"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_forbidden_fb004.py::test_flags_io_in_block_and_rule_modules"
      - "tools/eng-dev-gate/tests/unit/test_forbidden_fb005.py::test_numeric_literal_forms"
      - "tools/eng-dev-gate/tests/unit/test_forbidden_fb006.py::test_rationale_digit_probe"
      - "tools/eng-dev-gate/tests/unit/test_forbidden_fb008.py::test_collection_hooks"
    covers: [AC32, AC33, AC34, AC36]
    depends_on: [T10]
  - id: T12
    title: imports command and step
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/imports.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/registry.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 350
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_imports.py::test_layers"
      - "tools/eng-dev-gate/tests/unit/test_imports.py::test_public_modules"
      - "tools/eng-dev-gate/tests/unit/test_imports.py::test_declared_and_sasaah_and_third_party"
      - "tools/eng-dev-gate/tests/unit/test_imports.py::test_cycle"
    covers: [AC42, AC43, AC44, AC45]
    depends_on: [T3, T5]
  - id: T13
    title: "gate-check part 1: front matter, body parsing, plan and task, scope and budget"
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/frontmatter.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/gate_check.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "tools/eng-dev-gate/tests/integration/test_gate_check.py::test_valid_pull_request_passes"
      - "tools/eng-dev-gate/tests/integration/test_gate_check.py::test_plan_task_line_errors"
      - "tools/eng-dev-gate/tests/integration/test_gate_check.py::test_plan_not_on_gate_branch"
      - "tools/eng-dev-gate/tests/integration/test_gate_check.py::test_unknown_task"
      - "tools/eng-dev-gate/tests/integration/test_gate_check.py::test_file_outside_globs_including_rename"
      - "tools/eng-dev-gate/tests/integration/test_gate_check.py::test_changelog_and_local_testing_in_scope"
      - "tools/eng-dev-gate/tests/integration/test_gate_check.py::test_budget_counting"
      - "tools/eng-dev-gate/tests/unit/test_frontmatter.py::test_plan_front_matter_rules"
    covers: [AC6, AC7, AC8, AC9, AC10, AC10a, AC11, AC13]
    depends_on: [T2b, T3]
  - id: T14
    # Amendment (B-089, documents only): AC10b moves to T14b; with it T14 measured 428 lines against 400 (D-12: split).
    title: "gate-check part 2: spec and plan pull requests, lane, reasons, protected paths, and the gate-check job"
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/gate_check.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/gate_check_docs.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/codeowners.py"
      - ".github/workflows/ci.yml"
      - "tools/eng-dev-gate/actions/gate-check/action.yml"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "tools/eng-dev-gate/tests/integration/test_gate_check_docs.py::test_spec_plan_pull_request_only"
      - "tools/eng-dev-gate/tests/integration/test_gate_check_docs.py::test_lane_branch"
      - "tools/eng-dev-gate/tests/integration/test_gate_check_docs.py::test_none_reasons"
      - "tools/eng-dev-gate/tests/integration/test_gate_check_docs.py::test_status_approved"
      - "tools/eng-dev-gate/tests/integration/test_gate_check_docs.py::test_protected_paths_awaiting_owner"
      - "tools/eng-dev-gate/tests/integration/test_gate_check_docs.py::test_gate_branch_merge"
    covers: [AC12, AC14, AC15, AC16, AC17, AC18]
    depends_on: [T6, T13]
  - id: T14b
    title: "gate-check: the ratchet baseline in a task's scope (AC10b)"
    # Amendment (B-089, documents only): split from T14 to keep both tasks within the size cap.
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/gate_check.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 80
    max_sessions: 1
    tests_first:
      - "tools/eng-dev-gate/tests/integration/test_gate_check.py::test_ratchet_baseline_in_scope"
    covers: [AC10b]
    depends_on: [T14]
  - id: T15
    title: risk-floor command and job
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/risk_floor.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - ".github/workflows/ci.yml"
      - "tools/eng-dev-gate/actions/risk-floor/action.yml"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/integration/test_risk_floor.py::test_union_of_maps_and_commits"
      - "tools/eng-dev-gate/tests/integration/test_risk_floor.py::test_risk_sets_and_body_line"
      - "tools/eng-dev-gate/tests/integration/test_risk_floor.py::test_invalid_map"
    covers: [AC19, AC20, AC21]
    depends_on: [T13]
  - id: T16
    title: "test-first part 1: title, exemptions, commit selection, new and changed tests"
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/test_first.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/integration/test_test_first_selection.py::test_exempt_types"
      - "tools/eng-dev-gate/tests/integration/test_test_first_selection.py::test_no_test_commit_and_mixed_commit"
      - "tools/eng-dev-gate/tests/integration/test_test_first_selection.py::test_refactor_and_test_types"
      - "tools/eng-dev-gate/tests/integration/test_test_first_selection.py::test_tests_first_files"
    covers: [AC22, AC25, AC26, AC28]
    depends_on: [T13]
  - id: T17
    title: "test-first part 2: base worktree, runs, classification, isolation, and the test-first job"
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/test_first.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/test_first_run.py"
      - ".github/workflows/ci.yml"
      - "tools/eng-dev-gate/actions/test-first/action.yml"
      - "tools/eng-dev-gate/docs/local-testing.md"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "tools/eng-dev-gate/tests/integration/test_test_first_run.py::test_red_green"
      - "tools/eng-dev-gate/tests/integration/test_test_first_run.py::test_passes_at_base_and_fails_at_head"
      - "tools/eng-dev-gate/tests/integration/test_test_first_run.py::test_base_isolation_and_cleanup"
    covers: [AC23, AC24, AC27]
    depends_on: [T16]
  - id: T18
    title: secrets command and the security job
    # Amendment (B-099, documents only): T18 also edits .gate/gate.yml for the secret-scan allowlist entries its own
    # step needs on the existing tree (a reviewed false positive is allowlisted by rule, path and fingerprint).
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/secrets.py"
      - ".gate/gate.yml"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/registry.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - ".github/workflows/ci.yml"
      - "tools/eng-dev-gate/actions/security/action.yml"
      - "tools/eng-dev-gate/docs/local-testing.md"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_secrets.py::test_range_scan_no_echo"
      - "tools/eng-dev-gate/tests/unit/test_secrets.py::test_allowlist_fingerprint"
    covers: [AC46, AC62]
    depends_on: [T3, T6]
  - id: T19
    title: licenses step and generated-document freshness
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/licenses.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/generated.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/registry.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_licenses.py::test_allowed_unknown_exception"
      - "tools/eng-dev-gate/tests/integration/test_generated.py::test_freshness"
    covers: [AC51, AC52]
    depends_on: [T5]
  - id: T20
    title: mutation step (backend decision, ADR, dependency)
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/mutation.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/registry.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/pyproject.toml"
      - "tools/eng-dev-gate/docs/adr/0002-mutation-backend.md"
      - "tools/eng-dev-gate/docs/local-testing.md"
      - "tools/eng-dev-gate/tests/**"
      - "uv.lock"
    max_changed_lines: 300
    max_sessions: 3
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_mutation.py::test_changed_modules_only"
      - "tools/eng-dev-gate/tests/unit/test_mutation.py::test_score_threshold"
    covers: [AC53]
    depends_on: [T7]
  - id: T21
    title: workflows lint (WF001 to WF005)
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/workflows.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/registry.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 320
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_workflows_lint.py::test_pin_permissions_injection_trigger"
      - "tools/eng-dev-gate/tests/unit/test_workflows_lint.py::test_ci_shape_base_first"
    covers: [AC60, AC68]
    depends_on: [T6]
  - id: T22
    title: reviewer prompts, review command and the ci-review job
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/review.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/prompts/**"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - ".github/workflows/ci.yml"
      - "tools/eng-dev-gate/actions/ci-review/action.yml"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_review.py::test_prompt_hashes_and_modes"
    covers: [AC61]
    depends_on: [T6, T13]
  - id: T23
    title: windows-tests command and the windows job
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/windows_tests.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - ".github/workflows/ci.yml"
      - "tools/eng-dev-gate/actions/windows/action.yml"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_windows_tests.py::test_declared_paths"
      - "tools/eng-dev-gate/tests/unit/test_ci_files.py::test_windows_job_only_on_push"
    covers: [AC59, AC63]
    depends_on: [T6, T7]
  - id: T24
    title: approvals port and verification with bootstrap off
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/approvals.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/gate_check.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/gate_check_docs.py"
      - "tools/eng-dev-gate/docs/local-testing.md"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_approvals.py::test_required_approvers_by_risk_set"
      - "tools/eng-dev-gate/tests/integration/test_gate_check_docs.py::test_normal_mode_verifies_approvals"
      - "tools/eng-dev-gate/tests/unit/test_modes.py::test_normal_mode_never_awaits_in_gate_check"
    covers: [AC3, AC16, AC17]
    depends_on: [T14]
  - id: T25
    title: Documentation, changelog 0.1.0 and the self-gate run
    files:
      - "tools/eng-dev-gate/README.md"
      - "tools/eng-dev-gate/CHANGELOG.md"
      - "tools/eng-dev-gate/docs/local-testing.md"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_docs.py::test_readme_lists_every_command"
    covers: [AC64]
    depends_on: [T7, T8, T9, T11, T12, T14, T14b, T15, T17, T18, T19, T20, T21, T22, T23, T24, T26, T27, T28, T29]
  - id: T26
    title: Base-commit gate (gate root, provenance, head-run rules); built before T6
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/gate_root.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/config/gate_config.py"
      - "tools/eng-dev-gate/src/eng_dev_gate/cli.py"
      - "tools/eng-dev-gate/docs/local-testing.md"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "tools/eng-dev-gate/tests/integration/test_gate_root.py::test_policy_from_gate_root_not_head"
      - "tools/eng-dev-gate/tests/integration/test_gate_root.py::test_provenance_rules"
      - "tools/eng-dev-gate/tests/integration/test_gate_root.py::test_head_run_in_both_modes"
    covers: [AC65, AC66, AC67]
    depends_on: [T3]
  - id: T27
    title: "risk-floor: a none-reason pull request records its risk from the body Risk line"
    # Amendment (B-336, documents only): T27 to T29 turn three lead fixes found by the live gate jobs into plan tasks.
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/risk_floor.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 60
    max_sessions: 1
    tests_first:
      - "tools/eng-dev-gate/tests/integration/test_risk_floor.py::test_none_reason_takes_the_body_risk_line"
    covers: [AC21a]
    depends_on: [T15]
  - id: T28
    title: "gate action: the interim workspace-wide pytest step is removed"
    files:
      - "tools/eng-dev-gate/actions/gate/action.yml"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 20
    max_sessions: 1
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_ci_files.py::test_gate_action_runs_only_check"
    covers: [AC59]
    depends_on: [T6, T7]
  - id: T29
    title: "mutation: a run that produces no mutant passes with MU003"
    files:
      - "tools/eng-dev-gate/src/eng_dev_gate/checks/mutation.py"
      - "tools/eng-dev-gate/tests/**"
    max_changed_lines: 80
    max_sessions: 1
    tests_first:
      - "tools/eng-dev-gate/tests/unit/test_mutation.py::test_zero_mutants_is_nothing_to_mutate"
      - "tools/eng-dev-gate/tests/unit/test_mutation.py::test_uncovered_mutants_count_as_survivors"
    covers: [AC53a]
    depends_on: [T20]
---

# Implementation plan: eng-dev-gate 0.1

Spec: [0001-eng-dev-gate-0.1](../specs/0001-eng-dev-gate-0.1.md). Process:
[process/01](../../../../design/process/01-lifecycle.md) §4,
[process/04](../../../../design/process/04-implementation-rules.md),
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md).

## 1. Approach

**Research.** Nothing in the workspace can be reused: it holds the design hub and (after B-002) the root files. The
tools are used, not rebuilt: ruff, mypy, pytest and coverage.py for the steps; `uv lock --check`, `uv build` and
`uv audit` (all three confirmed in uv 0.11 by their help output) for the root jobs. Everything else (the AST rules, the
import check, the secret scan, the front matter and body parsing, the byte-exact renderer) is small enough to write
(spec §2). The Sasaah repository has no equivalent to reuse and no code is copied from it (A12).

**Order.** A useful gate reaches CI at T6, the seventh pull request: T1 to T5 build the package, reporting, configuration,
the renderer and the `check` orchestrator with the format, lint, type and lock steps; T26 (numbered last because it was
added last, built before T6) adds the base-commit gate, so that no job is ever wired to the head's own gate by design;
T6 puts `gate`, `agents-drift` and
`build` into the root workflow in place of the skeleton. Every later task adds its step to `check` through
`checks/registry.py` and, when it is a pull-request-context command, its own job, so the gate grows while it already
protects the workspace. The riskiest parts come early among the checks that guard the process itself: `gate-check`
(T13, T14) and `test-first` (T16, T17), because the other tasks are then reviewed under them. After T14 lands, every
later pull request must carry a valid `Plan-Task:` line and, after T17, a `test:` first commit.

**Facts to verify during the work (not assumed here).** Each is recorded in the pull request of the task that needs it:
the key names of coverage.py's JSON report (T7: `totals` must give lines and branches separately); whether ruff and
mypy accept an issue reference inside a `noqa` or `type: ignore` comment (T9; if not, the reference moves to the
line above and AC41 and RT006 are amended by a plan change); that `PYTHONPATH` beats an editable install in the base
worktree (T17, through the import probe); the exit codes of `uv audit` (T18); the SHA of each third-party action
(T6, looked up with the GitHub tools when writing the workflow, never guessed); that `uv run --project <gate-root>
--package eng-dev-gate` runs the base gate in its own environment while the head environment runs the code under test,
that `hashFiles` in a step `if:` sees `.gate-base`, and that `PYTHONPATH` puts the base plugin ahead of an editable
install (T6 and T26, local testing list); Windows support of the mutation
backend (T20, spec §11 Q4).

**Test fixtures.** `tests/support/repo.py` (T2a) builds temporary git repositories with fixed dates and a local identity,
writes the `.gate/` files and a toy package, and returns a handle that runs `cli.main` in-process. External tools and
GitHub are fake ports except in the one integration test per tool step.

## 2. Tasks

Each task is one pull request of at most about 400 changed lines of non-test, non-generated code, starts with a `test:`
commit holding the failing tests, and names `Plan-Task: tools/eng-dev-gate/docs/plans/0001-eng-dev-gate-0.1.md#T<n>`.
The workspace `uv.lock` is regenerated with `uv lock` in tasks that change dependencies (T1, T20).

**T1** creates the package: `pyproject.toml` (project metadata, `[project.scripts] eng-gate`, the runtime dependencies
of §3, dependency groups, its own `[tool.eng-gate]` with profile `tool`), README, CHANGELOG, `.gate/agents.yml` and
`AGENTS.md` (rendered once by following spec §4.13 by hand, since the renderer arrives in T4; T4's test proves the
committed file equals the rendering and re-renders if not), the `CLAUDE.md` pointer, `docs/local-testing.md`, the
dependency ADR (`docs/adr/0001-runtime-dependencies.md`, for the owner queue), and the CLI shell with the exit codes and
`--version`.

**T2a** adds the pieces everything uses: Finding and step results with text, JSON, Actions annotation and summary
output; POSIX glob matching on `PurePosixPath.full_match`; the GitHub event file reader; and the repository fixture.
**T2b** adds the git port and workspace discovery from `[tool.uv.workspace]`. Amendment (B-056): the former single task
T2 measured 573 changed lines of non-test code against its limit of 380, so it is split into T2a and T2b.

**T3** adds `.gate/gate.yml` (initial values: bootstrap on, gate branch `build/v1`, globs, limits), the configuration
models, the floors table with its citations, and the mode logic (read from the base commit in pull-request context,
never from environment or options). It is the first task that touches a protected root path.

**T4** implements `agents render`, `keys` and `drift` and wires them into the CLI. If `agents drift` shows that the
root `AGENTS.md` (or the package's) differs from its rendering, the task re-renders it; otherwise those files stay
untouched.

**T5** adds the `check` orchestrator, the step registry and the `lock`, `format`, `lint` and `types` steps with the
explicit tool configuration of spec §4.12.

**T6** replaces the CI skeleton with the thin root workflow and the composite actions `setup`, `gate`,
`agents-drift` and `build`, with the base-first steps of spec §4.14 (head checkout, base checkout into `.gate-base`,
each action in a base variant with `gate-root` and a guarded head variant; `.gate-base/` in `.gitignore`), adds the `packages` command (names and JSON), and records which Actions steps still need a
real run in `docs/local-testing.md`. This is the first useful gate job.

**T7** adds the `tests` step (coverage run, JSON parse, separate line and branch thresholds) and the pytest plugin
(Hypothesis `ci` profile, deselection guard). **T8** adds the `config` step. **T9** adds the ratchet.

**T10 and T11** build the `forbidden` engine and its eight rules in two pull requests: T10 holds the engine, scope
handling, `.gate/forbidden.yml` and the four simpler rules; T11 holds the I/O, numeric literal, rationale and
collection-hook rules, whose false-positive behavior needs the most test cases.

**T12** adds the `imports` check with the layer, public module, declared dependency, Sasaah, third-party and cycle rules.

**T13 and T14** build `gate-check`: T13 has the front matter models, body parsing, plan and task lookup on the gate
branch, scope globs and the budget; T14 has the spec and plan pull-request rule, the lane, the `none` reasons, the
CODEOWNERS matcher, the base-branch rules, the bootstrap `awaiting owner` reports, and the job. **T15** adds
`risk-floor` and its job.

**T16 and T17** build `test-first`: T16 has the title, exemptions, commit selection and the AST detection of new or
changed tests; T17 has the temporary base worktree, the pytest runs, the classification, the isolation probe, the
cleanup and the job.

**T18** adds `secrets` and the `security` job (secret scan plus `uv audit --locked`). **T19** adds `licenses` and the
generated-document freshness. **T20** adds `mutation` after choosing the backend in a second package-local ADR
(`docs/adr/0002-mutation-backend.md`). **T21** adds the `workflows` lint, including WF005, the shape of `ci.yml` that keeps every pull-request job on the gate
of the base commit.

**T22** adds the pinned reviewer prompts with their hash manifest, the `review` command, and the `ci-review` job; it
writes the prompts from the checklist of process/06 §2 and the severities of §3, and treats all pull request content
as data. **T23** adds `windows-tests` and the `windows` job (push to `build/v1` only). **T24** adds the approvals
port, a GitHub REST adapter (standard-library HTTP) behind it, and the verification paths that run when bootstrap is off;
all of it is tested with fakes and none of it can be run for real until identities exist (local testing list).

**T26** adds the gate root (spec §4.16): the global `--gate-root` option, the reader that takes `.gate/gate.yml`,
`.gate/forbidden.yml`, the base risk map and the prompts from it while the sources stay the head tree, the provenance
checks (CF009 for a gate root that is not the base commit or does not hold the running package; AW09 or CF009 for a head
run, by mode and by whether the base has the job's action), and the table from command to job. Every later check reads
its policy through this reader, never from the working tree directly; the review of each later task checks that. Changes
to the gate take effect from the next pull request: once T6 has put the jobs into CI, each task is judged by the gate of
its base commit.

**T25** completes the README (every command, with an example), the CHANGELOG entry for 0.1.0, and the local-testing
file, and confirms that the whole workspace passes its own gate in CI (AC64). The tag `eng-dev-gate-v0.1.0` is created
after the owner approves; it is not part of this plan.

## 3. Dependencies

New runtime dependencies (each needs the package-local ADR of process/04 §7; ADR-0001 lists purpose, alternatives,
license, maintenance and size; **owner queue**):

| Dependency | Purpose | License (to be verified by the license check in T19 and recorded in the ADR) |
|---|---|---|
| PyYAML | Safe YAML loading of front matter, `.gate/*.yml` and workflows | MIT |
| Pydantic (v2) | Boundary models for configuration, front matter, events and results (process/04 §5) | MIT |
| ruff | Format and lint steps, pinned so packages cannot choose another version | MIT |
| mypy | Strict type step, pinned for the same reason | MIT |
| pytest | Test runner and the plugin host | MIT |
| coverage | Line and branch coverage | Apache-2.0 |

T20 adds one mutation tool (mutmut or cosmic-ray, chosen there with ADR-0002; both are expected to be on the allowed
list). Development dependencies: Hypothesis (property tests of glob matching, escaping and the placeholder scanner;
MPL-2.0 is allowed). The build backend is the one chosen by B-002 for the workspace, or the uv build backend if none is
set. There is no dependency on another workspace package.

## 4. Verification

- Local gate per task: `uv run eng-gate check` once it exists (T5 onward); before that, `uv run ruff format --check`,
  `uv run ruff check`, `uv run mypy --strict` and `uv run pytest` by hand. Each pull request links its CI run.
- Fake-host scenarios do not apply (the gate touches no host). The equivalent is the temporary-repository integration
  tests listed per task.
- Needs local test or an owner action (none was run in the build environment): `eng-gate check` on Windows; the
  Windows job; the mutation backend on Windows (T20); the approvals adapter against real GitHub reviews and the
  identities (T24); the `ci-review` providers (not in 0.1); the first real GitHub Actions run of every job, including
  the SHA pins and the `edited` trigger (each CI task reports its run). They are listed in the package's
  `docs/local-testing.md`, which the lead merges into the workspace `LOCAL-TESTING.md`.
- Live acceptance scripts: none; the gate drives no host program.

## 5. Rollback

Every task is a separate squash-merged pull request: revert the merge commit. The CI jobs are separate, so a
misbehaving job is reverted without losing the others (reverting touches `.github/workflows/ci.yml`, a protected path:
a revert needs the owner's review, or the lead's in bootstrap mode). If a rule produces false positives in a downstream
package before it is fixed, the fix is a new task or a pull request on the rule; the rule is never disabled by
configuration. Until T14 lands there is no gate on pull requests, only on `check`; after it, an emergency revert follows
[process/12](../../../../design/process/12-operations.md) §1.
