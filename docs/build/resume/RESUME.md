<!-- The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text. -->

**Status of this copy:** as saved by the lead on 2026-11-12 and 2026-11-14 05:50 UTC. The state after that (runs, merges) is in [../HANDOFF.md](../HANDOFF.md). The `<lane>.args.json` files beside this file are the saved lane arguments, copied verbatim except that machine paths inside them are the same placeholders as above (`<lead>`, `<build-v1>`, `<worktrees>`, `<hub>`); they are valid JSON, so they carry no note of their own. Replace the placeholders with the real paths before passing them to the workflow tool.

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
