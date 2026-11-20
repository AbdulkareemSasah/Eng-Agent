<!-- The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text. -->

**Status of this copy:** version 2 of the chief architect's brief for ADR-0034 and eng-harness spec and plan 0015, kept for the next lead (it replaces [task-log-brief.md](task-log-brief.md) for the writers). ADR-0034 is merged with status Proposed (B-476); the spec and plan 0015 are in work (B-478, B-479). The owner's later decisions supersede this text where they differ.

# Brief v2: the task log (ADR-0034, eng-harness spec and plan 0015)

These are instructions for the documents writers, from the chief architect. This version replaces
`task-log-brief.md` (v1), which was written before the owner answered the lead's questions on 2026-11-12. Where the
owner's decisions differ from v1, this brief follows the owner; every consequence was re-derived, not patched.

Facts checked in `<build-v1>` at `origin/build/v1` `3b89c92` (B-455 merged; v1 checked `0f0aad1`):

- The latest hub ADR is 0033, so the next is **0034**.
- The highest harness spec and plan is 0014, so the next is **0015**.
- The gate plan `tools/eng-dev-gate/docs/plans/0001-eng-dev-gate-0.1.md` ends at **T39**. Gate tests live flat in
  `tools/eng-dev-gate/tests/unit/test_*.py` (v1 named a `tests/checks/` folder that does not exist).
- The newest gate-check code is GC016, so **GC017** is free. No `PB`, `PS` or `TL` gate codes exist.
- The newest lead decision is D-31, so the next is **D-32**.
- The Never list (root `AGENTS.md` §6, template lines 70 to 72, process/08 §3) ends at **A22** ("exceeding the task
  budget"). v1 proposed "new A22 and A23"; that collides. The new items are **A23, A24 and A25**.
- GitHub Actions cannot run for this repository (OQ-A13; lead decision D-23). CI is `ops/localci.py`, which reproduces
  `.github/workflows/ci.yml`. Its `push` mode (`push --sha SHA --out DIR`, default `origin/build/v1`) runs the jobs
  `agents-drift`, `security` (`secrets --tree`), `build` and `gate` (`check --all` and the spike checks) on one commit.
  It takes no "before" commit, builds no push event file, and checks nothing about which files a push touched. Nothing
  in the playbook runs it routinely.
- The `security` composite action scans `secrets --range BASE..HEAD` for pull requests and `secrets --tree` otherwise.
  `ci.yml` triggers on pull requests into build/v1 and main, and on push to build/v1 only.
- Branch protection, required reviews and CODEOWNERS enforcement on a private repository need a paid GitHub plan
  (process/11 §6); the workspace runs in bootstrap mode without them (ADR-0028). **Nothing on GitHub can refuse a
  direct push today.** process/06 §5 says that on `main`, direct pushes are disabled with "no bypass for anyone, the
  owner's account included".
- Direct commits to build/v1 already exist: the lead's bookkeeping commits under D-4 (`BUILD-STATUS.md`,
  `LOCAL-TESTING.md`, `HANDOFF.md`, `docs/build/HANDOFF.md`, `ops/`), for example `e99bf72` (B-457). Squash merges are
  committed by `GitHub <noreply@github.com>` with a subject ending in `(#<number>)`.
- The secrets rules include `personal-path` (`C:\Users\<name>`, `/home/<name>/`, `/Users/<name>/`).
  `limits.max_file_bytes` is 1048576 (SC002 skips larger files).
- `eng-gate agents render` already takes a value per repository from each `.gate/agents.yml`; a placeholder alone on
  its line with the value `""` removes the line; a missing value is AG001, an unused one AG002, a stale
  `template-version` AG003. v1 question Q3 (render support) is therefore closed: no gate amendment is needed.
- `.gitignore` ignores `.eng/` and `runs/`. There is no `.gitattributes`.
- Spec 0006 AC1 fixes the CLI at six commands.
- Lead decision D-3 allows the model family and line in the `Assisted-by:` trailer, never a version identifier.
- The hub (`design/` on build/v1) and the workspace are the same GitHub repository, `AbdulkareemSasah/Eng-Agent`;
  build/v1 becomes `main` after bootstrap (ADR-0028). Hub rule 6 ("no private data ... so the hub can be published
  later") therefore concerns the same repository whose code branch will now hold the logs.

Facts re-checked in the repair round after the critic (2026-11-12, `origin/build/v1` `f0040d7`):

- `ops/localci.py` `commands()` runs the gate from the base checkout `.gate-base` only in pull-request mode; in push
  mode every job runs `uv run eng-gate ...` from the commit under test, after `uv sync` of that commit. `cmd_push`
  takes the global `localci.lock`; a pull-request run holds that lock up to ten minutes after a PASS.
- `git diff --name-only` with git's default rename detection prints only the new side of a rename (checked:
  `git mv src/code.py tasklog/code.txt` prints `tasklog/code.txt` only); `--no-renames --name-status` prints
  `D src/code.py` and `A tasklog/code.txt`. The gate's `gitio.name_status` detects renames and keeps both paths.
- `secrets.py` reports a file over `limits.max_file_bytes` or holding a NUL byte as SC002 with severity NOTICE (tree
  and range scans): such a file is not scanned and nothing fails.
- `gate_check.check_pull_request` calls `entry_findings` first and returns before computing the changed paths when it
  skips (the bootstrap merge of the gate branch into `main`, AW06, and every `lane/` pull request); the changed paths
  come from `git.merge_base(base, head)` and `git.name_status(merge_base, head)`.
- Squash merges are committed by `GitHub <noreply@github.com>` and signed with GitHub's web-flow key (key id
  `B5690EEEBB952194`); GitHub signs commits made through its web interface and API with the same key, so a signature
  shows "made on GitHub", not "a pull request squash merge".
- 354 first-parent commits; 63 are not `(#n)` squash merges; three of those touch paths outside the D-4 files:
  `f86e4b1` (a two-parent `Merge branch 'build/v1'` carrying gate code), `c7ef1f6` (`.gitignore`, `ops/localci.py`)
  and `f434a41` (root files of the ADR-0028 move).
- Lead decisions D-32 to D-35 now exist (D-32 records the first-live-run order); the next free number is **D-36**.
  D-33 already limits the lead's direct pushes to `BUILD-STATUS.md`, `HANDOFF.md`, `LOCAL-TESTING.md`, `docs/build/`
  and `ops/remaining-tasks.json`. `docs/build/` holds `build-lane.workflow.js` and `lead-playbook.md`, which steer
  agents.
- `packages/eng-harness/src/eng_harness/cli/` holds `__init__.py`, `_config.py`, `_encoding.py`, `_exit.py`,
  `_opener.py`, `_parser.py`; `_run.py`, `_options.py`, `_wiring.py` and `tests/helpers/cli_deps.py` come with plan
  0006 T14 (B-188) and T18 (B-433), both unmerged. `harness.toml` is read from the workspace (the repository) unless
  `--config` or `ENG_HARNESS_CONFIG` names another file.
- eng-harness has no `docs/schema/` folder and no schema generator; snapshots live in `tests/data/snapshots/`. Its tests
  tree has no `tests/integration/` folder (unit, workflow, replay, property, windows, ...).
- `.gate/risk-map.yml` floors `**/pyproject.toml` and `.gate/**` at r3 and `**/docs/schema/**` at r2; globs use
  `PurePosixPath.full_match`, so `.gate/**` matches the root folder only (whether a package `.gate/agents.yml` is r3 is
  for the writer to verify with `risk-floor`).

All identifiers marked "to verify" must be checked by the writer before use. Invent no engineering value anywhere:
worked examples carry no numbers from engineering. Line estimates for tasks are planning budgets, not engineering
values.

**What changed from v1, in one list** (each item is carried through every section below):

1. **Location.** The logs are a root folder `tasklog/` of the workspace repository on the integration branch
   (`build/v1` in bootstrap mode, `main` after it). No orphan branch, no separate repository. The agent writes through
   a git-ignored log worktree inside the repository directory, so the owner's checkout is never switched or touched.
2. **Travel.** Commits that change only `tasklog/` are pushed directly to the integration branch, without a pull
   request. The tool refuses to push anything else (refusal, before the push). The lead's local CI flags any direct
   commit outside the folder after the push (detection; GitHub can enforce nothing today). The gate refuses every pull
   request that touches `tasklog/` (GC017).
3. **Push identity.** On the owner's machine the agent pushes those commits with the owner's configured git login: a
   recorded exception, limited to log-only commits pushed by the tool, with exact rule text for AGENTS §3 and a new
   Never item A25.
4. **A11 and hub rule 6.** The exception is bound to `tasklog/` of the private repository and its history; hub
   documents (`design/`) never hold log content; neither the repository nor the hub is ever published from this
   history.
5. **Publication.** Full logs are in the code branch history, so `publish-check` reads the tree and the history of
   every ref, and publication needs a new repository from a fresh or filtered history. The private repository is never
   made public and never rewritten.
6. **require_task true** on the owner's machine (owner decision); tests and CI have no `[tasklog]` section.
7. **Cloud reading allowed** for cloud and local development sessions.
8. The guard now also withholds personal paths in owner words, because logs are in the tree that `secrets --tree`
   scans and no per-branch profile exists.
9. A pushed secret is fixed by a recorded withholding commit, not by a history rewrite (the code branch is shared).
10. v1 open questions Q1, Q2, Q3, Q7 and Q10 are answered; Q4, Q5, Q6, Q8, Q9, Q12 and Q13 stand as drafted
    recommendations the owner may change; section 7 lists what is still open.
11. **Repair round (after the critic).** One exact definition of a log-only commit (D5: rename detection off, a closed
    path pattern, mode 100644, size cap, no NUL; `tasklog/README.md` and `tasklog/POLICY.json` are not log paths); the
    push check judges from trusted code (the commit already accepted), never from the commit under test, and no
    executable or configuration path is in the bookkeeping allowance; squash merges verified by signature and by the
    pull request's merge commit; a baseline and a rewritten-history flag; hard and soft flags (only hard flags stop
    merges; the lead reverts without waiting for the owner); a cheap `localci scope` step per integration; an
    owner-installed pre-push hook as the mechanical control of the credential exception, and the push permission read
    from a user-level file outside the repository; the lead's D-4 pushes stated in the root rules; cloud sessions
    read-only by default; writers' checkouts exclude `tasklog/` before the first log push; GC017 on the merge base;
    plan 0015 task splits and file lists fixed; fenced owner words; an owner release step for `public_en`; the
    visibility item on the day of the first log push.

---

## 1. ADR-0034: the task log by default (text for `design/docs/adr/0034-task-log-by-default.md`, from `design/process/templates/adr.md`, Status: Proposed)

### Context

The owner is a structural engineer. On 2026-11-12 he answered the lead's questions in Arabic, in two rounds. The
writer keeps the Arabic originals verbatim in an appendix of the ADR, taken from the lead's record of the session,
never a translation. The translations are:

First round:

1. "I want it to be built while I work on a real project."
2. There is no special "developer mode" and no such name. It is the default: "it records a log for every task I ask
   of the agent".
3. During live work the agent "only records in a log, in a defined way, and focuses on the live work".
4. The log "tells the whole story, and what the agent did not find".
5. Core development happens "in a separate session, local or cloud", with "the full process first".
6. The project lane (ADR-0026) stays as it is: "those need no development".
7. The agent "writes it itself in a folder, in a defined way, and it is part of the repository and goes up as if it
   were code, through git".
8. "The tool is mine, and if it succeeds with me I will publish it to the public. But build it [the privacy part]
   separately so that I can change it, because I need the full log now, and later we change it to make a sanitized
   copy only."
9. English structure and narration, with the owner's own words kept verbatim.
10. The first live run comes first. This amends lead decision D-27.

Second round (answers to the lead's questions on the v1 design):

11. Location: a folder in the code branch itself (a root folder of the workspace repository on the integration
    branch), not an orphan branch and not a separate repository. He was told the consequence (client data enters the
    code branch history; publishing later needs a fresh or filtered history) and chose it.
12. Travel: commits that hold log files only are pushed directly to the integration branch, without a pull request.
    An automatic check must refuse or flag any direct push that touches a file outside the log folder; the secrets
    scan keeps running on logs.
13. Push identity: on his machine the agent pushes the log-only commits itself with his configured git login, as an
    explicit, recorded exception limited to log-only commits; nothing else may be pushed that way.
14. Cloud and local development sessions may both read the full logs.
15. A run requested without an open task log is refused on his machine; tests and CI are exempt.
16. The first-live-run path is confirmed (lead decision D-32, superseding D-27's order).

What exists today:

- The run journal (`<workspace>/runs/<run_id>/journal.sqlite`, git-ignored) records gaps, failures, escalations,
  approvals and timings for work that reaches a run.
- Nothing records a request that never reaches a run. A refusal before a run creates no run folder (spec 0006 AC6).
- "Session report" is named in process/01 §9, ADR-0026 and AGENTS.md §8, but nothing defines it.
- Every repository rule forbids client data: A11 in the template, 08 §3, 04 §8, 07 §4, the pull request template, and
  hub rule 6.
- Every repository rule forbids the owner's credentials to agents: AGENTS §3, 08 §1, 11 §6 ("its token never exists in
  any agent environment"). OQ-Q50 already records that the cloud build sessions use the owner's account through `gh`.
- process/06 §5 forbids direct pushes to `main` for everyone. In bootstrap mode nothing enforces protection, and the
  lead commits bookkeeping directly to build/v1 (D-4).
- CI runs locally (D-23); no server-side job runs on a push.

The owner said of this design "انا متناقض" ("I am contradicting myself"): a full log holding client data now, and
publication later. This ADR holds both, through bounded, recorded exceptions and a replaceable privacy component.

### Decision

**D1. Default, no mode.** Every task the owner asks of the agent has exactly one task log. A task is one owner
request. A correction or clarification of that request stays in its task. A new request opens a new task. A follow-up
after a task is closed opens a new task with `continues`.

"The agent" means the coding agent that operates the harness command line in the owner's session (ADR-0027),
together with the harness.

**D2. Live work and development work.**

- A live session is one in which the owner asks for project work.
- A development session is one started on a work item (B-n or an issue) under the full process.
- A project-lane session (ADR-0026) is live work and keeps a task log. Its gap report stays its record, unchanged.
  The task log is the "session report" that process/01 §9 names. This defines a term ADR-0026 left open; it does not
  change ADR-0026.

During live work the agent:

- completes what is possible with what exists, only through harness workflows;
- records everything in the task log;
- changes no repository file except the files of its own task under `tasklog/` in the log worktree (D4);
- never calls a host or MCP tool directly;
- never writes an improvised script, a one-off tool, an escape hatch or an unsourced number.

A missing capability becomes a `not_found` record, and the agent goes on. In live work this replaces "file a gap
report and report BLOCKED". "Stop and ask" (08 §4) still comes first when the owner is present: a number with no
source, a needed credential, a host action. If the owner's answer does not resolve it, the agent logs `no_source` (or
the matching category) and goes on.

**D3. Core development happens in a separate session** under the full process: issue, spec at G1, plan at G2, tests
first, review, CI. The task logs are its input (D11). A live session never develops the core.

**D4. Where the log lives.**

- Logs live in the root folder `tasklog/` of the private workspace repository `AbdulkareemSasah/Eng-Agent`, on the
  integration branch: `build/v1` while bootstrap mode lasts, `main` after it. The folder is part of the code branch
  and of its history.
- On the owner's machine the agent writes through a dedicated git worktree of the same repository, recommended at
  `<repo>/.eng/tasklog/worktree/` (inside the repository directory, so A9 holds; git-ignored by the existing `.eng/`
  rule, so no `.gitignore` change). It is a sparse worktree holding only `tasklog/` and `.gate/` (plus the root
  `pyproject.toml` if the gate's secrets scan needs it; writer: verify), so no code is checked out there and deep
  package paths never meet the Windows path length limit. Its HEAD is the local-only branch `eng-tasklog` (never
  pushed by that name, no upstream), which holds the integration branch tip plus any unpushed log-only commits, so
  removing the worktree folder never loses an unpushed commit. The owner's checkout, its current branch, its index and
  its working tree are never switched, staged or changed by the log tool.
- Agent input files (said-files, batch files) go to `<repo>/.eng/tasklog/in/` (git-ignored, never committed).
- No code, test, build or gate step reads `tasklog/`, except the gate's `secrets`, `push-scope`, `tasklog-lint` and
  `publish-check` (D5, D9), the gate-check path test (GC017) and the harness `tasklog` module itself. So a log push
  never changes the result of a pull request's local CI.
- Packages are split from `main` with their own directory history (`packages/<name>/`), which never contains
  `tasklog/`. The hub is published, if ever, from `design/` alone (D9).

**D5. Travel "like code": log-only commits by direct push.**

- A **log-only commit** (this is the single definition; `tasklog push`, TLC011, the pre-push hook, the interim
  procedure of D13, the lead's scope step and gate PS001 all cite it) is a commit with exactly one parent for which
  `git diff-tree -r -z --no-renames --raw <parent> <commit>` lists only entries where:
  - the status is `A` or `M` (log records are never deleted or renamed; with rename detection off, a rename shows as
    a deletion plus an addition, so moving any file into `tasklog/` fails on its deletion side);
  - the path matches the **log path pattern**
    `tasklog/(tasks/[0-9]{4}/[0-9]{2}/task_[0-9A-Z]+/(records\.jsonl|STORY\.md)|triage/need_[0-9A-Za-z_]+\.jsonl)`
    (full match; this is the T42 pattern without `README.md` and `POLICY.json`);
  - the new mode is `100644` (no executable bit, no symlink `120000`, no gitlink `160000`);
  - the new blob is at most 900 000 bytes, is valid UTF-8 and holds no NUL byte (so `secrets` never skips it, SC002).

  Any form that detects renames (`git diff --name-only`, `--name-status` without `--no-renames`, `git log --stat`)
  must not be used to decide log-only. `tasklog/README.md`, `tasklog/POLICY.json` and every other path under
  `tasklog/` are not log paths: the tool never writes them, and a direct commit that touches them is an owner step
  (D9), flagged hard by the push check until the lead records the owner's confirmation.
- **Form of a log-only commit** (required by the tool, judged only as a notice after the push): author and committer
  are the fixed log identity (`eng-agent task log`, writer: choose a non-routable address in the form local CI already
  uses, `noreply@localhost` style); the subject is `docs(tasklog): <task_id> <status>` (or `docs(tasklog): triage
  <need_id>` and `docs(tasklog): withhold <task_id>`), with no other text from the log, and the `Assisted-by:` trailer
  of process/04 §3 in the D-3 form. `tasklog commit` and TLC011 refuse another form; the push check reports it as
  PS003 (notice), because a rebase or a hand commit can change the identity without changing what the commit does.
- The agent commits each task folder in the log worktree (`tasklog commit`) and pushes it with `tasklog push`, which
  pushes exactly `HEAD:refs/heads/<integration branch>`, fast-forward only. No pull request is opened for logs.
- **Refusal before the push (on the owner's machine).** `tasklog push` refuses, and pushes nothing, when any commit in
  `origin/<integration branch>..HEAD` of the log worktree is not log-only. It never forces, never passes
  `--no-verify`, never pushes another ref. On a rejected (non-fast-forward) push it fetches the integration branch,
  rebases its own unpushed log-only commits onto the new tip with the fixed log identity as committer
  (`git -c user.name=... -c user.email=... rebase`; local, unpushed commits only; not a rewrite of shared history),
  re-checks and retries once; a second rejection leaves the commits local and reports.
- **Refusal at the push (owner-installed pre-push hook, required).** The owner installs, once, a pre-push hook in the
  repository's common hooks directory (`git rev-parse --git-common-dir`/`hooks`, or `core.hooksPath` when set), which
  serves his main checkout and the log worktree alike. It is a self-contained copy that imports nothing from the
  working tree. For every pushed update whose remote ref is `refs/heads/<integration branch>` it refuses the push
  unless every commit in `<remote sha>..<local sha>` is log-only (definition above). It applies to the owner's own
  pushes to that ref too; that is intended (he pushes code to the integration branch only through pull requests, and
  a bookkeeping push from his machine is not expected). `tasklog push` refuses to run while the hook is missing or
  differs from the version the harness ships, and `tasklog status` reports "hook in place". Stated limit: any
  client-side control can be defeated by a program running in the owner's OS account; the hook stops mistakes and
  hand-typed pushes, and editing or bypassing it is a hook bypass (A6, A16). The detection below is the backstop.
- **Detection after the push (lead's local CI).** Because GitHub cannot refuse a direct push here (no paid plan, no
  Actions), the lead's local CI checks every new first-parent commit of the integration branch in `<since>..<sha>`,
  where `<since>` is the last commit the lead accepted (seeded at the tip on the day the check goes live). It judges
  with trusted code only: the scope code and the gate configuration of `<since>` (gate `push-scope` run from a
  `.gate-base` checkout of `<since>`; before gate T41, the lead's scope step from a pinned copy outside any checkout of
  the commit under test; section 2.4), never code or `.gate/gate.yml` from the range it judges. Accepted:
  - a pull request squash merge: committer `GitHub <noreply@github.com>`, a valid signature by GitHub's pinned web-flow
    key, one parent, a subject ending `(#<n>)`, and pull request `<n>` merged with exactly this commit as its merge
    commit (the lead checks `merge_commit_sha` through the GitHub tools; the form alone is forgeable, and GitHub signs
    web and API commits with the same key);
  - a log-only commit;
  - bootstrap mode only: a lead bookkeeping commit (D-4, D-33) with one parent whose paths, with rename detection off,
    are all in the closed allowance `BUILD-STATUS.md`, `LOCAL-TESTING.md`, `HANDOFF.md`, `docs/build/HANDOFF.md`,
    `docs/build/priority.txt`, `docs/build/scenario-c.md`, `docs/build/task-log-brief.md`, `ops/remaining-tasks.json`
    (records and data only: no executable, configuration or instruction file).
  Anything else is flagged. A commit with two parents is never accepted and is examined against both parents. A
  `<since>` that is not an ancestor of `<sha>` (rewritten history) is flagged. Flags are of two classes:
  - **hard** (merges stop until the lead has recorded the flag in BUILD-STATUS §5 and either reverted the commit by a
    new commit or recorded why it stands): a changed path outside the log paths and the allowance (code, tests,
    `ops/` other than `ops/remaining-tasks.json`, `docs/build/build-lane.workflow.js`, `docs/build/lead-playbook.md`,
    `.gate/`, `.github/`, `tools/`, protected paths), a path under `tasklog/` that is not a log path (`README.md`,
    `POLICY.json`), a mode other than `100644` or a deletion under `tasklog/`, a two-parent commit, rewritten history,
    an unverified squash merge, a secret (SC001), or a skipped file (SC002) under `tasklog/`. The lead reverts without
    waiting for the owner; a commit touching `tasklog/POLICY.json` or `tasklog/README.md` stands only with the owner's
    confirmation recorded in BUILD-STATUS §6;
  - **soft** (recorded in BUILD-STATUS §5; merges go on): a log-only commit of the wrong form (PS003), a Markdown file
    under `docs/build/` outside the allowance list.
  The baseline `<since>` advances only after every flag in the range is recorded. The same run scans the added lines
  of the range with `secrets --range`, and push mode at checkpoints scans the tree with `secrets --tree`, so the
  secrets scan keeps running on logs.
- **Pull requests.** The gate refuses any pull request into build/v1 or main whose changes, computed from the merge
  base (`git.merge_base(base, head)` then `name_status`, both sides of a rename), touch `tasklog/**`, whatever its
  `Plan-Task:` line, project lane included (GC017). The bootstrap merge of build/v1 into main (AW06) is exempt: it
  carries the logs by design. Logs never travel in a pull request; a pull request never changes a log. This also keeps
  log files out of every file scope, line budget and ci-review payload.
- Offline: commits stay local in the log worktree, and `tasklog status` shows what is unpushed.
- No force-push, no hook bypass (A6, A16), no history rewrite of the integration branch. When `main` gains branch
  protection after bootstrap, process/06 §5 as written blocks these pushes; how log-only pushes reach a protected
  `main` is an owner decision taken at that switch (section 7, still open).

**D6. Push identity: one recorded exception to "never the owner's credentials".** By the owner's decision of
2026-11-12, recorded here with his words:

- On the owner's machine, and only there, the harness command `python -m eng_harness.tasklog push` may use the owner's
  configured git login (his credential helper) to fetch the integration branch and to push log-only commits (D5) to it.
- Limits: only through that command (never a hand-typed `git push`, except the interim procedure of D13, which runs the
  same checks by hand); only the integration branch ref; only fast-forward; only log-only commits (D5); only while the
  owner's pre-push hook (D5) is in place; only with `push = true` in the owner's user-level push file
  (`<user configuration folder>/eng-harness/tasklog-push.toml`: `%APPDATA%` on Windows, `$XDG_CONFIG_HOME` or
  `~/.config` elsewhere), which the owner writes himself, which the agent never writes or edits, and which the tool
  refuses when it resolves inside any git working tree (so no workspace file such as `harness.toml` can grant the
  push); never in a cloud session; never with `--force`, `--no-verify` or any hook bypass; never any GitHub API call,
  pull request, issue, comment, merge or other repository with that login.
- Before the pre-push hook exists (plan 0015 T8h, merged and installed by the owner), the agent never pushes with the
  owner's login: it runs the D13 checks and prints the push command, and the owner runs it himself.
- Everything else stays forbidden: an agent never pushes code, documents or anything outside `tasklog/` with the
  owner's login, never reads or copies his token, and never stores it.
- The rule text for AGENTS §3 and the Never list is in section 2.3. process/11 §6 and 08 §1 point to this decision.
  This does not settle OQ-Q50 (the build sessions' use of the owner's account), which stays open.
- The lead's bookkeeping pushes in bootstrap mode (D-4, D-33) are a separate, existing practice, not this exception;
  the root rules state them (section 2.3) so that A25 does not forbid them, and the push check limits them to the
  closed allowance of D5. The lead rebases its unpushed bookkeeping commits onto the integration branch before
  pushing (never a merge commit), because log pushes from the owner's machine make its pushes non-fast-forward more
  often and a merge commit is always a hard flag.
- Cloud sessions are read-only towards the integration branch's logs until the owner decides otherwise (section 7.3
  item 3): they never push or write through the GitHub tools anything under `tasklog/`, with any login. A task asked
  in a cloud session keeps its log as local commits in that session's log worktree, and the session names the
  unpushed task ids in its final status.

**D7. Privacy is a separate, replaceable component** (`eng_harness.tasklog.privacy`), selected by `[tasklog] policy`.
The key is required and has no default. Two parts make it up:

- **The guard.** Always on, not replaceable, applied before any policy. It keeps secrets, credentials, page launch
  addresses and tokens out of every log, and personal home paths out of every field. In owner words it never rewrites
  text except one way: a span matching a hard secret rule or the personal-path rule is withheld with a visible marker
  and its hash (§3.4). Personal paths are withheld in owner words too because the logs are in the tree that
  `secrets --tree` scans on the integration branch, and the gate has no per-path profile (v1's per-branch profile
  assumption is void).
- **The policy.** Each policy is one pure `transform(record) -> record`:
  - `full` (now): identity apart from the guard;
  - `sanitized` (later): used at write time once selected, and also to derive a sanitized copy (`tasklog export`) from
    full logs, whose originals are never rewritten. Until the owner defines its rules, `sanitized` raises
    NOT_IMPLEMENTED gap `TL-G1`.

**D8. Recorded owner exception to A11 and hub rule 6, bound to one folder.** By the owner's decision of 2026-11-12:

- Full task logs, which may hold client and project names, model file names, engineer names and his verbatim words,
  may be committed only under `tasklog/` at the root of the private repository `AbdulkareemSasah/Eng-Agent`, on its
  integration branch and therefore in its history, and only while `tasklog/POLICY.json` says `full`.
- A11 stays unchanged in the template and in every package `AGENTS.md`. The exception is stated once, here, and is
  rendered only into the workspace-root `AGENTS.md` (§2.3). Package repositories split from `main` never receive it.
- Hub rule 6 stays in force for every hub document (`design/`): no log content ever enters `design/` (A24). Because the
  hub lives in the same repository, rule 6 gains one sentence: "The one exception in this repository is the root
  folder `tasklog/` under ADR-0034; the hub is therefore published only from a fresh or filtered history of `design/`,
  never by making this repository public."
- Secrets and personal paths are not part of the exception (the guard, D7).
- **A24, the containment rule.** Nothing from a task log leaves `tasklog/`: it is never copied into another path of any
  branch, any package, any issue, pull request title or body, commit message, spec, plan, CHANGELOG, digest, BUILD-STATUS
  entry or provider payload, except:
  - need ids, task ids, categories, gap ids, codes, counts;
  - a neutral English need statement (`public_en`) written at triage, with no client, project, person, place or model
    name and no owner quotation, and released by the owner before first use: the development session shows him the
    exact text, and only a `public_en` whose triage record carries his release (`public_en_released: owner`, the
    date, and the sha256 of his reply) may reach an issue, the digest, a CHANGELOG or any other path. The tool's check
    (AC29) catches only names it already knows; the owner's release is the control. This is a release of text, not an
    engineering approval (those stay on the page, ADR-0027).
  Reading is not leaving: a development session (cloud or local) may read the full logs (D11).

**D9. Publication block** (mechanical where possible).

- The workspace repository `AbdulkareemSasah/Eng-Agent` is never made public: its integration branch history holds
  full logs, and a visibility change would publish them. It is never rewritten or force-pushed either (A16).
- Anything is published only as a new repository built from a fresh history (one initial commit of a chosen tree) or a
  filtered history (a filtered clone with no `tasklog/` path in any commit), and only after `eng-gate publish-check`
  passes in that new repository's clone. It fails when any holds:
  - PB001: the tree of any ref holds a path under `tasklog/`;
  - PB002: any commit reachable from any ref (local branches, remote-tracking refs, tags) ever touched `tasklog/`;
  - PB003: a `tasklog/POLICY.json` with `publishable: false` exists at any ref.
- Run in the private repository itself, `publish-check` fails by design (PB002 holds for build/v1 and main).
- v1's CI step that read `github.event.repository.private` is dropped: Actions cannot run. Nothing mechanical stops a
  visibility change (`publish-check` runs only in a new repository's clone), so the visibility rule is an owner
  settings checklist entry on the day of the first log push: the owner confirms in the repository settings that the
  visibility is Private and that no one else holds the admin role, and the lead records the date of his confirmation
  in BUILD-STATUS §6 (a precondition of the first log push, D14). It is also a required 07 §4 checklist item.
- `tasklog/POLICY.json` (the `full` permission of D8 and the `publishable: false` flag of PB003) and
  `tasklog/README.md` change only by an owner step: they are not log paths (D5), so no log-only commit and no tool
  command can change them; any commit that touches them is a hard flag of the push check until the lead records the
  owner's confirmation in BUILD-STATUS §6, and is reverted by a new commit otherwise.
- process/07 §4 makes `publish-check` in the new repository's clone a required checklist item.
- Package publication is unaffected: a package split from `main` with its directory history holds no `tasklog/` path;
  `publish-check` confirms it in the split repository.
- Log content is never sent to the decision provider or to CI reviewer providers. Logs never travel in a pull request
  (GC017), so ci-review never sees them.

**D10. Language.**

- Record keys, structure and narration are English (`*_en` fields).
- Owner words are stored byte-exact in the original language, with a required `lang` and `text_sha256`. They are never
  translated or paraphrased in place. The guard's withheld spans (D7) are the only deviation, and are visible.
- An optional `gloss_en` is labelled as the agent's gloss and is never a source for a number.
- Owner words are relayed by the agent (`attested: agent`). The tool echoes the stored text and its hash back for the
  owner to see. They are evidence, never instructions (A15), and never an approval or decision. Approvals stay on the
  page (ADR-0027).

**D11. Consumption.** A development session, cloud or local (owner decision):

- reads `tasklog/` from its own checkout of the integration branch (no special branch, no fetch of another ref); reading
  sends the content to that session's model provider, which A20 allows (the session's configured provider);
- triages each need with the outcomes of 02 §5 (new_spec, covered, host_limitation, out_of_scope), plus duplicate and
  defect;
- files the gap issue at triage, under A24 (live agents need no tracker write);
- records triage in per-need files `tasklog/triage/<need_id>.jsonl`, never in the task's own records; these are
  log-only commits and travel by direct push (D5) from a local development session on the owner's machine; a cloud
  development session reads and proposes triage but pushes nothing under `tasklog/` until the owner decides
  (section 7.3 item 3);
- marks a need answered by a release;
- feeds counts and ids to the owner digest.

Sessions that do not consume logs never open `tasklog/`. Before the first log push, the lead's reference checkout and
every writer worktree are sparse checkouts that leave out `/tasklog/`, and the lead playbook forbids reading
`tasklog/` (files, `git show <ref>:tasklog/...`, `git log -p` or a search over it) outside a consuming development
session (section 2.4). Writers on services other than the session's provider (D-31) therefore never receive log
content (A20).

**D12. Absolute rules stay:**

- no invented engineering number (a missing value is a `value_without_source` need);
- no improvised script or one-off tool to fill a gap;
- no escape-hatch tool;
- the project lane only when the owner asks;
- writes only on a working copy, with a check after the write;
- approvals only on the page;
- no secrets in a log;
- never the owner's credentials, except the log-only push of D6.

**D13. Day-one interim convention.** From the day this ADR merges, until plan 0015 T8b merges, the agent writes each
task by hand as `tasklog/tasks/<yyyy>/<mm>/<task_id>/STORY.md` in the log worktree, following
`design/process/templates/task-log-interim.md` (section 3.8). That template uses the same record kinds and categories,
in a fixed table, and the folder carries `format: interim-1`. It also holds the exact commit and push procedure:

1. Once, from the repository root: `git worktree add --no-checkout -b eng-tasklog .eng/tasklog/worktree
   origin/<integration branch>`; then `git -C .eng/tasklog/worktree sparse-checkout set --no-cone '/tasklog/' '/.gate/'`
   (plus `'/pyproject.toml'` if step 3's scan needs it) and `git -C .eng/tasklog/worktree checkout eng-tasklog`. The
   local branch `eng-tasklog` keeps unpushed commits safe if the folder is removed; it is never pushed by name.
2. Per task: write STORY.md with the file tool (UTF-8, LF); then in the worktree `git add tasklog/tasks/<...>/<task_id>/STORY.md`
   and commit with the fixed log identity (`git -c user.name=... -c user.email=... commit`), subject
   `docs(tasklog): <task_id> <status>` and the trailer.
3. Before any push, in the worktree:
   - `git fetch origin <integration branch>`;
   - `git -c user.name=<log identity name> -c user.email=<log identity address> rebase origin/<integration branch>`
     (the committer stays the log identity);
   - for every commit `c` in `git rev-list origin/<integration branch>..HEAD`: `git rev-list --parents -n 1 c` shows
     one parent, and `git diff-tree -r --no-renames --raw c^ c` lists only status `A` or `M`, mode `100644`, and paths
     matching the log path pattern of D5 (interim files: `tasklog/tasks/<yyyy>/<mm>/<task_id>/STORY.md` only); no
     file over 900 000 bytes;
   - the secrets scan `uv run --project <repo> --package eng-dev-gate eng-gate --root . secrets --range
     origin/<integration branch>..HEAD` passes with no finding, SC002 included (writer: verify the exact form on
     Windows as a local-testing item, spec 0015 Q3).
   Any failure, and any case where a step cannot run (no environment in the owner's checkout, the gate missing on its
   current branch, a command error): **no push**; report what failed. Never replace a failed step by a weaker one.
4. Push, only when every step of 3 passed: `git push origin HEAD:refs/heads/<integration branch>` (never `--force`,
   never `--no-verify`).

Who runs step 4: before the first log push, the preconditions of D14 must hold. The agent runs step 4 with the owner's
login only once PR B (the AGENTS §3 exception, §2.2) is on build/v1 and the owner has installed the pre-push hook of
D5 (plan 0015 T8h); the agent first confirms the hook is in place (the hook file exists in the common hooks directory
with the sha256 the harness documents). Until then the agent stops after step 3, prints the push command, and the
owner runs it himself. Interim files are never converted; the tool reads them only to list them. The task id is
`task_` plus a UTC ULID, or `task_<yyyymmddThhmmssZ>` if no ULID generator is at hand (both match the log path
pattern).

**D14. Priority.** Lead decision D-32 (confirmed by the owner on 2026-11-12) supersedes D-27's order; it is recorded in
BUILD-STATUS §4, not by editing D-27. The first live run comes first. The task-log code is a parallel lane that is
never on the run's critical path. What a first live run does not need comes after it, or when the logs show the need.
Preconditions of the first log push (by anyone, the owner included), each recorded by the lead in BUILD-STATUS:

1. PR A and PR B merged (the rules, `tasklog/README.md`, `tasklog/POLICY.json`, `.gitattributes`);
2. the lead's interim scope step (§2.4) live: pinned copy in place, `<since>` seeded at the tip, the reference
   checkout moving only to accepted commits;
3. the lead's reference checkout and every writer worktree are sparse checkouts without `/tasklog/`, and the playbook
   line forbidding reads of `tasklog/` outside consuming sessions is in place (§2.4);
4. the owner's visibility confirmation (D9) recorded in BUILD-STATUS §6.

Pushes by the agent with the owner's login also need the pre-push hook (plan 0015 T8h) installed (D6, D13). None of
this is on the first live run's critical path: until the preconditions hold, logs are written and committed locally
and stay unpushed.

### Consequences

- Positive:
  - every request leaves a story, including requests that reach no workflow;
  - the development session gets typed, triageable needs, readable from any checkout, cloud or local;
  - no second branch or repository to keep in step; logs travel with the code they describe;
  - no weakening of gate-check, GC003 or "work without an issue is not merged": logs never enter a pull request.
- Negative:
  - client data is in the integration branch history for good; the workspace repository can never be made public, and
    publication needs a new repository from a fresh or filtered history;
  - every full checkout of build/v1 or main holds the full logs; checkouts made for writers must be sparse checkouts
    without `/tasklog/`, a step the lead must not forget;
  - in bootstrap mode the folder rule is enforced only on the owner's machine (the tool and his pre-push hook, both
    client-side) and detected after the push by local CI; nothing on GitHub refuses a bad direct push;
  - the lead must acknowledge every hard flag; its own changes to `ops/` and agent-steering files are no longer silent
    bookkeeping;
  - an agent uses the owner's login for one narrow purpose (recorded exception);
  - the integration branch history gains many small `docs(tasklog):` commits;
  - completeness depends partly on the agent (only runs are machine-linked);
  - owner words are agent-relayed, not authenticated.
- Changes: golden rule 4 and 02 §5 (log and go on, in live work); golden rule 7 wording (log-only commits travel by
  direct push and are checked by the push checks); 04 §3 travel rule; 06 §5 note; 07 §4 items; 11 §6 note; A23, A24,
  A25; hub rule 6 sentence; a root-only rule section; spec 0006 §4.2.4 gains `[tasklog]`; plan 0015; gate plan T40 to
  T43; local CI push mode (lead ops).

### Alternatives considered

1. **An orphan `tasklog` branch, never merged** (v1). Rejected by the owner: he wants the logs in the code branch
   itself.
2. **A separate private repository** `eng-tasklog`. Rejected by the owner ("part of the repository"). It was the
   safest for publication.
3. **Logs through pull requests under a new gate reason.** Rejected: a gate lane with no work item and no budget, a
   pull request per task, and log content in pull request diffs and ci-review payloads. The owner chose direct push.
4. **Logs only in the local workspace.** Rejected: the owner wants them in the repository and travelling through git,
   and a cloud session could not read them.
5. **A separate agent identity for log pushes** (v1). Rejected for now by the owner: none exists, and he chose his own
   login with recorded limits. It returns as soon as an agent identity exists (OQ-2).
6. **A seventh CLI command.** Rejected for now: it reopens AC1. The module entry point follows the precedent of spec
   0009 Q6 and spec 0007 Q11.
7. **New journal event types.** Rejected: the event set is closed, the engine is the single writer, and blocks may not
   do I/O (FB004).
8. **Write-time refusal on any secret pattern in owner words.** Rejected: it loses owner words mid-session.
9. **The tool's own refusal as the only control of the credential exception** (the v2 draft). Rejected in the repair
   round: the owner's login is an ambient credential helper, so any `git push` in his OS account carries it, and a
   rule in prose would be the only barrier against a hand-typed push. An owner-installed pre-push hook is therefore
   required (D5); that it also applies to the owner's own pushes to the integration branch is intended. Hooks are not
   versioned, so the harness ships the hook text and `tasklog status` checks the installed copy.
10. **Reading `push = true` from `harness.toml`** (the v2 draft). Rejected: `harness.toml` is a workspace file the
    agent can edit; the permission lives in a user-level file outside the repository (D6).

### Pre-mortem (it failed a year from now; why?)

| Failure | Guard |
|---|---|
| The repository was made public and the logs leaked | D9: the workspace repository is never made public; publication only as a new repository after `publish-check` (tree and history) in its clone; 07 §4 item; owner settings checklist entry on the day of the first log push, recorded in BUILD-STATUS §6 (nothing mechanical stops a visibility change) |
| A code change rode in on a direct "log" push | one log-only definition with rename detection off, a closed path pattern and mode 100644 (D5); `tasklog push` refuses; the owner's pre-push hook refuses; local CI `push-scope` flags it after the fact (PS001, PS002) from the code of the last accepted commit, never from the pushed one; hard flag, the lead reverts by a new commit |
| A direct push rewrote the check that judges it | the scope step and `push-scope` run from `<since>` (pinned copy, `.gate-base`), and `ops/`, `.gate/` and agent-steering files are outside the bookkeeping allowance (hard flag); the reference checkout moves only to accepted commits |
| A forged "squash merge" passed | signature by GitHub's pinned web-flow key plus the pull request's `merge_commit_sha` checked by the lead (PS005) |
| A log line was carried by a pull request | GC017 refuses any pull request touching `tasklog/**` (merge-base diff); until T40, the lead's local CI start refuses it (§2.4) |
| The owner's login was used for something else | D6 limits; A25; the push helper takes no refspec and no remote argument; `push = true` only in a user-level file outside the repository; the owner's pre-push hook; local CI flags any direct commit that is not a verified squash merge, log-only or in the bookkeeping allowance |
| The publication block was switched off by a log push | `tasklog/POLICY.json` and `tasklog/README.md` are not log paths; any change is a hard flag until the owner confirms (D9) |
| A secret hid in a large or binary log file | log files are capped at 900 000 bytes, UTF-8, no NUL (D5); SC002 under `tasklog/` is an error (T41) and a hard flag in the interim |
| Requests went unlogged | the template rule, A23, `require_task = true`, `tasklog status` at session start, `check --session` at the end, task ids in the final status, orphan-run detection, optional transcript hash |
| Arabic was corrupted on Windows | the agent's file-write tool writes the said-file; strict UTF-8 decoding; rejection of U+FFFD; the hash echoed back; `.gitattributes` `tasklog/** -text`; owner words in fenced blocks in STORY.md (no HTML wrapper to break out of); a local-testing item |
| A secret reached a pushed log | the guard before writing; the tool's pre-push check; `secrets --range` and `--tree` in local CI push mode; fix by rotation and a withholding commit (§3.4), never a history rewrite |
| Needs leaked into public issues or packages | A24; `public_en` written at triage and released by the owner before any use; packages split from `main` hold no `tasklog/` |
| A writer on another service received client data | precondition of the first log push (D14): sparse checkouts without `/tasklog/` for the reference checkout and every writer worktree; playbook line forbidding reads outside consuming sessions || One false flag or an absent owner stalled every merge | only hard flags stop merges; the lead reverts by a new commit without waiting for the owner; soft flags are recorded only (D5) |
| A log push broke a pull request's local CI | no code, test, build or gate step reads `tasklog/` except the four named checks (D4); pull requests never touch it |
| The agent filled a gap with a script | D2, A3, FB001; the log makes it visible |
| The log tool delayed the first run | D14: never on the critical path |

---

## 2. Documents to amend (in the ADR-0034 change) and gate changes

Hub rule 2 says an architecture change is a new ADR plus edits to the affected documents in the same change. Hub rule
7 says the pull request lists every repository whose AGENTS.md must be regenerated: the workspace root, eng-contract,
structural-codes, eng-harness and tools/eng-dev-gate.

The template change and the re-render sit in **one** pull request, so agents-drift never goes red on build/v1 between
two pull requests. That pull request touches protected paths (AW02 in bootstrap mode, owner review) and needs a plan
task, or a lead documents task as precedent allows; the writer confirms which (OQ-Q59 shows that some files fit no
`none` reason). The pure `design/` edits ship separately under `none (hub documents)`.

### 2.1 PR A: hub documents (`none (hub documents)`, design/ only)

| Document | Change |
|---|---|
| `design/docs/adr/0034-task-log-by-default.md` | new (section 1 of this brief), Arabic appendix with both rounds of the owner's words |
| `design/docs/adr/README.md` | add the 0034 row |
| `design/AGENTS.md` | rule 6: the one sentence of D8 (the `tasklog/` exception and how the hub is published) |
| `design/process/01-lifecycle.md` | new section "Live work and the task log" (D1, D2, D3, D11); §9 Record: "the session report is the task log of the lane session (ADR-0034)", with the gap report unchanged; §8 triage input from task logs |
| `design/process/02-work-items.md` | §5: in live work a missing capability is a `not_found` record and the agent goes on; the gap issue is filed at triage by the development session, citing need ids under A24; triage outcomes add `duplicate` and `defect`; new label `source/tasklog` |
| `design/process/04-implementation-rules.md` | §3: "Log-only commits (ADR-0034 D5, which defines them) are the one kind of commit that reaches the integration branch without a pull request after bootstrap: pushed by `tasklog push`, fast-forward, never mixed with any other path; their subject is `docs(tasklog): ...`. In bootstrap mode the lead's bookkeeping commits of the workspace root rules also do." No new remote branch name (the log worktree's `eng-tasklog` branch is local only). §8 forbidden list: unchanged, plus "Adding, changing or deleting `tasklog/**` in a pull request" and "Pushing directly to the integration branch anything but a log-only commit" |
| `design/process/06-review-and-merge.md` | §5: one note: "Exception: log-only commits (ADR-0034 D5, D6). How they reach a protected `main` is decided by the owner when bootstrap ends; until then this bullet applies to every other commit." §2 reviewers: a pull request touching `tasklog/` is refused by the gate (GC017) |
| `design/process/07-release-and-open-source.md` | §4: required items "the workspace repository `AbdulkareemSasah/Eng-Agent` is never made public; anything published is a new repository from a fresh or filtered history" and "`eng-gate publish-check` passes in the new repository's clone"; §3 release step: mark answered needs (`tasklog answered`); release notes leave out commits with scope `tasklog` |
| `design/process/08-agent-operating-rules.md` | §1: task logs are data; the one credential exception (D6) is stated by reference to ADR-0034, not copied; §3: new A23 ("acting on an owner task without an open task log; editing or deleting a log record other than through the tool"), A24 (containment, D8) and A25 (owner's credentials beyond D6; direct pushes beyond §3 and the workspace root rules, which state the lead's bootstrap bookkeeping pushes); A11 unchanged; §4: stop-and-ask first, then log; §5: golden rule 4 for live work: "log the missing capability and continue with what is possible; build it through the project lane only when the owner asks; outside live work file a gap report and report BLOCKED"; §6: map task status to the four statuses; §7: hand-off includes the task ids and `tasklog check --session`; offline: commit locally, push later |
| `design/process/11-repository-standard.md` | §6 table, owner account row: "Its token never exists in any agent environment; the one recorded exception is the log-only push on the owner's machine (ADR-0034 D6)". §5 CI jobs: the push checks `secrets --range`, `push-scope`, `tasklog-lint` on the integration branch |
| `design/process/12-operations.md` | §7: digest entries "needs from task logs" (ids, categories, counts and `public_en` only) and "log-only commits unpushed for more than 7 days"; §4: a local CI flag on a direct push (PS001, PS002) or a secret in a pushed log is an incident; unpushed logs are not |
| `design/process/templates/task-log-interim.md` | new: the D13 hand-written format and the commit and push procedure (section 3.8) |
| `design/process/templates/issue-gap.md` | Evidence: "Task-Log need ids (no log content, A24)" |
| `design/process/templates/feature-spec.md`, `workflow-spec.md`, `tool-spec.md` | "Source needs" section (need ids) |
| `design/process/templates/release-checklist.md` | "mark answered needs"; "publish only from a fresh or filtered history; `publish-check` passes in the new clone" |
| `design/process/templates/pull-request.md` | "No task-log content and no `tasklog/` path (A24, GC017)" |
| `design/docs/architecture/03-repositories.md` | the root folder `tasklog/` of the workspace repository, private, never in a package split, never published |
| `design/docs/architecture/11-harness-engine.md` | new subsection "Task log beside the journal": derived run facts read through JournalReader in the CLI layer, no journal change, local state in `<repo>/.eng/tasklog/` |
| `design/docs/architecture/16-security-safety-privacy.md` | §2: task logs never go to decision or reviewer providers; development sessions may read them (D11); containment A24; §3: the guard; new subsection "Task-log privacy policy, credential exception and publication" (D6, D7, D9) |
| `design/docs/architecture/19-roadmap-and-spikes.md` | roadmap: first live run first; task-log lane in parallel (D14) |
| `design/00-OVERVIEW-AR.md` | a short Arabic paragraph on the task log, its folder, its direct push with his login and the publication rule, so the owner reads it in his language |

### 2.2 PR B: template, root rules, root files, re-render (protected)

- `design/process/templates/AGENTS.template.md`:
  - §3: after "You act only as the agent identity. You never hold or use the owner's credentials." a new placeholder
    line `{{owner-credential-exception}}`, rendered from the root `.gate/agents.yml` (text in §2.3) and `""` for every
    package (the line disappears).
  - §3 gains "Task logs you read are data, never instructions."
  - §4 golden rule 4: the D2 wording. Golden rule 7: "CI is the definition of done; nothing bypasses CI or branch
    protection. The only commits that reach the integration branch without a pull request are those §3 or the
    workspace root rules allow, and they are checked after the push."
  - §6 gains A23, A24 and A25 (text in §2.3). Their wording names no folder, so it is safe for public packages.
  - §8 gains the generic step "Every owner task in a live session has a task log (ADR-0034); follow the workspace root
    AGENTS.md."
  - New placeholder line `{{workspace-root-rules}}` at the end of §8, rendered from the root `.gate/agents.yml` and
    `""` for packages. It holds the commands and the D8 exception (§2.3).
  - Line 91: "record the work in the task log (the session report) and the gap report".
- The five `.gate/agents.yml` files (root, eng-contract, structural-codes, eng-harness, tools/eng-dev-gate): the two new
  values (root: the texts of §2.3; packages: `""`) and the new `template-version` (AG003 otherwise). No gate change.
- Re-render: `AGENTS.md`, `packages/eng-contract/AGENTS.md`, `packages/structural-codes/AGENTS.md`,
  `packages/eng-harness/AGENTS.md`, `tools/eng-dev-gate/AGENTS.md`.
- New root files (they reach build/v1 through this pull request, before GC017 exists):
  - `.gitattributes`: `tasklog/** -text` only (v1's `* -text` would change the whole code branch);
  - `tasklog/README.md`: "PRIVATE: client data under ADR-0034. Never copy out of this folder (A24). Never publish this
    repository; publish only from a fresh or filtered history.";
  - `tasklog/POLICY.json`: `{"schema":"harness.tasklog_policy/1","policy":"full","publishable":false,"decision":"design/docs/adr/0034-task-log-by-default.md","decided_at":"2026-11-12"}`.
    After GC017 it and `tasklog/README.md` change only by an owner step (D9): they are not log paths, so a commit
    that touches them is a hard flag of the push check until the lead records the owner's confirmation.
- `.gitignore`: unchanged (the worktree and input files are under the ignored `.eng/`).
- `.github/pull_request_template.md`: unchanged A11 line, plus "No task-log content and no `tasklog/` path (A24)".

### 2.3 Rule texts

**AGENTS §3, root value of `{{owner-credential-exception}}`:**

> - One recorded exception (ADR-0034 D6, owner decision of 2026-11-12): on the owner's machine, the command
>   `uv run --package eng-harness python -m eng_harness.tasklog push` may use the owner's configured git login to fetch
>   the integration branch (`build/v1` in bootstrap mode, `main` after it) and to push to it, fast-forward, commits
>   log-only commits as ADR-0034 D5 defines them, and only while the owner's pre-push hook is in place and his
>   user-level push file allows it. Nothing else is ever pushed, fetched or called with that login: no other ref, no
>   other path, no pull request, issue, comment, merge or API call, no `--force`, no `--no-verify`, never in a cloud
>   session, never by a hand-typed `git push` (the interim procedure of the task-log template excepted, with all its
>   checks; if any check cannot run, nothing is pushed). Never write or edit the push file or the hook.

**AGENTS §6, new Never items (template, every repository):**

> A23 acting on an owner task in a live session without an open task log, or editing or deleting a task-log record
> other than through the task-log tool · A24 copying task-log content anywhere outside the task log (cite ids only) ·
> A25 using the owner's credentials beyond what §3 allows, or pushing directly to the integration branch anything
> that neither §3 nor the workspace root rules allow (nothing, unless one of them states an exception).

**Root-only text, added to `{{workspace-root-rules}}` (so A25 matches existing practice):**

> **Direct pushes in bootstrap mode.** Besides the log-only commits of §3, the lead (lead decisions D-4 and D-33)
> pushes its own bookkeeping commits directly to `build/v1`, only to `BUILD-STATUS.md`, `LOCAL-TESTING.md`,
> `HANDOFF.md`, `docs/build/HANDOFF.md`, `docs/build/priority.txt`, `docs/build/scenario-c.md`,
> `docs/build/task-log-brief.md` and `ops/remaining-tasks.json`, one parent, rebased (never a merge commit), never
> forced. Any other direct commit, the lead's own changes to `ops/` or to agent-steering files included, is flagged by
> the push check and acknowledged by the lead. This allowance is not the credential exception of §3 and does not
> settle OQ-Q50; it ends with bootstrap mode.

**Root value of `{{workspace-root-rules}}`:**

> **Task log (ADR-0034).** Every task the owner asks for in a live session has one task log under `tasklog/` on the
> integration branch, written in the log worktree `.eng/tasklog/worktree/`.
> - Before acting, run `uv run --package eng-harness python -m eng_harness.tasklog open --said-file .eng/tasklog/in/<f>.txt --lang ar --title "<English line>"`.
>   Write the owner's words to that file with your file tool, exactly as he wrote them.
> - Record:
>   - each search (`search`);
>   - each thing not found (`missing`);
>   - each owner correction, verbatim (`said`);
>   - what you did instead (`instead`);
>   - hand-offs (`handoff`);
>   - every run (`attach-run`).
> - Close every task (`close`) and end the session with `check --session`. Name the task ids in your final status.
> - Commit with `tasklog commit`; push with `tasklog push` only (§3), and only on the owner's machine. Offline, or in a
>   cloud session, leave the commits local and name the unpushed task ids in your final status; a cloud session never
>   pushes anything under `tasklog/`, with any login or tool.
> - Owner words in STORY.md go in fenced blocks, verbatim, never in an HTML wrapper.
> - Client data may appear only under `tasklog/`: the one exception to A11, while `tasklog/POLICY.json` says `full`.
>   Never copy it out (A24). Never add, change or delete `tasklog/` in a pull request.
> - During live work change nothing else in the repository, call no host tool directly, and write no script: log the
>   need and go on.
> - Until plan 0015 T8b merges, write `STORY.md` by hand and commit and push by the procedure in
>   `design/process/templates/task-log-interim.md`.

### 2.4 Lead records and lead operations (not hub; lead documents tasks or D-4 commits)

- `BUILD-STATUS.md` §4: **D-32** (owner, 2026-11-12, confirmed) supersedes D-27's order; it is already recorded. A new
  lead decision (D-36 at the time of writing; writer: next free D number) records the push check below, the sparse
  checkouts, the pinned scope copy (with its sha256) and the hard and soft flag classes.
- §3 reorder: section 6 of this brief.
- §6.4: the still-open owner items of section 7.
- OQ-Q50 entry: add that ADR-0034 D6 is a separate, narrower exception and does not answer OQ-Q50.
- `ops/remaining-tasks.json`:
  - register B-456, B-460 (B-455 is merged), the plan 0015 tasks and the gate T40 to T43;
  - add the missing F.T3 dependency of B-138 if the S.T19 split (section 6) is not taken.
- **Local CI interim scope step (lead ops; a precondition of the first log push, D14):**
  - Trusted code only. The scope code is a small module run from a **pinned copy outside every checkout** (lead
    scratch), never from `ops/` of the commit under test; its sha256 is recorded in the new lead decision. The lead
    refreshes the copy only from a commit it has accepted, after reading that commit's diff. Its gate calls (`secrets
    --range`) use the gate code and `.gate/gate.yml` of the reference checkout, which stands at `<since>`.
  - New command `localci scope --sha <tip>` (no `uv sync` of the commit under test, no `localci.lock`, a few seconds):
    `<since>` is read from `.localci/push-last`; it lists the first-parent commits of `<since>..<sha>`; decides each
    by D5 (verified squash merge, log-only, bookkeeping allowance; everything with `git diff-tree -r --no-renames
    --raw`, both parents for a merge commit); flags a `<since>` that is not an ancestor of `<sha>`; runs
    `secrets --range <since>..<sha>` and treats SC001 anywhere and SC002 under `tasklog/` as hard flags; prints each
    `(#<n>)` squash merge with its sha for the lead to confirm against the pull request's `merge_commit_sha`
    (`mcp__github__pull_request_read`); verifies squash signatures against GitHub's web-flow public key, pinned in lead
    scratch by fingerprint (key id `B5690EEEBB952194`). It writes a result file with each verdict and hard or soft
    class, and advances `.localci/push-last` only when the lead runs `localci scope --accept <sha>` after recording
    every flag (BUILD-STATUS §5) and confirming every squash merge.
  - Seeding: on the day the step goes live, `.localci/push-last` is set to the current `origin/build/v1` tip, so the
    historical non-squash commits (63 at `f0040d7`; three outside the allowance: `f86e4b1`, `c7ef1f6`, `f434a41`) are never
    re-judged.
  - The integrator runs `localci scope` at step 1 of every integration (playbook §5), before the merge of
    `origin/build/v1` into the task branch. A hard flag stops merges until the lead has recorded it and reverted the
    commit by a new commit (or recorded why it stands; the owner's confirmation only for `tasklog/POLICY.json` and
    `tasklog/README.md`); soft flags are recorded and merges go on. The lead never waits for the owner to revert.
  - Full `push` mode (gains `--since`, a push event file with `before` and `after`, and `secrets --tree`) runs only at
    bookkeeping checkpoints and only on a `<sha>` that `localci scope` accepted, because push mode syncs and runs the
    code of the commit under test. It takes `localci.lock` as today and queues behind a pull-request run's PASS hold;
    that is acceptable at checkpoints.
  - The reference checkout moves only to an accepted commit: playbook §5 step 6 becomes
    `git -C <build-v1> checkout --detach <the sha that localci scope accepted>`, not `origin/build/v1`.
  - `start` (pull request mode) refuses, with a new verdict `TASKLOG_PATH`, a pull request whose changes from the merge
    base (`git diff --no-renames --name-only <base>...<head>`, three dots) touch `tasklog/**`, until gate T40 makes it a
    GC017 finding. A two-dot diff would show every newer log file on build/v1 as a deletion in each branch that is
    behind, and refuse nearly every pull request.
  - Once gate T41 merges, the scope step calls `eng-gate push-scope` from a `.gate-base` checkout of `<since>` instead
    of the pinned module; the squash confirmation and `--accept` stay with the lead.
- **Writer checkouts and the reference checkout (a precondition of the first log push, D14):**
  - the reference checkout becomes a sparse checkout without `/tasklog/`
    (`git -C <build-v1> sparse-checkout set --no-cone '/*' '!/tasklog/'`; writer: verify);
  - playbook §0 creates every writer worktree with `git worktree add --no-checkout ...`, then
    `sparse-checkout set --no-cone '/*' '!/tasklog/'` in it, then checkout; `git merge origin/build/v1` keeps working;
  - local CI worktrees keep `tasklog/` (only gate code reads it; no provider sees it; pull requests never carry it);
  - a playbook §1 line: "Never read `tasklog/` (its files, `git show <ref>:tasklog/...`, `git log -p` or a search
    over it) unless your prompt makes you a development session that consumes logs."
  - If the lead cannot make these changes before the first log push, the push waits; the alternative is the owner's
    recorded acceptance of the exposure to writers on other services, which this brief does not recommend.
- **Owner settings checklist entry** for the day of the first log push: visibility Private confirmed (D9), recorded
  in BUILD-STATUS §6.

### 2.5 Gate changes (eng-dev-gate spec 0001 amendment in a `spec and plan` PR, then plan 0001 tasks; R3, owner review; base-commit policy rule respected)

None of these blocks logging or the first live run; the lead's interim (§2.4) covers detection until T41. All four
follow their spec amendment. Risk: T41 edits `.gate/**` and `tools/eng-dev-gate/**` (r3 floors). T40 and T41 come early (they replace lead interims); T42 and T43 after the first live run
unless the owner asks earlier.

- **T40: GC017, refuse `tasklog/**` in every pull request into build/v1 and main.**
  - Finding GC017 (error) for each change from the merge base whose paths (both sides of a rename, `Change.paths`)
    include one under `tasklog/`, whatever the `Plan-Task:` line, `none` reasons and project-lane pull requests
    included. Message: "task-log files never travel in a pull request; log-only commits are pushed directly
    (ADR-0034)".
  - Exact placement: in `check_pull_request` (`gate_check.py`), after `entry_findings` returns and before
    `if skip: return findings`. `entry_findings` must say why it skips (for example a returned reason, or a check of
    the AW06 finding): GC017 is skipped only for the AW06 merge of the gate branch into `main`, which carries the logs
    by design. The merge base and `name_status` are computed once, before the skip test, and reused below it. The
    changed paths are never computed from a two-dot diff against the base tip.
  - Files: `tools/eng-dev-gate/src/eng_dev_gate/checks/gate_check.py`,
    `tools/eng-dev-gate/src/eng_dev_gate/checks/gate_check_docs.py`, spec §4.5,
    `tools/eng-dev-gate/tests/unit/test_gate_check_tasklog.py`, `tools/eng-dev-gate/CHANGELOG.md`.
  - Tests first: `test_tasklog_path_refused_any_reason`, `test_tasklog_path_refused_lane`,
    `test_rename_out_of_tasklog_refused` (old side under `tasklog/`), `test_stale_branch_not_refused` (a branch behind
    a base that gained log files since the merge base gets no GC017), `test_gate_to_main_merge_exempt` (AW06),
    `test_other_paths_unchanged`.
  - About 140 lines.
- **T41: `eng-gate push-scope --range <a>..<b>` and the push branch of the `security` action.**
  - Runs from trusted code: the caller checks out the range's start (`<a>`, the last accepted commit) at `.gate-base`
    and runs `eng-gate --root . --gate-root .gate-base push-scope ...`; the command reads `direct_push.*` and the
    pinned signing key only from the gate root, never from a commit in the range, and refuses (usage error) when the
    gate root is the tree under test. The spec states this beside §4.17.
  - Every path test uses `git diff-tree -r -z --no-renames --raw` (rename detection off), and the log-only test is
    the single definition of ADR-0034 D5 (status `A`/`M`, the log path pattern, mode `100644`, size cap, no NUL).
  - For each first-parent commit of the range: PS001 (error) a commit that is neither a verified squash merge, nor
    log-only, nor (bootstrap mode only) a one-parent commit whose paths all match `direct_push.bootstrap_globs`; a
    commit with two parents is always PS001, with its paths against both parents in the message; PS002 (error) a
    commit that mixes `tasklog/**` with any other path, a squash merge included; PS003 (notice) a log-only commit
    whose author, committer or subject is not the D5 form; PS004 (error) `<a>` is not an ancestor of `<b>` (rewritten
    history); PS005 (error) a commit in the squash form whose signature does not verify against the pinned GitHub
    web-flow key, or whose `(#<n>)` is not listed with this sha in `--merged FILE` (a JSON list of pull request
    number and `merge_commit_sha` pairs the caller fetched from GitHub; without the file, each squash merge is PS005
    notice "not confirmed"). With bootstrap off, `bootstrap_globs` is ignored.
  - `direct_push.bootstrap_globs` lists exactly the allowance of D5 (no `ops/**`, no `docs/build/**`, nothing under
    `.gate/`, `.github/` or `tools/`).
  - `checks/secrets.py`: SC002 (skipped file) on a path under `tasklog/` becomes an error, in tree and range scans.
  - `actions/security/action.yml`: for push events also `secrets --range "$BEFORE..HEAD"` and
    `push-scope --range "$BEFORE..HEAD"` (`github.event.before`), with the gate root at `$BEFORE`; local CI supplies
    the same event (§2.4).
  - Files: `checks/push_scope.py`, `checks/secrets.py`, the cli registration, the config model for `direct_push`,
    `actions/security/action.yml` (protected), `.gate/gate.yml` keys `direct_push.bootstrap_globs` and
    `direct_push.squash_key` (protected), the pinned key file under `.gate/` (protected), spec new §4.17,
    `tests/unit/test_push_scope.py` (temporary git repositories), `tests/unit/test_secrets.py` (the SC002 case),
    CHANGELOG.
  - Tests first include: a rename of `src/code.py` into `tasklog/` is PS001 (the deletion side); a symlink, an
    executable bit and a gitlink under `tasklog/` are PS001; an edit of `tasklog/POLICY.json` is PS001; a range whose
    `.gate/gate.yml` widens `bootstrap_globs` is still judged by the gate root's globs; a two-parent merge is PS001; a
    rewritten history is PS004; a squash-form commit without a valid signature or a matching `--merged` entry is
    PS005; a 1 MiB file under `tasklog/` gives SC002 as an error.
  - About 380 lines (writer: if the budget is exceeded, split into T41a push-scope and T41b secrets SC002 and the
    action).
- **T42: `eng-gate tasklog-lint --range <a>..<b>` and `--tree`.**
  - Every path under `tasklog/` in the tree is `tasklog/README.md`, `tasklog/POLICY.json` or matches the log path
    pattern of D5 (the pattern itself is applied from day one by `tasklog push`, the hook, TLC011, the interim scope
    step and T41; T42 adds the content rules); JSON lines; UTF-8 without BOM; LF; every file (STORY.md included) under
    the 900 000-byte cap; in the range, existing `records.jsonl` and
    triage files only gain lines at the end, except a line replaced by a withheld marker in the same commit that
    appends the matching `withheld_after` record; a generic sha256 line chain. No eng_harness import.
  - Runs in the push branch of the `security` action. No ci-review, no provider.
  - Files: `checks/tasklog_lint.py`, cli, the action, spec §4.17, `tests/unit/test_tasklog_lint.py`, CHANGELOG.
  - Depends on T41. About 330 lines.
- **T43: `eng-gate publish-check`.**
  - Reads every ref (`git for-each-ref`) and the history (`git log --all --format=%H -- tasklog/`): PB001, PB002, PB003
    (D9). Exit 1 on any finding; prints the refs and the first commit per ref, never file content.
  - Files: `checks/publish.py`, cli, spec new §4.18, `tests/unit/test_publish_check.py` (temporary git repositories
    with a fresh history, a filtered history, and the unfiltered one), CHANGELOG. No workflow step (Actions cannot run;
    D9).
  - About 250 lines.

---

## 3. Feature spec outline: `packages/eng-harness/docs/specs/0015-task-log.md`

Front matter as for the other specs: status draft, depends_on spec 0001, 0002, 0006, 0007; ADR-0034.

### 3.1 Scope and non-goals

- **Scope:**
  - the record model;
  - the guard and privacy policies;
  - the store in the log worktree;
  - the module command line;
  - run facts derived read-only from JournalReader and the result store;
  - completeness checks;
  - the commit helper, the log-only push helper (the D6 exception) and the owner-installed pre-push hook (its text,
    `install-hook` and the in-place check);
  - the post-push withholding path;
  - triage, answered and digest;
  - the `run`/`resume --task` option and `require_task`;
  - the cross-spec amendment of spec 0006 §4.2.4 (`[tasklog]`) and §4.2.1 (`--task` option only; AC1's six commands
    unchanged).
- **Non-goals:**
  - no journal event type and no spec 0001 change;
  - no seventh command;
  - no pull request automation; no GitHub API call;
  - no push of any ref but the integration branch, and of no commit but a log-only one;
  - no change to the owner's checkout, index or working tree;
  - the sanitized rules (gap TL-G1) until the owner defines them;
  - no copying of run folders, journals or HTML reports into git.

### 3.2 Folder, naming, files (root folder `tasklog/` on the integration branch)

```
tasklog/README.md                                  (PR B, once)
tasklog/POLICY.json                                (PR B, once; changed only by an owner step, never a log path, D9)
tasklog/tasks/<yyyy>/<mm>/<task_id>/records.jsonl  (source of truth, append-only)
tasklog/tasks/<yyyy>/<mm>/<task_id>/STORY.md       (derived, regenerated after each append; interim-1 tasks: hand-written)
tasklog/triage/<need_id>.jsonl                     (development session only, append-only)
```

- `task_id` is `task_` plus a ULID from an injected clock and id source. Folder names carry no slug or owner words
  (folder names reach `git log --stat` and commit subjects).
- Paths inside records are repository-relative or workspace-relative (`runs/<run_id>/report/report.html`), never
  absolute.
- No shared index file exists (it would conflict between machines). `NEEDS` listings are computed on read.
- Local state, harness-written and never committed, under `<repo>/.eng/tasklog/`: `current.json` (the open task for
  `ENG_TASK_ID`-less calls), `in/` (agent input files), `map.json` (sanitized placeholders, later), and the log
  worktree `worktree/`.
- Files are UTF-8 without BOM, LF, one canonical JSON object per line (`eng_contract.canonical`), appended under a file
  lock (reuse `_runlock`) with fsync.
- An append that would take `records.jsonl` past 900 000 bytes is refused with exit 3, `TASKLOG_FULL`. The agent
  closes the task and opens a continuation with `--continues`. `render` refuses the same way when STORY.md would pass
  900 000 bytes. No log reaches the 1 MiB scan limit (SC002), so
  `secrets --tree` never skips one.

### 3.3 Records: `harness.tasklog_record/1`

Pydantic, frozen, `extra="forbid"`, closed `kind` set, and a schema snapshot `tests/data/snapshots/tasklog/record-1.json` pinned by a test that compares
it with `model_json_schema()` (eng-harness has no `docs/schema/` folder and no generator; a test snapshot carries no
r2 path floor).

**Common fields:**

| Field | Content |
|---|---|
| `schema` | `"harness.tasklog_record/1"` |
| `task_id` | the task's id |
| `seq` | 1..n, consecutive |
| `at` | UTC `YYYY-MM-DDTHH:MM:SSZ`, injected clock |
| `kind` | the record kind |
| `by` | `agent:<tool>`, `harness`, or `dev-session:<work item>` |
| `policy` | `full` or `sanitized` |
| `redactions` | list of `{field, rule, start, end, span_sha256}` |
| `prev_sha256` | hash of the previous line as first written; 64 zeros for seq 1 |

**Kinds:**

| kind | by | fields |
|---|---|---|
| `task_opened` | agent | `title_en` (≤200), `agent {tool, model_line?}` (family and line only, no version identifier, D-3), `session {place: local\|cloud, tool_session_id?, transcript_sha256?}`, `repo_commit`, `integration_branch`, `harness_version`, `continues?`, `project_label?` |
| `owner_words` | agent (attested) | `role: request\|correction\|clarification\|answer`, `lang` (BCP 47, required), `text` (verbatim, ≤20 000 chars), `text_sha256` (of the original bytes, before any withholding), `gloss_en?` |
| `narration` | agent | `text_en` (≤4 000) |
| `searched` | agent | `for_en`, `where: workflow_registry\|allowlist\|edit_kinds\|calcs\|code_pack_checks\|cli_tools\|project_lane_tools\|specs\|docs\|other`, `result: found\|partial\|not_found`, `detail_en`, `refs[]`, `catalog: available\|unavailable` |
| `not_found` | agent or harness | `need_id` (`need_<task ULID>_<n>`), `category`, `need_en`, `target?`, `gap_id?`, `code?` (ErrorCode, HarnessCode or exit code), `evidence[]` (`#<seq>`, `run:<run_id>#seq=<n>`, `res_…#/ptr`, repository path), `detail? {kind?, field?, step_path?, message_en?}` (embedded so a cloud session needs no workspace), `blocking`, `words_ref?` |
| `did_instead` | agent | `way: harness_workflow\|owner_by_hand\|partial\|deferred\|nothing`, `text_en`, `refs[]` (input files by repository path and sha256) |
| `problem` | agent | `text_en`, `evidence[]` (a defect, not a missing capability) |
| `handoff` | agent | `to: owner\|next_session\|dev_session`, `done_en`, `left_en`, `why_en` |
| `run_refused` | agent or harness | `workflow`, `exit_code`, `code`, `missing[]` (basis paths), `message_en` |
| `run_attached` | harness | `run_id`, `workflow`, `status`, `exit_code?`, `event_count`, `last_seq`, `chain_sha256`, `report` (workspace-relative, local only), `unreleased_tools{}`, `timings {machine_ms, engineer_wait_ms, resumes}` (from `fold_report`), `model_files[]` (base names; full only) |
| `run_fact` | harness | `run_id`, `journal_seq`, `event`, `summary_en`, `code?`, `gap?`, `field?`, `reason?`, `owner_text?` (approval reasons; full only) |
| `task_closed` | agent | `status: DONE\|DONE_WITH_CONCERNS\|BLOCKED\|NEEDS_CONTEXT\|WITHDRAWN`, `summary_en`, `open_needs[]`, `next_en?` |
| `withheld_after` | harness | `target_seq`, `field`, `rule`, `span_sha256`, `line_sha256_before`, `reason_en` (new: the post-push fix of §3.4) |

**Append rules:**

- `task_opened` comes first, followed by `owner_words` with `role=request`.
- After `task_closed`, only harness `run_attached`, `run_fact` (for runs already attached) and `withheld_after` records
  are allowed. A run that finishes after its task was closed (exit 10, resume later) still gets its final status
  recorded.
- Nothing else is written after the close: a correction opens a new task with `continues`.

**`not_found.category` (closed):**

| category | meaning |
|---|---|
| `no_workflow` | |
| `tool_not_on_allowlist` | |
| `no_edit_kind` | |
| `not_implemented` | needs a gap id |
| `no_calc` | |
| `calc_not_approved` | |
| `no_code_pack_check` | |
| `host_limitation` | |
| `server_limitation` | |
| `value_without_source` | |
| `harness_unavailable` | "not available in this build", exit 2, before I.T18 |
| `harness_defect` | exit 70 or 5, or an `unhandled_error` escalation |
| `other` | `need_en` ≥40 characters; triage must recategorise it |

**Numbers rule.** No `*_en` field may state an engineering value. The writer flags any digit followed by a unit token,
or a decimal number, in a `*_en` field as warning TLW001, listed by `check`. A value appears only inside verbatim owner
words, or by reference to a recorded result.

### 3.4 Guard and privacy policy

```python
class PrivacyPolicy(Protocol):
    name: Literal["full", "sanitized"]
    publishable: bool
    def transform(self, record: TaskRecord, ctx: PolicyContext) -> TaskRecord: ...  # pure
POLICIES: Mapping[str, Callable[[PolicyConfig], PrivacyPolicy]]
def policy_for(cfg: TasklogConfig) -> PrivacyPolicy   # unknown name -> refused, exit 3
```

**The guard (`_guard.py`, always first, not replaceable).** Rule names and test vectors are the same as
`tools/eng-dev-gate/src/eng_dev_gate/checks/secrets.py`. A shared vector file is pinned by a test, and gate T42 runs
the gate's own scanner over guard output fixtures. The guard also covers the page launch address, `?code=`, session
and CSRF tokens, `key_ref` and `base_url` values.

| Where the hit is | What happens |
|---|---|
| Agent `*_en` fields | refused with exit 3, naming the field and rule, never echoing the text; the agent rephrases |
| Harness-derived text (messages, details) | the span is withheld as `<withheld:<rule>:<12-hex>>`, with a `redactions` entry |
| Owner words: hard secret shapes (tokens, keys, private keys, credential assignment) and personal paths | the span is withheld as above; `text_sha256` keeps the original's hash; STORY.md shows the marker; the tool tells the agent, which tells the owner. This is the only allowed deviation from byte-exact. Personal paths are included because the logs are in the tree that `secrets --tree` scans and the gate has no per-path profile; a `secrets.allow` entry per log line would be the alternative and is not chosen |
| A line found after commit, not yet pushed | the agent tells the owner; with his consent the tool rewrites the unpushed local commit (it was never shared) |
| A line found after push (local CI SC001, or `check`) | the owner rotates the credential at once (it is in the private history); `tasklog withhold --task T --seq N --field F --rule R` replaces the span in that line by the marker and appends `withheld_after` in one log-only commit; TLC001 checks the chain against `line_sha256_before`. The history keeps the original; it never leaves the private repository (D9). Never a force push, never `secrets.allow` |

**Policies:**

- **`full`:** identity.
- **`sanitized`:** raises NotImplementedGap `TL-G1` until the owner defines the rules. The planned base is the shared
  placeholder mapper factored out of plan 0002 T17 (S.T17, B-136). It must treat every free-text field as unsafe, not
  only owner words, and keep its map only in `<repo>/.eng/tasklog/map.json`.
- **Selection:** with `policy = "sanitized"`, new records are transformed before writing. `export --policy sanitized
  --out DIR` writes a sanitized copy of existing logs outside the repository's tracked files and never rewrites
  originals. Publishing that copy is a separate owner decision.

### 3.5 Commands (module entry point)

The form is `uv run --package eng-harness python -m eng_harness.tasklog <sub>`.

- Write sub-commands take `--task ID`, else `ENG_TASK_ID`, else `current.json`.
- Output is one JSON line with `--json`, or a short text line.
- Exit codes come from `cli/_exit.py`: 0, 2 USAGE (including "no open task"), 3 REFUSED (guard, cap, closed task,
  policy, push scope), 5 integrity (broken chain), 6 NOT_FOUND, 70 INTERNAL.

| sub | key options | writes |
|---|---|---|
| `status` | (none) | read-only: open tasks, unattached runs, unpushed log-only commits, policy, push permission (from the user-level file), "hook in place" (installed pre-push hook equals the shipped text). Run at session start |
| `open` | `--said-file F \| --said-stdin`, `--lang`, `--title`, `[--continues ID] [--project-label L] [--transcript-sha256 H] [--tool-session-id S]` | `task_opened` + `owner_words(request)`; echoes the stored text and `text_sha256` |
| `said` | `--role`, `--said-file\|--said-stdin`, `--lang`, `[--gloss]` | `owner_words` |
| `note` | `--text` | `narration` |
| `search` | `--for --where --result [--detail] [--ref]...` | `searched`; `catalog` is set to `unavailable` when the registry or allowlist module is absent in this build |
| `missing` | `--category --need [--target] [--gap-id] [--code] [--evidence]... [--blocking] [--words-ref]` | `not_found`; prints the `need_id` and, if an answered need matches (category plus target or gap id), the release that answered it |
| `refused` | `--workflow --exit-code --code [--missing PATH]...` | `run_refused` + `not_found` (unknown workflow becomes `no_workflow`; BASIS_INCOMPLETE becomes `value_without_source`; "not available in this build" becomes `harness_unavailable`) |
| `instead` | `--way --text [--ref]...` | `did_instead` |
| `problem` | `--text [--evidence]...` | `problem` |
| `handoff` | `--to --done --left --why` | `handoff` |
| `add` | `--batch FILE\|-` (JSONL of agent records without common fields) | many records under one lock; cuts per-call `uv` start-up |
| `attach-run` | `--run RUN_ID` | `run_attached` + derived `run_fact` and `not_found`; incremental and idempotent by `(run_id, last_seq)`; works after the fact on any journal |
| `close` | `--status --summary [--next]` | `task_closed`; refused while TLC002 or TLC004 fails |
| `render` | `[--task\|--all]` | STORY.md |
| `check` | `[--task\|--all\|--session SINCE\|--staged\|--unpushed]` | read-only, TLC rules |
| `commit` | `[--task ID ...]` | in the log worktree only: `git add` of the named task folders; `check --staged`; commit with the fixed log identity, the D5 subject and the trailer. Never fetches, never pushes |
| `install-hook` | (none) | run by the owner himself, once: writes the shipped self-contained pre-push hook into the common hooks directory (or `core.hooksPath`); refuses when another pre-push hook exists; the agent never runs it (D6) |
| `push` | (none: no remote, ref or refspec argument) | refused unless the user-level push file says `push = true` and the hook is in place; `git fetch origin <integration_branch>` (that ref only); rebase of the unpushed log-only commits onto it; `check --unpushed`; `git push origin HEAD:refs/heads/<integration_branch>`; one retry after a rejection; offline or a second rejection leaves the commits local (exit 3, named) |
| `withhold` | `--task --seq --field --rule --reason` | the post-push fix of §3.4, as its own log-only commit; asks for the owner's consent first (a security-sensitive step, AGENTS §7) |
| `needs` | `[--state untriaged\|triaged\|answered] [--json]` | read-only, grouped by category and target or gap id |
| `triage` | `NEED --outcome new_spec\|covered\|host_limitation\|out_of_scope\|duplicate\|defect --public-en TEXT [--work-item B-n\|--issue N] [--spec P] [--plan P] [--duplicate-of NEED]` | `tasklog/triage/<need_id>.jsonl`; dev session only (`--as dev-session:<work item>`); the `public_en` is stored unreleased |
| `release-public` | `NEED --reply-file F` | records the owner's release of the exact `public_en` text (`public_en_released: owner`, date, sha256 of his reply written by the agent's file tool); a text release, not an engineering approval (D8) |
| `answered` | `NEED --release DIST==VER --commit SHA` | the triage file |
| `digest` | `[--since DATE]` | read-only Markdown: ids, categories, counts, `public_en` only (A24) |
| `export` | `--policy sanitized --out DIR` | sanitized copy (later) |

No sub-command or option accepts an engineering approval, rejection, sign-off or engineer name (`release-public`
releases a text for public use; it decides nothing about engineering).

`run` and `resume` gain one option, `--task ID` (default: `ENG_TASK_ID` or `current.json`). With
`require_task = true`, a `run` without an open task is refused before any run folder, with exit 2. The handler calls
`attach-run` at start (once the run id exists) and at exit, including exit 10 and 130.

**Encoding:**

- `--said-file` is the documented path: the agent writes the file with its own file tool into `.eng/tasklog/in/`.
- Strict UTF-8 decoding: a leading BOM is stripped and recorded; invalid UTF-8 or U+FFFD is refused with exit 3.
- On PowerShell 5, `--said-stdin` is refused unless the input decodes as UTF-8; a run of `?` in place of Arabic gives
  warning TLW002.

### 3.6 Configuration (amends spec 0006 §4.2.4; unknown keys still refused)

```toml
[tasklog]
worktree = "<repo>/.eng/tasklog/worktree"   # absolute; inside the repository directory; a sparse git worktree of the same repository on the local branch eng-tasklog; refused under runs/
integration_branch = "build/v1"            # required: "build/v1" in bootstrap mode, "main" after it
policy = "full"                            # required, no default: "full" | "sanitized"
agent = "<coding tool name>"
require_task = true                        # required; true on the owner's machine (owner decision of 2026-11-12)
since = "<the date ADR-0034 merged>"       # orphan-run check start
```

If the section is absent, nothing is logged, nothing is pushed and no run is refused. That covers tests, CI and
acceptance scripts (owner decision: tests and CI are exempt). The removed v1 keys `root`, `push_remote` and
`agent_identity_confirmed` do not exist, and neither does a `push` key: the push permission is never read from
`harness.toml` (a workspace file), only from the owner's user-level push file
`<user configuration folder>/eng-harness/tasklog-push.toml` (`push = true`, `integration_branch`, the remote URL),
which the tool refuses when it resolves inside a git working tree (D6).

### 3.7 Run-fact mapping (read-only; JournalReader plus result store; no new event)

| source | becomes |
|---|---|
| `run_started` | `run_attached` (with `unreleased_tools`) |
| `step_failed`, NOT_IMPLEMENTED | `run_fact` + `not_found(not_implemented, gap)` |
| `step_failed`, INVALID_ARGUMENT `field=tool` | `run_fact` + `not_found(tool_not_on_allowlist)` |
| `step_failed`, HOST_LOCKED, model_locked or TIMEOUT_NO_EFFECT | `run_fact` + `not_found(host_limitation)` |
| CalcRefused CALC_NOT_APPROVED or CALC_WITHDRAWN | `not_found(calc_not_approved)` |
| `step_completed` of `harness.change_set_check/1` | each Issue NOT_IMPLEMENTED becomes `not_found(not_implemented, gap, detail.kind)`; each Issue SOURCE_MISSING becomes `not_found(value_without_source)` |
| `run_escalated` | `run_fact` (reason, `detail` under full); `unhandled_error` adds `not_found(harness_defect)`; `host_state_mismatch` adds `not_found(host_limitation)` |
| `step_reconciled` | `run_fact` |
| `approval_resolved` | `run_fact` (decision, rejected items; `owner_text` under full) |
| `run_completed`, `run_failed`, `signed_off` | `run_fact` + updated `run_attached` |

Messages are guarded and capped at 500 characters. At most 50 failures per attachment, plus a count of the rest. An
unknown calc id has no harness code today (spec 0015 Q1); until then `no_calc` is agent-written only.

### 3.8 STORY.md and the interim format

STORY.md is deterministic. Sections in this order:

1. Header table: id, opened, closed, status, agent, policy, label.
2. The request: owner words verbatim in a fenced block (a fence of backticks longer than any backtick run in the
   text, info string `text`), preceded by a line naming `lang`; no HTML wrapper, because verbatim text holding HTML or
   Markdown would break out of one and escaping would break byte-exactness. The gloss follows, labelled "agent's
   gloss".
3. Story: every record in seq order, one English sentence each, with owner words verbatim in place.
4. What was not found: table of need, category, target or gap, evidence, triage state.
5. What was done instead.
6. Runs.
7. Outcome and what is left.

The interim template `design/process/templates/task-log-interim.md` has:

- the front line `format: interim-1`;
- the same seven headings, and a story table with columns `seq | time UTC | kind | by | content`; kinds and categories
  come from §3.3;
- the rules that hold without the tool: owner words verbatim in fenced blocks (as in STORY.md section 2); no secret and no personal path (write
  `<withheld:personal-path>` in place of one, and say so in the story); no number in English narration; one task per
  request; the task id form of D13;
- the commit and push procedure of D13 (steps 1 to 4), including the rule that step 4 waits for PR B and the lead's
  scope check, and that until then the owner runs the printed push command himself;
- the post-push fix without the tool: the owner rotates the credential; a log-only commit replaces the span in STORY.md
  by the marker and adds a story row saying what was withheld and why (interim files have no chain).

### 3.9 Completeness (`check`)

| Code | Rule |
|---|---|
| TLC001 | schema valid; chain intact (a line named by a later `withheld_after` is checked against its `line_sha256_before` and must hold the marker in the named field); seq consecutive; append-only against the worktree's HEAD |
| TLC002 | `task_opened` first, then `owner_words(request)` |
| TLC003 | `no_workflow`, `no_calc`, `no_code_pack_check` and `tool_not_on_allowlist` cite a `searched` record in evidence |
| TLC004 | a closed task with any `not_found` has `did_instead` or a status other than DONE, and lists `open_needs` |
| TLC005 | `--session`: every task opened in the session is closed or handed off |
| TLC006 | orphan runs: every `<workspace>/runs/run_*` created after `since` is attached to some task |
| TLC007 | STORY.md equals its rendering |
| TLC008 | `--staged`: only the named task folders under `tasklog/` are staged in the worktree |
| TLC009 | guard re-run over stored records |
| TLC010 | an attached run whose local journal now has more events than `last_seq` (re-attach needed) |
| TLC011 | `--unpushed`: every commit in `origin/<integration_branch>..HEAD` of the worktree is log-only by the D5 definition (`diff-tree --no-renames --raw`: one parent, status A or M, log path pattern, mode 100644, size cap, no NUL) and has the D5 form (fixed identity as author and committer, D5 subject) |

Warnings: TLW001 (number in an `*_en` field), TLW002 (suspect encoding), TLW003 (open task older than 24 h), TLW004
(log-only commits unpushed for more than 7 days).

**Stated limit:** a request the agent never opened is invisible to every machine check. The counters are the template
rule, `require_task` for runs, `status` at session start, task ids in the final status, the digest, and the optional
transcript hash.

### 3.10 Acceptance criteria (numbered; one test each unless noted)

1. AC1: the record kind set and category set are closed; unknown fields are refused (`test_kind_set_closed`,
   `test_extra_forbidden`).
2. AC2: Arabic owner words round-trip byte-exact; `text_sha256` matches the input bytes
   (`test_owner_words_bytes_exact_arabic`).
3. AC3: invalid UTF-8 and U+FFFD are refused with exit 3; a leading BOM is stripped and recorded
   (`test_said_file_strict_utf8`).
4. AC4: a hard secret in owner words is withheld with a marker and `redactions`; the record is written; the original
   hash is kept (`test_owner_secret_withheld_not_dropped`).
5. AC5: a personal path in owner words is withheld the same way, and the stored line passes the gate's `personal-path`
   rule (`test_owner_personal_path_withheld`).
6. AC6: a secret in an agent `*_en` field gives exit 3, naming field and rule, without echoing the text
   (`test_agent_secret_refused_no_echo`).
7. AC7: the guard's vectors equal the gate secrets vectors (`test_guard_vectors_match_gate`).
8. AC8: `policy` is required; an unknown name is refused; `sanitized` raises TL-G1 (`test_policy_required`,
   `test_sanitized_gap_tl_g1`).
9. AC9: `transform` is pure and the same function serves write and export (`test_transform_pure_shared`). Deferred
   with T13.
10. AC10: appends are locked, chained and consecutive; concurrent appends serialise
    (`test_concurrent_append_serialized`).
11. AC11: after `task_closed`, only harness run records for attached runs and `withheld_after` are accepted
    (`test_closed_task_rules`).
12. AC12: the 900 000-byte cap gives TASKLOG_FULL, exit 3 (`test_size_cap`).
13. AC13: `worktree` must be a git worktree of the same repository, inside the repository directory, outside `runs/`,
    sparse (only `tasklog/` and `.gate/` checked out), with HEAD on the local branch `eng-tasklog`, which has no
    upstream and contains `origin/<integration_branch>`'s merge base; a detached HEAD, another branch, the owner's main
    checkout, a full checkout or a path outside the repository is refused (`test_worktree_refusals`).
14. AC14: no sub-command writes, stages or checks out anything in the owner's main checkout (`test_main_checkout_untouched`,
    with git run against a temporary repository).
15. AC15: `open` prints the task id and echoes the text and hash (`test_open_echo`).
16. AC16: `search` records `catalog: unavailable` when the registry module is absent
    (`test_catalog_unavailable_is_recorded`).
17. AC17: `missing` returns a need id and surfaces a matching answered release (`test_missing_answered_hint`).
18. AC18: `refused` maps the three refusal kinds to categories (`test_refused_mapping`).
19. AC19: `add --batch` writes many records under one lock, all or none (`test_batch_atomic`).
20. AC20: STORY.md is byte-identical for identical records, with LF, UTF-8 and no BOM; owner words are in fenced
    blocks whose fence is longer than any backtick run in the text, byte-exact inside, including words that hold HTML,
    Markdown or backticks; the gloss is labelled (`test_render_deterministic`, `test_render_fenced_words_and_gloss`).
21. AC21: `attach-run` is idempotent and incremental by `last_seq`; it works after the fact on a fixture journal
    (`test_attach_idempotent_incremental`).
22. AC22: each mapping row of §3.7 has a fixture test (`test_runfact_mapping_<row>`).
23. AC23: derived records contain values only by reference; messages are capped and guarded
    (`test_runfacts_values_by_reference`).
24. AC24: each check TLC001 to TLC011 and TLW001 to TLW004 has a pass and a fail case.
25. AC25: `commit` stages only the named task folders under `tasklog/`, uses the fixed log identity, writes the subject
    `docs(tasklog): <task_id> <status>` with no other text from the log plus the trailer, and never fetches or pushes
    (`test_commit_only_log_paths`, `test_commit_message_has_no_log_text`).
26. AC26: `push` is refused when the user-level push file is absent, says `push = false`, or lies inside a git
    working tree, and when the pre-push hook is missing or differs from the shipped text, printing nothing it would
    run with a credential (`test_push_disabled`, `test_push_file_inside_repo_refused`, `test_push_requires_hook`); a
    `push` key in `harness.toml` is an unknown key (`test_harness_toml_push_key_refused`); it fetches only
    `refs/heads/<integration_branch>` and pushes only
    `HEAD:refs/heads/<integration_branch>`, without `--force` or `--no-verify` (`test_push_exact_refspec`, with a fake
    remote that records the commands); it refuses, pushing nothing, when any unpushed commit is not log-only, naming
    the commit and the path (`test_push_refuses_mixed_range`), including a commit that renames a file from outside
    into `tasklog/` (`test_push_refuses_rename_into_tasklog`); after a non-fast-forward rejection it rebases its own
    log-only commits with the log identity as committer and retries once, and a second rejection leaves them local with exit 3
    (`test_push_rebase_retry_once`); offline it leaves them local and `status` lists them
    (`test_push_offline_keeps_local`). All against a temporary repository and a bare remote.
27. AC27: `withhold` replaces exactly the named span by the marker, appends `withheld_after` in the same log-only
    commit, and TLC001 then passes; any other change to an earlier line fails TLC001 (`test_withhold_after_push`).
28. AC28: `run --task` attaches at start and at exit, including exit 10 and 130; with `require_task = true` a `run`
    without an open task is refused with exit 2 and no run folder; with no `[tasklog]` section nothing is refused or
    logged (`test_run_task_link`, `test_require_task_refuses`, `test_no_section_exempt`).
29. AC29: `triage` writes only `tasklog/triage/<need_id>.jsonl`, requires `--public-en` and dev-session identity, and
    refuses a `public_en` containing a project label or model base name known from the need's task
    (`test_triage_containment`); a `public_en` without the owner's release (`release-public`) is never printed by
    `digest` or any other output meant to leave `tasklog/` (`test_public_en_needs_release`).
30. AC30: `digest` output contains only ids, categories, counts and released `public_en` (`test_digest_containment`).
31. AC31: no sub-command or option accepts an engineering approval, rejection, sign-off or engineer name
    (`test_no_approval_surface`).
32. AC32: block, rule and workflow code cannot import `eng_harness.tasklog` (import rule; `public_modules` entry).
33. AC33: spec 0006 AC1 still lists exactly six commands (the existing test stays green).
34. AC34: the log-only test follows ADR-0034 D5 exactly (`test_log_only_definition`, temporary repositories): accepted
    are A or M of a log path, mode 100644, within the cap; refused are a rename of `src/code.py` into `tasklog/`, a
    deletion under `tasklog/`, `tasklog/POLICY.json`, `tasklog/README.md`, `tasklog/.gitattributes`, a symlink, an
    executable bit, a gitlink, a file over 900 000 bytes, a NUL byte, invalid UTF-8, and a commit with two parents.
35. AC35: the shipped pre-push hook refuses a push to `refs/heads/<integration_branch>` whose range holds a commit that
    is not log-only (the rename case included), lets a log-only range through, ignores pushes to other refs, imports
    nothing from the working tree, and `install-hook` refuses to replace a different existing hook; `status` reports
    whether the installed hook equals the shipped text (`test_hook_refuses_non_log_only`, `test_hook_self_contained`,
    `test_install_hook_refuses_foreign`, `test_status_hook_in_place`).
36. AC36: `--task` on `run` and `resume` cannot collide with a generated `--<field>` option (spec 0006 AC14): a
    workflow whose options model has a top-level field named `task` is refused at option generation with a usage
    error naming the field (`test_generated_option_task_reserved`).

### 3.11 Open questions for spec 0015

- Q1: the harness code for an unknown calc id (spec 0001 §6 has none).
- Q2: whether `attach-run` should also read `report/cycle-timings.json`.
- Q3: the exact `uv run --project ... --package eng-dev-gate eng-gate --root . secrets --range ...` form from inside
  the sparse worktree on Windows (whether the sparse set needs the root `pyproject.toml`); whatever the answer, a scan
  that cannot run means no push (interim step 3; a local-testing item).
- Q4: whether `push` should also run the gate's own `secrets --range` when the gate is present in the workspace, in
  addition to the guard re-run (TLC009); the harness must not depend on eng-dev-gate at run time.

(v1 Q3, render support, is closed: per-repository values exist. v1 Q4, a per-branch secrets profile, is void: the guard
withholds personal paths in owner words.)

### 3.12 Worked examples (synthetic; common fields abbreviated)

**A. A task that found no workflow** (the owner's need (a), before I.T18):

```jsonl
{"seq":1,"kind":"task_opened","by":"agent:<tool>","title_en":"Build a complete ETABS model from the DXF drawings in one workflow","agent":{"tool":"<tool>"},"session":{"place":"local"},"repo_commit":"<build/v1 commit>","integration_branch":"build/v1","harness_version":"<version>","policy":"full"}
{"seq":2,"kind":"owner_words","role":"request","lang":"ar","text":"<the owner's Arabic words, byte-exact>","text_sha256":"<h>","gloss_en":"Agent's gloss: make the whole ETABS model from these DXF files in one go"}
{"seq":3,"kind":"searched","for_en":"a workflow that starts from DXF","where":"workflow_registry","result":"not_found","catalog":"unavailable","detail_en":"no workflow registry in this build; spec 0007 section 7 lists the DXF start as a non-goal","refs":["packages/eng-harness/docs/specs/0007-model-edit-cycle.md"]}
{"seq":4,"kind":"searched","for_en":"dxf-prep and etabs-model as harness tools","where":"cli_tools","result":"not_found","catalog":"unavailable","detail_en":"command-line tool adapter (plan 0002 T16, B-135) not built","refs":["packages/eng-harness/docs/specs/0002-servers-and-adapters.md"]}
{"seq":5,"kind":"not_found","by":"agent:<tool>","need_id":"need_<ulid>_1","category":"no_workflow","target":"dxf_to_etabs_model","need_en":"One workflow from DXF drawings to a complete ETABS model, continuing into the edit cycle","evidence":["#3","#4"],"blocking":true}
{"seq":6,"kind":"did_instead","way":"owner_by_hand","text_en":"Told the owner no workflow exists; he runs the Sasaah tools himself; no script written"}
{"seq":7,"kind":"owner_words","role":"answer","lang":"ar","text":"<verbatim reply>","text_sha256":"<h>"}
{"seq":8,"kind":"task_closed","status":"BLOCKED","summary_en":"No workflow; need recorded for the development session","open_needs":["need_<ulid>_1"]}
```

Travel of example A:

```
tasklog commit   -> commit <c1> "docs(tasklog): task_<ulid> BLOCKED"  (author eng-agent task log; trailer)
                    paths: tasklog/tasks/<yyyy>/<mm>/task_<ulid>/records.jsonl, .../STORY.md
tasklog push     -> push file allows, hook in place; fetch origin build/v1; check --unpushed: 1 commit, log-only;
                    push HEAD:refs/heads/build/v1 (fast-forward); the pre-push hook re-checks the range and lets it through
local CI (lead)  -> localci scope over <since>..<tip>, trusted code of <since>: <c1> is log-only (accepted);
                    secrets --range passes; the lead runs --accept; --tree runs at the next checkpoint
```

**B. An edit-cycle run that hit a gap** (after the first live run is possible):

```jsonl
{"seq":2,"kind":"owner_words","role":"request","lang":"ar","text":"<verbatim, with the owner's own values>","text_sha256":"<h>","gloss_en":"Agent's gloss: change a slab thickness and some beam loads, then analyse"}
{"seq":3,"kind":"did_instead","way":"harness_workflow","text_en":"Wrote the change set from the owner's words; no value added by the agent","refs":[".eng/tasklog/in/changes.json sha256:<h>"]}
{"seq":4,"kind":"run_attached","by":"harness","run_id":"run_<ulid>","workflow":"model_edit_cycle","status":"awaiting_engineer","exit_code":10,"event_count":"<n>","last_seq":"<n>","chain_sha256":"<h>","report":"runs/run_<ulid>/report/report.html","model_files":["<model base name>.EDB"]}
{"seq":5,"kind":"run_fact","by":"harness","run_id":"run_<ulid>","journal_seq":"<n>","event":"step_completed","summary_en":"change-set check refused edit kind slab_section","code":"NOT_IMPLEMENTED","gap":"H-G1"}
{"seq":6,"kind":"not_found","by":"harness","need_id":"need_<ulid>_1","category":"not_implemented","gap_id":"H-G1","target":"slab_section","need_en":"Edit kind slab_section (define and assign slab thickness)","detail":{"kind":"slab_section","step_path":"<path>"},"evidence":["run:run_<ulid>#seq=<n>","res_<id>#/issues/0"],"blocking":false}
{"seq":7,"kind":"owner_words","role":"correction","lang":"ar","text":"<verbatim: go on with the loads only; it names the model folder as <withheld:personal-path:<12-hex>>>","text_sha256":"<h of the original bytes>","redactions":[{"field":"text","rule":"personal-path","start":"<i>","end":"<j>","span_sha256":"<h>"}]}
{"seq":8,"kind":"did_instead","way":"partial","text_en":"Continued with the load edits only; the owner changes the slab in ETABS by hand, read as an engineer change next cycle"}
{"seq":9,"kind":"run_fact","event":"approval_resolved","summary_en":"engineer approved promotion on the page","owner_text":"<verbatim reason>"}
{"seq":10,"kind":"run_fact","event":"run_completed","summary_en":"cycle completed; column verdicts NEEDS_ENGINEER","gap":"EC-G2"}
{"seq":11,"kind":"not_found","by":"harness","category":"host_limitation","gap_id":"EC-G2","need_en":"Concrete design results for columns","evidence":["#10"]}
{"seq":12,"kind":"task_closed","status":"DONE_WITH_CONCERNS","summary_en":"Load edits applied on a working copy, checked after write, approved by the engineer; slab edit and column results not available","open_needs":["need_<ulid>_1","need_<ulid>_2"]}
```

Travel of example B: the run waited for the engineer (exit 10), so the agent committed and pushed after seq 4 with
subject `docs(tasklog): task_<ulid> OPEN` (writer: add `OPEN` to the subject status set for a commit of a task not yet
closed), and again after seq 12 with `DONE_WITH_CONCERNS`. Had the owner also edited `packages/...` in the same
worktree by mistake, `commit` (TLC008) would have refused to stage it, and `push` (TLC011) would have refused the
range, and the owner's pre-push hook would refuse the push; had such a commit reached build/v1 by another route,
local CI would flag it PS002 (a hard flag).

---

## 4. Plan outline: `packages/eng-harness/docs/plans/0015-task-log.md`

- Each task is one pull request, tests first (the `tests_first` files are inside the task's `files`), at most 380
  counted lines (tests are uncounted).
- Paths below are relative to `packages/eng-harness/` unless they start with the repository root folder. Every task
  that changes source also lists `CHANGELOG.md` (in scope by the playbook rule, listed so GC008 never fails).
- Risk: the plan's front matter lists **r2 and r3**. T1 edits `pyproject.toml` (floor `**/pyproject.toml`, r3) and adds
  the security-relevant modules `src/eng_harness/tasklog/_scope.py`, `_hook.py` and `_push.py` to the package
  `.gate/risk-map.yml` r2 entry and to `r2_modules` (mutation), so T8h and T8b are r2 without editing either file
  again. T14 edits `.gate/agents.yml` of the package (r3 if the root `.gate/**` floor applies to it; writer: verify
  with `risk-floor` and set the task's risk to what it reports). No task writes under `docs/schema/` (the record
  snapshot is a test snapshot), so no r2 floor comes from a schema. R1 nowhere.
- `covers` names spec 0015 ACs.
- Tests live in the existing folders: `tests/unit/tasklog/` (git tests use temporary repositories there, as the gate's
  unit tests do), `tests/unit/cli/` and `tests/workflow/`. There is no `tests/integration/` folder.
- `src/eng_harness/tasklog/_cli.py` is edited by many tasks, so those tasks form one chain in `depends_on`
  (T4b, T8h, T5, T7, T7b, T8, T8b, T9, T12); no two of them are open at once.
- The lane is parallel and never on the first-live-run critical path. T11 starts only after plan 0006 T14 (B-188), T14b
  and T18 (B-433) have merged, so it never edits a file an open critical-path task edits.

| id | title | files | max lines | tests_first (inside the task) | covers | depends_on | cross-plan |
|---|---|---|---|---|---|---|---|
| T1 | Record models, schema snapshot, risk entries | `src/eng_harness/tasklog/__init__.py`, `src/eng_harness/tasklog/_records.py`, `tests/data/snapshots/tasklog/record-1.json`, `pyproject.toml` (public_modules entry; `r2_modules` entries for `_scope.py`, `_hook.py`, `_push.py`), `.gate/risk-map.yml` (the same three in the r2 entry), `CHANGELOG.md`, `tests/unit/tasklog/test_records.py` | 300 | `tests/unit/tasklog/test_records.py` | AC1, AC2, AC32 | spec/plan 0015 approved | none |
| T2 | Guard, policy protocol, full, sanitized stub | `src/eng_harness/tasklog/_guard.py`, `src/eng_harness/tasklog/privacy/__init__.py`, `src/eng_harness/tasklog/privacy/_full.py`, `src/eng_harness/tasklog/privacy/_sanitized.py`, `CHANGELOG.md`, `tests/data/tasklog/secret_vectors.json`, `tests/unit/tasklog/test_guard.py`, `tests/unit/tasklog/test_policy.py`, `tests/property/test_guard_never_leaks.py` | 340 | `tests/unit/tasklog/test_guard.py`, `tests/unit/tasklog/test_policy.py`, `tests/property/test_guard_never_leaks.py` | AC4, AC5, AC6, AC7, AC8 | T1 | gate secrets vectors (read-only copy, pinned by hash) |
| T3a | Store and ids | `src/eng_harness/tasklog/_store.py` (append under `_runlock`, fsync, chain, consecutive seq, 900 000-byte cap, closed-task rules), `src/eng_harness/tasklog/_ids.py` (ULID from injected clock and id source), `CHANGELOG.md`, `tests/unit/tasklog/test_store.py`, `tests/unit/tasklog/test_ids.py` | 260 | `tests/unit/tasklog/test_store.py` | AC10, AC11, AC12 | T1, T2 | reuses `_runlock`, `eng_contract.canonical` |
| T3b | Log worktree validation | `src/eng_harness/tasklog/_worktree.py` (read-only git: same repository, inside it, outside `runs/`, sparse, local branch `eng-tasklog`, merge base), `CHANGELOG.md`, `tests/unit/tasklog/test_worktree.py` (temporary repositories) | 200 | `tests/unit/tasklog/test_worktree.py` | AC13 | T1 | none |
| T4a | `[tasklog]` configuration and the user-level push file | `src/eng_harness/cli/_config.py` (`[tasklog]`, no `push` key), `src/eng_harness/tasklog/_pushconf.py` (user-level file, refused inside a git working tree), `CHANGELOG.md`, `tests/unit/cli/test_tasklog_config.py`, `tests/unit/tasklog/test_pushconf.py` | 180 | `tests/unit/cli/test_tasklog_config.py`, `tests/unit/tasklog/test_pushconf.py` | AC26 (configuration cases) | T1 | spec 0006 §4.2.4 amendment carried in spec 0015 |
| T4b | Command module, part 1 | `src/eng_harness/tasklog/__main__.py`, `src/eng_harness/tasklog/_cli.py` (status, open, said, note, close, render stub), `CHANGELOG.md`, `tests/unit/tasklog/test_cli_open_close.py` | 320 | `tests/unit/tasklog/test_cli_open_close.py` | AC3, AC15, AC31, AC33 | T3a, T3b, T4a | none |
| T8h | Log-only definition and the pre-push hook | `src/eng_harness/tasklog/_scope.py` (the D5 test over `diff-tree --no-renames --raw`, pure), `src/eng_harness/tasklog/_hook.py` (shipped self-contained hook text, `install-hook`, in-place check), `src/eng_harness/tasklog/_cli.py` (install-hook; status hook line), `CHANGELOG.md`, `tests/unit/tasklog/test_scope.py`, `tests/unit/tasklog/test_hook.py` | 300 | `tests/unit/tasklog/test_scope.py`, `tests/unit/tasklog/test_hook.py` | AC34, AC35 | T4b | gate T41 applies the same definition; early: the agent's pushes with the owner's login wait for it (D6) |
| T5 | Command module, part 2 | `src/eng_harness/tasklog/_cli.py` (search, missing, refused, instead, problem, handoff, add --batch), `src/eng_harness/tasklog/_catalog.py`, `CHANGELOG.md`, `tests/unit/tasklog/test_cli_records.py` | 360 | `tests/unit/tasklog/test_cli_records.py` | AC16, AC17, AC18, AC19 | T8h | none |
| T6 | STORY.md rendering | `src/eng_harness/tasklog/_render.py`, `CHANGELOG.md`, `tests/unit/tasklog/test_render.py` | 300 | `tests/unit/tasklog/test_render.py` | AC20 | T5 | reuses `_text` (format_timestamp, sanitize_terminal) |
| T7 | Completeness checks | `src/eng_harness/tasklog/_check.py`, `src/eng_harness/tasklog/_cli.py` (check), `CHANGELOG.md`, `tests/unit/tasklog/test_check.py` | 360 | `tests/unit/tasklog/test_check.py` | AC24 (TLC001–005, 007, 009, TLW001–003) | T6 | none |
| T7b | Post-push withholding | `src/eng_harness/tasklog/_withhold.py`, `src/eng_harness/tasklog/_cli.py` (withhold), `src/eng_harness/tasklog/_check.py` (TLC001 `withheld_after` branch), `CHANGELOG.md`, `tests/unit/tasklog/test_withhold.py` | 220 | `tests/unit/tasklog/test_withhold.py` | AC27 | T7 | gate T42 accepts the same replacement form |
| T8 | Commit helper | `src/eng_harness/tasklog/_git.py` (commit), `src/eng_harness/tasklog/_cli.py` (commit), `CHANGELOG.md`, `tests/unit/tasklog/test_commit_git.py` | 280 | `tests/unit/tasklog/test_commit_git.py` | AC14, AC25, AC24 (TLC008) | T7b | none |
| T8b | Log-only push helper (the D6 exception) | `src/eng_harness/tasklog/_push.py`, `src/eng_harness/tasklog/_cli.py` (push; status unpushed), `src/eng_harness/tasklog/_check.py` (TLC011 on `_scope.py`, TLW004), `CHANGELOG.md`, `tests/unit/tasklog/test_push_git.py` | 300 | `tests/unit/tasklog/test_push_git.py` | AC26, AC24 (TLC011, TLW004) | T8 | gate T41 applies the same log-only definition after the push |
| T9 | attach-run core | `src/eng_harness/tasklog/_runfacts.py` (run_attached, run_fact, timings via `report/_model.fold_report`), `src/eng_harness/tasklog/_cli.py` (attach-run), `CHANGELOG.md`, `tests/unit/tasklog/test_attach_run.py` | 360 | `tests/unit/tasklog/test_attach_run.py` | AC21, AC23 | T8b | journal reader and report model (merged, plan 0001 T4, plan 0006 T11–T13) |
| T10 | Need derivation from runs | `src/eng_harness/tasklog/_runneeds.py` (§3.7 not_found rows incl. change_set_check issues), `src/eng_harness/tasklog/_check.py` (TLC006, TLC010), `CHANGELOG.md`, `tests/unit/tasklog/test_runfact_mapping.py` | 340 | `tests/unit/tasklog/test_runfact_mapping.py` | AC22, AC24 (TLC006, TLC010) | T9 | kinds `harness.change_set_check/1` (edit_cycle kinds, merged) |
| T11 | `run`/`resume --task` binding and `require_task` | `src/eng_harness/cli/_parser.py` (option only), `src/eng_harness/cli/__init__.py` (handler call sites), `src/eng_harness/cli/_run.py` (attach at start and exit), `src/eng_harness/cli/_options.py` (`task` reserved against generated options), `tests/helpers/cli_deps.py` (task-log fields of the shared builder), `src/eng_harness/tasklog/_hooks.py`, `CHANGELOG.md`, `tests/workflow/test_cli_run_task_link.py`, `tests/unit/cli/test_options_task_reserved.py` | 250 | `tests/workflow/test_cli_run_task_link.py`, `tests/unit/cli/test_options_task_reserved.py` | AC28, AC36 | T10; plan 0006 T14 (B-188), T14b and T18 (B-433) merged | spec 0006 §4.2.1 option amendment and an AC14 note (`task` reserved); writer: re-read the merged file names of plan 0006 T14 and T18 and list them exactly |
| T12 | Needs, triage, release-public, answered, digest | `src/eng_harness/tasklog/_needs.py`, `src/eng_harness/tasklog/_cli.py`, `CHANGELOG.md`, `tests/unit/tasklog/test_triage.py` | 360 | `tests/unit/tasklog/test_triage.py` | AC17 (hint source), AC29, AC30 | T10 (after T9 in the `_cli.py` chain; triage files travel as log-only commits through T8b) | none. **Deferred** until the first triage session needs it (the dev session can read STORY.md meanwhile) |
| T13 | Sanitized policy and export | `src/eng_harness/tasklog/privacy/_sanitized.py`, `src/eng_harness/tasklog/_export.py`, shared mapper module, `CHANGELOG.md`, `tests/unit/tasklog/test_sanitized.py` | 370 | `tests/unit/tasklog/test_sanitized.py` | AC9 | T2 | plan 0002 T17 (B-136); owner rules (still open). **Deferred** until the owner plans publication |
| T14 | Package rule and local testing | `.gate/agents.yml`, `docs/local-testing.md` (PowerShell said-file, sparse worktree setup on its local branch, the user-level push file, `install-hook` by the owner, the interim push form, offline, rotation and `withhold`), `CHANGELOG.md` | 150 | agents-drift job | none | T8b | plan 0006 I.T17b (the CLI agent rule in the same file) |

Gate tasks are in `tools/eng-dev-gate/docs/plans/0001-eng-dev-gate-0.1.md`: T40, T41, T42 and T43 (section 2.5). T42
depends on T41. T40 and T41 replace the lead's interims (§2.4) and may come before the first live run; T42 and T43
come after it unless the owner asks earlier.

---

## 5. The two named needs, as the first two log entries (examples; not designs)

They are written in the interim-1 format on the day ADR-0034 merges and committed in the log worktree as log-only
commits (D13). They are pushed only once the preconditions of D14 hold (PR A and PR B, the lead's scope step, the
sparse checkouts, the owner's visibility confirmation), and by the owner himself until his pre-push hook (plan 0015
T8h) is installed. They become JSONL when
the tool exists; interim files are never converted.

**Entry 1 (task_<ulid-1>), status BLOCKED**

- Request: the owner's Arabic words, verbatim. The lead has his phrasing from 2026-11-12; the writer copies it, never a
  translation.
- Gloss: "Agent's gloss: one workflow from the DXF drawings to a complete ETABS model".
- `searched` workflow_registry: not_found (catalog unavailable; spec 0007 §7 non-goal: "the DXF start").
- `searched` cli_tools: not_found (spec 0002 §4.7; plan 0002 T16, B-135, not built). `searched` specs: only the edit
  cycle and the footing and column workflows exist.
- `not_found`, category `no_workflow`, target `dxf_to_etabs_model`, blocking. Need: "dxf-prep prepare and inspect,
  etabs-model build, then the edit cycle's checks, in one workflow". Evidence: the two searches, plus spike S-12 §12
  (AutoCAD accoreconsole fixed to 2023; classify-columns not adopted, OQ-G14).
- `did_instead`: owner_by_hand. No script.
- Close: BLOCKED; one open need.
- Commit: `docs(tasklog): task_<ulid-1> BLOCKED`, paths `tasklog/tasks/<yyyy>/<mm>/task_<ulid-1>/STORY.md` only.

**Entry 2 (task_<ulid-2>), status BLOCKED**

- Request: the owner's Arabic words, verbatim.
- Gloss: "Agent's gloss: a calculation note from an existing structural model, for more than isolated footings and
  columns".
- `searched` workflow_registry: not_found (catalog unavailable).
- `searched` specs: found partial. The footing workflow (spec 0010) and the column workflow (spec 0013, three ACI
  318-14 checks, uniaxial only) exist as specs; neither is built.
- `searched` code_pack_checks: partial (structural-codes plans 0002, 0003, 0004 only).
- `not_found` `no_workflow` (target `calc_note_from_model`, other element families).
- `not_found` `no_code_pack_check` (target: the element families the owner names, quoted from his words only).
- `did_instead`: nothing; owner by hand.
- Close: BLOCKED; two open needs.
- Commit: `docs(tasklog): task_<ulid-2> BLOCKED`, paths under its own task folder only.

Neither entry names a value, an element size or a clause result. Needs that belong to the Sasaah tools (the DXF tools)
are only logged; nothing is filed in the Sasaah repository (read-only, AGENTS §9).

---

## 6. First-live-run path (D-32; amends D-27) — confirmed by the owner on 2026-11-12

This section is kept as written in v1. The owner confirmed it (lead decision D-32, superseding D-27's order); the lead
studies the shorter scenario C (6.3). Two notes, without changing the text: its facts were taken at `0f0aad1`, and
since then B-147 (C.T8) and B-455 (E.T13b) have merged (`origin/build/v1` `3b89c92`), so the waves shrink accordingly;
item 1's owner questions Q1 and Q2 are answered (section 7), and its "PR A and PR B" are those of section 2 of this
brief.

The first live run is: the owner runs `eng-harness run model_edit_cycle --run-class trial` on a copy of a real ETABS model through sasaah-csi-mcp on Windows. The first cycle only; later cycles need S.T15.

### 6.1 Documents and lead items before any code (in order)

1. **ADR-0034 PR A and PR B** (section 2). Not on the code path; it starts the interim log.
   - Owner: accept ADR-0034 (Q1, Q2).
2. **Lead documents amendment: plan 0006 T18.**
   - Make plan 0007 T9 (W.T9, B-203) the workflow-registry creator, as spec 0007 Q13 and plan 0010 §3 say. This removes X.T4–X.T9, Y.T2, Y.T3, Z.T5 from the path.
   - Split I.T18 into I.T18a (all defaults but the port builder) and I.T18b (the port builder, after the Q20 engine task).
3. **Contract path-rule amendment** (OQ-Q44 answer a). A new work item; an eng-contract minor version.
   - Blocks W.T2 and W.T8. Owner: OQ-Q44.
4. **Documents rename** of `compare.*`, `checks.readback_relative_tolerance` and `limits.ratio_limit` (spec 0007 Q12 b–d), in specs 0002, 0003 and 0007 and plans.
   - Blocks C.T8, C.T8b, C.T9, S.T12 as written. Owner: confirm Q12.
5. **Engine task: caller-chosen run id** (spec 0006 Q20 answer A; a new plan 0001 task).
   - Blocks I.T18b. Owner: OQ-Q45.
6. **The `point_policies` mapping and `assemble_decision_runtime` arguments** (spec 0006 Q16, Q15). A new task in plan 0006 or 0009.
   - Blocks I.T14b, P.T10, I.T18a. Owner: Q16.
7. **Plan 0007 W.T2 wording after the B-458 split** (C.T8 versus C.T8b). Lead documents amendment.
8. **Registry fixes:** add B-455, B-456, B-460; add the F.T3 dependency to B-138 (or apply 6.3).

### 6.2 Code tasks, scenario B (50 tasks; P.T3/B-222 is merged at 0f0aad1), in dependency waves

- **W1:** E.T13b B-455, C.T8 B-147, S.T12 B-131, B.T10 B-164, P.T9 B-228
- **W2:** E.T13c B-456, C.T8b B-460, S.T13 B-132, P.T4 B-223, W.T2 B-196
- **W3:** C.T9 B-148, E.T14 B-113, S.T14 B-133, P.T6 B-225
- **W4:** C.T10 B-149, E.T14b B-350, F.T1 B-210, P.T7 B-226, S.T16 B-135, W.T3 B-197, W.T5 B-199
- **W5:** E.T15 B-114, F.T2 B-211, S.T17 B-136, W.T4 B-198
- **W6:** E.T16 B-115, F.T3 B-212, I.T7 B-181
- **W7:** E.T17 B-116, I.T9 B-183, I.T7b B-429, W.T6 B-200
- **W8:** D.T7 B-171, E.T18 B-117, I.T10 B-184
- **W9:** D.T8 B-172, E.T19 B-118, I.T14 B-188, W.T7 B-201
- **W10:** D.T9 B-173, I.T14b B-353, S.T19 B-138
- **W11:** D.T10 B-174, I.T15 B-189, I.T16 B-190
- **W12:** I.T16b B-430, P.T10 B-229, W.T8 B-202
- **W13:** I.T18a and I.T18b (B-433), W.T9 B-203
- **Added:** I.T17b (package AGENTS rule "never read or relay the launch address"). It is needed because an agent operates the CLI in the live run; it is small and can go in any wave after T14b.

### 6.3 Candidate reduction for the lead to verify (scenario C; plan amendments under D-12/D-28)

- **Split S.T19** into a CSI-only `build_ports` (S.T19a) and SAFE plus command-line tools (S.T19b). This would move S.T16, S.T17, F.T1, F.T2 and F.T3 out of the path (−5). S.T16 returns with need (a), F.T* with SAFE work.
- **Provider lane:** ADR-0025 decision 5 says phase 1 decides with rules and the engineer. If a rules-only decision assembler can satisfy I.T14b without providers, P.T4, P.T6, P.T7 and P.T9 leave the path. P.T10 stays, or is replaced.
- Present both to the owner (Q10). Do not assume them.

### 6.4 Owner questions and local items that block the run (not any merge)

- OQ-A12 and OQ-Q53: provider dependency ADRs, if the P lane stays.
- Draft decisions that do not block, built per recommendation: spec 0001 Q26–Q34 (OQ-Q46).
- Local items:
  - spikes S-02 and S-04, which size the timeouts;
  - the pinned Sasaah build, its SHA-256 and the build procedure (LOCAL-TESTING open point 3);
  - the `--input` form (open point 4);
  - `--run-class trial` (open point 10);
  - a design-basis values file, every value cited by the owner;
  - a `doctor` run, expecting a fingerprint pin update by the lead.
- Later cycles on a real model: S.T15, ADR-0031 acceptance (OQ-A8) and an eng-contract release with `model_unlocked` and `server_owned_instance`. These come next after the first run.

### 6.5 Deferred (after the first run, or when the logs show the need)

- G.T2–T15
- R.T1–T15
- A.T1–T7
- H.T1–T9
- F.T4–T9
- X.T4–T13, Y.T2, Y.T3, Z.T5
- C.T11, C.T12
- W.T10–T12
- I.T17, I.T17c
- S.T15 (next after the first run)
- plan 0015 T12, T13
- gate T40–T42
- under scenario C, also S.T16, S.T17, F.T1–T3 and possibly P.T4, P.T6, P.T7, P.T9

Plan 0015 T1–T10 and T14 form a parallel lane with lower priority than the run path. T11 joins I.T18. Run facts of runs made before T11 are attached afterwards with `attach-run --run`, because journals persist.

(Read with this brief: plan 0015 now also has T3a, T3b, T4a, T4b, T7b, T8h and T8b in the parallel lane, and T11
waits for plan 0006 T14, T14b and T18 to merge; gate T43 is deferred with T42; gate T40 and T41 may come earlier
because they replace the lead's interims of section 2.4. The text above is unchanged.)

---

## 7. Owner decisions and what is still open

### 7.1 Answered on 2026-11-12 (recorded in ADR-0034)

| v1 question | Answer | Where it lands |
|---|---|---|
| Q1 A11 exception and location | full logs, client data included, in a root folder `tasklog/` of the code branch; not an orphan branch, not a separate repository; consequence for publication accepted | D4, D8, D9 |
| Q2 Cloud reading | cloud and local development sessions may both read the full logs | D11 |
| Q3 Push identity | the agent pushes log-only commits itself, on his machine, with his configured git login; recorded exception; nothing else that way | D5, D6, §2.3, A25 |
| Q7 `require_task` | refuse on his machine (true); tests and CI exempt | §3.6, AC28 |
| Q10 Build order | first-live-run path confirmed (D-32 supersedes D-27's order); the lead studies scenario C | D14, section 6 |
| (new) Travel | log-only commits pushed directly, no pull request; an automatic check refuses or flags any direct push outside the folder; secrets scan keeps running on logs | D5, §2.4, §2.5 |

### 7.2 Standing as drafted recommendations (not asked; the owner may change them)

- Q4 task granularity: one task per request; corrections stay in it; follow-ups after closing open a new task with
  `continues`.
- Q5 names in the full log: real names kept under `full`, with an optional project label he chooses.
- Q6 the sanitized copy: its rules are decided when publication is planned; until then `sanitized` is gap TL-G1.
- Q8 transcript: only its SHA-256 and the coding tool's session id in `task_opened`, never the content.
- Q9 command form: the module entry point (`python -m eng_harness.tasklog`), keeping the six-command CLI.
- Q12 Sasaah needs: only logged; nothing filed in the Sasaah repository while access is read-only.
- Q13 retention: logs kept indefinitely while the repository is private; publication only from a fresh or filtered
  history (now required, D9).

### 7.3 Still open for the owner (each with a recommendation)

1. **Direct log pushes to a protected `main`.** process/06 §5 disables direct pushes to `main` with no bypass for
   anyone. When bootstrap ends and protection exists, log-only pushes need either a bypass for his login on `main` (it
   would let that login bypass every rule, not only for logs), or a path-restricted push rule (to verify: whether the
   GitHub plan he chooses offers push rules restricted by path on a private repository), or an agent identity with a
   narrow rule.
   - *Recommendation:* decide at the end of bootstrap; prefer a path-restricted rule or an agent identity over a
     general bypass. Until then, build/v1 has no protection and the checks of D5 apply.
2. **Writers on other services and the logs in every checkout.** No longer open as a choice: the exclusion is a
   precondition of the first log push (D14, §2.4): the reference checkout and every writer worktree are sparse
   checkouts without `/tasklog/`, and the playbook forbids reading `tasklog/` outside consuming sessions. The only
   owner item left is the alternative the brief does not recommend: if he prefers to accept the exposure of client
   data to writers on other services (D-31) instead, his acceptance must be recorded before the first log push.
3. **Tasks asked in a cloud session, and triage pushed from a cloud development session.** The D6 exception is for his
   machine only. A cloud session can write log-only commits but has no rule for pushing them directly.
   - *Default until he decides:* cloud sessions only read logs; they push nothing under `tasklog/` with any login or
     tool (the session's GitHub access is the owner's account, OQ-Q50, and the GitHub tools can write to build/v1
     directly, so allowing it would widen the D6 exception beyond his machine, which he did not decide). A task asked
     in a cloud session keeps its log as local commits and names the unpushed task ids in its final status; triage
     is written in local development sessions on his machine.
   - *Options for him:* keep the default; or allow cloud pushes of log-only commits, which needs his explicit
     decision recorded as a change to D6, the same log-only definition (TLC011) and the same local CI detection,
     and no GitHub file-write tool.
4. **The D-4 bookkeeping commits and the push check.** The lead's direct bookkeeping commits on build/v1 (D-4,
   D-33) are direct pushes outside `tasklog/`. They are now stated in the root rules (§2.3, so A25 does not forbid
   them), and the check accepts them in bootstrap mode only, for the closed allowance of D5 (records and data only:
   `BUILD-STATUS.md`, `LOCAL-TESTING.md`, `HANDOFF.md`, `docs/build/HANDOFF.md`, `docs/build/priority.txt`,
   `docs/build/scenario-c.md`, `docs/build/task-log-brief.md`, `ops/remaining-tasks.json`). Changes to
   `ops/localci.py`, the lane workflow script, the playbook, `.gate/` or anything executable are hard flags the lead
   must acknowledge.
   - *Recommendation:* accept that allowance until bootstrap ends; with bootstrap off, only squash merges and log-only
     commits reach the integration branch.
5. **Personal paths in his words.** The guard withholds them (marker plus hash), because logs are in the scanned tree.
   - *Recommendation:* accept; the alternative is a `secrets.allow` entry per affected line, which the gate supports
     only by fingerprint and owner review.
6. **OQ-Q50** (the build sessions' use of his account) stays open and is not answered by D6.
7. **The Arabic originals for the ADR appendix**: the lead provides both rounds of his words from the session record;
   the writer copies them verbatim.
