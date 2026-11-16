---
id: spec-0006-cli-progress-pages-report
issue: "B-065"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r3]
---

# Spec 0006: eng-harness command line, terminal progress, approval page and run report

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-04

This spec implements the phase 1 interface of [ADR-0027](../../../../design/docs/adr/0027-phase-1-interface.md): the
command line, live progress in the terminal, the local HTML approval page and the HTML run report. Sources:
[11](../../../../design/docs/architecture/11-harness-engine.md) §3 (`ctx.approve`) and §11,
[14](../../../../design/docs/architecture/14-harness-ui.md) §5 and §6 (the part of the deferred UI phase 1 needs),
[16](../../../../design/docs/architecture/16-security-safety-privacy.md) §4 and §5,
[13](../../../../design/docs/architecture/13-templates-and-design-basis.md) §4 (basis confirmation),
[18](../../../../design/docs/architecture/18-first-slice-dxf-to-etabs.md) steps 6, 15, 16, 17 and
[ADR-0026](../../../../design/docs/adr/0026-project-lane-for-tools.md) §3 (results from unreleased project-lane tools
are marked). It implements the ports `ApprovalPort`, `InputPort`, `ProgressSink` and `RunControlPort` of the engine
([spec 0001](0001-engine.md), "engine §n"), the page side of the basis setup of
[spec 0004](0004-templates-and-basis.md) §4.6, and registers `eng-harness doctor` of
[spec 0002](0002-servers-and-adapters.md) §4.9. It uses the contract of
[eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract §n"). It does not repeat
them. Details the architecture leaves open are marked **[added]** and listed in §11. Session findings from the Sasaah
baseline design notes (`agent-sessions/_baseline/DESIGN-NOTES.md`, read-only): A7 (the interface was an early
priority; progress with expected times), A8 (no progress display; a heartbeat) and C8 (the Arabic environment: Hijri
calendar, cp1256, Arabic paths).

**Amendment B-098.** The provider-layer spec ([spec 0009](0009-providers.md) Q7) asked that this spec read the
`[providers.*]` tables of `harness.toml` and call `assemble_decision_runtime` when it builds the engine's decision layer,
and that the run header record the runtime's summary. Both are made here (§4.2.2, §4.2.4, AC4, AC62, AC63) and listed in
§11 (Q15, Q16); the header field itself is engine AC69.

**Amendment B-354.** Four points the specs left open (root `LOCAL-TESTING.md`, open points 5, 6, 7 and 13) are
decided here and in [spec 0007](0007-model-edit-cycle.md): `run --answers FILE` pre-answers the first data request
(§4.2.1, AC64; spec 0007 Q7); a workflow that needs basis confirmation is started without `--no-wait`, and the
`run --no-wait` route of spec 0007 Q7 is withdrawn (§4.4.7, AC47); the one supported command form from the workspace
root is `uv run --package eng-harness eng-harness <command>` (§4.1, AC65); the A3 audit and the A7 prompt count are a
module entry point of spec 0007 (its AC35), not a seventh command (AC1 unchanged). Listed in §11 as Q17 and Q18.

**Amendment B-471.** By the owner's instruction of 2026-11-12, Q15, Q16 and Q20 are decided as their rows recommend:
`DecisionSettings` is read from `[decisions]` (spec 0005 §4.3; §4.2.4), `assemble_decision_runtime` takes the four
inputs of §4.2.2 step 5 and its summary carries the dropped releases (spec 0009 §4.1, AC29), the Status section of the
report shows the run's decision runtime (§4.6.1), and the command line draws the run id at step 1 for `run` as for
`resume` and passes it to `Engine.start` (engine AC70; §4.2.2, §4.4.8; AC66).

**Amendment B-495.** By the owner answer of 2026-11-14, the refusal of `[cli_tools.*]` entries before servers plan
T19b (spec 0002 AC43, gap H-G8) exits 2 (`USAGE`), not 70 (§4.2.3, §6; spec 0002 §11 Q9).

**Amendment B-510.** After the pre-flight audit of plan 0006: the merged engine asks the ports with `wait=False`, so
the command line gives the page ports the process wait mode (§4.4.5 step 2); a file answer's `by` comes only from
`[engine] engineer` and is refused while it is unset (§4.2.1, AC46, AC64); the inputs of `--template`, the
`basis_ref` of a workflow without required basis fields and the item that carries a sign-off exception's reason are
open (Q22 to Q24).

**Amendment B-536.** First-live-run gaps: the command line builds the host port's model files from the run's input
and catches the port builder's H-G8 refusal (§4.2.2 step 2, AC67, AC68; spec 0002 H-G10 closed), and `report` writes
`report/cycle-timings.json` (AC69).

## 1. Problem

In the sessions behind ADR-0024, more than 20 hours went into interface work while host work stalled, the engineer
asked "is there progress?" about 40 times in one session, and tests failed on the Hijri calendar, cp1256 consoles and
Arabic paths. The engine (spec 0001) can run, pause and resume a workflow, but nobody can start it, see it, answer it
or read what it did. The engineer works through coding agents (ADR-0027), so the approval of a change set must be
something an agent cannot give. Nothing of this exists yet; the first workflow (spec 0007) and acceptance A7 of 18 §5
(at most one engineer prompt per cycle besides the change-set approval and the engineer turn) depend on it.

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| NiceGUI, FastAPI, Flask, Starlette | A web framework and ASGI server for one local page with six routes, no scripts. Deferred to the full UI by ADR-0027; each is a new dependency (A10) | Not used |
| Standard library `http.server` (`ThreadingHTTPServer`) | Enough for a loopback server with a handful of routes; request size, headers and routing are ours to check (§4.4) | Used |
| Jinja2 (autoescape) | Autoescape is the main benefit. A new dependency, a package ADR (A10), and a template-injection class of defects; layouts here are fixed tables and forms | Not used (§4.5, Q1) |
| Standard library `html.escape` with a small builder | Same guarantee through types: only escaped text reaches output (§4.5) | Used |
| `argparse`, `statistics`, `secrets`, `hmac`, `signal`, `subprocess`, `os.startfile` | All needed pieces exist in the standard library. `webbrowser` is not used: it honours the `BROWSER` environment variable, which would let the caller of `run` choose the program that receives the launch address (§4.4.4) | Used |
| Rich, Textual, `tqdm` | Terminal widgets; progress here is one line per event and one live line | Not used |
| `eng-harness` engine (spec 0001) | `JournalReader` already gives every view the progress, page and report need (11 §5); `ProgressSink` and the ports are defined | Used; no second source of truth |
| Contract (`ResultStore`, `Quantity`, `Ref`, kinds) | Results, references and provenance for the report | Used; no logic re-implemented |

No runtime dependency is added: `eng-contract` and `pydantic` only (plus what specs 0002 and 0004 add).

## 3. Acceptance criteria

Test paths are relative to `packages/eng-harness/`. "Fake ports" and "fake-host workflow test" are as in engine §3. The
page tests use a real server on the loopback interface and `http.client`; no browser runs in CI.

### 3.1 Command line

- AC1. Given `eng-harness --help`, then exactly the commands `run`, `resume`, `status`, `stop`, `report` and `doctor`
  are listed; `approve`, `reject`, `sign`, and any abbreviation of a command, are usage errors (exit 2); and no option
  of any command accepts an approval, a rejection, a sign-off or an engineer name. Test:
  `tests/unit/cli/test_parser.py::test_commands_exact_and_no_approve`.
- AC2. Given the modules `eng_harness.cli` and `eng_harness.progress`, then neither imports the answer models or the
  answer-producing functions of `eng_harness.pages`, with one named exception: `cli` may import
  `pages.accept_answers_file` (§4.2.1, AC46), which refuses everything but data inputs; and only `eng_harness.pages`
  constructs `ApprovalAnswer`, `InputAnswer` or `BasisSetupAnswer` (static check of imports and names against an
  allowlist of exactly that one function). Test:
  `tests/rules/test_cli_cannot_answer.py::test_no_answer_construction_outside_pages`.
- AC3. Given each outcome (§4.2.3), then the process exit code is the one in the table: every `RunStatus`, each stop
  reason, `RunRefused`, `RunLocked`, `JournalIntegrityError`, an unknown run, a usage error and an unexpected exception.
  Test: `tests/unit/cli/test_exit_codes.py::test_outcome_mapping`.
- AC4. Given `harness.toml`, then it is found by `--config`, then `ENG_HARNESS_CONFIG`, then `<workspace>/harness.toml`;
  the sections `[engine]`, `[progress]`, `[page]` and `[project_lane]` validate (§4.2.4); an unknown key, a wrong type
  or an out-of-bounds value is a usage error (exit 2) naming the key; the sections of specs 0002, 0003 and 0009
  (`[providers.*]`, validated by AC62) pass through.
  Test: `tests/unit/cli/test_config.py::test_discovery_and_sections`.
- AC5. Given standard output redirected to a pipe whose default encoding is cp1256, when a message holds Arabic text
  and a character cp1256 cannot encode, then nothing raises and the bytes are UTF-8; given a console, the encoding is
  kept and unencodable characters print as backslash escapes. Test:
  `tests/unit/cli/test_encoding.py::test_redirected_output_is_utf8`.
- AC6. Given `run` with an unregistered workflow, an input file that is not valid JSON or fails the workflow's input
  model, a basis with missing required fields, or calcs refused for a production run, then no run folder is created and
  the exit code is 2 (usage) or 3 (refused) as §4.2.3 states, with the paths or codes listed. Test:
  `tests/unit/cli/test_run_refusals.py::test_refusals_create_no_run`.
- AC7. Given a test workflow, fake ports and a confirmed basis, when `run --json` is called and the page client approves
  the one approval, then the process exits 0, the journal ends with `run_completed`, the report file exists, and
  standard output is one JSON object with `run_id`, `workflow`, `status`, `exit_code`, `pending`, `escalation` and
  `report`. Test: `tests/workflow/test_cli_run.py::test_run_completes_and_writes_report`.
- AC8. Given a workflow that reaches an approval, when `run --no-wait` is called, then the page is not served, the
  process exits 10 with the pending request titles and the `resume` command (no address, no token), the journal ends
  with `run_paused`; and a later `resume` without `--no-wait`, answered on the page, completes the run without
  repeating a write. Test: `tests/replay/test_cli_resume.py::test_no_wait_then_resume`.
- AC9. Given a live run in a long fake step, when `stop <run_id>` is called, then the run pauses at the next safe point
  with `run_paused` (reason `stop_requested`), `run` exits 12 and the run process removes the stop file (§4.4.8);
  given a run with no live engine, `stop` exits 0, says it is not running and writes no stop file; given a stop file
  left behind, `resume` removes it at the start of the command, before step 1 of §4.2.2 (§4.4.8). Test:
  `tests/workflow/test_cli_stop.py::test_stop_pauses_at_safe_point` (a fake engine from `CliDeps` that polls
  `FileRunControl`; the real-engine stop is re-checked in plan T17 by
  `tests/workflow/test_cli_stop.py::test_stop_real_engine_pauses_at_safe_point`, B-412). The two removals in `cli/_run.py` are also
  tested by `tests/replay/test_cli_resume.py::test_stop_file_removed_on_return_and_before_resume` (plan T14). That
  `FileRunControl` reaches the real engine's ports is tested by
  `tests/unit/cli/test_production_wiring.py::test_engine_ports_carry_stop_progress_and_cascade` (plan T16b).
- AC10. Given an interrupt signal, then the first one is a stop request (as AC9) and the second ends the process at
  once with exit 130; the journal then resumes as after any crash (engine AC30). While the run id is not yet known or
  its run folder does not exist yet (§4.4.8, B-412), there is no live engine to pause, and the first interrupt ends the
  process as the second does (exit 130, no stop file). Test:
  `tests/unit/cli/test_signals.py::test_first_interrupt_requests_stop` (both cases).
- AC11. Given journals in each state (live, interrupted, paused, needs engineer, completed, failed, altered), when
  `status` runs, then the table and the JSON show the `RunView` status, the step in progress, the pending requests (kind
  and title), the escalation, the heartbeat age and the next command to run; an altered journal exits 5 naming the first
  bad `seq`; an unknown id exits 6; and `status` never writes (journal bytes and modification time unchanged) and never
  prints an address, a token or a launch code. Test: `tests/unit/cli/test_status.py::test_states_and_read_only`.
- AC12. Given `report <run_id>`, then `<run>/report/report.html` is written atomically; `--out FILE` refuses an
  existing file without `--force`; an altered journal gives exit 5 and writes nothing. Test:
  `tests/unit/cli/test_report_command.py::test_output_rules`.
- AC13. Given `doctor`, then it calls `eng_harness.doctor.run` of spec 0002 with the options passed through and returns
  its exit code unchanged. Test: `tests/unit/cli/test_doctor_command.py::test_exit_code_passthrough`.
- AC14. Given a workflow with an `options_model`, then `run` offers one `--<field-name>` option for each top-level
  field of type `str`, `int`, `bool`, enum or `Literal`, and offers none for a field that holds a quantity or a nested
  model: those values come from `--input FILE`, as references or literals (P2). Test:
  `tests/unit/cli/test_options.py::test_generated_options_exclude_quantities`.
- AC62. Given `run` or `resume` and a `harness.toml`, then the `[providers.*]` tables are read once with
  `load_providers_config` (spec 0009 §4.2) in step 1 of §4.2.2, and a table that spec 0009 refuses (its AC1 to AC4) is
  a usage error (exit 2) naming the key, with no run folder, no journal event and no credential-store access; then
  `assemble_decision_runtime` (spec 0009 §4.1, §4.10) is called exactly once, in step 5 of §4.2.2, before
  `Engine.start` or `Engine.resume`, also when no `[providers.*]` table exists, and the `DecisionPort` given to the
  engine is the cascade of spec 0005 built from the returned runtime (its `model`, its `llm` and its
  summary); the runtime's warnings (which include the release findings) are printed to standard error and are not an
  error. Test: `tests/unit/cli/test_decision_wiring.py::test_providers_read_and_runtime_assembled` (with
  `CliDeps` holding a recording assembler).
- AC63. Given a run started through `run` with a runtime whose summary is a known JSON object, then the journal's
  `run_started.decision_runtime` equals that object; given a `resume` after the summary changed (another
  `model_version`), then `run_resumed.decision_runtime` holds the new object; and no journal byte, standard-output or
  standard-error line holds a `base_url`, a `key_ref` or a key. Test:
  `tests/workflow/test_cli_run.py::test_run_header_records_decision_runtime`.
- AC64. Given `run --answers FILE` (B-354), then the file is read and checked to be one JSON object in step 2 of
  §4.2.2, and a file that is missing, not valid JSON or not an object is a usage error (exit 2) with no run folder, as
  is any file while `[engine] engineer` is unset (§4.2.1, B-510);
  given a workflow whose first data request (kind `block`, marker `x-eng-input: data`) opens, then that request, and
  only that one, is answered from the file through `pages.accept_answers_file` (no page is served for it) and the
  journal holds `input_provided` for it with the same `by` as `resume --answers`; an answer that fails the request's
  model is refused by the engine and the request is presented again on the page (or exit 10 with `--no-wait`), and a
  later data request (a re-asked change set) is never answered from the file; approvals, choices and `engine.*`
  requests are never answered from it; given a run that opens no data request, the run outcome is unchanged and one
  warning on standard error says the file was not used. Test:
  `tests/workflow/test_cli_answers.py::test_run_answers_first_data_request`.
- AC65. Given the package `pyproject.toml`, then `[project.scripts]` declares exactly
  `eng-harness = "eng_harness.cli:main"`, `python -m eng_harness --help` prints the usage that `main(["--help"])`
  prints with the program name `eng-harness`, and the workspace root `pyproject.toml` declares no script named
  `eng-harness` (the supported root form is `uv run --package eng-harness eng-harness <command>`, §4.1). Test:
  `tests/unit/cli/test_parser.py::test_entry_point_and_root_form`.
- AC66. Given `run` with the default `CliDeps()` (amendment B-471, Q20 answer A), then the `port_builder` default is
  spec 0002 `build_ports`; the run id (`run_` + ULID from the ids source) is drawn at step 1 of §4.2.2 and the run-id
  cell holds it before any port is built; the engine receives the same id in `RunRequest.run_id` (engine AC70); and
  `run` and `resume` are available. Test: `tests/unit/cli/test_default_deps.py::test_port_builder_bound_and_run_id_drawn`.
- AC67. **[added: B-536]** Given a workflow whose input model has a top-level field annotated `pathlib.Path` and an
  input file that gives it the absolute path of an existing file, when `run` is called, then the port builder receives
  `files` mapping the file's base name to that path; when `resume` is called for that run, then it receives the same
  mapping from the run's stored input, also when the original file has been moved since `run`; and a relative path, a
  missing file or two such fields with one base name ends `run` with exit 2 and no run folder (§4.2.2 step 2). Test:
  `tests/workflow/test_cli_run.py::test_model_files_reach_the_port_builder`.
- AC68. **[added: B-536]** Given a port builder that raises `NotImplementedGap` (spec 0002 AC43, gap H-G8), when `run`
  or `resume` is called, then its message, which names H-G8 and the entries, is printed on standard error, the exit
  code is 2 (`exit_code_for(Outcome.USAGE)`, returned by the command itself), no run folder is created by `run`, and nothing is journaled (§4.2.2 step 2). Test:
  `tests/workflow/test_cli_run.py::test_port_builder_gap_exits_2`.
- AC69. **[added: B-536]** Given `report <run_id>` for a run whose journal holds at least one edit cycle (spec 0007
  §4.9), then after the HTML it writes `<run>/report/cycle-timings.json` by
  `write_cycle_timings(edit_cycle_timings(reader, store), path)`, in the run folder whatever `--out` says; given a run
  without an edit cycle, it writes no such file. Decision (B-536): only the `report` command writes it, not step 6 of
  `run`, because the owner's guide collects it with `report` and one writer keeps one rule. Test:
  `tests/unit/cli/test_report_command.py::test_cycle_timings_file`.

### 3.2 Terminal progress

- AC15. Given the journals of earlier runs of the same workflow in the workspace, then the expected time of a step
  (kind and name) is the median `duration_ms` of its completed instances in the last `history_runs` runs that ended
  `COMPLETED`, shown with the minimum, maximum and sample count, and only when the samples reach `min_samples`;
  otherwise "no estimate". A step that failed or was reconciled contributes nothing. The median lies between the
  minimum and the maximum for any input. Tests: `tests/unit/progress/test_expected.py::test_median_range_and_min_samples`,
  `tests/property/test_expected_bounds.py::test_median_within_range`.
- AC16. Given a fixed event sequence and a fixed clock, then the terminal mode shows one live line (step name, elapsed,
  expected) and one persistent line per finished step, the plain mode shows persistent lines and heartbeat lines only,
  and the JSON mode shows one JSON object per line; the text equals the golden files. Test:
  `tests/golden/test_progress_render.py::test_tty_plain_json`.
- AC17. Given an open approval or input request, then progress shows "waiting for engineer" with the request title and
  the time waited, no expected time, and no address or token. Test:
  `tests/unit/progress/test_render_waiting.py::test_waiting_shows_no_expected_or_url`.
- AC18. Given a running step and a clock that advances without any journal event, then a heartbeat line is printed and
  `<run>/heartbeat.json` is rewritten every `heartbeat_s`; given a live engine whose heartbeat file is older than
  `stale_after_heartbeats` intervals, `status` reports "no heartbeat" with its age. Test:
  `tests/unit/progress/test_heartbeat.py::test_heartbeat_without_events`. The heartbeat's run folder from the run-id cell
  (§4.4.8) is tested by `tests/unit/cli/test_production_wiring.py::test_heartbeat_follows_run_id_cell` (plan T16b).
- AC19. Given an output stream whose writes block, then `emit` returns within 10 ms, the engine is not delayed, and
  when the bounded queue is full the oldest lines are dropped and a count is printed later; the journal stays complete.
  Given a renderer that raises, `emit` raises (the sink does not swallow the failure), so that the engine can detach
  it. Test: `tests/unit/progress/test_sink.py::test_blocked_stream_does_not_block_engine` (the sink alone, no engine).
  The engine half, that a raising sink is detached and the run continues, is engine AC58 (engine plan T18); it is
  re-checked in plan T17 by `tests/workflow/test_progress_detach.py::test_raising_renderer_detached_run_continues`
  (B-412), with `TerminalProgress` installed directly as the real engine's only sink. Through the production wiring the
  fan-out of plan T16b detaches a failing member itself and the engine never sees the failure, so that path is tested
  by plan T16b (`tests/unit/cli/test_production_wiring.py::test_failing_sink_detached_alone`), not here.
- AC20. Given a committed event, then the line is written to the stream in under 200 ms at p95 (11 §10). Test:
  `tests/perf/test_progress_latency.py::test_event_to_line_p95`.
- AC21. Given any string taken from data (a model name, a message, a file name), then terminal output holds no
  C0 or C1 control character, no escape sequence and no bidirectional control character (shown as `<U+XXXX>`). Test:
  `tests/property/test_text_sanitize.py::test_no_control_sequences`.

### 3.3 Approval page: server and security (16 §4, §5)

- AC22. Given a started page server, then its address is `127.0.0.1` and its port is chosen by the operating system
  (two servers get different ports); a request to bind any other address raises; and no source line names `0.0.0.0`,
  `::` or `localhost`. Test: `tests/unit/pages/test_server_bind.py::test_loopback_random_port`.
- AC23. Given the launch address, then its code opens a session once (cookie `eh_<port>_session`, `HttpOnly`,
  `SameSite=Strict`; the name carries the port so that two servers on one host do not overwrite each other) and
  redirects; a second use, a wrong code and a request without the cookie each get 403 with no run data; session and
  launch values have at least 256 bits of randomness and are compared with `hmac.compare_digest`. Test:
  `tests/unit/pages/test_session_token.py::test_launch_code_once`.
- AC24. Given a request whose `Host` is not exactly `127.0.0.1:<port>` (a DNS-rebinding name, `localhost`, another
  port), or a POST whose `Origin` is missing or not `http://127.0.0.1:<port>`, or whose `Sec-Fetch-Site` is present and not
  `same-origin`, then it is refused (421 or 403) before any handler runs; a POST with the right `Origin` and no
  `Sec-Fetch-Site` header (an older browser) passes this check. Test:
  `tests/unit/pages/test_request_checks.py::test_host_origin_fetch_metadata`.
- AC25. Given a POST whose CSRF token is missing, wrong, or issued for another route kind, another request or setup
  id, another bound hash (the preview hash of an approval, the fields-schema hash of an input or choice request, the
  draft hash of a basis setup) or another session, then it is refused (403) and the port and the journal are
  untouched; this holds for each of the three kinds of POST (§4.4.2). Test:
  `tests/unit/pages/test_request_checks.py::test_csrf_bound_to_request_and_hash` (parametrized over the three kinds).
- AC26. Given every screen and error page, then each response carries the headers of §4.4.2 (the exact
  Content-Security-Policy included) and the markup holds no `script` element, no event-handler attribute, no `style`
  attribute, no `iframe`, `object`, `embed`, `link` or `img`, and no URL that is not a relative path of this server.
  Test: `tests/unit/pages/test_headers_and_markup.py::test_csp_and_no_active_content`.
- AC27. Given the route table of §4.4.3, then any other path is 404, any other method 405, a body over `max_body_bytes`
  413, a content type other than `application/x-www-form-urlencoded` 415, and an unknown or repeated form field 400.
  Test: `tests/unit/pages/test_routes.py::test_route_table_and_limits`.
- AC28. Given `max_failed_requests` refused requests (token, Host, Origin, CSRF), then the server answers 503 to every
  request and prints a warning; given the run function returns, the server and its threads stop and the port is free.
    Tests: `tests/unit/pages/test_lockdown.py::test_failed_requests_lock_server`,
  `::test_shutdown_releases_port`.
- AC61. Given a run that serves the page, then the launch address is opened by an opener that ignores the `BROWSER`
  environment variable (the child process environment has it removed) and is never written to standard output,
  standard error, a log, `status` output or the journal: when the opener fails, or with `--no-browser`, it is written
  only to the controlling terminal (`/dev/tty`, `CONOUT$`), and when there is none the process says that the address
  cannot be shown and that the run should be started from a terminal or with `--no-wait`. Tests:
  `tests/unit/cli/test_opener.py::test_browser_variable_ignored`,
  `tests/workflow/test_launch_address.py::test_address_never_on_stdout_or_stderr` (stderr redirected, opener failing,
  no controlling terminal: the code appears on neither stream).


### 3.4 Approval flow (11 §3, 18 step 6)

- AC29. Given an open `CHANGE_SET` request, when the engineer approves on the page, then the engine receives an
  `ApprovalAnswer` whose `shown_sha256` equals the request's and journals `approval_resolved` (`by` =
  `engineer:<name>`); given a form whose hash differs from the open request, then 409 and the request is shown again.
  Test: `tests/workflow/test_page_approval.py::test_answer_bound_to_hash`.
- AC30. Given two simultaneous answers to one request, then exactly one is accepted, the other gets 409, and the
  journal holds one `approval_resolved`. Test: `tests/unit/pages/test_single_use.py::test_concurrent_answers_one_wins`.
- AC31. Given an answer, then: a rejection needs a reason of 1 to 500 characters after trimming; each rejected item
  needs its own reason; an approval that rejects every item is refused ("use reject"); an item id not in the request
  is refused; and every refusal re-renders the screen with the message and records nothing. Test:
  `tests/unit/pages/test_answer_validation.py::test_reasons_and_items`.
- AC32. Given the answer models, then they hold only `request_id`, `shown_sha256`, `decision` or `choices` (option
  ids), `rejected_items`, `item_reasons`, `reason`, `by`, `acknowledged_unreleased` and `confirmed_sections`; they have
  no member that carries an engineering value, and extra members are refused. Test:
  `tests/unit/pages/test_answer_models.py::test_answers_carry_no_values`.
- AC33. Given a three-item change set in which item 2 is rejected on the page, then the journal records
  `rejected_items = [item 2]` with its reason, the writes of items 1 and 3 proceed, and the write of item 2 raises
  `BlockRuleViolation` (engine AC56). Test: `tests/workflow/test_page_approval.py::test_per_item_reject_end_to_end`.
- AC34. Given an approved change set whose model changed (the fake host is edited) after the answer and before the first
  write, then `ApprovalVoid` is raised before the write (engine AC55), nothing is written, and the page shows the
  request as voided with the engine's message. Test: `tests/workflow/test_page_approval.py::test_void_after_model_change`
  (plan T17, real engine). The page half (§4.4.5: a `step_failed` with code `APPROVAL_VOID` marks the approved request
  voided) is tested by `tests/unit/pages/test_void.py::test_void_shown_on_resolved_request` (plan T7b, B-412).
- AC35. Given a run waiting at an approval whose process is killed, when it is resumed, then the same request id with
  the same preview hash is shown again, an answer completes the run, and no `approval_resolved` exists for the killed
  wait. Test: `tests/replay/test_page_resume.py::test_kill_while_waiting_then_resume`.
- AC36. Given `answer(wait=True)` and a stop request, then it returns `None` within 1 second; given `wait=False` and no
  answer, it returns `None` at once. Test: `tests/unit/pages/test_wait.py::test_stop_ends_wait`.
- AC37. Given an accepted POST, then the page shows "recorded" only after the sink has seen the matching
  `approval_resolved` event, and shows "received, not yet recorded" with a link to `/` after `ack_timeout_s`. Test:
  `tests/workflow/test_page_approval.py::test_page_confirms_after_commit`. That the page server's sink receives the
  events through the fan-out of the production wiring, isolated from a failing member, is tested by
  `tests/unit/cli/test_production_wiring.py::test_failing_sink_detached_alone` (plan T16b).
- AC38. Given several open requests (parallel children), then `/` lists them in `seq` order and each is answered on its
  own page. Test: `tests/unit/pages/test_index.py::test_multiple_open_requests`.
- AC39. Given the engineer name, then it is 1 to 100 characters without control characters, defaults to
  `[engine] engineer` when set, is remembered for the session, and is never taken from the operating system account
  (the test makes `getpass.getuser` raise). Test:
  `tests/unit/pages/test_answer_validation.py::test_name_rules_and_no_os_account`.

### 3.5 Screens

- AC40. Given a `CHANGE_SET` request with a difference report, then the screen shows the title, the items with their
  labels and referenced values, the differences from the last revision as a table, the binding (model id, revision,
  fingerprint and file hash, shortened) and the short preview hash, one reject box per item, and the buttons Approve and
  Reject; it matches the snapshot. Test: `tests/golden/test_screens.py::test_change_set_screen`.
- AC41. Given `PROMOTION` and `INFO` requests, then the screens show the target and the backup by base name, the hash of
  the original and of the working copy, and the same buttons; they match the snapshots. Test:
  `tests/golden/test_screens.py::test_promotion_and_info_screens`.
- AC42. Given a `SIGN_OFF` request, then the screen shows the report of the run so far (marked DRAFT) at `/report`, the
  verdict counts, each verdict that is not `PASS` or `NOT_APPLICABLE` as an exception with its own reason field, and
  the engineer name; signing is refused unless every exception has a reason; and when results depend on unreleased
  tools (§4.6.3) the screen lists them and signing is refused without the acknowledgement. Test:
  `tests/workflow/test_signoff.py::test_signoff_rules`.
- AC43. Given the engineer-turn request of the edit cycle (18 step 15) with the options `accept`, `more_edits` and
  `hand_edit`, then the screen shows exactly three buttons with the catalog labels, the `hand_edit` label tells the
  engineer to save in the host program first, and one press is one answer that carries only the option id. Test:
  `tests/unit/pages/test_choice_screen.py::test_engineer_turn_three_options`.
- AC44. Given a batched decision with N questions, then the screen is one form with one option group and its labeled
  evidence per question and one Submit; an answer with a question left open or an option outside the question is
  refused; the answer carries N option ids. Test:
  `tests/unit/pages/test_choice_screen.py::test_batched_decisions_one_submit`.
- AC45. Given the engine's own requests (`engine.in_flight`, `engine.host_state`, `engine.escalation`), then they are
  choice screens showing the reason and the evidence, and they can be answered only there (the file path refuses them, AC46). Test:
  `tests/unit/pages/test_choice_screen.py::test_engine_requests_choices`.
- AC46. Given a `ctx.ask` data request (schema marker `x-eng-input: data`, §4.4.6), then the page shows its fields
  (name, type, unit, bounds) read-only with the text "provide the answers with `resume --answers FILE`"; given such a
  file, `pages.accept_answers_file` builds the `InputAnswer`, the engine validates it (engine AC61) and journals
  `input_provided` with `by` = `engineer:<name>` (`<name>` from `[engine] engineer`; while it is unset the file is
  refused with exit 2 and nothing journaled, §4.2.1, B-510). The file path refuses, with exit 2 and nothing journaled: an answer for
  an unknown request id; a request that is not of kind `block`; any request whose id starts with `engine.`
  (`engine.in_flight`, `engine.host_state`, `engine.escalation`); and every request whose schema does not carry
  `x-eng-input: data`, which includes the engineer turn and batched decisions (choice requests, marker `choice` or no
  marker). Tests: `tests/workflow/test_cli_answers.py::test_form_request_answers_file`,
  `tests/unit/pages/test_answers_file.py::test_file_refuses_choice_engine_and_unmarked_requests` (an answers file for
  the engineer turn, a batched decision and `engine.in_flight` is refused and the journal bytes are unchanged).
- AC47. Given a basis draft with every required field present, when `run` is called, then the page shows the sections
  and rows of the `BasisSetupView` (value, unit, source, citation, state, bounds, banners); a confirmable section has a
  box, a section with a missing row has none; confirming all sections with a name freezes the basis (spec 0004) and
  starts the run; an answer whose `draft_sha256` is not that of the draft currently shown is refused (409) before
  `freeze`; rejecting with a reason ends with exit 3, no run folder and no stored basis. The answer and the
  setup log `<workspace>/setups/<setup_id>.json` hold `by`, `at`, `draft_sha256` and the section names, never a value.
  Given `run --no-wait` for a workflow with required basis fields (B-354), then no page is served, the process exits
  10 saying that the basis is confirmed only by a `run` started without `--no-wait`, and no run folder, journal, setup
  log or stored basis exists.
    Tests: `tests/workflow/test_cli_basis.py::test_basis_confirmation_flow`, `::test_reject_leaves_no_run`,
  `::test_stale_draft_hash_refused`, `::test_no_wait_basis_exits_10_nothing_stored`.

### 3.6 Untrusted text

- AC48. Given adversarial strings (markup, quotes, `javascript:` text, `</style>`, bidirectional overrides, escape
  sequences, NUL, a 10 MB string, Arabic text mixed with digits) in every text field of the journal, of result
  payloads and of previews, then on every screen and in the report the text appears only escaped, inside a labeled
  field, wrapped in `<bdi dir="auto">`, with bidirectional controls shown as `<U+XXXX>`, truncated at
  `display_max_chars` with the original length stated; parsing the output finds only allowlisted tags and attributes
  and text nodes equal to the escaped input. Test: `tests/property/test_untrusted_text.py::test_every_screen_and_report_escape`.
- AC49. Given the HTML builder, then an attribute accepts only a `SafeToken` (`[A-Za-z0-9_.-]{1,64}`) or an enumerated
  value, a data string is never placed in an attribute, a URL, a class name, an id or a style, and passing one raises.
  Test: `tests/unit/test_html.py::test_attributes_accept_only_tokens`.

### 3.7 Run report (ADR-0027 §1, 14 §6, ADR-0026 §3)

- AC50. Given `build_report(reader, store, marks, clock, version)`, then it reads nothing else (the module imports no
  file or process module and a test with every other file made unreadable passes) and the same inputs give the same
  bytes. Test: `tests/unit/report/test_build_report.py::test_inputs_only_and_deterministic`.
- AC51. Given a fixture run (two revisions, a change set with a rejected item, verdicts, decisions, a resume), then the
  report holds the sections of §4.6.1 and matches the snapshot. Test:
  `tests/golden/test_report.py::test_report_snapshot`.
- AC52. Given any report, then every value cell (class `v`) holds a link to a row of the sources table (result id and
  pointer, kind, producer and version, or the basis `source` string with its confirmation) through an in-page
  fragment link (`href="#src-N"`), and the link target exists.
  Test: `tests/unit/report/test_sources.py::test_every_value_has_source`.
- AC53. Given a run without `signed_off`, then the report carries the mark DRAFT (banner, title prefix, watermark);
  given `signed_off`, the banner shows the name and time and the unsigned mark is gone; given `run_completed.draft`
  true, "DRAFT SOURCES" stays after signing; given a run that is not terminal, "INCOMPLETE" shows with its status.
  Test: `tests/unit/report/test_draft_mark.py::test_draft_signed_and_sources`.
- AC54. Given release marks that name a tool, then every result produced by it, and every result with such a result
  among its ancestors (through `parents` and provenance inputs), carries the mark in every place it appears, the
  banner counts them, and the sign-off screen lists the same set; a result with no such ancestor carries none; a
  lineage deeper than `lineage_depth_limit` is marked and flagged "lineage incomplete". Tests:
  `tests/property/test_release_marks.py::test_marked_set_is_closure`,
  `tests/unit/report/test_release_marks.py::test_marks_everywhere`.
- AC55. Given change-set approvals, then the changes section shows per approval the items with accepted or rejected
  state and reason, the binding, the applied steps and their read-back results, the differences (engineer changes
  included), and the list of model revisions with fingerprints and base file names. Test:
  `tests/unit/report/test_changes.py::test_changes_decisions_revisions`.
- AC56. Given the events of a run, then the timings section gives for each step its start and duration, the time the
  engineer waited (the sum of `approval_resolved.at - approval_requested.at` and the same for inputs), the machine
  time (the sum of completed step durations) and the number of resumes, counted as distinct `resume_no` values (a
  restore appends a second `run_resumed` with the same `resume_no`, engine Q26); the sums equal the sums over the
  fixture. Test:
  `tests/unit/report/test_timings.py::test_wait_and_run_times`.
- AC57. Given an altered journal, then no report is built (`JournalIntegrityError`); given a live engine, the report
  states "run in progress as of seq N". Test: `tests/unit/report/test_build_report.py::test_tampered_refused_live_banner`.
- AC58. Given any output (progress, page, report, setup log, JSON), then dates read `YYYY-MM-DD HH:MM:SS UTC` in the
  Gregorian calendar, digits are ASCII and the decimal separator is a point, whatever the locale or calendar; no
  module of this spec imports `locale` or uses a locale-dependent time directive. On Windows the same holds with an
  Arabic workspace path, a cp1256 console and the `ar-SA` culture. Tests:
  `tests/rules/test_culture_invariant.py::test_no_locale_calls`,
  `tests/windows/test_arabic_environment.py::test_arabic_workspace_and_cp1256`.
- AC59. Given a report or setup log, then the file is UTF-8 without a byte order mark, with LF line endings, declares
  `<meta charset="utf-8">`, is written to a temporary name and renamed, and Arabic text round-trips. Test:
  `tests/unit/report/test_write.py::test_utf8_lf_atomic`.
- AC60. Given the modules of this spec, then they import only the standard library, `eng_contract`, `pydantic` and the
  modules of this package (specs 0002 to 0005 where they own the type). Test:
  `tests/rules/test_imports.py::test_third_party_imports_limited`.

## 4. Design

### 4.1 Package layout and public API

`packages/eng-harness/src/eng_harness/`, extending engine §4.1.1. New public modules go in
`[tool.eng-gate] public_modules`; block and rule code may import none of them (engine §4.1.2).

| Module | Public names | Who may import |
|---|---|---|
| `eng_harness.cli` | `main(argv, *, deps) -> int`, `ExitCode`, `CliDeps`, `HarnessConfig`, `ConfigError` | the entry point, tests |
| `eng_harness.progress` | `ExpectedTimes`, `ProgressRenderer`, `TerminalProgress` (the `ProgressSink`), `Heartbeat`, `Liveness`, `read_liveness` | `cli`, tests |
| `eng_harness.pages` | `PageServer`, `PageApprovalPort`, `PageInputPort`, `PageBasisSetupPort`, `Screen`, `accept_answers_file` | `cli` (only `PageServer`, the ports and `accept_answers_file`, AC2), tests |
| `eng_harness.report` | `build_report`, `write_report`, `ReleaseMarks`, `unreleased_dependencies`, `ReportError`, `edit_cycle_timings` and `write_cycle_timings` (spec 0007 §4.9; amendment B-536) | `cli`, `pages` (sign-off screen), tests |

Internal modules: `_text.py` (sanitizing, durations, timestamps, numbers), `_html.py` (§4.5), `cli/_parser.py`,
`_exit.py`, `_config.py`, `_encoding.py`, `_opener.py` (launch-address opener and terminal writer, §4.4.4), `_options.py`,
`_run.py`, `_status.py`, `_stop.py` (the `stop` command), `_signals.py`, `_control.py` (the stop-file protocol,
`FileRunControl`), `_wiring.py`; `progress/_expected.py`, `_render.py`, `_sink.py`, `_heartbeat.py`; `pages/_security.py`, `_server.py`,
`_routes.py`, `_answers.py` (answer models, `ApprovalSubmission`, checks), `_answers_file.py` (`accept_answers_file`), `_ports.py`, `_wait.py`, `_screens_approval.py`, `_screens_choice.py`,
`_screens_basis.py`, `_labels.py` (the label catalog), `_css.py`; `report/_lineage.py`, `_model.py`, `_sections.py`, `_document.py`, `_write.py`. The
`pages/` folder holds the path-risk floor r3 (`.gate/risk-map.yml`), which is why this spec's plan is r3 throughout.
The entry point is `[project.scripts] eng-harness = "eng_harness.cli:main"` and `python -m eng_harness`. `main`
takes its collaborators in `CliDeps` (registry, port factories, clock, ids, streams, launch-address opener, decision-runtime
assembler: `eng_harness.providers.assemble_decision_runtime` by default, AC62; the decision-port factory that builds the
cascade of spec 0005 from the assembled runtime, `decision_port_factory`, B-412), so every test
runs without a host, a browser or the real clock. A collaborator whose real implementation has not merged is an
optional field that defaults to `None` until it does (so `CliDeps()` still builds); a command whose collaborators are
not all set stays "not available in this build" (exit 2), and no stub stands in for the missing implementation;
plan T18a and T18b bind every such default once the real implementations have merged, while a collaborator already merged when
its field is added (the engine factory, `freeze`) gets its default in that task (plan §3, B-412).

**Invocation from the workspace root (B-354).** The one supported form is
`uv run --package eng-harness eng-harness <command> [options]`, run in the workspace root. The root project
`eng-platform` is not installed (`[tool.uv] package = false`) and does not depend on its members, so a plain
`uv sync` there installs the root's dependencies and `dev` group only and, being an exact sync, removes members an
earlier command installed; `uv run eng-harness` then fails with "Failed to spawn". `--package eng-harness` makes
`uv run` sync and run in the `eng-harness` member, which installs it with its entry point whatever was synced before
(checked with uv 0.11 on this workspace's `eng-gate`, which behaves the same way; Q18). `uv run --package eng-harness
python -m eng_harness` is the equivalent module form. No change to the root `pyproject.toml` is needed (AC65); the
package's `[project.scripts]` entry is plan T3's.

### 4.2 Command line

#### 4.2.1 Commands

Global options: `--workspace DIR` (absolute; overrides `ENG_WORKSPACE`, contract §4.5.1), `--config FILE`.

| Command | Purpose and options |
|---|---|
| `run <workflow>` | Start a run. `--input FILE` (JSON, the workflow input; values may be `$ref`), `--basis FILE` (the values file, spec 0004 §4.4), `--template NAME[@VERSION]` **[added]**, `--mode {work_on_copy,approve_each_write,autonomous_logged}` (default `[engine] default_mode`), `--run-class {trial,production}` (spec 0003 §4; default `production`, Q7), `--answers FILE` (B-354, AC64: the bare JSON object of one answer, given to the first `ctx.ask` data request the run opens; the keyed form of `resume` is not taken, because request ids depend on the run id), generated `--<field>` options (AC14), and the shared options below |
| `resume <run_id>` | Replay and continue (engine §4.5.1). `--answers FILE` answers pending `ctx.ask` data requests only (AC46), as JSON `{"<request_id>": {...}}`, or the bare object when exactly one data request is pending; and the shared options |
| `status [<run_id>]` | Without an id: the 20 most recent runs. With an id: AC11. `--json`. Read-only |
| `stop <run_id>` | Ask a live run to pause at the next safe point (`--wait SECONDS` waits for it to end) |
| `report <run_id>` | Build the report (§4.6). `--out FILE`, `--force`. Also writes `<run>/report/cycle-timings.json` (spec 0007 §4.9; AC69) |
| `doctor` | Spec 0002 §4.9 (`--json`, `--show-paths`) |

Shared options of `run` and `resume`: `--no-wait` (never wait for an answer: exit 10 at the first open request),
`--wait-timeout SECONDS` (default: wait until answered or stopped), `--no-browser` (do not open the page; show the launch address on the
controlling terminal only, §4.4.4), `--progress {auto,tty,plain,json,off}` (default `auto`: `tty` on a terminal, else `plain`),
`--json` (the final result as one JSON object on standard output; progress goes to standard error), `--no-report`,
`--task ID` (amendment B-478: links the run to an open task log, default `ENG_TASK_ID`, then the open task of
`.eng/tasklog/current.json`; with `[tasklog] require_task = true` a `run` without an open task is refused with exit 2
before any run folder; ignored without a `[tasklog]` section; a top-level options-model field named `task` is refused
at option generation; [spec 0015](0015-task-log.md) §4.5.3, AC28, AC36). AC1's six commands are unchanged.

**There is no approve command, no option that answers a request, and no file that approves.** Approval, rejection,
per-item rejection and sign-off exist only on the page (ADR-0027 §2). An agent that runs a workflow can start, resume,
stop and inspect it, and read the report; it cannot give the answer (AC1, AC2). Input values for `ctx.ask` data requests and the
basis values arrive as files, because they are data; their confirmation by the engineer happens at the change-set
approval and on the basis screen (Q3). **`--answers` cannot decide anything.** `run` and `resume` turn the file into
an `InputAnswer` only through `pages.accept_answers_file(request, payload, by)`, which accepts a request only if it is of
kind `block`, its id does not start with `engine.`, and its schema carries the marker `x-eng-input: data` (the marker
`ctx.ask` sets and the choice helpers never set, §4.4.6). The engineer turn, batched decisions and the engine's own
requests are choices and can only be answered on the page; any other request is refused with exit 2 and nothing is
journaled (AC46). The answer's `by` is `engineer:<name>`, `<name>` being the `[engine] engineer` setting: no option
names an engineer (AC1), the operating-system account is never used (AC39) and a file serves no page, so while the
setting is unset `run --answers` and `resume --answers` are refused with exit 2 and a message naming
`[engine] engineer`, before any run folder is created and with nothing journaled (B-510). For `run`, the CLI holds the file's object and wraps the page `InputPort`: the first `present` of a
data request is answered from it once through `pages.accept_answers_file`; every other request, a later data request
included, goes to the page port unchanged (AC64).

Rule for coding agents, recorded in the package `AGENTS.md` (plan T17b): run `run` and `resume` in the background and
follow them with `status`, or use `--no-wait` and tell the engineer to resume (a `run` that needs basis confirmation is
started by the engineer without `--no-wait`, §4.4.7); never read or relay the launch address
or open the page; the approval is the engineer's. The rule is generated into the package
`AGENTS.md` from `packages/eng-harness/.gate/agents.yml`.

#### 4.2.2 Flow of `run`

1. Resolve the workspace and configuration (including `[providers.*]` through `load_providers_config` of spec 0009
   §4.2, AC62); for `run`, draw the run id (`run_` + ULID from the ids source) and fill the run-id cell (§4.4.8,
   Q20); build the registry from `CliDeps`; find the workflow (`RunRefused`-like refusal otherwise). The
   ports (built at the end of step 2) take no basis: the CSI host port reads the read-back tolerance from the basis frozen at step 3, through the
   run header, when its first check runs (spec 0002 §4.5.8, AC44; amendment B-503), so neither `run` nor `resume`
   passes it.
2. Validate the input file against the workflow's input model, without creating anything (engine AC16). Read the
   `--answers` file, if given, and check that it is one JSON object (AC64); its fields are checked by the engine when
   the request opens. Then build the tool and host ports as
   `port_builder(config, workspace, store, run_folder, clock, ids, files)` (amendment B-536, AC67): `files` maps a
   model key to a file for each top-level field of the workflow's input model annotated `pathlib.Path` (a model file);
   the key is the file's base name and the file is the field's value, which must be absolute and name an existing
   file. A relative path, a missing file or two such fields with one base name is a usage error (exit 2) with no run
   folder; these refusals apply to `run`. `resume` builds `files` from the run's stored input and does not check that
   the files still exist. Decision (B-536): `resume` passes a moved original on unchecked, because once the working
   copy exists the host port works on the copy in the run folder and never reads the original again (spec 0002 §4.5.9
   `working_copy`); a run that stopped before its copy existed meets `NOT_FOUND` at `working_copy`, as today. A
   `NotImplementedGap` from the port builder (spec 0002 AC43, gap H-G8) is printed on standard error and ends the
   command with `exit_code_for(Outcome.USAGE)` (2), before any run folder and with nothing journaled (AC68). Decision
   (B-536): the command returns the usage exit itself rather than through `exit_code_for_error`, because the merged
   error-code table maps `NOT_IMPLEMENTED` only once servers plan T19a adds it. Decision (B-536): the
   command line builds `files`, because only it holds the file's path at `run` and at `resume`. Decision (B-536): a
   model file is written in `--input` as its absolute path, not as a `harness.file_input/1` reference, because a
   reference holds only the base name, hash and size, from which no component can find the file, while the path is
   kept in the run's input for `resume`. Decision (B-536): the model key is the base name, because the journal records
   base names of model files only (engine §4.4.2 `model_saved`) and the workflow can derive it from its input.
3. If the workflow declares required basis fields: build the draft from `--template` and `--basis` (spec 0004
   `build_draft`; the template folders and the version rule are Q22, and the `basis_ref` of a workflow without
   required basis fields is Q23). If a required field is missing, print the paths and exit 3 without serving a page. Otherwise show the
   basis confirmation screen (§4.4.7), wait, then `freeze`. This happens before a run exists; nothing is journaled.
4. Production run class: `HarnessCalcPort.preflight`; a refusal lists the calcs and exits 3. The calc port is built
   with the run's store, the run class (`--run-class` for `run`; for `resume` the run header's `run_class`, read before
   `Engine.resume`), the clock and the ids; the calc registry, the approvals file of spec 0003 (`src/eng_harness/calcs/approvals.yaml`) and the calc
   settings are those of spec 0003 §4.12 (B-412), and so is its `basis_fields` map (spec 0007 §4.5; amendment B-498).
5. Build the decision layer: call `assemble_decision_runtime` (spec 0009 §4.1, §4.10) with the `ProvidersConfig`, the
   `DecisionSettings` (spec 0005 §4.3, read from `[decisions]`; Q15), the workspace and the point policies its release
   check needs (Q16), print its `warnings` (which include the release findings) to standard error, and build the
   cascade of spec 0005 from the returned runtime (`model`, `llm` and `summary`; spec 0009 §4.1; the cascade reads
   released points from the `DecisionSettings` it is given, spec 0005 §4.3) as the `DecisionPort`; the cascade hands the summary to the engine for the run header (spec 0005 §4.12, engine
   AC69; AC62, AC63). Install `TerminalProgress` as the `ProgressSink` (and the page server as a second sink for
   AC37), `FileRunControl` as the `RunControlPort`, the page ports as `ApprovalPort` and `InputPort`, and start
   `Engine.start` with the run id of step 1 in `RunRequest.run_id`.
6. On return, write the report (unless `--no-report`), print the summary, map the outcome to the exit code.

`resume` is steps 1, 5 and 6 with `Engine.resume`, building its ports after step 1 by the rule of step 2 from the
run's input (the run header's `input_ref`, read before `Engine.resume` as step 4 reads `run_class`; AC67); it removes a stale stop file first, at the start of the command, before step 1 (§4.4.8). The page server starts lazily at
the first `present` (never when `--no-wait` is given or no request opens) and stops when the process returns.

#### 4.2.3 Exit codes

| Code | Name | When |
|---|---|---|
| 0 | `OK` | Run completed; `status`, `stop`, `report` succeeded |
| 1 | `RUN_FAILED` | The run ended `FAILED`; `doctor` reported a failed check (spec 0002 AC37) |
| 2 | `USAGE` | Usage or configuration error; invalid input file; a configuration this build cannot serve (`[cli_tools.*]` entries before servers plan T19b, spec 0002 AC43, gap H-G8; owner answer of 2026-11-14, B-495) |
| 3 | `REFUSED` | `RunRefused` (`BASIS_INCOMPLETE`, `SERVER_CHECK_FAILED`), unknown workflow, calcs refused, basis rejected on the page |
| 4 | `RUN_LOCKED` | Another process holds the run (`RunLocked`) |
| 5 | `JOURNAL_INTEGRITY` | `JournalIntegrityError` |
| 6 | `NOT_FOUND` | No such run |
| 10 | `AWAITING_ENGINEER` | Paused at an open approval or input, or basis confirmation pending with `--no-wait` |
| 11 | `NEEDS_ENGINEER` | Escalated (`NEEDS_ENGINEER`): the page shows the choices |
| 12 | `STOPPED` | Paused by a stop request |
| 70 | `INTERNAL` | Unexpected exception; the message names an error id; the journal is intact and resumable |
| 130 | `INTERRUPTED` | Second interrupt; or a first interrupt before the run folder exists (AC10, §4.4.8) |

#### 4.2.4 Configuration

`harness.toml` sections owned here. All are software settings (not engineering values); unknown keys are refused.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `[engine] default_mode` | enum | `work_on_copy` | Permission mode (11 §7) |
| `[engine] engineer` | str, 1 to 100 | unset | Name proposed on the page; never an operating-system account |
| `[engine]` limits | int ≥ 1 | engine §4.10 | `EngineSettings` fields |
| `[progress] heartbeat_s` | int ≥ 1 | 10 | Heartbeat interval |
| `[progress] stale_after_heartbeats` | int ≥ 2 | 3 | Heartbeat age after which `status` says "no heartbeat" |
| `[progress] history_runs` | int ≥ 1 | 20 | Earlier runs read for expected times |
| `[progress] min_samples` | int ≥ 1 | 3 | Samples needed for an estimate |
| `[progress] queue_lines` | int ≥ 1 | 1000 | Bounded output queue |
| `[page] open_browser` | bool | true | Open the launch address in the default browser |
| `[page] max_body_bytes` | int | 32768 | POST body limit |
| `[page] max_failed_requests` | int | 20 | Lockdown threshold (AC28) |
| `[page] ack_timeout_s` | int | 10 | AC37 |
| `[page] display_max_chars` | int | 500 | Truncation of untrusted text (AC48) |
| `[providers.decision]`, `[providers.llm]` | tables | absent (no providers, phase 1 behavior) | Owned by spec 0009 §4.2, not by this spec: passed to `load_providers_config`, whose refusal is a usage error naming the key (AC62); no key for a secret exists |
| `[decisions]`, `[decisions.shadow_released.<point>]` | tables | absent (the `DecisionSettings` defaults, phase 1 behavior) | Owned by spec 0005 §4.3, not by this spec: passed through as `DecisionSettings` (Q15, amendment B-471) |
| `[project_lane.<tool>] record` | str | none | A tool not yet released (ADR-0026 §3); `record` names its gap report or session record (Q5) |
| `[tasklog]` (`worktree`, `integration_branch`, `policy`, `agent`, `require_task`, `since`) | table | absent (nothing logged, pushed or refused; tests and CI) | Amendment B-478: owned by [spec 0015](0015-task-log.md) §4.6, which validates it; `integration_branch`, `policy` and `require_task` are required when the table exists; there is no `push` key (the push permission lives only in a user-level file outside the repository, ADR-0034 D6) |

### 4.3 Terminal progress (ADR-0027 §1, 11 §10, notes A7 and A8)

**Sink.** `TerminalProgress.emit(event)` formats the event (microseconds, no I/O) and puts the text on a bounded queue
that a writer thread drains to standard error; when the queue is full the oldest line is dropped and counted. `emit`
therefore never blocks, whatever the consumer does (an agent that stops reading its pipe must not stall a run). The
journal stays complete; a dropped line is a display loss only (engine §4.10).

**Display.** From the events: the current step (path, name, kind; at most three running steps are shown with "+N more"),
its elapsed time, its expected time, and the run's elapsed time. `terminal` mode keeps one live line, rewritten with a
carriage return and an erase sequence, plus a persistent line for each finished step, decision, approval, input,
`model_saved`, escalation and run event. `plain` mode prints persistent lines and heartbeat lines only. `json` mode
prints `{"at", "event", "path", "name", "elapsed_ms", "expected_ms"}` per line. Durations read `MM:SS`, or `H:MM:SS`
from one hour, by integer arithmetic. Data-derived text goes through `sanitize_terminal` (AC21).

**Expected time.** `ExpectedTimes.build(workspace, workflow, settings)` reads, read-only through `JournalReader`, the
last `history_runs` runs of the workflow that ended `COMPLETED`, and keys durations by `(kind, name)` (for tool steps the
tool name). Inserted and housekeeping steps are included under their names. The estimate is the median
(`statistics.median`) with minimum, maximum and count, shown only from `min_samples` samples:
`expected ~02:10 (01:05 to 04:40, 7 earlier runs)`. Otherwise `no estimate`. The same workflow on a larger model takes
longer, which is why the range is always shown. The index is built once before the engine starts; display lookups are
dictionary reads.

**Heartbeat.** An asyncio task in the run process (not a thread, so a stalled event loop stops it) wakes every
`heartbeat_s`, prints `heartbeat: <step> still running, <elapsed>, <expected>, journal seq N`, and rewrites
`<run>/heartbeat.json` (`pid`, `at`, `step`, `step_started_at`, `seq`) by temporary file and rename. The run folder
is read at each beat from the run-id cell of §4.4.8 (B-412); while the cell is empty or the folder does not exist yet,
the beat prints its line and writes no file, and it never creates the folder. The file is
process information, not a journal event: the journal has one writer and is not the place for liveness. `status` combines
`journal.is_locked`, the file and its age (`read_liveness`): locked and fresh is "running"; locked and older than
`stale_after_heartbeats` intervals is "no heartbeat, possibly stuck"; not locked is the `RunView` status
(`INTERRUPTED` for a non-terminal run). Nothing here terminates a worker; silence handling of servers belongs to
spec 0002 (timeouts, Job Objects).

**Waiting.** An open request shows `waiting for engineer: <title>, <elapsed waiting>` and no expected time. The
launch address is never part of progress output (§4.4.4).

### 4.4 The approval page

One `PageServer` per `run` or `resume` process serves the run's open requests. It lives only while that process lives;
the durable parts of a wait are the journaled request and the replay (§4.4.5).

#### 4.4.1 Server

- `ThreadingHTTPServer` bound to `("127.0.0.1", 0)`; after binding the address is checked to be `127.0.0.1`. HTTP/1.0
  style (`Connection: close`), a socket timeout per request, daemon threads.
- On start the server draws a launch code, a session secret and a CSRF key (`secrets.token_urlsafe(32)` each). The
  launch address is `http://127.0.0.1:<port>/launch?code=<code>`. `GET /launch` with the right code, once, sets the
  session cookie `eh_<port>_session` (`HttpOnly; SameSite=Strict; Path=/`; no `Secure` because the origin is plain
  HTTP on loopback) and redirects to `/`. Browsers scope cookies by host and not by port, so the name carries the port:
  two servers on `127.0.0.1` (two runs being resumed) do not overwrite each other's cookie. The server accepts only
  the cookie of its own name. A second use is 403.
- Handler threads never touch the engine directly. They validate a request, then pass the result to the engine's event
  loop with `loop.call_soon_threadsafe` and wait for the matching future.

#### 4.4.2 Checks and headers

Every request, in this order, before any handler: `Host` equals `127.0.0.1:<port>`; for POST, `Origin` is required and equals
`http://127.0.0.1:<port>`, and `Sec-Fetch-Site`, when present, is `same-origin` (when absent the `Origin` check alone
decides); the session cookie matches (except for `/launch`); for POST, the CSRF token matches. A failure counts toward
`max_failed_requests`. The CSRF token is `HMAC-SHA256(csrf_key, route + "\n" + subject_id + "\n" + bound_sha256 + "\n"
+ session_id)`, rendered into the form, with these inputs per POST route:

| POST | `route` | `subject_id` | `bound_sha256` |
|---|---|---|---|
| `/answer/<request_id>`, approval request | `approval` | `request_id` | the request's `shown_sha256` |
| `/answer/<request_id>`, input or choice request | `choice` | `request_id` | the request's `fields_schema_sha256` (the journaled schema, which holds the options and the evidence shown) |
| `/setup/<setup_id>` | `setup` | `setup_id` | the `draft_sha256` of the draft rendered |

A token is therefore valid for one route kind, one request or setup, one rendered content and one session. The handler
also compares the answer's own hash member (`shown_sha256`; `draft_sha256` for a setup) with the current one and
answers 409 on a difference, before the engine or `freeze` is called.

Every response, errors included:

```
Content-Security-Policy: default-src 'none'; style-src 'sha256-<hash of the one style element>'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'
Cache-Control: no-store
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
X-Frame-Options: DENY
Content-Type: text/html; charset=utf-8
```

The page has one inline `style` element (its hash is in the policy) and no script, so there is no JavaScript to
attack, no external font, image or stylesheet, and nothing is fetched from another host (16 §5). Index pages refresh
with `<meta http-equiv="refresh">`; forms do not. The access log omits query strings and cookies.

#### 4.4.3 Routes

| Method and path | Purpose |
|---|---|
| `GET /launch?code=` | Open the session |
| `GET /` | Run status and the open requests, in `seq` order |
| `GET /request/<request_id>` | One approval or input request |
| `GET /setup/<setup_id>` | The basis confirmation screen |
| `GET /report` | The report of the run so far, built on each request (§4.6) |
| `POST /answer/<request_id>` | An answer |
| `POST /setup/<setup_id>` | A basis confirmation or rejection |

Ids match `[A-Za-z0-9_-]{1,64}` and name a request that exists. Nothing else exists: the page can approve, reject (with a
reason), reject single items, sign and choose among given options. It cannot edit a value (ADR-0027 pre-mortem).

#### 4.4.4 Opening the page

The process opens the launch address with the opener in `CliDeps` (`cli/_opener.py`), not with `webbrowser`, which
honours `BROWSER`: the default opener is `os.startfile` on Windows, `open` on macOS and `xdg-open` elsewhere, run with
`BROWSER` removed from the child environment. It prints only "approval page opened in your browser". The address is
**never written to standard output or standard error**, because a coding agent that runs `eng-harness run` reads both.
If opening fails, or with `--no-browser`, the address is written only to the controlling terminal (`/dev/tty`, or
`CONOUT$` on Windows). When there is no controlling terminal the process prints "the launch address cannot be shown
here; run from a terminal, or use --no-wait and resume later", and the page cannot be reached (AC61). After the first
launch the cookie serves other tabs of the same browser at `http://127.0.0.1:<port>/`. This does not protect against a
process of the same user that has the terminal, reads the opener's command line or drives the server itself (Q2).

#### 4.4.5 How the run waits, and the approval binding

1. `ctx.approve` (engine §4.9) journals `approval_requested` (FULL) with the preview reference, `shown_sha256`, the
   binding and the items, then calls `ApprovalPort.present(request)`. The page registers the request with its view and
   renders from the stored `harness.approval_preview/1` result after checking that its hash equals `shown_sha256`
   (else the screen says the preview is damaged and offers no button).
2. The merged engine calls `answer(request_id, wait=False)` at every request and pauses on `None` (engine §4.9). The
   process wait mode is the command line's (§4.2.1: wait unless `--no-wait`, up to `--wait-timeout`), so
   `cli/_wiring.py` wraps the page ports: the wrapper ignores the engine's `wait` and asks the page port with the
   process wait mode (B-510). Waiting, the port awaits an `asyncio.Event`, polling the stop file
   (§4.4.8) every second. It returns `None` on a stop request, on `--wait-timeout`, or at once with `--no-wait`; the engine then pauses
   (`run_paused`, reason `awaiting_approval`) and the process exits 10 (or 12 for a stop).
3. A POST that passes §4.4.2 and the answer checks (below) is parsed into an `ApprovalSubmission` (the validated form),
   turned into an `ApprovalAnswer` (an `InputAnswer` for a choice) and handed to the waiting `answer` call. **The answer is held in memory only**: it is not written anywhere until the engine journals it, one
   `approval_resolved` event, FULL durability. There is no answer file in the run folder, so nothing else can place an
   answer there (the `inbox/` folder that engine §4.4.1 reserves stays unused, Q4).
4. The page answers the browser only when the sink has seen the matching `approval_resolved` event (AC37).
5. If the process dies at any point before the journal write, the answer is lost and the request is shown again after
   `resume`, with the same request id and the same hash (engine AC36); the engineer answers again. If it dies after, the
   journal holds the answer. The wait is durable because the request is journaled and replay re-presents it.

Answer checks, after the server's own: the request is open in this run; `shown_sha256` equals the request's (for an
input or choice request, its `fields_schema_sha256`); no
`approval_resolved` exists and none is being processed (a per-request lock); rejected item ids are items of the request;
a reason of 1 to 500 characters exists for a rejection and for each rejected item; an approval is not issued with every
item rejected; the engineer name is valid (AC31, AC39). The engine then checks again (engine AC54); the page never
decides alone.

The binding to the model state is the engine's: the page shows it, and the engine re-reads the model just before the
first write under the approval and voids the approval on a mismatch (engine §4.9, AC34). Approval of a change set is
single use and ends at the first `check_model` of a bound model. No journal event names a void: `ApprovalVoid` is a
`StepError`, journaled as `step_failed` with code `APPROVAL_VOID`, and it carries no request id (Q21). When the page
sink sees such a `step_failed`, the page marks as voided the most recent approved `CHANGE_SET` or `PROMOTION` request
resolved in this process, and its screen shows "voided" with the error's message (an untrusted `field`), no form and
no button (AC34, B-412). With no such request in this process (the answer was given before a resume), the message is
shown on the index page as a run message.

#### 4.4.6 Screens

| Screen | Request | Content and answers |
|---|---|---|
| Change set (18 step 6) | `CHANGE_SET` | Title; items (label, referenced values with their sources); differences from the last revision as a table (`diff_ref`), engineer changes marked; binding table; preview hash; per-item reject boxes with a reason field each; Approve; Reject with a reason |
| Promotion (18 step 16) | `PROMOTION` | Target and backup by base name; hash of the original and the working copy's `origin_sha256`; Approve; Reject |
| Info | `INFO` | The text; Acknowledge (approve) or Reject |
| Sign-off (18 step 17) | `SIGN_OFF` | Link to `/report`; verdict counts; each exception (a verdict whose status is not `PASS` or `NOT_APPLICABLE`) with an accept box and a written reason; the unreleased-tool list with an acknowledgement box when it is not empty; the engineer name; Sign; Reject |
| Engineer turn (18 step 15) | choice request | Three buttons: accept this revision, ask for more edits, I edited by hand: continue. One press, one option id |
| Batched decisions (11 §3 `decide_many`) | choice request, N questions | One form: per question the prompt, labeled evidence, one option group; one Submit |
| Engine requests | `engine.in_flight`, `engine.host_state`, `engine.escalation` | The reason, the evidence references, the choices of engine §4.5 (`applied`, `not_applied`, `abandon`; `accept`, `restore`, `abandon`) |
| Input | `block` data request (`x-eng-input: data`) | The fields read-only (name, type, unit, bounds) and the instruction to use `resume --answers FILE` |
| Basis confirmation (13 §4) | `BasisSetupView` | §4.4.7 |

An input request carries a marker in its JSON Schema, `x-eng-input`, with the value `data` (set by `ctx.ask`: values
for the workflow) or `choice` (set by the engine's choice helpers `decide` and `decide_many`, by the engineer turn, and
by the engine's own `engine.*` requests: an answer decides what happens). **A schema with no marker is a choice**
(fail-safe). The marker, not the presence of `enum` properties, decides what may be answered by file (§4.2.1, AC46).
The page renders a choice request from its schema: a property with an `enum` is a question (its `title` is the prompt
and its enum values the options, with labels from the package's label catalog `pages/_labels`, never from data); a
property marked `x-eng-evidence` is a bounded, labeled, read-only text. The answer carries option ids only (AC32). The
marker, and the engine refusing a request whose schema has `enum` properties but declares neither `data` nor `choice`,
are an amendment of engine §4.9; the alignment with the engineer tier of spec 0005 is Q6.

An exception on the sign-off screen is accepted with its own reason; the reasons travel as `item_reasons` of the answer
(14 §6; the engine's `ApprovalAnswer` and `approval_resolved` gain the member, Q8; which item carries an exception's
reason is Q24). Sign-off is refused by the page
when an exception has no reason, and the engine appends `signed_off` for the approved `SIGN_OFF` request (engine §4.9).

#### 4.4.7 Basis confirmation

Before a run exists (spec 0004 §4.6), `PageBasisSetupPort.present(view)` registers the `BasisSetupView` and
`answer(setup_id, wait=...)` returns a `BasisSetupAnswer`. The screen shows the banners (`draft_template`,
`synthetic_template`), then each section with its rows: label, value, unit, source, citation, state, bounds. A
confirmable section has a confirm box; a section with a missing required row has none and the draft is not offered
(step 3 of §4.2.2 exits earlier). Values are not editable. Confirm needs all boxes and a name; Reject needs a reason.
The screen is rendered from one draft and the form carries its `draft_sha256`; the answer is refused (409) if the
hash is not that of the current draft, before `freeze` (AC47, §4.4.2). The answer holds `setup_id`, `draft_sha256`, the confirmed section names, `by` and `at` (from the injected clock), or
the rejection; the page appends a record to `<workspace>/setups/<setup_id>.json` (spec 0004 Q5). In-process only: a
`--no-wait` run does not serve it (exit 10, nothing stored), and an interrupted setup starts again with the same
command (a new draft hash if the files changed). **There is no deferred basis confirmation (B-354).** No run exists
before the basis is frozen, so there is nothing to resume: a workflow with required basis fields is started by the
engineer with `run` without `--no-wait`, in a terminal, and the basis is confirmed on this screen in that process;
`--no-wait` there exits 10 with a message saying so (AC47). For the first change set of spec 0007, `run --answers
FILE` (AC64) replaces the interim `run --no-wait` route that spec 0007 Q7 had proposed: one `run` confirms the basis,
takes the change set from the file and waits at the change-set approval on the page.

#### 4.4.8 The stop file (B-412)

The stop request is one file, `<workspace>/runs/<run_id>/stop.json`, a JSON object with exactly two members:
`requested_at` (a contract `Timestamp`, shown as in §4.7) and `by` (`cli` for the `stop` command, `signal` for the
first interrupt of AC10). The writer writes a temporary file in the same folder and renames it over `stop.json`, so a
reader never sees a partial file. `cli/_control.py` holds the protocol:

- `FileRunControl.stop_requested(run_id)` (the engine's `RunControlPort`) returns true while the file exists, whatever
  its content; the page ports' wait (§4.4.5 step 2) polls the same check. `eng_harness.pages` may not import
  `eng_harness.cli` (§4.1), so the page ports take the check by injection (`stop_requested: Callable[[], bool]`), and
  `cli/_wiring.py` binds it to `FileRunControl` for the run.
- The run id behind the run-folder bindings (B-412 review; extended by the eighth review). The page ports'
  `stop_requested` and `report` (`GET /report`, §4.4.3) take no argument, but both need the run id, and for `run` the
  run id does not exist when `cli/_wiring.py` builds its collaborators: `Engine.start` creates it and returns it only
  in `RunOutcome`, and `InputRequest` and the journal `Event` do not carry it. `cli/_wiring.py` therefore keeps the
  run id in one cell, filled at once with the known run id for `resume`. For `run` it is filled at step 1 of §4.2.2
  with the run id the command line draws and passes in `RunRequest.run_id` (Q20 answer A, amendment B-471; engine
  AC70); until that binding (plan T18b) it is filled from the first `ApprovalRequest.run_id` that the wrapped page
  `ApprovalPort` receives, and, once the progress sink reaches the real engine, from the `run_started` event
  (`RunHeader.run_id`) that the sink receives, whichever comes first; a later value that differs is a defect and raises.
  After T18b those two fills stay in place, but for `run` they only confirm the id of step 1 (a differing value
  raises), so step 1 is the one source of the run id for `run`. The cell is the one source of the run id for every
  collaborator that needs the run folder `<workspace>/runs/<run_id>`, and each states what it does while the cell is
  empty:
  - the page ports: `stop_requested` returns false and `report` returns the fixed "report not available yet"
    document; the engine's own `RunControlPort` is not affected, since it receives `stop_requested(run_id)`;
  - the first interrupt (`cli/_signals.py`, AC10): with the cell filled and the run folder present it writes
    `stop.json` with `by` = `signal`; while the cell is empty or the folder does not exist yet, no engine can be
    paused (steps 1 to 4 of §4.2.2, the basis screen included, or the start of `Engine.start`), so the first
    interrupt ends the process as the second does (exit 130); nothing is buffered, and a run already created resumes
    as after a crash (engine AC30);
  - the heartbeat (§4.3): prints its line and writes no file;
  - the tool and host ports: spec 0002 `build_ports(config, workspace, store, run_dir, clock, ids)` needs the run
    folder, the engine takes its ports at construction, and it calls `ToolPort.unreleased_tools()` for the run header
    before `run_started` is journaled, so for `run` only the fill at step 1 comes early enough. The `CliDeps` port
    builder takes the run folder as a callable that reads the cell (and raises while it is empty), and its real
    default is bound with that fill (plan T18b).
  `Engine.start` takes the run id chosen by the caller (Q20 answer A, decided by amendment B-471; engine §4.5.1, AC70),
  so the cell is filled for `run` as for `resume` before any port is built (end of step 2, amendment B-536).
- `stop <run_id>` writes the file only when the run lock is held (a live engine); otherwise it writes nothing, exits 0
  and says the run is not running (AC9). `stop --wait SECONDS` then waits until the run lock is released, or the
  seconds pass.
- The run process (`cli/_run.py`) removes the file when `Engine.start` or `Engine.resume` returns with `run_paused`
  reason `stop_requested`, or with any other outcome while the file exists.
- `resume` removes a stale file at the start of the command, before step 1 and before `cli/_signals.py` installs its
  handler, never just before `Engine.resume`: a file that the first interrupt writes during step 1 or step 5 is then
  kept and honored at the engine's first check (AC9, AC10).

The file is process information, like `heartbeat.json`, not a journal event. It is an addition to the run folder of
engine §4.4.1 (Q19).

### 4.5 HTML, escaping and the templating choice

**Choice: the standard library, no template engine (Q1).** Jinja2 would give autoescape, but it is a new runtime
dependency (A10, a package ADR), has its own expression language and a history of sandbox escapes, and these pages are
fixed tables and forms. The same guarantee is obtained by construction in `_html.py`:

- Text is `Text` (escaped with `html.escape(..., quote=True)` after `sanitize_html`) or `Trusted` (a constant written in
  this package, created only inside `_html.py` and the label catalog). The builder accepts nothing else, and a
  `str` where a node is expected is a type error (`mypy --strict`) and a runtime error.
- Untrusted data enters only through `field(label, value)`: a fixed label from the catalog and the value as
  `<bdi dir="auto">escaped text</bdi>`, truncated at `display_max_chars` with "(N characters)", with bidirectional
  controls replaced by `<U+XXXX>` and control characters removed. `<bdi>` keeps Arabic or mixed text from reordering
  the text around it.
- Attributes accept `SafeToken` (`[A-Za-z0-9_.-]{1,64}`) or enumerated values only; hrefs are built from route
  constants and validated ids (AC49).
- One shared style sheet (`pages/_css.py`), embedded once per document; its SHA-256 goes into the policy.

Page language is English in phase 1 (`lang="en"`, `dir="ltr"`); data in any script is displayed correctly. Arabic
labels and right-to-left layout belong to the full UI ADR (Q9).

### 4.6 The run report

#### 4.6.1 Content

`build_report(reader: JournalReader, store: ResultStore, marks: ReleaseMarks, clock, version) -> str` returns one
self-contained HTML document built from the journal and the result store only (11 §5: what the engineer reads is what
happened). Sections:

1. **Status**: run id, workflow, block name, version and code hash, mode, engine and contract versions, template and
   design basis (name, version, hash; who confirmed each value and when, from the `engineer:<name>@<time>` source of its basis field), start
   and end, status, the marks (DRAFT, DRAFT SOURCES, INCOMPLETE, trial run, unreleased tools), the integrity line:
   event count and the last `chain_sha256`, and the decision runtime of the run header (`RunView.decision_runtime`,
   engine AC69): its providers and released points, with the dropped releases (spec 0009 AC29), as plain label and
   value rows like the other Status rows (not value cells: the header is not a stored result, so it has no sources
   row), held to the generic renderer's caps (at most 200 rows and depth 4, with "N more"); nothing when it is empty
   (Q16 (c), amendment B-471).
2. **Changes**: model revisions (`model_saved`: role, revision, fingerprint, base file name); per `CHANGE_SET` approval
   the items with state and reasons, the binding, the applied steps with read-back results, and the differences
   including engineer changes; promotion and its backup.
3. **Results summary**: verdict counts and governing ratios, failing members, model-check results, analysis messages
   and drift summaries, by registered renderers (below).
4. **Sources**: the table every value cell links to (AC52): result id and pointer, kind, producer and version, creation
   time, parents; for basis fields the `source`, citation and confirmation; engineer inputs with `entered_by` and time.
5. **Decisions**: `decision_made` (point, options, choice, deciding tier, confidence), approvals and inputs (request,
   kind, decision, who, when, reasons), escalations and reconciliations.
6. **Timings**: per step start and duration, engineer waiting time against machine time, resumes (AC56).
7. **Run events**: resumes, host starts and instances left open (from the journal events).

A registry maps result kinds to section renderers (`verdicts.set/1`, `issues.model_check/1`, `forces.story_drifts/1`,
`basis.*`, `harness.approval_preview/1`); the kinds of specs 0002, 0003 and 0007 register theirs. A kind with no
renderer is shown by a generic renderer: a bounded table of labeled escaped cells (at most 200 rows and depth 4, with
"N more" and the result id). The report never recomputes an engineering value: it shows stored values and their
units. Source of every value: a value cell is built only through `value_cell(value, source)`, and `source` is required
(AC52).

#### 4.6.2 DRAFT, completeness

Outputs are DRAFT until the engineer signs (14 §6): the banner, the `<title>` prefix and a print watermark show DRAFT
until `signed_off` is in the journal, then the name and time of the signing. `run_completed.draft` true (draft calcs or
templates, 10 §4) keeps "DRAFT SOURCES" after signing. A run that is not terminal shows "INCOMPLETE: <status>" and, with
a live engine, "run in progress as of seq N". The report is derived, rewritten whenever asked, never appended to the
journal, and written to `<run>/report/report.html` (AC12, AC59). The document carries
`<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'sha256-…'">` and no script.

#### 4.6.3 Unreleased project-lane tools (ADR-0026 §3)

`ReleaseMarks` maps tool names to the record of their project-lane branch (from `[project_lane.<tool>]`; Q5).
`unreleased_dependencies(reader, store, marks)` returns the marked results: every result whose producer tool is in the
map, and every result with such a result among its ancestors, following `ResultRecord.parents` and the references in
`provenance.inputs` breadth-first to `lineage_depth_limit` (default 50). A result beyond the limit is marked and
flagged. A step that called a marked tool is marked in the timings. The mark text is "Depends on unreleased tool
`<tool>` (record `<record>`)". The same function feeds the report banner and the sign-off screen, which requires the
acknowledgement (AC42, AC54), so the engineer signs knowing which results came from an unreleased tool.

### 4.7 Text, dates and numbers

`_text.py` is the only place that formats: `format_duration_ms` (integer arithmetic), `format_timestamp` (slicing a
contract `Timestamp` into `YYYY-MM-DD HH:MM:SS UTC`), `format_number` (`format(x, ".6g")`-style with an explicit
specification, ASCII digits), `sanitize_terminal`, `sanitize_html`, `truncate`. Nothing in this spec imports `locale`
or calls `strftime`, `%c`, `%x`, `%X`, `%A`, `%B`, `%p` or the `n` format type (AC58); `datetime` is used only to parse
and compare. All files are opened with `encoding="utf-8"` and `newline="\n"`; the standard streams are reconfigured at
start (AC5): redirected streams to UTF-8, a console keeps its encoding with `errors="backslashreplace"`. Paths are
`pathlib.Path` values and are never encoded by hand, so Arabic folder names work; messages show base names unless a
path is needed to act (the report path).

### 4.8 Concurrency

The engine loop, the writer thread of the sink and the page handler threads are the only threads. Page state (open
requests, accepted flags) is guarded by one lock; the engine loop is entered only through `call_soon_threadsafe`. The
heartbeat task runs on the engine loop.

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `--input` file | JSON object | per workflow model | the workflow input model | values may be `$ref`; a model file (a `pathlib.Path` field) is an absolute path (§4.2.2 step 2) | engineer or agent |
| `--basis` file | YAML or JSON `{engineer, values}` | canonical per suffix | by `FieldSpec` (spec 0004) | no | engineer or agent, confirmed on the page |
| `--answers` file | JSON | per request fields | the request's model | no | engineer or agent |
| Page form fields | `application/x-www-form-urlencoded` | none | §4.4.3; reasons 1 to 500; name 1 to 100; body at most `max_body_bytes` | no | engineer; carry decisions and option ids, never engineering values |
| Final result (`--json`) | JSON object | none | AC7 | no | the process |
| Report | HTML, UTF-8 | none | one document | no | journal and store |
| `heartbeat.json`, stop file, setup log | JSON | none | small | no | the process, `stop`, the page |

## 6. Errors

| Condition | Code | Exit |
|---|---|---|
| Usage, configuration, input file invalid | `INVALID_ARGUMENT` | 2 |
| Configuration this build cannot serve (spec 0002 AC43, gap H-G8; B-495) | `NOT_IMPLEMENTED` | 2 |
| Basis incomplete or rejected, server check failed, calcs refused, unknown workflow | `BASIS_INCOMPLETE`, `SERVER_CHECK_FAILED`, `CALC_NOT_APPROVED`, `CALC_WITHDRAWN` (engine §6, spec 0003) | 3 |
| Another process holds the run | `RUN_LOCKED` | 4 |
| Journal altered | `JOURNAL_INTEGRITY` | 5 |
| Unknown run | `REF_NOT_FOUND` | 6 |
| Page request refused | HTTP 400, 403, 404, 405, 409, 413, 415, 421, 503 (no run data in the body) | — |

## 7. Non-goals

- Any graphical application, a model view, live websocket updates, a results browser, a template editor, settings
  screens (ADR-0027 §3, 14 §3 target screens); NiceGUI and spike S-09.
- Editing values on the page; approval by command line, by file, by environment variable or by the agent chat.
- User accounts, authentication of the engineer's identity beyond the session and the typed name, remote access, TLS,
  a page that outlives its run process.
- Arabic interface strings and right-to-left layout (data in Arabic is displayed correctly, §4.5); PDF reports (14 §6).
- Recomputing or reinterpreting any engineering value; the report shows stored values only.
- Server silence handling and worker termination (spec 0002); the workflow's own screens and options (spec 0007).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| An agent approves its own change set | R1 (model writes) | No approve command or file; answers only from the page process after session, Host, Origin, CSRF and hash checks; the launch address is opened by an opener that ignores `BROWSER` and is never written to standard output or error, only to the controlling terminal; `--answers` cannot answer choices or engine requests (AC46); static test AC2. Residual risk: a same-user process (Q2) |
| A page for one request answers another, or an old page answers a new preview | R1 | CSRF token bound to request, hash and session; hash compared by page and engine; single use; engine void check (AC25, AC29, AC30, AC34) |
| Untrusted text (drawing, model, file) becomes markup or terminal control | R1 | Escaping by construction, labeled `<bdi>` fields, strict CSP, no script, sanitized terminal text (AC21, AC26, AC48, AC49) |
| DNS rebinding or a cross-site form post reaches the loopback server | R1 | Exact `Host`, `Origin`, `Sec-Fetch-Site`, `SameSite=Strict`, random port, lockdown (AC22 to AC28) |
| Results of an unreleased tool are signed unnoticed | R1 | Marks in report, timings and sign-off screen; acknowledgement required (AC42, AC54) |
| The report differs from what happened | R1 | Built only from journal and store; deterministic; integrity line; refuses an altered journal (AC50, AC57) |
| A blocked output pipe stalls the run | R2 | Queue and writer thread; drop and count (AC19) |
| Expected times mislead on a larger model | R2 | Range and sample count always shown; no estimate below `min_samples` |
| Locale, calendar or code page breaks output | R2 | One formatting module, static rule, Windows test with Arabic path and cp1256 (AC5, AC58) |
| The page grows into an unplanned interface | R2 | Route table fixed (AC27); no value inputs; requests to edit values go to the full UI ADR |
| Browser behavior (CSP, bidi rendering, form handling) differs from the tests | R2 | Local test on the owner's browser (`docs/local-testing.md`) |

## 9. Test strategy

| Criteria | Layer | Location |
|---|---|---|
| AC1, AC3 to AC6, AC10 to AC14, AC61 (opener), AC62, AC65, AC66; AC9, AC18, AC19, AC37 (production wiring, plan T16b) | Unit | `tests/unit/cli/` |
| AC15, AC17 to AC19 | Unit | `tests/unit/progress/` |
| AC22 to AC28, AC30 to AC32, AC34 (page half, plan T7b), AC36, AC38, AC39 | Unit (real loopback server, `http.client`) | `tests/unit/pages/` |
| AC49, AC50, AC52 to AC57, AC59 | Unit | `tests/unit/`, `tests/unit/report/` |
| AC2, AC58 (rule), AC60 | Rules (static) | `tests/rules/` |
| AC7, AC9, AC19 (engine half, plan T17), AC29, AC33, AC34, AC37, AC42, AC46, AC47, AC61 (address on no stream), AC63, AC64 | Fake-host workflow (real engine, fake ports, real SQLite, page client; a task built before the engine it needs uses the staged-engine stand-in below, and plan T17 or T17c re-checks it with the real engine) | `tests/workflow/` |
| AC8 (staged engine, re-checked in plan T17c), AC9 (stop-file removals, plan T14), AC35 | Replay (process killed, resumed) | `tests/replay/` |
| AC16, AC40, AC41, AC51 | Golden (document and text snapshots; not engineering oracles, so kept under `tests/data/snapshots/`, not the protected `tests/data/golden/`) | `tests/golden/` |
| AC15 (bounds), AC21, AC48, AC54 | Property (Hypothesis, CI profile `derandomize=True`) | `tests/property/` |
| AC43 to AC45, AC46 (file refusals) | Unit | `tests/unit/pages/` |
| AC67, AC68 (amendment B-536) | Fake-host workflow (fake engine and port builder from `CliDeps`) | `tests/workflow/` |
| AC69 (amendment B-536) | Unit | `tests/unit/cli/` |
| AC20 | Performance | `tests/perf/` |
| AC58 (Windows) | Windows job, marker `windows` | `tests/windows/` |

Staged engine (B-412): a workflow or replay test whose task is built before the engine it needs has merged drives the
port under test with a test-local stand-in for the engine (it journals through the merged `JournalWriter` and feeds
the events to the sink) or with a fake engine from `CliDeps`. This holds for every such criterion: AC29 and AC37 (plan
T7), AC42 (plan T9b), AC7 and AC8 (plan T14), AC46 and AC64 (plan T14c), AC61 and AC63 (plan T14b), AC47 (plan T15) and AC9 (plan
T16). AC33, AC34 and AC35 are tested end to end only in plan T17, with the real engine; the page's voided display that
AC34 needs is built and unit-tested in plan T7b, so T17 adds tests only. Plans T17 and T17c wait for the real engine
with approvals (engine plan T15, which brings engine T9 to T14b); T17 also waits for progress delivery and the
run-control check between steps (engine plan T18; the run-control half is added to it by amendment B-412). Until the
engine's `EnginePorts` holds the progress and run-control fields (engine plan T18; its `decision` field, engine plan
T14, is merged and plan T14b maps the cascade into it, B-510), `cli/_wiring.py`
builds those ports and gives them to the `CliDeps` engine factory, whose default passes the real engine only the
fields `EnginePorts` holds; plan T16b completes that mapping, and plans T17 and T17c depend on it, so they re-check each
staged criterion with the real engine through the production wiring; the engine half of AC19 is the one exception,
re-checked with `TerminalProgress` as the real engine's only sink (AC19). Plan T17:
`tests/workflow/test_cli_stop.py::test_stop_real_engine_pauses_at_safe_point` (AC9),
`tests/workflow/test_progress_detach.py::test_raising_renderer_detached_run_continues` (AC19),
`tests/workflow/test_page_approval.py::test_answer_bound_to_hash_real_engine` (AC29) and
`::test_page_confirms_after_commit_real_engine` (AC37). Plan T17c:
`tests/workflow/test_cli_run.py::test_run_completes_and_writes_report_real_engine` (AC7),
`tests/replay/test_cli_resume.py::test_no_wait_then_resume_real_engine` (AC8),
`tests/workflow/test_signoff.py::test_signoff_rules_real_engine` (AC42),
`tests/workflow/test_cli_answers.py::test_form_request_answers_file_real_engine` (AC46),
`tests/workflow/test_cli_basis.py::test_basis_confirmation_flow_real_engine` (AC47),
`tests/workflow/test_launch_address.py::test_address_never_on_stdout_or_stderr_real_engine` (AC61),
`tests/workflow/test_cli_run.py::test_run_header_records_decision_runtime_real_engine` (AC63) and
`tests/workflow/test_cli_answers.py::test_run_answers_first_data_request_real_engine` (AC64). The unit criteria
(AC6, AC62 and the others of the unit rows) need no engine: their collaborators are recorders by design.

No engineering value is computed here, so there are no golden engineering tests. Tests use the contract's `FixedClock`
and `SeededIdSource`, a fake browser opener, and the engine's fake ports. Coverage floors 85% line and 75% branch
(process/05 §2); mutation score at least 80% on `pages/_security.py`, `pages/_answers.py`, `pages/_ports.py`,
`_html.py`, `_text.py` and `report/_lineage.py`. Browser-level checks need the owner's machine
(`docs/local-testing.md`).

## 10. Version impact

Adds the commands, the four public modules and the file formats of §5 to `eng-harness` 0.1.0 (new package). The
`approval_resolved` payload gains `item_reasons` and `ApprovalAnswer` the same member (engine amendment, Q8): a minor
change to the journal schema that the reader must read with and without. The marker `x-eng-input` on input requests (Q6) is a second engine amendment; a request without it is read as a choice. The JSON result of §4.2.1 and the exit codes
are public interface: a change is minor or major with a changelog entry. Amendment B-098: `harness.toml` passes
`[providers.*]` to spec 0009, `CliDeps` gains the decision-runtime assembler, and the run header gains
`decision_runtime` (engine AC69), all additive. Amendment B-354: `run` gains `--answers FILE` (additive) and the
basis-confirmation exit of `--no-wait` is stated (AC47); no journal or contract change.

## 11. Open questions, gaps and additions

| Id | Question or gap | Owner | Recommendation |
|---|---|---|---|
| Q1 | Templating: Jinja2 with autoescape and a package ADR, or the standard library | Owner | Standard library (§4.5): no dependency, escaping by construction, tested by property; revisit if the full UI needs a template engine |
| Q2 | A coding agent that itself runs `eng-harness run` is a same-user process and has these routes to the launch address: (1) the `BROWSER` environment variable, which `webbrowser.open` honours, so the agent can name a program that captures the address; (2) standard error, where an address printed after a failed open (typical in a headless agent environment) would be read; (3) `--no-browser`. Beyond the address, Host, Origin and Sec-Fetch-Site are forgeable by a plain HTTP client, and the opener's command line is visible in the process list. 16 §5 asks for the token, not for protection from the user's own processes | Owner | Accept the residual risk for v1 with these mitigations (§4.4.4, AC61): an own opener that drops `BROWSER`; the address is written only to the controlling terminal, never to standard output or error, so (2) and (3) yield nothing without a terminal; the agent rule (§4.2.1); every write still needs the change-set approval, and `--answers` cannot answer choices. Not closed: an agent with a controlling terminal, or reading the process list. A stronger factor (a separate operating-system account, Windows Hello) is a later ADR |
| Q3 | Values given to `ctx.ask` by `--answers` and basis values are files an agent may write; only basis values are confirmed on a page | Owner | Accept: asked values reach a model only through a later change-set approval; revisit if a workflow writes asked values without one |
| Q4 | Engine §4.4.1 reserves `inbox/` for answers and its Q10 accepts the answer inbox; here the page runs in the engine's process and answers stay in memory, so nothing in the run folder can carry an answer | Owner | Remove `inbox/` from engine §4.4.1 at its next amendment; a file would let any local process answer |
| Q5 | How the report learns that a tool is unreleased: the journal does not record it | Owner | `[project_lane]` in `harness.toml` now (the report states the list it used); better: spec 0002's tool descriptor carries `release` and the engine records `unreleased_tools` in `run_started`, so a later configuration change cannot unmark a result |
| Q6 | The convention for choice and evidence fields (enumerated properties, `x-eng-evidence`), the marker `x-eng-input` (`data` or `choice`, unmarked is a choice, §4.4.6) and how the engineer-tier decisions of spec 0005 reach `InputPort`; spec 0005 is not merged | Owner | Add the marker to engine §4.9 (`ctx.ask` sets `data`; the choice helpers and `engine.*` set `choice`) and align with spec 0005 when it merges; the page needs the marker, enumerated properties and bounded text |
| Q7 | Default `--run-class`: `production` refuses calcs that are not `approved`; `trial` runs draft calcs with `draft: true` (spec 0003) | Owner | `production` by default, `trial` explicit; a refusal is the safe failure |
| Q8 | 14 §6 asks that each accepted exception has a written reason; engine `ApprovalAnswer` and `approval_resolved` carry one `reason` | Owner | Add `item_reasons` (item id to reason) to both; per-item rejection reasons use it too (AC31, AC42) |
| Q9 | Arabic interface text and right-to-left layout in phase 1 | Owner | English labels now; Arabic and RTL with the full UI ADR (14 §2, spike S-09); data in any script is already shown bidi-safe |
| Q10 | The wait for an answer has no time limit by default | Owner | Unlimited until answered or stopped; `--wait-timeout` for scripts. A paused run costs nothing and resumes by replay |
| Q11 | Defaults of the software settings in §4.2.4 (heartbeat 10 s, three intervals, 20 runs, three samples, 32 KiB, 20 failures, 10 s) are chosen here, not measured | Owner | Accept; tune after the first local runs (expected-time accuracy and heartbeat noise need real runs) |
| Q12 | The sign-off exceptions are verdicts other than `PASS` and `NOT_APPLICABLE`; 14 §6 says "every verdict is `PASS`" | Owner | `NOT_APPLICABLE` needs no reason; `FAIL`, `NEEDS_ENGINEER` and `ERROR` do |
| Q13 | Extra `doctor` checks that belong to this spec: the page can bind to `127.0.0.1`, a browser can be opened, the console encoding, the locale and calendar | Owner (spec 0002) | Add them to the doctor of spec 0002 through an extension point; until then they are exercised by AC22 and AC58 |
| Q14 | Engine §4.9 lists `ApprovalKind` `CHANGE_SET`, `PROMOTION`, `SIGN_OFF`, `INFO`, while 18 step 15 calls the engineer turn "approve" | Owner | The engineer turn is a choice request (§4.4.6), not an approval kind: it binds no model state and writes nothing. Spec 0007 states its options |
| Q15 | Spec 0005 §4.3 and spec 0009 §4.2 say this spec reads `DecisionSettings` (`local_only`, `sensitive_values`, `export_enabled`, `shadow_released.<point>` and the limits) from `harness.toml`, but no document names its section or its keys' types and bounds, and §4.2.4 had no entry for it | Owner | Name the section `[decisions]` (keys the fields of spec 0005 §4.3, `shadow_released.<point>` as a sub-table) in an amendment of spec 0005 §4.3, which owns the type; this spec then passes it through like `[providers.*]`. Until then T14 builds `DecisionSettings` with its defaults (`local_only` false, no release), which is the phase 1 behavior. Decided as recommended (owner instruction of 2026-11-12; amendment B-471): spec 0005 §4.3 and §4.2.4 |
| Q16 | Amendment B-098 (spec 0009 Q7). (a) Spec 0009 names `assemble_decision_runtime` and its result (providers, verified releases, summary) but not its arguments; §4.2.2 step 5 reads them as the `ProvidersConfig`, the `DecisionSettings`, the workspace and the point policies of `verify_releases` **[added]**. (b) Release findings (spec 0009 §4.10: "findings go to the run report as warnings") reach standard error only, because the report reads the journal and the store only (§4.6.1) and the summary of spec 0009 AC29 does not hold them. (c) The report's Status section does not yet show `decision_runtime` | Owner | (a) Fix the signature in plan 0009 T10 to these inputs. (b) Add the dropped releases (`point`, `reason`) to the summary in an amendment of spec 0009 AC29, so they are journaled with it. (c) Show the providers and released points of `RunHeader.decision_runtime` in the Status section at the next amendment of §4.6.1 (report plan T13). Decided as recommended (owner instruction of 2026-11-12; amendment B-471): (a) spec 0009 §4.1 and plan 0009 T10 (now T10b, amendment B-475); (b) spec 0009 AC29 (plan 0009 T7); (c) §4.6.1, built by plan T13b because T13 is merged. (d) Amendment B-475: under spec 0009 AC49 (the phase-1 assembly, plan 0009 T10a) no release is kept and no point policy is read, so the `point_policies` value of step 5 in phase 1 is the empty mapping, never `None` (a `None` field keeps `run` and `resume` "not available in this build"); the mapping from the workflow policies is needed first by plan 0009 T10b, whose release check reads it |
| Q17 | Amendment B-354 (spec 0007 Q7; `LOCAL-TESTING.md` open points 5 and 13). The first change set could reach a run only by `resume --answers`, and the interim route `run --no-wait` could not start a workflow that needs basis confirmation, because a `--no-wait` run does not serve the basis page and no run exists to resume | Owner | Decided **[added]**: `run --answers FILE` pre-answers the first data request only, through `accept_answers_file` (AC64); a workflow with required basis fields starts only with a waiting `run` (§4.4.7, AC47); the `run --no-wait` route is withdrawn. No answer path is widened: the file still answers data requests only, and the change set is still approved on the page |
| Q18 | Amendment B-354 (`LOCAL-TESTING.md` open point 6). How the owner invokes the command from the workspace root. The decision rests on uv's documented command-line options (`uv run --package`, `uv sync` being exact) and a check on this workspace with uv 0.11; the uv workspace documentation page was not reachable from the authoring session | Owner | Decided: `uv run --package eng-harness eng-harness <command>` (§4.1, AC65); the owner may confirm it against docs.astral.sh. `LOCAL-TESTING.md` should use this form for every `eng-harness` command |
| Q19 | Amendment B-412. Neither this spec nor engine §4.4.1 named the stop file's path, content or remover; engine §4.4.1 lists only `journal.sqlite`, `run.lock`, `copies/` and `backups/` | Owner | Decided here **[added]**: `runs/<run_id>/stop.json` with `requested_at` and `by`, written by rename, removed by the run process and by `resume` (§4.4.8); add `stop.json` and `heartbeat.json` to engine §4.4.1 at its next amendment |
| Q20 | Amendment B-412 (eighth review). For `run`, the run folder does not exist when the command line must build the tool and host ports: spec 0002 `build_ports` takes `run_dir`, the engine takes its ports at construction and calls `ToolPort.unreleased_tools()` before `run_started`, and `Engine.start` draws the run id itself (engine §4.4.1, `run_` + ULID from its `IdSource`). The run-id cell of §4.4.8 cannot fill early enough | Owner | (A, recommended) amend the engine spec: `RunRequest` gains an optional `run_id` chosen by the caller (`run_` + ULID, the engine's pattern), which `Engine.start` uses when given and refuses with `INVALID_ARGUMENT`, creating nothing, when that run folder exists; `cli/_wiring.py` then draws the run id at step 1 and fills the cell at once for `run` as for `resume`, so every run-folder binding is set before anything is built. (B) amend spec 0002: `build_ports` takes the run folder as a callable resolved at the first call that needs it, and `unreleased_tools()` needs none. Either way the `CliDeps` port builder already takes the run folder as a callable (plan T14); binding its default (plan T18) waits for the answer, and under (A) the lead adds the engine task and plan T18 draws the run id in `cli/_wiring.py`. Decided: answer A (owner instruction of 2026-11-12; amendment B-471): engine §4.4.1, §4.5.1 and AC70 (engine plan T20, work item B-472); §4.2.2 and §4.4.8 here; plan T18 split into T18a (every default but the port builder) and T18b (the port builder and the run id at step 1, after engine plan T20; AC66) |
| Q21 | Amendment B-412 (eighth review). `ApprovalVoid` carries no request id, so the page ties a void to the most recent approved `CHANGE_SET` or `PROMOTION` request of the process (§4.4.5); with nested approvals in force that may name the wrong one | Owner | Add the approval's `request_id` to the `ApprovalVoid` detail (engine §4.9, §6) at the engine's next amendment; the page then marks that request. Until then the rule of §4.4.5 holds, and the message itself is always shown |
| Q22 | Amendment B-510. The inputs of `--template NAME[@VERSION]` (§4.2.1, §4.2.2 step 3) are not defined: spec 0004 §4.3 takes the user folder of `TemplateRepository(shipped_dir, user_dir)` from "the settings file of spec 0006", but §4.2.4 has no such key and `harness.toml` refuses an unknown section; and `TemplateRepository.get` needs an exact version, while no document says which version `NAME` alone means | Owner | Writer's recommendation (B-510): add `[templates] user_dir` (a path; unset means no user folder) to §4.2.4 and name it in spec 0004 §4.3; require `@VERSION` (`NAME` alone is a usage error, exit 2), because the template version is part of the basis's identity and a "highest version" rule would change the draft of one command when a file is added. Interim reading until answered (plan T15): shipped templates only (the user folder is a path that cannot exist, named in plan T15, which `TemplateRepository` reads as empty), and `--template NAME` without `@VERSION` exits 2 naming the form `NAME@VERSION` |
| Q23 | Amendment B-510. `RunRequest.basis_ref` is required (engine §4.5.1), but step 3 of §4.2.2 freezes a basis only when the workflow declares required basis fields, and no document says what `run` passes for a workflow without them | Owner | Writer's recommendation (B-510): pass `res_` followed by 26 zeros, a well-formed reference that names no stored result; the engine loads the basis at the start only when a field is required (engine invariant 5), so such a run does not read it. Such workflows are test workflows in v1 (the shipped workflows declare required basis fields); a run that reaches a decision or the report's basis rows would fail on the reference, so a report guard or an optional `basis_ref` is a later amendment if such workflows are wanted in production. Interim reading until answered: the same value (plan T14) |
| Q24 | Amendment B-510. Each sign-off exception is accepted with its own reason carried in `item_reasons` (§4.4.6, AC42), but the engine and the page accept `item_reasons` keys that are items of the request only (engine §4.9; `pages/_answers.py`), the preview items of the sign-off are the outputs (spec 0007 §4.5 step 17), and a verdict has no id (several verdicts can share one output): no key exists for one reason per verdict | Owner | Writer's recommendation (B-510): the `SIGN_OFF` preview holds one item per output and one item per exception, in report verdict order, with id `exc_<n>` (n from 1) and no refs, so `signed_off.outputs` is unchanged; an exception's reason is the `item_reasons` entry of its item, and the page refuses sign-off while an exception item has no reason (amend §4.4.6, AC42 and spec 0007 §4.5 step 17; plan T9b and plan 0007 T9b follow). Interim reading until answered (plan T9b): the page follows the recommendation, so each exception keeps its own reason field (AC42); an exception without its `exc_<n>` item has no reason and signing is refused, so a workflow run with exceptions can be signed only once its step 17 adds the items (spec 0007 §4.5 step 17 and plan 0007 T9b follow at the answer) |
| G1 | Browser behavior (CSP enforcement, bidi rendering, print layout of the report) cannot be tested in CI | Owner | `docs/local-testing.md` lists the manual checks; nothing is claimed working before then |
