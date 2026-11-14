# ADR-0034: The task log by default: every owner task has a log in `tasklog/`, pushed directly as log-only commits

Status: Proposed · Date: 2026-11-12 · Deciders: owner. The decisions below were given by the owner on 2026-11-12, in
two rounds of answers to the lead's questions; this written record awaits his acceptance (hub rule 3). On 2026-11-14
he answered open questions 1, 2, 3 and 5, recorded under each question.

## Context

The owner is a structural engineer. His answers of 2026-11-12, translated (the Arabic originals are in the appendix):

First round:

1. "I want it to be built while I work on a real project."
2. There is no "developer mode" and no such name. It is the default: "it records a log for every task I ask of the
   agent".
3. During live work the agent "only records in a log, in a defined way, and focuses on the live work".
4. The log "tells the whole story, and what the agent did not find".
5. Core development happens "in a separate session, local or cloud", with "the full process first".
6. The project lane ([ADR-0026](0026-project-lane-for-tools.md)) stays as it is: "those need no development".
7. The agent "writes it itself in a folder, in a defined way, and it is part of the repository and goes up as if it
   were code, through git".
8. "The tool is mine, and if it succeeds with me I will publish it to the public. But build it [the privacy part]
   separately so that I can change it, because I need the full log now, and later we change it to make a sanitized
   copy only."
9. English structure and narration, with the owner's own words kept verbatim.
10. The first live run comes first.

Second round (on the first design):

11. Location: a root folder of the workspace repository on the integration branch, not an orphan branch and not a
    separate repository. He was told the consequence (client data enters the code branch history; publishing later
    needs a fresh or filtered history) and chose it.
12. Travel: commits that hold log files only are pushed directly to the integration branch, without a pull request.
    An automatic check must refuse or flag any direct push that touches a file outside the log folder; the secrets
    scan keeps running on logs.
13. Push identity: on his machine the agent pushes the log-only commits itself with his configured git login, as an
    explicit, recorded exception limited to log-only commits; nothing else may be pushed that way.
14. Cloud and local development sessions may both read the full logs.
15. A run requested without an open task log is refused on his machine; tests and CI are exempt.
16. The first-live-run path is confirmed (lead decision D-32 in `BUILD-STATUS.md` §4, superseding D-27's order).

What exists today:

- The run journal (`<workspace>/runs/<run_id>/journal.sqlite`, git-ignored) records work that reaches a run. Nothing
  records a request that never reaches one; a refusal before a run creates no run folder.
- "Session report" is named in [process/01](../../process/01-lifecycle.md) §9 and ADR-0026, but nothing defines it.
- Every rule forbids client data in a repository (A11, [process/04](../../process/04-implementation-rules.md) §8,
  [process/07](../../process/07-release-and-open-source.md) §4, the pull request template, hub rule 6) and the
  owner's credentials to agents ([process/08](../../process/08-agent-operating-rules.md) §1,
  [process/11](../../process/11-repository-standard.md) §6).
- [process/06](../../process/06-review-and-merge.md) §5 forbids direct pushes to `main` for everyone. In bootstrap mode
  ([ADR-0028](0028-build-v1-in-this-repository.md)) nothing on GitHub enforces protection: no paid plan, and GitHub
  Actions cannot run, so CI is the lead's local reproduction of the CI workflow. The lead already commits its
  bookkeeping directly to `build/v1` (lead decisions D-4 and D-33).

The owner said of this design "انا متناقض" ("I am contradicting myself"): a full log holding client data now, and
publication later. This ADR holds both, through bounded, recorded exceptions and a replaceable privacy component.

## Decision

**D1. Default, no mode.** Every task the owner asks of the agent has exactly one task log. A task is one owner request;
a correction or clarification stays in its task; a new request opens a new task; a follow-up after a task is closed
opens a new task that names the earlier one (`continues`). "The agent" is the coding agent that operates the harness
command line in the owner's session ([ADR-0027](0027-phase-1-interface.md)), together with the harness.

**D2. Live work and development work.** A live session is one in which the owner asks for project work. A development
session is one started on a work item under the full process. A project-lane session is live work and keeps a task
log; its gap report stays its record. The task log is the "session report" of process/01 §9 (this defines a term
ADR-0026 left open; ADR-0026 is unchanged). During live work the agent completes what is possible only through harness
workflows, records everything in the task log, changes no repository file except its own task's files under
`tasklog/` (D4), never calls a host or MCP tool directly, and writes no improvised script, one-off tool, escape hatch
or unsourced number. A missing capability becomes a `not_found` record and the agent goes on; in live work this
replaces "file a gap report and report `BLOCKED`". Stop-and-ask (process/08 §4) still comes first when the owner is
present; if his answer does not resolve it, the agent logs the need and goes on.

**D3. Core development happens in a separate session** under the full process (issue, G1, G2, tests first, review,
CI). The task logs are its input (D11). A live session never develops the core.

**D4. Where the log lives.**

- Logs live in the root folder `tasklog/` of the private workspace repository (`eng-platform`, this repository), on the
  integration branch: `build/v1` in bootstrap mode, `main` after it. The folder is part of the code branch and its
  history.
- On the owner's machine the agent writes through a dedicated git worktree, recommended at
  `<repo>/.eng/tasklog/worktree/` (inside the repository directory, so A9 holds; git-ignored by the existing `.eng/`
  rule). It is a sparse worktree holding only `tasklog/` and `.gate/`, on the local-only branch `eng-tasklog` (never
  pushed by that name), so removing the folder never loses an unpushed commit. The owner's checkout, its branch, index
  and working tree are never switched, staged or changed by the log tool. Agent input files go to
  `<repo>/.eng/tasklog/in/` and are never committed.
- No code, test, build or gate step reads `tasklog/` except the gate's secrets scan, its push checks (`push-scope`,
  `tasklog-lint`), `publish-check` (D9), the pull request refusal (GC017, D5) and the harness task-log module. A log
  push therefore never changes the result of a pull request's CI.
- Packages split from `main` with their own directory history never contain `tasklog/`. The hub is published, if
  ever, from `design/` alone (D9).

**D5. Travel "like code": log-only commits by direct push.**

- A **log-only commit** (the single definition; every tool, hook, check and procedure cites it) is a commit with
  exactly one parent for which `git diff-tree -r -z --no-renames --raw <parent> <commit>` lists only entries where:
  the status is `A` or `M` (log records are never deleted or renamed; with rename detection off, a rename shows as a
  deletion plus an addition); the path fully matches the **log path pattern**
  `tasklog/(tasks/[0-9]{4}/[0-9]{2}/task_[0-9A-Z]+/(records\.jsonl|STORY\.md)|triage/need_[0-9A-Za-z_]+\.jsonl)`;
  the new mode is `100644` (no executable bit, symlink or gitlink); and the new blob is at most 900 000 bytes, valid
  UTF-8, with no NUL byte (so the secrets scan never skips it). A form that detects renames (`git diff --name-only`,
  `--name-status` without `--no-renames`, `git log --stat`) never decides log-only. `tasklog/README.md`,
  `tasklog/POLICY.json` and every other path under `tasklog/` are not log paths: the tool never writes them, and a
  commit that touches them is an owner step (D9).
- **Form** (required by the tool; judged only as a notice after the push): author and committer are the fixed log
  identity `eng-agent task log <tasklog@localhost>`; the subject is `docs(tasklog): <task_id> <status>` (`OPEN` for a
  task not yet closed), `docs(tasklog): triage <need_id>` or `docs(tasklog): withhold <task_id>`, with no other log
  text; the `Assisted-by:` trailer of process/04 §3.
- The agent commits each task folder in the log worktree and pushes with the harness push command, which pushes exactly
  `HEAD:refs/heads/<integration branch>`, fast-forward only, never forced, never with `--no-verify`. No pull request
  is opened for logs. On a rejected push it fetches, rebases its own unpushed log-only commits with the log identity
  as committer (local commits only, not a rewrite of shared history), re-checks and retries once.
- **Refusal before the push:** the push command refuses, pushing nothing, when any commit in
  `origin/<integration branch>..HEAD` of the log worktree is not log-only.
- **Refusal at the push:** the owner installs, once, a pre-push hook in the repository's common hooks directory,
  shipped by the harness as a self-contained file that imports nothing from the working tree. For every push to
  `refs/heads/<integration branch>` it refuses unless every commit in the range is log-only. It applies to the owner's
  own pushes to that ref too (he pushes code only through pull requests). The push command refuses to run while the
  hook is missing or differs from the shipped text. Stated limit: a program in the owner's OS account can defeat any
  client-side control; editing or bypassing the hook is a hook bypass (A6). Detection after the push is the backstop.
- **Detection after the push:** because GitHub refuses nothing here, the bootstrap CI checks every new first-parent
  commit of the integration branch since the last commit the lead accepted, with trusted code only (the check code and
  gate configuration of that accepted commit, never of the range it judges). Accepted: a pull request squash merge
  (committer GitHub, a valid signature by GitHub's pinned web-flow key, one parent, a `(#<n>)` subject, and pull
  request `<n>` merged with exactly this commit as its merge commit); a log-only commit; in bootstrap mode only, a
  lead bookkeeping commit with one parent whose paths, rename detection off, are all in the closed allowance
  `BUILD-STATUS.md`, `LOCAL-TESTING.md`, `HANDOFF.md`, `docs/build/HANDOFF.md`, `docs/build/priority.txt`,
  `docs/build/scenario-c.md`, `docs/build/task-log-brief.md`, `ops/remaining-tasks.json` (records and data only).
  Anything else is flagged. Flags are:
  - **hard** (merges stop until the lead has recorded the flag and reverted the commit by a new commit, or recorded why
    it stands): a path outside the log paths and the allowance (code, tests, other `ops/` files, agent-steering files
    under `docs/build/`, `.gate/`, `.github/`, `tools/`, protected paths); a `tasklog/` path that is not a log path; a
    mode other than `100644` or a deletion under `tasklog/`; a two-parent commit; rewritten history; an unverified
    squash merge; a secret; a file under `tasklog/` the secrets scan skipped. The lead reverts without waiting for the
    owner; a commit touching `tasklog/POLICY.json` or `tasklog/README.md` stands only with the owner's recorded
    confirmation;
  - **soft** (recorded; merges go on): a log-only commit of the wrong form; another Markdown file under `docs/build/`.
  The same check scans the added lines with `secrets --range`, and checkpoints scan the tree with `secrets --tree`.
- **Pull requests:** the gate refuses any pull request into `build/v1` or `main` whose changes from the merge base
  (both sides of a rename) touch `tasklog/**`, whatever its `Plan-Task:` line, project lane included (GC017). The
  bootstrap merge of `build/v1` into `main` is exempt: it carries the logs by design. Logs never appear in file
  scopes, line budgets or CI reviewer payloads.
- Offline, commits stay local in the log worktree. No force push, no hook bypass, no history rewrite of the
  integration branch (A6, A16). How log-only pushes reach a protected `main` is decided by the owner at the end of
  bootstrap, with a path-restricted rule or an agent identity preferred over a general bypass (question 1).

**D6. Push identity: one recorded exception to "never the owner's credentials".** By the owner's decision:

- On the owner's machine, and only there, the harness push command may use the owner's configured git login (his
  credential helper) to fetch the integration branch and to push log-only commits (D5) to it.
- Limits: only through that command (never a hand-typed `git push`, except the interim procedure of D13, which runs the
  same checks by hand); only the integration branch ref; only fast-forward; only log-only commits; only while the
  pre-push hook (D5) is in place; only with `push = true` in the owner's user-level push file
  (`<user configuration folder>/eng-harness/tasklog-push.toml`), which the owner writes himself, which the agent never
  writes or edits, and which the tool refuses when it resolves inside any git working tree (no workspace file can grant
  the push); never in a cloud session; never with `--force`, `--no-verify` or any hook bypass; never a GitHub API
  call, pull request, issue, comment, merge or other repository with that login.
- Until the hook exists and the owner has installed it, the agent never pushes with his login: it runs the D13 checks,
  prints the push command, and the owner runs it himself.
- Everything else stays forbidden: an agent never pushes anything outside `tasklog/` with the owner's login, never
  reads, copies or stores his token. This does not settle owner queue item OQ-Q50 (the build sessions' use of the
  owner's account).
- The lead's bootstrap bookkeeping pushes (D-4, D-33) are a separate, existing practice, not this exception: the
  workspace root rules state them, and the push check limits them to the allowance of D5. The lead rebases its
  unpushed bookkeeping commits before pushing, never a merge commit.
- Cloud sessions push nothing under `tasklog/`, with any login or tool (question 3, answered 2026-11-14). A task asked
  in a cloud session keeps its log as local commits, and the session names the unpushed task ids in its final status.

**D7. Privacy is a separate, replaceable component** of the harness, selected by a required `policy` setting with no
default.

- **The guard** is always on, not replaceable, and applied before any policy. It keeps secrets, credentials, page
  launch addresses and tokens out of every log, and personal home paths out of every field. In owner words it rewrites
  only one way: a span matching a hard secret rule or the personal-path rule is withheld with a visible marker and its
  hash. Personal paths are withheld because the logs are in the tree the secrets scan reads, which has no per-path
  profile.
- **The policy** is one pure transform per record: `full` (now) is identity apart from the guard; `sanitized` (later)
  is used at write time once selected, and to derive a sanitized copy from full logs, whose originals are never
  rewritten. Until the owner defines its rules, `sanitized` is a `NOT_IMPLEMENTED` gap.

**D8. Recorded owner exception to A11 and hub rule 6, bound to one folder.**

- Full task logs, which may hold client and project names, model file names, engineer names and the owner's verbatim
  words, may be committed only under `tasklog/` at the root of the private workspace repository, on its integration
  branch and therefore in its history, and only while `tasklog/POLICY.json` says `full`.
- A11 stays unchanged in the template and every package `AGENTS.md`. The exception is stated here and rendered only
  into the workspace-root `AGENTS.md`. Package repositories split from `main` never receive it.
- Hub rule 6 stays in force for every hub document: no log content ever enters `design/` (A24). Because the hub lives
  in the same repository, rule 6 states the one exception and how the hub is published.
- Secrets and personal paths are not part of the exception (D7).
- **A24, containment.** Nothing from a task log leaves `tasklog/`: it is never copied into another path of any branch,
  any package, an issue, a pull request title or body, a commit message, a spec, a plan, a changelog, the digest, a
  build record or a provider payload, except need ids, task ids, categories, gap ids, codes and counts, and a neutral
  English need statement (`public_en`) written at triage, with no client, project, person, place or model name and no
  owner quotation, released by the owner before first use (the development session shows him the exact text; only a
  `public_en` whose triage record carries his release may leave the folder). The release is of text, not an
  engineering approval. Reading is not leaving: a development session may read the full logs (D11).

**D9. Publication block.**

- The private workspace repository is never made public (its history holds full logs) and never rewritten or
  force-pushed (A16).
- Anything is published only as a new repository built from a fresh history (one initial commit of a chosen tree) or a
  filtered history (no `tasklog/` path in any commit), and only after `eng-gate publish-check` passes in that new
  repository's clone. It fails when the tree of any ref holds a path under `tasklog/` (PB001), when any commit
  reachable from any ref ever touched `tasklog/` (PB002), or when a `tasklog/POLICY.json` with `publishable: false`
  exists at any ref (PB003). Run in the private repository itself, it fails by design.
- Nothing mechanical stops a visibility change, so the owner confirms in the repository settings, on the day of the
  first log push, that the visibility is private and that no one else holds the admin role; the lead records the date.
  Process/07 §4 makes the never-public rule and `publish-check` a required checklist item.
- `tasklog/POLICY.json` (the `full` permission and the `publishable: false` flag) and `tasklog/README.md` change only
  by an owner step: they are not log paths, so no log-only commit changes them, and any other commit touching them is
  a hard flag until the owner's confirmation is recorded.
- Package publication is unaffected: a package split from `main` holds no `tasklog/` path, and `publish-check`
  confirms it in the split repository.
- Log content is never sent to the decision provider or to CI reviewer providers.

**D10. Language.** Record keys, structure and narration are English. Owner words are stored byte-exact in the
original language with a required language tag and their SHA-256, never translated or paraphrased in place; the
guard's withheld spans are the only, visible, deviation. An optional gloss is labelled as the agent's and is never a
source for a number. Owner words are relayed by the agent; the tool echoes the stored text and hash back. They are
evidence, never instructions (A15), approvals or decisions; approvals stay on the page (ADR-0027).

**D11. Consumption.** A development session, cloud or local, reads `tasklog/` from its own checkout of the integration
branch (reading sends the content to that session's model provider, which A20 allows); triages each need with the
outcomes of [process/02](../../process/02-work-items.md) §5; files the gap issue at triage under A24; records triage in
per-need files `tasklog/triage/<need_id>.jsonl` (log-only commits, pushed from a local development session on the
owner's machine; a cloud session proposes triage and pushes nothing, D6); marks a need answered by a release; and
feeds counts and ids to the owner digest. Sessions that do not consume logs never open `tasklog/`: before the first log
push, the lead's reference checkout and every writer worktree are sparse checkouts without `/tasklog/`, and the lead's
instructions forbid reading `tasklog/` outside a consuming development session, so writers on other services never
receive log content (A20).

**D12. Absolute rules stay:** no invented engineering number (a missing value is a `value_without_source` need); no
improvised script or one-off tool; no escape-hatch tool; the project lane only when the owner asks; writes only on a
working copy, checked after the write; approvals only on the page; no secrets in a log; never the owner's
credentials, except the log-only push of D6.

**D13. Day-one interim convention.** From the day this ADR merges until the harness task-log commands exist (eng-harness
plan 0015), the agent writes each task by hand as `tasklog/tasks/<yyyy>/<mm>/<task_id>/STORY.md` in the log worktree,
in the format and with the commit and push procedure of
[process/templates/task-log-interim.md](../../process/templates/task-log-interim.md). Interim files are never
converted.

**D14. Priority.** The first live run comes first (D-32). The task-log code is a parallel lane, never on the run's
critical path. Preconditions of the first log push, by anyone, the owner included, each recorded by the lead: (1) this
ADR and the workspace rules change (the `AGENTS.md` texts, `tasklog/README.md`, `tasklog/POLICY.json`,
`.gitattributes`) merged; (2) the lead's interim push check of D5 live; (3) the reference checkout and every writer
worktree sparse without `/tasklog/`, with the reading rule of D11 in place; (4) the owner's visibility confirmation
(D9). Pushes by the agent with the owner's login also need the pre-push hook installed (D6). Until then logs are
written and committed locally and stay unpushed.

**Standing recommendations** (not asked; the owner may change them): one task per request (D1); real names kept under
`full`, with an optional project label he chooses; the sanitized rules decided when publication is planned; of the
coding tool's transcript only its SHA-256 and session id are recorded, never the content; the task-log commands are a
module entry point of the harness, keeping its six-command CLI; needs that belong to the Sasaah tools are only logged,
nothing is filed in the Sasaah repository; logs are kept indefinitely while the repository is private.

## Questions for the owner

Questions 1, 2, 3 and 5 were answered by the owner on 2026-11-14 (his words are in the appendix); questions 4 and 6
are open.

1. **Log-only pushes to a protected `main`.** Process/06 §5 disables direct pushes to `main` with no bypass. When
   bootstrap ends, log-only pushes need a bypass for his login (it would bypass every rule, not only for logs), a
   path-restricted push rule (if his GitHub plan offers one on a private repository), or an agent identity with a
   narrow rule. *Answered 2026-11-14:* decided at the end of bootstrap; a path-restricted rule or an agent identity is
   preferred over a general bypass. The choice itself is made then.
2. **Exposure to writers on other services.** The alternative to the sparse checkouts of D11 is accepting the
   exposure of client data to writers on other services, which needs his recorded acceptance first. *Answered
   2026-11-14:* the sparse-checkout precondition of D11 stays a precondition of the first log push (D14).
3. **Log pushes from cloud sessions.** D6 is for his machine only; allowing cloud pushes of log-only commits would be
   a change to D6 (their GitHub access is his account, OQ-Q50). *Answered 2026-11-14:* cloud sessions read logs and
   push nothing under `tasklog/`; the push exception of D6 is for the owner's machine only.
4. **The lead's bookkeeping allowance.** *Recommendation:* accept the closed allowance of D5 until bootstrap ends; then
   only squash merges and log-only commits reach the integration branch.
5. **Personal paths in his words.** The alternative to withholding them is a reviewed secrets allow entry per affected
   line. *Answered 2026-11-14:* the guard withholds them (D7).
6. **OQ-Q50** stays open; D6 does not answer it.

## Consequences

- Positive: every request leaves a story, including requests that reach no workflow; the development session gets
  typed, triageable needs from any checkout; no second branch or repository to keep in step; no weakening of
  gate-check or "work without an issue is not merged", because logs never enter a pull request.
- Negative: client data is in the integration branch history for good, so the workspace repository can never be made
  public and publication needs a new repository; every full checkout holds the logs, so writer checkouts must be
  sparse; in bootstrap mode the folder rule is enforced only client-side on the owner's machine and detected after the
  push; the lead must acknowledge every hard flag, its own changes to `ops/` and agent-steering files included; an
  agent uses the owner's login for one narrow purpose; the history gains many small `docs(tasklog):` commits;
  completeness depends partly on the agent; owner words are agent-relayed, not authenticated.
- Changes in the same change as this ADR: golden rules 4 and 7; process/01, 02, 04, 06, 07, 08, 11, 12; architecture
  03, 11, 16, 19; hub rule 6; the templates `task-log-interim.md` (new), `issue-gap.md`, `feature-spec.md`,
  `workflow-spec.md`, `tool-spec.md`, `release-checklist.md`, `pull-request.md`; the Arabic overview.
- Separate changes: the `AGENTS.md` template, the workspace root rules (with the D6 exception and the bookkeeping
  pushes), the re-rendered `AGENTS.md` files of the workspace root, eng-contract, structural-codes, eng-harness and
  eng-dev-gate, `.gitattributes`, `tasklog/README.md` and `tasklog/POLICY.json`; the eng-dev-gate spec and plan
  amendment (GC017, push checks, `publish-check`); eng-harness spec and plan 0015 (amending spec 0006 with the
  `[tasklog]` configuration and the `--task` option); the lead's interim push check.

## Alternatives considered

- **An orphan `tasklog` branch, never merged**: rejected by the owner; he wants the logs in the code branch.
- **A separate private repository**: rejected by the owner ("part of the repository"); it was the safest for
  publication.
- **Logs through pull requests under a new gate reason**: a gate lane with no work item or budget, a pull request per
  task, and log content in diffs and reviewer payloads. The owner chose direct push.
- **Logs only in the local workspace**: the owner wants them in the repository, and a cloud session could not read
  them.
- **A separate agent identity for log pushes**: none exists; the owner chose his login with recorded limits. It returns
  when an agent identity exists (question 1).
- **A seventh CLI command**: reopens the harness CLI's six-command criterion; a module entry point is used instead.
- **New journal event types**: the event set is closed, the engine is the single writer, and blocks do no I/O.
- **Refusing writes on any secret pattern in owner words**: loses owner words mid-session.
- **The tool's own refusal as the only control of the credential exception**: the owner's login is an ambient
  credential helper, so any `git push` in his OS account carries it; the owner-installed pre-push hook is required.
- **The push permission in `harness.toml`**: a workspace file the agent can edit; it lives in a user-level file.

## Pre-mortem

| Failure a year from now | Guard |
|---|---|
| The repository was made public and the logs leaked | D9: never made public; publication only as a new repository after `publish-check`; the owner's settings confirmation on the day of the first log push |
| A code change rode in on a direct "log" push | one log-only definition, rename detection off (D5); the push command and the owner's hook refuse; detection after the push from trusted code; hard flag, reverted by a new commit |
| A direct push rewrote the check that judges it | the check runs from the last accepted commit; `ops/`, `.gate/` and agent-steering files are outside the allowance |
| A forged squash merge passed | GitHub's pinned web-flow signature plus the pull request's merge commit |
| A log line was carried by a pull request | GC017 on the merge-base diff |
| The owner's login was used for something else | D6 limits; A25; no ref or remote argument; push permission only in a user-level file; the hook; detection of every other direct commit |
| The publication block was switched off by a log push | `tasklog/POLICY.json` and `tasklog/README.md` are not log paths; any change is a hard flag |
| A secret hid in a large or binary log file | the 900 000-byte cap, UTF-8, no NUL (D5); a skipped file under `tasklog/` is a hard flag |
| Requests went unlogged | A23, `require_task`, the status check at session start, task ids in the final status, orphan-run detection |
| Arabic was corrupted on Windows | the agent's file tool writes the words; strict UTF-8; the hash echoed back; `tasklog/** -text`; fenced blocks in `STORY.md` |
| A secret reached a pushed log | the guard; the pre-push check; the secrets scans after the push; rotation and a withholding commit, never a history rewrite |
| Needs leaked into public issues or packages | A24; `public_en` released by the owner; split packages hold no `tasklog/` |
| A writer on another service received client data | D14 precondition: sparse checkouts and the reading rule |
| A false flag or an absent owner stalled every merge | only hard flags stop merges; the lead reverts without waiting for the owner |
| The log tool delayed the first run | D14: never on the critical path |

Early warning: a hard flag of the push check, a `docs(tasklog):` commit that is not log-only, or a live session whose
final status names no task id.

## Appendix: the owner's words (Arabic, verbatim)

The originals are copied from the lead's record of the session, never translated back from the Context above.

> انا متناقض

On 2026-11-14 the lead put questions 1, 2, 3 and 5 above to him, each with its recommendation. He answered in one line
that the recommendations are applied. It answers those four as recommended; questions 4 and 6 were not part of that
batch and stay open:

> نفّذ التوصيات

The originals of answers 1 to 16 are inserted here from the lead's session record before the owner accepts this
record; until then this appendix is incomplete.
