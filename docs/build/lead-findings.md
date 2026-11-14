<!-- The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text. -->

**Status of this copy:** the lead findings queue of the cloud session of 2026-11-14 (work item B-487), kept for the next lead and for the next engine and plan amendments. BUILD-STATUS section 6 holds the owner questions; this file holds the full list. `reports/b<NNN>-*.md` files it names lived in `<lead>/reports/` and are not kept.

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
