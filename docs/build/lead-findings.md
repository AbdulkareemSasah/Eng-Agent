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

## Plan pre-flight audit, first run (2026-11-15, run wf_469071df-21c; measure 1 of playbook section 7)

- 47 agents, 5.5 million tokens, 52 minutes; 28 tasks of four plans checked. 43 findings: 28 confirmed by the
  adversarial verifier, 15 rejected. Files: <lead>/reports/plan-audit/<slug>-confirmed.md (confirmed with the
  corrected edits; rejected listed at the end) and <slug>.md (the raw record).
- engine 0001 (5): T17 block-module allowlist of spec 4.1.2 against merged workflow modules (eng_harness.kinds.edit_cycle,
  eng_contract.units); T17 rules tests cannot be red at the base (TF004); T18 progress sink has no seam in its files
  (AC58); T18 overhead test is green at the base; T19 (crash matrix) adds no source, so its test is green at the base.
- interface 0006 (9): T14 the merged engine always calls answer(rid, wait=False) while spec 4.4.5 says wait=True;
  T14b `[decisions]` is refused by the merged configuration; T15 needs WorkflowDef.basis_fields (plan 0007 T6) and the
  inputs of --template are undefined; T14 RunRequest.basis_ref for a workflow without basis fields; T9 the HTML builder
  cannot render the form field names with ':' and where sign-off exception reasons travel is undefined; T14 `by` of a
  file answer when [engine] engineer is unset; stale prose on EnginePorts in T14, T14b, T16b.
- edit cycle 0007 (10): T4 calc cannot output verdicts.set/1 (registry refuses a non-harness output kind) and has no
  input list; T6 import cycle block.py -> basis._fields; T7 to T9 gate FB005 flags the literal in version=1 of
  @decision_point, @rule, @workflow, @block (.gate/forbidden.yml lists only calc and CheckMeta); T8 calcs take the
  whole basis record but BasisView offers only ref(path); T9 is planned at the 400 cap; T10 timings section lives in
  report/_document.py (not listed) and the value-source audit lacks the list of engineering parameters; T11 and T12
  tests_first are green at the base (T12 has no source file).
- decisions 0005 (4): T8 redaction paths have no field in the merged Suggestion model; T10 and T8 tests_first green at
  the base; T7 to T9 do NOT need engine T17 (only T10 does): the decisions wave can start as soon as the plan says so.
- Lane plan-fixes-1 (first lane on lane script version 2, run wf_36c0dc39-8de): B-509 engine amendment, B-512 decisions
  amendment. Queued: B-510 interface amendment (when a lane frees), B-511 edit-cycle amendment (after B-503 merges,
  same plan parts). Test-only tasks (engine T19, edit-cycle T12) need a pull request title type the gate exempts from
  the red-at-base run: set prTitle when launching them, as B-509 and B-511 will state.

## 2026-11-15 about 16:00 UTC

- Merged since the resume: B-505 (#352), B-504, B-149 C.T10 (#353, the rebuilt branch), B-509 (engine audit fixes),
  B-503 (first-live-run gaps). Count 194 of 334 (B-503 added three tasks).
- The owner said the progress is slow. LEAD DECISION (follows D-32, first live run first): all capacity goes to the
  first-live-run path. Lane calcs-4 stopped after B-149 merged (B-150 C.T11 and B-151 C.T12 are off the path; resume
  with resume-calcs-4.js later). Held and off the path until the path lanes thin out: tasklog-docs, amendments-zt5-gt2,
  B-501, B-502, B-507, B-508. adr-accept (B-496) is short and stays queued behind the path lanes.
- Path still to merge, about 36 tasks: engine T16, T16b, T17, T18, T19, T21 and the task B-503 added; servers T16
  (in integration), T19a; interface T7b, T9, T10, T13b, T14, T14b, T15, T16, T16b, T18a; edit cycle T3 to T12;
  decisions T7 to T10; providers T10a; templates T10 (B-164 rebuild).
- B-509 (#354) and B-512 (#356) MERGED: lane script version 2 worked for documents tasks (early push by the writer).
  Lanes launched on version 2: decisions-1 (run wf_05f38bb6-2eb): B-171 D.T7 -> B-172 D.T8 -> B-173 D.T9;
  plan-fixes-2 (run wf_edee707e-81a): B-510 interface audit fixes -> B-511 edit-cycle audit fixes.
- Owner question to collect: decisions spec Q16 (redaction paths: optional `paths` on Suggestion; interim: recorded
  without paths). Engine T18 budget of about 200 is an estimate. local-testing.md line 3 still names T19 (T16 or T16b).
- Registry pushed directly (state file): B-118 title type `test`, B-171 deps emptied, B-174 deps, B-149 branch -r2
  (commits 6563f01 and 34040c3; the first collapsed the file to one line by mistake, the second restored its layout).
  B-503 new task ids and B-500, T21 entries still to add at the checkpoint.
- run-gaps ended: B-503 MERGED (#355): new tasks engine T22 (not-clean summary stops the run), servers T21, edit-cycle
  T13 (budgets are estimates: T19a 310, T21 150, T13 40, T3 340, T22 30); T19a now waits for plan 0007 T5 and T13 and
  plan 0002 T21; plan 0007 T8 waits for engine T22. Unordered file pairs that may conflict at integration: T19a and
  servers T16 (_toolport.py), T21 and plan 0013 T2 (_kinds.py), plan 0007 T13 and servers T15 (csi/_tools.py).
  Lead findings: RUN THE PLAN AUDIT ON servers T19a before launching it (AdapterHostPort has no preflight, acquire,
  release, session_epoch; no production ModelBinder; ServerCheck exists only after preflight); host_design_verdicts
  reads limits.ratio_limit_ratio but the basis_fields map names only model_diff and readback_check (for B-511).
- B-197 W.T3 NEEDS_PLAN_AMENDMENT: written (worktree b197, head bda000f, 294 lines); the kind harness.expected_effects/1
  lacks the calc payload wrapper members, so the record cannot be stored; fix is in kinds/calcs.py (not in T3's files)
  plus the footing verification record's hash line. Lane editcycle-5 (version 2, run wf_7550c639-02c): B-513 docs ->
  B-197. Defects of merged harness.change_set_check found by the T3 writer (homed by B-513): no INVALID_ITEM_ID for an
  item id containing '/', duplicate terms of one combination item not refused.

## Usage limit again, 2026-11-15 about 17:20 to 18:40 UTC

- The 5-hour limit stopped five lanes (resets 18:40 UTC): plan-fixes-2 (B-510 at review round 2, B-511 not started),
  decisions-1 (B-171 D.T7 written and reviewed, died at the gate), editcycle-4 (B-199 at the gate; B-505 merged #352),
  editcycle-5 (B-513 reviewed, died at integration), interface-2 (B-489 at the gate). engine-4 (B-115 at integration,
  pull request 357, local CI running) and servers-3 (B-135 at integration) were still alive at 18:13 UTC.
- The owner said «كمل» at about 18:10 UTC; a scheduled message wakes the lead at 18:43 UTC to resume (resume scripts
  for the version 2 lanes are built: resume-plan-fixes-2.js, resume-decisions-1.js, resume-editcycle-5.js).
- interface-2 results: B-429 I.T7b GATE_BLOCKED: written and reviewed (worktree b429, head f08f758) but its gate never
  ran: it was not in PRIORITY.txt and priority items kept the lock (playbook 5b starvation). FIX: every path item is in
  PRIORITY.txt now (B-429, B-183, B-184, B-489, B-171 to B-174, B-500, B-116 to B-118, B-198, B-200 to B-203, B-138,
  B-229, B-136). B-183 I.T9 NEEDS_PLAN_AMENDMENT: written (worktree b183, head 86d3e4d): the HTML builder needs a
  FieldName type in _html.py for the answer field names with ':' (audit finding F6, amendment B-510); 382 lines in
  list against 380, 399 with _html.py; trial patch <lead>/reports/b183-trial-out-of-list.patch.
- Lead findings: the merged engine passes wait=False on every port call (spec 0006 4.4.5 says wait=True; B-510 F1);
  AC31 refusal re-render needs _routes.py; POLL_S is 0.5 s against "every second"; load-sensitive test
  tests/unit/pages/test_single_use.py::test_concurrent_answers_one_wins (add to the playbook list); D.T7: the plan's
  risk set is r1, r3 (not r1, r2, r3); label state stores the outgoing state while the hash is of the full state
  (spec 4.10/4.11 should say so); spec 0007 section 4.10 says the adapter-local tools are "in the CSI allowlist"
  (they are in _tools.py); spec 0007 section 6 lacks rows for T5's error codes; B-513: six draft calc hashes move
  (owner re-verification bookkeeping); spec 0007 Q18 (same-key terms) is an owner question.
- Measured: today's window lasted about 3.5 hours with six to seven lanes plus the audit (5.5 million tokens).

## Low-cost mode, 2026-11-15 about 19:30 UTC (work item B-514; the owner: the slow method used up his allowance)

- Measured from the agent records of the whole session: opus 174 agents (6.5M output, 42M cache-write, 1.22 billion
  cache-read), sonnet 284 agents (9.2M output, 82M cache-write, 1.47 billion cache-read). By role (fresh tokens):
  write sonnet 32.3M (55), integrate sonnet 29.3M (74), write opus 20.8M (41), review opus 17.5M (81), gate sonnet 6.6M
  (34), review sonnet 6.0M (29), fix opus 4.8M, refute 4.0M, audit 3.4M, verify opus 2.5M. About 1.9M per merged PR.
- Done: <lead>/tools/integrate.sh (the integrator's mechanical steps), lane script version 3
  (<lead>/build-lane-v3.workflow.js: writer writes the PR body file, integrator is a fixed sequence at low
  effort), playbook section 8. Neither has run yet: watch the first version 3 lane.
- servers-3 stopped (B-136 S.T17 is off the path). Off the path and frozen: task log, B-507, B-508, B-501, B-502,
  calcs T11 and T12, columns, footing, other hosts, S.T17, S.T19b. B-496 (ADR-0034 Accepted) stays queued: short.

## 2026-11-15 about 19:45 UTC: the merge queue is stuck behind one failed local CI run

- B-115 (engine T16, pull request 357) holds the integration lock since about 18:13 UTC. Its first local CI run (1651 s)
  FAILED on the flaky merged test tests/unit/pages/test_single_use.py::test_concurrent_answers_one_wins ([200, 404]
  where [200, 409] is expected; from T7, pull request 350); the second run started 19:17 UTC. Waiting behind it:
  B-171, B-199, B-429, B-489, B-513. No merge since 18:36 UTC.
- A read-only diagnosis agent (sonnet) is finding the root cause and the smallest fix; results in
  <lead>/reports/flaky-single-use.md and .patch. Then: a home for the fix (a file added to an unwritten or
  waiting task is a mechanical amendment by the lead; a new task is not).
- Lesson for the estimate: a local CI run of an engine pull request takes about 27 minutes and a flaky test doubles it.
- Measured at 19:45 UTC: the container has 4 cores and the load average was 8.9 with seven lanes, a local CI run with
  mutation and the diagnosis agent's stress loop. Rule added (playbook section 8 item 7): at most three writing lanes.
  ops/localci.py entered build/v1 by a direct state commit of the earlier lead (c7ef1f6): it is lead tooling, but it is
  not in the list of files the owner let this session push directly; a change to it (per-pull-request CI without the
  mutation step, full CI on build/v1 every ten merges) needs the owner's word. Asked on 2026-11-15.
- Owner approved (verbatim «نعم موافق، طبّق وكمل»): per-pull-request local CI without the mutation step, full run on
  build/v1 every ten merges (B-516, playbook section 8 item 8). A sonnet agent is changing ops/localci.py in
  <worktrees>/b516 (no push); the lead pushes it to build/v1 under the integration lock when no local CI run is in
  progress, then updates the reference checkout. Merges since the last full run with mutation: count from this push.
- Flaky test diagnosed (report <lead>/reports/flaky-single-use.md, patch flaky-single-use.patch): a PRODUCT
  defect of merged T7 code, not a test defect. Router.handle (pages/_routes.py 110 to 112) fetches the screen before
  submit; PageHub.screen (pages/_ports.py 109) returns None once the request is recorded, so the loser of two
  concurrent answers gets 404 where AC30 requires 409. Failure rate under load 19 to 30 percent of runs, 0 of 400 with
  the fix (an `answering` keyword of the screen lookup on POST; 11 counted lines in _ports.py and _routes.py, 2 lines in
  tests/helpers/page_client.py).
- Home: T7b (B-429, written, not merged, already lists _ports.py). FIRST lead-written mechanical amendment: B-517
  (worktree <worktrees>/b517, commit a04c082: plan 0006 T7b files += pages/_routes.py, tests/helpers/page_client.py;
  budget 130 unchanged, 111 with the fix); integrating with tools/integrate.sh run by the lead in the background
  (first real use of the script). interface-3 stopped; after B-517 merges relaunch B-429 on lane script version 3 with
  the patch applied as a `fix` commit plus the reviewer on the delta.
- B-516 (ops/localci.py without the mutation step in pull request runs): commit 52a8848 in <worktrees>/b516, reviewed
  by the lead, waiting on the integration lock to be pushed (background job).

## 2026-11-15 22:15 UTC, lane editcycle-4 finished (B-505 #352, B-199 W.T5 #362 merged)
- Spec 0007 section 4.10 line 578 says "three adapter-local tools in the CSI allowlist": they are in adapters/csi/_tools.py, not in the allowlist file; T5 prose "allowlist entries" has the same stale wording. Mechanical prose correction (lead-written, section 8 item 6) with the next edit-cycle amendment.
- Spec 0007 section 6 lacks rows for the codes T5 chose: CONFLICT (write or save while a snapshot is open, existing snapshot target, copy hash differs), NOT_FOUND (unknown snapshot name), INTERNAL (no revision wiring). This is an error-code change: full documents cycle, with the B-503 follow-ups.
- With revisions wired every write costs one extra csi_model_info read; csi_run_analysis is refused while a snapshot is open: note for the edit-cycle workflow host-call budget.
- Known gaps listed in the pull request: AdapterHostPort not told of the new working file after csi_open_revision; production wiring of Revisions belongs to servers T19a; host table names are unconfirmed host facts (OQ-G10, local-testing row 5d).
B-517 merged #363 (6cfd75d) 22:24 UTC: first use of integrate.sh by the lead; local CI without mutation took 11 minutes (gate job 668 s). Merges since the B-516 push (aad1561): 1.

## 2026-11-15 22:30 UTC, lane interface-2 finished (B-181 merged earlier; B-429 and B-183 moved to lanes interface-5 and interface-4; B-489 stopped at integration)
- B-489 (I.T13b): the repair commit 80dee90 left one test signature unformatted; the gate after merge failed at the format step ST001. Tail lane `tail-489` (run wf_ed0e3c4a-91b, script <lead>/build-lane-tail.workflow.js: named repair, then the fixed integrator sequence) runs the formatter and integrates. Lesson for the playbook: a repair writer runs the whole gate without mutation, never only the tests.
- I.T7 lead findings still open: (L1, first-live-run path) the merged engine passes wait=False on every port call (engine/_approvals.py:126, _decide.py:222 and :274, _inflight.py:230) while spec 0006 4.4.5 step 2 says the run waits on the page: B-510 dealt with "waiting on the page" in the plan (check T14 covers the wait mode before launching T14); (L2) AC31 "re-renders the screen with the message" against the refusal page with a link back; (L3) stop poll 0.5 s against "every second" in spec 4.4.5.
- Process measurement: B-489's integrator waited about 1.5 hours for the integration lock. With B-516 the queue now moves at about 11 minutes per pull request.

## 2026-11-15 22:40 UTC, lane plan-fixes-2 finished (B-510 #359, B-511 #364 merged); plan tasks total now 340
- OWNER, on the path: spec 0007 Q19 (output kind of harness.host_design_verdicts: (a) wrapper kind harness.host_design_verdicts/1 accepted by the design summary, recommended; (b) calc port and contract change). Blocks W.T4b, W.T9a, W.T9b, W.T11, W.T12. Asked on 2026-11-15.
- OWNER, on the path: W.T15 (B-524) changes the protected .gate/forbidden.yml (FB005 admits version=1 of block, workflow, decision_point, rule; 10 lines); T7 waits for it. Asked on 2026-11-15.
- OWNER, later: spec 0006 Q22, Q23, Q24 (each has an interim reading in its task; Q24: an edit-cycle run whose report has exceptions cannot be signed until Q24 is answered and spec 0007 step 17 adds the exc_<n> items; reject still works).
- New ids: B-524 W.T15 (gate member eng-dev-gate, title type fix or feat so that test-first applies), B-525 W.T4b, B-526 W.T9a, B-527 W.T9b (B-203 is replaced by these two), B-528 I.T14c.
- Registry changes due at the checkpoint: B-183 drops AC42 and the sign-off title; B-188 drops AC46 and AC64; B-353 deps I.T14 -> I.T14c; B-430 drops E.T14 and E.T14b; B-432 and B-433 add W.T6; B-433 drops P.T1; B-198 retitled analysis_summary only; B-206 prTitle and branch type `test(eng-harness)`.
- Budgets that are estimates: W.T4 200, W.T4b 240, W.T9a 200, W.T9b 230, W.T11 150, W.T6 300 (doubtful). Writers measure early.
- Spec 0013 step 12 passes "basis": ...: becomes B.record_ref() with the column wave (frozen).

## 2026-11-15 22:50 UTC, lane editcycle-5 finished (B-513 #358, B-197 W.T3 #366 merged); B-500 E.T16b merged #365. Count 200 of 340. Merges since the B-516 push: 4 (#363, #364, #365, #366).
- The hashes of six merged draft calcs moved with kinds/calcs.py (B-197): owner re-verification of drafts as for any hash change (spec 0003 4.5); list them in LOCAL-TESTING at the checkpoint.
- Spec 0007: 4.4.1 and 4.4.2 name an input `state` while both calcs take flat fields (mechanical prose correction); nothing says what a wall_section item does when its name matches a slab or deck section (K2; read-back fails on the safe side): owner or documents item, later.
- expected_effects does not check that `check` belongs to the given `change_set`: the workflow (T8) supplies both; note for the T8 writer.
- Q18 (same-key terms) open; T14 must not build it.

## 2026-11-15 23:25 UTC, lane engine-4 finished (B-499 #349, B-115 #357, B-500 #365 merged; B-116 NEEDS_PLAN_AMENDMENT; B-117, B-118 skipped)
- B-116 (E.T17) written at 32e9689 (122 of 250, gate pass): needs engine/_runner.py and three collateral tests in the T17 list. Mechanical amendment B-529 written by the lead; lane engine-5 continues B-116 (review, mutation, integration held until B-529 merges), then B-117, B-118, B-521.
- integrate.sh has a hold marker now: `locks/hold.b<NNN>` makes `merge <NNN>` wait.
- B-500 findings for the Q40 answer (owner queue): a promotion resolved `applied` at a resume journals no model_saved role promoted (report lists no promoted model, about 12 lines); the backups folder is flat (two models with the same base name overwrite each other's backup; needs a spec sentence); the promote step journals no model_key (spec 4.3.2 and 4.5.3 should state it).
- B-115 findings: AC49's saves_new_file exception and the engineer-only under= rule (EC3) belong to plan 0007 T6 (B-200): until it merges any under= approval suppresses the inserted always-ask approval. T6 is therefore on the first-live-run path before any live write. Q41 and Q43 are built as the writer's recommendation (owner queue). _steps.resume_path repeats _invariants.path_key (merge them in a later task that lists both).

## 2026-11-16 00:12 UTC
- Merged: B-172 D.T8 #367, B-183 I.T9 #368 (first task merged by lane script version 3). Count 202 of 340. Merges since the B-516 push: 6.
- B-489: the tail lane could not repair it (first `test:` commit 77e9110 holds a test green at the base; TF004; pushed history). Pull request 360 closed by the lead; rebuild on branch -r2 in lane interface-6 (D-22).
- Lesson for the playbook (section 2): before the first push every writer runs the test-first check itself, not only the gate; a test added to the first `test:` commit that passes at the base costs a full rebuild.

## 2026-11-16 00:20 UTC
- Merged: B-429 I.T7b with the single-use race fix #370. Count 203 of 340. Merges since the B-516 push: 7. B-529 opened as #371 (lead-written), local CI running.
- LEAD ERRORS in lane arguments (cost: one writer agent each): (1) B-198 W.T4 launched before its dependency S.T21 (B-519, lane gaps-1): the writer returned BLOCKED with nothing written; relaunch B-198 when B-519 has merged (worktree wt/b198 exists, empty branch). (2) B-522 launched with `Risk: r1, r3` while plan 0007's set is r1, r2, r3: risk-floor RF002 failed in local CI, repaired by the lane. Before a launch: read the plan's risk set from its front matter and every `depends_on` including the prose "waits for".
- B-429 lead finding (low): with `answering`, a POST to a recorded request builds the screen only for the router to discard it before submit answers 409.
B-529 merged #371 (adc9a61) 00:29 UTC; hold on B-116 removed. Merges since the B-516 push: 8 (#363 to #368, #370, #371). Local CI gate job 652 s.

## 2026-11-16 00:40 UTC, plan audit 2 finished (1.6 million tokens, 15 minutes): servers T19a 7 confirmed, 3 rejected; providers T10a 1 confirmed, 1 rejected
- Servers T19a could not have been written: AdapterHostPort lacks the HostPort protocol methods and never reloads adapter/state.json (new T19c), no production ModelBinder exists, build_ports is given no inspector, launcher, lock folder, files, checks or allowlists, the pre-image rule raises TypeError on saves and opens and breaks four reconcile tests, one tests_first gap, budget 313 against about 420 real. Amendment B-530 (Opus writer: design choices), lane plan-fixes-3.
- Providers T10a: DecisionRuntime fields and warning type undefined. Amendment B-531.
- Cross-plan note (not confirmed, low confidence): no task of plan 0006 catches NotImplementedGap from the port builder for the exit 2 clause of spec AC43.
- After B-531: launch B-229 (P.T10a). After B-530, B-519, B-522 and B-118: T19c (new id B-532) then B-138 (S.T19a).

## 2026-11-16 00:45 UTC, lane editcycle-6 finished without a merge
- B-523 (W.T14): third rebuild for TF004 (after B-149 and B-489): a negative-control test, green at the base, sat in the first `test:` commit. Pull request 372 closed; rebuild by the tail lane rebuild-523 (byte-identical content, no second review or mutation run). Playbook section 8 item 11 and lane script version 3.1 now make the writer run the test-first check before the first push.
- B-523 lead findings: plan 0007 T14 prose names only the change_set_check hash, but the expected_effects hash moves too (import closure): prose touch-up; spec 0007 4.4.1 does not set the order of issues within one item (INVALID_ITEM_ID first is pinned by two golden cases).

## 2026-11-16 01:05 UTC, lane decisions-1 finished (B-171 #361, B-172 #367, B-173 D.T9 #373 merged)
- Decisions plan risk set is [r1, r3] (the plan wins over the prompt).
- T10 (B-174) must pass max_concurrent_decisions from EngineSettings when it builds the Cascade; Cascade satisfies DecisionPort only after T10 adds runtime_summary.
- Spec 0005 open points decided by writers and tested (state them at the next documents amendment): 4.8 batch timeout is the largest timeout_ms_model, a yes/no point is never batched, the batch id hashes the sorted request ids joined by newline, a refused answer set returns stored outcomes for resolved calls; 4.5 a call with an engineer_choice and no stored request consults no provider; the recorded error form `ProviderError:<code>` and the `error` key missing from the entry shape of 4.9; 4.10/4.11 the label stores the outgoing state while state_sha256 is of the full state (AC30, AC35). Q16 (paths on a skipped_redaction entry) open, interim reading applied.

## 2026-11-16 01:15 UTC, measured numbers after ten merges under the new settings (B-516 pushed 22:09 UTC as aad1561)
- Ten pull requests merged in 2 h 54 min (22:09 to 01:03): seven plan tasks (B-500, B-197, B-172, B-183, B-429, B-522, B-173) and three documents amendments (B-517, B-511, B-529). Count 205 of 340. Rate 2.4 tasks per hour, 3.4 pull requests per hour.
- Tokens, lanes on script version 3 (62 agents so far): 7.5 million fresh, 113 million cache-read. A complete task costs 0.55 to 0.9 million fresh tokens (B-183 0.88, B-522 0.80 with one repair, B-518 0.57 before its repair) against 1.9 million per merged pull request before. Integrator 0.15 million per run (0.40 before). Writers hold 55 of the 113 million cache-read tokens: long writer sessions are the next cost to cut.
- Failures in the period and their cost: three TF004 rebuilds (B-489, B-523; rule added), two lead launch errors (B-198 dependency, B-522 risk line), one budget overrun found only after writing (B-204, 451 against 380: split B-533), one merge conflict (B-518, repair running).
- B-204 (W.T10) NEEDS_PLAN_AMENDMENT: split into T10 and T10b by B-533 (lane plan-fixes-4).
- Periodic full gate with mutation started on build/v1 at 995d893.

## 2026-11-16 01:20 UTC, the periodic run and what the mutation step really covers
- `eng-gate check --all` on build/v1 at 995d893 passed in 12 minutes, but its mutation step mutated nothing: the step mutates the R1 and R2 modules changed against the merge base with origin/build/v1, and on build/v1 itself that set is empty. The lead's first "full run" therefore proved the tests, not the mutation score. Corrected: <lead>/tools/periodic-mutation.sh <base> runs the mutation step with a pull-request event whose base is the previous periodic commit (first run: base aad1561, head 995d893, in progress).
- Per-change mutation in the lanes (gate runner, in the task worktree) was always real: there the merge base is the task's base.
- Measured gate-job seconds of local CI: code pull requests with mutation 1184 to 2127 (B-171, B-199, B-149, B-115); documents pull requests 690 to 770; after B-516 every pull request 580 to 670.

## 2026-11-16 01:25 UTC: B-489 I.T13b merged #374 (rebuild). Count 206 of 340. Low finding: test_status_decision_runtime_caps tests the depth cap only on the omitted side.

## 2026-11-16 01:35 UTC, lane editcycle-7 finished: B-204 (split, B-533) and B-200 (one collateral test file, B-535) both written and pushed, neither merged yet
- B-200 (W.T6) at fca68e6: 259 of 300, test-first pass; needs tests/workflow/test_modes.py in the list: lead-written mechanical amendment B-535 (in the queue), lane editcycle-8 continues (review, mutation, integration held).
- B-200 writer concerns for the documents queue: EC5's `p~post.save` clause has nothing to attach to in the merged engine (not built, no test: the reviewer decides whether a criterion is uncovered); a tool save whose integrity check fails raises after step_completed and a replay does not raise again; a save reconciled applied in-process journals no model_saved until the next resume; csi_open_revision (effect write, action open) keeps its approve_each_write preview (EC6 names action save only); the resume `describe` call is limited to a latest write with action save or open because replay tests pin the port-call list.

## 2026-11-16 01:50 UTC: merged B-116 E.T17 #375 and B-523 W.T14 #376 (rebuild by the tail lane: 0.19 million tokens, two agents). Count 208 of 340. Merges since the periodic checkpoint 995d893: 3 (#374, #375, #376).
- The periodic mutation run (base aad1561) uses four mutmut workers at nice 10: load 6 on four cores while it runs. If a local CI run fails on a load-sensitive test while it runs, stop it and rerun it when the queue is short.

## 2026-11-16 01:57 UTC: periodic mutation run PASS (base aad1561, head 995d893, 40 minutes, all six members; log logs/periodic-mutation-995d893.log). Next periodic run: base 995d893, due after ten merges counted from it (three so far: #374, #375, #376).

## 2026-11-16 02:30 UTC, lane plan-fixes-4 finished (B-533 merged #379: T10 split into T10 and T10b)
- ON THE PATH, no task wires report/cycle-timings.json: spec 0007 4.9 says the report also writes it and LOCAL-TESTING tells the owner to collect it for the B-1 sheet, but write_cycle_timings has no caller and plan 0006 T14 calls write_report only. Add it to plan 0006 T14 (or a new small task) in the documents item that precedes the T14 launch.
- Stale cross-references naming T10 for count_prompts: spec 0010 line 49, plan 0010 line 449, LOCAL-TESTING line 517 (should read T10 and T10b): mechanical, at the checkpoint.
- T11 still lists pyproject.toml for a public_modules entry that exists at the base (its r3 risk from that file would go): mechanical.
- OWNER QUEUE (interim readings stated in spec 0007 4.9): (a) the A7 prompt counter does not count a decision request still open at the end of the journal, nor approvals answered by a mode caller; (b) machine time per cycle excludes scope steps and engineer steps, which differs from the run-level machine time of spec 0006 AC56 (sum of every completed step): the report shows two machine figures with different rules: which one is the B-1 figure?

## 2026-11-16 02:35 UTC: merged B-531 #377 (providers documents), B-518 I.T9b #378, B-533 #379. Count 209 of 340. Merges since the periodic checkpoint 995d893: 6 (#374 to #379).

## 2026-11-16 02:43 UTC: B-535 merged #380 (4c4be4d), hold on B-200 removed. Merges since the periodic checkpoint 995d893: 7.
