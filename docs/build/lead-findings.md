<!-- The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text. -->

**Status of this copy:** the lead findings queue as it stood at the stop of 2026-11-14 about 21:00 UTC (work item B-506). `reports/b<NNN>-*.md` files it names lived in `<lead>/reports/` and are not kept here, except the ones saved beside this file.

# Lead findings queue (for the next engine spec amendment and the owner queue)

## From the engine lane (B-455 E.T13b #308, B-456 E.T13c #316, B-113 E.T14)
- Spec 0001 AC45 and the 4.6 #9 row say ContractError PRECONDITION_FAILED (units_verified); section 6 and resume step 6 say NEEDS_ENGINEER (units_mismatch). Code follows section 6. Amend AC45 and the #9 row.
- 4.6 #9 (c): reconnect read that finds the model not loaded (loaded false, ok true) passes in one process; spec silent.
- A read that raises a transport exception does not mark the host timed out; spec names only three codes.
- The model_open refusal has no engine acceptance criterion.
- working_copy binding "after that step" belongs to the task that adds ctx.working_copy.
- check_model/save steps inserted by _invariants.py do not wait for a pending host: needs its own plan task.
- OWNER QUESTION: a write reconciled not_applied again and again reruns without a cap (no cap invented).
- Numbering of inserted `~host.units` steps by attempt is not stated in spec 0001.
- 4.6 #10 "after every live step" read as after each ToolPort.call only (pinned by test_host_lease_and_close); spec should say it.
- Lease refused at start raises HOST_LOCKED after run_started: run has no terminal or escalation event; can it be resumed?
- _ctx_impl.py:203: BaseException during ToolPort.call journals no host_started.
- E.T14: pending decision in-flight window (handled or queued by B-481); point lookup uses decisions._points.discover(), a non-registered point raises BlockRuleViolation in the engine while spec 0005 AC5 assigns it to the cascade; decide_many re-sends only pending calls (check against decisions plan T7).

## From the run-blockers lane (B-471 #313, B-472 E.T20 #319)
- L1 (blocks T18a): no plan task creates the point_policies default (decision point name -> DecisionPolicy). B-475 is told to define the phase-1 value; if it reports a question, it goes to the owner.
- OWNER QUESTION L2: with a caller-chosen run id, a SERVER_CHECK_FAILED refusal leaves runs/<run_id>/servers/ behind (engine 4.6 row 8 says a refusal writes nothing): keep or remove the logs? Retry with the same id is then refused: plan 0006 T18b must draw a fresh id per attempt.
- L3 (state files): registry B-433 (T18) -> T18a and T18b; new entries for engine T20 (B-472, merged) and plan 0006 T13b; PRIORITY.txt.
- _runner.py:168-179 check-then-act window for a chosen id (acceptable; spec note later).
- Plan 0009 T7 budget (300) not re-measured after the summary gained dropped-release pairs.
- Old amendment comments in plan 0006 T14, T14b, T16, T18a still mention T18 and plan 0010 T9.

## From the basis lane (B-474 #315, B-164 B.T10 pull request 323 open, CI FAIL test-first TF004)
- B-164 holds until engine T19 (B-118) merges (plan 0004 section 1 and engine plan section 1 say T10 needs T19).
- TF004: three T10 tests pass at the base (they pin merged code): amendment B-482 decides the rule-consistent fix.
- Low: no test pins laziness or caching of ctx.basis; "a run that never reads it loads no basis" is true of the ctx loader only; resume does not check the stored basis exists before step 9 (later engine spec).
- Low: engine spec 0001 has no acceptance criterion for the ctx.basis wiring (spec 0004 AC28 covers it).

## From scenario C (B-475 #321, merged a71479b)
- Off the first-live-run path now: servers T16, T17, T19b; SAFE plan 0008 T1 to T3; providers T4, T6, T7, T10b. PRIORITY.txt corrected.
- Registry (state files, next checkpoint): B-138 -> S.T19a (pending E.T13, T15, T16, T19; also after W.T5: both edit tests/fakes/sasaah_csi/**); new items S.T19b (after S.T16, S.T19a), P.T10b (after P.T7, P.T10a); B-229 -> P.T10a (pending D.T10, E.T14b); B-433 (I.T18a/b) points to P.T10a; HANDOFF line 87 says T19.
- Needed before P.T10b: a task that builds the real point-policy mapping (plan 0006 table: no task creates it). Phase 1 binds the empty mapping.
- OWNER (spec acceptance): new AC43 (spec 0002), AC49 (spec 0009), gaps H-G8 and PR-G1, Q16 (d).
- Open: should the phase-1 summary journal dropped releases as (point, reason) like AC29, or stderr warnings only (as written)?
- Open (CLI): the H-G8 refusal exits 70 INTERNAL; exit 2 USAGE may fit better (spec 0006 4.2.3 row 70 says the journal is resumable).
- Closing tasks T19b and T10b replace tests named in AC43/AC49 but do not list the spec files.
- Budgets T19a 230, T19b 120, T10a 150 are estimates.
- Local testing guide notes: first live run settings omit [cli_tools.*]; record mode not available at the first run.

## B-164 rebuild recipe (after B-482 #325; launch only after engine T19, B-118, merges)
Fresh branch from origin/build/v1 (D-22). Commit 1 `test:` holds only tests/workflow/test_basis_workflow.py with
test_unconfirmed_basis_refuses_the_run and its four exclusive imports removed (ruff format applied). Commit 2
`feat(eng-harness): ...` holds CHANGELOG.md, engine/_ctx_impl.py, engine/_runner.py,
tests/property/test_template_basis_props.py and the full tests/workflow/test_basis_workflow.py, copied from
<worktrees>/b164 and re-merged with the engine changes. Net diff equals B-164's. Close pull request 323 or
replace its branch; Plan-Task line names T10.

## From the calcs-2 lane (B-467 #312, B-469 #318, B-470 C.T8c #324; B-460 C.T8b stopped at the mutation step)
- B-460: mutmut turns `identities[-1]` into `[+1]`, the calc-module rules test then reports FB005 on the mutated copy. Lead decision: follow the B-470 precedent (name the element without a numeric literal, inside T8b's files); the rules test is not changed. Patch of the rejected route: reports/b460-trial-rules-test.patch.
- B-483 (docs, before C.T9 and W.T3): effect `key` is the D2 reported key with the list name (spec 0003 4.8 R3, spec 0007 4.4.2 and K6); spec 0007 4.5 steps 4 and 9 name flat before_/after_ inputs; plan 0003 section 1 mentions T8c.
- B-484 (docs): other quantity basis paths still without unit suffix (checks.equilibrium_relative_tolerance, mapping.offset_x/y/z, modeling.section_increment, materials.concrete_fc, materials.rebar_fy, columns.effective_length_factor, foundation.*, materials.*, durability.* of structural-codes plan 0002 Q2); merged footing calc harness.footing_subjects still reads compare.angle (new calc hash; owner re-verifies).
- OWNER QUEUE: clause document aci318_14.13_3_1_1.bearing_pressure_service.md line 110 basis `limits.ratio_limit` -> `limits.ratio_limit_ratio` (protected).
- State files: LOCAL-TESTING.md lines 539, 540, 542 still list old basis names (fix at the next checkpoint).
- Low: kind example fixtures model_diff.json and readback_check.json use old-form keys; compare_section counts section members under key [] only when changed; null key member rule (only trailing case.step may be null); the edit-cycle workflow must pass model_diff.BASIS_FIELDS as the CalcPort basis_fields.

## From the basis-names lane (B-484 #330, merged beccdb9) and merges of 2026-11-14 (B-113 #326, B-466 #327, B-476 #328, B-483 #329)
- Hold of playbook 5d lifted; note rewritten (names on origin/build/v1 bind; b281, b395, b396 writers rename).
- New plan tasks (deferred set, not on the first-live-run path): footing plan 0010 T3b (merged harness.footing_subjects reads suffixed names; budget 40; edits tests/data/golden/footing/subjects-*.json, a CODEOWNERS test-oracle path: AW02/GC015 owner review; regenerates its calcs.lock.json entry, and whichever of T3b and another calc task merges second regenerates its own entry) = work item B-485; templates plan 0004 T11 (template keys and FieldSpec paths follow the contract basis path rule; budget 60; templates/_model.py is CODEOWNERS-protected) = work item B-486. Their tests_first were reasoned, not run: the writer verifies red at the base first.
- OWNER O-1: does harness.footing_subjects need version 2 after the rename (calcs spec 4.2)? T3b keeps version 1 (draft, never approved).
- OWNER O-3: 13 renames in 8 protected ACI clause documents (table in b484-writer.md section 2d) plus line 110 `limits.ratio_limit`.
- LEAD O-2: aci318-14 tests/unit/test_bearing.py line 132 old name: fold into the next aci318-14 task that touches the file.
- ADR-0034 merged as Proposed: owner acceptance and its six open questions (ADR section 'Open questions for the owner') go to the owner now.
- 2026-11-14: lane editcycle-1 first run (wf_b258f30b-e6a): the B-196 writer refused the task (saw the owner's status question as the only request). Relaunched as wf_cbbe19b3-09c with an authority note; standing note added to playbook 5d.

## From the engine-2 lane, completed 2026-11-14 (B-481 #322, B-113 E.T14 #326, B-350 E.T14b #332 merged; B-114 E.T15 NEEDS_PLAN_AMENDMENT)
- B-114 (E.T15, approvals) is written in <worktrees>/b114 (commits ab0f9be test, 68568fc feat; 338 of 380 lines; gate pass without mutation). It needs engine/_runner.py in T15's files (one line: ports.approvals passed to Ctx). Amendment B-492 (B-488 to B-491 are registry entries of the checkpoint: I.T18b, I.T13b, S.T19b, P.T10b), then engine-3 lane continues B-114 to B-118.
- read and decide steps always journal attempt 1 (_ctx_impl.py 259, 345-359); in a restored range ResumeIndex expects attempt+1 (calc and tool do that). Settle read and decide together (later engine amendment).
- A hard kill after decision_made and before step_completed journals decision_made again for the same request id at the rerun; the reader takes the first. Spec 0001 4.5.3 or 4.4 could state it.
- No DecisionPort wired: decide raises ContractError INTERNAL (no new code). Lead decision recorded here.
- step_rerun reason for a rerun decision step is `read_in_flight` (enum has no decision reason); engineer-tier decide rerun: spec does not say whether it re-presents or reuses the answer.
- ctx.ask stores quantity-typed fields with unit null: spec 0001 4.3.2 / plan T14b do not say how the unit is derived; needed before a block asks for a quantity (plans 0010, 0013).
- tests/unit/test_runner.py::test_caller_chosen_run_id failed once under load on a leftover run.lock (flaky; watch).
- E.T15 concerns: approval_requested.binding stored as dict (spec 4.9 writes a list); fingerprint and file-hash tracking after a step under an approval left to the task that journals tool saves (B-415 text); signed_off.outputs reading; only ctx.block is an expiry scope; approve step in flight resumes as NeedsReconciliation (as ask does; _inflight.py outside T15); need_approval helper kept.
- Gate notice RT001: tools/eng-dev-gate noqa count fell 19 -> 18 (ratchet --update in a later gate task).

## From the editcycle-1 lane (B-196 W.T2 NEEDS_PLAN_AMENDMENT, 2026-11-14)
- B-196 written in <worktrees>/b196 (head aa802f6, 349 of 380 lines, nine hand-derived golden cases). The calc-module rules test (spec 0003 4.3 allowed imports) blocks eng_harness.kinds.edit_cycle and eng_harness.workflows.model_edit_cycle (ChangeSetDraft, refused_gap from T1b). Trial patch <lead>/reports/b196-trial-rules-test.patch. Amendment B-493 (spec 0003 4.3 plus plan 0007 T2 files), then B-196 continues in lane editcycle-2.
- Spec questions recorded in the calc's verification record: harness.csi_name_lists/1 has no load-case list (K2 cannot check a load_case combination term); known joints = frame ends, area joints, restraint rows; a non-number basis value is SOURCE_MISSING; answer reference form #/fields/change_set/value/items/<i>/<field>.
- W.T8 must pass the calc's BASIS_FIELDS as the CalcPort basis_fields.

## Owner answers of 2026-11-14 («نفّذ التوصيات»)
- Record: <lead>/reports/owner-answers-2026-11-14.md. Applied by B-495 (specs and plans) and B-494 (ADR-0034). Still unanswered: section C of the record (ADR-0034 acceptance, scenario C acceptance, clause documents route, combination factors, MODEL_CHANGED_OUTSIDE, point-policy mapping task). Next state checkpoint records the answers in BUILD-STATUS section 6.
- QUEUED: B-496 (ADR-0034 status Proposed -> Accepted, README row, references, Arabic appendix with «أقبل») launches when lane owner-answers (wf_b225907a-526) has merged B-494.
- B-497 (clause documents rename, owner-reviewed pull request, not merged by the integrator): lane clause-docs.

## Lane calcs-3 finished (run wf_66240cfa-1a7), 2026-11-14

- Merged: B-483 (#329), B-460 C.T8b (#333), B-148 C.T9 (#338). B-149 C.T10: REPAIR_BLOCKED at integration, pull request 343 open, not merged.
- B-149 cause: TF004. `test_golden_expectations_are_valid_payloads` of the first test commit 15cb935 passes at the base
  (it validates against `DesignSummary`, which exists at the base). The writer's local fix bfcfddc (not pushed) looks the
  kind up through the calc registry, which fails at the base for the right reason, but test-first reads the first `test:`
  commit, so the history must be rebuilt. LEAD DECISION (D-22): rebuild on a fresh branch
  `feat/b149-harness-ct10-calc-4-design-results-r2`, new pull request replaces 343 (lane calcs-4). No force push.
- DEFECT for the edit cycle (B-498, docs, before W.T3 = B-197): spec 0003 section 4.8 R3 with spec 0007 section 4.4.2:
  a `set` or `add` effect on a whole combination (key [combinations, C]) cannot explain the item changes that D2 reports
  under the nested key [combinations, C, items, case, case_type]; a correct load_combination_set edit gives `unexpected`
  and FAIL. Either R3 lets a parent-key effect explain nested changes (then merged calc 3 needs a code follow-up), or
  spec 0007 projects combination effects per item (only W.T3, not yet written, changes).
- Spec 0003 wording gaps, merged code is the conservative reading (B-498 records them, no new behaviour): AC38 message
  "no design results" has no field in harness.design_summary/1 (the code puts reasons in trace step `status_reasons`);
  section 4.9 S5 `changes` when `previous` is absent (code: all lists empty); read-back: `remove` of an object still
  present gives mismatch, an effect under a duplicated key is compared with every object, trace outputs are
  [identical, status]; section 4.12 HarnessCalcPort signature lacks `basis_fields` (code has it, supplied at construction).
- Open, not decided by documents (owner queue): Effect.unit is read by nothing (refuse a unit that differs from the
  field's canonical unit?); section 4.9 does not say whether verdicts whose source is not `host` (Q7) or verdicts and
  frames of different models are refused; R0 "(or its working copy)" cannot be recognised (RefMeta has no derived_from).
- Still open from earlier: footing/subjects.py reads the old field `compare.angle`; the edit-cycle workflow (W.T8) must
  pass BASIS_FIELDS as CalcPort basis_fields; RT001 notice (eng-dev-gate noqa count 19 -> 18) needs `ratchet --update`
  in a separate change; golden cases of calc 3 use one tolerance for every kind (unit tests cover the lookup).
- Count: plan tasks total is now 330 (plan 0015 adds 20, B-495 adds 1); merged 191 (188 + B-148, B-133, B-114).

## Lane engine-3 finished (run wf_7e3d299f-d84), 2026-11-14

- Merged: B-492 (#337), B-114 E.T15 (#341). B-115 E.T16: NEEDS_PLAN_AMENDMENT at the write stage; B-116 to B-118 skipped.
- B-115: written and committed locally in <worktrees>/b115 (aaf8d4a test, 0add9db feat, 2326f2e test typing; not
  pushed; note <lead>/reports/b115-writer.md): 408 counted lines against 380 (CHANGELOG 1, local-testing 2,
  _ctx_impl 85, _modes 242, _promote 73, _runner 5), above the 400 cap, and files outside T16's list: engine/_runner.py
  (5 lines) and six existing test files (one to three lines each). LEAD DECISION (D-12): split, never stretch:
  amendment B-499 splits T16 into T16 (modes, always-ask, working copies) and T16b (file-copy promotion, work item
  B-500); lane engine-4 then rebuilds B-115 to the amended T16 and writes B-500 from the same local work.
- Findings the amendment B-499 must give a home or queue as open questions: (a) a promote step in flight is journaled
  with effect "none" while spec table 4.3.2 says "write", and reconciling it through ToolPort.reconcile would be wrong;
  (b) `ask` (and engineer-tier decision) is not in `_inflight._RERUN` although spec 4.5.3 says it is presented again
  (AC36), T14b is merged; (c) DEFECT on the first-live-run path: `_steps.resume_path` does not hash model keys outside
  the path grammar (@, /, backslash) and real keys are file paths: a resume raises ValueError; (d) spec 4.9 writes
  `approval_requested.binding` as a list, merged code uses a map keyed by model key; (e) step_rerun of an approval
  carries reason `read_in_flight`; (f) tool saves under an approval do not update the expected fingerprint and file
  hash (plan 0007 T6 must extend Approvals.stepped); (g) FileOps.sha256 must use the adapter's file_sha256 definition;
  writer readings where the spec is silent (every open model gets a copy at first write; promoting a model with no
  working copy is a BlockRuleViolation; a rejected item rejects the whole write; grants are re-bound to the copy).
- An approval asked inside an `attempts` or `parallel` child expires at the enclosing ctx.block return (B-114 note).

## Usage limit stop and resume, 2026-11-14 (about 13:00 to 17:05 UTC)

- All ten lanes died at the 5-hour usage limit (agents failed with "You've hit your 5-hour limit"). Nothing was lost:
  worktrees intact, stale file integrate.owner.b196 removed (no flock process behind it).
- Resume method that works: per-lane script <lead>/resume/resume-<lane>.js (the lane script with the exact
  original args embedded as ARGS, taken from the session transcript; args also saved as <lane>.args.json and
  args-by-run.json), copied to the session scratchpad (the Workflow tool only loads scripts from there or from paths it
  returned), launched with resumeFromRunId = the lane's run id. Cached agents replay; only the dead agent runs again.
- Resumed at 17:08 UTC: editcycle-2 (B-196 integrate), servers-2 (B-135 integrate, then B-136), clause-docs (B-497
  integrate, no merge), owner-answers (B-494 review), calcs-4 (B-149 gate), editcycle-3 (B-498 review, B-199 write),
  engine-4 (B-499 write), interface-2 (B-181, B-489 write). HELD until short lanes finish (pace, D-35):
  amendments-zt5-gt2 (B-281 integrate, then B-282, B-283) and tasklog-docs (B-479 integrate).
- Full lane results of the stopped runs: <lead>/reports/lane-results-2026-11-14.md.

## Queue from those results (work items to open; numbers reserved)

- B-501 (docs, structural-codes plan 0004 T5 files += packages/eng-harness/tests/unit/calcs/test_code_pack_route.py,
  the third test that pins the registered check count; then B-334 Z.T5 applies the one-line test edit; pull request 331
  is red until then). Deferred set.
- B-502 (docs, plan 0015 gains task T0 "AGENTS template and workspace root rules for the task log (ADR-0034 PR B)" with
  the 13 files, budget 100, so that B-477's commit 65a4e82 in <worktrees>/b477 has a Plan-Task; body Risk: r2, r3).
  Task-log set; protected paths, owner review expected (AW02).
- B-503 (docs, FIRST-LIVE-RUN PATH, after B-499 and B-498 merged): (1) the engine ignores summary.clean:
  engine/_invariants.py Guard.check raises ModelIntegrityError only for a FailureEnvelope or ContractError, so a
  READBACK_MISMATCH does not stop a run (spec 0001 invariant 1): needs an engine plan task; (2) gap H-G9 (spec 0002
  line 992): no task hands the frozen basis value checks.readback_relative_tolerance_ratio to ReadBack.tolerance_ratio
  (ports are built at step 1 of spec 0006 4.2.2, basis frozen at step 3, resume skips the freeze): decide how (a
  build_ports argument, a setter on AdapterHostPort, or building the ports after step 3) and give it a task (T19a?);
  until then every written quantity reads back READBACK_UNAVAILABLE; (3) T19a must add CSI_KINDS to the run's
  KindRegistry, wire WrittenItems/host.wrote into CsiToolPort and Binding.pre_image_ref; (4) plan 0007 T4's inputs
  harness.csi_design_results/1 and harness.csi_analysis_messages/1 use CsiRows from eng_harness.adapters.csi._replies,
  which spec 0003 4.3 does not admit: move the model to a kinds module or type the inputs otherwise, before B-198;
  (5) plan 0002 T14 names `preview` but the CSI preview is not built (ToolPort.preview came with engine T15): home in a
  later task; (6) open questions, not to decide: does csi_design_run count as an adapter write (wrote())? audit-log
  evidence of spec 0002 4.5.7 has no reader or format; a wanted value of zero is compared exactly; take_warnings() is
  global (OQ-Q67); BUILD_CHANGED is not a HarnessCode member; attempt folder run_dir/tools/<op_id> against spec 4.7;
  (7) decide before plan 0007 T9 merges whether the change-set model moves to a kinds-level module (calc hash closure,
  circular import risk, plan 0013 imports private names from _change_set).
- B-495 readings to confirm with the owner: the rerun cap stop uses the existing NeedsReconciliation stop (not a new
  NEEDS_ENGINEER reason), and the one automatic rerun allowance starts again after each engineer decision; NOT_IMPLEMENTED
  maps to exit 2 for every caller. B-495 added engine task T21 (30 lines) to plan 0001.
- State checkpoint to do: BUILD-STATUS section 6 rows OQ-Q65, Q68, Q85, Q86, Q87, Q90 answered (2026-11-14); owner queue
  ids for the B-465 questions; registry entries for T16b (B-500), T21, plan 0015 tasks; B-149 branch -r2.
- B-497 notes: PR body Risk line (documents say r1); wording item at aci318_14.13_3_1_1 lines 62-63 ("Basis paths are
  lower case ... not in a suffix") now contradicts the renamed rows: goes to the owner in the PR's "For the owner".
- B-479: PR body Risk should be r3; local CI must pass --merged for PS005; lead runbook needs a push-scope step.

## 2026-11-14 evening

- B-196 W.T2 merged (#344): 192 of 330. Low spec findings of W.T2 for a later spec 0007 wording amendment: 4.4.1 input
  `state` is flat fields in code; harness.csi_name_lists/1 has no load-case names (K2 cannot check a load_case term);
  4.3.3 names no component for "dimension greater than zero" (thickness 0 passes when bounds.thickness_min_mm is 0);
  a literal in a non-canonical unit is judged at its exact binary value (0.3 m = 299.999... mm is refused at min 300).
- servers-2 ended: B-135 S.T16 REPAIR_NEEDS_PLAN_AMENDMENT (pull request 345 open). Cause of the CI failure, and of the
  flaky test_caller_chosen_run_id noted earlier: helper `_meta_run_id` in tests/unit/test_runner.py never closes its
  sqlite connection (wal/shm files vanish at garbage collection). Trial patch <lead>/reports/b135-trial-test-runner.patch.
  The `trivial` Plan-Task reason excludes tests/, so: lane servers-3 (run wf_0d05cf16-f04): B-504 docs (T16 files +=
  that test file) -> B-135 (apply patch, existing pull request 345) -> B-136 S.T17.
- S.T16 spec notes: BUILD_CHANGED and LAUNCH_FAILED are not HarnessCode members (adapter uses HOST_ERROR with host_code);
  attempt folder is run_dir/tools/<op_id>; script parameter names -Dxf and -Config are not in the spec (live check).
- B-497 clause documents: pull request 346 OPEN, local CI PASS (9 jobs) on head 96c4f5d against base 4894701, NOT merged:
  awaiting owner review (owner instruction of 2026-11-14). 12 files, 36 counted lines. Items for the owner in the body:
  aci318_14.13_3_1_1 lines 62-63 wording now contradicts the renamed rows; test_bearing.py line 132 keeps the old name
  (next aci318-14 code task); body Risk r0 while the documents say r1. After the owner merges: update playbook 5d and the
  build/v1 copies (docs/build/lead-playbook.md line 195, lead-findings lines 58 and 66) at the next checkpoint.
- tasklog-docs resumed (run wf_db726637-cfb) for the B-479 integration.
- B-497 MERGED by the lead on the owner's instruction «راجعت الطلب 346، ادمجه» (squash d265bee, pull request 346).
  Playbook 5d note updated. build/v1 copies (docs/build/lead-playbook.md line 195, lead-findings lines 58, 66) to update
  at the next checkpoint. Follow-ups: wording of aci318_14.13_3_1_1 lines 62-63 (owner), test_bearing.py line 132 (next
  aci318-14 code task). The integrator of B-494 was holding the lock at the time: it will see BEHIND and merge the base.
- B-494 MERGED (#347): ADR-0034 records the four answers of 2026-11-14; status still Proposed. Lane adr-accept launched
  (run wf_65fa107b-ac6): B-496 moves the status to Accepted on the owner's word «أقبل» and completes the Arabic appendix
  from <lead>/reports/adr-0034-owner-words.md (the 16 answers of 2026-11-12, extracted from the session record;
  all owner messages are in <lead>/reports/owner-words-transcript.txt). Checkpoint items: BUILD-STATUS lines 516
  and 678 and docs/build/lead-findings.md line 68 still say six open questions.
- B-498 MERGED (#348): repair (a), combination edits projected per item; new `change_set` and `basis` inputs of
  harness.expected_effects. B-199 W.T5 NEEDS_PLAN_AMENDMENT: written (worktree b199, head 4aa388b), 371 counted lines
  against 330. Lanes launched: editcycle-4 (run wf_985a361a-b3e): B-505 docs (T5 budget) -> B-199; run-gaps (run
  wf_8090e001-2d6): B-503 docs (first-live-run gaps, seven items) -> B-197 W.T3.
- Owner asked on 2026-11-14 whether this method guarantees working code; the lead's answer: it guarantees agreement
  with the specs and with the fake server, not with the real host; the first live run is the real proof.

## Speed-up measures approved by the owner, 2026-11-14 (work item B-506; no agent was run for it)

- Applied as work-method edits only: playbook section 7 (and pointers in sections 2 and 4), lane script version 2
  (`<lead>/build-lane-v2.workflow.js`: early push by writers, run-only gate runner on the small model with a
  second runner if it dies, gate fixes by the writer model, mutation step alone when the head already passed the gate
  without mutation), the audit script (`<lead>/plan-audit.workflow.js`), the order of the next start in
  RESUME.md. Both scripts pass a syntax check; neither has run.
- Numbers behind the measures (git log of build/v1 since 2026-11-12): 27 pull requests merged, 15 documents and 12
  implementation; 7 of the 15 documents pull requests were plan amendments for a file list, a budget, an import rule or
  a split, and 3 more of that kind were in flight at the stop (B-501, B-504, B-505). Local CI's gate job took 583 s on
  a documents-only pull request (346). One integration at a time.
- Not in force until code merges: measure 2 (B-507), measures 3 and 4b (B-508). Measure 3 may turn out small or be
  dropped: some tests read specs, clause documents and verification records, so a documents-only pull request cannot
  simply skip the tests.
