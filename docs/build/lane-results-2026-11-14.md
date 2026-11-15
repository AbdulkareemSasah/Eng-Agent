<!-- The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text. -->

**Status of this copy:** results and lead findings returned by the lanes that the usage limit stopped on 2026-11-14 (source for work items B-501 to B-503).


# Lane servers-2

## B-465 DOC.ST12 -> MERGED 310
**concerns:** 1. I added products/__init__.py to T12b's files, beyond the module the lead named. `ProductProfile` only carries `tables`, so the read-back columns can only reach `_checks.py` through the profile, which lives in that file. Drop it if the lead prefers `_checks.py` to import `_etabs` directly.
2. The T12b prose says where the warnings go: `take_warnings()` is drained into the `check_model` envelope, because that is the only envelope HostPort returns. This is close to a design choice; the lead should confirm it.
3. T12 grows past the lead's list: the wall-thickness fingerprint work (item 4, L2) adds `_state.py`, products/_etabs.py and test_csi_state.py to T12, because T12 has room in its budget and T12b is near the 380 cap. T12 covers only AC25 and AC26, and AC27 is still covered by T11 and T11b. B-131 must add this work, and the `_toolport.py` binder change, to its branch, with a new test for the wall edit in test_csi_state.py; I did not change its tests_first.
4. T12b's budget of 375 is tight. The `_checks.py` draft was never run or tested, and T12b also holds the saved-fingerprint, `wrote`/`take_warnings` and product-table work. If it overruns, the saved fingerprint (L3) could move to T19, which needs `_hostport.py`, `_identity.py` and test_csi_session_ops.py added and its budget of 200 raised.
5. The T12b prose records the tolerance delivery as an open owner question. T12b (B-466) cannot finish check_model's quantity comparison until question A is answered, or the lead accepts the recommendation as a draft decision.
6. I kept pyproject.toml and `_allowlist.toml` in T12's files even though the B-131 writer found them unnecessary, so the existing shared-file entry for `_allowlist.toml` (T12, T13, T15) stays true.

- L1 owner question: how the read-back tolerance is delivered. The documents name the field (spec 0002 sections 4.5.8, 5 and 11 G-2; spec 0007 section 4.8 renames it checks.readback_relative_tolerance_ratio, Q12). They do not say how the value reaches check_model(model_key): the engine HostPort signature takes only model_key, and spec 0003 section 4.4 covers only calcs. Recommendation: T19 hands the frozen basis value to AdapterHostPort when it wires the port for a run. While the value is absent, quantities are READBACK_UNAVAILABLE. The engine port signature does not change. The lead also has to decide whether B-466 starts before the owner answers.
- L2 owner question: combination factors. Spec 0002 section 5 makes scale_ratio a ref-capable engineering quantity, so references are required under require_refs (section 4.5.1). Contract section 5 resolves references per field, and contract section 4.10.2 puts scale_ratio inside the combination items. The documents therefore do not settle it. Recommendation: the factors come from the change-set result as one reference for the combination's items, not as a literal per item. Until that is decided, B-131's literal scale_ratio stays and is listed in the T12 pull request.
- L3: the plan prose says 'an owner question (B-465)' twice with no owner-queue id. Give both an id in BUILD-STATUS section 6 and refer to it from the plan.
- L4: T13 takes the T11 mapper fix (B-451 L1) and keeps its budget of 300. The fix is small, but measure it at T13.
- L5: B-131 picks up the new _toolport.py and _state.py work on its existing branch. Its 301 measured lines remain the base of T12's 340.
- L6: the gate checks were run on a synthetic event: gate-check awaiting-owner (only AW03 and AW08, no GC005, GC008, GC009 or GC016 finding), test-first skipped (docs exempt), risk-floor pass.
- L6: T12's budget of 340 is about 13 percent over its recorded estimate of about 300. The lead asked for about 10 percent (about 330). It is within the 380 cap and is left as is.
- L7: the T12b prose quotes `checks.readback_relative_tolerance` as spec 4.5.8 reads today. B-467 (the basis rename to the spec 0007 4.8 names) must update this quotation too. B-466 is held by playbook 5d until both B-464 and B-467 are merged.
- L8: the writer's Q-C (which result reports the drained MODEL_CHANGED_OUTSIDE warnings; recommendation: the step result of the model_state read that found them) should join round 1's L1 (how the read-back tolerance is delivered) and L2 (combination factors) in the BUILD-STATUS section 6 owner queue with ids. Round 1's L3 still applies: the plan says 'an owner question (B-465)' and 'a lead question (B-465)' without ids.
- Round 1's L1 to L5 stand.
- L9 (low): the edit builder signature (model, descriptor, binding) carries no op_id. So the written-items book can match prepare (called in the wrapped builder) with commit (called in CsiToolPort.call) only by call order or by a context variable. This is harmless while writes to one model run one at a time, but B-466 should state the pairing in its tests.
- L1 to L8 from rounds 1 and 2 stand. Three owner questions still need owner-queue ids in BUILD-STATUS section 6: how the read-back tolerance reaches check_model, whether combination factors may be literals or must be references, and which result reports the drained MODEL_CHANGED_OUTSIDE warnings (writer's Q-C). The plan prose cites them only as '(B-465)'.

## B-131 S.T12 -> MERGED 314
**concerns:** 1) The registry prTitle still reads 'edit kinds, read-back helpers and check_model', but read-back and check_model are T12b (B-466) and are not in this change; the integrator's PR body should say so. 2) The gate prints a notice that is not from this change: RT001 tools/eng-dev-gate noqa count fell from 19 to 18 (drift on the base; I did not touch that ratchet entry). 3) Combination factors (scale_ratio) remain literals inside the contract's CombinationItem, per the plan's interim reading of the open B-465 owner question. 4) The wall-section table key is unconfirmed until the first local run (OQ-G10). 5) Mutation score not measured.

- The registry prTitle still names 'read-back helpers and check_model', which belong to T12b (B-466). The writer kept the registry branch and prTitle. The PR body must say that this change is T12 as amended by B-465 and the rest is B-466, or the lead adjusts the title.
- The combination factors (scale_ratio) stay literals inside the contract's CombinationItem. This is the open B-465 owner question. The change follows the plan's interim reading and invents nothing.
- The wall_sections table key ('Wall Property Definitions - Specified') is unconfirmed until the first local run (OQ-G10). It also adds one csi_db_table_read to every state read.
- The spec 4.6.2 check 'the section must exist (checked against the state)' is not in this change. Spec 0007 line 306 (step 3 model state) owns it, so there is no gap here.
- Mutation was not run (skipped as instructed). The full gate (playbook section 4) must run before integration. origin/build/v1 has moved to f0040d7 (B-228) since the merge base ef5d883; git merge-tree says the merge is clean.
- Notice already on the base, not caused by this change: RT001 tools/eng-dev-gate noqa count fell from 19 to 18 (the ratchet asks for `ratchet --update`).

## B-466 S.T12b -> MERGED 327
**concerns:** 1. The engine ignores the check result. Guard.check in engine/_invariants.py raises ModelIntegrityError only for a FailureEnvelope, so a success envelope with summary.clean false clears the dirty flag. The spec makes the mismatch an issue in the result, so this adapter returns it that way. Until the engine reads summary.clean, a READBACK_MISMATCH does not stop a run. This is an engine finding and I did not fix it.
2. _replies.load_set (a T11 file, T13's to fix) types every combination item load_pattern and drops the host kind. A combination that names another combination (which csi_add_load_combo can write) makes the next state read fail with UNEXPECTED_REPLY (LoadSet unknown pattern). The combination read-back therefore compares item names and factors only. COMBO_REFERENCE_MISSING can fire only for a load_combination item naming a missing combination, and load_case items are not checked.
3. Tolerance delivery follows the OQ-Q65 recommendation and is not an owner answer. T19 must pass ReadBack(tolerance_ratio=<frozen basis value>) to AdapterHostPort, and the same WrittenItems plus host.wrote to CsiToolPort. The port does not enforce the basis bound of > 0.
4. CsiToolPort's written and wrote arguments are optional. test_csi_steps.py, a T12 test outside this task's files, builds the port without them and is unchanged. A port made without them records into a book nobody reads, so T19 must wire them.
5. take_warnings is global, so a warning for another model rides on this model's check, with its model key in the message. The destination recommended in OQ-Q67 (the model_state step result) is a later task.
6. The written-items book is in memory only. After a crash or resume it is empty, and a write with an unknown outcome is not committed. Both belong to T14 reconciliation and T19.
7. Table keys, the columns UniqueName, Section, Name and Thickness (read in the model's present units), and the combination read-back shape are unconfirmed (OQ-G10). A table or column that is not as assumed gives READBACK_UNAVAILABLE, not a mismatch. No docs/local-testing.md row was added because that file is not in the task's files list, so the lead should place the OQ-G10 row.
8. The margin is 2 lines (378 of 380), so any review fix that adds source lines needs a matching trim.
9. check_model re-reads the whole model state (about 15 host calls) plus two lists and two tables. That is fine on the fake and needs measuring at the first local run.

- The engine ignores summary.clean: engine/_invariants.py Guard.check raises ModelIntegrityError only for a FailureEnvelope or a ContractError. It clears the dirty flag for any success envelope, so a READBACK_MISMATCH does not stop a run (spec 0001 invariant 1). This needs an engine plan task and is not in lead-findings.md.
- Tolerance delivery (OQ-Q65) follows the queue recommendation, not an owner answer. T19 must wire ReadBack(tolerance_ratio=<frozen basis value checks.readback_relative_tolerance_ratio>) into AdapterHostPort(readback=...) and pass the same WrittenItems and host.wrote to CsiToolPort. The port does not enforce the basis bound > 0.
- take_warnings() is global, so check_model of one model drains and reports another model's MODEL_CHANGED_OUTSIDE warnings (OQ-Q67, where the drained warnings should go).
- The combination read-back compares item names and factors but not the item kind, because the T11 mapper _replies.load_set drops the host kind. That file belongs to T13, which should fix the mapper and then add the kind to the read-back.
- _hostport.py:121 calls the private CsiStateReader._rows. A public reader method needs _state.py, which is outside the T12b files (later task or amendment).
- A wanted value of zero is compared exactly, because spec 4.5.8 defines only a relative ratio with no absolute floor. A host round-off on a written zero would therefore be a mismatch (conservative). Spec question.
- The written-items book is in memory, so it is lost on resume, and writes with an unknown outcome are not committed. That is T14 reconciliation and T19 wiring.
- Round 1 lead findings 1 to 7 stand. Read 'T19' in them as T19a (B-475): the engine Guard.check ignores summary.clean; tolerance delivery follows the OQ-Q65 recommendation, not an owner answer; take_warnings() is global (OQ-Q67); the combination item kind is not compared (T13 _replies mapper); _hostport.py calls the private CsiStateReader._rows; a zero wanted quantity is compared exactly; the book is in memory only (T14, T19a).
- New: check_model reads the written items after two awaited host reads. A write running at the same time on the same model would be compared against a snapshot taken before it. The engine runs one step at a time per model, so this cannot happen today. Any future concurrent use of one model's port must keep that order.
- origin/build/v1 has moved past the merge base by B-481 and B-475. Both are documents only and nothing in them affects T12b. The integrator must merge origin/build/v1 before pushing.

## B-132 S.T13 -> MERGED 334
**concerns:** 1. AC28's "after the engine's save" is shown only through the descriptor's `action` of `analysis` or `design`, which triggers the engine's save-first invariant (engine AC43). The end-to-end run through the real engine is T19a's.
2. The reply field names of the three results tools, `csi_design_results` and `csi_analysis_messages` are my choice, flagged OQ-G10. The inventory gives input schemas only. The status and run shapes (`{cases:[{case,status_code}]}` and `{started:true}`) come from the S-02 spike. The first local run must confirm all of them. `docs/local-testing.md` is outside T13's files, so I added no row; the handoff note lists the names.
3. `CSI_KINDS` is not in the run's `KindRegistry`. `_kinds.py` is outside T13's files, and the status kind was never registered either. T19a must extend the registry with `CSI_KINDS`, or storing an analysis result is refused. My test overrides the `store` fixture the same way.
4. `ANALYSIS_MESSAGES` is a constant in `products/_etabs.py` and not a `TABLES` entry, because `test_csi_state.py` pins that every profile table is read by the state reader. `analysis_messages` has no caller yet; plan 0007 T5 (`csi_read_analysis_messages`) will compose it. The profile class (`products/__init__.py`) is outside T13's list, so T5 imports the constant or adds the field.
5. Mutation was not run. I wrote tests for the boundaries I could foresee and expect at least 80 percent, but have no measurement.
6. `csi_design_run` with aluminum or coldformed is sent to the host as a ledgered write, and the host's `unsupported_by_version` maps to `NOT_SUPPORTED_BY_VERSION`. Refusing locally before the send is possible if the lead prefers.
7. The handoff note is <lead>/reports/b132-writer.md. The gate log is <lead>/logs/b132-gate.log.

- CSI_KINDS is not in the run's KindRegistry (_kinds.py is outside T13). test_csi_analysis.py extends the store by hand. T19a, which wires the ports, must add CSI_KINDS, or a stored analysis or design result is refused.
- csi_design_run does not call wrote(). Steel design with auto-select sections can change frame sections, and the next state read would then report MODEL_CHANGED_OUTSIDE for a change the adapter's own run made. Spec 4.6.4 and design 04 section 3.4 do not say whether a design run counts as an adapter write. This needs a spec decision (T14 or an amendment).
- analysis_messages() and products/_etabs.ANALYSIS_MESSAGES have no source caller yet. Plan 0007 T5 composes them over csi_db_table_read, and the profile has no table field for them (products/__init__.py is outside T13).
- The reply field names of the results tools are the writer's choice, because the S-12 inventory gives only input schemas (OQ-G10). T17's contract and fidelity tests and the first local run must confirm them.
- AC28's 'after the engine's save' is shown through ToolInfo.action ('analysis'/'design', which engine invariant 7 keys on) and the long-role routing. The save itself is proven by engine AC43 and, end to end, by T19a.
- CSI_KINDS is not in the run's KindRegistry (_kinds.py is outside T13). T19a, which wires the ports, must add it, or a stored analysis or design result is refused.
- csi_design_run does not call wrote. A steel design with auto-select sections can change frame sections, and the next state read would then report MODEL_CHANGED_OUTSIDE. Spec 4.6.4 and design 04 section 3.4 do not say whether a design run counts as an adapter write, so this needs a spec decision (T14 or an amendment).
- analysis_messages and ANALYSIS_MESSAGES have no caller in the source yet. Plan 0007 T5 composes them over csi_db_table_read, and the profile has no field for the table key.
- The reply field names of the results tools are the writer's choice (OQ-G10, now recorded in local-testing item 5c). T17's contract and fidelity tests and the first local run must confirm them.
- origin/build/v1 has moved two documents-only commits past the merge base (B-476, B-483). Neither touches T13's files and the merge is clean. The integrator merges them in as usual.

## B-133 S.T14 -> MERGED 339
**concerns:** 1. Pre-image provider (needs T19a or a spec sentence). `ModelBinder.binding(host_key, model, descriptor)` receives no call arguments, so a binder cannot point `Binding.pre_image_ref` at one object. Spec 4.5.7 only says "the last model-state read of the object". I defined the contract that `reconcile` reads: the ref resolves to the `observed` value of a `read_back` taken before the write, either a dict or null for an object that was absent. Until the T19a wiring supplies it, a setter whose state still equals the old state reconciles `unknown` (never a wrong `not_applied`). A combination that is absent with no pre-image is also `unknown`. I did not read the pre-image fresh before every write, because that costs about 23 host reads per write. The lead may want the spec sentence made precise.
2. `preview` is not implemented. The `ToolPort` protocol in `ports.py` has no `preview` (engine plan T15, B-388 adds it) and `ports.py` is outside this task's files. Nothing consumes it yet.
3. Wiring is left to T19a. `CsiToolPort` passes `reconciler=` through its `**wiring`, so T19a must build `CsiReconciler(product="ETABS", tolerance_ratio=ReadBack.tolerance_ratio)` and pass it. Without a reconciler no tool supports reconcile and the engine asks the engineer.
4. Not reachable here. `csi_save_model` is `HostPort.save` and `csi_unlock_model` belongs to T15. Neither is in `tool_allowlist()`, so `supports_reconcile` is false for them. The Sasaah audit-log lines are not read as evidence because no audit-log reader exists in the adapter.
5. A reconcile read that fails with anything other than a timeout is raised as `ContractError`, and the host stays wedged. A returned `unknown` frees the host.
6. `reconcile` reads references with the revision untracked. The write itself raised the model's revision, so a reference made earlier would otherwise be `REF_STALE` exactly when its write was applied.
7. Mutation score was not measured. Mutation was skipped by instruction, but the tests were written for it.

- Plan 0002 T14 names `preview`, but ToolPort in ports.py (outside T14 files) has no preview until engine plan T15 (B-388). The plan should move the CSI preview to a later task.
- Spec 0002 §4.5.7 evidence includes 'the Sasaah audit-log lines for the op, if any'. There is no reader, no line format and no way to match an op to its lines, and the fake writes no audit log. The spec should define these or record the gap. The module docstring says this part is not done.
- Binding.pre_image_ref: the spec says only 'the last model-state read of the object (state cache)'. The writer chose this contract: the ref resolves to the `observed` value of a read_back taken before the write. No binder sets it until T19a, so until then a setter whose write was not applied reconciles as 'unknown'. That is safe, but the spec sentence should be made precise and T19a should wire it.
- reconcile and read_back resolve references with an untracked revision (_toolport.py:55), because the write itself raised the revision. This is sound for reconcile. T19a should not rely on read_back to catch stale references.

## B-135 S.T16 -> INTEGRATOR_DIED 
- Spec 4.7 and section 6 call BUILD_CHANGED a harness code raised as ToolFailed, but HarnessCode in errors.py (outside T16 files) has no such member. The adapter uses HOST_ERROR with host_code BUILD_CHANGED (LAUNCH_FAILED likewise). Amend the spec wording or add the HarnessCode member in a later task.
- Spec 4.7 puts the attempt folder at run_dir/tools/<step path>/<attempt>, but ToolPort.call gives only op_id, so the adapter uses run_dir/tools/<op_id>. The spec should say so.
- The script parameter names -Dxf and -Config, and harness.file_input/1 references as inputs, are not in the spec. Confirm the names in the live check and bring the references with the input-file registry task. The AC31 clause 'the step is journaled' is only exercised by T19b.

## B-136 S.T17 -> SKIPPED_DEPENDENCY 

# Lane amendments-zt5-gt2

## B-461 DOC.ZT5 -> MERGED 306
**concerns:** The numstat of the commit is 4 added and 1 deleted lines, all in the plan document. A documents amendment has no line budget to check, so 5 is the raw count. The RT001 ratchet notice comes from the base branch, not from this change, so I left it alone. I did not write <lead>/reports/b461-writer.md. Q11 still offers the alternative of amending plan 0002 PK-AC3. I left that sentence as it was.

- Low, non-blocking: packages/structural-codes/docs/plans/0004-aci318-14-column-checks.md line 172 (T5 prose) names only plan 0002's test_pack.py; the Q11 row (line 255) now names the other two tests. No contradiction, but the T5 prose could point to Q11 for them.

## B-334 Z.T5 -> REPAIR_NEEDS_PLAN_AMENDMENT 
**detail.summary:** The CI failure cannot be fixed inside T5's file list. test_allowlist_holds_the_footing_and_column_ids (packages/eng-harness/tests/unit/calcs/test_code_pack_route.py, line 283) asserts set(FOOTING_CHECK_IDS) == the aci318_14 ids from Registry.discover(). T5 registers three column checks, so the registry now holds nine ids and the assertion fails. The harness allowlist module (_code_packs.py) already holds COLUMN_CHECK_IDS and needs no change. The same scope change was approved for plan 0002's test_pack.py (six to nine), so this is not a weakened expectation. Trial result: I changed line 283 to `set(FOOTING_CHECK_IDS) | set(COLUMN_CHECK_IDS) == registered` as an uncommitted edit, and `uv run eng-gate check --package eng-harness --skip mutation` gave `check: pass`. I then reverted the edit. No other package calls Registry.discover. The test file is the only file the trial touched (1 line added, 1 removed, 0 counted lines). The worktree <worktrees>/b334 is clean at 256b232 with no new commit. The earlier fix to the writer report's counted-lines line is already in place (15 of 80). I appended a repair note to <lead>/reports/b334-writer.md.

**detail.proposed_amendment:** Add packages/eng-harness/tests/unit/calcs/test_code_pack_route.py to the files of T5 in packages/structural-codes/docs/plans/0004-aci318-14-column-checks.md. Add it as a comment line in the style of amendment B-461: "these tests pin the number of registered checks". The edit is line 283 of test_allowlist_holds_the_footing_and_column_ids, changed from `assert set(FOOTING_CHECK_IDS) == registered  # the six ACI footing checks, one each` to `assert set(FOOTING_CHECK_IDS) | set(COLUMN_CHECK_IDS) == registered  # six footing and three column checks, one each`. max_changed_lines stays 80, because test files are not counted. Once that amendment is on origin/build/v1, a writer applies the one-line edit, commits it as a test commit with the (B-334) suffix, runs the eng-harness and aci318-14 member gates with --skip mutation, and the integrator reruns local CI.

**detail.concerns:** The head is still 256b232, so PR 331 stays red until the amendment merges and the test edit lands. No source file changes. The mutation, gate and CI results for the aci318-14 member are unchanged from the earlier passes.

- CK-AC3 (plan 0004 section 3) lists the allowed citation origins without 'Mechanics of materials'. tests/unit/test_pack_columns.py:32 accepts that prefix, which is covered by 'names a physical bound' and is already allowed in test_pack.py:35. Suggest naming it in CK-AC3 in the next documents change. Low, does not block.
- CK-AC8 mutation evidence is still open: this round's gate ran with --skip mutation. Because of MU003 (OQ-Q57) the @check bodies of the three column checks get no mutants. The full gate (playbook section 4) is still needed before integration.
- CK-AC3 (plan 0004 section 3) lists the allowed Cited prefixes as 'ACI 318-14 ', 'SI prefix', 'Statics', 'Geometry', 'Numerical method' or 'names a physical bound'. test_pack_columns.py, like test_pack.py, also allows 'Mechanics of materials'. The modules use it for the physical bound 'a strength is positive' and for the b*h^2/6 and b*h^3/12 denominators, which were merged earlier in B-330. Adding 'Mechanics of materials' to the CK-AC3 list would make the criterion match the test word for word. This does not block the change.
- CK-AC4 says 'one column section evaluated by the three checks with the hand-check inputs'. The test uses HC-1 of each case file. That is the same 500 x 500 section with Ast 4000 mm2, but the demands differ: Pu 3000 kN for max axial against Pu 1500 kN with Mu 300 kN.m for axial-flexure, and the limits check takes Ag only. The criterion could be reworded to 'the HC-1 inputs of each case file'. Non-blocking.

## B-462 DOC.GT2b -> MERGED 336
**concerns:** 1. Not run: the documents gate-check (GC rules) needs the pull request's context, so it has not run locally. Local CI will run it.
2. The T1 prose in plan 0013 still says the kinds are registered "beside the edit-cycle kinds", but T1 is merged without `_kinds.py`. I did not edit that sentence; the new T2 sentence records that T2 now does the registration.
3. The B-281 branch still uses the old basis field name `compare.length`. Under playbook 5d the binding name is `compare.length_mm`, so the B-281 writer has to rename it when finishing that branch. This is not part of B-462.

- When the B-281 writer finishes on top of this amendment, they must also apply the B-484 rename (compare.length -> compare.length_mm, playbook 5d). Their handoff note still uses the old name. This does not affect the budget.
- Not run here: the full gate-check, because it needs the base checkout's gate with its own environment as --gate-root. Local CI must cover it. What did run here: front matter parse with the gate's parsers (T2 has 345 lines and 13 files, under the 400 cap), and eng-gate risk-floor, which gives pass. For a spec-and-plan pull request the recorded set is the documents' risk [r1,r2,r3] and the body Risk: r0 line is not compared (risk_floor.py), which matches the earlier documents pull requests.
- GC010: plans 0003 and 0013 do not both change here, because plan 0003 needs no change. Only spec 0003 and plan 0013 change, and the gate allows several specs and plans in one documents pull request.

## B-281 G.T2 -> INTEGRATOR_DIED 
- Spec conflict: spec 0013 section 6 says 'basis field missing -> CalcRefused'. Spec 0003 section 6, which 4.4 says every calc follows, and the merged model_diff use INVALID_ARGUMENT. The code follows spec 0003. Align spec 0013 section 6 in a documents change.
- The four owner points of the verification record: (1) stories known from the frames read: a faithful reading, since 4.4.1 has no model.stories/1 input; (2) a column without a story, or whose section is not in the sections, is INVALID_ARGUMENT: defensible, because the kind requires a story and has only the three L1 issue codes, but the spec is silent, so it goes to the owner; (3) the scope read from the answer fields frames/select: faithful (spec 4.3, engine AC61, same shape as T1b), not an owner point; (4) text sort by name: faithful, since AC5 needs a canonical order and the spec fixes none. Owner queue: points 1, 2 and 4, plus calc id harness.column_select v1, hash f7b81a359e8dd186b1dd118180a13d6339dda26fb64f342ed5952f0d57691d49 (R1, draft).
- The calc keeps private copies of the T1 selection models (_Column, _Excluded, _Issue) because those names are private in kinds/column_design.py. A test validates the body against ColumnSelection, so they cannot drift silently. A later T1 follow-up could make them public, as kinds.footing does.
- Commits 61a3df6..1a67bbb carry Co-Authored-By and Claude-Session trailers that name a model, against D-3. Playbook 5c says they are not rewritten. The integrator's squash commit message must carry only Assisted-by: anthropic/claude.
- origin/build/v1 has moved to 57fe7b5 (B-492, documents only) since the merge base 6ac7159. The integrator merges it. The mutation step has not run; the full gate (playbook section 4) must run it.
- Spec 0003 section 6 has no row for a basis field in the wrong unit. The merged calcs disagree: model_diff raises INVALID_ARGUMENT and footing_subjects raises UNIT_MISMATCH. This change follows footing_subjects and raises UNIT_MISMATCH. Since B-464 the contract already refuses a non-mm compare.length_mm when it parses the basis, so this check in the calc is only a second line of defence. Spec 0003 section 6 should name one code for this case (low).
- Still open from round 1: spec 0013 section 6 says a missing basis field gives CalcRefused, but spec 0003 section 6 says INVALID_ARGUMENT. The code follows spec 0003. Align spec 0013 section 6 in a documents change.
- Open points of the verification record. Point 1 (stories come from the frames read) is faithful: the input list of spec 0013 4.4.1 has no model.stories/1, even though the contract defines that kind, so the owner may add it as an input later. Point 2 (a column without a story, or whose section is not in the sections, is INVALID_ARGUMENT) has a source in spec 0003 section 6, but spec 0013 does not cover the case, so the owner should confirm it. Point 3 (scope read from the answer fields frames and select) is faithful to spec 0013 4.3 and does not need the owner. Point 4 (sort by name as plain text) is faithful: no source fixes an order, and AC5 only needs a fixed one.
- No new spec defect from the oracle lens. On the four open points in the verification record I agree with review round 1. Points 1 (known stories come from the frames read) and 2 (a column without a story, or with a section missing from the sections, is INVALID_ARGUMENT) are defensible readings of a silent spec and go to the owner. Point 3 (scope read from the stored answer fields frames and select) and point 4 (sort by name as plain text) are faithful readings of spec 0013 4.3 and AC5.

## B-282 G.T3 -> SKIPPED_DEPENDENCY 

## B-283 G.T4 -> SKIPPED_DEPENDENCY 

# Lane tasklog-docs

## B-476 DOC.ADR34A -> MERGED 328
**concerns:** 1. **The Arabic appendix is incomplete.** The lead notes ask for the owner's words "exactly as the brief gives them", but the brief has only one Arabic phrase, "انا متناقض". The originals of answers 1 to 16 are not in the brief or in any lead file (I searched <lead> and the build records for Arabic text). Brief 7.3 item 7 says the lead supplies them. The appendix says they will be added from the lead's session record before the owner accepts the ADR. I did not translate anything back into Arabic. The lead must provide the text before this goes to the owner.
2. **I did not use the repository's GitHub name.** design/ files say "the private workspace repository (`eng-platform`, this repository)" instead of the brief's `owner/repo` name, to keep the owner's login out of the hub (hub rule 6; 07 §4 forbids usernames). The ADR does cite lead decisions D-4, D-32, D-33 and OQ-Q50 as build records.
3. **Codes and gate commands that do not exist yet.** GC017, PB001 to PB003, and the gate commands `push-scope`, `tasklog-lint` and `publish-check` are named in the ADR and hub documents as planned; the gate amendment will define them. I left the PS codes out of hub documents.
4. **The golden rules now differ from the AGENTS template until PR B merges.** process/README golden rules 4 and 7 no longer match AGENTS.template §4. process/README.md also says the template is re-rendered "in the same change" as a process change, which the PR A / PR B split goes against. Under hub rule 7, the PR body must list the five repositories to regenerate (workspace root, eng-contract, structural-codes, eng-harness, tools/eng-dev-gate) and say PR B does it.
5. **Owner review is needed.** Every changed file is a protected path (AW02), design/AGENTS.md included. Its rule 6 change is the owner-decided D8 sentence.
6. **Two small additions beyond the 2.1 table**, made for consistency: a `duplicate`/`defect` outcome line in the issue-gap template, and row 14 in the Arabic overview's table of decisions waiting for the owner, asking him to accept ADR-0034.

- The Arabic appendix holds only 'انا متناقض'. The originals of answers 1-16 are not in the brief (brief 7.3 item 7). The lead must supply them before the owner accepts the ADR; ADR line 348 says so.
- Between PR A and PR B, hub text points to texts that do not exist yet: process/08 §1 and A25 (the workspace-root AGENTS.md §3 and root rules), process/04 §3 and §8, and golden rules 4 and 7, which now differ from the rendered AGENTS.md. process/README.md line 59 also says every package is re-rendered 'in the same change'. Read literally, A25 forbids the lead's D-4 pushes during that window. Merge PR B right after PR A, and list the five repositories to regenerate in PR A's body (hub rule 7).
- The hub now names GC017, PB001-PB003, push-scope, tasklog-lint and publish-check before the gate amendment defines them. The gate spec amendment must use exactly these names.
- Gap in the brief: A23 forbids editing a task-log record other than through the task-log tool. In the interim, though, the agent writes STORY.md by hand, and the withholding fix also edits it by hand. The rule text in brief 2.3, which PR B renders, should exempt the interim template procedure.
- Gap in the brief: a hard-flagged commit that touches tasklog/ (a deletion, a POLICY.json edit, a mixed commit) has no clean way to be reverted. GC017 refuses a revert pull request. A direct revert is neither log-only nor in the bookkeeping allowance, so the check flags it again. D5 or the gate amendment needs a recorded path for this case.
- Checked: the pull request body line should be 'Plan-Task: none (hub documents)'. Gate spec 0001 §4.5 accepts that reason when every file is under design/, and all 24 files are. The risk line is r0. Owner review is required (AW02, protected design/ paths).
- Arabic appendix holds only the one quote; the Arabic originals of answers 1 to 16 are not in the brief (brief 7.3 item 7). The lead supplies them before the owner accepts the ADR.
- Between PR A and PR B the hub refers to texts that do not exist yet (workspace-root AGENTS.md section 3, root rules, golden rules 4 and 7 vs the rendered AGENTS.md, process/README 're-rendered in the same change'). Merge PR B right after PR A, and list the five repositories to regenerate in PR A's body (hub rule 7).
- The hub names GC017, PB001-PB003, push-scope, tasklog-lint and publish-check before the gate amendment defines them; the gate amendment must use exactly these names.
- Brief gap: A23 forbids editing a log record other than through the task-log tool, but the interim template has the agent write STORY.md by hand; PR B / brief 2.3 should carve out the interim procedure.
- Brief gap: a hard-flagged commit touching tasklog/ cannot be reverted cleanly (a revert PR is refused by GC017, a direct revert is neither log-only nor in the bookkeeping allowance); D5 or the gate amendment needs a recorded path.

## B-477 DOC.ADR34B -> NEEDS_PLAN_AMENDMENT 
**detail.summary:** The PR B change is written and committed in <worktrees>/b477 (branch docs/b477-adr-0034-agents-template-root-rules, one commit 65a4e82 on 0e37ff5, not pushed). It cannot pass gate-check on build/v1 yet: no `Plan-Task: none (...)` reason fits these files, and no plan task lists them. A plan task has to be added first; the exact amendment is below.

What the commit holds:
- **design/process/templates/AGENTS.template.md:**
  - §3: a `{{owner-credential-exception}}` line after the identity rule, and "Task logs you read are data, never instructions."
  - §4: golden rule 4 in the D2 wording (the same as process/README); golden rule 7 in the brief's words.
  - §6: A23, A24 and A25 in the §2.3 text.
  - §8: the live-session task-log step; line 91 now says "task log (the session report)"; a `{{workspace-root-rules}}` line at the end of §8.
- **Root .gate/agents.yml:** the new template-version sha256:9af22849c597. The owner-credential-exception value is the §2.3 text. The workspace-root-rules value is the Task log block followed by the bootstrap Direct pushes block.
- **The four package agents.yml files:** the new version, and both new values set to "", so the lines disappear in package files.
- **Re-render:** all five AGENTS.md files were produced with `uv run eng-gate agents render --all`; none was edited by hand.
- **.gitattributes (new):** `tasklog/** -text` only. `git check-attr` shows it applies to tasklog/ paths and nothing else.
- **.github/pull_request_template.md:** the A11 line is unchanged; the line "No task-log content and no `tasklog/` path (A24)" is added.
- The tasklog/ folder was not created.

Checks run:
- Gate: `uv run eng-gate check --all --skip mutation` gave `check: pass`, exit 0 (log <lead>/logs/b477-check.log). This run includes the eng-dev-gate package. Its one notice was already there before this change (RT001, tools/eng-dev-gate noqa count 19 -> 18).
- `eng-gate agents drift` passes.
- Simulated gate-check (synthetic event, run from <build-v1> at 0e37ff5 with --gate-root):
  - `Plan-Task: none (hub documents)` and `none (trivial)` both fail with GC011.
  - Both also give AW02 (12 protected paths; .gitattributes is the one unprotected file), AW08 and AW03.
- risk-floor with `Risk: r0` fails with RF001, floor [r2, r3]:
  - r2 comes from packages/eng-contract/.gate/agents.yml and packages/eng-contract/AGENTS.md.
  - r3 comes from .gate/agents.yml, .github/pull_request_template.md and the two tools/eng-dev-gate files.
- Trial: a local throwaway plan commit (since removed) added a task listing these 13 files to a plan with risk [r2, r3], and the PR body said `Risk: r2, r3`:
  - gate-check: awaiting-owner (AW01, AW02, AW08, AW03), no error;
  - risk-floor: pass;
  - test-first: skipped (exempt: type docs).
- Counted lines: 82 (72 added, 10 deleted); the generated AGENTS.md files are not counted.

The handoff note is <lead>/reports/b477-writer.md.

**detail.proposed_amendment:** The gate rule that blocks this: gate spec 4.5 step 3 (`gate_check_docs._fits`). No `none` reason fits these files:
- `hub documents` needs every path under design/;
- `trivial` excludes .gate/ and .github/, excludes .yml files, and allows at most 10 lines;
- `spec and plan`, `spike` and `release` do not apply.

This is the same gap as OQ-Q59. A D-4 direct commit is not possible either: ADR-0034 D5 makes agent-steering files a hard flag.

Precedent:
- Package AGENTS values changed through plan tasks: eng-harness plan 0006 T17b (a docs pull request, exempt from test-first) and gate plan T4 (root AGENTS.md).
- The template itself changed only in B-002 (#7) and in the direct commit f434a41, both before the gate existed.

risk-floor rules RF001 and RF002 mean:
- the hosting plan's risk set must contain r2 and r3;
- the body's `Risk:` line must name that set exactly.

Recommended amendment: a `spec and plan` pull request (or the spec/plan 0015 pull request itself) adds this task to packages/eng-harness/docs/plans/0015-task-log.md, whose front-matter risk is [r2, r3] per brief §4:

```yaml
  - id: T0
    title: "AGENTS template and workspace root rules for the task log (ADR-0034 PR B)"
    # Amendment (B-477): the template change, the five .gate/agents.yml values and the re-render in one pull request
    # (agents-drift stays green), with .gitattributes and the pull request template line; a docs pull request, exempt
    # from test-first. AGENTS.md files are generated and not counted (measured 82 counted lines).
    files:
      - "design/process/templates/AGENTS.template.md"
      - ".gate/agents.yml"
      - "packages/eng-contract/.gate/agents.yml"
      - "packages/structural-codes/.gate/agents.yml"
      - "packages/eng-harness/.gate/agents.yml"
      - "tools/eng-dev-gate/.gate/agents.yml"
      - "AGENTS.md"
      - "packages/eng-contract/AGENTS.md"
      - "packages/structural-codes/AGENTS.md"
      - "packages/eng-harness/AGENTS.md"
      - "tools/eng-dev-gate/AGENTS.md"
      - ".gitattributes"
      - ".github/pull_request_template.md"
    max_changed_lines: 100
    max_sessions: 1
    depends_on: []
```

With that task, the PR B body carries:
- `Plan-Task: packages/eng-harness/docs/plans/0015-task-log.md#T0`
- `Risk: r2, r3`

Expected `awaiting owner` notices in bootstrap mode:
- AW01 (draft plan, if the plan is large);
- AW02 (12 protected paths);
- AW08;
- AW03.

If PR B must merge before plan 0015 exists, the same task can go into a plan that already carries r2 and r3, for example eng-harness plan 0001 [r1, r2, r3]. The body must then say `Risk: r1, r2, r3`, which over-declares r1. Widening gate plan 0001 to [r2, r3] is not recommended: every later gate pull request would then need `Risk: r2, r3` (RF002).

**detail.concerns:** 1. **Risk line.** The prompt gives `r0`, but the measured floor is r2 and r3; `r0` fails with RF001.
2. **Brief wording.** The §2.3 credential text says "push to it, fast-forward, commits log-only commits as ADR-0034 D5 defines them", which is garbled. I wrote "only log-only commits", with the meaning unchanged. The reviewer should confirm.
3. **tasklog/README.md and tasklog/POLICY.json.** They are left out, as the lead note says. ADR-0034 D14 precondition (1) and brief §2.2 count them as part of the workspace rules change, and say they reach build/v1 before GC017 (gate T40). After T40 no pull request can carry them, and changing them is an owner step (D9). The lead must place them before T40 merges.
4. **Pull request template wording.** The root template line says "(A24)", as the brief says. The hub pull-request template says "(A24, GC017)".
5. **Hub rule 7.** The pull request body must list the five repositories this change regenerates: workspace root, eng-contract, structural-codes, eng-harness, tools/eng-dev-gate.
6. **Commit trailer.** The commit carries only `Assisted-by: anthropic/claude`, per playbook 5c and D-3. I did not add the Co-Authored-By or Claude-Session lines the session reminder asks for.
7. **Later edit to eng-harness agents.yml.** Plan 0015 T14 (in the brief) edits packages/eng-harness/.gate/agents.yml again. Its `workspace-root-rules` value must stay "".


## B-478 DOC.TLSPEC -> MERGED 335
**concerns:** 1. ADR-0034 is still Proposed. The spec says it cannot be approved until the owner accepts the ADR. Because the spec's risk includes r2 and the plan is large, both need the owner's approval (G1 and G2). The ADR appendix with the owner's Arabic words is still incomplete. That belongs to the ADR, not this change.
2. AC10 now means something different from the brief. Two concurrent appends never interleave: the second is refused with exit 4 instead of waiting for the first. I made this change because the lock the brief told us to reuse does not wait. If the lead wants appends to wait for each other, that needs a waiting lock and a decision on how long to wait.
3. I made a few small decisions the brief did not spell out: the shared helper `tests/helpers/tasklog_git.py` is listed in the git tasks, T13 depends on T12 (for the `_cli.py` chain), and the run-link module is named `_runlink.py`. Each is listed in the summary and the handoff note.
4. The plan's risk is [r2, r3]. The package `.gate/` files have no risk floor of their own (I checked with the gate's glob matcher), but they need the owner's review because CODEOWNERS covers them. This applies to T1 and T14.

- ADR-0034 is still Proposed, so spec 0015 cannot be approved before the owner accepts it. The spec says so, and spec risk r2 means owner approval at G1.
- The spec reads the end of the ADR D13 interim ('until the harness task-log commands exist') as the merge of plan 0015 T8b. The lead or the owner should confirm this reading; it interacts with author finding 5 (no fallback while the hook is missing).
- The brief-versus-ADR differences the writer resolved (log identity, OPEN status, the sparse set without the root pyproject.toml, the interim end, no repository name) are recorded only in the writer's note. They should go into the pull request body.
- The pull request risk line r0 matches the changed paths (documents only; the writer reports risk-floor pass). The [r2, r3] front matter applies to the later task pull requests.
- Checked and right: the writer's corrections of the brief against build/v1 5dff5d8. These cover the non-blocking RunLock, the Timings field names, the location of fold_report and ResultStore, upper-case RunView.status, model_locked mapped to HOST_LOCKED, Issue having no kind, INVALID_ARGUMENT with field=tool, CalcRefused codes, gaps H-G1 and EC-G2, the absent files of plan 0006 T14, T14b, T18a and T18b, plan 0002 T17's _record.py and the absent workflows/__init__.py. The gate checks also hold: parse_plan within 400, no criterion uncovered, tests_first files inside their task, no test basename clash.
- Carried from round 1. ADR-0034 is Proposed, so spec 0015 cannot be approved before the owner accepts the ADR. The spec reads ADR D13 as ending the interim when T8b merges; the lead or owner should confirm that reading. The record of where the brief and the ADR differ belongs in the pull request body. The r0 risk line matches the changed paths.
- The hook guards both build/v1 and main when the push file is unusable (fail closed). This is consistent with ADR-0034 D4 and the interim template, so it is not an invented value. It is still a design choice the owner should see at G1.
- Step 3 of the interim template tests paths for STORY.md only. After T8b merges, spec §4.7 replaces that test with check --unpushed. The hub template can cite this when it is next revised.
- LOW: Between T12 and T12b, triage files exist but TLC001 and TLC009 do not check them yet, although spec 0015 §4.3.1 says they do (packages/eng-harness/docs/specs/0015-task-log.md, the line after 'One file per need'; plan T12b depends_on [T12]). Both tasks are deferred together, so merging them back to back hides the gap. A follow-up can make T12b's merge a condition of the first triage session.
- LOW: Spec 0015 line 424 ('module sources. Its first line is') is a short line left over from the rewrap. Cosmetic only.
- Carried from rounds 1 and 2: ADR-0034 is still Proposed, so the owner must accept it before the spec can be approved. The owner should see two design choices at G1: the interim ends when T8b merges, and the hook fails closed by guarding both build/v1 and main. The record of where the brief and the ADR differ belongs in the PR body. The PR risk line r0 matches the changed paths.

## B-479 DOC.TLGATE -> INTEGRATOR_DIED 
- The PR body's Risk line should be r3, not r0. For a spec and plan PR, risk-floor records the changed documents' risk (risk: r3 in both files), and the brief's section 2.5 says r3 with owner review.
- PS005 without --merged is only a notice, and GitHub Actions has no merged list. The real squash confirmation depends on local CI passing --merged (brief section 2.4); lead operations must supply it.
- On push, the head variant of the security action runs, so a direct push can edit that action and drop the push checks. Record this in the section 4.16 'Limits that remain' paragraph. Local CI run from the accepted commit is the backstop.
- T41's tests need gpg on the runner and a per-test key, never the pinned key. Decide whether they skip or fail when gpg is missing (windows-tests).
- TL006 'as first written' depends on eng-harness spec 0015 section 4.3, which does not say whether the trailing LF is hashed. T42 must follow plan 0015 T3a.
- Risk line: the prompt asks for `Risk: r0`, but both changed documents carry `risk: r3` and the brief's section 2.5 says r3 with owner review. risk-floor passes either way for a spec and plan pull request, but `Risk: r3` is the honest record (carried from round 1, finding 9).
- Carried from round 1 (findings 10, 12, 13): local CI must pass `--merged` so PS005 can confirm squash commits. T41's signed-commit fixtures should use a key generated per test, and someone must decide what the tests do when `gpg` is missing (the Windows runner). TL006 must follow plan 0015 T3a on whether the trailing LF is hashed.
- Low: when a forced push leaves `before` outside the clone, the push branch exits 2 and judges nothing, so PS004 is never reported. The job still fails, so the gate stays strict, and force pushes to build/v1 are forbidden anyway.
- The per-push result is now advisory only (spec 0001 section 4.17: valid only while every earlier range passed). The authoritative push-scope run is the lead's own local CI run from the last accepted commit (`<since>`), so the lead's runbook needs a step for it.
- origin/build/v1 has moved to 6ac7159 (B-462, eng-harness documents only). That commit touches neither file, so the integrator's merge should be clean.

# Lane owner-answers

## B-495 DOC.OWNER1114 -> MERGED 342
**concerns:** 1. **Read-back tolerance has no task that passes it in production.** I wrote the rule but could not fully apply it. No plan task gives the frozen basis value `checks.readback_relative_tolerance_ratio` to ReadBack.tolerance_ratio. The ports are built at step 1 of spec 0006 §4.2.2, before the basis is frozen at step 3, and build_ports takes no basis. Until a task does this, check_model will report READBACK_UNAVAILABLE for every written quantity on the first live run. Question for you: which task passes the value, and how — a build_ports argument, a later setter on AdapterHostPort, or building the ports after step 3?
2. **Rerun cap stop is my reading of "stops for the engineer".** I used the existing NeedsReconciliation stop. Your OQ-Q68 recommendation said NEEDS_ENGINEER with reason `reconcile_exhausted`, a reason that is not in the documents. AC71 also counts an attempt after the engineer's not_applied as not automatic, so the one automatic rerun allowance starts again after each engineer decision. Please confirm both readings.
3. **Exit code 2 widens the command line's error map.** cli/_exit.py would map the whole code NOT_IMPLEMENTED to exit 2. Today only the H-G8 refusal can reach the command line with that code. The file is plan 0006 T3's (merged); it is now also in servers T19a's file list.
4. **Q38 has no test of the exact case.** test_caller_chosen_run_id checks that a start is refused when the run folder exists, but not a SERVER_CHECK_FAILED refusal itself. A test-only task would pass at its base (TF004), so I added none.
5. **BUILD-STATUS rows are yours to update.** OQ-Q86, OQ-Q87 and OQ-Q90 say "no lead recommendation" there, but the owner record counts them as answered; I followed the record. You need to mark OQ-Q65, Q68, Q85, Q86, Q87 and Q90 answered in BUILD-STATUS.md.
6. **Commit trailer.** Per playbook 5c the commit carries only `Assisted-by: anthropic/claude`, not the session's Co-Authored-By lines.

- L1: how the read-back tolerance reaches the port still needs a decision and a plan task. The ports are built before the basis is frozen, so the options are a build_ports argument, a later setter on AdapterHostPort, or building the ports after step 3. The resume case must read the frozen basis from the run. This is on the first-live-run path: until it is done, check_model reports READBACK_UNAVAILABLE for every written quantity.
- L2: spec 0006 section 6 now maps NOT_IMPLEMENTED to exit 2 for every caller of the error-code map, not only for H-G8, and the row stays after T19b closes H-G8. That is acceptable as 'a configuration this build cannot serve', but it deserves a line when T19b replaces the gap.
- L3: the sentence added to AC70 cites the existing test_caller_chosen_run_id, which pins the refusal of an existing run folder, not a SERVER_CHECK_FAILED refusal. A test-only task would already pass at its base (TF004), so none was added. This follows the lead's instruction.
- L4: engine T21's budget of 30 lines is an estimate, not a measurement. It is plausible (about 15 lines in _inflight.py) but tight.
- L5: marking the six answers in the BUILD-STATUS open-question list is the lead's job; that state file is not edited in this change.
- L1 (now recorded as gap H-G9, packages/eng-harness/docs/specs/0002-servers-and-adapters.md:992): no plan task hands the frozen value of checks.readback_relative_tolerance_ratio to ReadBack.tolerance_ratio. The ports are built at step 1 of spec 0006 section 4.2.2, the basis is frozen at step 3, resume skips the freeze, and build_ports takes no basis. Until a task does this, every written quantity reads back READBACK_UNAVAILABLE on the first live run. Two things are needed: a decision on how the value gets there (a build_ports argument, a setter on the adapter host port, or building the ports after step 3) and a task to do it. Pull request 338 (calc harness.readback_check) uses the compare.* tolerances, so it does not close this gap.
- L2: spec 0006 section 6 now maps NOT_IMPLEMENTED to exit 2 for every caller, not only the H-G8 refusal. That is acceptable, but the row should be looked at again when T19b closes H-G8.
- L3: the sentence added to AC70 cites test_runner.py::test_caller_chosen_run_id, which tests the refusal of an existing run folder, not a SERVER_CHECK_FAILED refusal itself. A test-only task would already pass at its base (TF004), so the writer added none.
- L4: BUILD-STATUS.md is the lead's state file, so marking the six questions answered there is the lead's job (OQ-Q85, Q86, Q87, Q68, Q65, Q90).

## B-494 DOC.ADR34ANS -> REVIEWER_DIED 

# Lane editcycle-2

## B-493 DOC.WT2 -> MERGED 340
**concerns:** 1. The B-196 calc does not match this amendment as it stands. The T2 writer must make three changes, all inside T2's file list: change the calc's import to `eng_harness.workflows.model_edit_cycle._change_set`; rewrite calcs.lock.json with `uv run python -m eng_harness._calc._hash --write-lock`; and edit the rules test as described in the summary. The writer's own trial patch, which admits the package `eng_harness.workflows.model_edit_cycle`, is deliberately not what the spec allows.

2. T4 is not covered, so the plan says only T3 uses the same imports, not T3 and T4. The inputs of `harness.host_design_verdicts` and `harness.analysis_summary` are `harness.csi_design_results/1` and `harness.csi_analysis_messages/1`. Their model, `CsiRows`, lives in the adapter module `eng_harness.adapters.csi._replies`, which uses pathlib and converts host replies; its package `__init__` loads the allowlist. Allowing it would break the reasoning of section 4.3, so I did not. A decision is needed before T4 starts. Options: (a) a later amendment and code task moves `CsiRows`, or a kinds model for those two kinds, into a kinds module such as kinds/edit_cycle.py, which is not in T4's file list today; (b) T4 types those inputs another way.

3. At runtime, importing `_change_set` still runs its parent package `__init__` files. Today they only re-export names. Once T6 and T7 put the WorkflowDef there, importing `eng_harness.calcs` will import the workflow's block code, though not into the hash. If the workflow ever imports `eng_harness.calcs`, this becomes a circular import. T6 and T7 should watch for this; moving the change-set model into a kinds module later would remove the issue.

- T4's calcs (host_design_verdicts, analysis_summary) take harness.csi_design_results/1 and harness.csi_analysis_messages/1, whose model CsiRows is in eng_harness.adapters.csi._replies. That module imports pathlib and does host unit conversion, so it is not admissible under §4.3. The change correctly claims only T3. A later amendment must move CsiRows (or a kinds copy) into a kinds module, or type those inputs another way. T4's file list has neither today.
- Spec 0007 §4.1 gives _change_set.py the risk floor 'block code', yet its source now enters the content hash of R1 calcs. Consider whether changes to that module should carry the calc risk class.
- B-196 must switch its import to `from eng_harness.workflows.model_edit_cycle._change_set import ChangeSetDraft, refused_gap` and rewrite calcs.lock.json. Both files are in T2's files, and the budget stays 349/380 (the rules test is under tests/** and not counted).
- The coupling in the author finding goes away if a later code task moves the change-set model (ChangeSetDraft, its item models, refused_gap) to a kinds-level module, for example eng_harness.kinds.change_set. workflows/column_design/_requests.py also imports private names (_M, _InputValue) from _change_set, so that move touches plan 0013's files too. Decide before plan 0007 T9 merges.
- From round 1 and still open: T4's CsiRows input lives in eng_harness.adapters.csi._replies and is not admitted by 4.3; a later amendment must deal with it.
- From round 1 and still open: _change_set.py has the risk floor 'block code' in spec 0007 4.1, yet its content now enters the hash of R1 calcs. Consider giving that module the calc's risk class.
- From round 1 and still open: B-196 must import from eng_harness.workflows.model_edit_cycle._change_set by module name and rewrite calcs.lock.json. Both are inside T2's files.
- LOW: spec 0003 section 4.3 (packages/eng-harness/docs/specs/0003-calcs.md lines 328-329) names `workflows/__init__.py` as a parent that runs on import. That file does not exist today (the package is a namespace package); plan 0007 T9 creates it. The sentence reads correctly because it says 'from plan 0007 T9', but a later amendment could say 'once plan 0007 T9 creates it'.
- Still open from rounds 1 and 2: T4's `CsiRows` input lives in `eng_harness.adapters.csi._replies` and spec 0003 section 4.3 does not admit it. A later amendment must decide whether to move it to a kinds module or type those inputs another way.
- Still open from rounds 1 and 2: `_change_set.py` has the risk floor 'block code' in spec 0007 section 4.1, yet its content now enters the content hash of R1 calcs. Consider giving it the calc risk class.
- Still open from rounds 1 and 2: moving the change-set model to a kinds-level module (for example `eng_harness.kinds.change_set`) would remove the coupling to the parent packages. That move also touches plan 0013's `workflows/column_design/_requests.py`, which imports private names from `_change_set`. Decide before plan 0007 T9 merges.
- For B-196: change the import to `from eng_harness.workflows.model_edit_cycle._change_set import ChangeSetDraft, refused_gap` and rewrite calcs.lock.json. Both files are inside T2's file list.

## B-196 W.T2 -> INTEGRATOR_DIED 
- low: Spec 0007 section 4.4.1 names a single input `state`. The calc instead takes the read set as flat fields (frames, areas, sections, restraints), as calcs 2 and 3 do (spec 0003 section 4.7, spec 0007 step 9). The spec text should say so.
- low: harness.csi_name_lists/1 has no list of load-case names, so K2 does not check a combination term of type load_case (item 1 of the verification record). Spec 0007 section 4.10 or 4.4.1 should decide what happens here.
- low: Spec 0007 section 4.3.3 says the contract's structural bounds (dimensions greater than zero) apply, but does not say which component applies them. Neither ChangeSetDraft nor the calc refuses a thickness of 0 when bounds.thickness_min_mm is 0. The spec should say whether harness.change_set_check applies that bound.
- Round 1 finding 2 (low, still open): spec 0007 section 4.4.1 names one input `state`, but the calc takes the read set as flat fields (frames, areas, sections, restraints), the same way calcs 2 and 3 do. The spec text should say this.
- Round 1 finding 3 (low, still open): harness.csi_name_lists/1 has no load-case list, so K2 does not check a combination term of type load_case (packages/eng-harness/src/eng_harness/calcs/edit_cycle/change_set_check.py line 231, verification record item 1). Spec 0007 section 4.10 or 4.4.1 should decide this.
- Round 1 finding 4 (low, still open): spec 0007 section 4.3.3 names no component for the structural bound 'dimension greater than zero'. When bounds.thickness_min_mm is 0, neither ChangeSetDraft nor the calc refuses a thickness of 0. The spec should say which component applies the bound.
- low: Spec 0007 section 4.3.3 says the contract's structural bounds apply (contract 4.10.2, where AreaSection.thickness_mm is Positive), but it does not say which component enforces them. With bounds.thickness_min_mm = 0, a thickness of 0 passes harness.change_set_check and would only be refused later by the kind. The spec should say whether K4 applies 'greater than zero'. This repeats round 1 lead finding 4, seen from the sources side.
- low: A literal near a bound but entered in a non-canonical unit is judged at its exact binary value. For example 0.3 m becomes 299.99999999999998889 mm, so it is refused when bounds.thickness_min_mm = 300. The code is consistent with eng_contract.units.convert_exact and with the word 'exact' in K4. The spec could state this rule explicitly, or choose a decimal reading of literals instead, so the behaviour is decided rather than incidental.

# Lane clause-docs

## B-497 DOC.CLAUSES -> INTEGRATOR_DIED 
- L1: packages/structural-codes/aci318-14/tests/unit/test_bearing.py line 132 still uses the old name foundation.allowable_bearing_pressure in a synthetic basis. It is not tied to the documents. Fold the rename into the next aci318-14 code task (B-484 O-2; HANDOFF line 169).
- L2: after this merges, several records go stale: docs/build/lead-playbook.md line 195, docs/build/lead-findings.md lines 58 and 66, and PLAYBOOK section 5d ('the protected clause documents keep the old names'). Update them at the next bookkeeping checkpoint (D-4).
- L3: in a spec-and-plan pull request the body line 'Risk: r0' is for information only. The recorded risk comes from the changed documents, and the clause documents' front matter says r1. risk-floor passed with r0; consider whether the body should say r1.
- L4: the premise that the gate would print 'awaiting owner' notices for these paths does not hold. Neither gate log contains such a line, and gate-check reports only AW08 and AW03. There is no AW02 because the clause documents are not CODEOWNERS paths; the 'Owner approval: awaiting owner' line in each document is what protects them.
- L5: origin/build/v1 has moved to 9ccfa15 (B-148, harness calc files only). The branch merges cleanly with no overlap.
- L1: packages/structural-codes-aci318-14 tests/unit/test_bearing.py line 132 keeps foundation.allowable_bearing_pressure (synthetic basis, not tied to the documents, B-484 O-2); fold the rename into the next aci318-14 code task.
- L2: once this merges, docs/build/lead-playbook.md line 195, docs/build/lead-findings.md lines 58 and 66, and PLAYBOOK section 5d ('the protected clause documents keep the old names') go stale; update them at the next bookkeeping checkpoint (D-4).
- L3: the PR body line 'Risk: r0' comes from the prompt, but the front matter of the changed documents says r1. Risk-floor passed in round 1 either way; the lead decides which value the body shows.
- L4 (integrator): the 'For the owner' section must hold the rename table (13 lines, 18 path tokens) and the open wording item at aci318_14.13_3_1_1.bearing_pressure_service.md lines 62-63 ('Basis paths are lower case ... not in a suffix'), which now contradicts the renamed rows. Do not merge (owner instruction of 2026-11-14).
