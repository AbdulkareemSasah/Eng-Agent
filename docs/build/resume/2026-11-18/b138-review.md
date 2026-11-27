> Read the latest pause checkpoint round for the current verdict. B-562 has merged. See [the current writer note](b138-writer-session-3.md).

# B-138 lead review

## Preliminary implementation review (working tree after eeae76fe)

Verdict: CHANGES. This is a review of the initial uncommitted implementation and tests, not approval of an immutable candidate. The lead did not write the change. A complete final-head review and verification are still required.

Author findings sent to the writer:

1. High: the crash matrix initially cut only the two assignment steps, while AC36 requires every write step in the real-engine cycle. Include open, revision save, analysis and design; preserve explicit engineer decisions for unreconciled/unknown outcomes rather than assuming an automatic successful replay. Assert no repeated write and journal evidence.
2. High: pre-image capture initially replaced the binder's pre_image_ref unconditionally. Plan T19a explicitly requires opt-in `record_pre_image=False` for existing hand-wired ports, with production build_ports enabling it. Capture only reconcilable writes; preview must retain a hand-wired binder's supplied reference when opt-in is false.
3. High: preview initially skipped identity binding for every open action. The spec's exception concerns an unbound open only. A bound open must retain its model identity/revision; a stale bound model must fail normal binding checks. The unbound case must not perform a binder/host read. A narrow optional internal callback over the host's binding cache is an acceptable in-scope implementation seam; no engine port contract changes are authorized.
4. High: the initial binder called IdentityStore.resolve(path), which can change the file identity baseline and consume outside-edit warnings. Read the already-bound identity record without resolving the disk path; test that an outside file change remains visible to the next model_state check after a binding query.
5. Medium: the private constructors used tolerance_provider instead of the plan's `tolerance` keyword. Follow the named constructor seam in T19a's prose for both host and reconciler.

The writer reports fixes for these findings, including the full six-write matrix and a regression for the outside-edit baseline. Those fixes remain subject to final diff/test review. The lead requested a full reread of the previously truncated T19a prose and spec 4.5.7–4.5.9; the writer confirmed that reread.

Other sensitive contracts checked during the preliminary review: ServerManager lifetime inside AdapterPorts; frozen basis provider on start and resume without a numerical fallback; shared WrittenItems, host.wrote, Revisions and reopened/opener wiring; product/host program executable provenance; explicit H-G8 refusal and exit 2; preflight and units failures before writes/reconciliation. Test-first commit eeae76fe has observed runtime failures (missing build_ports and exit 70 versus 2), with no collection failure. No final PASS, mutation result or real host behavior is claimed here.

## Adapter checkpoint review (668c3830c7c25912483d09626d43d64ca87e259b)

Verdict: CHANGES. Reviewed the complete production adapter diff again at this immutable local checkpoint. The opt-in pre-image behavior, bound-open preview identity, cache-only unbound-open exception, read-only binder identity, planned tolerance keyword and shared frozen-provider wiring resolve the earlier adapter findings. The expanded matrix and new engine regressions honestly expose the EC1 handoff and post-open bookkeeping gaps; those remain pending the independently approved B-562 amendment and implementation.

One new HIGH author finding is confirmed by independent adversarial source verification in b138-adapter-sources-verifier.md: `_load` unconditionally registers persisted process IDs as manager attach targets. The manager attaches during preflight before resume can handle a lost model. A dead/reused cached process can therefore cause the wrong attach or a server-check refusal instead of the existing AC63 recovery. Preserve the cached bindings for recovery, but register only an instance satisfying the existing inspector PID/start-time identity policy. A regression must inspect stale/reused attach targets; the current fake accepts every attach, so healthy-preflight assertions alone would not fail on the broken implementation. A live identity control must retain normal attachment. This fix stays within the existing host-port and workflow-test scope.

No additional high/medium finding was found in the stable engineering-value sources, preview, or binder review. This is still not a final implementation approval: formal test-first, the complete non-diagnostic matrix, full package gate, mutation and final strong engine review remain outstanding.

## Pause checkpoint review (0a407606b1b49c8f7d6277bd6a585d20fbcd6762)

The stale-PID finding is resolved in the committed checkpoint. Independently reviewed the entire delta from 668c3830: the dead/reused/live regression added in 6f609b0a and the three-line guarded registration change in 0a407606. Reloaded bindings, instances and expected units remain available for recovery; only an instance accepted by the existing CsiSession.alive PID/start-time policy becomes the manager's attach target. The regression inspects actual csi_attach calls, retains a live control and checks preserved binding/unit state. Recorded red evidence contains the two wrong stale/reused attaches; the green run passes all three cases. No executable-identity enforcement beyond the existing inspector policy is claimed.

This is approval of that scoped fix and a reviewable pause checkpoint, not approval of the entire B-138 implementation. Overall status remains CHANGES / incomplete: the merged B-562 contract and expanded engine/port/journal implementation are not yet applied to this task branch. Formal test-first, full matrix, full package gate, mutation and final strong review remain pending. The owner explicitly requested uploading unfinished work for handoff on 2026-11-18; the branch was pushed at this exact checkpoint without opening an implementation PR or claiming those checks passed. Three writer sessions have been used; a reviewed session-budget amendment is needed before a fresh fourth writer session.
