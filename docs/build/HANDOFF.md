# Build handoff checkpoint (cloud session 2, 2026-11-12)

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
