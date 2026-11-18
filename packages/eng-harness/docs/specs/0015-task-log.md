---
id: spec-0015-task-log
issue: "B-478"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r2, r3]
---

# Spec 0015: eng-harness task log (`python -m eng_harness.tasklog`)

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-14
Source needs: none (the owner's decisions of 2026-11-12 recorded in ADR-0034)

This spec builds the harness side of [ADR-0034](../../../../design/docs/adr/0034-task-log-by-default.md) ("ADR D<n>"):
every task the owner asks of the agent has one task log under the root folder `tasklog/` of the workspace repository,
written in a git-ignored log worktree and pushed directly to the integration branch as log-only commits. The ADR is
the governing decision; where this spec and the ADR differ, the ADR wins. It is `Proposed`, so this spec cannot be
approved before the owner accepts it. The spec composes, and does not repeat: the engine
[spec 0001](0001-engine.md) ("engine §n"), the command line [spec 0006](0006-cli-progress-pages-report.md) ("CLI §n"),
which this spec amends (§4.6, §4.5.3), the edit cycle [spec 0007](0007-model-edit-cycle.md), and the hand-written
interim format [task-log-interim.md](../../../../design/process/templates/task-log-interim.md) ("interim template").
The gate side (GC017, `push-scope`, `tasklog-lint`, `publish-check`) belongs to the eng-dev-gate spec and plan, not
here. Names of existing code were checked on `build/v1` at `5dff5d8`.

## 1. Problem

The run journal (`<workspace>/runs/<run_id>/journal.sqlite`, engine §4.4) records work that reaches a run. A request
that never reaches a run leaves nothing: a refusal before a run creates no run folder (CLI AC6), a missing workflow is
told to the owner and forgotten, and the development session that should build the missing capability has no record of
what was asked, what was searched and what was not found. "Session report" is named by process/01 §9 and ADR-0026 but
not defined. The owner asked for a log of every task that "tells the whole story, and what the agent did not find",
kept in the repository and travelling through git (ADR context, answers 4 and 7).

## 2. Reuse research

| Existing | Use here |
|---|---|
| `eng_harness.journal.JournalReader(run_dir)` (read-only, chain-verifying; `events(after_seq)`, `header()`, `run()`, `models()`) | run facts are read through it; no journal change, no new event type (ADR alternatives) |
| `eng_harness.report._model.fold_report(reader, store)` with `store` an `eng_contract.store.ResultStore` | `run_attached.timings` from `ReportModel.timings` (`machine_ms`, `waiting_ms`, `resumes`), `event_count`, `chain_sha256` |
| `RunHeader.unreleased_tools`, `RunView.status`, `ApprovalResolved.reason` and `item_reasons`, `RunEscalated.reason` | copied into `run_attached` and `run_fact` |
| `eng_harness.kinds.edit_cycle.ChangeSetCheck` (`harness.change_set_check/1`, `issues[]` of `Issue {item_id, severity, code, detail, gap}`) | needs derived from a check result (§4.8). `Issue` has no `kind`; the kind is taken from the `resolved` item with the same `item_id` when one exists |
| `eng_contract.ids.Clock` and `IdSource.new_ulid()` | task and need ids, injected (tests use `FixedClock`, `SeededIdSource`) |
| `eng_contract.canonical.canonical_json` | one canonical JSON object per record line |
| `eng_harness._runlock.RunLock(dir)` (non-blocking exclusive lock on `<dir>/run.lock`, raises `RunLocked`) | the append lock, kept in local state (§4.2); it does not wait, so a second writer is refused, not queued |
| `eng_harness._text` (`format_timestamp`, `sanitize_terminal`, `truncate`) | STORY.md and terminal text |
| `eng_harness.cli._exit.ExitCode` | the exit codes of every sub-command (§6) |
| gate `checks/secrets.py` `RULES` (nine rules, `personal-path` included) and its 12-digit fingerprint | the guard uses the same rule names and patterns; a vector file copied from the gate's test samples is pinned by a test (AC7); the harness never imports eng-dev-gate |
| record-mode sanitizer of [spec 0002](0002-servers-and-adapters.md) §4.8.1 (plan 0002 T17, `servers/_record.py`, not merged) | the planned base of the `sanitized` policy (T13), factored out into a shared placeholder mapper |

No library is added. Git is called as a subprocess (`git` on the path), only from the store's worktree checks, `commit`,
`push`, `install-hook` and `status`.

## 3. Acceptance criteria

Tests live in `tests/unit/tasklog/` (git tests build temporary repositories and a bare remote there),
`tests/unit/cli/`, `tests/rules/`, `tests/property/` and `tests/workflow/`. Every new test file name starts with
`test_tasklog_`, because test basenames must be unique (no `__init__.py`; mypy names a module by its basename).

### 3.1 Records, guard, store

- AC1. Given the record model, then the `kind` set and the `not_found.category` set are closed and an unknown field is
  refused. Test: `tests/unit/tasklog/test_tasklog_records.py::test_kind_set_closed`, `::test_extra_forbidden`.
- AC2. Given Arabic owner words, when stored and read back, then they are byte-exact and `text_sha256` is the SHA-256
  of the input bytes. Test: `tests/unit/tasklog/test_tasklog_records.py::test_owner_words_bytes_exact_arabic`.
- AC3. Given a said-file with invalid UTF-8 or U+FFFD, then exit 3; a leading BOM is stripped and recorded. Test:
  `tests/unit/tasklog/test_tasklog_cli_open_close.py::test_said_file_strict_utf8`.
- AC4. Given a hard secret in owner words, then the span is withheld with a marker and a `redactions` entry, the record
  is written and `text_sha256` keeps the original's hash. Test:
  `tests/unit/tasklog/test_tasklog_guard.py::test_owner_secret_withheld_not_dropped`.
- AC5. Given a personal path in owner words, then it is withheld the same way and the stored line passes the gate's
  `personal-path` rule. Test: `tests/unit/tasklog/test_tasklog_guard.py::test_owner_personal_path_withheld`.
- AC6. Given a secret in an agent `*_en` field, then exit 3 naming the field and the rule, without echoing the text.
  Test: `tests/unit/tasklog/test_tasklog_guard.py::test_agent_secret_refused_no_echo`.
- AC7. Given the guard's vector file, then it equals the gate's secret samples, pinned by hash. Test:
  `tests/unit/tasklog/test_tasklog_guard.py::test_guard_vectors_match_gate`.
- AC8. Given `[tasklog]` without `policy`, or with an unknown name, then it is refused; `sanitized` raises gap `TL-G1`.
  Test: `tests/unit/tasklog/test_tasklog_policy.py::test_policy_required`, `::test_sanitized_gap_tl_g1`.
- AC9. Given a policy, then `transform` is pure and the same function serves writing and `export`. Test:
  `tests/unit/tasklog/test_tasklog_sanitized.py::test_transform_pure_shared` (deferred with T13).
- AC10. Given appends, then they are chained and consecutive under the lock; two concurrent appends never interleave:
  one is written and the other is refused with exit 4 and writes nothing; appends to a triage file are chained and
  seq-numbered the same way under the need's lock (§4.2, §4.3.1). Test:
  `tests/unit/tasklog/test_tasklog_store.py::test_concurrent_append_never_interleaves`,
  `::test_triage_append_chain_and_lock`.
- AC11. Given a closed task, then only harness `run_attached` and `run_fact` records of runs already attached, and
  `withheld_after`, are accepted. Test: `tests/unit/tasklog/test_tasklog_store.py::test_closed_task_rules`.
- AC12. Given an append that would take `records.jsonl` past 900 000 bytes, then `TASKLOG_FULL`, exit 3. Test:
  `tests/unit/tasklog/test_tasklog_store.py::test_size_cap`.
- AC13. Given `[tasklog] worktree`, then it must be a git worktree of the same repository, inside the repository
  directory, outside `runs/`, sparse (only `tasklog/` and `.gate/` checked out), with HEAD on the local branch
  `eng-tasklog`, which has no upstream and contains the merge base with `origin/<integration_branch>`; a detached HEAD,
  another branch, the owner's main checkout, a full checkout or a path outside the repository is refused. Test:
  `tests/unit/tasklog/test_tasklog_worktree.py::test_worktree_refusals`.
- AC14. Given any sub-command, then nothing is written, staged or checked out in the owner's main checkout. Test:
  `tests/unit/tasklog/test_tasklog_commit.py::test_main_checkout_untouched`.

### 3.2 Commands

- AC15. Given `open`, then it prints the task id and echoes the stored text and its hash. Test:
  `tests/unit/tasklog/test_tasklog_cli_open_close.py::test_open_echo`.
- AC16. Given `search` while the workflow registry module is absent, then `catalog: unavailable` is recorded. Test:
  `tests/unit/tasklog/test_tasklog_cli_records.py::test_catalog_unavailable_is_recorded`.
- AC17. Given `missing`, then it returns a need id and names the release of a matching answered need, read from the
  triage files through the `harness.tasklog_triage/1` model (§4.3.1). Test:
  `tests/unit/tasklog/test_tasklog_cli_records.py::test_missing_answered_hint` (fixture triage lines written by the
  test).
- AC18. Given `refused`, then unknown workflow, `BASIS_INCOMPLETE` and "not available in this build" map to
  `no_workflow`, `value_without_source` and `harness_unavailable`. Test:
  `tests/unit/tasklog/test_tasklog_cli_records.py::test_refused_mapping`.
- AC19. Given `add --batch`, then all records are written under one lock, or none. Test:
  `tests/unit/tasklog/test_tasklog_cli_records.py::test_batch_atomic`.
- AC20. Given identical records, then STORY.md is byte-identical, LF, UTF-8 without BOM; owner words are in fenced
  blocks whose fence is longer than any backtick run in the text, byte-exact inside, also when they hold HTML, Markdown
  or backticks; the gloss is labelled. Test: `tests/unit/tasklog/test_tasklog_render.py::test_render_deterministic`,
  `::test_render_fenced_words_and_gloss`.
- AC21. Given `attach-run` twice, or after more events, then it is idempotent and incremental by `last_seq`, also on a
  fixture journal after the fact. Test: `tests/unit/tasklog/test_tasklog_attach_run.py::test_attach_idempotent_incremental`.
- AC22. Given a fixture for each row of §4.8, then the derived records are those of the row. Test:
  `tests/unit/tasklog/test_tasklog_runfact_mapping.py::test_runfact_mapping` (one parameter per row).
- AC23. Given derived records, then they hold values only by reference, and messages are guarded and capped. Test:
  `tests/unit/tasklog/test_tasklog_attach_run.py::test_runfacts_values_by_reference`.
- AC24. Given each check TLC001 to TLC011 and warning TLW001 to TLW004, then a pass case and a fail case exist. Test:
  `test_check_<code>` in the test file of the task that adds the check (plan 0015).
- AC25. Given `commit`, then it stages only the named task folders under `tasklog/`, uses the fixed log identity,
  writes the subject `docs(tasklog): <task_id> <status>` with no other log text plus the trailer, and never fetches or
  pushes. Test: `tests/unit/tasklog/test_tasklog_commit.py::test_commit_only_log_paths`,
  `::test_commit_message_has_no_log_text`.
- AC26. Given `push`:
  it is refused when the user-level push file is absent, says `push = false` or lies inside a git working tree, and
  when the pre-push hook is missing or differs from the shipped text, printing nothing it would run with a credential
  (`tests/unit/tasklog/test_tasklog_push.py::test_push_disabled`,
  `tests/unit/tasklog/test_tasklog_pushconf.py::test_push_file_inside_repo_refused`,
  `tests/unit/tasklog/test_tasklog_push.py::test_push_requires_hook`); a `push` key in `[tasklog]` is an unknown key
  (`tests/unit/cli/test_tasklog_config.py::test_harness_toml_push_key_refused`); it is refused, pushing nothing, when
  `[tasklog] integration_branch` differs from the push file's `integration_branch`
  (`tests/unit/tasklog/test_tasklog_push.py::test_push_branch_mismatch_refused`) or the log worktree's `origin` URL
  differs from the push file's remote URL (`::test_push_remote_mismatch_refused`); it fetches only
  `refs/heads/<integration_branch>` and pushes only `HEAD:refs/heads/<integration_branch>`, without `--force` or
  `--no-verify` (`tests/unit/tasklog/test_tasklog_push.py::test_push_exact_refspec`, a fake remote that records the
  commands; the following tests are in the same file); it refuses, pushing nothing,
  when an unpushed commit is not log-only, naming the commit and the path (`::test_push_refuses_mixed_range`), a commit
  that renames a file from outside into `tasklog/` included (`::test_push_refuses_rename_into_tasklog`); after a
  non-fast-forward rejection it rebases its own log-only commits with the log identity as committer and retries once,
  and a second rejection leaves them local with exit 3 (`::test_push_rebase_retry_once`); offline it leaves them local
  and `status` lists them (`::test_push_offline_keeps_local`).
- AC27. Given `withhold`, then exactly the named span is replaced by the marker and `withheld_after` is appended in the
  same log-only commit, and TLC001 passes; any other change to an earlier line fails TLC001. Test:
  `tests/unit/tasklog/test_tasklog_withhold.py::test_withhold_after_push`.
- AC28. Given `run --task`, then the run is attached at start and at exit, exit 10 and 130 included; with
  `require_task = true` a `run` without an open task is refused with exit 2 and no run folder; with no `[tasklog]`
  section nothing is refused or logged. Test: `tests/workflow/test_tasklog_run_link.py::test_run_task_link`,
  `::test_require_task_refuses`, `::test_no_section_exempt`.
- AC29. Given `triage`, then it writes only `tasklog/triage/<need_id>.jsonl`, requires `--public-en` and the
  development-session identity, and refuses a `public_en` holding a project label or model base name known from the
  need's task; a `public_en` without the owner's release (`release-public`) is never printed by `digest` or any other
  output meant to leave `tasklog/`; a guard hit in any free-text field of a triage line is refused with exit 3 naming
  the field and the rule, without echoing the text, and nothing is written. Test:
  `tests/unit/tasklog/test_tasklog_triage.py::test_triage_containment`, `::test_public_en_needs_release`,
  `::test_triage_free_text_guard_refused`.
- AC30. Given `digest`, then it holds only ids, categories, counts and released `public_en`. Test:
  `tests/unit/tasklog/test_tasklog_triage.py::test_digest_containment`.
- AC31. Given every sub-command, then no sub-command or option accepts an engineering approval, rejection, sign-off or
  engineer name. Test: `tests/unit/tasklog/test_tasklog_cli_open_close.py::test_no_approval_surface`.
- AC32. Given block, rule and workflow modules, then none imports `eng_harness.tasklog` (a static import test; FB004
  matches top-level module names only). Test: `tests/rules/test_tasklog_imports.py::test_blocks_do_not_import_tasklog`.
- AC33. Given `eng-harness --help`, then CLI AC1 still lists exactly six commands; its existing test stays green.
- AC34. Given temporary repositories, then the log-only test follows ADR D5 exactly: accepted are `A` or `M` of a log
  path, mode `100644`, within the cap; refused are a rename of `src/code.py` into `tasklog/`, a deletion under
  `tasklog/`, `tasklog/POLICY.json`, `tasklog/README.md`, `tasklog/.gitattributes`, a symlink, an executable bit, a
  gitlink, a file over 900 000 bytes, a NUL byte, invalid UTF-8 and a commit with two parents. Test:
  `tests/unit/tasklog/test_tasklog_scope.py::test_log_only_definition`.
- AC35. Given the shipped pre-push hook, then it refuses a push to `refs/heads/<integration_branch>` whose range holds a
  commit that is not log-only (the rename case included), lets a log-only range through, ignores pushes to other refs
  and imports nothing from the working tree; it takes `<integration_branch>` only from the user-level push file, never
  from `harness.toml`, so a different `[tasklog] integration_branch` does not move the guarded ref; when the push file
  is absent, invalid or inside a git working tree, it guards both `refs/heads/build/v1` and `refs/heads/main`; the
  definitions it embeds equal the sources of `_scope.py` and `_pushconf.py`; `install-hook` refuses to replace a
  different existing hook; `status` reports whether the installed hook equals the shipped text. Test:
  `tests/unit/tasklog/test_tasklog_hook.py::test_hook_refuses_non_log_only`, `::test_hook_self_contained`,
  `::test_hook_branch_from_push_file_only`, `::test_hook_fails_closed_without_push_file`,
  `::test_hook_embeds_module_sources`, `::test_install_hook_refuses_foreign`, `::test_status_hook_in_place`.
- AC36. Given a workflow whose options model has a top-level field `task`, then option generation refuses it with a
  usage error naming the field (`--task` cannot collide with CLI AC14). Test:
  `tests/unit/cli/test_tasklog_task_option.py::test_generated_option_task_reserved`.
- AC37. Given the triage model, then the `kind` set and the `outcome` set are closed, an unknown field is refused,
  `duplicate_of` is required exactly when the outcome is `duplicate`, and a `public_released` line applies only to the
  `public_en` whose SHA-256 it names. Test: `tests/unit/tasklog/test_tasklog_records.py::test_triage_model_closed`,
  `::test_release_binds_text_hash`.
- AC38. Given `commit --need`, then it stages only the named needs' triage files and writes the subject
  `docs(tasklog): triage <need_id>`; given `withhold --need`, then the span is replaced in the triage line and
  `withheld_after` is appended to the same triage file in one log-only commit with that subject, and TLC001 passes;
  TLC001 (schema, chain, seq, the `withheld_after` branch) and TLC009 (the guard re-run) check triage files as they
  check `records.jsonl`. Test: `tests/unit/tasklog/test_tasklog_triage_commit.py::test_commit_need_only_triage_file`,
  `::test_withhold_need_in_triage_file`, `::test_check_tlc001_triage_chain`, `::test_check_tlc009_triage`.
- AC39. Given `close` while TLC002 or TLC004 fails, then it is refused with exit 3 naming the check and writes nothing.
  Test: `tests/unit/tasklog/test_tasklog_check.py::test_close_refused_while_incomplete`.
- AC40. Given a run folder created after `since` that no task has attached, then `status` lists it under unattached
  runs (the TLC006 rule). Test: `tests/unit/tasklog/test_tasklog_runfact_mapping.py::test_status_unattached_runs`.

## 4. Design

### 4.1 Scope

The record model; the guard and privacy policies; the store in the log worktree; the module command line; run facts
derived read-only from `JournalReader` and the result store; completeness checks; the commit helper, the log-only push
helper (the D6 exception) and the owner-installed pre-push hook (its text, `install-hook`, the in-place check); the
post-push withholding path; triage, answered and digest; the `--task` option of `run` and `resume` and
`require_task`; the amendments of CLI §4.2.4 (`[tasklog]`) and §4.2.1 (`--task`; AC1's six commands unchanged).

### 4.2 Folder, naming, files (root folder `tasklog/` on the integration branch)

```
tasklog/README.md                                  (workspace rules change, once; never a log path, ADR D9)
tasklog/POLICY.json                                (same; changed only by an owner step)
tasklog/tasks/<yyyy>/<mm>/<task_id>/records.jsonl  (source of truth, append-only)
tasklog/tasks/<yyyy>/<mm>/<task_id>/STORY.md       (derived, rendered after each append; interim-1 tasks: hand-written)
tasklog/triage/<need_id>.jsonl                     (development session only, append-only; §4.3.1)
```

- `task_id` is `task_` plus a ULID from the injected `IdSource`; `need_id` is `need_<task ULID>_<n>`. Folder names
  carry no slug or owner words (they reach commit subjects and `git log --stat`).
- Paths inside records are repository-relative or workspace-relative (`runs/<run_id>/report/report.html`), never
  absolute. No shared index file exists (it would conflict between machines); listings are computed on read.
- Local state, written by the harness and never committed, under `<repo>/.eng/tasklog/` (git-ignored by the existing
  `.eng/` rule): `current.json` (the open task for calls without `--task` or `ENG_TASK_ID`), `in/` (agent input
  files), `locks/<task_id>/run.lock` (the append lock, outside the worktree so it can never be staged), `map.json`
  (sanitized placeholders, later) and the log worktree `worktree/`.
- Files are UTF-8 without BOM, LF, one canonical JSON object per line (`canonical_json`), appended with fsync while
  the task's `RunLock` is held (a triage file: the need's lock, `locks/<need_id>/run.lock`). `RunLock` does not wait:
  a second writer gets `RunLocked` and the command exits 4 (`RUN_LOCKED`) having written nothing.
- An append that would take `records.jsonl` past 900 000 bytes is refused with exit 3, `TASKLOG_FULL`; the agent
  closes the task and opens a continuation with `--continues`. `render` refuses the same way when STORY.md would pass
  900 000 bytes. No log file reaches the gate's 1 MiB scan limit (SC002), so the secrets scan never skips one (ADR D5).

### 4.3 Records: `harness.tasklog_record/1`

Pydantic, frozen, `extra="forbid"`, closed `kind` set; a schema snapshot `tests/data/snapshots/tasklog/record-1.json`
is pinned by a test against `model_json_schema()` (eng-harness has no `docs/schema/` folder and no generator).

**Common fields:** `schema` (`"harness.tasklog_record/1"`), `task_id`, `seq` (1..n, consecutive), `at` (UTC
`YYYY-MM-DDTHH:MM:SSZ`, injected clock), `kind`, `by` (`agent:<tool>`, `harness` or `dev-session:<work item>`),
`policy` (`full` or `sanitized`), `redactions` (list of `{field, rule, start, end, span_sha256}`), `prev_sha256`
(SHA-256 of the previous line as first written; 64 zeros for seq 1).

| kind | by | fields |
|---|---|---|
| `task_opened` | agent | `title_en` (≤200), `agent {tool, model_line?}` (family and line only, no version identifier), `session {place: local\|cloud, tool_session_id?, transcript_sha256?}`, `repo_commit`, `integration_branch`, `harness_version`, `continues?`, `project_label?` |
| `owner_words` | agent (attested) | `role: request\|correction\|clarification\|answer`, `lang` (BCP 47, required), `text` (verbatim, ≤20 000 characters), `text_sha256` (of the original bytes, before any withholding), `gloss_en?` |
| `narration` | agent | `text_en` (≤4 000) |
| `searched` | agent | `for_en`, `where: workflow_registry\|allowlist\|edit_kinds\|calcs\|code_pack_checks\|cli_tools\|project_lane_tools\|specs\|docs\|other`, `result: found\|partial\|not_found`, `detail_en`, `refs[]`, `catalog: available\|unavailable` |
| `not_found` | agent or harness | `need_id`, `category`, `need_en`, `target?`, `gap_id?`, `code?` (`ErrorCode`, `HarnessCode` or exit code), `evidence[]` (`#<seq>`, `run:<run_id>#seq=<n>`, `res_…#/ptr`, repository path), `detail? {kind?, field?, step_path?, message_en?}` (embedded, so a cloud session needs no workspace), `blocking`, `words_ref?` |
| `did_instead` | agent | `way: harness_workflow\|owner_by_hand\|partial\|deferred\|nothing`, `text_en`, `refs[]` (input files by repository path and SHA-256) |
| `problem` | agent | `text_en`, `evidence[]` (a defect, not a missing capability) |
| `handoff` | agent | `to: owner\|next_session\|dev_session`, `done_en`, `left_en`, `why_en` |
| `run_refused` | agent or harness | `workflow`, `exit_code`, `code`, `missing[]` (basis paths), `message_en` |
| `run_attached` | harness | `run_id`, `workflow`, `status` (`RunView.status`), `exit_code?`, `event_count`, `last_seq`, `chain_sha256`, `report` (workspace-relative, local only), `unreleased_tools{}`, `timings {machine_ms, waiting_ms, resumes}`, `model_files[]` (base names; `full` only) |
| `run_fact` | harness | `run_id`, `journal_seq`, `event`, `summary_en`, `code?`, `gap?`, `field?`, `reason?`, `owner_text?` (approval reasons; `full` only) |
| `task_closed` | agent | `status: DONE\|DONE_WITH_CONCERNS\|BLOCKED\|NEEDS_CONTEXT\|WITHDRAWN`, `summary_en`, `open_needs[]`, `next_en?` |
| `withheld_after` | harness | `target_seq`, `field`, `rule`, `span_sha256`, `line_sha256_before`, `reason_en` (§4.4) |

**Append rules:** `task_opened` first, then `owner_words` with `role=request`. After `task_closed` only harness
`run_attached` and `run_fact` of runs already attached (a run that ends after the close, exit 10 then a later resume,
still gets its final status) and `withheld_after` are accepted; a correction after the close opens a new task with
`continues`.

**`not_found.category` (closed):** `no_workflow`, `tool_not_on_allowlist`, `no_edit_kind`, `not_implemented` (needs a
gap id), `no_calc`, `calc_not_approved`, `no_code_pack_check`, `host_limitation`, `server_limitation`,
`value_without_source`, `harness_unavailable` ("not available in this build", exit 2), `harness_defect` (exit 70 or 5,
or an `unhandled_error` escalation), `other` (`need_en` of at least 40 characters; triage recategorises it). The kinds
and categories are those of the interim template.

**Numbers rule.** No `*_en` field states an engineering value. A digit followed by a unit token, or a decimal number,
in a `*_en` field is warning TLW001, listed by `check`. A value appears only inside verbatim owner words, or by
reference to a recorded result (ADR D12).

#### 4.3.1 Triage lines: `harness.tasklog_triage/1`

Same conventions as §4.3 (frozen, `extra="forbid"`, closed `kind` set, snapshot
`tests/data/snapshots/tasklog/triage-1.json`). One file per need; its lines are chained and seq-numbered exactly like
`records.jsonl`, and TLC001 and TLC009 check them the same way.

**Common fields:** `schema` (`"harness.tasklog_triage/1"`), `need_id`, `seq`, `at`, `kind`, `by`
(`dev-session:<work item>` or `harness`), `redactions`, `prev_sha256`.

| kind | by | fields |
|---|---|---|
| `triaged` | dev-session | `outcome: new_spec\|covered\|host_limitation\|out_of_scope\|duplicate\|defect` (process/02 §5 plus `duplicate` and `defect`), `public_en`, `public_en_sha256` (of its UTF-8 bytes), `work_item?` (`B-<n>`), `issue?`, `spec?`, `plan?` (repository paths), `duplicate_of?` (a need id; required exactly when `outcome` is `duplicate`) |
| `public_released` | dev-session | `public_en_sha256` (the exact text released), `public_en_released: owner`, `released_on` (UTC date), `reply_sha256` (of the owner's reply file) |
| `answered` | dev-session | `release` (`DIST==VER`), `commit` (40 hex digits) |
| `withheld_after` | harness | as in §4.3 |

A later `triaged` line replaces the earlier triage; its `public_en` is unreleased until a `public_released` line names
its `public_en_sha256`. A `public_en` leaves `tasklog/` (`digest`, any output meant to leave it) only when the latest
`triaged` line's `public_en_sha256` has a later `public_released` line (A24). Every free-text field of a triage line is
agent-written: a guard hit is refused as for an agent `*_en` field (§4.4), and the numbers rule applies. A secret found
in a triage line after it was committed is withheld with `withhold --need` (§4.4).

### 4.4 Guard and privacy policy (`eng_harness.tasklog.privacy`, ADR D7)

```python
class PrivacyPolicy(Protocol):
    name: Literal["full", "sanitized"]
    publishable: bool
    def transform(self, record: TaskRecord, ctx: PolicyContext) -> TaskRecord: ...  # pure
POLICIES: Mapping[str, Callable[[PolicyConfig], PrivacyPolicy]]
def policy_for(cfg: TasklogConfig) -> PrivacyPolicy   # unknown name: refused, exit 3
```

**The guard** (`_guard.py`, always first, not replaceable) uses the rule names and patterns of the gate's secrets
rules; it also covers the page launch address, `?code=`, session and CSRF tokens, `key_ref` and `base_url` values. The
marker is `<withheld:<rule>:<12 hex digits of the span's SHA-256>>`.

| Where the hit is | What happens |
|---|---|
| Agent `*_en` fields | refused with exit 3, naming the field and the rule, never echoing the text; the agent rephrases |
| Harness-derived text (messages, details) | the span is withheld with the marker and a `redactions` entry |
| Owner words: hard secret shapes (tokens, keys, private keys, credential assignments) and personal paths | the span is withheld with the marker; `text_sha256` keeps the original's hash; STORY.md shows the marker; the tool tells the agent, which tells the owner. The only deviation from byte-exact (ADR D7, D10) |
| A line found after commit, not yet pushed | the agent tells the owner; with his consent the tool rewrites the unpushed local commit (never shared) |
| A line found after push (`check`, or the lead's local CI) | the owner rotates the credential at once; `withhold --task T --seq N --field F --rule R` replaces the span in that line by the marker and appends `withheld_after` in one log-only commit (subject `docs(tasklog): withhold <task_id>`); in a triage file, `withhold --need NEED --seq N --field F --rule R` does the same and commits with the subject `docs(tasklog): triage <need_id>` (ADR D5 has no withhold form for a need); TLC001 checks the line against `line_sha256_before`. The history keeps the original inside the private repository (ADR D9); never a force push, never a secrets allow entry |

**Policies:** `full` is identity. `sanitized` raises `NotImplementedGap` `TL-G1` until the owner defines its rules;
its planned base is the placeholder mapper of the record-mode sanitizer (spec 0002 §4.8.1), factored out into a
shared module, treating every free-text field as unsafe, with its map only in `<repo>/.eng/tasklog/map.json`. With
`policy = "sanitized"` new records are transformed before writing; `export --policy sanitized --out DIR` writes a
sanitized copy outside the tracked files and never rewrites originals. Publishing it is a separate owner decision.

### 4.5 Commands

#### 4.5.1 Module entry point

`uv run --package eng-harness python -m eng_harness.tasklog <sub>` (ADR standing recommendation: a module entry point,
no seventh CLI command). Write sub-commands take `--task ID`, else `ENG_TASK_ID`, else `current.json`. Output is one
JSON line with `--json`, else a short text line. Exit codes are those of §6.

| sub | key options | writes |
|---|---|---|
| `status` | none | read-only: open tasks, unattached runs (the TLC006 rule), unpushed log-only commits, policy, push permission (from the user-level file), "hook in place" (the installed pre-push hook equals the shipped text) and the shipped hook's SHA-256. Run at session start |
| `open` | `--said-file F \| --said-stdin`, `--lang`, `--title`, `[--continues ID] [--project-label L] [--transcript-sha256 H] [--tool-session-id S]` | `task_opened` and `owner_words(request)`; echoes the stored text and `text_sha256` |
| `said` | `--role`, `--said-file \| --said-stdin`, `--lang`, `[--gloss]` | `owner_words` |
| `note` | `--text` | `narration` |
| `search` | `--for --where --result [--detail] [--ref]...` | `searched`; `catalog: unavailable` while the workflow registry (plan 0007 T9b) or allowlist module is absent in this build |
| `missing` | `--category --need [--target] [--gap-id] [--code] [--evidence]... [--blocking] [--words-ref]` | `not_found`; prints the `need_id` and, if an answered need matches (category plus target or gap id), the release that answered it |
| `refused` | `--workflow --exit-code --code [--missing PATH]...` | `run_refused` and `not_found` (unknown workflow: `no_workflow`; `BASIS_INCOMPLETE`: `value_without_source`; "not available in this build": `harness_unavailable`) |
| `instead` | `--way --text [--ref]...` | `did_instead` |
| `problem` | `--text [--evidence]...` | `problem` |
| `handoff` | `--to --done --left --why` | `handoff` |
| `add` | `--batch FILE \| -` (JSON lines of agent records without common fields) | many records under one lock |
| `attach-run` | `--run RUN_ID` | `run_attached`, derived `run_fact` and `not_found` (§4.8); incremental and idempotent by `(run_id, last_seq)`; works after the fact on any journal |
| `close` | `--status --summary [--next]` | `task_closed`; refused with exit 3 while TLC002 or TLC004 fails (AC39) |
| `render` | `[--task \| --all]` | STORY.md |
| `check` | `[--task \| --all \| --session SINCE \| --staged \| --unpushed]` | read-only, §4.10 |
| `commit` | `[--task ID ... \| --need NEED ...]` | §4.7; `--need` commits triage files, one commit per need |
| `install-hook` | none | §4.7; run by the owner himself, never by the agent |
| `push` | none (no remote, ref or refspec argument) | §4.7 |
| `withhold` | `--task \| --need`, `--seq --field --rule --reason` | §4.4; asks for the owner's consent first (security-sensitive, AGENTS §7) |
| `needs` | `[--state untriaged\|triaged\|answered] [--json]` | read-only, grouped by category and target or gap id |
| `triage` | `NEED --outcome new_spec\|covered\|host_limitation\|out_of_scope\|duplicate\|defect --public-en TEXT [--work-item B-n \| --issue N] [--spec P] [--plan P] [--duplicate-of NEED]` | a `triaged` line in `tasklog/triage/<need_id>.jsonl` (§4.3.1); development session only (`--as dev-session:<work item>`); `public_en` stored unreleased |
| `release-public` | `NEED --reply-file F` | a `public_released` line: the owner's release of the exact latest `public_en` (`public_en_released: owner`, the date, the SHA-256 of his reply written by the agent's file tool); a release of text, not an engineering approval (ADR D8) |
| `answered` | `NEED --release DIST==VER --commit SHA` | an `answered` line in the triage file |
| `digest` | `[--since DATE]` | read-only Markdown: ids, categories, counts, released `public_en` only (A24) |
| `export` | `--policy sanitized --out DIR` | sanitized copy (later, T13) |

No sub-command or option accepts an engineering approval, rejection, sign-off or engineer name.

#### 4.5.2 Encoding

`--said-file` is the documented path: the agent writes the file with its own file tool into `.eng/tasklog/in/`.
Decoding is strict UTF-8: a leading BOM is stripped and recorded; invalid UTF-8 or U+FFFD is refused with exit 3.
`--said-stdin` decodes the same way; a run of `?` in place of non-Latin text gives warning TLW002.

#### 4.5.3 `run` and `resume --task` (amends CLI §4.2.1)

`run` and `resume` gain one option, `--task ID` (default: `ENG_TASK_ID`, then `current.json`). With
`require_task = true`, a `run` without an open task is refused with exit 2 before any run folder exists. The handler
attaches the run (as `attach-run`) at start, once the run id exists, and at exit, exit 10 and 130 included. A workflow
options model with a top-level field named `task` is refused at option generation (AC36). Without a `[tasklog]`
section the option is accepted and ignored.

### 4.6 Configuration (amends CLI §4.2.4; unknown keys still refused)

```toml
[tasklog]
worktree = "<repo>/.eng/tasklog/worktree"   # absolute; inside the repository; the sparse log worktree (§4.7); refused under runs/
integration_branch = "build/v1"            # required: "build/v1" in bootstrap mode, "main" after it
policy = "full"                            # required, no default: "full" | "sanitized"
agent = "<coding tool name>"
require_task = true                        # required; true on the owner's machine (owner decision of 2026-11-12)
since = "<the date ADR-0034 merged>"       # start of the orphan-run check (TLC006)
```

With no `[tasklog]` section nothing is logged, nothing is pushed and no run is refused: tests, CI and acceptance
scripts are exempt (owner decision). There is no `push` key: the push permission is never read from `harness.toml`,
only from the owner's user-level push file `<user configuration folder>/eng-harness/tasklog-push.toml` (`%APPDATA%` on
Windows, `$XDG_CONFIG_HOME` or `~/.config` elsewhere; keys `push`, `integration_branch`, the remote URL), which the
owner writes himself and which the tool refuses when it resolves inside a git working tree (ADR D6). `push` and the
hook take the branch and the remote only from the push file: `[tasklog] integration_branch` (which the agent can edit)
serves writing (`task_opened`, the worktree checks, TLC011) and must equal the push file's value, else `push` is
refused; the log worktree's `origin` URL must equal the push file's remote URL, else `push` is refused (AC26).

### 4.7 Log worktree, commit, hook and push (ADR D4, D5, D6)

- **Worktree checks** (`_worktree.py`, read-only git): the rules of AC13; the owner's checkout, its branch, index and
  working tree are never switched, staged or changed.
- **Log-only.** `_scope.py` implements the single definition of ADR D5 over
  `git diff-tree -r -z --no-renames --raw <parent> <commit>` and the blob checks; it is pure over git output and is
  the one implementation `commit`, `push`, TLC011 and the hook text use. This spec does not restate the definition.
- **`commit`** works in the log worktree only: `git add` of the named task folders (`--task`) or the named needs'
  triage files (`--need`), `check --staged` (TLC008), then a
  commit with the fixed log identity `eng-agent task log <tasklog@localhost>` as author and committer, the subject
  `docs(tasklog): <task_id> <status>` (`OPEN` for a task not yet closed, else its `task_closed` status),
  `docs(tasklog): triage <need_id>` or `docs(tasklog): withhold <task_id>`, no other log text, and the `Assisted-by:`
  trailer of process/04 §3. It never fetches and never pushes.
- **`install-hook`** writes the shipped self-contained pre-push hook into the common hooks directory
  (`git rev-parse --git-common-dir`/`hooks`, or `core.hooksPath` when set) and refuses when another pre-push hook
  exists. The hook imports nothing from the working tree; for every pushed update of `refs/heads/<integration_branch>`
  it refuses unless every commit of `<remote sha>..<local sha>` is log-only; other refs pass. It reads
  `<integration_branch>` at each push from the user-level push file, never from `harness.toml`; when that file is
  absent, invalid or inside a git working tree, it guards both `refs/heads/build/v1` and `refs/heads/main`. The
  shipped text is a standard-library-only Python file that embeds the source of `_scope.py` and of the push-file
  reader `_pushconf.py` (both standard-library only) between markers, so the hook and the tool share one definition.
  `_hook.py` holds no copy of either: it assembles the shipped text at call time from its fixed header and the two
  module files read next to it, so the shipped SHA-256 changes with them; a test pins the embedded parts to the
  module sources. Its first line is
  `#!/usr/bin/env python3`; git runs it through `sh` (on Windows the `sh` of Git for Windows). Whether that resolves
  an interpreter on the owner's machine is a local-testing item (T14); a hook that cannot start fails the push. The
  owner runs `install-hook` himself; the agent never writes or edits the hook or the push file.
- **`push`** is refused unless the push file says `push = true`, its branch and remote match (§4.6) and the hook is in
  place. It runs
  `git fetch origin <integration_branch>` (that ref only), rebases the unpushed log-only commits onto it with the log
  identity as committer (local commits only), runs `check --unpushed` (TLC011), then
  `git push origin HEAD:refs/heads/<integration_branch>`, fast-forward, never `--force` or `--no-verify`. After a
  rejection it repeats once; offline or after a second rejection the commits stay local (exit 3, named). It is never
  run in a cloud session (ADR D6); there a task's commits stay local and the session names the unpushed task ids.
- **Interim.** Until plan 0015 T8b merges, the agent follows the interim template by hand (ADR D13); interim files are
  never converted, and the tool reads them only to list them.
- **Before the hook is installed** (ADR D6). While `push` refuses because the hook is missing or not in place, the
  agent never pushes with the owner's login: it runs the checks of the interim template's step 3 (with `check
  --unpushed` for the log-only test, which applies the full log path pattern of ADR D5, `records.jsonl` and triage
  files included) and, only when every check passes, prints the push command of step 4; the owner runs it himself.
  `push` itself prints no command in that case (AC26).

### 4.8 Run-fact mapping (read-only; `JournalReader` and the result store; no new event)

| source | becomes |
|---|---|
| `run_started` | `run_attached` (with `unreleased_tools`) |
| `step_failed`, `NOT_IMPLEMENTED` | `run_fact` and `not_found(not_implemented, gap)` |
| `step_failed`, `INVALID_ARGUMENT` with `field: tool` (spec 0002 §6) | `run_fact` and `not_found(tool_not_on_allowlist)` |
| `step_failed`, `HOST_LOCKED` (the interim mapping of the server's `model_locked`) or `TIMEOUT_NO_EFFECT` | `run_fact` and `not_found(host_limitation)` |
| `step_failed`, `CALC_NOT_APPROVED` or `CALC_WITHDRAWN` (`CalcRefused`) | `not_found(calc_not_approved)` |
| `step_completed` of `harness.change_set_check/1` | each `Issue` `NOT_IMPLEMENTED`: `not_found(not_implemented, gap, detail.kind)`; each `Issue` `SOURCE_MISSING`: `not_found(value_without_source)` |
| `run_escalated` | `run_fact` (reason; `detail` under `full`); `unhandled_error` adds `not_found(harness_defect)`; `host_state_mismatch` adds `not_found(host_limitation)` |
| `step_reconciled` | `run_fact` |
| `approval_resolved` | `run_fact` (decision, rejected items; `owner_text` from `reason` and `item_reasons` under `full`) |
| `run_completed`, `run_failed`, `signed_off` | `run_fact` and an updated `run_attached` |

Messages are guarded and capped at 500 characters (`truncate`). At most 50 failures per attachment, plus a count of the
rest. An unknown calc id has no harness code today (Q1); until then `no_calc` is written by the agent only.

### 4.9 STORY.md

STORY.md is deterministic, in this order: (1) header table: id, opened, closed, status, agent, policy, label; (2) the
request: a line naming `lang`, then the owner words verbatim in a fenced block (a backtick fence longer than any
backtick run in the text, info string `text`), never in an HTML wrapper, then the gloss labelled "agent's gloss"; (3)
story: every record in seq order, one English sentence each, owner words verbatim in place; (4) what was not found:
need, category, target or gap, evidence, triage state; (5) what was done instead; (6) runs; (7) outcome and what is
left. The interim template uses the same seven headings.

### 4.10 Completeness (`check`)

| Code | Rule |
|---|---|
| TLC001 | schema valid (task records and triage lines, §4.3.1); chain intact (a line named by a later `withheld_after` is checked against its `line_sha256_before` and must hold the marker in the named field); seq consecutive; append-only against the worktree's HEAD |
| TLC002 | `task_opened` first, then `owner_words(request)` |
| TLC003 | `no_workflow`, `no_calc`, `no_code_pack_check` and `tool_not_on_allowlist` cite a `searched` record in evidence |
| TLC004 | a closed task with any `not_found` has `did_instead` or a status other than `DONE`, and lists `open_needs` |
| TLC005 | `--session`: every task opened in the session is closed or handed off |
| TLC006 | orphan runs: every `<workspace>/runs/run_*` created after `since` is attached to some task |
| TLC007 | STORY.md equals its rendering (interim-1 folders, which hold a hand-written STORY.md and no `records.jsonl`, are skipped) |
| TLC008 | `--staged`: only the named task folders, or the named needs' triage files, under `tasklog/` are staged in the worktree |
| TLC009 | the guard re-run over stored records and triage lines |
| TLC010 | an attached run whose journal now has more events than `last_seq` (re-attach needed) |
| TLC011 | `--unpushed`: every commit of `origin/<integration_branch>..HEAD` in the worktree is log-only (ADR D5) and has the form of §4.7 (log identity as author and committer, subject) |

Warnings: TLW001 (number in a `*_en` field), TLW002 (suspect encoding), TLW003 (open task older than 24 h), TLW004
(log-only commits unpushed for more than 7 days).

**Stated limit:** a request the agent never opened is invisible to every machine check. The counters are the rules in
`AGENTS.md` (A23), `require_task` for runs, `status` at session start, task ids in the final status, the digest and
the optional transcript hash.

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| said-file | UTF-8 text | — | ≤20 000 characters | no | the agent's file tool, owner words verbatim |
| batch file | JSON lines | — | each line a record of §4.3 without common fields | no | the agent |
| `records.jsonl`, triage files | JSON lines | byte | ≤900 000 per file | no | this module only |
| STORY.md | Markdown | byte | ≤900 000 | no | `render` |
| journal, result store | read-only | — | — | yes (`run:`, `res_…`) | engine |

## 6. Errors

| Condition | Exit code (`cli/_exit.py`) | Fields |
|---|---|---|
| Usage error, no open task, `require_task` refusal of `run` | 2 `USAGE` | option or key |
| Guard refusal, `TASKLOG_FULL`, closed task, unknown policy, push not allowed, push branch or remote differing from the push file (AC26), non-log-only range, encoding refusal, `close` while TLC002 or TLC004 fails (AC39) | 3 `REFUSED` | field and rule; commit and path; key (`integration_branch` or the remote URL); or check code; never the refused text |
| Append lock held by another writer (`RunLocked`) | 4 `RUN_LOCKED` | task id |
| Broken chain (TLC001) or journal failing verification | 5 `JOURNAL_INTEGRITY` | task id and seq, or run id |
| No such task, run or need | 6 `NOT_FOUND` | id |
| `sanitized` policy (gap `TL-G1`) | 3 `REFUSED` | gap id |
| Unexpected exception | 70 `INTERNAL` | error id |

## 7. Non-goals

- No journal event type and no change to spec 0001; no seventh CLI command; no pull request automation and no GitHub
  API call.
- No push of any ref but the integration branch, and of no commit but a log-only one; no change to the owner's
  checkout, index or working tree.
- The sanitized rules (gap `TL-G1`) until the owner defines them.
- No copying of run folders, journals or HTML reports into git.
- GC017, `push-scope`, `tasklog-lint` and `publish-check` (eng-dev-gate) and the lead's interim push check.

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A non-log commit pushed with the owner's login | security | one log-only implementation (`_scope.py`, ADR D5); `push` refuses; the owner's hook refuses; detection after the push by the gate and the lead |
| A secret or personal path in a pushed log | security | the guard before writing; TLC009; `check --unpushed`; `withhold` and rotation (§4.4) |
| Arabic corrupted on Windows | data | said-file through the file tool; strict UTF-8; hash echoed back; fenced blocks; local-testing item |
| A secret hidden in an oversized log | security | the 900 000-byte cap (§4.2) |
| Unlogged requests | process | §4.10 stated limit and its counters |
| Concurrent writers | data | the append lock; the second writer is refused with nothing written |

## 9. Test strategy

Each criterion of §3 names its test and its layer (the test folder), so the template's criterion, layer and test table
is not repeated here. Git behaviour is tested against temporary repositories and a bare remote; no
test uses the network or the owner's credentials. Tests that read the gate's files (AC5, AC7) skip only when
`MUTANT_UNDER_TEST` is set and the file is missing. The hook text is tested by running it as a subprocess against a
temporary repository. `_scope.py` and `_hook.py` are r2 (mutation runs on them) and mutmut rewrites the sources in its
copy: no test pins the hook's SHA-256 or a stored copy, and a test that compares the hook text with the module sources
skips only when `MUTANT_UNDER_TEST` is set, with an issue reference and an expiry (the B-437 form). Windows-specific
encoding checks are local-testing items (T14).

## 10. Version impact

Minor: a new module `eng_harness.tasklog`, a new configuration section and one new option of `run` and `resume`; no
existing behaviour changes without a `[tasklog]` section.

## 11. Open questions and gaps

| Question | Owner | Answer |
|---|---|---|
| Q1. The harness code for an unknown calc id (engine §6 has none) | lead | open; until then `no_calc` is agent-written |
| Q2. Whether `attach-run` also reads `report/cycle-timings.json` (spec 0007) | lead | open |
| Q3. The exact `uv run --project <repository root> --package eng-dev-gate eng-gate --root . secrets --range ...` form from inside the sparse worktree on Windows (interim template step 3); a scan that cannot run means no push | owner (local test) | open |
| Q4. Whether `push` also runs the gate's `secrets --range` when the gate is present, besides TLC009; the harness must not depend on eng-dev-gate at run time | lead | open |
| `TL-G1`: the `sanitized` policy | owner | gap until the owner defines the rules (ADR D7) |

## 12. Worked examples (synthetic; common fields abbreviated)

### 12.1 A task that found no workflow

```jsonl
{"seq":1,"kind":"task_opened","by":"agent:<tool>","title_en":"Build a complete ETABS model from the DXF drawings in one workflow","agent":{"tool":"<tool>"},"session":{"place":"local"},"repo_commit":"<build/v1 commit>","integration_branch":"build/v1","harness_version":"<version>","policy":"full"}
{"seq":2,"kind":"owner_words","role":"request","lang":"ar","text":"<the owner's Arabic words, byte-exact>","text_sha256":"<h>","gloss_en":"Agent's gloss: make the whole ETABS model from these DXF files in one go"}
{"seq":3,"kind":"searched","for_en":"a workflow that starts from DXF","where":"workflow_registry","result":"not_found","catalog":"unavailable","detail_en":"no workflow registry in this build; spec 0007 section 7 lists the DXF start as a non-goal","refs":["packages/eng-harness/docs/specs/0007-model-edit-cycle.md"]}
{"seq":4,"kind":"searched","for_en":"dxf-prep and etabs-model as harness tools","where":"cli_tools","result":"not_found","catalog":"unavailable","detail_en":"command-line tool adapter (plan 0002 T16) not built","refs":["packages/eng-harness/docs/specs/0002-servers-and-adapters.md"]}
{"seq":5,"kind":"not_found","by":"agent:<tool>","need_id":"need_<ulid>_1","category":"no_workflow","target":"dxf_to_etabs_model","need_en":"One workflow from DXF drawings to a complete ETABS model, continuing into the edit cycle","evidence":["#3","#4"],"blocking":true}
{"seq":6,"kind":"did_instead","way":"owner_by_hand","text_en":"Told the owner no workflow exists; he runs the Sasaah tools himself; no script written"}
{"seq":7,"kind":"owner_words","role":"answer","lang":"ar","text":"<verbatim reply>","text_sha256":"<h>"}
{"seq":8,"kind":"task_closed","status":"BLOCKED","summary_en":"No workflow; need recorded for the development session","open_needs":["need_<ulid>_1"]}
```

Travel: `commit` makes one commit `docs(tasklog): task_<ulid> BLOCKED` (log identity, trailer) holding
`tasklog/tasks/<yyyy>/<mm>/task_<ulid>/records.jsonl` and `STORY.md`; `push` finds the push file allowing it and the
hook in place, fetches `origin build/v1`, finds one log-only unpushed commit (TLC011) and pushes
`HEAD:refs/heads/build/v1` fast-forward; the hook re-checks the range; the lead's check after the push accepts it as
log-only.

### 12.2 An edit-cycle run that hit a gap

```jsonl
{"seq":2,"kind":"owner_words","role":"request","lang":"ar","text":"<verbatim, with the owner's own values>","text_sha256":"<h>","gloss_en":"Agent's gloss: change a slab thickness and some beam loads, then analyse"}
{"seq":3,"kind":"did_instead","way":"harness_workflow","text_en":"Wrote the change set from the owner's words; no value added by the agent","refs":[".eng/tasklog/in/changes.json sha256:<h>"]}
{"seq":4,"kind":"run_attached","by":"harness","run_id":"run_<ulid>","workflow":"model_edit_cycle","status":"PAUSED","exit_code":10,"event_count":"<n>","last_seq":"<n>","chain_sha256":"<h>","report":"runs/run_<ulid>/report/report.html","unreleased_tools":{},"timings":{"machine_ms":"<n>","waiting_ms":"<n>","resumes":"<n>"},"model_files":["<model base name>.EDB"]}
{"seq":5,"kind":"not_found","by":"harness","need_id":"need_<ulid>_1","category":"not_implemented","gap_id":"H-G1","target":"slab_section","need_en":"Edit kind slab_section (define and assign slab thickness)","detail":{"kind":"slab_section","step_path":"<path>"},"evidence":["run:run_<ulid>#seq=<n>","res_<id>#/issues/0"],"blocking":false}
{"seq":6,"kind":"owner_words","role":"correction","lang":"ar","text":"<verbatim: go on with the loads only; it names the model folder as <withheld:personal-path:<12 hex>>>","text_sha256":"<h of the original bytes>","redactions":[{"field":"text","rule":"personal-path","start":"<i>","end":"<j>","span_sha256":"<h>"}]}
{"seq":7,"kind":"did_instead","way":"partial","text_en":"Continued with the load edits only; the owner changes the slab in ETABS by hand, read as an engineer change next cycle"}
{"seq":8,"kind":"run_fact","event":"approval_resolved","summary_en":"engineer approved promotion on the page","owner_text":"<verbatim reason>"}
{"seq":9,"kind":"run_fact","event":"run_completed","summary_en":"cycle completed; column verdicts NEEDS_ENGINEER"}
{"seq":10,"kind":"not_found","by":"agent:<tool>","need_id":"need_<ulid>_2","category":"host_limitation","gap_id":"EC-G2","need_en":"Concrete design results for columns","evidence":["#9","packages/eng-harness/docs/specs/0007-model-edit-cycle.md"],"blocking":false}
{"seq":11,"kind":"task_closed","status":"DONE_WITH_CONCERNS","summary_en":"Load edits applied on a working copy, checked after write, approved by the engineer; slab edit and column results not available","open_needs":["need_<ulid>_1","need_<ulid>_2"]}
```

Seq 5 is derived from the change-set check result (§4.8, the `step_completed` row: `not_found` only). Seq 9 carries no
gap, because `run_completed` holds none; the agent writes seq 10 itself from the column verdicts' message (spec 0007
§4.4.3, gap EC-G2), since no row of §4.8 derives it.

Travel: the run waited for the engineer (exit 10), so the agent committed and pushed after seq 4 with the subject
`docs(tasklog): task_<ulid> OPEN`, and again after seq 11 with `DONE_WITH_CONCERNS`. Had a file under `packages/` been
changed in the worktree by mistake, `commit` would refuse to stage it (TLC008), `push` would refuse the range (TLC011)
and the owner's hook would refuse the push.

### 12.3 The two named needs as the first entries (examples, not designs)

Both are written in the interim-1 format on the day ADR-0034 merges and committed in the log worktree as log-only
commits (ADR D13); they are pushed only once the preconditions of ADR D14 hold, and by the owner himself until his
pre-push hook is installed. Neither names a value, an element size or a clause result. Needs that belong to the Sasaah
tools are only logged; nothing is filed in the Sasaah repository.

- **Entry 1, `BLOCKED`.** Request: the owner's words, verbatim. Gloss: "one workflow from the DXF drawings to a
  complete ETABS model". `searched` workflow_registry: not_found (catalog unavailable; spec 0007 §7 lists the DXF start
  as a non-goal). `searched` cli_tools: not_found (spec 0002 §4.7; plan 0002 T16 not built). `searched` specs: only the
  edit cycle and the footing and column workflows exist. `not_found` `no_workflow`, target `dxf_to_etabs_model`,
  blocking: "dxf-prep prepare and inspect, etabs-model build, then the edit cycle's checks, in one workflow"; evidence
  the two searches and spike S-12 §12. `did_instead` `owner_by_hand`, no script. Commit
  `docs(tasklog): task_<ulid-1> BLOCKED`, its STORY.md only.
- **Entry 2, `BLOCKED`.** Request: the owner's words, verbatim. Gloss: "a calculation note from an existing structural
  model, for more than isolated footings and columns". `searched` workflow_registry: not_found. `searched` specs:
  partial (the footing workflow, spec 0010, and the column workflow, spec 0013, exist as specs; neither is built).
  `searched` code_pack_checks: partial (structural-codes plans 0002 to 0004). `not_found` `no_workflow`, target
  `calc_note_from_model`; `not_found` `no_code_pack_check`, target the element families the owner names, quoted from
  his words only. `did_instead` `nothing`; the owner works by hand. Commit `docs(tasklog): task_<ulid-2> BLOCKED`.
