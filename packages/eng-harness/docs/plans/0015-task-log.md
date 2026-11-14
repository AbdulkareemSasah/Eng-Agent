---
id: plan-b478-task-log
issue: "B-478"
spec: packages/eng-harness/docs/specs/0015-task-log.md
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r2, r3]  # r3 from pyproject.toml (T1); r2 from the security modules T1 adds to the package risk map and r2_modules
tasks:
  - id: T1
    title: Record models, schema snapshot, import rule, risk entries
    files:
      - "packages/eng-harness/pyproject.toml"  # public_modules entries eng_harness.tasklog and eng_harness.tasklog.privacy; r2_modules entries for _scope.py, _hook.py, _push.py
      - "packages/eng-harness/.gate/risk-map.yml"  # the same three modules in the r2 entry
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/__init__.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_records.py"
      - "packages/eng-harness/tests/data/snapshots/tasklog/record-1.json"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_records.py"
      - "packages/eng-harness/tests/rules/test_tasklog_imports.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_records.py::test_kind_set_closed"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_records.py::test_extra_forbidden"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_records.py::test_owner_words_bytes_exact_arabic"
      - "packages/eng-harness/tests/rules/test_tasklog_imports.py::test_blocks_do_not_import_tasklog"
    covers: [AC1, AC2, AC32]
    depends_on: []
  - id: T2
    title: Guard, policy protocol, full policy, sanitized stub
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_guard.py"
      - "packages/eng-harness/src/eng_harness/tasklog/privacy/__init__.py"
      - "packages/eng-harness/src/eng_harness/tasklog/privacy/_full.py"
      - "packages/eng-harness/src/eng_harness/tasklog/privacy/_sanitized.py"
      - "packages/eng-harness/tests/data/tasklog/secret_vectors.json"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_guard.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_policy.py"
      - "packages/eng-harness/tests/property/test_tasklog_guard_never_leaks.py"
    max_changed_lines: 340
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_guard.py::test_owner_secret_withheld_not_dropped"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_guard.py::test_owner_personal_path_withheld"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_guard.py::test_agent_secret_refused_no_echo"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_guard.py::test_guard_vectors_match_gate"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_policy.py::test_policy_required"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_policy.py::test_sanitized_gap_tl_g1"
      - "packages/eng-harness/tests/property/test_tasklog_guard_never_leaks.py::test_guard_never_leaks"
    covers: [AC4, AC5, AC6, AC7, AC8]
    depends_on: [T1]
  - id: T3a
    title: Store and ids
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_store.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_ids.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_store.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_ids.py"
    max_changed_lines: 260
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_store.py::test_concurrent_append_never_interleaves"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_store.py::test_closed_task_rules"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_store.py::test_size_cap"
    covers: [AC10, AC11, AC12]
    depends_on: [T1, T2]
  - id: T3b
    title: Log worktree validation
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_worktree.py"
      - "packages/eng-harness/tests/helpers/tasklog_git.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_worktree.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_worktree.py::test_worktree_refusals"
    covers: [AC13]
    depends_on: [T1]
  - id: T4a
    title: The [tasklog] configuration and the user-level push file
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/_config.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_pushconf.py"
      - "packages/eng-harness/tests/unit/cli/test_tasklog_config.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_pushconf.py"
    max_changed_lines: 180
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/cli/test_tasklog_config.py::test_harness_toml_push_key_refused"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_pushconf.py::test_push_file_inside_repo_refused"
    covers: [AC26]   # in part: the configuration cases; the push command follows in T8b
    depends_on: [T1]
  - id: T4b
    title: Command module, part 1 (status, open, said, note, close, render stub)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/__main__.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_cli.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_cli_open_close.py"
    max_changed_lines: 320
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_cli_open_close.py::test_said_file_strict_utf8"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_cli_open_close.py::test_open_echo"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_cli_open_close.py::test_no_approval_surface"
    covers: [AC3, AC15, AC31, AC33]   # AC33: the existing CLI AC1 test stays green
    depends_on: [T3a, T3b, T4a]
  - id: T8h
    title: Log-only definition and the pre-push hook
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_scope.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_hook.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_cli.py"  # install-hook; the status hook line
      - "packages/eng-harness/tests/helpers/tasklog_git.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_scope.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_hook.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_scope.py::test_log_only_definition"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_hook.py::test_hook_refuses_non_log_only"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_hook.py::test_hook_self_contained"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_hook.py::test_install_hook_refuses_foreign"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_hook.py::test_status_hook_in_place"
    covers: [AC34, AC35]
    depends_on: [T4b]
  - id: T5
    title: Command module, part 2 (search, missing, refused, instead, problem, handoff, add --batch)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_cli.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_catalog.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_cli_records.py"
    max_changed_lines: 360
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_cli_records.py::test_catalog_unavailable_is_recorded"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_cli_records.py::test_missing_answered_hint"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_cli_records.py::test_refused_mapping"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_cli_records.py::test_batch_atomic"
    covers: [AC16, AC17, AC18, AC19]
    depends_on: [T8h]
  - id: T6
    title: STORY.md rendering
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_render.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_render.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_render.py::test_render_deterministic"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_render.py::test_render_fenced_words_and_gloss"
    covers: [AC20]
    depends_on: [T5]
  - id: T7
    title: Completeness checks
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_check.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_cli.py"  # check
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py"
    max_changed_lines: 360
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py::test_check_tlc001"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py::test_check_tlc002"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py::test_check_tlc003"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py::test_check_tlc004"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py::test_check_tlc005"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py::test_check_tlc007"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py::test_check_tlc009"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py::test_check_tlw001"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py::test_check_tlw002"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_check.py::test_check_tlw003"
    covers: [AC24]   # in part: TLC001 to TLC005, TLC007, TLC009, TLW001 to TLW003
    depends_on: [T6]
  - id: T7b
    title: Post-push withholding
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_withhold.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_cli.py"  # withhold
      - "packages/eng-harness/src/eng_harness/tasklog/_check.py"  # the TLC001 withheld_after branch
      - "packages/eng-harness/tests/helpers/tasklog_git.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_withhold.py"
    max_changed_lines: 220
    max_sessions: 1
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_withhold.py::test_withhold_after_push"
    covers: [AC27]
    depends_on: [T7]
  - id: T8
    title: Commit helper
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_git.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_cli.py"  # commit
      - "packages/eng-harness/src/eng_harness/tasklog/_check.py"  # TLC008
      - "packages/eng-harness/tests/helpers/tasklog_git.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_commit.py"
    max_changed_lines: 280
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_commit.py::test_commit_only_log_paths"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_commit.py::test_commit_message_has_no_log_text"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_commit.py::test_main_checkout_untouched"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_commit.py::test_check_tlc008"
    covers: [AC14, AC25, AC24]   # AC24 in part: TLC008
    depends_on: [T7b]
  - id: T8b
    title: Log-only push helper (the ADR-0034 D6 exception)
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_push.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_cli.py"  # push; the status unpushed line
      - "packages/eng-harness/src/eng_harness/tasklog/_check.py"  # TLC011 on _scope.py, TLW004
      - "packages/eng-harness/tests/helpers/tasklog_git.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_push.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_push.py::test_push_disabled"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_push.py::test_push_requires_hook"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_push.py::test_push_exact_refspec"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_push.py::test_push_refuses_mixed_range"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_push.py::test_push_refuses_rename_into_tasklog"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_push.py::test_push_rebase_retry_once"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_push.py::test_push_offline_keeps_local"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_push.py::test_check_tlc011"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_push.py::test_check_tlw004"
    covers: [AC26, AC24]   # AC24 in part: TLC011, TLW004
    depends_on: [T8]
  - id: T9
    title: attach-run core
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_runfacts.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_cli.py"  # attach-run
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_attach_run.py"
    max_changed_lines: 360
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_attach_run.py::test_attach_idempotent_incremental"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_attach_run.py::test_runfacts_values_by_reference"
    covers: [AC21, AC23]
    depends_on: [T8b]
  - id: T10
    title: Need derivation from runs
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_runneeds.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_check.py"  # TLC006, TLC010
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_runfact_mapping.py"
    max_changed_lines: 340
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_runfact_mapping.py::test_runfact_mapping"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_runfact_mapping.py::test_check_tlc006"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_runfact_mapping.py::test_check_tlc010"
    covers: [AC22, AC24]   # AC24 in part: TLC006, TLC010
    depends_on: [T9]
  - id: T11
    title: The --task option of run and resume, and require_task
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/cli/_parser.py"  # the option only
      - "packages/eng-harness/src/eng_harness/cli/__init__.py"  # handler call sites
      - "packages/eng-harness/src/eng_harness/cli/_run.py"  # attach at start and at exit
      - "packages/eng-harness/src/eng_harness/cli/_options.py"  # task reserved against generated options
      - "packages/eng-harness/src/eng_harness/tasklog/_runlink.py"
      - "packages/eng-harness/tests/helpers/cli_deps.py"  # task-log fields of the shared builder
      - "packages/eng-harness/tests/workflow/test_tasklog_run_link.py"
      - "packages/eng-harness/tests/unit/cli/test_tasklog_task_option.py"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/test_tasklog_run_link.py::test_run_task_link"
      - "packages/eng-harness/tests/workflow/test_tasklog_run_link.py::test_require_task_refuses"
      - "packages/eng-harness/tests/workflow/test_tasklog_run_link.py::test_no_section_exempt"
      - "packages/eng-harness/tests/unit/cli/test_tasklog_task_option.py::test_generated_option_task_reserved"
    covers: [AC28, AC36]
    depends_on: [T10]   # and plan 0006 T14, T14b, T18a and T18b merged (section 3)
  - id: T12
    title: Needs, triage, release-public, answered, digest
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/_needs.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_cli.py"  # needs, triage, release-public, answered, digest
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_triage.py"
    max_changed_lines: 360
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_triage.py::test_triage_containment"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_triage.py::test_public_en_needs_release"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_triage.py::test_digest_containment"
    covers: [AC17, AC29, AC30]   # AC17 in part: the hint's source, the triage files
    depends_on: [T10]   # deferred until the first triage session needs it (section 2)
  - id: T13
    title: Sanitized policy and export
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/tasklog/privacy/_sanitized.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_export.py"
      - "packages/eng-harness/src/eng_harness/tasklog/_cli.py"  # export
      - "packages/eng-harness/src/eng_harness/_placeholders.py"  # the placeholder mapper factored out of servers/_record.py
      - "packages/eng-harness/src/eng_harness/servers/_record.py"
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_sanitized.py"
    max_changed_lines: 370
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/tasklog/test_tasklog_sanitized.py::test_transform_pure_shared"
    covers: [AC9]
    depends_on: [T2, T12]   # and plan 0002 T17 merged; deferred until the owner plans publication (section 2)
  - id: T14
    title: Package rule and local testing
    files:
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/.gate/agents.yml"
      - "packages/eng-harness/AGENTS.md"
      - "packages/eng-harness/docs/local-testing.md"
    # A docs pull request, exempt from test-first like plan 0006 T17b; AGENTS.md is generated and not counted.
    max_changed_lines: 150
    max_sessions: 1
    covers: []
    depends_on: [T8b]
---

# Implementation plan: eng-harness task log

## 1. Approach

The spec is [0015](../specs/0015-task-log.md), under [ADR-0034](../../../../design/docs/adr/0034-task-log-by-default.md).
`max_changed_lines` counts non-test, non-generated lines (process/04 §4); tests and snapshots are on top, and no task
is above 380. The order puts the pieces every later task relies on for safety first: the closed record model, the
guard, the append-only store and the worktree checks, then the single log-only implementation and the pre-push hook
(T8h) before any command that commits or pushes. The run facts (T9, T10) read the merged journal reader and report
model only. The lane runs in parallel with the first live run and is never on its critical path (ADR D14); until T8b
merges, task logs are written by hand in the interim format (ADR D13).

Paths in the front matter are repository-relative. Every task that changes source lists `CHANGELOG.md`. New test file
names start with `test_tasklog_` (basenames must be unique; spec §3). Git tests use temporary repositories and a bare
remote built by `tests/helpers/tasklog_git.py`.

Risk: `[r2, r3]`. T1 edits `packages/eng-harness/pyproject.toml` (floor `**/pyproject.toml`, r3) and adds
`src/eng_harness/tasklog/_scope.py`, `_hook.py` and `_push.py` to the r2 entry of `packages/eng-harness/.gate/risk-map.yml`
and to `r2_modules` (mutation), so T8h and T8b are r2 without editing either file again. The package `.gate/` files
carry no floor of their own (the root `.gate/**` glob matches the root folder only; checked with the gate's glob
matcher), but `**/.gate/` is a CODEOWNERS path, so T1 and T14 need the owner's review. No task writes under
`docs/schema/` (the record snapshot is a test snapshot). No r1 path is touched.

## 2. Tasks

- **T1** creates the package `eng_harness.tasklog` with the frozen record models of spec §4.3, the schema snapshot,
  the static test that block, rule and workflow modules never import the package (FB004 cannot name a submodule), and
  the public-module and r2 entries.
- **T2** adds the guard (the gate's secret rule names and patterns, the launch address, tokens) with the vector file
  copied from the gate's test samples and pinned by hash, the `PrivacyPolicy` protocol, `full`, and `sanitized` as gap
  `TL-G1`. A property test checks that no generated secret survives the guard.
- **T3a** adds the store: append under the task's `RunLock` kept in `.eng/tasklog/locks/`, fsync, chain, consecutive
  seq, the 900 000-byte cap and the closed-task rules; `_ids.py` forms task and need ids from `eng_contract.ids`.
  `RunLock` does not wait, so a concurrent writer is refused with exit 4.
- **T3b** adds the read-only worktree checks of spec AC13 and the git test helper.
- **T4a** adds `[tasklog]` to `HarnessConfig` (no `push` key) and the reader of the user-level push file, refused
  inside a git working tree. The spec 0006 §4.2.4 amendment is already in that spec (B-478).
- **T4b** starts the module entry point: `status`, `open`, `said`, `note`, `close` and a `render` stub, with strict
  UTF-8 said-files and the echo of text and hash.
- **T8h** comes before any committing command: `_scope.py` is the one implementation of the ADR D5 definition, and
  `_hook.py` holds the shipped hook text, `install-hook` and the in-place check. The agent's pushes with the owner's
  login wait for it (ADR D6).
- **T5** adds the remaining agent records and `add --batch`.
- **T6** renders STORY.md deterministically with fenced owner words.
- **T7** adds the completeness checks that need no git or runs.
- **T7b** adds `withhold` and the `withheld_after` branch of TLC001.
- **T8** adds `commit` (log identity, subject, trailer; TLC008).
- **T8b** adds `push` (the D6 exception), TLC011 and TLW004. With it the interim procedure ends.
- **T9** attaches runs: `run_attached` and `run_fact` from `JournalReader`, `fold_report` and the result store.
- **T10** derives needs from runs (the `not_found` rows of spec §4.8, the change-set check issues) and adds TLC006 and
  TLC010.
- **T11** adds `--task` to `run` and `resume`, `require_task`, the attach calls at start and exit, and the reserved
  `task` option name. It edits files that plan 0006 T14, T14b, T18a and T18b create or change, so it starts only after
  all four have merged and never edits a file an open critical-path task edits.
- **T12** adds needs, triage, `release-public`, answered and digest. **Deferred** until the first triage session needs
  it; a development session can read STORY.md meanwhile.
- **T13** implements `sanitized` and `export` on the placeholder mapper factored out of plan 0002 T17's
  `servers/_record.py` into `src/eng_harness/_placeholders.py`. **Deferred** until the owner defines the rules and plans
  publication.
- **T14** writes the package rule into `.gate/agents.yml` (re-rendered `AGENTS.md`) and the local-testing items:
  PowerShell said-files, the sparse worktree on its local branch, the user-level push file, `install-hook` by the owner
  and the shipped hook's SHA-256, the interim push form (spec Q3), offline work, rotation and `withhold`.

`src/eng_harness/tasklog/_cli.py` is edited by T4b, T8h, T5, T7, T7b, T8, T8b, T9, T12 and T13, so these tasks form
one chain in `depends_on` and no two of them are open at once.

## 3. Dependencies

No runtime or development dependency is added. Git is called as a subprocess. Cross-plan dependencies:

| Task | Needs merged first | Why |
|---|---|---|
| T9 | plan 0001 T4 (journal reader), plan 0006 T11 to T13 (report model) | merged |
| T10 | plan 0007 kinds `harness.change_set_check/1` | merged |
| T11 | plan 0006 T14 (B-188), T14b (B-353), T18a and T18b (B-433) | `cli/_run.py`, `cli/_options.py` and `tests/helpers/cli_deps.py` come with them; spec 0006 §4.2.1 carries the `--task` amendment (B-478) |
| T13 | plan 0002 T17 (B-136) | the record-mode sanitizer it factors out |
| T14 | plan 0006 T17b | the CLI agent rule in the same `.gate/agents.yml` |
| — | eng-dev-gate plan 0001 (GC017, `push-scope`, `tasklog-lint`, `publish-check`) | they apply the same log-only definition after the push; none blocks this plan |

## 4. Verification

Local gate per task (`uv run eng-gate check --package eng-harness`). All git behaviour is tested against temporary
repositories and a bare remote; no test pushes to a real remote or uses the owner's credentials. Local testing on the
owner's machine before the agent pushes with his login: the T14 items (Windows said-file round trip, the sparse
worktree, `install-hook`, one `push` of a log-only commit, the hook refusing a mixed commit).

## 5. Rollback

Each task is one pull request and reverts by a new commit. Removing the `[tasklog]` section turns logging off without
a code change; logs already pushed stay in `tasklog/` (never deleted or rewritten, ADR D5, D9).
