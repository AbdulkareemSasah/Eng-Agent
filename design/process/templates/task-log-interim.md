format: interim-1

# Task log {{task_id}}

<!-- Interim hand-written task log (ADR-0034 D13), used until the harness task-log commands exist (eng-harness plan
0015). One file per owner request: tasklog/tasks/<yyyy>/<mm>/<task_id>/STORY.md, written in the log worktree
(ADR-0034 D4). Interim files are never converted. Delete this comment in the copy. -->

## 1. Header

| Field | Value |
|---|---|
| Task id | `task_` plus a UTC ULID, or `task_<yyyymmddThhmmssZ>` when no ULID generator is at hand |
| Opened (UTC) | {{YYYY-MM-DDTHH:MM:SSZ}} |
| Closed (UTC) | {{YYYY-MM-DDTHH:MM:SSZ, or open}} |
| Status | `OPEN`, `DONE`, `DONE_WITH_CONCERNS`, `BLOCKED`, `NEEDS_CONTEXT` or `WITHDRAWN` |
| Agent | {{coding tool; model family and line only, no version identifier}} |
| Policy | `full` |
| Label | {{optional project label chosen by the owner}} |
| Continues | {{earlier task id, if this is a follow-up}} |

## 2. The request

Language: {{BCP 47 tag, for example `ar`}}

````text
{{The owner's words, byte-exact, never translated. The fence is longer than any backtick run in the text.}}
````

Agent's gloss: {{one English line; never a source for a number}}

## 3. Story

| seq | time UTC | kind | by | content |
|---|---|---|---|---|
| 1 | {{time}} | `task_opened` | agent | {{English title}} |
| 2 | {{time}} | `owner_words` (request) | agent | see section 2 |

Kinds: `task_opened`, `owner_words` (request, correction, clarification, answer), `narration`, `searched` (where:
workflow_registry, allowlist, edit_kinds, calcs, code_pack_checks, cli_tools, project_lane_tools, specs, docs, other;
result: found, partial, not_found), `not_found`, `did_instead` (harness_workflow, owner_by_hand, partial, deferred,
nothing), `problem`, `handoff`, `run_refused`, `run_attached`, `run_fact`, `task_closed`. Later owner words go in their
own fenced block below the table, referenced from their row.

## 4. What was not found

| need id | category | target or gap | evidence (seq, run, path) | triage state |
|---|---|---|---|---|

Need id: `need_<task id without the task_ prefix>_<n>`. Categories: `no_workflow`, `tool_not_on_allowlist`,
`no_edit_kind`, `not_implemented` (with a gap id), `no_calc`, `calc_not_approved`, `no_code_pack_check`,
`host_limitation`, `server_limitation`, `value_without_source`, `harness_unavailable`, `harness_defect`, `other` (at
least 40 characters of need; triage recategorises it). `no_workflow`, `no_calc`, `no_code_pack_check` and
`tool_not_on_allowlist` cite a `searched` row as evidence.

## 5. What was done instead

## 6. Runs

| run id | workflow | status | exit code | report (workspace-relative) |
|---|---|---|---|---|

## 7. Outcome and what is left

## Rules that hold without the tool

- Owner words verbatim, in fenced blocks as in section 2, never in an HTML wrapper.
- No secret and no personal path anywhere, owner words included: write `<withheld:personal-path>` (or
  `<withheld:secret>`) in place of the span and say so in the story.
- No number in English narration; a value appears only in verbatim owner words or by reference to a recorded result.
- One task per request (ADR-0034 D1); a follow-up after the close is a new task that names this one.
- Nothing from this file leaves `tasklog/` except ids, categories and counts (A24).

## Commit and push procedure

Integration branch: `build/v1` in bootstrap mode, `main` after it. Log identity (ADR-0034 D5):
`-c user.name="eng-agent task log" -c user.email=tasklog@localhost`.

1. Once, from the repository root: `git worktree add --no-checkout -b eng-tasklog .eng/tasklog/worktree
   origin/<integration branch>`; then `git -C .eng/tasklog/worktree sparse-checkout set --no-cone '/tasklog/'
   '/.gate/'`; then `git -C .eng/tasklog/worktree checkout eng-tasklog`. The branch `eng-tasklog` is local only and
   never pushed by name.
2. Per task: write `STORY.md` with the file tool (UTF-8, LF). In the worktree, `git add` that file only, and commit
   with the log identity, the subject `docs(tasklog): <task_id> <status>` and the `Assisted-by:` trailer.
3. Before any push, in the worktree:
   - `git fetch origin <integration branch>`;
   - `git <log identity> rebase origin/<integration branch>`;
   - for every commit `c` in `git rev-list origin/<integration branch>..HEAD`: `git rev-list --parents -n 1 c` shows
     one parent, and `git diff-tree -r --no-renames --raw c^ c` lists only status `A` or `M`, mode `100644`, and
     paths of the form `tasklog/tasks/<yyyy>/<mm>/<task_id>/STORY.md`, and each new blob (`git cat-file blob
     c:<path>`) is at most 900 000 bytes, valid UTF-8 and free of NUL bytes (the log-only definition of ADR-0034 D5);
   - `uv run --project <repository root> --package eng-dev-gate eng-gate --root . secrets --range
     origin/<integration branch>..HEAD` reports no finding, SC002 included.

   Any failure, or any step that cannot run: no push; report what failed. Never replace a failed step by a weaker one.
4. Only when every step of 3 passed: `git push origin HEAD:refs/heads/<integration branch>`, never `--force`, never
   `--no-verify`.

Who runs step 4: nobody before the preconditions of ADR-0034 D14 are recorded. After that, the owner runs the printed
command himself until his pre-push hook (ADR-0034 D5) is installed; only then may the agent run it with his login, after
confirming the hook file is in the common hooks directory with the SHA-256 the harness documents (D6).

## Fixing a pushed secret without the tool

The owner rotates the credential at once (it stays in the private history). A log-only commit replaces the span in
`STORY.md` by the marker and adds a story row saying what was withheld and why. Never a history rewrite or force push.
