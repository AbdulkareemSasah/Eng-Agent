<!-- The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text. -->

**Status of this copy:** as saved by the lead at the stop of 2026-11-14 about 21:00 UTC (work item B-506). It is NEWER than the checkpoint section of [../HANDOFF.md](../HANDOFF.md) (B-487): read this file last. The `<lane>.args.json` files beside it are the saved lane arguments with the same placeholders; a `resume-<lane>.js` named below is the lane script with those arguments embedded (rebuild it from `../build-lane.workflow.js` and the args file).

# Resume note: all lanes stopped by the owner at 20:38 UTC, 2026-11-12 (he needs the usage allowance)

Owner instruction: launch no new workflow and resume nothing until he says to continue.
origin/build/v1 at 4bea5bd (B-464, #320). Plan tasks merged: 182 of 305.

Resume each lane with the lane script, `resumeFromRunId` and the IDENTICAL args saved beside this file
(`<lane>.args.json`); finished agents replay from the journal, the agent that was cut off runs again.

| Lane | Run id | Tasks | Stopped at |
|---|---|---|---|
| engine-2 | wf_2aa69ef3-6fb | B-481, B-113, B-350, B-114..B-118 | B-481 waiting for the integration lock (written, reviewed) |
| servers-2 | wf_291c36a0-69b | B-466, B-132, B-133, B-135, B-136 left | B-466 (S.T12b) in work |
| calcs-2 | wf_063e17d6-666 | B-470, B-460, B-148, B-149 left | B-470 waiting for the integration lock |
| basis | wf_153cc0a2-b0f | B-164 left | B-164 waiting for the integration lock |
| tasklog-docs | wf_db726637-cfb | B-476..B-479 | B-476 reviewed APPROVE, not merged |
| scenario-c | wf_6488545e-6ea | B-475 | pull request 321 open, local CI was running on 9d851f90af (check its result; a PASS on the head continues from playbook step 6) |
| amendments-zt5-gt2 | wf_86423180-ee8 | B-334, B-462, B-281..B-283 left | B-334 full gate / integration |
| footing-col (paused earlier) | wf_89fc0eda-b17 | B-395 (needs plan amendment), B-396, B-397 | paused |

Before resuming: `ls <lead>/locks` must show no integrate.owner.* or prio-wait.* files (removed at the stop);
check open pull requests into build/v1; after scenario C merges, correct PRIORITY.txt.
Queued for the owner: <lead>/reports/lead-findings.md (two owner questions), ADR-0034 acceptance after B-476.

## Resumed on 2026-11-14 05:50 UTC (owner said continue; machine had restarted, state intact)
Running (same run ids): engine-2 task wtmi6r2hr, basis wnuo53nnr, scenario-c wd3ttrr6i, calcs-2 wtk1xk0z0,
servers-2 wygj98tsl, tasklog-docs wh3s2a2wi. NOT resumed yet (deferred set, D-35): amendments-zt5-gt2
(wf_86423180-ee8), footing-col (wf_89fc0eda-b17); start one when basis or scenario-c finishes.

## 2026-11-14, lanes launched after the resume (arguments are in the session transcript, in the Workflow call that started each run)
- calcs-3: run wf_66240cfa-1a7 (B-483 merged, B-460 merged as pull request 333; B-148, B-149 follow)
- basis-names: run wf_a55b13c1-0d0, finished (B-484 merged)
- editcycle-1: run wf_cbbe19b3-09c (B-196 W.T2); the first run wf_b258f30b-e6a ended at once (writer refused), do not resume it
- engine-2: run wf_2aa69ef3-6fb finished (B-114 stopped for a plan amendment)
- engine-3: run wf_7e3d299f-d84 (B-492 docs, then B-114 to B-118)
- editcycle-2: run wf_1718544e-72b (B-493 docs, then B-196 W.T2 continues); editcycle-1 run wf_cbbe19b3-09c finished (B-196 stopped for a plan amendment)
- owner-answers: run wf_b225907a-526 (B-495 specs and plans, then B-494 ADR-0034 answers); source reports/owner-answers-2026-11-14.md
- clause-docs: run wf_6151b08e-a0b (B-497, owner-reviewed pull request: the integrator does not merge; expected outcome BLOCKED 'awaiting owner review')

## Lanes launched 2026-11-14 after lane calcs-3 finished

- calcs-4: run wf_12a01a80-367 (B-149 rebuild on branch ...-r2 replacing pull request 343, then B-150 C.T11, B-151 C.T12)
- interface-2: run wf_950086fe-50c (B-181 I.T7, B-429 I.T7b, B-183 I.T9, B-184 I.T10, B-489 I.T13b)
- editcycle-3: run wf_cea722ef-4ab (B-498 docs: R3 and combination effects; B-199 W.T5)
- Waiting: B-197 W.T3 needs B-196 (lane editcycle-2) and B-498 merged. B-496 needs B-494 merged.
- engine-4: run wf_4b8ff203-756 (B-499 docs: T16 split -> B-115 E.T16 rebuilt -> B-500 E.T16b -> B-116 -> B-117 -> B-118)
  B-115 full local work: <worktrees>/b115 head 2326f2e (to be kept as local branch wip/b115-full).

## 2026-11-14 17:08 UTC: resumed after the usage-limit stop (see lead-findings.md, section "Usage limit stop and resume")

Run ids are unchanged by a resume. Scripts: <lead>/resume/resume-<lane>.js (copy to the session scratchpad
before use). Running: editcycle-2 wf_1718544e-72b, servers-2 wf_291c36a0-69b, clause-docs wf_6151b08e-a0b,
owner-answers wf_b225907a-526, calcs-4 wf_12a01a80-367, editcycle-3 wf_cea722ef-4ab, engine-4 wf_4b8ff203-756,
interface-2 wf_950086fe-50c. Held: amendments-zt5-gt2 wf_86423180-ee8, tasklog-docs wf_db726637-cfb.

## 2026-11-14 about 21:00 UTC: STOPPED by the owner («توقف، احتاج الليميت»). Resume only when he says to continue.

All nine lanes stopped with TaskStop; gate, local CI and lock-holder processes killed; owner and prio-wait lock files
removed. To resume: copy <lead>/resume/resume-<lane>.js to the session scratchpad (for the lanes that have
one) and launch with resumeFromRunId; for the lanes launched after 17:08 UTC use the lane script with the args from the
session transcript (extract again into args-by-run.json with the snippet in lead-findings, section "Usage limit stop
and resume") and the run id below.
- calcs-4 wf_12a01a80-367 (B-149 rebuild at gate/integrate, then B-150, B-151)        resume-calcs-4.js
- engine-4 wf_4b8ff203-756 (B-499 docs, then B-115, B-500, B-116, B-117, B-118)        resume-engine-4.js
- interface-2 wf_950086fe-50c (B-181, B-429, B-183, B-184, B-489)                      resume-interface-2.js
- amendments-zt5-gt2 wf_86423180-ee8 (B-281 integrate, then B-282, B-283)              resume-amendments-zt5-gt2.js
- tasklog-docs wf_db726637-cfb (B-479 integrate)                                       resume-tasklog-docs.js
- servers-3 wf_0d05cf16-f04 (B-504 docs, B-135 on pull request 345, B-136)             args in transcript
- adr-accept wf_65fa107b-ac6 (B-496 ADR-0034 Accepted)                                 args in transcript
- editcycle-4 wf_985a361a-b3e (B-505 docs, B-199)                                      args in transcript
- run-gaps wf_8090e001-2d6 (B-503 docs, B-197)                                         args in transcript
Queued, not launched: B-501 (codes plan 0004 T5 files), B-502 (plan 0015 T0 for B-477), state checkpoint.
Count at the stop: see `git log origin/build/v1`; last stated 192 of 330.
- All nine lanes now have resume-<lane>.js and <lane>.args.json in this folder. At the stop: B-499 (#349) and B-181 (#350) had merged; pull request 351 open with its CI run killed and released. Count 193 merged.

## Order of the next start (after the owner says to continue). Speed-up measures: playbook section 7 (B-506)

1. Resume the nine stopped lanes with their own `resume-<lane>.js` (older role texts, cached agents replay). At most
   six lanes at a time (usage limit: it stopped all work twice); path lanes first: engine-4, run-gaps, editcycle-4,
   interface-2, servers-3, calcs-4; then adr-accept, tasklog-docs, amendments-zt5-gt2.
2. Run `<lead>/plan-audit.workflow.js` (measure 1) over the first-live-run plans, with in `notes` the
   amendments in flight for each plan (B-503 run gaps, B-504 servers T16, B-505 edit-cycle T5): engine 0001 (T16b, T17,
   T18, T19, T21 and whatever B-503 adds), servers 0002 (T17, T19a, T19b), interface 0006 (T7b, T9, T10, T13b, T14,
   T14b, T15, T16, T16b, T17, T17b, T17c, T18a, T18b), edit cycle 0007 (T3, T4, T6 to T12), decisions 0008 (T7 to
   T10), providers 0009 (T4, T6, T7, T10a, T10b). Then ONE documents amendment per plan with the confirmed findings.
3. Every NEW lane uses `<lead>/build-lane-v2.workflow.js` (measures 4a, 5, 6); copy it to the session
   scratchpad first (the Workflow tool loads scripts only from there or from paths it returned). It has not run yet:
   watch its first lane (gate runner on the small model, early pushes) and fall back to the old script if it misbehaves.
4. Open work items B-507 (measure 2: gate spec 0001 amendment and its plan task for small edits of existing tests
   outside the file list, with the conditions of playbook section 7 item 2) and B-508 (measures 3 and 4b: local CI for
   documents-only pull requests and reuse of a mutation result, only with the proof playbook section 7 requires; find
   first which spec and plan govern `ops/localci.py` and the gate's CI jobs). Both touch protected gate paths: the
   owner approved the measures on 2026-11-14; the pull requests show the usual awaiting-owner notices.
5. Then the queue: B-501, B-502, the state checkpoint (BUILD-STATUS section 6 rows, registry entries for T16b = B-500,
   T21, plan 0015 tasks, the B-149 branch `-r2`), and the waves that open as dependencies merge.
