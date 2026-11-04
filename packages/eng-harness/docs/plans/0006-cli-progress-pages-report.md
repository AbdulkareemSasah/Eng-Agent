---
id: plan-b065-cli-progress-pages-report
issue: "B-065"
spec: packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r3]               # r3 because T3 touches pyproject.toml and pages/** has the r3 path floor
tasks:
  - id: T1
    title: "Text, date and number formatting and sanitizing"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/_text.py"
      - "packages/eng-harness/tests/property/test_text_sanitize.py"
      - "packages/eng-harness/tests/rules/test_culture_invariant.py"
      - "packages/eng-harness/tests/unit/test_text.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/property/test_text_sanitize.py::test_no_control_sequences"
      - "packages/eng-harness/tests/rules/test_culture_invariant.py::test_no_locale_calls"
    covers: [AC21, AC58]
    depends_on: []
  - id: T2
    title: "HTML builder: escaping by construction, safe tokens, labeled untrusted fields, style hash"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/_html.py"
      - "packages/eng-harness/src/eng_harness/pages/_css.py"
      - "packages/eng-harness/tests/unit/test_html.py"
      - "packages/eng-harness/tests/property/test_html_escape.py"
    max_changed_lines: 280
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/test_html.py::test_attributes_accept_only_tokens"
    covers: [AC49]
    depends_on: [T1]
  - id: T3
    title: "Command line shell: parser, exit codes, configuration, output encoding, launch-address opener, entry point"
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/__main__.py"
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"
      - "packages/eng-harness/src/eng_harness/cli/_parser.py"
      - "packages/eng-harness/src/eng_harness/cli/_exit.py"
      - "packages/eng-harness/src/eng_harness/cli/_config.py"
      - "packages/eng-harness/src/eng_harness/cli/_encoding.py"
      - "packages/eng-harness/src/eng_harness/cli/_opener.py"
      - "packages/eng-harness/tests/unit/cli/test_opener.py"
      - "packages/eng-harness/tests/unit/cli/test_parser.py"
      - "packages/eng-harness/tests/unit/cli/test_exit_codes.py"
      - "packages/eng-harness/tests/unit/cli/test_config.py"
      - "packages/eng-harness/tests/unit/cli/test_encoding.py"
      - "packages/eng-harness/tests/rules/test_cli_cannot_answer.py"
      - "packages/eng-harness/tests/rules/test_imports.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_parser.py::test_commands_exact_and_no_approve"
      - "packages/eng-harness/tests/unit/cli/test_opener.py::test_browser_variable_ignored"
      - "packages/eng-harness/tests/rules/test_cli_cannot_answer.py::test_no_answer_construction_outside_pages"
      - "packages/eng-harness/tests/unit/cli/test_exit_codes.py::test_outcome_mapping"
      - "packages/eng-harness/tests/unit/cli/test_config.py::test_discovery_and_sections"
      - "packages/eng-harness/tests/unit/cli/test_encoding.py::test_redirected_output_is_utf8"
      - "packages/eng-harness/tests/rules/test_imports.py::test_third_party_imports_limited"
    covers: [AC1, AC2, AC3, AC4, AC5, AC60, AC61]
    depends_on: [T1]
  - id: T4
    title: "Expected times from earlier journals and the progress renderer"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/progress/__init__.py"
      - "packages/eng-harness/src/eng_harness/progress/_expected.py"
      - "packages/eng-harness/src/eng_harness/progress/_render.py"
      - "packages/eng-harness/tests/unit/progress/test_expected.py"
      - "packages/eng-harness/tests/unit/progress/test_render_waiting.py"
      - "packages/eng-harness/tests/property/test_expected_bounds.py"
      - "packages/eng-harness/tests/golden/test_progress_render.py"
      - "packages/eng-harness/tests/data/snapshots/progress/**"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/progress/test_expected.py::test_median_range_and_min_samples"
      - "packages/eng-harness/tests/property/test_expected_bounds.py::test_median_within_range"
      - "packages/eng-harness/tests/golden/test_progress_render.py::test_tty_plain_json"
      - "packages/eng-harness/tests/unit/progress/test_render_waiting.py::test_waiting_shows_no_expected_or_url"
    covers: [AC15, AC16, AC17]
    depends_on: [T1]
  - id: T5
    title: "Non-blocking progress sink, heartbeat task and liveness reader"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/progress/_sink.py"
      - "packages/eng-harness/src/eng_harness/progress/_heartbeat.py"
      - "packages/eng-harness/tests/unit/progress/test_sink.py"
      - "packages/eng-harness/tests/unit/progress/test_heartbeat.py"
      - "packages/eng-harness/tests/perf/test_progress_latency.py"
    max_changed_lines: 280
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/progress/test_heartbeat.py::test_heartbeat_without_events"
      - "packages/eng-harness/tests/unit/progress/test_sink.py::test_blocked_stream_does_not_block_engine"
      - "packages/eng-harness/tests/perf/test_progress_latency.py::test_event_to_line_p95"
    covers: [AC18, AC19, AC20]
    depends_on: [T4]
  - id: T6
    title: "Page server: loopback bind, launch code and session, Host, Origin and CSRF checks, headers, routes, lockdown"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/__init__.py"
      - "packages/eng-harness/src/eng_harness/pages/_security.py"
      - "packages/eng-harness/src/eng_harness/pages/_server.py"
      - "packages/eng-harness/src/eng_harness/pages/_routes.py"
      - "packages/eng-harness/tests/helpers/page_client.py"
      - "packages/eng-harness/tests/unit/pages/test_server_bind.py"
      - "packages/eng-harness/tests/unit/pages/test_session_token.py"
      - "packages/eng-harness/tests/unit/pages/test_request_checks.py"
      - "packages/eng-harness/tests/unit/pages/test_headers_and_markup.py"
      - "packages/eng-harness/tests/unit/pages/test_routes.py"
      - "packages/eng-harness/tests/unit/pages/test_lockdown.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/pages/test_server_bind.py::test_loopback_random_port"
      - "packages/eng-harness/tests/unit/pages/test_session_token.py::test_launch_code_once"
      - "packages/eng-harness/tests/unit/pages/test_request_checks.py::test_host_origin_fetch_metadata"
      - "packages/eng-harness/tests/unit/pages/test_request_checks.py::test_csrf_bound_to_request_and_hash"
      - "packages/eng-harness/tests/unit/pages/test_headers_and_markup.py::test_csp_and_no_active_content"
      - "packages/eng-harness/tests/unit/pages/test_routes.py::test_route_table_and_limits"
      - "packages/eng-harness/tests/unit/pages/test_lockdown.py::test_failed_requests_lock_server"
      - "packages/eng-harness/tests/unit/pages/test_lockdown.py::test_shutdown_releases_port"
    covers: [AC22, AC23, AC24, AC25, AC26, AC27, AC28]
    depends_on: [T2]
  - id: T7
    title: "Answer models and checks, approval and input ports, durable wait, stop-file run control"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/_answers.py"
      - "packages/eng-harness/src/eng_harness/pages/_ports.py"
      - "packages/eng-harness/src/eng_harness/pages/_wait.py"
      - "packages/eng-harness/src/eng_harness/cli/_control.py"
      - "packages/eng-harness/tests/unit/pages/test_answer_models.py"
      - "packages/eng-harness/tests/unit/pages/test_answer_validation.py"
      - "packages/eng-harness/tests/unit/pages/test_single_use.py"
      - "packages/eng-harness/tests/unit/pages/test_wait.py"
      - "packages/eng-harness/tests/unit/pages/test_index.py"
      - "packages/eng-harness/tests/workflow/test_page_approval.py"
    max_changed_lines: 390
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/test_page_approval.py::test_answer_bound_to_hash"
      - "packages/eng-harness/tests/unit/pages/test_single_use.py::test_concurrent_answers_one_wins"
      - "packages/eng-harness/tests/unit/pages/test_answer_validation.py::test_reasons_and_items"
      - "packages/eng-harness/tests/unit/pages/test_answer_models.py::test_answers_carry_no_values"
      - "packages/eng-harness/tests/unit/pages/test_wait.py::test_stop_ends_wait"
      - "packages/eng-harness/tests/workflow/test_page_approval.py::test_page_confirms_after_commit"
      - "packages/eng-harness/tests/unit/pages/test_index.py::test_multiple_open_requests"
      - "packages/eng-harness/tests/unit/pages/test_answer_validation.py::test_name_rules_and_no_os_account"
    covers: [AC29, AC30, AC31, AC32, AC36, AC37, AC38, AC39]
    depends_on: [T5, T6]
  - id: T8
    title: "Report package skeleton, release marks and lineage closure"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/__init__.py"
      - "packages/eng-harness/src/eng_harness/report/_lineage.py"
      - "packages/eng-harness/tests/unit/report/test_release_marks.py"
      - "packages/eng-harness/tests/property/test_release_marks.py"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/property/test_release_marks.py::test_marked_set_is_closure"
      - "packages/eng-harness/tests/unit/report/test_release_marks.py::test_marks_everywhere"
    covers: [AC54]
    depends_on: [T1]
  - id: T9
    title: "Approval screens: change set, promotion, info and sign-off"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/_labels.py"
      - "packages/eng-harness/src/eng_harness/pages/_screens_approval.py"
      - "packages/eng-harness/tests/golden/test_screens.py"
      - "packages/eng-harness/tests/data/snapshots/screens/**"
      - "packages/eng-harness/tests/workflow/test_signoff.py"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/golden/test_screens.py::test_change_set_screen"
      - "packages/eng-harness/tests/golden/test_screens.py::test_promotion_and_info_screens"
      - "packages/eng-harness/tests/workflow/test_signoff.py::test_signoff_rules"
    covers: [AC40, AC41, AC42]
    depends_on: [T2, T7, T8]
  - id: T10
    title: "Choice screens (engineer turn, batched decisions, engine requests), the read-only input screen and the answers-file gate"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/_screens_choice.py"
      - "packages/eng-harness/src/eng_harness/pages/_answers_file.py"
      - "packages/eng-harness/tests/unit/pages/test_choice_screen.py"
      - "packages/eng-harness/tests/unit/pages/test_answers_file.py"
    max_changed_lines: 370
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/pages/test_choice_screen.py::test_engineer_turn_three_options"
      - "packages/eng-harness/tests/unit/pages/test_choice_screen.py::test_batched_decisions_one_submit"
      - "packages/eng-harness/tests/unit/pages/test_choice_screen.py::test_engine_requests_choices"
      - "packages/eng-harness/tests/unit/pages/test_answers_file.py::test_file_refuses_choice_engine_and_unmarked_requests"
    covers: [AC43, AC44, AC45, AC46]
    depends_on: [T2, T7]
  - id: T11
    title: "Report model: fold the journal and the store; timings, waiting and machine time"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_model.py"
      - "packages/eng-harness/tests/unit/report/test_timings.py"
      - "packages/eng-harness/tests/fixtures/report_run.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/report/test_timings.py::test_wait_and_run_times"
    covers: [AC56]
    depends_on: [T8]
  - id: T12
    title: "Report sections: changes, results, sources, decisions; renderer registry; value cells with sources"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_sections.py"
      - "packages/eng-harness/tests/unit/report/test_sources.py"
      - "packages/eng-harness/tests/unit/report/test_changes.py"
      - "packages/eng-harness/tests/golden/test_report.py"
      - "packages/eng-harness/tests/data/snapshots/report/**"
    max_changed_lines: 390
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/report/test_sources.py::test_every_value_has_source"
      - "packages/eng-harness/tests/unit/report/test_changes.py::test_changes_decisions_revisions"
      - "packages/eng-harness/tests/golden/test_report.py::test_report_snapshot"
    covers: [AC51, AC52, AC55]
    depends_on: [T2, T11]
  - id: T13
    title: "Report document: DRAFT and completeness marks, integrity line, policy meta, atomic UTF-8 write"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_document.py"
      - "packages/eng-harness/src/eng_harness/report/_write.py"
      - "packages/eng-harness/tests/unit/report/test_build_report.py"
      - "packages/eng-harness/tests/unit/report/test_draft_mark.py"
      - "packages/eng-harness/tests/unit/report/test_write.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/report/test_build_report.py::test_inputs_only_and_deterministic"
      - "packages/eng-harness/tests/unit/report/test_build_report.py::test_tampered_refused_live_banner"
      - "packages/eng-harness/tests/unit/report/test_draft_mark.py::test_draft_signed_and_sources"
      - "packages/eng-harness/tests/unit/report/test_write.py::test_utf8_lf_atomic"
    covers: [AC50, AC53, AC57, AC59]
    depends_on: [T12]
  - id: T14
    title: "Commands run and resume: wiring, generated options, answers file, signals, outcome mapping"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/_options.py"
      - "packages/eng-harness/src/eng_harness/cli/_run.py"
      - "packages/eng-harness/src/eng_harness/cli/_signals.py"
      - "packages/eng-harness/src/eng_harness/cli/_wiring.py"
      - "packages/eng-harness/tests/unit/cli/test_options.py"
      - "packages/eng-harness/tests/unit/cli/test_run_refusals.py"
      - "packages/eng-harness/tests/unit/cli/test_signals.py"
      - "packages/eng-harness/tests/workflow/test_cli_run.py"
      - "packages/eng-harness/tests/workflow/test_cli_answers.py"
      - "packages/eng-harness/tests/workflow/test_launch_address.py"
      - "packages/eng-harness/tests/replay/test_cli_resume.py"
    max_changed_lines: 400
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_run_refusals.py::test_refusals_create_no_run"
      - "packages/eng-harness/tests/workflow/test_cli_run.py::test_run_completes_and_writes_report"
      - "packages/eng-harness/tests/replay/test_cli_resume.py::test_no_wait_then_resume"
      - "packages/eng-harness/tests/unit/cli/test_signals.py::test_first_interrupt_requests_stop"
      - "packages/eng-harness/tests/unit/cli/test_options.py::test_generated_options_exclude_quantities"
      - "packages/eng-harness/tests/workflow/test_cli_answers.py::test_form_request_answers_file"
      - "packages/eng-harness/tests/workflow/test_launch_address.py::test_address_never_on_stdout_or_stderr"
    covers: [AC6, AC7, AC8, AC10, AC14, AC46, AC61]
    depends_on: [T3, T5, T7, T9, T10, T13]
  - id: T15
    title: "Basis confirmation screen, setup log and its place in run"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/_screens_basis.py"
      - "packages/eng-harness/tests/workflow/test_cli_basis.py"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/test_cli_basis.py::test_basis_confirmation_flow"
      - "packages/eng-harness/tests/workflow/test_cli_basis.py::test_reject_leaves_no_run"
      - "packages/eng-harness/tests/workflow/test_cli_basis.py::test_stale_draft_hash_refused"
    covers: [AC47]
    depends_on: [T14]
  - id: T16
    title: "Commands status, stop, report and doctor"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/_status.py"
      - "packages/eng-harness/src/eng_harness/cli/_stop.py"
      - "packages/eng-harness/tests/unit/cli/test_status.py"
      - "packages/eng-harness/tests/unit/cli/test_report_command.py"
      - "packages/eng-harness/tests/unit/cli/test_doctor_command.py"
      - "packages/eng-harness/tests/workflow/test_cli_stop.py"
    max_changed_lines: 330
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_status.py::test_states_and_read_only"
      - "packages/eng-harness/tests/workflow/test_cli_stop.py::test_stop_pauses_at_safe_point"
      - "packages/eng-harness/tests/unit/cli/test_report_command.py::test_output_rules"
      - "packages/eng-harness/tests/unit/cli/test_doctor_command.py::test_exit_code_passthrough"
    covers: [AC9, AC11, AC12, AC13]
    depends_on: [T14]
  - id: T17
    title: "End-to-end approval, replay and untrusted-text tests; Arabic environment; local testing list; agent rule"
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/.gate/agents.yml"
      - "packages/eng-harness/tests/property/test_untrusted_text.py"
      - "packages/eng-harness/tests/replay/test_page_resume.py"
      - "packages/eng-harness/tests/windows/test_arabic_environment.py"
      - "packages/eng-harness/tests/workflow/test_page_approval.py"
    max_changed_lines: 150
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/test_page_approval.py::test_per_item_reject_end_to_end"
      - "packages/eng-harness/tests/workflow/test_page_approval.py::test_void_after_model_change"
      - "packages/eng-harness/tests/replay/test_page_resume.py::test_kill_while_waiting_then_resume"
      - "packages/eng-harness/tests/property/test_untrusted_text.py::test_every_screen_and_report_escape"
      - "packages/eng-harness/tests/windows/test_arabic_environment.py::test_arabic_workspace_and_cp1256"
    covers: [AC33, AC34, AC35, AC48, AC58]
    depends_on: [T15, T16]
---

# Implementation plan: eng-harness command line, progress, approval page and run report

## 1. Approach

The spec is [0006](../specs/0006-cli-progress-pages-report.md). `max_changed_lines` counts non-test, non-generated
lines (process/04 §4); tests and snapshots are on top. The order puts the security-critical and shared pieces first and
lets the rest stack on them:

- T1 and T2 are the two modules every other task depends on for correctness: sanitizing and formatting (`_text.py`),
  and the HTML builder in which untrusted text can only enter escaped and labeled (`_html.py`). They are small and
  property-tested before any screen exists.
- T3 creates the entry point and the parser first, so that "no approve command" (AC1) and "the command line cannot
  answer" (AC2, a static test) hold from the start and every later task is checked against them. It also adds the
  `[project.scripts]` entry and the new public modules to `[tool.eng-gate]` (the reason for r3).
- T4 and T5 (progress) have no page dependency and can be built in parallel with T6 to T10 by another agent.
- T6 is the riskiest task (the security checks of 16 §5): bind, session, Host, Origin, CSRF, headers, routes,
  lockdown, tested against a real loopback server. T7 adds the answer path (hash binding, single use, reasons) and
  the durable wait; T9 and T10 add the screens. T8 (release marks) precedes T9 because the sign-off screen lists the
  marked results.
- T11 to T13 build the report from the journal and the store only. T11 folds the data; T12 renders sections and the
  source links; T13 adds the marks, the integrity line, the policy and the atomic write.
- T14 to T16 wire the commands: run and resume first (they exercise everything), then the basis confirmation inside
  `run`, then status, stop, report and doctor. T17 closes with the cross-cutting end-to-end tests, the Windows Arabic
  environment test, the local testing list and the agent rule.

No new runtime dependency: `http.server`, `argparse`, `subprocess`, `statistics`, `secrets`, `hmac` and `html` from the
standard library (spec §2, Q1). Reuse: `JournalReader`, the ports and `Event` from engine T4 and T6; `ResultStore`
and `Quantity` from the contract; `BasisSetupPort` from plan 0004 T7; `eng_harness.doctor.run` from plan 0002 T18.

## 2. Tasks

**T1 Text** (spec §4.7). `format_duration_ms`, `format_timestamp`, `format_number`, `sanitize_terminal`,
`sanitize_html`, `truncate`; the rules test that no module of this spec imports `locale` or uses locale-dependent
time directives.

**T2 HTML builder** (spec §4.5). `Text`, `Trusted`, `SafeToken`, `field(label, value)` with `<bdi dir="auto">`,
element builder, style element and its SHA-256 for the policy. Property tests on escaping.

**T3 Shell** (spec §4.1, §4.2.1, §4.2.3, §4.2.4, §4.4.4). `main(argv, deps)`, six subcommands registered as stubs that
call into later modules, `ExitCode`, `HarnessConfig` with strict sections, stream encoding setup, the launch-address
opener of `CliDeps` (platform opener with `BROWSER` removed; writer to the controlling terminal only); `[project.scripts]`,
`__main__`, `public_modules`. The rules tests for AC2 and AC60 start here and tighten as modules appear.

**T4 Progress display** (spec §4.3). `ExpectedTimes.build` (read-only journals, median, range, sample floor) and
`ProgressRenderer` for the three modes, with text snapshots.

**T5 Sink and heartbeat** (spec §4.3). The bounded queue and writer thread, `TerminalProgress.emit`, the heartbeat
task and `heartbeat.json`, `read_liveness`, and the 200 ms latency test.

**T6 Server and security** (spec §4.4.1 to §4.4.3). `PageServer`, launch code, session cookie `eh_<port>_session`, CSRF
token with the per-route inputs of spec §4.4.2 (approval, choice, setup; the test is parametrized over the three), Host,
Origin and Fetch Metadata checks, headers, route table with limits, lockdown, shutdown. `tests/helpers/page_client.py`
is the loopback client used by all page tests. Security lens review.

**T7 Answers and ports** (spec §4.4.5). `ApprovalSubmission` and the answer models in `pages/_answers.py` (no value members), the checks,
`PageApprovalPort` and `PageInputPort` (present, awaitable answer, `wait=False`, stop, timeout), the per-request lock,
acknowledgement after the sink sees `approval_resolved`, `FileRunControl` (stop file). Security lens review.

**T8 Release marks** (spec §4.6.3). `ReleaseMarks`, `unreleased_dependencies` with the breadth-first closure over
`parents` and provenance inputs, the depth limit, and the package skeleton of `report/`. The property test compares
with an independent reachability oracle on random graphs.

**T9 Approval screens** (spec §4.4.6). Change set, promotion, info and sign-off with the exception and
acknowledgement rules; `_labels.py` catalog; snapshots.

**T10 Choice screens** (spec §4.4.6). Choice sets from the request's JSON Schema (engineer turn, batched decisions,
engine requests) and the read-only input screen; `pages.accept_answers_file`, the only way a file becomes an
`InputAnswer`: it accepts a `block` request with `x-eng-input: data` and refuses `engine.*`, choice and unmarked
requests.

**T11 Report model** (spec §4.6.1 sections 5 to 7). Folding `JournalReader` views and store records into a
`ReportModel`; waiting and machine time. A shared fixture run (`tests/fixtures/report_run.py`) is reused by T12 and T13.

**T12 Report sections** (spec §4.6.1). Renderer registry, generic bounded renderer, `value_cell(value, source)` with
the mandatory source, the sources table, changes and results; snapshot.

**T13 Report document** (spec §4.6.2). Status banner and marks, integrity line, policy meta, `build_report`,
`write_report`.

**T14 Run and resume** (spec §4.2.2). Generated options, `CliDeps` wiring of engine, adapters, calcs, decision and page
ports, signal handling, outcome mapping, `--answers` through `pages.accept_answers_file`, report at the end, launch
address shown on the controlling terminal only (AC61). Fake-host workflow and replay tests.

**T15 Basis confirmation** (spec §4.4.7). The screen, the answer, the setup log and the early steps of `run`.

**T16 status, stop, report, doctor** (spec §4.2.1, §4.3 heartbeat). Read-only status, the `stop` command in
`cli/_stop.py` (it writes and waits on the stop file whose protocol lives in `cli/_control.py`, T7),
the report command, the doctor pass-through.

**T17 End to end** (spec §3.4, §3.6, §3.7). Per-item rejection and void flows through the page, the killed-wait replay,
the all-screens untrusted text property test, the Windows Arabic test (Arabic workspace path, cp1256 console,
`ar-SA` culture where present), `docs/local-testing.md`, and the rule "approvals are the engineer's; never read or relay
the launch address" in `packages/eng-harness/.gate/agents.yml`, with `AGENTS.md` and `CLAUDE.md` re-rendered by
`eng-gate agents render` when that tool exists, otherwise by the first task after it exists.

## 3. Dependencies

- Runtime: none new (`eng-contract`, `pydantic`; the YAML and MCP dependencies belong to plans 0004 and 0002). No
  package ADR is needed. Using Jinja2 instead would need one (A10; spec Q1).
- Development: none new.
- Other plans: engine plan T4 (reader), T6 (ports), T9 (runner), T15 (approvals), T18 (progress delivery);
  plan 0002 T18 (doctor) and the adapter wiring `build_ports`; plan 0003 `HarnessCalcPort` and `preflight`; plan 0004
  T7 (`BasisSetupPort`, `build_setup_view`) and T8 (`freeze`); plan 0007 for the workflow registry. T14 and T15 use
  fakes and `CliDeps` until the real ones merge, so they do not wait; the pull request that finds the real
  implementation missing states it.
- Amendments to other documents (spec §11): engine §4.4.1 (`inbox/`), engine §4.9 (`item_reasons`, the choice
  convention and the `x-eng-input` marker), spec 0002 (tool `release`, doctor checks). They are owner queue items, not part of any task here.

## 4. Verification

Local gate per task as in the engine plan §4; the pull request links its CI run. Review lenses: correctness, Python,
type design, silent failure, tests; T3, T6, T7, T9, T10 and T15 additionally with the security lens (T10: the answers-file gate; T3 and T14: the launch address) (what an agent, a
web page in the browser, or a hostile drawing text can do); T8, T11 to T13 additionally against ADR-0026 §3 and the
rule "built only from the journal and the store". The second-family review and the owner's approvals are
`awaiting owner` in bootstrap mode.

Windows CI job: `tests/windows/` (Arabic environment) and `tests/perf/` (progress latency). Page tests bind the
loopback interface only.

Needs local test (listed in `docs/local-testing.md` by T17): (1) the approval page in the owner's real browser: no
Content-Security-Policy violation in the console, Arabic and mixed-direction text from a real drawing and model
displays correctly, forms submit, a second tab opens by cookie; (2) the report opened and printed from disk: the DRAFT
watermark and the layout; (3) a workstation with an Arabic regional setting, the Hijri calendar and a cp1256 console:
`run`, `status`, `report`; (4) expected times and the heartbeat on a real analysis run, with the host programs (this
needs spec 0007's workflow and the Sasaah servers); (5) opening the launch address through the default browser when
the default is not Chromium-based. Nothing here drives a host program in CI.

## 5. Rollback

Each task is one squash-merged pull request; nothing outside this package consumes it until spec 0007's workflow runs.
Reverting a task reverts its dependants. The page and the report hold no state: a defect is fixed forward and a report
is rebuilt from the journal with `eng-harness report`. A changed exit code or JSON key is a public change (spec §10).
The `item_reasons` member of the journal (spec Q8) is read by readers with and without it.
