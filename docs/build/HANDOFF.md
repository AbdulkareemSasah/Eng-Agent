# Build handoff checkpoint (cloud session, 2026-11-12)

Committed directly to `build/v1` under lead decision D-4 (build state files): a pull request for this path cannot pass
gate-check, since no `Plan-Task: none (<reason>)` of gate spec 4.5 fits a document under `docs/build/` (#300 closed).

Checkpoint for the next lead agent of the v1 build, written when the owner asked to wind down on 2026-11-12. Read this
file, then the root [HANDOFF.md](../../HANDOFF.md) (process and resume prompt), [BUILD-STATUS.md](../../BUILD-STATUS.md)
(sections 4 to 6) and `git log origin/build/v1 -20`. Integration branch: `build/v1` (never push to `main`).

## 1. Where the build stands

- Plan tasks merged: 171 of 294 (58.2 %). Amendments B-447, B-450 and B-454
  split three tasks into seven, so the total grew from 290 to 294. Documents amendments and lead fixes are counted
  separately.
- This session (2026-11-11 and 2026-11-12) merged 33 pull requests, from #256 to #299; see section 2.
- Phases: 0 done; 1 and 2 in progress (engine invariants, servers and CSI adapter, calcs, providers, report, footing
  workflow, ACI column checks); 3 and 4 not started beyond the column kinds, requests and checks.

## 2. Merged in this session

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

## 3. Open pull requests at the checkpoint

| PR | Work item | State |
|---|---|---|
| #2 | the build/v1 draft pull request | leave open |

A pull request that conflicts in `packages/eng-harness/pyproject.toml` (the one-line `public_modules` list),
`CHANGELOG.md` or `.gate/ratchet.json` must merge `build/v1` into its branch (never rebase): keep both changelog
lines, the union of the `public_modules` entries, and for the ratchet the base's counts plus this change's own rise.
`lead/mergebase.sh <worktree>` does the first two mechanically.

## 4. In-progress branches (all pushed to GitHub)

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

## 5. Remaining order

1. No pull request of the session is left open (except the build/v1 draft #2).
2. B-455 (E.T13b) and B-456 (E.T13c); then engine E.T14 to E.T19.
3. Plan amendments for B-147 (C.T8) and B-281 (G.T2), then those tasks; C.T9 to C.T12 follow C.T8.
4. B-451 (S.T11b, ready), then servers S.T12 to S.T19 (S.T15 stays unregistered: owner and local tests).
5. Providers P.T3, P.T4, P.T6, P.T7, P.T9, P.T10; interface I.T7 onward; decisions D.T7 to D.T10; edit cycle W.T2 to
   W.T12; footing workflow X.T4 to X.T13; column workflow G.T3 onward; ACI column Z.T5 (pack registration, ready: Z.T2 to Z.T4 merged); SBC overlay Y.T2, Y.T3.
6. Phase 3 and 4 plans: SAFE (0008), Revit (0011), SAP2000 (0012), IDEA (0014).
`ops/remaining-tasks.json` lists every task with its pending dependencies.

## 6. Known problems

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

## 7. The lead scripts (folder `lead/` in the build user's home directory, outside the repository)

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

## 8. Writer rule for the future

New writer tasks use **OpenCode with `opencode/deepseek-v4.1-flash-free`** (owner, 2026-11-12). Cursor chats already in
progress may finish on composer-2.5. OpenCode is outside AGENTS.md section 9 like Cursor (owner queue OQ-Q49): the
lead still reviews every diff, runs the gate and local CI, and merges; writers never push or touch pull requests.
