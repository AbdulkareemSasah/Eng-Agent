# Integration and continuation checkpoint of 2026-11-17 (build/v1 at 1ec7566)

The owner authorized continuation after the quota pause. This checkpoint records integrated state and active guidance; it does not change product source. The reference checkout is detached at `1ec7566c016aacf75c15aacb260435df44f23c67`. No CI job is currently running.

This top checkpoint is authoritative. Older handoffs and machine snapshots below are retained for history and are superseded where their state differs.

## A. Integrated state

- **Plan progress:** 232 of 354 current plan tasks merged. The registry has 183 entries. B-551/#415, B-553/#416 and B-561/#414 are merged. B-550/#411, B-552/#412 and B-560/#413 were already checkpointed. Merge records and CI evidence for the current three are in [integration-2026-11-17/](integration-2026-11-17/).
- B-551 squash: `9c26ab3435c9dd3867313bdef2eb60e63633c218`; B-553 squash: `1ec7566c016aacf75c15aacb260435df44f23c67`; B-561 squash: `c803dad7f65f1f9a4f3b770dcb12bb080504e02c`.
- B-553's risk is `r2, r3` after B-561; its DOC.B561 dependency is cleared. B-551 has no pending dependencies. The registry IDs and merged PR fields reflect these integrations.
- Earlier continuation already integrated B-544/#408 (registry tasks W.T7b/W.T16b/W.T9c/I.T9c), B-547/#410, and B-554/#409; B-551, B-552, B-553 and B-561 are now integrated as listed above. Existing task-log items remain: B-537 PR #384 appears open through the API although its content is integrated at `45dc8ab9`; do not redo or close it. B-334 PR #331 remains frozen. B-164 PR #323 needs the documented future TF004 rebuild.

## B. Current first-live-run order

1. **B-138 (S.T19a)** and **B-556 (W.T7b)** are active; their writers are using `.worktrees/b138` and `.worktrees/b556`.
2. Then B-555 (W.T17), B-557 (W.T16b), and the B-164 rebuild in the established order before B-202 (W.T8). B-164 remains held for its documented TF004 rebuild after its prerequisites.
3. B-202 waits for B.T10 (B-164), S.T19a (B-138), and W.T7b (B-556); E.T23 (B-551) is merged and cleared. Continue with the existing owner order after those dependencies.
4. Refresh remote PR state before integration work. There is no local CI run in progress.

## C. Mutation and CI state

- Periodic mutation run 5 passed (exit 0), six members; interval 11:09:17–11:24:15 UTC (898 seconds), base `4f1a7e67`, head `d9c19fb`. Its proof is [periodic-mutation-d9c19fb.log](integration-2026-11-17/periodic-mutation-d9c19fb.log). Three PR merges (#414–#416) followed that run, so the next periodic run is due after seven additional PR merges, using `d9c19fbd` as its base.
- B-551 per-change mutation passed the configured 80% floor on authored head `b55b965b`; successful output did not emit an exact score, so none is claimed.
- B-553's mutation selector passed, but the package has no eligible configured R1/R2 modules; no numerical score is claimed.
- B-551 and B-553 passed batched local CI on exact PR heads `db65b2a60e7184d68d5c782a252eb83ed06dbf4e` and `580fa8881eda103033da6e6c09826d1b93690db3`. The full gate ran on batch tree `9db7ea3f93ded33999befc85e126bf9c419fdbdf`, 895 seconds, with both CI summaries matching that tree. B-561 local CI passed on exact head `6fda1a2beea771e1223d9acd6c2355247c414f06`; its full gate took 1249 seconds.
- The B-561 automatic base merge commit `6fda1a2beea771e1223d9acd6c2355247c414f06` lacked an `Assisted-by` trailer. It was published before detection and was preserved; the final squash commit has the required sole trailer.
- Windows was not run on this Linux machine. `uv audit --locked` was not run because `api.osv.dev` is outside AGENTS.md §9 allowed services. Both remain owner local-test items. No claim is made that either check passed.
- First live host behavior remains unverified pending owner-side testing.

## D. Active changed-line guidance

B-553 is merged: GC009 reports counted lines as a notice. Changed-line counts are informative only. They never stop work, trigger a split, or require a plan amendment; scope, test-first, risk floor, and `max_sessions` remain binding. D-12 is marked superseded in BUILD-STATUS.md. Active playbook and workflow copies are updated; historical checkpoints and v34 are preserved as history.

## E. Machine layout and continuation

- Reference checkout: `/workspace/Eng-Agent`, detached at the current `build/v1` head above. Worktrees: `/workspace/Eng-Agent/.worktrees`; lead scratch: `/workspace/Eng-Agent/.lead`; active writers are in `.worktrees/b138` and `.worktrees/b556`. Scratch copies and task worktrees are ignored through `.git/info/exclude`.
- Continue using the configured environment paths: `UV_CACHE_DIR=/workspace/Eng-Agent/.lead/uv-cache` and `UV_PYTHON_INSTALL_DIR=/workspace/Eng-Agent/.lead/python`; setup used `uv sync --all-packages --locked` with uv 0.13.6 and CPython 3.14.10. Setup evidence and prior machine measurements are in [machine-layout.md](resumed-2026-11-17/machine-layout.md).
- The live lead playbook and workflow helpers are in `.lead/PLAYBOOK.md`, `.lead/lane-scripts/`, and `.lead/tools/`; tracked reference copies are under `docs/build/`. Reconstruct/refresh those ignored runtime copies from the tracked files when a new machine or environment replaces the workspace.
- The existing handover record above was made 2026-11-17; its B-544/#408, B-547/#410 and B-554/#409 completions remain valid. Its older pre-integration state for B-551/B-552/B-553 is superseded by this checkpoint.


---

# Resume update of 2026-11-17 (build/v1 at 2a2171ea)

This is the newest machine-side checkpoint. No new merges are recorded since the prior checkpoint; the older handoff below remains for its history. The latest measured counts supplied for this resume are 229 merged plan tasks of 353 current plan tasks, and 182 registry entries after adding B-560. The prior handoff retained a total of 349 after B-544 had added four tasks (W.T7b, W.T16b, W.T9c and I.T9c); recounting current plan front matter gives 353. The registry before B-560 had 181 entries; B-554 is pull request #409 and is now recorded as merged.

## A. Current work and reviews

- **B-550 (S.T23):** task branch `feat/b550-harness-st23-open-original-visible-launch`, resumed from published head `e65e608` with the build/v1 merge and collateral test; final head `79302d00953686dea66e21d671cc17a0fc242553` has the same tested tree as `d032e673`. Focused tests (25), package gate, test-first and mutation checks passed; mutation found zero eligible R1/R2 modules (no score, no MU003). Independent review APPROVE. Task-branch push was confirmed fast-forward, `e65e6080..79302d00953686dea66e21d671cc17a0fc242553`. This resumed session created no PR and ran no local CI; current PR-list status is unverified. Review: [b550-review.md](resumed-2026-11-17/b550-review.md).
- **B-551 (E.T23):** published branch remains at `2361039`; blocked on B-560, then needs the documented one-line collateral test adjustment and a rerun of its gate. Independent implementation review remains outstanding; this resumed session created no PR, and current PR-list status is unverified.
- **B-552 (G.T40 documents):** local continuation head `8cb72712` (author metadata corrected before publication; tree matches `0200eebd`); independent review APPROVE and `uv run eng-gate check --package eng-dev-gate --skip mutation` passed on that tree. The early task-branch push to origin is confirmed; this resumed session created no PR and ran no local CI; current PR-list status is unverified. B-553 stays dependent on DOC.B552. Review: [b552-review.md](resumed-2026-11-17/b552-review.md).
- **B-554:** merged as #409; registry corrected to `merged_pr: 409` and `branch_pushed: true`.
- **B-560:** local documents branch `docs/b560-engine-t23-collateral-test`, head `c4d0e566`; adds `packages/eng-harness/tests/unit/test_ctx_basis.py` to plan 0001 T23's file list and records why. Independent review APPROVE and `uv run eng-gate check --package eng-harness --skip mutation` passed on `c4d0e566`. The early task-branch push to origin is confirmed; this session created no PR and ran no local CI; current PR-list status is unverified. B-551 now depends on DOC.B560. Review and writer note: [b560-review.md](resumed-2026-11-17/b560-review.md), [b560-writer.md](resumed-2026-11-17/b560-writer.md).

B-550, B-552 and B-560 task-branch pushes are confirmed. This resumed session created no PR and ran no local CI for them; current PR-list status is unverified. B-164 (B.T10) remains queued; it is still a prerequisite for W.T8 (B-202), and its prior PR #323 failed local CI on TF004. Keep it in the prescribed order and do not start it yet.

## B. Resume blockers and external state

Git fetch and remote branch listing succeeded: 429 remote branches were listed and `origin/build/v1` is at `2a2171ea`. The GitHub API endpoint `api.github.com` returned HTTP CONNECT 403, and no GitHub MCP tool was available, so open pull requests and remote local-CI/merge state could not be refreshed. A `GH_TOKEN` variable exists, but its value was not read or printed and no authentication conclusion was drawn. The owner said «سأطبّق تعديل الشبكة» (“I will apply the network change”); application is not yet confirmed. PR listing, pull-request creation, local CI via the pull-request runner, and merges remain outstanding. Restore API access and check the current PR list before creating or updating pull requests. Afterward, run local CI on each current PR head and merge only on PASS.

The latest seven PR merges are after periodic mutation base `4f1a7e6`; the next periodic mutation run is due after three more PR merges, using base `4f1a7e6`. Do not claim any additional mutation result.

## C. Next order

1. Confirm API access after the owner applies the network change; refresh `origin/build/v1`, remote task branches and open PRs before acting.
2. B-550 local checks passed and its task-branch push is confirmed at `79302d00953686dea66e21d671cc17a0fc242553`; mutation found zero eligible R1/R2 modules (no score/no MU003). B-560 package gate passed and its task-branch push is confirmed. Recheck local branches and reviews, then create or merge pull requests only after the lead checks current remote state and CI requirements.
3. Merge B-560 before resuming B-551. Then apply the recorded assertion adjustment to B-551, run its package gate and obtain independent implementation review.
4. Resume B-552's approved continuation, then B-553 after B-552 merges. Complete B-550's PR and local CI before starting B-138 (S.T19a).
5. Keep B-556 on its planned parallel first-live-run path. B-202 (W.T8) waits for B.T10 (B-164), E.T23 (B-551), S.T19a (B-138) and W.T7b (B-556). Keep B-164 queued until its documented order/dependency allows it; do not jump ahead.
6. Continue the first-live-run order in the previous checkpoint and registry. The first live host behavior remains unverified until owner-side testing.

## D. Machine layout and setup

The reference checkout is `/workspace/Eng-Agent` on `build/v1`, HEAD `2a2171ea`; worktrees are under `/workspace/Eng-Agent/.worktrees`; lead scratch is `/workspace/Eng-Agent/.lead`. Playbook, priority list, findings, resume material, tools and workflow scripts are copied under `.lead/`; `.lead/` and `.worktrees/` are excluded through `.git/info/exclude`. Linux x86_64, 5 available processors, 34,906,004 kB total memory. `uv sync --all-packages --locked` succeeded with CPython 3.14.10 and uv 0.13.6; see [machine-layout.md](resumed-2026-11-17/machine-layout.md) for setup results and the two non-blocking uv-build version warnings. No tests or gates were run for machine setup.

## E. Durable resumed notes

Review records, writer handoffs, pull request bodies and compact gate/push logs are copied to [resumed-2026-11-17/](resumed-2026-11-17/). Machine-specific paths in those copies use `<lead>`, `<worktrees>` and `<build-v1>` placeholders. Full gate logs remain in the lead scratch folder and may be checked by their owners when the running commands finish.

---

# Build handoff checkpoint of 2026-11-17 (build/v1 at d5ea640, updated to 8b2722f and later): hand-over to a lead on another machine

Written by the lead of the cloud session when the owner asked for a hand-over to another agent on another machine
(2026-11-17, about 09:30 UTC). This was the newest checkpoint at that hand-over; the resume update above supersedes its current-state details, and the sections below stay for their history.

## A. State

- **Plan tasks merged: 229 of 349** (228 at the first write of this section; B-547 #410 merged after it) (the total is the `- id:` entries in the front matter of every plan under
  `packages/**/docs/plans/` and `tools/*/docs/plans/`, recounted at d5ea640; it grew from 340 by the tasks the
  first-live-run walk-through added). Merged since the checkpoint of 2026-11-16: B-200 #383, B-174 #385, B-204 #386,
  B-229 #387, B-184 #388, B-524 #391, B-519 #381, B-532 #392, B-520 #394, B-534 #395, B-198 #396, B-521 #397,
  B-117 #389, B-118 #399, B-525 #400, B-201 #402, B-548 #405, B-546 #406, B-549 #407; documents B-537, B-538, B-536,
  B-542, B-545, B-541, B-543; lead tooling B-539 (local CI batch mode, three direct commits by the owner's word).
- **Registry:** `ops/remaining-tasks.json` has 177 entries; every merged entry now carries `merged_pr`; B-546 to B-555
  were added; B-138 (S.T19a) has risk `r1, r2, r3` and waits only for S.T23 (B-550).
- **Priority:** the first live run (D-32). The path is in [priority.txt](priority.txt) and in section C.

## B. In flight at the hand-over (started in the old session; they may still finish there)

Check each on GitHub first (`git ls-remote --heads origin`, open pull requests into `build/v1`, `git log origin/build/v1`).
A merged one is done. A pushed branch with no pull request continues from its branch (review, gate, pull request,
local CI, merge). Nothing pushed: start the item fresh from its registry entry.

| Item | What | State at the hand-over |
|---|---|---|
| B-544 | Documents: first-live-run gaps, third set, part 2 | **Merged as #408.** It carries the owner D-3 decision and added W.T7b (B-556), W.T16b (B-557), W.T9c (B-558) and plan 0006 I.T9c (B-559), now in the registry. |
| B-547 | W.T16 item-id rule in harness.change_set_check (engineering calc) | **Merged as #410.** B-555 (W.T17) can start. Notes: the counted lines sit at the estimate 30; the mutation step ran only in local CI without mutation, so the next periodic run covers it; if a delete item of the change-set preview ever gets a fixed id, the reserved ids must grow (spec 0007 4.5 step 6). |
| B-551 | E.T23 Preview.models and ctx.promote take a model key | Pushed, head 2361039, no pull request; 23 counted lines, test-first pass. Stopped: the types step fails on one existing test outside the file list (`tests/unit/test_ctx_basis.py` line 120). Needs a small documents amendment adding that file to plan 0001 T23, then the one-line edit in its registry note, gate, review, pull request. |
| B-552 then B-553 | Owner decision of 2026-11-17: the changed-line count is an estimate, not a limit | **B-552 is written and pushed** (branch docs/b552-gate-line-count-estimate, head 48420c1, gate without mutation pass, no pull request): gate spec (GC009 a notice, no size cap, links ADR-0035) and gate plan T40 (estimate 260; its files include the design/ copies, the AGENTS template with its five rendered AGENTS.md files, the template-version lines in the .gate/agents.yml files and .github/pull_request_template.md, because the gate refuses those next to a spec or plan, GC010). Next: review it (Opus), open its pull request, local CI, merge. Then **B-553** (T40): start from [b552-t40-documents-trial.patch](b552-t40-documents-trial.patch) (the documents part, 117 counted lines, agents drift pass) plus the code and test changes listed in [line-limit-sweep.md](line-limit-sweep.md) sections B and C; the base gate still judges it, so it must stay inside 260 or the plan estimate is raised first. Writer note: [b552-writer.md](b552-writer.md); body: [b552-pr-body.md](b552-pr-body.md). |
| B-554 | Plan 0002 T23 lists the collateral test of B-550 | **Merged as #409.** B-550 must merge origin/build/v1 before its local CI (its scope is judged against the plan in its base). |
| Hub | `claude/pensive-volta-gcx0y9`: process documents and ADR-0035 for the same decision | **Done and reviewed** (commit 83264cc; renumbered from 0028 to 0035 in 49f43e0, because the build copy holds 0028 to 0034). The hub index still lacks rows for 0028 to 0034 (an owner choice whether to copy them in). |
| B-550 | S.T23 open the original, visible launch | Pushed, head e65e608, no pull request; 77 counted lines (estimate 60, raised to 80 by B-554) and one collateral test, now in its file list. Merge origin/build/v1, apply [b550-collateral-test_csi_revisions.patch](b550-collateral-test_csi_revisions.patch), rerun the gate without mutation, review (Opus), pull request, local CI, merge. It no longer waits for B-553 (it fits 80). Body draft: [b550-pr-body.md](b550-pr-body.md). |
| Mutation run 4 | Periodic full mutation, base 575b912, head 4f1a7e6 | **Passed** (finished 09:04 UTC, every member pass). The next periodic run is due ten merges after 4f1a7e6, with base 4f1a7e6. |

Until B-553 merges, the old gate still fails a pull request above its estimate (GC009). Lane script
[build-lane-v35.workflow.js](build-lane-v35.workflow.js) has no budget stop; use it only after B-553 merges, and
[build-lane-v34.workflow.js](build-lane-v34.workflow.js) before that.

## C. Order of the next work (first live run)

1. Finish section B.
2. B-550 (S.T23), then B-138 (S.T19a, port wiring: the central task; Opus reviewer). In parallel: B-556 (W.T7b, the D-3 drift stop).
3. B-555 (W.T17, engineering) after B-547, then B-557 (W.T16b, engineering).
4. W.T8 (B-202) after B-551, B-138 and B-556; then W.T9a (B-526), W.T9b (B-527), B-558 (W.T9c) and B-559 (I.T9c).
5. Interface: I.T14 (B-188), I.T14c (B-528), I.T14b (B-353), then I.T15, T16, T16b, T18a, T18b.
6. W.T11, W.T12. Then the remaining tasks of the registry by `depends_on`; the frozen list (D-32) stays frozen until
   the first live run.
7. Owner guide `LOCAL-TESTING.md` corrections found by the walk-through (`walkthrough-confirmed.md`, C4, C6, C7/C30,
   C15, C26 and the rest listed in lead-findings): `--template blank@0.1.0`; lower-case hash; `[engine] engineer` is
   needed for `--answers`; the tool fingerprint was never compared with a live tools/list; the model is locked after an
   analysis; `name` instead of `engineer` in the basis file; the model path in input.json is absolute; stop then
   resume for a later change set; the run id is printed on stderr; an item id is a token of 1 to 57 characters; doctor
   works without harness.toml; file encoding (utf-8-sig); also fix the numbering of
   `packages/eng-harness/docs/local-testing.md` (two items 22 and two items 23).
8. Owner queue (BUILD-STATUS section 6.6 and lead-findings): the design choices recorded for B-536, B-541, B-543,
   B-545; spec 0006 Q22 to Q24; Q16; engine Q40, Q41, Q43; the unused `windows_launcher()` (drop it or give it an
   inspector argument, B-546 note); from B-544: harness.change_set_check stays at version 1 although its output references change; with steel_and_concrete each kind's design summary sees the other kind's frames as not_designed, so the turn's design status is never PASS on a model with both kinds (a calc change would filter frames per kind); a summary with no drift row passes D-3, so if the live host returns no drift rows story drift goes unchecked (keep on the local-test list); the extra model-state read at step 13; the canonical value stored in the answer; the Q14 interim D-2 route; exception items taken from every cycle.

## D. How the new lead works (rules the owner set; all still in force)

- Talk to the owner in Arabic; code, commits and documents in English. The lead writes no code: every change is
  written, reviewed, gated and integrated by subagents. **Delegate to smaller, cheaper models** for writing and routine
  review; keep the strongest model for the lead's own judgement and for reviewing sensitive work (first-live-run
  wiring, engineering calcs and checks, gate changes). Credits are limited: run few lanes at once (about four), one
  audit at a time, no dry runs.
- Permissions: push task branches; open pull requests into `build/v1`; squash-merge after an independent review and a
  local CI PASS on the current head. Push directly to `build/v1` only the state files (BUILD-STATUS.md, HANDOFF.md,
  LOCAL-TESTING.md, `docs/build/`, `ops/remaining-tasks.json`). Never push to `main`. Commit trailer: only
  `Assisted-by: anthropic/claude` (no model names, no other trailer).
- Local CI per pull request without mutation; a full mutation run every ten merges (periodic-mutation.sh). Batch
  mode: create `<lead>/BATCH_MODE` to let `ops/localci.py` test up to three waiting pull requests as one batch.
- Stop rule: when the owner says stop or needs his allowance, create `<lead>/locks/pause.lane` (lane script v3.4 and
  later: agents that start see it and return at once), let running integrators finish, save state, resume only on his
  word.
- Lessons in [lead-playbook.md](lead-playbook.md) section 8 (items 9 to 15): no second gate run under the integration
  lock; hold markers; the writer runs the test-first check before the first push; replace scripts by `mv`, never edit
  them in place while lanes run them; live local CI has CPU priority (`tools/ci-priority.sh`).

## E. Rebuild the machine layout

As section 7 item 2 of the checkpoint of 2026-11-14 below says: the paths in `docs/build/` are placeholders
(`<lead>`, `<build-v1>`, `<worktrees>`, `<hub>`, `<lane-scripts>`, `<session-transcript>`). Clone the repository,
make a reference checkout of `build/v1`, copy `lead-playbook.md` to `<lead>/PLAYBOOK.md`, `priority.txt` to
`<lead>/PRIORITY.txt`, `lead-findings.md` to `<lead>/reports/lead-findings.md`, `resume/` to `<lead>/resume/`,
`tools/` to `<lead>/tools/`, the lane scripts to `<lane-scripts>/`; replace the placeholders with real paths
(`sed -i 's#<lead>#/real/path#g'`); create `<lead>/locks`, `<lead>/pr`, `<lead>/logs`, `<lead>/integ`; run
`uv sync --all-packages --locked` once per worktree. Local CI needs Linux. The workflow run ids in RESUME.md belong to
the old session and cannot be resumed elsewhere: restart from the state on GitHub.

# Build handoff checkpoint of 2026-11-16 (build/v1 at 4c4be4d, work item B-506)

**State.** 209 of 340 plan tasks merged. The 340 is the number of `- id:` entries in the front matter of the plan files
under `packages/*/docs/plans/` as the lead measured it; the 209 is the lead's count after pull request 378. Since then
only documents amendments merged (#379, #380), so the count stands. 24 task pull requests merged since the checkpoint
of 2026-11-14 (185 of 309): B-350 #332, B-460 #333, B-132 #334, B-148 #338, B-133 #339, B-114 #341, B-196 #344,
B-181 #350, B-149 #353, B-135 #345, B-115 #357, B-171 #361, B-199 #362, B-500 #365, B-197 #366, B-172 #367, B-183 #368,
B-429 #370, B-522 #369, B-173 #373, B-489 #374, B-116 #375, B-523 #376, B-518 #378. Documents amendments merged in
the same period: B-478, B-462, B-492, B-493, B-495, B-497, B-494, B-498, B-499, B-504, B-505, B-509, B-503, B-512,
B-513, B-510, B-517, B-511, B-529, B-531, B-533, B-535.

**Registry.** `ops/remaining-tasks.json` now has B-518 to B-528 and B-534 and the changes of amendments B-510, B-511,
B-513 and B-533. Merged dependencies are removed from `pending_deps`. Entries of merged items stay in the file.

**Lanes not marked finished in [resume/RESUME.md](resume/RESUME.md)** (check each against `git log origin/build/v1`
before relaunching): interface-4 (B-184 left), gaps-1 (B-519, B-520), engine-5 (B-117, B-118, B-521), interface-6,
editcycle-8 (B-200, its hold removed after B-535), decisions-2 (B-174), editcycle-9 (B-204, B-534), providers-1 (B-229).
Waiting to launch: B-198 after B-519; B-138 after B-530's task T19c, B-118, B-519 and the audit; B-188 after B-117, B-518
and B-184.

**Owner decisions that are open:** spec 0007 Q19; the protected gate change W.T15 (B-524); spec 0006 Q22, Q23, Q24;
the interim readings of spec 0007 section 4.9; engine Q40, Q41 and Q43. Details: BUILD-STATUS section 6.6.
The lead's batch-merge proposal (one local CI run for up to three ready pull requests) is also open: BUILD-STATUS
section 6.6, row OD-3.

**Where the lead's tooling is.** Copies are in this folder (`docs/build/`): lead-playbook.md, priority.txt,
lead-findings.md, `resume/` (RESUME.md and the lane arguments), the lane scripts build-lane.workflow.js,
build-lane-v2.workflow.js, build-lane-v3.workflow.js, build-lane-v31.workflow.js, build-lane-tail.workflow.js and
plan-audit.workflow.js, `tools/integrate.sh` and `tools/periodic-mutation.sh`, and the confirmed findings of plan
audit 2 (plan-audit-2-servers-0002-confirmed.md, plan-audit-2-providers-0009-confirmed.md). The originals live in the
session's own lead folder and do not survive the container. Paths in the copies are placeholders (section 7, item 2
below).

The checkpoint of 2026-11-14 follows and stays for its history.

# Build handoff checkpoint (cloud session of 2026-11-14, after the pause)

> **Newer state (2026-11-14, work item B-506):** the lead stopped all lanes at the owner's word on 2026-11-14 about 21:00 UTC. The state at that stop (lanes, run ids, queue, order of the next start, 193 of 331 plan tasks merged) is in [resume/RESUME.md](resume/RESUME.md); the speed-up measures the owner approved are in [lead-playbook.md](lead-playbook.md) section 7. The sections below describe the checkpoint of work item B-487.

Committed directly to `build/v1` under lead decision D-4 (build state files). Work item B-487, written by the lead
bookkeeper of the session for the next lead agent. This section is the newest; the checkpoint of 2026-11-12 below it
and the one below that stay for the history they record. Read this section, then the lead playbook
([lead-playbook.md](lead-playbook.md), in full), [resume/RESUME.md](resume/RESUME.md), the lead findings
([lead-findings.md](lead-findings.md)), the root [HANDOFF.md](../../HANDOFF.md) (process),
[BUILD-STATUS.md](../../BUILD-STATUS.md) (sections 3 to 6) and `git log origin/build/v1 -25`. Integration branch:
`build/v1` (never push to `main`). The paths in `docs/build/` are placeholders (section 7, item 2).

The session is the "Cloud session of 2026-11-12 (second cloud session)", resumed after the owner's pause. The lead is a
Claude session that writes no code: every change is written, reviewed, gated and integrated by Claude subagents in
workflow lanes (D-33). Timeline: the owner needed his usage allowance and every lane was stopped at once on
2026-11-12 at 20:38 UTC; the machine restarted during the pause (state intact); the owner said to continue on 2026-11-14
at 05:50 UTC and every running lane was resumed with its run id and identical arguments (D-36).

## 1. Where the build stands

- **Plan tasks merged: 185 of 309 (59.9 %).** Counted by the method of the checkpoint below: the total is the number of
  tasks in the `tasks:` front matter of the 20 plan files under `packages/*/docs/plans`,
  `packages/structural-codes/*/docs/plans` and `tools/*/docs/plans` on `origin/build/v1` (309 at beccdb9, recounted from
  the files); the merged count is the previous checkpoint's 177 plus the eight plan-task work items merged since
  b559295 (B-228 P.T9, B-131 S.T12, B-456 E.T13c, B-464 CT.T19, B-472 E.T20, B-470 C.T8c, B-113 E.T14, B-466 S.T12b).
  124 plan tasks are unmerged. The total grew from 301 to 309 by plan amendments (engine T20; calcs T8c; servers T19
  into T19a and T19b; providers T10 into T10a and T10b; interface T13b and T18 into T18a and T18b; footing T3b;
  templates T11), which is why the percentage moved little (58.8 % to 59.9 %). The lead's own count is the same.
  Compare progress by this method only. SBC overlay plan 0003 T4 is counted as unmerged, as before.
- Documents amendments and lead fixes are not plan tasks. Merged since the last checkpoint: B-467, B-468, B-469,
  B-471, B-474, B-475, B-476, B-480, B-481, B-482, B-483, B-484 (twelve; with the eight plan tasks that is the 20 pull
  requests of section 2).
- Phases: 0 done; 1 and 2 in progress; 3 and 4 not started beyond the column kinds, requests and checks.
- **Priority:** the first live run comes first (D-32); scenario C is applied (D-39), so servers T16, T17, T19b, SAFE
  plan 0008 T1 to T3 and providers T4, T6, T7, T10b are off the path. `priority.txt` lists the path in order.
- **Pace:** the usage allowance bounds it (D-35, D-36). Five lanes run; one deferred lane is stopped (section 4).

## 2. Merged since the last checkpoint (20 pull requests: #309, #311 to #322, #324 to #330)

| Work item | Task | Pull request |
|---|---|---|
| B-228 | P.T9 evaluation store, release verification, evaluate command | #309 |
| B-468 | DOC: contract plan T19 owns the harness calc lock | #311 |
| B-467 | DOC: basis field names carry the unit suffixes | #312 |
| B-471 | DOC: caller-chosen run id, decisions settings, registry on the edit cycle, the T18 split | #313 |
| B-131 | S.T12 CSI edit kinds and the tool port | #314 |
| B-474 | DOC: templates and basis plan T10 wires Ctx.basis | #315 |
| B-456 | E.T13c invariant 10 and the resume order | #316 |
| B-480 | DOC: contract plan T19 also owns the footing subjects verification record | #317 |
| B-469 | DOC: difference report key carries its list; calcs T8c | #318 |
| B-472 | E.T20 Engine.start takes a caller-chosen run id | #319 |
| B-464 | CT.T19 basis paths accept the contract unit suffixes | #320 |
| B-475 | DOC: scenario C, servers T19 and providers T10 split | #321 |
| B-481 | DOC: engine plan T14 budget | #322 |
| B-470 | C.T8c difference keys carry their list | #324 |
| B-482 | DOC: templates and basis plan T10 tests-first list | #325 |
| B-113 | E.T14 ctx.decide and ctx.decide_many | #326 |
| B-466 | S.T12b CSI read-back helpers and check_model | #327 |
| B-476 | DOC: ADR-0034, the task log by default (status Proposed) | #328 |
| B-483 | DOC: effect keys are the reported difference keys | #329 |
| B-484 | DOC: the remaining basis paths carry their unit suffix | #330 |

Direct commit under D-4 after b559295: d881c1c (a correction to the previous checkpoint's count text).

## 3. Decisions of this period (recorded in BUILD-STATUS sections 4 and 6)

- Owner: stop on 2026-11-12 at 20:38 UTC, continue on 2026-11-14 at 05:50 UTC; the decisions of 2026-11-12 recorded in
  the checkpoint below (full cycle, direct pushes of build state files only, OQ-Q44 answer (a), the first live run
  first, the task log by default) stand.
- Lead: D-36 (stop and resume of all lanes at once), D-37 (B-164: no gate exemption, rebuilt after E.T19), D-38 (B-460:
  the B-470 precedent for the mutation step), D-39 (scenario C applied as a draft), D-40 (the basis path rename is
  complete, the hold of playbook 5d is lifted).
- Owner queue (all items with recommendations are in BUILD-STATUS section 6): ADR-0034 acceptance with its six
  questions (OQ-A14); the scenario C spec changes (OQ-Q62); OQ-Q85 to OQ-Q91 are new, and OQ-Q65 to OQ-Q68, OQ-Q75 were
  updated. The full queue of lead findings is [lead-findings.md](lead-findings.md).

## 4. What is running, by lane (state at beccdb9; run ids are for `resumeFromRunId`)

| Lane | Run id | State |
|---|---|---|
| engine-2 (critical path) | wf_2aa69ef3-6fb | B-481 and B-113 (E.T14) merged; next B-350 (E.T14b; a local branch with three commits exists), then B-114 (E.T15), B-115 (E.T16), B-116 (E.T17), B-117 (E.T18), B-118 (E.T19) |
| servers-2 | wf_291c36a0-69b | B-465, B-131 (S.T12), B-466 (S.T12b) merged; next B-132 (S.T13; local branch with commits), B-133 (S.T14), then B-135 (S.T16) and B-136 (S.T17), which are off the path |
| tasklog-docs | wf_db726637-cfb | B-476 (ADR-0034, Proposed) merged; B-477 (AGENTS template and root rules), B-478 (spec and plan 0015), B-479 (gate spec and plan amendment) in work; the writer note of B-477 reports NEEDS_PLAN_AMENDMENT (no `Plan-Task: none (<reason>)` of gate spec 4.5 step 3 fits its 13 files, the gap of OQ-Q59); what the lane did with it is unknown at this checkpoint |
| amendments-zt5-gt2 | wf_86423180-ee8 | B-334 (Z.T5) at integration (`integrate.owner.b334` was held), then B-462 (docs), B-281 (G.T2), B-282 (G.T3), B-283 (G.T4) |
| calcs-3 | wf_66240cfa-1a7 | B-483 merged; B-460 (C.T8b) in its third round (D-38), then B-148 (C.T9), B-149 (C.T10). Its arguments are not among the saved argument files (the saved calcs-2.args.json belongs to the earlier run wf_063e17d6-666 of this lane); whether a copy exists elsewhere is unknown |
| footing-column-calcs (deferred) | wf_89fc0eda-b17 | stopped on 2026-11-12, not resumed (allowance): B-395 (footing T4) needs a plan amendment (OQ-Q61), B-396 (footing T5) written with the full gate pending, B-397 not started; both branches use basis names from before B-484 and are renamed by their writers |

Lanes of the earlier run that are not in the list above: scenario-c (wf_6488545e-6ea) ended with B-475 merged; basis
(wf_153cc0a2-b0f) ended with B-474 merged and B-164 stopped at its local CI FAIL (D-37); its run state beyond that is
not recorded here.

**Risk of losing work:** these task branches have commits that `git ls-remote --heads origin` did not show on GitHub at
the time of writing: B-132, B-350, B-395, B-396, B-460, B-477, B-478 (the worktree also had two uncommitted files),
and the v2 branch of B-281 (the old branch of B-281 is on GitHub and abandoned, D-22). The container is temporary:
push each task branch with `git push -u origin <branch>` (task branches only; the owner approved this) and check
`git branch -r`. The writer and reviewer notes lived in `<lead>/reports/`; for merged items they are in the pull request
bodies, and the findings that need a later decision are in [lead-findings.md](lead-findings.md) and BUILD-STATUS
section 6. Lock files at the time of writing: `integrate.owner.b334` and `prio-wait.b132`, `prio-wait.b350`,
`prio-wait.b460` (live lanes; remove any that is older than the restart of the machine or than three hours with no
process behind it).

## 5. What waits, and for what

- B-164 (B.T10, #323 open with a local CI FAIL on TF004): rebuilt on a fresh branch after E.T19 (B-118) merges, by
  the recipe in [lead-findings.md](lead-findings.md); then #323 is closed or replaced (D-37).
- Decisions D.T7 to D.T10 (B-171 to B-174): wait for E.T14b (B-350) and E.T17 (B-116).
- Interface I.T7 (B-181) and what follows it: wait for E.T15 (B-114).
- Edit cycle W.T2 (B-196): C.T8b (B-460); W.T5 (B-199): S.T13, S.T14; W.T6 (B-200): E.T15, E.T16.
- S.T19a (B-138): E.T15, E.T16, E.T19 (and W.T5, since both edit `tests/fakes/sasaah_csi/**`).
- P.T10a (B-229): its plan dependency is P.T1 only (merged); the cross-plan prose of plan 0009 also names decisions T10
  and engine T14b, so check before launching.
- I.T18a (B-433), then I.T18b (B-488), and the report status section I.T13b (B-489): see the registry.
- Owner: ADR-0034 and the scenario C spec changes (section 3).

## 6. Remaining order

1. **First-live-run path (D-32, D-39)**, in the order of [priority.txt](priority.txt) (it is also the order in which
   work items take the gate and integration locks). Unmerged on it: engine B-350, B-114 to B-118; servers B-132, B-133,
   B-138 (S.T19a); calcs B-460, B-148, B-149; basis B-164 (after B-118); decisions B-171 to B-174; interface B-181,
   B-183, B-184, B-188 to B-190, B-353, B-429 to B-431, B-433 (I.T18a), and then B-488 (I.T18b) and B-489 (I.T13b);
   edit cycle B-196 to B-203; providers B-229 (P.T10a). B-488 and B-489 are new and not yet in `priority.txt`: add them
   after B-433. The list also names merged items, which is harmless.
2. **Task log:** B-477 to B-479 in work, then the plan 0015 tasks; lower priority than the path.
3. **Deferred set** (after the first run, or when the logs show the need): G.T2 to T15, R.T1 to T15, A.T1 to T7, H.T1 to
   T9, F.T4 to T9, X.T4 to T13, Y.T2, Y.T3, Z.T5, C.T11, C.T12, W.T10 to T12, I.T17, I.T17c, S.T15 (next after the first
   run), plan 0015 T12 and T13, gate T40 to T42; off the path by scenario C: S.T16, S.T17, S.T19b (B-490), F.T1 to F.T3,
   P.T4, P.T6, P.T7, P.T10b (B-491); new from the basis rename: X.T3b (B-485), B.T11 (B-486).
4. Phase 3 and 4 plans: SAFE (0008), Revit (0011), SAP2000 (0012), IDEA (0014).

`ops/remaining-tasks.json` is updated by this checkpoint: B-433 now names I.T18a; B-138 names S.T19a; B-229 names
P.T10a; new entries B-485, B-486, B-488 (I.T18b), B-489 (I.T13b), B-490 (S.T19b) and B-491 (P.T10b); the dependencies
that named a split task follow the plan front matters. Entries of merged work items stay in the file.

## 7. How the next lead resumes

1. **Read** this section, the playbook (sections 1, 5, 5b, 5c and 5d first), [resume/RESUME.md](resume/RESUME.md),
   BUILD-STATUS sections 3 to 6, then `git fetch origin build/v1 && git log origin/build/v1 -25`. Check
   `git ls-remote --heads origin` and the open pull requests (`mcp__github__list_pull_requests`).
2. **Rebuild the machine layout** (the container is temporary). The paths in `docs/build/` are placeholders: `<lead>/`
   is the lead scratch folder with `reports/`, `pr/`, `logs/`, `locks/`, `resume/`; `<build-v1>` is a read-only
   reference checkout of `build/v1`; `<worktrees>/b<NNN>` is one worktree per work item; `<hub>` is the hub checkout;
   `<lane-scripts>` is the folder of workflow scripts. Copy lead-playbook.md to `<lead>/PLAYBOOK.md`, priority.txt to
   `<lead>/PRIORITY.txt`, lead-findings.md to `<lead>/reports/lead-findings.md`, task-log-brief-v2.md to
   `<lead>/reports/task-log-brief-v2.md`, b484-basis-path-inventory.md to `<lead>/reports/b484-writer.md` and resume/
   to `<lead>/resume/`; then replace the placeholders with the real paths in your copies (for example
   `sed -i 's#<lead>#/real/lead#g'`) and run `uv sync --all-packages --locked` in each worktree once.
3. **The lane workflow script** is [build-lane.workflow.js](build-lane.workflow.js) (the session's workflow tool; its
   arguments and its steps are described in item 3 of section 6 of the checkpoint below). One call runs one lane.
4. **The saved lane arguments** are in `resume/<lane>.args.json` (see [resume/RESUME.md](resume/RESUME.md); the
   placeholders in them are replaced the same way). Resume a lane with its run id from section 4 as `resumeFromRunId`
   and the identical arguments: finished agents replay from the cache and the agent that was cut off runs again. The
   files are the arguments as of 2026-11-12 and 2026-11-14 05:50 UTC; a lane started later (calcs-3) has none saved.
   A lane whose run id is lost starts fresh from the state on GitHub (an open pull request with a local CI PASS goes
   to the merge step, a pushed branch resumes in open-pull-request mode).
5. **The locks** (all under `<lead>/locks/`): `gate.lock`, `integrate.lock`, `prio-wait.b<NNN>`; rules as in item 4 of
   section 6 of the checkpoint below and in playbook sections 4, 5 and 5b. After a machine restart: remove any
   `integrate.owner.*` and `prio-wait.*` file older than the restart (`uptime -s`), start a new local CI run for a run
   directory whose `status.txt` is not final (playbook 5d).
6. **The priority list** is [priority.txt](priority.txt): update it when the owner accepts scenario C and as work items
   merge.
7. **Stop and resume procedure** (D-36): when the owner says stop, stop every lane workflow task at once, kill leftover
   `flock` holders of `integrate.lock` (`pgrep -af "flock <lead>/locks/integrate.lock"`), remove `integrate.owner.*`
   and `prio-wait.*` files, and save each lane's arguments and run id under `<lead>/resume/` (write them in
   RESUME.md). When he says continue: check `ls <lead>/locks`, the open pull requests and the local CI run
   directories, then resume every lane with its run id and identical arguments, the deferred lanes only when allowance
   is spare.
8. **Do not** let a writer start a task that reads the basis fields from a branch written before B-484 without
   renaming them (playbook 5d); keep commit trailers to `Assisted-by: anthropic/claude` (5c); write no model version
   identifiers (D-3); never edit the state files from a task branch (D-4); never push to `main`.
9. **Lead items that are not owner questions:** `tests/unit/test_bearing.py` line 132 of the aci318-14 pack uses the
   old basis name `foundation.allowable_bearing_pressure`: fold the rename into the next aci318-14 task that touches the
   file (a test-only task cannot pass test-first); the B-164 rebuild recipe and the other findings are in
   [lead-findings.md](lead-findings.md); the engine spec amendment that collects the engine findings (P-65) is not
   written yet.

---

# Earlier checkpoint (cloud session 2, 2026-11-12, at b559295)

(Superseded as the newest checkpoint by the section above; the text below is unchanged.)

Committed directly to `build/v1` under lead decision D-4 (build state files). Written by the lead of the second cloud
session for the next lead agent. This section is the newest; the older checkpoint (sections E1 to E8, from e99bf72) stays
below for the history it records. Read this section, then [docs/build/lead-playbook.md](lead-playbook.md) in full, the
root [HANDOFF.md](../../HANDOFF.md) (process), [BUILD-STATUS.md](../../BUILD-STATUS.md) (sections 3 to 6) and
`git log origin/build/v1 -20`. Integration branch: `build/v1` (never push to `main`).

The session is "Cloud session of 2026-11-12 (second cloud session)", resumed from the checkpoint at e99bf72. The lead is
a Claude session that writes no code: every change is written, reviewed, gated and integrated by Claude subagents in
workflow lanes (D-33).

## 1. Where the build stands

- **Plan tasks merged: 177 of 301 (58.8 %).** How it was counted: the total is the number of tasks in the `tasks:` front
  matter of every plan file under `docs/plans/` on `origin/build/v1` (20 plans in `packages/` and `tools/`, at ef5d883); the
  unmerged tasks are the entries of `ops/remaining-tasks.json` of the pause whose work item is not named in the
  first-parent log of `origin/build/v1` (117), plus the six plan tasks that registry did not list (E.T13c, C.T8b,
  eng-contract T19, S.T12b, S.T15, F.T9), plus SBC overlay plan 0003 T4, which is unmerged too: that plan drops T4 only if
  ACI column plan 0004 T5 (Z.T5, B-334) merges before SBC T2 (Y.T2, B-326), and neither has merged, so T4 stays to build
  unless Z.T5 merges first. 301 - 117 - 7 = 177. Documents amendments and lead fixes are not plan tasks and are counted
  separately.
- The same count at the previous checkpoint (e99bf72) gives 173 of 298; that checkpoint reported 171 of 294 on a count
  that cannot be reproduced, so compare progress by this method only. This session merged four plan tasks (B-451 S.T11b,
  B-222 P.T3, B-147 C.T8, B-455 E.T13b) and five documents amendments (B-458, B-459, B-461, B-463, B-465), and added three plan tasks by splits (calcs
  T8b, eng-contract T19, servers T12b). Pull request #309 (B-228, P.T9) is open with a local CI PASS; it makes 178 when it merges.
- Phases: 0 done; 1 and 2 in progress; 3 and 4 not started beyond the column kinds, requests and checks.
- **Priority:** the first live run comes first (D-32, owner decision of 2026-11-12, supersedes D-27): the owner runs the
  model edit cycle on a copy of a real ETABS model through sasaah-csi-mcp (`eng-harness run model_edit_cycle --run-class
  trial`, the first cycle only). The path and the deferred set are in section 6 of [task-log-brief.md](task-log-brief.md).
- **Pace:** the session's model usage limit bounds it, not local CI (D-35). About ten lanes at once used a five-hour
  allowance in about three hours and every lane stopped at once at about 14:30 UTC; the lanes restarted at 17:25 UTC
  from their journals, and from then only lanes on the first-live-run path run.

## 2. Merged in this session (nine pull requests, #301 to #308 and #310)

| Work item | Task | Pull request |
|---|---|---|
| B-458 | DOC: calcs plan T8 split into T8 and T8b | #301 |
| B-459 | DOC: column plan T2 budget 200 to 345 | #302 |
| B-451 | S.T11b CSI model-state reader, fingerprint, units read | #303 |
| B-222 | P.T3 shared HTTP client, error mapping, outgoing guard | #304 |
| B-147 | C.T8 comparison core (rebuilt on a fresh branch after the split) | #305 |
| B-461 | DOC: ACI column plan T5 owns the two check-count tests | #306 |
| B-463 | DOC: basis paths accept the contract unit suffixes (OQ-Q44 answer a) | #307 |
| B-455 | E.T13b invariant 9 and the first-use binding | #308 |
| B-465 | DOC: servers plan T12 split into T12 and T12b | #310 |

## 3. Owner decisions of this session (recorded in BUILD-STATUS sections 4 and 6)

- The full cycle (task branches pushed, pull requests squash-merged into `build/v1` after an independent review and a
  local CI PASS, never `main`) and direct pushes of the build state files only (BUILD-STATUS.md, HANDOFF.md,
  LOCAL-TESTING.md, `docs/build/`, `ops/remaining-tasks.json`).
- OQ-Q44 answered (a): basis paths accept the contract unit suffixes in the last segment (B-463 merged; code B-464).
- The written recommendations of the open software questions that block the first live run are applied: spec 0007 Q12
  (b) to (d) (B-467), spec 0006 Q20 answer A, a caller-chosen run id (OQ-Q45; B-471 documents, B-472 code), spec 0006
  Q15 and Q16 (B-471).
- First live run first (D-32); the owner also asked the lead to study the shorter path, scenario C, which is done
  ([scenario-c.md](scenario-c.md); the owner decides, OQ-Q62).
- The task log by default (ADR-0034, **not yet written**; owner queue OQ-A14): see [task-log-brief.md](task-log-brief.md).
  The brief predates the owner's later decisions that the log is a folder in the code branch itself (the brief says a
  separate `tasklog` branch), that log-only commits are pushed directly and, on the owner's machine, with the owner's git
  login; write the ADR and spec 0015 from the brief amended for those decisions. No code of the log is on the path.

## 4. What is running, by lane (state when this checkpoint was written)

| Lane | Work items | State |
|---|---|---|
| Engine | B-456 (E.T13c); then B-113, B-350, B-114 to B-118 (E.T14 to E.T19) | B-456 in writing (restarted); the rest queued |
| Servers | B-131 (S.T12); then B-466 (S.T12b, new), B-132, B-133, B-135, B-136 | B-465 merged (#310); B-131 first half written, resumes on the amended T12; B-466 waits for B-131, B-464 and B-467 |
| Providers and misc | B-228 (P.T9, #309); B-164 (B.T10) | #309 open with a local CI PASS, the integrator was cut off before the merge and was restarted (check `git log`); B-164 in writing; B-223, B-225, B-226 (P.T4, P.T6, P.T7) wait for the scenario C result |
| Calcs | B-460 (C.T8b); then B-148, B-149 (C.T9, C.T10); C.T11 and C.T12 deferred | B-460 written, review BLOCKED until B-464, B-467, B-469 and B-470 merge; second round queued |
| Contract and basis | B-468 (DOC, T19 files, risk set), then B-464 (T19 code) | B-468 in review (restarted; round 2 recorded APPROVE); B-464 written, waits for B-468 |
| Documents | B-467 (basis field rename), B-471 (run id, decisions settings, registry on W.T9, I.T18 split) | both in writing (restarted); B-469 (calcs spec 4.7, new T8c) queued, then code B-470 (C.T8c) and B-472 (engine run id) |
| Paused, deferred set (D-35) | B-334 (Z.T5: written, reviewed, verified, full gate then integration pending); B-395 (X.T4: written, stopped with a proposed amendment, OQ-Q61); B-396 (X.T5: written, reviewed, verified, full gate pending, OQ-Q60); B-397 (X.T6); B-462 (DOC) then B-281, B-282, B-283 (G.T2 to G.T4; G.T2 rebuilt on a v2 branch, waits for B-462) | wait for spare allowance |

**Risk of losing work:** at the time of writing these task branches exist only in the container, not on GitHub
(worktrees under `<worktrees>/`): feat/b131 (and four uncommitted files), b281 (v2), b334, b395, b396, b456, b460, b464,
and docs/b467, b468, b471. Push each task branch with `git push -u origin <branch>` (task branches only; the owner
approved this) before the container is recycled, and run `git branch -r` to see what is already there. The writer and
reviewer notes of this session lived in `<lead>/reports/` (b<NNN>-writer.md, b<NNN>-review.md) and go with the
container: for merged items they are in the pull request bodies (Review section); for unmerged items the findings that
need a later decision are recorded in BUILD-STATUS section 6 (OQ-Q60 to OQ-Q84).

## 5. Remaining order

1. **First-live-run path (D-32)**, in the order of [priority.txt](priority.txt) (it is also the order in which work
   items take the gate and integration locks). Before any code: the documents and lead items of section 6.1 of the
   brief: B-463 (done), B-468 then B-464 (basis path rule), B-467 (basis field names), B-471 (run id, decisions settings,
   registry on W.T9, I.T18 split) with B-472, B-469 with B-470 (difference keys), the registry fixes (done in this
   checkpoint). Then the code waves of section 6.2: W1 B-455 (done), B-147 (done), S.T12 B-131, B.T10 B-164, P.T9 B-228;
   W2 E.T13c B-456, C.T8b B-460, S.T13 B-132, P.T4 B-223, W.T2 B-196; W3 C.T9 B-148, E.T14 B-113, S.T14 B-133, P.T6
   B-225; W4 C.T10 B-149, E.T14b B-350, F.T1 B-210, P.T7 B-226, S.T16 B-135, W.T3 B-197, W.T5 B-199; and on to W13
   (I.T18a and I.T18b, W.T9), plus I.T17b. Scenario C (OQ-Q62) removes S.T16, S.T17, F.T1 to F.T3 and P.T4, P.T6, P.T7,
   P.T9 from this path (50 tasks to 41) once the owner accepts it. S.T12b (B-466, in plan 0002 since #310) joins before S.T13 (B-132).
2. **Task log:** ADR-0034 (documents), spec and plan 0015 as a parallel lane of lower priority than the path.
3. **Deferred set** (after the first run, or when the logs show the need): G.T2 to T15, R.T1 to T15, A.T1 to T7, H.T1 to
   T9, F.T4 to T9, X.T4 to T13, Y.T2, Y.T3, Z.T5, C.T11, C.T12, W.T10 to T12, I.T17, I.T17c, S.T15 (next after the first
   run), plan 0015 T12 and T13, gate T40 to T42, and under scenario C S.T16, S.T17, F.T1 to F.T3 and possibly P.T4,
   P.T6, P.T7, P.T9.
4. Phase 3 and 4 plans: SAFE (0008), Revit (0011), SAP2000 (0012), IDEA (0014).

`ops/remaining-tasks.json` lists the registered tasks with their pending dependencies; this checkpoint added B-456,
B-460, B-464, B-466, B-470 and B-472 and moved C.T9 (B-148), W.T2 (B-196) to C.T8b and S.T13 (B-132) to S.T12b. Entries
for plan tasks that a pending amendment creates (C.T8c: B-469; the engine run id: B-471) say so in their `lead_notes`.

## 6. How the next lead resumes

1. **Read** this section, the lead playbook ([lead-playbook.md](lead-playbook.md); it is the instruction every lane
   agent gets, so read all of it, especially sections 1, 5, 5b, 5c and 5d), BUILD-STATUS sections 3 to 6, then
   `git fetch origin build/v1 && git log origin/build/v1 -20`. Check `git ls-remote --heads origin` and the open
   pull requests (`mcp__github__list_pull_requests`) for what the lanes left.
2. **Rebuild the machine layout** (the container is temporary). The paths in `docs/build/` are placeholders: `<lead>/`
   is the lead scratch folder with `reports/`, `pr/`, `logs/`, `locks/` (copy lead-playbook.md to `<lead>/PLAYBOOK.md`
   and priority.txt to `<lead>/PRIORITY.txt`); `<build-v1>` is a read-only reference checkout of `build/v1`;
   `<worktrees>/b<NNN>` is one worktree per work item. Replace the placeholders with the real paths in your copy.
   Run `uv sync --all-packages --locked` in each worktree once.
3. **The lane workflow script** is [build-lane.workflow.js](build-lane.workflow.js), for the session's workflow tool.
   One call runs one lane: `args.lane` (a name) and `args.tasks`, an ordered list of objects with `id` (B-NNN), `key`
   (plan key such as `E.T13c`), `num`, `plan` and `planTask`, `member` (the gate's `--package`), `kind` (`impl` or
   `docs`), `title`, `branch`, `prTitle`, `risk`, `notes` (lead notes), `needs` (work items of the same lane that must
   merge first), `writerModel` and `writerEffort`. Per task it runs: writer (tests first), reviewer with up to two fix
   rounds, two verifiers for engineering content, the full gate under `gate.lock`, the integrator under
   `integrate.lock`. A task whose writer returns `NEEDS_PLAN_AMENDMENT` stops with the proposed amendment: write it as
   a documents work item (D-12, D-34), then resume. Resume a lane from the state on GitHub: an open pull request with a
   local CI PASS goes straight to the merge step (playbook section 5), a pushed branch resumes in open-pull-request mode.
4. **The locks** (all under `<lead>/locks/`): `gate.lock` (one full gate with mutation at a time), `integrate.lock` (one
   integration at a time; the holder gives the lock up after four hours; an `integrate.owner.b<NNN>` file with no
   `flock` process behind it is stale: remove it), and `prio-wait.b<NNN>` files (a work item that is in
   priority.txt creates one before it queues for a lock; items not in the list wait while any exists; one older than
   three hours is stale). At the checkpoint `prio-wait.b228` and `prio-wait.b468` were set and `integrate.owner.b465` was left by
   B-465's integrator (merged as #310): remove it if no `flock` process holds it.
5. **The priority list** is [priority.txt](priority.txt): the work items on the first-live-run path, in order. Update it
   when the owner answers OQ-Q62 (scenario C) and when B-471, B-469 and the new work items merge.
6. **Do not** let a writer start a task that reads the renamed basis fields before B-464 and B-467 are on
   `origin/build/v1` (playbook section 5d); keep commit trailers to `Assisted-by: anthropic/claude` (section 5c); write
   no model version identifiers (D-3); never edit the state files from a task branch (D-4).
7. **Owner queue** (BUILD-STATUS section 6): OQ-Q60 (footing L1, an engineering choice) and OQ-Q62 (scenario C) are the
   two that change what is built next; OQ-A14 (ADR-0034) and the task-log questions OQ-Q80 to OQ-Q82 are next after
   them.
8. Open items of the last hour: B-228's merge (#309), B-468's review, the three documents work items in
   writing, the engine and servers lanes in writing. Re-read `git log origin/build/v1` before assuming any of them
   is still open.

---

# Earlier checkpoint (cloud session 1, wind-down of 2026-11-12, at e99bf72)

Committed directly to `build/v1` under lead decision D-4 (build state files): a pull request for this path cannot pass
gate-check, since no `Plan-Task: none (<reason>)` of gate spec 4.5 fits a document under `docs/build/` (#300 closed).

Checkpoint for the next lead agent of the v1 build, written when the owner asked to wind down on 2026-11-12. Read this
file, then the root [HANDOFF.md](../../HANDOFF.md) (process and resume prompt), [BUILD-STATUS.md](../../BUILD-STATUS.md)
(sections 4 to 6) and `git log origin/build/v1 -20`. Integration branch: `build/v1` (never push to `main`).

## E1. Where the build stood

- Plan tasks merged: 171 of 294 (58.2 %). Amendments B-447, B-450 and B-454
  split three tasks into seven, so the total grew from 290 to 294. Documents amendments and lead fixes are counted
  separately.
- This session (2026-11-11 and 2026-11-12) merged 33 pull requests, from #256 to #299; see section 2.
- Phases: 0 done; 1 and 2 in progress (engine invariants, servers and CSI adapter, calcs, providers, report, footing
  workflow, ACI column checks); 3 and 4 not started beyond the column kinds, requests and checks.

## E2. Merged in this session

| Work item | Task | Pull request |
|---|---|---|
| B-437 | DOC.CALCRULES calc-module rules | #260 |
| B-440 | DOC.PROVT1 license exceptions in providers T1 | #270 |
| B-439 | G.T39 FB005 form A4 (version keyword) | #271 |
| B-444 | lead fix: aci318-14 pack test under mutation | #272 |
| B-330 | Z.T1 shared column section model | #269 |
| B-445 | DOC: engine T12 owns four journal-pinning tests | #275 |
| B-393 | X.T2 code-pack route of the CalcPort | #268 |
| B-139 | S.T20 IDEA framework additions | #273 |
| B-129 | S.T10 harness-side model identity, CSI session operations | #276 |
| B-446 | license exceptions for cffi and regex (split out of #274) | #278 |
| B-447 | DOC: column plan T1 split into T1 and T1b | #280 |
| B-137 | S.T18 eng-harness doctor | #281 |
| B-220 | P.T1 providers dependencies, configuration, network guard | #274 |
| B-449 | lead fix: provider dependency test under mutation | #282 |
| B-111 | E.T12 invariants 1, 2, 3, 7 | #279 |
| B-186 | I.T12 report sections | #277 |
| B-450 | DOC: servers plan T11 split into T11 and T11b | #286 |
| B-333 | Z.T4 longitudinal reinforcement limits | #284 |
| B-452 | DOC: golden-loader cases leave tests_first (TF008) | #287 |
| B-146 | C.T7 calc 1, model fingerprint | #283 |
| B-453 | DOC: Revit, column and IDEA plans carry risk r2 (RF001) | #289 |
| B-331 | Z.T2 maximum axial strength | #288 |
| B-280 | G.T1 column workflow kinds (rebuilt from #285) | #290 |
| B-454 | DOC: engine plan T13 split into T13, T13b, T13c | #291 |
| B-221 | P.T2 credential store and key management | #292 |
| B-130 | S.T11 CSI reply mapping (after B-450) | #294 |
| B-187 | I.T13 report document | #295 |
| B-448 | G.T1b column request models | #297 |
| B-332 | Z.T3 axial flexure (oracle-verified twice) | #298 |
| B-227 | P.T8 evaluation core | #293 |
| B-394 | X.T3 footing subjects calc | #256 |
| B-224 | P.T5 strict LLM output type and prompt | #296 |
| B-112 | E.T13 invariants 5, 6, 8 at start (after B-454) | #299 |

## E3. Open pull requests at the checkpoint

| PR | Work item | State |
|---|---|---|
| #2 | the build/v1 draft pull request | leave open |

A pull request that conflicts in `packages/eng-harness/pyproject.toml` (the one-line `public_modules` list),
`CHANGELOG.md` or `.gate/ratchet.json` must merge `build/v1` into its branch (never rebase): keep both changelog
lines, the union of the `public_modules` entries, and for the ratchet the base's counts plus this change's own rise.
`lead/mergebase.sh <worktree>` does the first two mechanically.

## E4. In-progress branches (all pushed to GitHub)

| Work item | Task | Branch | Writer session | What is left |
|---|---|---|---|---|
| B-281 | G.T2 `harness.column_select` | `feat/b281-harness-gt2-calc-harness-column-select` | Cursor composer-2.5 chat `6c6af3bf-e21c-4c64-8acb-4d99153bc30c` | STOPPED: 313 counted lines against the plan's 200; needs a plan amendment (a budget within 400, or a split, D-12), then review (engineering calc: hand-check the golden `derivation`s, X/Y and the verticality tolerance) |
| B-147 | C.T8 `harness.model_diff` | `feat/b147-harness-ct8-calc-2-difference-report` | Cursor composer-2.5 (session id lost: its report step failed) | STOPPED: 532 counted lines against 380 (`model_diff.py` 436); needs a plan split (D-12), then review |
| B-451 | S.T11b | not started | — | ready (S.T11 merged in #294; calcs T7 merged); the earlier reader draft is on `wip/lead-stashes-2026-11-12` under `wip-stash/b130-t11b-stash/` |
| B-455, B-456 | E.T13b, E.T13c | not started | — | after E.T13 (#299); the earlier draft parts are on `wip/lead-stashes-2026-11-12` under `wip-stash/b112-t13bc-stash/`. B-112's writer notes: the inserted check and save steps do not wait for a pending host; a write reconciled `not_applied` again and again reruns without a cap (owner question) |

`wip/lead-stashes-2026-11-12` holds plain copies of earlier drafts kept for later tasks; it is not a pull request
branch. Work items B-448 to B-457 are registered in BUILD-STATUS section 3; B-451, B-455 and B-456 are not yet in
`ops/remaining-tasks.json` (the lead kept them in ``lead/extra-tasks.json``, which `brief.py`, `openpr.py` and
`write.sh` read).

## E5. Remaining order

1. No pull request of the session is left open (except the build/v1 draft #2).
2. B-455 (E.T13b) and B-456 (E.T13c); then engine E.T14 to E.T19.
3. Plan amendments for B-147 (C.T8) and B-281 (G.T2), then those tasks; C.T9 to C.T12 follow C.T8.
4. B-451 (S.T11b, ready), then servers S.T12 to S.T19 (S.T15 stays unregistered: owner and local tests).
5. Providers P.T3, P.T4, P.T6, P.T7, P.T9, P.T10; interface I.T7 onward; decisions D.T7 to D.T10; edit cycle W.T2 to
   W.T12; footing workflow X.T4 to X.T13; column workflow G.T3 onward; ACI column Z.T5 (pack registration, ready: Z.T2 to Z.T4 merged); SBC overlay Y.T2, Y.T3.
6. Phase 3 and 4 plans: SAFE (0008), Revit (0011), SAP2000 (0012), IDEA (0014).
`ops/remaining-tasks.json` lists every task with its pending dependencies.

## E6. Known problems

- **Local CI is slow.** A pull request that changes eng-harness source runs the mutation step on the changed modules;
  large modules (for example the column kinds) take 30 minutes or more. Run one local CI at a time (it holds a lock)
  and at most two full gate runs at once.
- **Mutation-score and mutation-copy failures.** The gate's mutation step runs the tests in a copy of the member alone:
  a test that reads a file outside the member (workspace `uv.lock`, clause specs, `spikes/`) must skip only when
  `MUTANT_UNDER_TEST` is set and the file is missing (B-369, B-444, B-449 pattern, with a ratchet count). A test that
  compares a calc's content hash with the registry fails under mutation by design: leave that comparison to
  `tests/contract/test_calc_lock.py`. New check modules often land below the 80 % score: add tests on the undecorated
  helpers. Code-pack check bodies under `@check` get no mutants at all (MU003; owner queue OQ-Q57).
- **Load-sensitive tests** (P-54): `tests/unit/progress/test_sink.py` (10 ms bound) and
  `tests/unit/pages/test_routes.py` (socket timeout) fail now and then under load; rerun.
- **git network hangs.** `git fetch` and `git push` sometimes stall ("git-remote-https died of signal 15"): run
  `git repack -d`, retry with `timeout 120`. A `gh pr create` that times out may still have created the pull request
  (check `gh pr list --head <branch>`).
- **Cursor runs drop their connection** ("Connection stalled"); the branch keeps what was committed. Restart in a fresh
  chat with a continuation note; after two failures on one task, use another writer.
- **Plan defects found and fixed** (check new plans for the same): tests_first files outside the task (B-452, TF008),
  plan risk below the path floor (B-453, RF001), tasks over 400 lines (B-447, B-450, B-454), a pull request cannot
  grant itself a gate policy change such as a license exception (B-446: the gate reads policy from the base commit).

## E7. The lead scripts (folder `lead/` in the build user's home directory, outside the repository)

They are the lead's scratch tooling on this machine; copy them if the next session runs elsewhere.

| Script | Use |
|---|---|
| `write.sh <B-NNN> <model> [resume-id] [message-file]` | Run one writer in the task's worktree `.claude/worktrees/b<NNN>` (created from `origin/build/v1` or the pushed branch). Without a resume id it writes the brief with `brief.py`; `CONT_NOTE=<file>` appends a continuation note. A Cursor chat id (UUID) resumes on Cursor composer-2.5; an OpenCode session id (`ses_...`) resumes on OpenCode. At the wind-down it refuses new tasks |
| `brief.py <B-NNN> <worktree>` | Print the self-contained brief from the plan front matter (files, budget, tests_first, lead notes, engineering rules) |
| `openpr.py <B-NNN or -> <worktree> <summary.md> [review.md]` | Push the branch with `LEAD_PUSH=1` and open the pull request into `build/v1` (Work-Item, Plan-Task, the plan's bare Risk set; a `<summary>.json` overrides title, work item, plan task and risk) |
| `prbody.py <pr> <Section> <file> [--append]` | Replace or append a `## Section` of a pull request body |
| `ci.sh <pr>` | Fetch the pull request JSON and start `ops/localci.py` |
| `merge.sh <pr> <run-dir>` | Check the PASS head, write the Local CI summary into the body, squash-merge as `<title> (#N)`, release the lock |
| `ciq.sh <pr>...` | Sequential local CI queue: start, wait, merge on PASS, log to `logs/ciq.log` |
| `gq.sh <B-NNN>...` | Sequential full gates (mutation included), log to `logs/gq.log` |
| `bstatus.py <json>` | Set the pull request and status cells of BUILD-STATUS task rows and add rows |
| `mergebase.sh <worktree>` | Merge the remote branch tip and `origin/build/v1` into a worktree branch, resolve CHANGELOG and `public_modules` conflicts, push (no force) |
| `extra-tasks.json` | Registry entries for work items created after `ops/remaining-tasks.json` (B-448, B-451, B-455, B-456) |

`.git/hooks/pre-push` in the main checkout refuses a push unless `LEAD_PUSH=1`, so writers cannot push. Wait on the
logs by line count, not by grepping a pull request number (an old FAIL line matches).

## E8. Writer rule for the future

New writer tasks use **OpenCode with `opencode/deepseek-v4.1-flash-free`** (owner, 2026-11-12). Cursor chats already in
progress may finish on composer-2.5. OpenCode is outside AGENTS.md section 9 like Cursor (owner queue OQ-Q49): the
lead still reviews every diff, runs the gate and local CI, and merges; writers never push or touch pull requests.
