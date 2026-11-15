<!-- The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text. -->

# Owner answers of 2026-11-14 (lead record; the single source for work items B-494 and B-495)

On 2026-11-14 the lead put a batch of open questions to the owner, each with a recommendation where one existed, and
told him that the words «نفّذ التوصيات» ("apply the recommendations") would be enough for everything he did not want
to change. The owner answered, verbatim: «نفّذ التوصيات». So every question below that carried a recommendation is
answered with that recommendation. Questions that carried no recommendation, and the two acceptances, are NOT answered.

## A. ADR-0034 (task log by default), section "Open questions for the owner"
- Question 3 (log pushes from cloud sessions): ANSWERED: cloud sessions read logs and push nothing under `tasklog/`;
  the push exception of D6 is for the owner's machine only.
- Question 2 (exposure to writers on other services): ANSWERED: the sparse-checkout precondition of D11 stays a
  precondition of the first log push.
- Question 1 (log-only pushes to a protected `main` after bootstrap): ANSWERED as recommended: decided at the end of
  bootstrap; a path-restricted rule or an agent identity is preferred over a general bypass. (The choice itself stays
  to be made then.)
- Question 5 (personal paths in his words): ANSWERED: the guard withholds them.
- Question 4 (the lead's bookkeeping allowance) and question 6 (OQ-Q50): NOT put to the owner in this batch; still open.
- The status of ADR-0034 stays `Proposed`: the owner has not yet said he accepts the written record (hub rule 3).

## B. Technical questions
1. With a caller-chosen run id, a SERVER_CHECK_FAILED refusal leaves the run's server logs in the run folder.
   ANSWERED: the logs stay (they are the evidence of the refusal), and a retry with the same run id is refused.
2. How many times is a write that reconciliation found not applied rerun automatically?
   ANSWERED: once; then the run stops for the engineer.
3. Where does check_model take the read-back tolerance from?
   ANSWERED: from the basis field, passed by the workflow (as servers plan 0002 T12b prose already reads).
4. Exit code of the refusal of `[cli_tools.*]` settings at phase 1 (gap H-G8, spec 0002 AC43 as amended by B-475):
   ANSWERED: 2 (usage error), not 70.
5. Dropped decision releases in the phase-1 run summary (spec 0009 AC49 as amended by B-475): ANSWERED: they are
   journaled (point and reason), not only printed as warnings.
6. Does the merged calc harness.footing_subjects need version 2 after its basis input is renamed? ANSWERED: no, it
   stays version 1 (draft, never approved), as footing plan 0010 T3b says.

## C. Not answered (no recommendation was given, or an explicit acceptance is needed)
- Combination factors in the contract's CombinationItem: literals or references? (interim reading of the plan stands)
- Which result reports MODEL_CHANGED_OUTSIDE warnings.
- Acceptance of ADR-0034 as written (status move).
- Acceptance of the scenario C spec changes (AC43 of spec 0002, AC49 of spec 0009, gaps H-G8 and PR-G1, Q16 (d)).
- Protected ACI clause documents (14 basis path renames in 8 documents): a pull request the owner reviews, or his own edit.
- Which task builds the real point-policy mapping before providers T10b.

## D. Second message of the owner, 2026-11-14 (verbatim): «أقبل، وأطلق مهمة وثائق البنود بطلب دمج أراجعه»
The lead had written that the word «أقبل» is enough to accept ADR-0034. So:
- ADR-0034 is ACCEPTED by the owner as written, with his four answers of section A. The status moves from `Proposed`
  to `Accepted` by work item B-496, after B-494 has recorded the four answers (an accepted ADR is not edited again).
- Protected ACI clause documents: the owner asked for a work item with a pull request that HE reviews: work item
  B-497. The integrator opens the pull request and runs local CI but does not merge it.
- Acceptance of the scenario C spec changes (AC43, AC49, H-G8, PR-G1, Q16 (d)): the lead does not read «أقبل» as
  covering it; asked again.

## E. Third message of 2026-11-14 (verbatim): «راجعت الطلب 346، ادمجه»

- The owner reviewed pull request 346 (B-497, clause documents basis path names) and told the lead to merge it.
- Done by the lead: squash merge d265bee on build/v1 (local CI PASS on head 96c4f5d against base 4894701, the base at
  the time of the merge). The three open items of the pull request's "For the owner" section were not answered by this
  message (wording of aci318_14.13_3_1_1 lines 62-63; test_bearing.py line 132; Risk line r0 or r1): still open.

## F. Speed-up measures, 2026-11-14 (after the stop)

- The owner asked (verbatim): «اقترح اشياء تسرع في التطوير بدون التأثير على الجودة». The lead proposed six measures.
- The owner answered (verbatim): «طبق الاقتراحات فقط كتعديل على ملفات اسلوب العمل ولا تبدأ بتشغيل اي وكيل او سير عمل
  واعطني نسبة تقريبية لنسبة التسريع».
- Reading: all six are approved, including the three that needed his word (small edits of existing tests outside the
  file list; a shorter local CI for documents-only pull requests; the mutation step not repeated). Applied by the lead
  as edits of the work-method files only (playbook section 7, lane script version 2, plan-audit script, resume order),
  work item B-506; no agent or workflow was started. Measures 2, 3 and 4b need a change of the gate or of local CI
  (code): they are recorded as approved and queued as work items B-507 and B-508 for the next start; they are not in
  force before those merge. The proposed numbers of measure 2 (8 files, 30 lines) are the lead's, to be seen by the
  owner in the gate amendment.
