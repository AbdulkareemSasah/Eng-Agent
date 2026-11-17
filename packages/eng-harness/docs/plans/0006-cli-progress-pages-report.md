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
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.pages (amendment B-356)
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
  - id: T2b
    title: "In-page fragment links in the HTML builder"
    # Amendment (B-435, documents only): new; T12 cannot link a value cell to its sources row (AC52) without it.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/_html.py"
      - "packages/eng-harness/tests/unit/test_html.py"
    max_changed_lines: 60
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/test_html.py::test_fragment_href"
    covers: [AC52]
    depends_on: [T2]
  - id: T3
    title: "Command line shell: parser, exit codes, configuration, output encoding, entry point"
    # Amendment (B-359): split; the launch-address opener moves to T3b (the task measured 418 lines against the 400-line cap, D-12).
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/__main__.py"
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"
      - "packages/eng-harness/src/eng_harness/cli/_parser.py"
      - "packages/eng-harness/src/eng_harness/cli/_exit.py"
      - "packages/eng-harness/src/eng_harness/cli/_config.py"
      - "packages/eng-harness/src/eng_harness/cli/_encoding.py"
      - "packages/eng-harness/tests/unit/cli/test_parser.py"
      - "packages/eng-harness/tests/unit/cli/test_exit_codes.py"
      - "packages/eng-harness/tests/unit/cli/test_config.py"
      - "packages/eng-harness/tests/unit/cli/test_encoding.py"
      - "packages/eng-harness/tests/rules/test_cli_cannot_answer.py"
      - "packages/eng-harness/tests/rules/test_imports.py"
    max_changed_lines: 380
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_parser.py::test_commands_exact_and_no_approve"
      - "packages/eng-harness/tests/rules/test_cli_cannot_answer.py::test_no_answer_construction_outside_pages"
      - "packages/eng-harness/tests/unit/cli/test_exit_codes.py::test_outcome_mapping"
      - "packages/eng-harness/tests/unit/cli/test_config.py::test_discovery_and_sections"
      - "packages/eng-harness/tests/unit/cli/test_encoding.py::test_redirected_output_is_utf8"
      - "packages/eng-harness/tests/rules/test_imports.py::test_third_party_imports_limited"
      - "packages/eng-harness/tests/unit/cli/test_parser.py::test_entry_point_and_root_form"
    covers: [AC1, AC2, AC3, AC4, AC5, AC60, AC65]
    depends_on: [T1]
  - id: T3b
    title: "Launch-address opener: platform opener with BROWSER removed, address to the controlling terminal only"
    # Amendment (B-359): the opener part of the former T3; CliDeps gets its default opener here.
    files:
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"
      - "packages/eng-harness/src/eng_harness/cli/_opener.py"
      - "packages/eng-harness/tests/unit/cli/test_opener.py"
    max_changed_lines: 100
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_opener.py::test_browser_variable_ignored"
    covers: [AC61]
    depends_on: [T3]
  - id: T4
    title: "Expected times from earlier journals and the progress renderer"
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.progress (amendment B-356)
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
    # Amendment (B-412, documents only): progress/__init__.py added for the public names of spec 4.1; AC19 here is the sink alone (the engine detach is engine AC58, re-checked in T17).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.progress (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/progress/__init__.py"
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
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.pages (amendment B-356)
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
    title: "Answer models and checks, approval and input ports, durable wait"
    # Amendment (B-412 eighth review, documents only): cli/_control.py (stop-file protocol) moves to the new T7b with the voided display; re-estimated 390 -> 340.
    # Amendment (B-412, documents only): pages/__init__.py added; stop-file protocol of spec 4.4.8; dispatch mapping with refusal fallback; report callable; engine stand-in in workflow tests.
    # Amendment (B-412 fourth review, documents only): tests/helpers/engine_standin.py added (the shared engine stand-in that T9 imports).
    # Amendment (B-412 fifth review, documents only): the page ports take the stop check by injection (pages may not import cli).
    # Amendment (B-412 ninth review, documents only): paragraph no longer lists FileRunControl as T7 work (it is T7b's).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.cli, eng_harness.pages (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/__init__.py"
      - "packages/eng-harness/src/eng_harness/pages/_answers.py"
      - "packages/eng-harness/src/eng_harness/pages/_ports.py"
      - "packages/eng-harness/src/eng_harness/pages/_wait.py"
      - "packages/eng-harness/tests/helpers/engine_standin.py"
      - "packages/eng-harness/tests/unit/pages/test_answer_models.py"
      - "packages/eng-harness/tests/unit/pages/test_answer_validation.py"
      - "packages/eng-harness/tests/unit/pages/test_single_use.py"
      - "packages/eng-harness/tests/unit/pages/test_wait.py"
      - "packages/eng-harness/tests/unit/pages/test_index.py"
      - "packages/eng-harness/tests/workflow/test_page_approval.py"
    # About 120 lines for the answer models and checks, 140 for the ports, dispatch, refusal fallback and the two
    # injected callables, 40 for the wait, 30 for the acknowledgement and 10 for the exports (an estimate).
    max_changed_lines: 340
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
  - id: T7b
    title: "Stop-file run control and the voided approval display"
    # Amendment (B-412 eighth review, documents only): new; the stop-file protocol of spec 4.4.8 (moved from T7) and the page's voided display of AC34 (spec 4.4.5), so that T17 adds tests only.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/_control.py"
      - "packages/eng-harness/src/eng_harness/pages/_ports.py"
      # Amendment (B-517, documents only): the router and the page test helper join T7b for one fix of merged T7 code
      # that local CI found: a second answer that arrives after the first was recorded got 404 from the screen lookup
      # in the router instead of the 409 of AC30, so tests/unit/pages/test_single_use.py::test_concurrent_answers_one_wins
      # failed under load. The lookup takes an `answering` argument on POST (11 counted lines; 100 measured before it).
      - "packages/eng-harness/src/eng_harness/pages/_routes.py"
      - "packages/eng-harness/tests/helpers/page_client.py"
      - "packages/eng-harness/tests/unit/cli/test_control.py"
      - "packages/eng-harness/tests/unit/pages/test_void.py"
    # About 60 lines for FileRunControl and the write, read and remove helpers, 40 for the voided state and screen.
    max_changed_lines: 130
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_control.py::test_stop_file_written_by_rename_and_removed"
      - "packages/eng-harness/tests/unit/pages/test_void.py::test_void_shown_on_resolved_request"
    covers: [AC34]
    depends_on: [T7]
  - id: T8
    title: "Report package skeleton, release marks and lineage closure"
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.report (amendment B-356)
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
    title: "Approval screens: change set, promotion and info"
    # Amendment (B-412, documents only): pages/_ports.py added to register the four screens in the PageApp dispatch; the AC42 test injects a stub report callable.
    # Amendment (B-412 third review, documents only): the AC42 workflow test uses the test-local engine stand-in of T7; T17c re-checks AC42 with the real engine.
    # Amendment (B-412 fourth review, documents only): the stand-in is imported from tests/helpers/engine_standin.py (T7's file), not duplicated.
    # Amendment (B-412 ninth review, documents only): the page ports gain a marks (ReleaseMarks) parameter for the sign-off screen; T14 binds it.
    # Amendment (B-510, documents only): the builder admits only SafeToken field names (AC49), so pages/_answers.py gets token-safe prefixes, with the two tests that pin a "choice:" literal; the 380 estimate plus that change passes the 380 split mark, so the sign-off screen (AC42), the marks parameter and test_signoff.py move to the new T9b; budget 380 -> 270.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.pages (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/_answers.py"
      - "packages/eng-harness/src/eng_harness/pages/_labels.py"
      - "packages/eng-harness/src/eng_harness/pages/_ports.py"
      - "packages/eng-harness/src/eng_harness/pages/_screens_approval.py"
      - "packages/eng-harness/tests/golden/test_screens.py"
      - "packages/eng-harness/tests/data/snapshots/screens/**"
      - "packages/eng-harness/tests/unit/pages/test_answer_validation.py"
      - "packages/eng-harness/tests/unit/pages/test_index.py"
    # About 250 lines for the three screens, the label catalog and the dispatch registration, and 4 for the prefixes (an estimate, not a measurement).
    max_changed_lines: 270
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/golden/test_screens.py::test_change_set_screen"
      - "packages/eng-harness/tests/golden/test_screens.py::test_promotion_and_info_screens"
    covers: [AC40, AC41]
    depends_on: [T2, T7]
  - id: T9b
    title: "Sign-off screen: verdict counts, exceptions with reasons, unreleased tools and the acknowledgement"
    # Amendment (B-510, documents only): new, split from T9; the sign-off screen of spec 4.4.6 (AC42), the page ports' marks parameter (T14 binds it) and the sign-off check before an answer is taken; exception reasons follow the interim reading of spec Q24.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/_labels.py"
      - "packages/eng-harness/src/eng_harness/pages/_ports.py"
      - "packages/eng-harness/src/eng_harness/pages/_screens_approval.py"
      - "packages/eng-harness/tests/workflow/test_signoff.py"
    # About 90 lines for the screen and its labels, 25 for the marks parameter and the check hook, 5 of CHANGELOG.md (an estimate, not a measurement).
    max_changed_lines: 140
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/test_signoff.py::test_signoff_rules"
    covers: [AC42]
    depends_on: [T8, T9]
  - id: T9c
    title: "Sign-off screen reads the edit cycle's design verdicts (harness.host_design_verdicts/1)"
    # Amendment (B-544, documents only): new fix task for merged T9b code (first-live-run walk-through C25, C32; spec
    # 4.4.6, AC42, Q24). _facts counts only results of kind verdicts.set/1, which the edit cycle never stores, so its
    # sign-off shows no exception and refuses nothing. About 6 lines of pages/_screens_approval.py (the kind filter and
    # one model per kind) and 1 of CHANGELOG.md: budget 20 (an estimate).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/_screens_approval.py"
      - "packages/eng-harness/tests/workflow/test_signoff.py"
    max_changed_lines: 20
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/workflow/test_signoff.py::test_signoff_reads_host_design_verdicts"
    covers: [AC42]
    depends_on: [T9b]
  - id: T10
    title: "Choice screens (engineer turn, batched decisions, engine requests), the read-only input screen and the answers-file gate"
    # Amendment (B-412, documents only): depends on T9 (_labels.py); pages/__init__.py, _labels.py and _ports.py added.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.pages (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/__init__.py"
      - "packages/eng-harness/src/eng_harness/pages/_labels.py"
      - "packages/eng-harness/src/eng_harness/pages/_ports.py"
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
    depends_on: [T2, T7, T9]
  - id: T10c
    title: "Page fixes: the voided display matches the engine's request kinds, the input screen tells how a waiting run takes a data answer"
    # Amendment (B-545, documents only): new fix task for merged T7b and T10 code (first-live-run walk-through C28, C27; spec 4.4.5, AC34, AC46).
    # About 2 lines in pages/_ports.py (_VOIDABLE gains change_set and promotion), 3 in pages/_labels.py (INPUT_NOTE) and 1 of CHANGELOG.md: budget 15 (an estimate).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/pages/_ports.py"
      - "packages/eng-harness/src/eng_harness/pages/_labels.py"
      - "packages/eng-harness/tests/unit/pages/test_void.py"
      - "packages/eng-harness/tests/unit/pages/test_choice_screen.py"
    max_changed_lines: 15
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/pages/test_void.py::test_void_marks_the_engine_kinds"
      - "packages/eng-harness/tests/unit/pages/test_choice_screen.py::test_data_request_names_stop_and_resume"
    covers: [AC34, AC46]
    depends_on: [T7b, T10]
  - id: T11
    title: "Report model: fold the journal and the store; timings, waiting and machine time"
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.report (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_model.py"
      - "packages/eng-harness/tests/unit/report/test_timings.py"
      - "packages/eng-harness/tests/fixtures/report_run.py"
      - "packages/eng-harness/tests/fixtures/__init__.py"  # B-426: mypy needs the package marker (one module name for the fixture)
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/report/test_timings.py::test_wait_and_run_times"
    covers: [AC56]
    depends_on: [T8]
  - id: T12
    title: "Report sections: changes, results, sources, decisions; renderer registry; value cells with sources"
    # Amendment (B-412, documents only): the snapshot covers the fragment _sections.py renders (T13 extends it).
    # Amendment (B-412 fifth review, documents only): sections 6 and 7 (timings, run events) move to T13; T12 keeps sections 2 to 5 and its 390 budget.
    # Amendment (B-435, documents only): depends on T2b (fragment links for AC52); section inputs (ReportModel, JournalReader, ResultStore).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.report (amendment B-356)
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
    depends_on: [T2, T2b, T11]
  - id: T13
    title: "Report document: DRAFT and completeness marks, integrity line, policy meta, timings and run events sections, atomic UTF-8 write"
    # Amendment (B-412, documents only): report/__init__.py added; the report snapshot extended to the whole document (AC51).
    # Amendment (B-412 fifth review, documents only): sections 6 and 7 of spec 4.6.1 (timings, run events) rendered here, from T12; budget 300 -> 380.
    # Amendment (B-435, documents only): report/_model.py, test_timings.py and its fixture added: resumes counted and listed by distinct resume_no (AC56, engine Q26).
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.report (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/__init__.py"
      - "packages/eng-harness/src/eng_harness/report/_document.py"
      - "packages/eng-harness/src/eng_harness/report/_model.py"
      - "packages/eng-harness/src/eng_harness/report/_write.py"
      - "packages/eng-harness/tests/unit/report/test_build_report.py"
      - "packages/eng-harness/tests/unit/report/test_draft_mark.py"
      - "packages/eng-harness/tests/unit/report/test_write.py"
      - "packages/eng-harness/tests/unit/report/test_timings.py"
      - "packages/eng-harness/tests/fixtures/report_run.py"
      - "packages/eng-harness/tests/golden/test_report.py"
      - "packages/eng-harness/tests/data/snapshots/report/**"
    # About 80 more lines for sections 6 and 7 (an estimate, not a measurement).
    max_changed_lines: 380
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/report/test_build_report.py::test_inputs_only_and_deterministic"
      - "packages/eng-harness/tests/unit/report/test_build_report.py::test_tampered_refused_live_banner"
      - "packages/eng-harness/tests/unit/report/test_draft_mark.py::test_draft_signed_and_sources"
      - "packages/eng-harness/tests/unit/report/test_write.py::test_utf8_lf_atomic"
      - "packages/eng-harness/tests/unit/report/test_timings.py::test_wait_and_run_times"
    covers: [AC50, AC51, AC53, AC56, AC57, AC59]
    depends_on: [T12]
  - id: T13b
    title: "Report status section: the run's decision runtime"
    # Amendment (B-471, documents only): new; spec Q16 (c) and spec 4.6.1 (owner instruction of 2026-11-12). T13 is merged, so the Status rows of the decision runtime are a task of their own.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/report/_document.py"
      - "packages/eng-harness/tests/golden/test_report.py"
      - "packages/eng-harness/tests/data/snapshots/report/**"
    # About 25 lines in _document.py and 3 of CHANGELOG.md (an estimate, not a measurement).
    max_changed_lines: 50
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/golden/test_report.py::test_report_snapshot"
    covers: [AC51]
    depends_on: [T13]
  - id: T14
    title: "Commands run and resume: wiring, generated options, answers file, outcome mapping"
    # Amendment (B-342, documents only): the original T14 (430 lines) exceeded limits.max_task_lines (400, gate GC005);
    # lead decision D-12: split. T14 keeps the run and resume wiring (AC6, AC7, AC8, AC14, AC46); T14b keeps signal
    # handling, the launch address on the terminal only (AC10, AC61) and the decision layer of amendment B-098
    # (AC62, AC63).
    # Amendment (B-412, documents only): cli/__init__.py added (CliDeps fields, run and resume handlers); CliDeps defaults rule of section 3; page report bound to build_report.
    # Amendment (B-412 review, documents only): stop-file removals of spec 4.4.8 in _run.py and their test; budget 340 -> 360.
    # Amendment (B-412 second review, documents only): tests/helpers/cli_deps.py added (the shared fully set CliDeps builder of section 3).
    # Amendment (B-412 third review, documents only): workflow and replay tests use a fake engine from CliDeps; T17c re-checks AC7, AC8, AC46 and AC64 with the real engine.
    # Amendment (B-412 fourth review, documents only): T14 binds the engine-factory default to the merged Engine and adds the workflow-registry field (T18 binds it after plan 0010 T9).
    # Amendment (B-412 fifth review, documents only): the engine factory takes the full port set; its default maps only the fields the merged EnginePorts holds (T16b completes it); the page ports' stop check bound to FileRunControl.
    # Amendment (B-412 seventh review, documents only): run-id cell behind the page ports' stop check and report (spec 4.4.8) and its test; calc-port factory field; AC9 in covers; budget 360 -> 390.
    # Amendment (B-412 eighth review, documents only): depends on T7b (cli/_control.py); port builder takes the run folder from the cell; calc-port factory arguments fixed; ExpectedTimes index; budget 390 -> 400.
    # Amendment (B-412 ninth review, documents only): resume removes a stale stop file at the start of the command (spec 4.4.8); ReleaseMarks from [project_lane.*] built in _wiring.py; paragraph budget text fixed to 400.
    # Amendment (B-510, documents only): split; the page ports' wait mode (spec 4.4.5 step 2) and the engineer-name rule of file answers (spec 4.2.1) did not fit the 400 cap, so they go with run --answers and resume --answers (AC46, AC64, test_cli_answers.py) to the new T14c; basis_ref of a workflow without required basis fields (spec Q23, interim); EnginePorts prose corrected (decision merged); depends on T9b (marks); budget 400 -> 355.
    # Amendment (B-541, documents only): first-live-run gaps, third set (spec 4.2.2 step 5, 4.2.3, 4.7, AC71; spec 0002 AC48): run and resume enter the ports around Engine.start and Engine.resume; a ConfigError from the port builder exits 2; a LocalWorkspaceError where the workspace is built exits 2; HOST_LOCKED maps to exit 4 (cli/_exit.py and its table test added); the --input file is read as utf-8-sig; the port builder's result is the cli-local Protocol RunPorts in cli/__init__.py (T14 does not wait for plan 0002 T22); budget 355 -> 380.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.cli (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"
      - "packages/eng-harness/src/eng_harness/cli/_exit.py"  # HOST_LOCKED -> 4 (B-541)
      - "packages/eng-harness/src/eng_harness/cli/_options.py"
      - "packages/eng-harness/src/eng_harness/cli/_run.py"
      - "packages/eng-harness/src/eng_harness/cli/_wiring.py"
      - "packages/eng-harness/tests/helpers/cli_deps.py"
      - "packages/eng-harness/tests/unit/cli/test_options.py"
      - "packages/eng-harness/tests/unit/cli/test_run_refusals.py"
      - "packages/eng-harness/tests/unit/cli/test_run_id_binding.py"
      - "packages/eng-harness/tests/unit/cli/test_exit_codes.py"  # the HOST_LOCKED case (B-541)
      - "packages/eng-harness/tests/workflow/test_cli_run.py"
      - "packages/eng-harness/tests/replay/test_cli_resume.py"
    # Amendment B-354: `run --answers FILE` (AC64), about 30 lines; budget 310 -> 340.
    # Amendment B-412 seventh review: the run-id cell, about 30 lines; budget 360 -> 390.
    # Amendment B-412 eighth review: the ExpectedTimes index and the port builder's run-folder callable, about 10 lines; budget 390 -> 400 (the cap).
    # Amendment B-510: run --answers (about 30 lines) and resume --answers (about 20) move to T14c; the basis_ref placeholder, about 2 lines; budget 400 -> 355.
    # Amendment B-541: the ports' context around both engine calls about 8, the port builder's ConfigError about 3, the workspace refusal about 4, the HOST_LOCKED entry 1, the RunPorts Protocol about 6 (an estimate): 355 + 22 = 377; budget 380.
    max_changed_lines: 380
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_run_refusals.py::test_refusals_create_no_run"
      - "packages/eng-harness/tests/unit/cli/test_run_id_binding.py::test_page_bindings_before_and_after_run_id"
      - "packages/eng-harness/tests/workflow/test_cli_run.py::test_run_completes_and_writes_report"
      - "packages/eng-harness/tests/replay/test_cli_resume.py::test_no_wait_then_resume"
      - "packages/eng-harness/tests/replay/test_cli_resume.py::test_stop_file_removed_on_return_and_before_resume"
      - "packages/eng-harness/tests/unit/cli/test_options.py::test_generated_options_exclude_quantities"
      - "packages/eng-harness/tests/workflow/test_cli_run.py::test_ports_entered_around_engine_call"  # AC71 (B-541)
      - "packages/eng-harness/tests/unit/cli/test_exit_codes.py::test_error_codes"  # case HOST_LOCKED -> 4 (B-541)
    covers: [AC6, AC7, AC8, AC9, AC14, AC71]  # AC71: run and resume; T16 covers its status, stop and report case
    depends_on: [T3, T3b, T5, T7, T7b, T9, T9b, T10, T13]
  - id: T14c
    title: "Commands run and resume: the page ports' wait mode and the answers files"
    # Amendment (B-510, documents only): new, split from T14; the wrapper that gives the page ports the process wait mode (spec 4.4.5 step 2), run --answers and resume --answers through pages.accept_answers_file, and their refusal while [engine] engineer is unset (spec 4.2.1).
    # Amendment (B-536, documents only): first-live-run gaps. The port builder is called at the end of step 2 with the model files of the input (spec 4.2.2 step 2, AC67; spec 0002 H-G10 closed), and its NotImplementedGap (spec 0002 AC43, gap H-G8) ends run and resume with exit 2 (AC68). cli/__init__.py (the port_builder field's type) and tests/helpers/cli_deps.py (the shared builder's fake port builder) added; budget 80 -> 130 (fix round 1 re-estimate).
    # Amendment (B-541, documents only): when T14c moves the port builder call to the end of step 2 it keeps T14's ConfigError exit beside its H-G8 exit, and it reads the --answers file as utf-8-sig (spec 4.7); the moved ConfigError clause is deleted at T14's place and added at the end of step 2 (about 6 counted lines; the encoding is an argument of a line T14c writes anyway); budget 130 -> 136 (estimate 135); files unchanged.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"  # the port_builder field takes files (B-536)
      - "packages/eng-harness/src/eng_harness/cli/_run.py"
      - "packages/eng-harness/src/eng_harness/cli/_wiring.py"
      - "packages/eng-harness/tests/helpers/cli_deps.py"  # the fake port builder takes files (B-536)
      - "packages/eng-harness/tests/workflow/test_cli_answers.py"
      - "packages/eng-harness/tests/workflow/test_cli_run.py"
    # About 30 lines for run --answers, 20 for resume --answers, 15 for the wait-mode wrapper, 5 for the engineer-name refusal and 5 of CHANGELOG.md (an estimate, not a measurement).
    # Amendment B-536: 35 to 45 lines for the model files (the walk over the input model's Path and Path | None fields, the three refusal messages, and at resume the registry lookup, the run-header read and the stored input), 3 for the field's type, 5 for the H-G8 exit and 1 of CHANGELOG.md (an estimate); 75 + 54 = 129, budget 130.
    # Amendment (B-543, documents only): the port builder also receives visible, the input's top-level visible_host bool or false (spec 4.2.2 step 2, AC67; spec 0007 4.2, spec 0002 4.1 item 6), at run and at resume from the stored input, passed by keyword as files is (build_ports takes both keyword-only); about 6 lines beside the model-files walk and 1 in the field's type: 129 + 7 = 136, budget 140; test_model_files_reach_the_port_builder also checks visible.
    # Amendment B-541: the moved ConfigError clause, about 3 lines deleted at T14's place and 3 added at the end of step 2 (an estimate): 129 + 6 = 135; budget 136.
    # Both amendments sit in this task: 129 + 6 (B-541) + 7 (B-543) = 142; budget 143.
    max_changed_lines: 143
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/workflow/test_cli_run.py::test_page_ports_wait_unless_no_wait_real_engine"
      - "packages/eng-harness/tests/workflow/test_cli_answers.py::test_form_request_answers_file"
      - "packages/eng-harness/tests/workflow/test_cli_answers.py::test_run_answers_first_data_request"
      - "packages/eng-harness/tests/workflow/test_cli_run.py::test_model_files_reach_the_port_builder"  # AC67 (B-536)
      - "packages/eng-harness/tests/workflow/test_cli_run.py::test_port_builder_gap_exits_2"  # AC68 (B-536)
    covers: [AC46, AC64, AC67, AC68]
    depends_on: [T10, T14]
  - id: T14b
    title: "Commands run and resume: signals, launch address on the terminal only, decision layer wiring"
    # Amendment (B-412, documents only): cli/__init__.py added (providers_loader and decision_assembler fields); CliDeps defaults rule of section 3.
    # Amendment (B-412 second review, documents only): tests/helpers/cli_deps.py added (T14b extends the shared builder with its new fields); T18 binds the defaults.
    # Amendment (B-412 third review, documents only): workflow tests use a fake engine from CliDeps; T17c re-checks AC61 and AC63 with the real engine.
    # Amendment (B-412 fifth review, documents only): the cascade goes into the factory's port set; the merged EnginePorts has no decision field yet, so T16b carries it to the real engine.
    # Amendment (B-412 sixth review, documents only): the cascade builder is the CliDeps field decision_port_factory (default None, plan 0005 T7 and T10 not merged); test_decision_wiring.py injects a recorder; T18 binds it.
    # Amendment (B-412 eighth review, documents only): the first interrupt reads the run-id cell; empty cell or missing run folder ends the process (exit 130); budget 120 -> 135.
    # Amendment (B-412 ninth review, documents only): decision_assembler call arguments fixed; the point policies of step 5 are supplied inside its default (T18).
    # Amendment (B-412 tenth review, documents only): point policies are a fourth decision_assembler argument from the CliDeps field point_policies (default None; T18 binds it), as spec 4.2.2 step 5 and Q16(a).
    # Amendment (B-510, documents only): cli/_config.py added (the [decisions] section, refused by the merged configuration, becomes a typed HarnessConfig field) and its test; the providers_loader default is the merged load_providers_config (its own tests-first case); the default engine factory maps the cascade into the merged EnginePorts.decision; depends on T14c; budget 135 -> 145.
    # Amendment (B-541, documents only): first-live-run gaps, third set (spec 4.2.1, 4.7, AC70): main resolves the workspace once (--workspace as ENG_WORKSPACE, the default workspace included) for the configuration lookup and hands that environment and the found configuration path to the handler; load_config reads utf-8-sig; tests/unit/cli/test_config.py added; budget 145 -> 160.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.cli (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"
      - "packages/eng-harness/src/eng_harness/cli/_config.py"
      - "packages/eng-harness/src/eng_harness/cli/_run.py"
      - "packages/eng-harness/src/eng_harness/cli/_signals.py"
      - "packages/eng-harness/src/eng_harness/cli/_wiring.py"
      - "packages/eng-harness/tests/helpers/cli_deps.py"
      - "packages/eng-harness/tests/unit/cli/test_signals.py"
      - "packages/eng-harness/tests/unit/cli/test_config.py"  # the workspace lookup and the byte-order mark (B-541)
      - "packages/eng-harness/tests/unit/cli/test_decision_wiring.py"
      - "packages/eng-harness/tests/workflow/test_cli_run.py"
      - "packages/eng-harness/tests/workflow/test_launch_address.py"
    # Amendment B-510: the [decisions] field (2 lines, measured by the audit), the providers_loader default and the decision mapping (about 6); budget 135 -> 145.
    # Amendment B-541: the workspace resolution in main, the environment and the configuration path handed on, about 10, and the byte-order mark 1 (an estimate): 145 + 11 = 156; budget 160.
    max_changed_lines: 160
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_signals.py::test_first_interrupt_requests_stop"
      - "packages/eng-harness/tests/workflow/test_launch_address.py::test_address_never_on_stdout_or_stderr"
      - "packages/eng-harness/tests/unit/cli/test_decision_wiring.py::test_providers_read_and_runtime_assembled"
      - "packages/eng-harness/tests/unit/cli/test_decision_wiring.py::test_decisions_section_reaches_assembler"
      - "packages/eng-harness/tests/unit/cli/test_decision_wiring.py::test_providers_loader_default_is_load_providers_config"
      - "packages/eng-harness/tests/workflow/test_cli_run.py::test_run_header_records_decision_runtime"
      - "packages/eng-harness/tests/unit/cli/test_config.py::test_default_workspace_and_option_reach_lookup"  # AC70 (B-541)
    covers: [AC10, AC61, AC62, AC63, AC70]
    depends_on: [T14c]
  - id: T15
    title: "Basis confirmation screen, setup log and its place in run"
    # Amendment (B-412, documents only): cli/__init__.py, _run.py, _wiring.py, pages/__init__.py and _ports.py added; budget 250 -> 330 (screen, port, setup log and run step 3 share it).
    # Amendment (B-412 second review, documents only): tests/helpers/cli_deps.py added (T15 extends the shared builder with any new basis field).
    # Amendment (B-412 third review, documents only): workflow tests use a fake engine from CliDeps; T17c re-checks AC47 with the real engine.
    # Amendment (B-412 fourth review, documents only): freeze and BasisSetupPort are merged, so T15 binds those CliDeps defaults itself.
    # Amendment (B-510, documents only): the CliDeps field basis_fields_of (default None; WorkflowDef.basis_fields is plan 0007 T6's) gives step 3 its FieldSpec list; the --template inputs follow the interim reading of spec Q22; budget 330 -> 340.
    # Amendment (B-541, documents only): the --basis file is read with spec 0004 load_strict and validated as EngineerValues {name, values} (spec 4.2.2 step 3, section 5); about 3 lines inside the step 3 estimate; files and budget unchanged.
    # Amendment (B-545, documents only): depends on T10c, which also edits pages/_ports.py; files and budget unchanged.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.pages (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"
      - "packages/eng-harness/src/eng_harness/cli/_run.py"
      - "packages/eng-harness/src/eng_harness/cli/_wiring.py"
      - "packages/eng-harness/src/eng_harness/pages/__init__.py"
      - "packages/eng-harness/src/eng_harness/pages/_ports.py"
      - "packages/eng-harness/src/eng_harness/pages/_screens_basis.py"
      - "packages/eng-harness/tests/helpers/cli_deps.py"
      - "packages/eng-harness/tests/workflow/test_cli_basis.py"
    max_changed_lines: 340
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/test_cli_basis.py::test_basis_confirmation_flow"
      - "packages/eng-harness/tests/workflow/test_cli_basis.py::test_reject_leaves_no_run"
      - "packages/eng-harness/tests/workflow/test_cli_basis.py::test_stale_draft_hash_refused"
      - "packages/eng-harness/tests/workflow/test_cli_basis.py::test_no_wait_basis_exits_10_nothing_stored"
    covers: [AC47]
    depends_on: [T14b, T10c]  # T10c: both edit pages/_ports.py (amendment B-545)
  - id: T16
    title: "Commands status, stop, report and doctor"
    # Amendment (B-412, documents only): cli/__init__.py added (handlers, doctor field); report and doctor handlers in cli/_status.py; stop test drives a fake engine (real one re-checked in T17).
    # Amendment (B-412 second review, documents only): tests/helpers/cli_deps.py added (T16 extends the shared builder with the doctor field); T18 binds the doctor default.
    # Amendment (B-412 fourth review, documents only): stop writes the file only while the run lock is held; --wait waits for the lock release (spec 4.4.8).
    # Amendment (B-510, documents only): eng_harness.doctor.run is merged, so T16 binds the doctor default itself (section 3 rule; two lines inside the budget; its own tests-first case).
    # Amendment (B-536, documents only): the report command also writes report/cycle-timings.json (spec AC69, spec 0007 4.9); report/__init__.py added (exports edit_cycle_timings and write_cycle_timings of plan 0007 T10b, which T16 waits for, section 3); budget 330 -> 345.
    # Amendment (B-541, documents only): first-live-run gaps, third set (spec AC13, AC71): the doctor handler passes the configuration path main found (None when none) and the command's environment as env, and ends a ConfigError with exit 2; status, stop and report end a LocalWorkspaceError with exit 2; waits for plan 0002 T22 (doctor.run's new arguments); budget 345 -> 355.
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entry for eng_harness.cli (amendment B-356)
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"
      - "packages/eng-harness/src/eng_harness/cli/_status.py"
      - "packages/eng-harness/src/eng_harness/cli/_stop.py"
      - "packages/eng-harness/src/eng_harness/report/__init__.py"  # exports the cycle-timings functions (B-536)
      - "packages/eng-harness/tests/helpers/cli_deps.py"
      - "packages/eng-harness/tests/unit/cli/test_status.py"
      - "packages/eng-harness/tests/unit/cli/test_report_command.py"
      - "packages/eng-harness/tests/unit/cli/test_doctor_command.py"
      - "packages/eng-harness/tests/workflow/test_cli_stop.py"
    # Amendment B-536: about 4 lines of exports in report/__init__.py and 8 in cli/_status.py (an estimate); budget 330 + 15.
    # Amendment B-541: the doctor call's arguments about 3, its ConfigError about 2, the workspace refusal of status, stop and report about 3 (an estimate): 345 + 8 = 353; budget 355.
    max_changed_lines: 355
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_status.py::test_states_and_read_only"
      - "packages/eng-harness/tests/workflow/test_cli_stop.py::test_stop_pauses_at_safe_point"
      - "packages/eng-harness/tests/unit/cli/test_report_command.py::test_output_rules"
      - "packages/eng-harness/tests/unit/cli/test_doctor_command.py::test_exit_code_passthrough"
      - "packages/eng-harness/tests/unit/cli/test_doctor_command.py::test_doctor_default_is_doctor_run"
      - "packages/eng-harness/tests/unit/cli/test_report_command.py::test_cycle_timings_file"  # AC69 (B-536)
      - "packages/eng-harness/tests/unit/cli/test_doctor_command.py::test_doctor_receives_config_path_and_environment"  # AC13 (B-541)
    covers: [AC9, AC11, AC12, AC13, AC69, AC71]  # AC71: the workspace case of status, stop and report (B-541)
    depends_on: [T14b]  # external: plan 0007 T10b (edit_cycle_timings, write_cycle_timings; B-536); plan 0002 T22 (doctor.run arguments; B-541)
  - id: T16b
    title: "Production wiring: the decision, progress and run-control ports reach the real engine"
    # Amendment (B-412 fifth review, documents only): new; waits for engine plan T14, T14b and T18 (EnginePorts gains the decision, progress and run-control fields); the one non-test task that completes cli/_wiring.py for them.
    # Amendment (B-412 seventh review, documents only): the fan-out isolates each sink; run_started fills the run-id cell of T14; second test node; budget 100 -> 130.
    # Amendment (B-412 eighth review, documents only): starts the heartbeat task (spec 4.3) with its run folder from the run-id cell; third test node; AC18 in covers; budget 130 -> 150.
    # Amendment (B-412 ninth review, documents only): AC19 in covers (the fan-out path of spec AC19, test_failing_sink_detached_alone); spec AC9, AC18, AC37 and section 9 name its nodes.
    # Amendment (B-510, documents only): engine plan T14 and T14b are merged and T14b maps the cascade into EnginePorts.decision, so T16b adds only the progress and run-control fields and waits only for engine plan T18; files and budget unchanged.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/_wiring.py"
      - "packages/eng-harness/src/eng_harness/cli/_run.py"
      - "packages/eng-harness/tests/unit/cli/test_production_wiring.py"
    # About 30 lines for the port mapping, 50 for the isolating fan-out and the run-id fill, 15 in _run.py and 20 for the heartbeat task (an estimate, not a measurement).
    max_changed_lines: 150
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_production_wiring.py::test_engine_ports_carry_stop_progress_and_cascade"
      - "packages/eng-harness/tests/unit/cli/test_production_wiring.py::test_failing_sink_detached_alone"
      - "packages/eng-harness/tests/unit/cli/test_production_wiring.py::test_heartbeat_follows_run_id_cell"
    covers: [AC9, AC18, AC19, AC37, AC62]
    depends_on: [T14b, T16]
  - id: T17
    title: "End-to-end approval, replay and untrusted-text tests; Arabic environment; real-engine re-checks"
    # Amendment (B-412, documents only): waits for engine plan T15 and T18 (real engine, no fakes); re-checks AC9, AC19, AC29 and AC37 with the real engine.
    # Amendment (B-412 second review, documents only): split; T17 holds only test files (a `test(...)` pull request, test-first step 3) and names its re-check nodes; the documentation part is T17b.
    # Amendment (B-412 fifth review, documents only): depends on T16b; the run-control wait is engine plan T18 (amended in this pull request), not T10 to T15.
    # Amendment (B-412 eighth review, documents only): the AC19 re-check installs TerminalProgress as the engine's only sink; the AC34 voided display is built in T7b.
    files:
      - "packages/eng-harness/tests/property/test_untrusted_text.py"
      - "packages/eng-harness/tests/replay/test_page_resume.py"
      - "packages/eng-harness/tests/windows/test_arabic_environment.py"
      - "packages/eng-harness/tests/workflow/test_cli_stop.py"
      - "packages/eng-harness/tests/workflow/test_page_approval.py"
      - "packages/eng-harness/tests/workflow/test_progress_detach.py"
    # Only test files, which are not counted (section 1): the counted budget is nominal; about 450 test lines are expected.
    max_changed_lines: 20
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/test_page_approval.py::test_per_item_reject_end_to_end"
      - "packages/eng-harness/tests/workflow/test_page_approval.py::test_void_after_model_change"
      - "packages/eng-harness/tests/replay/test_page_resume.py::test_kill_while_waiting_then_resume"
      - "packages/eng-harness/tests/property/test_untrusted_text.py::test_every_screen_and_report_escape"
      - "packages/eng-harness/tests/windows/test_arabic_environment.py::test_arabic_workspace_and_cp1256"
      - "packages/eng-harness/tests/workflow/test_progress_detach.py::test_raising_renderer_detached_run_continues"
      - "packages/eng-harness/tests/workflow/test_cli_stop.py::test_stop_real_engine_pauses_at_safe_point"
      - "packages/eng-harness/tests/workflow/test_page_approval.py::test_answer_bound_to_hash_real_engine"
      - "packages/eng-harness/tests/workflow/test_page_approval.py::test_page_confirms_after_commit_real_engine"
    covers: [AC9, AC19, AC29, AC33, AC34, AC35, AC37, AC48, AC58]
    depends_on: [T15, T16, T16b]
  - id: T17b
    title: "Local testing list and the agent rule in the package AGENTS.md"
    # Amendment (B-412 second review, documents only): new; the documentation half of T17 (a `docs(...)` pull request, exempt from test-first).
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/.gate/agents.yml"
      - "packages/eng-harness/AGENTS.md"
    # About 60 lines of local-testing.md, 15 of agents.yml and 10 of CHANGELOG.md; AGENTS.md is generated and not counted.
    max_changed_lines: 120
    max_sessions: 1
    depends_on: [T17]
  - id: T17c
    title: "Real-engine re-checks of the screens and the run and resume commands"
    # Amendment (B-412 third review, documents only): new; re-checks with the real engine the staged halves of AC7, AC8, AC42, AC46, AC47, AC61, AC63 and AC64 (test files only, as T17).
    # Amendment (B-412 fifth review, documents only): depends on T16b, so its re-checks go through the production wiring.
    files:
      - "packages/eng-harness/tests/replay/test_cli_resume.py"
      - "packages/eng-harness/tests/workflow/test_cli_answers.py"
      - "packages/eng-harness/tests/workflow/test_cli_basis.py"
      - "packages/eng-harness/tests/workflow/test_cli_run.py"
      - "packages/eng-harness/tests/workflow/test_launch_address.py"
      - "packages/eng-harness/tests/workflow/test_signoff.py"
    # Only test files, which are not counted (section 1): the counted budget is nominal; about 300 test lines are expected.
    max_changed_lines: 20
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/test_cli_run.py::test_run_completes_and_writes_report_real_engine"
      - "packages/eng-harness/tests/replay/test_cli_resume.py::test_no_wait_then_resume_real_engine"
      - "packages/eng-harness/tests/workflow/test_signoff.py::test_signoff_rules_real_engine"
      - "packages/eng-harness/tests/workflow/test_cli_answers.py::test_form_request_answers_file_real_engine"
      - "packages/eng-harness/tests/workflow/test_cli_basis.py::test_basis_confirmation_flow_real_engine"
      - "packages/eng-harness/tests/workflow/test_launch_address.py::test_address_never_on_stdout_or_stderr_real_engine"
      - "packages/eng-harness/tests/workflow/test_cli_run.py::test_run_header_records_decision_runtime_real_engine"
      - "packages/eng-harness/tests/workflow/test_cli_answers.py::test_run_answers_first_data_request_real_engine"
    covers: [AC7, AC8, AC42, AC46, AC47, AC61, AC63, AC64]
    depends_on: [T15, T16, T16b, T9c]  # T9c: both edit test_signoff.py (amendment B-544)
  - id: T18a
    title: "Bind the CliDeps defaults to the merged real implementations, except the port builder"
    # Amendment (B-412 second review, documents only): new; the one task that replaces the None defaults of the section 3 rule.
    # Amendment (B-412 fourth review, documents only): the registry is plan 0010 T9's workflows/__init__.py (T18 waits for it); engine factory and freeze are bound by T14 and T15.
    # Amendment (B-412 fifth review, documents only): depends on T16b, so run and resume become available in production only with the full port wiring.
    # Amendment (B-412 sixth review, documents only): also binds decision_port_factory to the cascade of plan 0005 (waits for plan 0005 T7 and T10).
    # Amendment (B-412 eighth review, documents only): calc-port factory default spelled out; the port builder default waits for spec Q20; cli/_wiring.py added (under answer A, it draws the run id for run).
    # Amendment (B-412 tenth review, documents only): also binds the point_policies default (the point-policy mapping of step 5).
    # Amendment (B-471, documents only): T18 split into T18a and T18b (owner instruction of 2026-11-12, spec Q20 answer A). T18a binds every default but the port builder; the workflow registry is plan 0007 T9b's workflows/__init__.py (spec 0007 Q13), so T18a does not wait for plan 0010 T9; cli/_wiring.py moves to T18b.
    # Amendment (B-475, documents only): the decision assembler default is plan 0009 T10a's phase-1 assemble_decision_runtime (spec 0009 AC49), and the point_policies default is the empty mapping (spec Q16 (d)), not None.
    # Amendment (B-503, documents only): the tests-first test also checks the basis_fields map of the default calc port (spec 4.2.2 step 4); the port builder passes no basis (spec 0002 H-G9 closed); files and budget unchanged.
    # Amendment (B-510, documents only): load_providers_config and doctor.run are merged and bound by T14b and T16, not here (AC13 leaves covers: T16 covers it); T18a also binds basis_fields_of (T15) to the workflow's basis_fields (plan 0007 T6); budget unchanged.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"
      - "packages/eng-harness/tests/unit/cli/test_default_deps.py"
    # About 50 lines in cli/__init__.py for six defaults and 5 of CHANGELOG.md (an estimate, not a measurement).
    max_changed_lines: 70
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_default_deps.py::test_defaults_are_the_real_implementations"
    covers: [AC62]
    depends_on: [T14b, T15, T16, T16b]
  - id: T18b
    title: "Bind the port builder default and draw the run id at step 1 for run"
    # Amendment (B-471, documents only): new, split from T18 (spec Q20 answer A, owner instruction of 2026-11-12); waits for engine plan T20 (work item B-472) and plan 0002 T19a (B-475).
    # Amendment (B-536, documents only): the default passes the files argument of T14c on to build_ports (spec 4.2.2 step 2); files and budget unchanged.
    # Amendment (B-543, documents only): the default also passes the visible argument of T14c on to build_ports (spec 4.2.2 step 2, spec 0002 4.1 item 6); files and budget unchanged.
    # Amendment (B-541, documents only): run prints the line "run id: <run_id>" on standard error once the id is drawn at step 1, and the default converts the server sections with spec 0002 servers_config (AC66); budget 40 -> 45.
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"
      - "packages/eng-harness/src/eng_harness/cli/_wiring.py"
      - "packages/eng-harness/tests/unit/cli/test_default_deps.py"
    # About 10 lines in cli/__init__.py, 20 in cli/_wiring.py and 3 of CHANGELOG.md (an estimate, not a measurement).
    # Amendment B-541: the run id line about 3 and the servers_config call 1 (an estimate): 33 + 4 = 37; budget 45.
    max_changed_lines: 45
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_default_deps.py::test_port_builder_bound_and_run_id_drawn"
    covers: [AC66]
    depends_on: [T18a]
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
  the durable wait, and T7b the stop-file protocol and the voided display; T9, T9b and T10 add the screens; T10c
  fixes the voided display's request kinds and the input screen's text (amendment B-545); T9c makes the sign-off
  screen read the edit cycle's design verdicts, before T17c, which also edits `test_signoff.py` (amendment B-544). T8 (release marks) precedes T9b because the sign-off screen lists the
  marked results.
- T11 to T13 build the report from the journal and the store only. T11 folds the data; T12 renders sections and the
  source links (sections 2 to 5); T13 adds the status section, the timings and run events sections, the marks, the
  integrity line, the policy and the atomic write; T13b adds the run's decision runtime to the status section (B-471).
- T14 to T16 wire the commands: run and resume first (T14, then T14c for the page ports' wait mode, the answers
  files and the model files of the port builder (amendment B-536), then T14b for signals, the launch address and the decision layer; they exercise everything), then the basis
  confirmation inside `run`, then status, stop, report and doctor;
  T16b completes the production wiring of the progress and run-control ports once the engine holds them. T17 closes with the cross-cutting end-to-end tests, the Windows Arabic
  environment test and the real-engine re-checks (test files only); T17b adds the local testing list and the agent
  rule; T17c re-checks the run commands and screens with the real engine (test files only); T18a and T18b (split by
  B-471) bind the `CliDeps` defaults whose real implementations were not merged when T14 to T16 were built.

No new runtime dependency: `http.server`, `argparse`, `subprocess`, `statistics`, `secrets`, `hmac` and `html` from the
standard library (spec §2, Q1). Reuse: `JournalReader`, the ports and `Event` from engine T4 and T6; `ResultStore`
and `Quantity` from the contract; `BasisSetupPort` from plan 0004 T7; `eng_harness.doctor.run` from plan 0002 T18.

## 2. Tasks

**T1 Text** (spec §4.7). `format_duration_ms`, `format_timestamp`, `format_number`, `sanitize_terminal`,
`sanitize_html`, `truncate`; the rules test that no module of this spec imports `locale` or uses locale-dependent
time directives.

**T2 HTML builder** (spec §4.5). `Text`, `Trusted`, `SafeToken`, `field(label, value)` with `<bdi dir="auto">`,
element builder, style element and its SHA-256 for the policy. Property tests on escaping.

**T2b In-page fragment links** (spec §4.5, AC52; amendment B-435). `fragment(token: SafeToken) -> Href` renders
`#<token>`; `_attr` accepts a fragment `Href` for `href` only, so that T12's value cells can link to their sources row.

**T3 Shell** (spec §4.1, §4.2.1, §4.2.3, §4.2.4, §4.4.4). `main(argv, deps)`, six subcommands registered as stubs that
call into later modules, `ExitCode`, `HarnessConfig` with strict sections, stream encoding setup, the launch-address
`CliDeps` with an opener slot; `[project.scripts]`,
`__main__`, `public_modules`. The rules tests for AC2 and AC60 start here and tighten as modules appear. Amendment
B-354: the entry point test of AC65 (the declared script, `python -m eng_harness`, no root script); the supported root
form `uv run --package eng-harness eng-harness` needs no change to the root `pyproject.toml` (spec §4.1).

**T3b Launch-address opener** (spec §4.2.1, AC61; amendment B-359, split from T3 at 418 lines). The platform opener with
`BROWSER` removed from the child environment and the writer to the controlling terminal only, as the default opener of
`CliDeps`.

**T4 Progress display** (spec §4.3). `ExpectedTimes.build` (read-only journals, median, range, sample floor) and
`ProgressRenderer` for the three modes, with text snapshots.

**T5 Sink and heartbeat** (spec §4.3). The bounded queue and writer thread, `TerminalProgress.emit`, the heartbeat
task and `heartbeat.json`, `read_liveness`, and the 200 ms latency test. Amendment B-412: T5 exports `TerminalProgress`,
`Heartbeat`, `Liveness` and `read_liveness` from `progress/__init__.py` (spec §4.1). AC19 is tested on the sink alone:
`emit` returns within 10 ms on a blocking stream, the oldest lines are dropped and counted when the queue is full, and a
renderer that raises makes `emit` raise so that the engine can detach the sink; the detach itself is engine AC58
(engine plan T18) and is re-checked with the real engine in T17. Amendment B-412 eighth review: `Heartbeat` takes
its file path as a callable (`Callable[[], Path | None]`) read at each beat; `None` means the run folder is not known
or does not exist yet, and the beat then prints its line and writes no file, never creating the folder (spec §4.3);
T16b binds the callable to the run-id cell of spec §4.4.8 and starts the task.

**T6 Server and security** (spec §4.4.1 to §4.4.3). `PageServer`, launch code, session cookie `eh_<port>_session`, CSRF
token with the per-route inputs of spec §4.4.2 (approval, choice, setup; the test is parametrized over the three), Host,
Origin and Fetch Metadata checks, headers, route table with limits, lockdown, shutdown. `tests/helpers/page_client.py`
is the loopback client used by all page tests. Security lens review.

**T7 Answers and ports** (spec §4.4.5). `ApprovalSubmission` and the answer models in `pages/_answers.py` (no value members), the checks,
`PageApprovalPort` and `PageInputPort` (present, awaitable answer, `wait=False`, stop, timeout), the per-request lock,
acknowledgement after the sink sees `approval_resolved` (`FileRunControl` moved to T7b, see (2)). Security lens review.
Amendment B-412: (1) T7 exports `PageApprovalPort` and `PageInputPort` from `pages/__init__.py`. (2) The stop-file
protocol of spec §4.4.8 is T7b's (amendment B-412 eighth review: it moved out of T7, whose estimate with it passed the
400-line cap); T7's wait only polls the injected `stop_requested` callable. (3)
`pages/_ports.py` implements `PageApp.screen(kind, id)`, whose `kind` is the route kind (`request` or `setup`,
`pages/_routes.py`): `screen('request', id)` looks up the open request by id and dispatches on its approval or request
kind (`CHANGE_SET`, `PROMOTION`, a choice kind, ...) through a mapping from that kind to a screen builder, and a kind
with no registered builder renders a refusal page (no form, no button); `screen('setup', id)` goes to the basis
builder. T9 and T10 register their builders in the mapping, and T15 registers the basis builder for `setup`. (4) The page ports take a `report: Callable[[], str]` behind `PageApp.report()`
(`GET /report`), by default a fixed "report not available yet" document; T14 binds it. The page ports also take the
stop check by injection (`stop_requested: Callable[[], bool]`, polled by the wait of `pages/_wait.py`), because
`eng_harness.pages` may not import `eng_harness.cli` (spec §4.1); `test_stop_ends_wait` injects it, and T14 binds it in
`cli/_wiring.py` to `FileRunControl` for the run (amendment B-412 fifth review). Both callables take no argument;
for `run` the run id does not exist when the page ports are built, so T14 binds them through the run-id cell of spec
§4.4.8 (amendment B-412 seventh review), and T7's ports need nothing beyond the two injected callables. (5) The workflow tests
(`test_answer_bound_to_hash`, `test_page_confirms_after_commit`) drive `PageApprovalPort` with a test-local stand-in for
the engine that journals `approval_requested` and `approval_resolved` through the merged `JournalWriter` and feeds the
events to the page sink; the real-engine half of AC29 and AC37 is re-checked in T17. The stand-in lives in the shared
test helper `tests/helpers/engine_standin.py` (amendment B-412 fourth review), so that T9 imports it instead of
duplicating it. Budget 390 to 340 by the eighth-review re-estimate (about 120 lines for the answer models and checks,
140 for the ports, the dispatch with its refusal fallback and the two injected callables, 40 for the wait, 30 for the
acknowledgement, 10 for the exports), after the stop-file protocol moved to T7b.

**T7b Stop-file run control and the voided display** (amendment B-412 eighth review; spec §4.4.5, §4.4.8, AC34). (1)
`cli/_control.py` holds the protocol of spec §4.4.8: `FileRunControl` (the engine's `RunControlPort`;
`stop_requested(run_id)` is true while `runs/<run_id>/stop.json` exists) and the write (`requested_at`, `by`, a
temporary file renamed over `stop.json`), read and remove helpers that T14, T14b and T16 call;
`test_control.py::test_stop_file_written_by_rename_and_removed`. (2) The voided display of spec §4.4.5: the page sink
of T7, in `pages/_ports.py`, maps a `step_failed` whose error code is `APPROVAL_VOID` to the most recent approved
`CHANGE_SET` or `PROMOTION` request resolved in this process and renders it voided with the error's message through
`field`, with no form and no button (with no such request, the message goes on the index page);
`test_void.py::test_void_shown_on_resolved_request` drives it with the T7 engine stand-in (it journals a
`step_failed` with `APPROVAL_VOID` through the merged `JournalWriter`). This is the page half of AC34; T17's
`test_void_after_model_change` re-checks it with the real engine, so T17 adds tests only.

**T8 Release marks** (spec §4.6.3). `ReleaseMarks`, `unreleased_dependencies` with the breadth-first closure over
`parents` and provenance inputs, the depth limit, and the package skeleton of `report/`. The property test compares
with an independent reachability oracle on random graphs.

**T9 Approval screens** (spec §4.4.6). Change set, promotion and info; `_labels.py` catalog; snapshots. Amendment
B-412: T9 registers the `CHANGE_SET`, `PROMOTION` and `INFO` builders in the dispatch mapping of `pages/_ports.py`
(T7). Amendment B-510: the sign-off screen, the `marks` parameter and `test_signoff_rules` (amendments B-412 third,
fourth and ninth review) are T9b's. The builder admits only a `SafeToken` in `name` and never a data string in an
attribute (AC49), and the form field prefixes of `pages/_answers.py` hold `:`, so T9 makes them token-safe: `REJECT`,
`REASON`, `CHOICE` = `"reject_"`, `"reason_"`, `"choice_"`, and the item check of `_approval` strips the one prefix a
key starts with instead of taking the text after `:`. A field name is a prefix and an item id (or a property name,
T10) and must be a token, so an id that is not a token or is longer than 57 characters makes the screen a refusal
screen (no form, no button) with the error text in an untrusted `field()`, never a partial form. The two tests that
pin a `"choice:"` literal (`tests/unit/pages/test_answer_validation.py::test_choices`,
`tests/unit/pages/test_index.py::test_multiple_open_requests`) use `CHOICE + "q"`; they pass at the base, so they
change in the implementation commit, not in the `test:` commit (TF004). The engineer-name default (`[engine]
engineer`, `PageHub.engineer`) is shown through `field()`, and the `by` input has no `value=`.

**T9b Sign-off screen** (amendment B-510, split from T9; spec §4.4.6, AC42). The `SIGN_OFF` builder in
`pages/_screens_approval.py`, registered in the dispatch mapping of `pages/_ports.py`: link to `/report` (DRAFT),
verdict counts, the exceptions, the unreleased-tool list with the acknowledgement box when it is not empty, the
engineer name, Sign and Reject; its labels in `pages/_labels.py`. The page ports gain a `marks: ReleaseMarks`
parameter for the list, which T14 binds (amendment B-412 ninth review), and a check, by request kind, that the page
runs on a posted form before the answer is taken (`PageHub.submit` has none), which refuses a signature while an
exception has no reason or the list is not acknowledged. Which item an exception's reason belongs to is spec Q24;
until it is answered T9b follows its interim reading, which is the recommendation: an exception is a verdict whose
status is not `PASS` or `NOT_APPLICABLE`, numbered n from 1 in report verdict order, and its row has its own reason
field, the `item_reasons` entry (`REASON` + item id) of the request item `exc_<n>`; an exception without its `exc_<n>`
item has no reason, so signing is refused (AC42). `test_signoff_rules` builds its own request with output items and
`exc_<n>` items (`approval_request(kind="SIGN_OFF", items=...)`), so it needs no preview builder, opens it through the
T7 engine stand-in imported from `tests/helpers/engine_standin.py` and injects a stub `report` callable (amendments B-412 third
and fourth review); T17c re-checks AC42 with the real engine.

**T9c Sign-off verdicts of the edit cycle** (amendment B-544; spec §4.4.6, AC42, Q24). `_facts` in
`pages/_screens_approval.py` takes the step results of kind `verdicts.set/1` or `harness.host_design_verdicts/1`, in
journal step order, and validates each as the model of its kind (`VerdictSet`, or `HostDesignVerdicts` of
`eng_harness.kinds.edit_cycle`, merged with plan 0007 T4b), because `VerdictSet` refuses the calc port's `calc` and
`trace`; counting and the `exc_<n>` numbering are unchanged. `test_signoff_reads_host_design_verdicts` stores a
`harness.host_design_verdicts/1` result with a `NEEDS_ENGINEER` and a `FAIL` verdict as a step result, and checks the
counts, the two exception rows with their reason fields and the refusal of a signature without both reasons; it fails
at the merge base, where the counts are zero and nothing is refused. Plan 0007 T9c adds the items to the edit cycle's
request in this order.

**T10 Choice screens** (spec §4.4.6). Choice sets from the request's JSON Schema (engineer turn, batched decisions,
engine requests) and the read-only input screen; `pages.accept_answers_file`, the only way a file becomes an
`InputAnswer`: it accepts a `block` request with `x-eng-input: data` and refuses `engine.*`, choice and unmarked
requests. Amendment B-412: T10 follows T9 and adds its labels (the engineer-turn options including the `hand_edit`
wording, and the engine-request option labels) to `pages/_labels.py`; it exports `accept_answers_file` from
`pages/__init__.py` and registers the choice and input screens in the dispatch mapping of `pages/_ports.py`.
Amendment B-510: an option group is named `CHOICE` + property name (token-safe since T9); a property name that is not
a token makes the screen a refusal screen, as in T9.

**T10c Page fixes from the first-live-run walk-through** (amendment B-545; spec §4.4.5, AC34, AC46). (1) The hub's
`_VOIDABLE` in `pages/_ports.py` holds `CHANGE_SET` and `PROMOTION` only, while `engine/_approvals.py` journals
`ApprovalKind.value` (`change_set`, `promotion`), so with the real engine an approved request is never marked voided;
T10c adds the lower-case values and keeps the upper-case names for the stand-in (spec §4.4.5 decision).
`test_void_marks_the_engine_kinds` presents `approval_request(kind="change_set")` and one of kind `promotion`, resolves
each approved and feeds an `APPROVAL_VOID` `step_failed`, and checks that the screen shows "voided"; it fails at the
merge base, where the message goes to the index. (2) `INPUT_NOTE` in `pages/_labels.py` becomes the text of spec
§4.4.5 step 2 (stop the run, then `resume RUN_ID --answers FILE`; `status` lists the run ids);
`test_data_request_names_stop_and_resume` checks the rendered input screen holds `stop RUN_ID` and
`resume RUN_ID --answers FILE`, and fails at the merge base. The existing assertion of `resume --answers FILE` in
`test_choice_screen.py` changes with the text, in the implementation commit. No other screen changes; T15 waits for
T10c because both edit `pages/_ports.py`.

**T11 Report model** (spec §4.6.1 sections 5 to 7). Folding `JournalReader` views and store records into a
`ReportModel`; waiting and machine time. A shared fixture run (`tests/fixtures/report_run.py`) is reused by T12 and T13.

**T12 Report sections** (spec §4.6.1). Renderer registry, generic bounded renderer, `value_cell(value, source)` with
the mandatory source, the sources table, changes and results; snapshot. Amendment B-412: `_sections.py` renders
sections 2 to 5 of spec §4.6.1 (changes, results summary, sources, decisions), and `test_report_snapshot` snapshots
that rendered fragment; T13 extends the snapshot to the whole document. Sections 6 (timings) and 7 (run events) are
rendered by T13 (amendment B-412 fifth review): T12's 390 lines leave no room for them under the 400 cap, and T11's
`ReportModel` already holds their data. Amendment B-435 (T12 depends on T2b): each value cell links with `fragment()`
to its sources-table row `id="src-N"` (AC52). The `_sections.py` functions take `(ReportModel, JournalReader,
ResultStore)`: the changes section (AC55) reads the `model_saved` revisions and the approval items from the
`JournalReader`, because T11's `ReportModel` does not hold them.

**T13 Report document** (spec §4.6.2). Status banner and marks, integrity line, policy meta, `build_report`,
`write_report`. Amendment B-412: T13 exports `build_report` and `write_report` from `report/__init__.py` and extends
`tests/golden/test_report.py::test_report_snapshot` and its snapshot to the whole document from `build_report`, which
completes AC51. Amendment B-412 fifth review: T13 also renders sections 6 (timings: per step start and duration,
engineer waiting time against machine time, resumes) and 7 (run events: resumes, host starts, instances left open) of
spec §4.6.1 in `_document.py` from T11's `ReportModel`, through T12's escaped cells; budget 300 to 380 (about 40 lines
per section, an estimate, not a measurement). Amendment B-435: T13 also fixes `report/_model.py`, which makes one
resume entry per `run_resumed`; it counts and lists distinct `resume_no` values (a restore appends a second
`run_resumed` with the same `resume_no`, engine Q26). T13 extends
`tests/unit/report/test_timings.py::test_wait_and_run_times`, the test spec AC56 names, with a restore that appends a
second `run_resumed` with the same `resume_no` (fixture `tests/fixtures/report_run.py`), and covers AC56.

**T13b Decision runtime in the status section** (spec §4.6.1, Q16 (c); amendment B-471, owner instruction of
2026-11-12; T13 is merged). `_document.py` adds to the Status section the run's decision runtime
(`RunView.decision_runtime`, engine AC69: the providers, the released points and the dropped releases of spec 0009
AC29), as plain label and value rows built in `_document.py` like the other Status rows (not value cells of
`report/_sections.py`: the header is not a stored result and has no sources row, AC52), held to the generic renderer's
caps of spec §4.6.1 (200 rows, depth 4, "N more"), and nothing when it is empty. The fixture header
of `tests/golden/test_report.py` gains a decision runtime and the snapshot its rows, so
`test_report_snapshot` fails at the merge base (AC51).

**T14 Run and resume** (spec §4.2.2). Generated options, `CliDeps` wiring of engine, adapters, calcs and page ports,
outcome mapping, report at the end. Fake-host workflow and replay
tests. Budget 380 lines (400 before amendment B-510, 355 after it, 380 after amendment B-541; see the amendments below). The original T14 (430 lines) was split by B-342 (D-12). Amendment B-510:
`run --answers` and `resume --answers` (AC46, AC64; about 50 lines) move to T14c with the page ports' wait mode, which
the 400 cap could not take; `run` and `resume` of T14 reject an `--answers` option as "not available in this build"
until T14c. For a workflow that declares no required basis field (step 3 does not run), T14 passes `basis_ref` `res_`
followed by 26 zeros, the interim reading of spec Q23 (about 2 lines). The report of step 6 (at the end and on a
pause) reads that reference through `report/_document.py` `_basis_rows`, which raises `REF_NOT_FOUND` on it, so a run
test with such a workflow passes `--no-report`, and a fake-engine test that writes the report journals a header whose
`basis_ref` names a result the test stored. Amendment
B-412: T14 adds its `CliDeps` fields in `cli/__init__.py` under the defaults rule of §3 and registers the `run` and
`resume` handlers there. Its fields include the engine factory, bound at once to the merged `eng_harness.engine.Engine`
(engine plan T9 and T9b), and the workflow-registry field (default `None`; T18a binds it to the registry of
`workflows/__init__.py` once plan 0007 T9b, which creates it (spec 0007 Q13), merges; plan 0010 T9 adds its workflow
there; amendment B-471) (amendment B-412 fourth review); `_wiring.py` binds the page ports' `report` callable to `build_report` over the run's reader
and store, and their stop check to `FileRunControl`; it builds `ReleaseMarks` from the configuration's
`[project_lane.<tool>]` tables for `build_report` and the page ports (amendment B-412 ninth review). Amendment B-412 fifth review: the engine-factory field takes the
full port set that `_wiring.py` builds (the six ports of engine plan T9, plus the `DecisionPort`, the
`ProgressSink` and the `RunControlPort` of spec §4.2.2 step 5), so a fake engine from `CliDeps` sees all of them; the
default factory maps into `EnginePorts` only the fields the merged `EnginePorts` holds. Amendment B-510: the merged
`EnginePorts` holds tool, host, calc, basis, approvals, inputs and `decision` (engine plan T14); T14b maps the
cascade into `decision`, and T16b maps the progress and run-control ports once engine plan T18 adds their fields.
Until then those two ports do not reach the real engine; T18a and T18b, which make `run` and `resume` available
with the default `CliDeps()`, follow T16b, so production never runs without them. T14 also owns the stop-file removals of spec §4.4.8 in `cli/_run.py`: the run process removes `stop.json`
when `Engine.start` or `Engine.resume` returns while the file exists, and `resume` removes a stale one at the start
of the command, before step 1 and before `cli/_signals.py` installs its handler, never just before `Engine.resume`
(amendment B-412 ninth review, spec §4.4.8), so a file the first interrupt writes during step 1 or step 5 is kept;
`test_stop_file_removed_on_return_and_before_resume` checks both with a fake engine from `CliDeps`, including a stop
file written after the stale-file removal, which the fake engine must still see
(about 20 lines, hence 340 to 360). AC9 is covered by T16 (the stop command) and by T14 (these removals).
Amendment B-412 seventh review: (a) the page ports' `stop_requested` and `report` need the run id, which for `run`
exists only once `Engine.start` has created it; `_wiring.py` binds both through the run-id cell of spec §4.4.8,
filled at once for `resume` and, for `run`, from the first `ApprovalRequest.run_id` that the wrapped page
`ApprovalPort` receives (T16b adds the `run_started` fill once the progress sink reaches the real engine); while it is
empty, `stop_requested` returns false and `report` returns the "report not available yet" document.
`test_run_id_binding.py::test_page_bindings_before_and_after_run_id` checks both callables before and after the cell
is filled, and that `resume` fills it at once (about 30 lines, hence 360 to 390). (b) The engine's `CalcPort` is
`HarnessCalcPort(registry, approvals, store, settings, run_class, clock, ids, *, basis_fields=None, code_packs=None)`
(spec 0003 §4.12), merged (plan 0003
T5; amendment B-510); T14 adds the `CliDeps` field `calc_port_factory` (default `None`: its default assembles what
T18a binds, below and §3), which
`_wiring.py` calls as `calc_port_factory(config, workspace, store, run_class, clock, ids)` (amendment B-412 eighth
review): the run's `ResultStore`, the run class (`--run-class` for `run`; for `resume` the run header's `run_class`,
read through the merged `JournalReader` before `Engine.resume`), the clock and the ids. The `approvals` argument of
`HarnessCalcPort` is the calcs approvals file of spec 0003 (`load_approvals`), not the page `ApprovalPort`; the calc
registry, the approvals file, the calc settings and the `basis_fields` map (spec 0003 §4.12, spec 0007 §4.5; B-498)
are the default factory's business (T18a). Step 4's preflight is
that port's `preflight`, so no separate preflight field exists. (c) The port builder field `port_builder` (default
`None`) is called as `port_builder(config, workspace, store, run_folder, clock, ids)` (T14c adds `files` and moves
the call to the end of step 2, amendment B-536, and adds `visible`, amendment B-543), where `run_folder` is a
callable that reads the run-id cell and raises while it is empty (spec §4.4.8); `build_ports` (spec 0002) builds
only the tool and host ports, and T18b binds the default (spec Q20 answer A, amendment B-471). (d) `_wiring.py` builds the
`ExpectedTimes` index once before the engine starts (`ExpectedTimes.build(workspace, workflow, settings)`, merged T4,
spec §4.3) and gives it to `TerminalProgress` (about 10 lines for (c) and (d), hence 390 to 400, then 355 after the
B-510 split). The engine's `BasisPort` is the merged `StoreBasisPort` over the run's `ResultStore` (plan 0004 T8),
built in `_wiring.py` with no field; the `Workspace`, the `ResultStore` and the `EngineSettings` that `Engine(...)`
takes are built in `_wiring.py` too (collaborator map of §3).
Amendment B-541 (spec §4.2.2 step 5, §4.2.3, §4.7, AC71; spec 0002 §4.1, AC48): (a) the port builder returns the ports
as an async context manager (spec 0002 `AdapterPorts`, plan 0002 T22). T14 does not wait for T22, so `cli/__init__.py`
types the result of `CliDeps.port_builder` as a cli-local structural type, a `Protocol` `RunPorts` whose
`__aenter__` answers an object exposing `tool_port` (`ToolPort`) and `host_port` (`HostPort`) and whose `__aexit__`
takes the exception triple; both the test fake and `AdapterPorts` fit it, and the command line imports no adapter
module (about 6 lines); `cli/_run.py` enters them just before
`Engine.start` and `Engine.resume` and leaves them when the call returns or raises, so the servers start inside the
manager's task group and shut down at the end (about 8 lines); the fake port builder of `tests/helpers/cli_deps.py`
returns ports that record entering and leaving, and `test_cli_run.py::test_ports_entered_around_engine_call` checks
the order around a fake engine that returns and one that raises; it fails at the merge base, where nothing enters them.
(b) A `ConfigError` from the port builder (spec 0002 §4.1: an invalid server section or no host program for a
server's product) is printed as `main` prints one and ends the command with `exit_code_for(Outcome.USAGE)` before any
run folder (about 3 lines; T14c keeps it when it moves the call). (c) `_wiring.py` builds the `Workspace` with
`resolve_workspace(deps.environ, default_location_probe())`; a `LocalWorkspaceError` prints its message and remedy and
ends `run` or `resume` with exit 2, nothing created (about 4 lines). (b) and (c) are cases of
`test_refusals_create_no_run`. (d) `cli/_exit.py` maps `HOST_LOCKED` to `RUN_LOCKED` (4), written beside the
`RUN_LOCKED` entry so that plan 0002 T19a's `NOT_IMPLEMENTED` entry, beside `INVALID_ARGUMENT`, merges without a
conflict whichever lands second; the case joins `test_error_codes` (1 line). (e) The `--input` file is read as
`utf-8-sig` (spec §4.7), a case of `test_run_completes_and_writes_report`. Budget 355 to 380 (fix round 1 of B-541:
the `RunPorts` type, about 6 lines).

**T14c Wait mode and answers files** (amendment B-510, split from T14; spec §4.2.1, §4.4.5 step 2, AC46, AC64). (1)
The merged engine calls `answer(request_id, wait=False)` at every request (`engine/_approvals.py`, `_decide.py`,
`_inflight.py`), while the process waits unless `--no-wait` (spec §4.2.1). `_wiring.py` therefore wraps the page
`ApprovalPort` and `InputPort` in a generic wrapper (`answer(request_id, *, wait) -> T | None`, naming no answer type,
so the AC2 rules test holds) that ignores the engine's `wait` and calls the inner port with `not --no-wait`; the
`--wait-timeout` value stays the page ports' parameter (T14). `test_cli_run.py::test_page_ports_wait_unless_no_wait_real_engine`
runs the merged `Engine` with the page ports through `CliDeps` and a test workflow with one approval and no required
basis field, with `--no-report` (the Q23 reference cannot be reported, T14): answered on the page, `run` exits 0; with
`--no-wait` it exits 10 at once. It fails at the merge base, where the engine's
`wait=False` reaches the page ports. (2) The B-354 part of the former T14: `run --answers FILE` (AC64): the object is
checked in step 2 and the page `InputPort` is wrapped so that the first data request is answered from it once through
`pages.accept_answers_file`; and `resume --answers` (AC46) answers pending data requests from the keyed object (or
the bare one when one data request is pending) the same way. (3) The answer's `by` is `engineer:<name>` from
`[engine] engineer`; while it is unset, both are refused with exit 2 naming `[engine] engineer`, before any run folder
(`run`, step 2) and with nothing journaled (spec §4.2.1, AC46, AC64), a case of `test_form_request_answers_file`.
Workflow tests use a fake engine from `CliDeps` except the wait test; T17c re-checks AC46 and AC64 with the real
engine. (4) Amendment B-536 (spec §4.2.2 step 2, AC67, AC68): the port builder is called at the end of step 2 as
`port_builder(config, workspace, store, run_folder, clock, ids, files, visible)` (`files` and `visible` by keyword;
`visible` is the input's top-level `visible_host` bool or false, amendment B-543, spec 0007 §4.2), `files` mapping the base name of each
top-level `pathlib.Path` field of the workflow's input model to its value (absolute and existing; a relative path, a
missing file or a repeated base name is exit 2 with no run folder); `resume` builds the same mapping from the run's
input read through `input_ref` of the run header before `Engine.resume`, without the existence check (a case of
`test_model_files_reach_the_port_builder` removes the original before `resume`). A `NotImplementedGap` from the port
builder (spec 0002 AC43, gap H-G8) prints its message on standard error and ends `run` and `resume` with
`exit_code_for(Outcome.USAGE)` (2), returned by T14c itself, not through `exit_code_for_error`, whose
`NOT_IMPLEMENTED` entry plan 0002 T19a adds later (T19a keeps its table case). `test_model_files_reach_the_port_builder`
and `test_port_builder_gap_exits_2` inject a recording or raising port builder through `CliDeps`; both fail at the
merge base, where the port builder takes no `files` and its exception is not caught. Amendment B-541: the moved call
keeps T14's `ConfigError` exit beside the H-G8 exit, and the `--answers` file is read as `utf-8-sig` (spec §4.7), a
case of `test_run_answers_first_data_request`. The move deletes the `ConfigError` clause at T14's place and adds it at
the end of step 2 (about 6 counted lines; the encoding is an argument of the read T14c writes), hence 130 to 136.

**T14b Signals, launch address, decision layer** (spec §4.2.2). Signal handling (the first interrupt is a stop
request, the second ends the process, AC10); the launch address shown on the controlling terminal only (AC61).
Amendment B-098: the decision layer is built from `[providers.*]` through `load_providers_config` and the `CliDeps`
assembler (`assemble_decision_runtime`), with the cascade of spec 0005 as the `DecisionPort` and the runtime's warnings
on standard error (AC62); the run header records the runtime's summary (AC63, through engine AC69). About 30 lines of
the 120. T15 and T16 follow T14b. Amendment B-412: `providers_loader` and `decision_assembler` are `CliDeps` fields in
`cli/__init__.py` under the defaults rule of §3: until plan 0009 T1 and T10a merge they default to `None` (the
decision layer is then not available and `run` and `resume` exit 2 "not available in this build"), AC62 is tested through injected recorders, and T18a binds the defaults once plan 0009 T1 and T10a have merged (amendment B-475). Amendment B-510: `load_providers_config` (plan 0009 T1) is merged, so T14b binds the `providers_loader` default to it (§3 rule), checked by `test_decision_wiring.py::test_providers_loader_default_is_load_providers_config` (the default `CliDeps().providers_loader` is that function); `decision_assembler` stays `None` until T18a. The merged configuration refuses `[decisions]` as an unknown section, so T14b adds `decisions: DecisionSettings = DecisionSettings()` to `HarnessConfig` in `cli/_config.py` (imported from `eng_harness.decisions._policy`; a bad value is a `ConfigError` naming `decisions.<key>`), and `_wiring.py` passes `config.decisions` as the assembler's `decision_settings`; `test_decision_wiring.py::test_decisions_section_reaches_assembler` checks that a `[decisions]` table reaches the recording assembler (it fails at the base, where the section is refused). `_wiring.py` calls the assembler as `decision_assembler(providers_config, decision_settings, workspace, point_policies)`, the four inputs of spec §4.2.2 step 5 and spec Q16(a), so the spec's default `assemble_decision_runtime` is called as the spec reads it; `point_policies` (the mapping from each point name to its `DecisionPolicy`) is a fourth `CliDeps` field in `cli/__init__.py`, default `None` under the defaults rule of §3 (while it is `None`, `run` and `resume` stay "not available in this build"), injected in AC62's tests (an empty mapping, recorded by the assembler recorder), and bound by T18a (amendment B-412 tenth review, replacing the ninth review's three-argument call). The
first interrupt writes the stop file of spec §4.4.8 with `by` = `signal`. Amendment B-412 eighth review:
`cli/_signals.py` reads the run-id cell of T14; while the cell is empty or the run folder does not exist yet (steps 1
to 4 of spec §4.2.2, the basis screen included, or the start of `Engine.start`), the first interrupt ends the process
as the second does (exit 130, no stop file, nothing buffered; spec §4.4.8, AC10).
`test_first_interrupt_requests_stop` covers both cases (about 15 lines, hence 120 to 135). Amendment B-541 (spec
§4.2.1, §4.7, AC70): `main` in `cli/__init__.py` resolves the workspace once with `resolve_workspace` and the default
location probe over a copy of `deps.environ` in which `--workspace`, when given, is `ENG_WORKSPACE`; its root is the
`<workspace>` of `resolve_config_path`; a `LocalWorkspaceError` leaves that argument `None` and is not reported by
`main` (the handlers meet it where they build their workspace, T14 and T16; `doctor` reports it). `main` keeps the
found configuration path on the parsed arguments (for `doctor`, T16) and calls the handler with `CliDeps` whose
`environ` is that copy. `load_config` reads `utf-8-sig`. `test_config.py::test_default_workspace_and_option_reach_lookup`
checks that a `harness.toml` in `<LOCALAPPDATA>/eng/workspaces/default` is found with no option, that with
`--workspace DIR` the file in `DIR` is found and the handler sees `ENG_WORKSPACE` = `DIR`, that with no workspace
configured the handler still runs, and that a file with a byte-order mark loads; it fails at the merge base, where the
default workspace is not looked up (about 11 lines, hence 145 to 160). Amendment B-412 fifth review: T14b puts the
cascade into the engine factory's port set (T14), and AC62 is checked on the fake engine's port set. Amendment B-510:
the merged `EnginePorts` has the `decision` field (engine plan T14), so T14b also maps the cascade into it in the
default engine factory (about 6 lines with the `providers_loader` default and the `[decisions]` field, hence 135 to
145); T16b's production test re-checks it.
Amendment B-412 sixth review: the cascade code (`eng_harness.decisions.Cascade`, plan 0005 T7, wired to the engine by
plan 0005 T10) is not merged, so T14b builds the `DecisionPort` through a third `CliDeps` field in `cli/__init__.py`,
`decision_port_factory` (default `None` under the defaults rule of §3). It takes the runtime that `decision_assembler`
returns and the run's decision inputs, and returns the decision port that goes into the engine factory's port set; its
exact parameters follow the `Cascade` construction of spec 0005 §4.5 as plan 0005 T7 and T10 fix it (the `rule_guard`
there is engine-supplied). While it is `None`, `run` and `resume` stay "not available in this build" (exit 2).
`test_decision_wiring.py` injects a recording factory and checks that it receives the assembled runtime and that its
result is the decision port the fake engine receives (AC62); `tests/helpers/cli_deps.py` gains the field. T18a binds
its default.

**T15 Basis confirmation** (spec §4.4.7). The screen, the answer, the setup log and the early steps of `run`.
Amendment B-354: `run --no-wait` with required basis fields exits 10 before any run exists, nothing stored (AC47).
Amendment B-412: step 3 of spec §4.2.2 goes in `cli/_run.py` and `cli/_wiring.py`; `PageBasisSetupPort` is exported
from `pages/__init__.py`, and its port class and the `setup` kind are registered in the dispatch of `pages/_ports.py`. A
basis-port factory or `freeze` that becomes a `CliDeps` field goes in `cli/__init__.py` under the defaults rule of §3;
both real implementations are merged (`BasisSetupPort` and `eng_harness.basis.freeze`, plan 0004 T7 and T8), so T15
binds such a field's default itself (amendment B-412 fourth review; T18a does not).
Budget 250 to 330: about 120 for the screen, 60 for the port and its registration, 50 for the setup log, 70 for step 3
and `--no-wait`, and 30 for the wiring (an estimate, not a measurement). Amendment B-510: (1) `build_draft` takes the
workflow's `FieldSpec` list, but the merged `WorkflowDef` has only `required_basis` (`basis_fields` is plan 0007
T6's). T15 adds the `CliDeps` field `basis_fields_of: Callable[[WorkflowDef], Sequence[FieldSpec]] | None`, default
`None` under the defaults rule of §3: while it is `None`, a workflow with required basis paths is "not available in
this build" (exit 2). `test_cli_basis.py` injects it with a test-local `FieldSpec` list and
`tests/helpers/cli_deps.py` gains it; T18a binds the default (about 6 lines). (2) The template folders and the version
rule of `--template` are spec Q22; until it is answered T15 follows its interim reading: shipped templates only (the
user folder is a path below a regular file of the package, `Path(eng_harness.templates.__file__) / "user"`, which can
never exist, so `TemplateRepository` reads it as empty; no folder is created), and `--template NAME` without
`@VERSION` exits 2 naming the form `NAME@VERSION`, a case in `test_cli_basis.py` (about 4 lines). Budget 330 to 340.
Amendment B-541 (spec §4.2.2 step 3, §5): step 3 reads the `--basis` file with spec 0004's `load_strict`
(`templates/_yaml.py`; YAML 1.2, which reads a JSON file too, with an optional byte-order mark) and validates it as
`EngineerValues` (`{name, values}`); a refusal is exit 2 naming the file; `test_basis_confirmation_flow` writes its
values file with `name` (about 3 lines inside the step 3 estimate; budget unchanged).

**T16 status, stop, report, doctor** (spec §4.2.1, §4.3 heartbeat). Read-only status, the `stop` command in
`cli/_stop.py` (it writes the stop file only when the run lock is held, and `--wait` waits until the run lock is
released, spec §4.4.8; the stop-file protocol lives in `cli/_control.py`, T7b; amendment B-412 fourth and eighth reviews),
the report command, the doctor pass-through. Amendment B-412: the report and doctor handlers live in `cli/_status.py`;
T16 registers the four handlers in the `CliDeps` handler table in `cli/__init__.py`. The doctor callable is a `CliDeps`
field under the defaults rule of §3, injected in `test_doctor_command`; `eng_harness.doctor.run` (plan 0002 T18) is merged, so T16 binds the default itself (amendment B-510; T18a does not), checked by `test_doctor_command.py::test_doctor_default_is_doctor_run` (the doctor field of a default `CliDeps()` is that function).
`test_stop_pauses_at_safe_point` drives a fake engine from `CliDeps` that polls `FileRunControl`; the real-engine stop
is re-checked in T17. Amendment B-536 (spec AC69): after the HTML, the report command writes
`<run>/report/cycle-timings.json` by `write_cycle_timings(edit_cycle_timings(reader, store), path)` (plan 0007 T10b,
exported from `report/__init__.py` here) when the timings hold at least one cycle, whatever `--out` says;
`test_cycle_timings_file` checks a scripted edit-cycle journal and one without a cycle. Amendment B-541 (spec AC13,
AC71; plan 0002 T22): the doctor handler calls the doctor callable with the configuration path `main` kept (`None`
when no file was found) and `env=deps.environ` (which carries `--workspace`, T14b), and ends a `ConfigError` with
exit 2 naming the key (`test_doctor_command.py::test_doctor_receives_config_path_and_environment`, which fails at
the merge base); `status`, `stop` and `report` end a `LocalWorkspaceError` from building their workspace with exit 2
and its message and remedy, a case of `test_states_and_read_only`. Budget 345 to 355.

**T16b Production wiring of the decision, progress and run-control ports** (amendment B-412 fifth review; spec
§4.2.2 step 5, AC9, AC37, AC62). The merged `EnginePorts` holds the tool, host, calc, basis, approval and input
ports and the `decision` field (engine plan T14, merged; T14b maps the cascade into it, amendment B-510); engine plan
T18 adds the `ProgressSink` and `RunControlPort` fields (engine plan §3, amendment B-412). T16b waits for engine plan
T18 and completes the default engine factory's mapping in `cli/_wiring.py`: `TerminalProgress` and the
page server's sink behind one fan-out `ProgressSink`, and `FileRunControl` as the run-control port; `cli/_run.py` takes
any change the mapping needs. The fan-out isolates its members (amendment B-412 seventh review): it catches a member's
failure, detaches that member itself and keeps delivering to the others, and it raises (so that the engine detaches
it under engine AC58) only when every member has failed. A raising terminal renderer (AC19) therefore does not cut
the page off from `approval_resolved` (AC37); `test_failing_sink_detached_alone` checks this. The fan-out also fills
the run-id cell of T14 from the `run_started` event (`RunHeader.run_id`, spec §4.4.8), which
`test_engine_ports_carry_stop_progress_and_cascade` checks too.
Amendment B-412 eighth review: T16b also starts T5's `Heartbeat` as an asyncio task in `cli/_run.py` beside the
engine call and cancels it when the call returns; its path callable reads the run-id cell (`<run folder>/heartbeat.json`,
`None` while the cell is empty or the folder does not exist). It belongs here because the beat shows the current step
and `seq` from the sink's events, which reach `TerminalProgress` only once the progress sink reaches the real engine
(engine plan T18); `test_heartbeat_follows_run_id_cell` checks that no file is written before the cell fills and that
the file is written in the run folder after (about 20 lines, hence 130 to 150).
`test_engine_ports_carry_stop_progress_and_cascade` builds the production `EnginePorts` through the default mapping and
checks those three fields; it fails at the merge base, where the default mapping leaves the progress and run-control
fields out. It is the only non-test task that touches those two fields, so T17 and T17c, which depend on it, re-check
through the production path.

**T17 End to end** (spec §3.4, §3.6, §3.7). Per-item rejection and void flows through the page, the killed-wait replay,
the all-screens untrusted text property test, the Windows Arabic test (Arabic workspace path, cp1256 console,
`ar-SA` culture where present). T17 waits for engine plan T15 (which brings T9 to T14b), engine plan T18 (progress
delivery and, by amendment B-412 fifth review, the run-control check between steps) and T16b (the production wiring),
and uses the real engine through the default port mapping, no fakes: it re-checks with the real engine the halves deferred from T5 (AC19, a raising
`TerminalProgress` renderer is detached and the run continues:
`test_progress_detach.py::test_raising_renderer_detached_run_continues`; amendment B-412 eighth review: this one test
installs `TerminalProgress` directly as the real engine's only sink, because through the production fan-out of T16b a
failing member is detached by the fan-out and engine AC58 is never reached; the fan-out path is T16b's
`test_failing_sink_detached_alone`), T7 (AC29 and AC37:
`test_page_approval.py::test_answer_bound_to_hash_real_engine` and `::test_page_confirms_after_commit_real_engine`) and
T16 (AC9: `test_cli_stop.py::test_stop_real_engine_pauses_at_safe_point`). It passes the real collaborators to
`CliDeps` explicitly, so it does not wait for T18a or T18b. Amendment B-412 second review: everything these tests exercise is
already merged at T17's merge base, so a `feat` pull request would fail test-first with TF004 (gate spec §4.7 step
4.3). T17 therefore holds only test files and its pull request is titled `test(eng-harness): ...`: test-first step 3
checks that no non-test file changed (TF007), and the tests run in the `gate` job, where they must pass at the head.
Its `tests_first` list names the nodes the review checks; they are not run against the merge base. AC34's page half
(the voided display) is T7b's (amendment B-412 eighth review), so `test_void_after_model_change` needs no code here.

**T17b Local testing list and agent rule** (amendment B-412 second review, the documentation half of T17; a
`docs(eng-harness): ...` pull request, exempt from test-first). `docs/local-testing.md`, and the rule "approvals are
the engineer's; never read or relay the launch address" in `packages/eng-harness/.gate/agents.yml`, with `AGENTS.md`
re-rendered by `uv run eng-gate agents render` in the same pull request (the CI `agents-drift` job fails on a
difference; `CLAUDE.md` is only `@AGENTS.md`). The template has no free-form slot for a package rule, so the rule text
(run and resume in the background and follow with `status`, or `--no-wait` and tell the engineer; never read or relay
the launch address or open the page; approvals are the engineer's) is appended to the `one-paragraph purpose` value,
and `entry-point` is set to `--package eng-harness eng-harness <command>`.

**T17c Real-engine re-checks of the run commands** (amendment B-412 third review; spec §9 staged engine). T9b, T14,
T14c, T14b and T15 test with the T7 engine stand-in or a fake engine from
`CliDeps` (§3). T17c waits for engine plan T15 (which brings T9 to T14b), for T16b (so engine plan T18 too) and for
plan 0007 T6 (`WorkflowDef.basis_fields`, for AC47; amendment B-510), and
re-checks each staged criterion with the real engine, through the production port mapping, and fake ports: AC7 (`test_cli_run.py::test_run_completes_and_writes_report_real_engine`), AC8
(`test_cli_resume.py::test_no_wait_then_resume_real_engine`), AC42 (`test_signoff.py::test_signoff_rules_real_engine`),
AC46 (`test_cli_answers.py::test_form_request_answers_file_real_engine`), AC47
(`test_cli_basis.py::test_basis_confirmation_flow_real_engine`), AC61
(`test_launch_address.py::test_address_never_on_stdout_or_stderr_real_engine`), AC63
(`test_cli_run.py::test_run_header_records_decision_runtime_real_engine`, the real engine's header through engine AC69
with a recording decision assembler, as in T14b) and AC64
(`test_cli_answers.py::test_run_answers_first_data_request_real_engine`). Like T17 it passes the real engine to
`CliDeps` explicitly (so it does not wait for T18a or T18b), holds only test files, and its pull request is titled
`test(eng-harness): ...` for the same test-first reason (TF004, TF007); its `tests_first` list names the nodes the
review checks. It is split from T17 to keep each test-only pull request within two sessions.

**T18a Bind the CliDeps defaults except the port builder** (amendment B-412 second review; split from T18 by
amendment B-471, owner instruction of 2026-11-12; spec §4.1, AC62; AC13 is T16's since amendment B-510). The task that replaces each `None` default
of the §3 rule but the port builder with the real implementation: the calc-port
factory `calc_port_factory` (plan 0003 T5 `HarnessCalcPort`, whose `preflight` serves step 4; amendment B-412 seventh
review; the eighth review spells the default out: it builds `HarnessCalcPort(registry, approvals, store, settings,
run_class, clock, ids, basis_fields=...)` from the calc registry of spec 0003, the approvals file read by the merged
`load_approvals` (`_calc/_approvals.py`), the calc settings from the configuration and the `basis_fields` map of spec
0003 §4.12 and spec 0007 §4.5 (B-498), with the arguments T14 passes), the workflow registry of `src/eng_harness/workflows/__init__.py`
(plan 0007 T9b, the one task that creates that module and registers the model-edit-cycle workflow in it, spec 0007
Q13; plan 0010 T9 and plan 0013 T11 and T13 add their blocks later, so T18a does not wait for them), `assemble_decision_runtime` (plan
0009 T10a, the phase-1 assembly of spec 0009 AC49; amendment B-475), the point-policy mapping `point_policies` (amendment B-412 tenth review), bound to the empty mapping, the phase-1 value of spec Q16 (d), never `None` (amendment B-475), the cascade builder `decision_port_factory` (the `Cascade` of plan 0005 T7, wired to the engine by
plan 0005 T10; amendment B-412 sixth review), and `basis_fields_of` (T15), bound to the workflow's `basis_fields`
(plan 0007 T6; amendment B-510). The engine factory and `freeze` are merged (engine
plan T9 and T9b; plan 0004 T8) and are bound by T14 and T15, and `load_providers_config` and `eng_harness.doctor.run`
by T14b and T16, not here (amendment B-412 fourth review; amendment B-510). It waits for
all of them; if one is still missing long after the others, the lead amends this plan to split T18a rather than bind
a stub. `test_defaults_are_the_real_implementations` checks that each of these fields of `CliDeps()` is the real
callable, that the calc port the default `calc_port_factory` builds carries the
`basis_fields` map (`harness.model_diff` and `harness.readback_check` mapped to the `BASIS_FIELDS` of
`calcs/model_diff.py`, spec 0007 §4.5; amendment B-503), and that `run` and `resume` stay "not available in this build" while the
port builder is `None`; it fails at the merge base because the defaults are `None`. T18a follows T16b (amendment B-412
fifth review). The port builder needs no basis argument: the read-back tolerance reaches the CSI host port from the
run header (spec 0002 §4.5.8, closed gap H-G9; amendment B-503), so T18a and T18b pass nothing for it.

**T18b Bind the port builder and draw the run id** (split from T18 by amendment B-471; spec §4.2.2 step 1, §4.4.8,
Q20 answer A). `cli/_wiring.py` draws the run id for `run` at step 1 (`run_` + ULID from the ids source), fills the
run-id cell at once, as for `resume`, and passes the id in `RunRequest.run_id` (engine plan T20, work item B-472,
engine AC70); the `port_builder` default is `build_ports` (plan 0002 T19a; amendment B-475), so the default calls `build_ports(config,
workspace, store, run_folder(), clock, ids, files=files, visible=visible)` (the `files` of T14c, amendment B-536, and its
`visible`, amendment B-543). `test_port_builder_bound_and_run_id_drawn` checks that the default is
`build_ports`, that the default hands `files` and `visible` to `build_ports` unchanged (a case with `visible` true), that for `run` the cell holds the id before any port is built and the engine receives the same id, and
that `run` and `resume` are then available with `CliDeps()`; it fails at the merge base because the default is `None`.
It covers AC66. Amendment B-541: once the id is drawn, `run` prints the line `run id: <run_id>` on standard error,
and the default converts the configuration's server sections with plan 0002 T22's `servers_config` before it calls
`build_ports`; `test_port_builder_bound_and_run_id_drawn` checks both (about 4 lines, budget 40 to 45). With the cell filled at step 1, the rule of spec §4.4.8 for a run id not yet known (AC10, tested by
T14b) applies to `run` only before step 1, and the fills from `ApprovalRequest.run_id` and `run_started` only confirm
the id (a differing value raises).
T18b follows T18a, so the default `CliDeps()` makes `run` and `resume` available only once every collaborator and the
decision, progress and run-control ports reach the real engine.

## 3. Dependencies

- Runtime: none new (`eng-contract`, `pydantic`; the YAML and MCP dependencies belong to plans 0004 and 0002). No
  package ADR is needed. Using Jinja2 instead would need one (A10; spec Q1).
- Development: none new.
- Other plans: engine plan T4 (reader), T6 (ports), T9 and T9b (runner start, resume; split by B-424), T14 (the
  `DecisionPort` field of `EnginePorts`), T15 (approvals), T18 (progress delivery, and the `RunControlPort` field with
  the stop check between steps, added to engine T18 by this plan's B-412 pull request; T16b waits for T18, T14 and
  T14b being merged; amendment B-510);
  plan 0002 T18 (doctor) and the adapter wiring `build_ports`; plan 0003 T5 (`HarnessCalcPort` and its `preflight`, the `calc_port_factory` default); plan 0004
  T7 (`BasisSetupPort`, `build_setup_view`) and T8 (`freeze`); plan 0002 T22 (`doctor.run` with `config_path=None`
  and `env`, `AdapterPorts`, `servers_config`) for T16, while T14 and T18b meet `AdapterPorts` and `servers_config`
  through their fakes and through plan 0002 T19a, which waits for T22 (amendment B-541); plan 0007 T6 (`WorkflowDef.basis_fields`) for T17c
  and T18a, not T15, which injects `basis_fields_of` (amendment B-510); plan 0007 T9b for the workflow registry (`workflows/__init__.py`, spec 0007 Q13; plan 0010 T9 adds its workflow to it; amendment B-471); engine plan T20 (caller-chosen run id, for T18b; amendment B-471); plan 0007 T10b (`edit_cycle_timings`,
  `write_cycle_timings`, for T16's `report/cycle-timings.json`; amendment B-536); for T14b (B-098),
  decision plan T7 (the `Cascade`) and T10 (the cascade's `runtime_summary()` and its engine wiring; amendment B-412
  sixth review: the cascade is the `decision_port_factory` default that T18a binds), engine plan T14b (`decision_runtime` in the header) and
  provider plan 0009 T1 (`load_providers_config`, merged; T14b binds it, amendment B-510) and T10a (`assemble_decision_runtime`, phase 1; amendment B-475). T14, T14c, T14b and T15 use
  fakes and `CliDeps` until the real ones merge, so they do not wait; the pull request that finds the real
  implementation missing states it. Their real-engine halves are re-checked in T17c (staged engine, below); plan 0009
  section 3 says the same (amendment B-412 third review).
- `CliDeps` defaults rule (amendment B-412; T14, T14b, T15, T16). Each `CliDeps` collaborator whose real implementation
  is not merged (port builder, calc-port factory `calc_port_factory` (its port serves the preflight; amendment B-412 seventh review; `HarnessCalcPort` is merged, but the default assembles the calc registry, the approvals file, the settings and the `basis_fields` map, T18a, amendment B-503), workflow registry, workflow basis fields `basis_fields_of` (plan 0007 T6; amendment B-510), decision assembler, cascade
  builder `decision_port_factory` (amendment B-412 sixth review)) is an optional field of the frozen dataclass that defaults to `None`, so `CliDeps()`
  still builds (what `eng_harness.cli:main` uses with `deps=None`, and what `tests/unit/cli/test_opener.py` calls).
  Tests pass the collaborators explicitly. A command counts as available only when every collaborator it needs is not
  `None`: the handler table (or the handler at dispatch) checks this, so with the default `CliDeps()` that command
  keeps exiting 2 "not available in this build". No stub stands in for a missing implementation in production code.
  T18a and T18b (split from T18 by B-471) replace every `None` default with the real one once the real implementations
  have merged; the providing tasks of the other plans do not touch `cli/__init__.py`. A collaborator whose real implementation is already merged
  when its field is added gets that default in the same task: the engine factory (`eng_harness.engine.Engine`, engine
  plan T9 and T9b) in T14, `freeze` and any basis-port factory (plan 0004 T7 and T8) in T15 (amendment B-412 fourth
  review: they were listed as not merged, which was out of date), the providers loader (`load_providers_config`, plan
  0009 T1) in T14b and the doctor callable (`eng_harness.doctor.run`, plan 0002 T18) in T16 (amendment B-510). Tests build a fully set `CliDeps` through the shared helper
  `tests/helpers/cli_deps.py`, which T14 creates and T14c (the `files` argument of the port builder, amendment B-536), T14b, T15 and T16 extend with the fields they add, so that a new
  field does not turn an earlier task's `run` or `resume` test into exit 2 (amendment B-412 second review).
  (Amendment B-412 review: the earlier wording "no default and required" would make `CliDeps()` raise `TypeError`.)
- Staged engine (amendment B-412; extended by the third review to every staged criterion, matching spec §9). The
  runner's start and resume (engine plan T9 and T9b) are merged, but approvals (engine plan T10 to T15), the
  `DecisionPort` field (engine plan T14), and progress delivery and stop polling (engine plan T18, which the B-412
  pull request amends to add the `RunControlPort` field and the check between steps) are not merged when T5, T7, T9,
  T14, T14b, T15 and T16 may be built (amendment B-510: approvals and the `DecisionPort` field are merged now; T14b
  maps the cascade into `EnginePorts.decision`). Until T16b, `cli/_wiring.py` builds no progress or run-control field. T5 tests the sink alone; T7's and T9's workflow tests use a test-local
  engine stand-in that journals through the merged `JournalWriter` (T9b's too); the workflow and replay tests of T14,
  T14c (but its wait test, which runs the merged engine), T14b, T15 and
  T16 use a fake engine from `CliDeps`. T16b waits for engine plan T18 and completes the production
  wiring. T17 waits for engine plan T15 and T18 and for T16b, and re-checks AC9, AC19, AC29 and AC37 with the real
  engine; T17c waits for engine plan T15 and for T16b, and re-checks AC7, AC8, AC42, AC46, AC47, AC61, AC63 and AC64
  (test files only, see T17 and T17c); both go through the production port mapping of T16b, except T17's AC19 re-check,
which installs `TerminalProgress` as the engine's only sink (T17). AC33, AC34 and AC35 are tested end to end only in
T17, with the real engine; the page's voided display that AC34 needs is built in T7b (amendment B-412 eighth review).
- Run folder for `run` (amendment B-412 eighth review; spec §4.4.8, Q20). The run-id cell of T14 is the one source of
  the run folder for the page ports, the first interrupt (T14b), the heartbeat (T16b) and the port builder; each
  follows the empty-cell rule of spec §4.4.8. The tool and host ports cannot wait for a fill, so under spec Q20 answer
  A (decided by amendment B-471, owner instruction of 2026-11-12) `Engine.start` takes a caller-chosen run id (engine
  plan T20, work item B-472) and T18b draws it at step 1, fills the cell and binds the `port_builder` default.
- Collaborator map (amendment B-412 sixth review; spec §4.2.2, §4.4.5, §4.4.8). Every object the command line builds,
  injects or binds, with the task that defines its `CliDeps` field (none: built inside `cli/` or `pages/`, no field),
  the task that binds its real default, and what provides the real code. "Merged" names a module on `build/v1`. This
  table is the assignment; a writer who finds an object missing from it stops and asks the lead.

| Object (spec step) | `CliDeps` field defined in | Real default bound in | Provided by |
|---|---|---|---|
| Configuration, `HarnessConfig` (§4.2.2 step 1) | none (`cli/_config.py`) | not applicable | merged (T3) |
| Streams, environment, handler table (§4.1) | T3 (`stdout`, `stderr`, `environ`, `handlers`) | T3; handlers registered by T14 (`run`, `resume`) and T16 (`status`, `stop`, `report`, `doctor`) | merged (T3) |
| Launch-address opener (§4.4.4) | T3b (`opener`) | T3b | merged (`cli/_opener.py`) |
| Clock and ids (§4.1) | T14 | T14 | merged (`eng_contract.ids`: `SystemClock` and the id helpers) |
| Providers loader `load_providers_config` (step 1) | T14b (`providers_loader`) | T14b (amendment B-510) | merged (plan 0009 T1, `providers/_config.py`) |
| Workflow registry (step 1) | T14 | T18a | plan 0007 T9b (`workflows/__init__.py`, spec 0007 Q13; amendment B-471) |
| Workflow basis fields, the `FieldSpec` list `build_draft` takes (step 3; amendment B-510) | T15 (`basis_fields_of`) | T18a (the workflow's `basis_fields`) | plan 0007 T6 (`WorkflowDef.basis_fields`) |
| Workspace, `eng_contract.store.Workspace` (step 1, amendment B-412 seventh review) | none (built in `cli/_wiring.py`, T14, over the environment `main` hands on, in which `--workspace` is `ENG_WORKSPACE`, T14b; amendment B-541) | not applicable | merged (`eng_contract.store`) |
| `ResultStore` of the workspace (steps 1, 5 and 6) | none (built in `cli/_wiring.py`, T14) | not applicable | merged (`eng_contract.store`) |
| `EngineSettings` from the `[engine]` limits of the configuration, engine §4.10 defaults otherwise (step 5, spec §4.2.4) | none (built in `cli/_wiring.py`, T14) | not applicable | merged (`engine/_runner.py`) |
| Port builder `build_ports`: tool and host ports only (end of step 2 since amendment B-536), called as `port_builder(config, workspace, store, run_folder, clock, ids, files, visible)` with `run_folder` a callable over the run-id cell (amendment B-412 eighth review) and `files` the model files of the input (T14c, amendment B-536) and `visible` the input's `visible_host` (T14c, amendment B-543) | T14 (`port_builder`; T14c adds `files` and `visible`; T14 enters the returned ports around the engine call, amendment B-541) | T18b (spec Q20 answer A, amendment B-471: T18b also draws the run id in `cli/_wiring.py`; it converts the server sections with `servers_config`, amendment B-541) | plan 0002 T19a (amendment B-475) over plan 0002 T22 (`AdapterPorts`, `servers_config`; amendment B-541); engine plan T20 (caller-chosen run id, work item B-472) |
| Calc port `HarnessCalcPort(registry, approvals, store, settings, run_class, clock, ids, *, basis_fields=None, code_packs=None)` (steps 4 and 5), called as `calc_port_factory(config, workspace, store, run_class, clock, ids)` (amendment B-412 eighth review) | T14 (`calc_port_factory`) | T18a (the default supplies the calc registry, the approvals file through the merged `load_approvals`, the calc settings and the `basis_fields` map, B-498) | plan 0003 T5; `load_approvals` merged (`_calc/_approvals.py`) |
| Run class: `--run-class` for `run`, the run header's `run_class` for `resume` (steps 4 and 5) | none (`cli/_wiring.py`, T14) | not applicable | merged (`cli/_parser.py`, T3; `JournalReader`, engine T4) |
| Engine `BasisPort`, `StoreBasisPort` over the `ResultStore` (step 5) | none (built in `cli/_wiring.py`, T14) | not applicable | merged (`basis/_port.py`, plan 0004 T8) |
| Input validation (step 2) | none (engine call) | not applicable | merged (engine plan T9, engine AC16) |
| `--answers` object and the wrapped `InputPort` (step 2, §4.2.1) | none (`cli/_wiring.py`, T14c; amendment B-510) | not applicable | T10 (`pages.accept_answers_file`) |
| Draft (`build_draft`), basis-port factory, `freeze` (step 3) | T15, if they become fields | T15 | merged (plan 0004 T7 and T8: `basis/_build.py`, `_setup.py`, `_freeze.py`) |
| Basis screen port `PageBasisSetupPort` and the `setup` kind (step 3, §4.4.7) | none (`pages/_ports.py`) | not applicable | T15 |
| Calc preflight (step 4) | none: `preflight` of the calc port built by `calc_port_factory` | T18a (through `calc_port_factory`) | plan 0003 T5 |
| Decision-runtime assembler `assemble_decision_runtime` and `DecisionSettings` from the configuration (step 5) | T14b (`decision_assembler`) | T18a | plan 0009 T10a (phase 1, spec 0009 AC49; amendment B-475); `DecisionSettings` merged (`decisions/_policy.py`), read from `[decisions]`, a typed `HarnessConfig` field that T14b adds in `cli/_config.py` (amendment B-510) |
| Point policies for the release check of `assemble_decision_runtime`: a mapping from each point name to its `DecisionPolicy` (step 5; spec 0009 AC42; spec Q16; amendment B-412 ninth review) | T14b (`point_policies`, default `None`), passed by `cli/_wiring.py` as the fourth argument: `decision_assembler(providers_config, decision_settings, workspace, point_policies)` (spec §4.2.2 step 5, Q16(a); amendment B-412 tenth review) | T18a, to the empty mapping, the phase-1 value (spec Q16 (d), spec 0009 AC49; amendment B-475) | workflow code `policies/` (spec 0005 §4.3 and section 5); no task creates the mapping yet, and none is needed before plan 0009 T10b; the assembler's arguments are fixed by spec 0009 §4.1 (spec Q16 (a), amendment B-471) |
| Cascade as the `DecisionPort` (step 5) | T14b (`decision_port_factory`) | T18a | plan 0005 T7 (`Cascade`) and T10 (engine wiring); T14b maps it into the merged `EnginePorts.decision` (engine plan T14; amendment B-510) |
| `ExpectedTimes` index, built once before the engine starts (spec §4.3; amendment B-412 eighth review) | none (`cli/_wiring.py`, T14) | not applicable | merged (`progress/_expected.py`, T4) |
| `TerminalProgress` as the `ProgressSink` (step 5) | none (built by `cli/_wiring.py`, T14, with the `ExpectedTimes` index) | not applicable | T5; reaches the real `EnginePorts` in T16b (engine plan T18) |
| Heartbeat task and `heartbeat.json` (spec §4.3; amendment B-412 eighth review) | none (started in `cli/_run.py` by T16b; its path callable reads the run-id cell) | not applicable | T5 (`Heartbeat`) |
| Page server's sink and the fan-out `ProgressSink` (step 5, AC37) | none | not applicable | T7 (page sink), T16b (fan-out that isolates each member) |
| Run-id cell, read by the page ports' `stop_requested` and `report`, the first interrupt, the heartbeat and the port builder's `run_folder` (§4.4.8) | none (`cli/_wiring.py`, T14) | not applicable | T14 (filled for `resume` and from `ApprovalRequest.run_id`); T16b (filled from `run_started`); T18b (filled at step 1 for `run`, spec Q20 answer A, amendment B-471) |
| `FileRunControl` as the `RunControlPort` (step 5, §4.4.8) | none (built by `cli/_wiring.py`, T14) | not applicable | T7b (`cli/_control.py`); reaches the real `EnginePorts` in T16b (engine plan T18) |
| Page settings (`[page]` configuration, the `[engine] engineer` name) and the `--wait-timeout` value given to the page ports (§4.2.1, §4.2.4, §4.4.5 step 2) | none (`cli/_wiring.py`, T14) | not applicable | merged (`PageSettings`, `pages/_server.py`, T6); the timeout is T7's port parameter |
| Voided approval display (§4.4.5, AC34) | none (`pages/_ports.py`) | not applicable | T7b; the engine's request kinds by T10c (amendment B-545) |
| Page `ApprovalPort` and `InputPort` (step 5), wrapped with the process wait mode (§4.4.5 step 2) | none (`cli/_wiring.py`, T14; the wait-mode wrapper T14c, amendment B-510) | not applicable | T7 (approval, dispatch), T7b (voided display), T9 and T9b (review screens), T10 (choice and input screens) |
| Page server `PageServer` (§4.4.1, started lazily) | none | not applicable | merged (`pages/_server.py`, T6) |
| Page ports' stop check `stop_requested` (§4.4.5 step 2) | none (injected into the page ports, T7) | bound to `FileRunControl` through the run-id cell by T14 (`cli/_wiring.py`) | T7 |
| Page ports' `report` callable (§4.4.3 `GET /report`) | none (injected into the page ports, T7) | bound to `build_report` through the run-id cell by T14 (`cli/_wiring.py`) | T13 (`build_report`) |
| Engine factory (step 5) | T14 | T14 | merged (engine plan T9 and T9b); the decision field mapped by T14b, the progress and run-control fields by T16b (amendment B-510) |
| `ReleaseMarks` from the `[project_lane.<tool>]` tables of the configuration (spec §4.6.3, Q5; amendment B-412 ninth review) | none (built in `cli/_wiring.py`, T14, from the merged `HarnessConfig.project_lane`) | not applicable | merged (`report/_lineage.py`, T8; `cli/_config.py`, T3); passed by T14 to `build_report` (step 6 and the page ports' `report` callable) and to the page ports for the sign-off screen (AC42, AC54), whose `marks` parameter T9b adds in `pages/_ports.py` (amendment B-510) |
| Report at the end (step 6) | none | not applicable | T13 (`build_report`, `write_report`), called by T14 |
| `report/cycle-timings.json` of the `report` command (spec AC69; amendment B-536) | none | not applicable | plan 0007 T10b (`edit_cycle_timings`, `write_cycle_timings`), called and exported by T16 |
| Outcome to exit code (step 6, §4.2.3) | none (`cli/_run.py`, T14) | not applicable | merged (`cli/_exit.py`, T3) |
| Stop-file removals (§4.4.8) | none (`cli/_run.py`) | not applicable | T14 |
| First interrupt writes the stop file (§4.4.8, AC10): reads the run-id cell; empty cell or missing run folder ends the process (exit 130) | none (`cli/_signals.py`) | not applicable | T14b, through `cli/_control.py` (T7b) and the cell (T14) |
| `stop` command and `--wait` (§4.4.8, AC9) | none (`cli/_stop.py`) | not applicable | T16, through `cli/_control.py` (T7b) |
| Doctor callable (AC13), called with the configuration path `main` keeps (T14b) and `env` (amendment B-541) | T16 | T16 (amendment B-510) | merged (plan 0002 T18, `eng_harness.doctor.run`); `config_path=None` and `env` from plan 0002 T22 |

- Amendments to other documents (spec §11): engine §4.4.1 (`inbox/`; `stop.json` and `heartbeat.json`, Q19), engine §4.9 (`item_reasons`, the choice
  convention and the `x-eng-input` marker), spec 0002 (tool `release`, doctor checks). They are owner queue items, not part of any task here. Amended in this
  plan's B-412 pull request, to agree with the `CliDeps` defaults rule: plan 0009 section 3 (T14b does not wait for
  plan 0009 T1 and T10, now T10a by amendment B-475; T18 binds `load_providers_config` and `assemble_decision_runtime`) and plan 0010 T9 (T18 binds
  the workflow registry default); engine plan 0001 T14 and T18 and its section 3 (the `EnginePorts` fields added after T9
  take a `None` default, and T18 adds the `RunControlPort` field and the stop check between steps; amendment B-412 fifth
  review).

## 4. Verification

Local gate per task as in the engine plan §4; the pull request links its CI run. Review lenses: correctness, Python,
type design, silent failure, tests; T3, T6, T7, T9, T9b, T10 and T15 additionally with the security lens (T10: the answers-file gate; T3 and T14b: the launch address) (what an agent, a
web page in the browser, or a hostile drawing text can do); T8, T11 to T13 additionally against ADR-0026 §3 and the
rule "built only from the journal and the store". The second-family review and the owner's approvals are
`awaiting owner` in bootstrap mode.

Windows CI job: `tests/windows/` (Arabic environment) and `tests/perf/` (progress latency). Page tests bind the
loopback interface only.

Needs local test (listed in `docs/local-testing.md` by T17b): (1) the approval page in the owner's real browser: no
Content-Security-Policy violation in the console, Arabic and mixed-direction text from a real drawing and model
displays correctly, forms submit, a second tab opens by cookie; (2) the report opened and printed from disk: the DRAFT
watermark and the layout; (3) a workstation with an Arabic regional setting, the Hijri calendar and a cp1256 console:
`run`, `status`, `report`; (4) expected times and the heartbeat on a real analysis run, with the host programs (this
needs spec 0007's workflow and the Sasaah servers); (5) opening the launch address through the default browser when
the default is not Chromium-based; (6) the first run with no workspace configured (amendment B-541): `main`
(`cli/__init__.py`, T14b) calls `resolve_workspace` with `default_location_probe()`, which must classify
`%LOCALAPPDATA%\eng\workspaces\default` as local on the owner's Windows machine, so that every command finds the
`harness.toml` there. Nothing here drives a host program in CI.

## 5. Rollback

Each task is one squash-merged pull request; nothing outside this package consumes it until spec 0007's workflow runs.
Reverting a task reverts its dependants. The page and the report hold no state: a defect is fixed forward and a report
is rebuilt from the journal with `eng-harness report`. A changed exit code or JSON key is a public change (spec §10).
The `item_reasons` member of the journal (spec Q8) is read by readers with and without it.
