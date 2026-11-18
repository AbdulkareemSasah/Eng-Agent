> Review of the now-merged documents. [The integration report](b556-b562-integration.md) records subsequent CI and merge.

# B-562 independent lead review

## Round 1 (cd9d190ae7ee3f2cc1e5a9ea71de379ae2c9e818)

Verdict: APPROVE. The lead did not write this amendment. This is a specification and scope review, not approval of the still-unimplemented B-138 engine changes. The package gate and current-head local CI remain separate requirements.

Reviewed the entire three-file diff against the owner's explicit 2026-11-17 approval of a conservative, explicit original-open content capability; the existing edit-cycle Step 2 and engine EC1; the independently confirmed crash-matrix evidence; and the source writer's complete impact report.

The port method defaults to false and the CSI adapter alone supplies its known pathless-original-open guarantee. The engine remains adapter-neutral. A strict optional per-attempt journal bit records an explicit opt-in, while missing/null/false and legacy payloads stay conservative. Omitting None preserves earlier canonical payloads; replay uses the recorded classification rather than a new adapter description. The guarantee concerns model content and does not change the write effect, permissions, leases, units checks, sibling exclusion, unknown-outcome reconciliation or retry rules.

The dirty exception only avoids a new mark from that non-mutating operation; earlier actual dirty state remains set. The resume exception requires the marked successful/applied original open and its exact live completed post-copy attempt, matching origin and distinct copy, and a historical working-copy save at the same path between that attempt's start and completion. Stale attempts, restore cuts, later original bindings, unresolved opens, actual original/copy writes and unexpected lost/reopened hosts retain normal recovery. Historical proof remains available after a later copy save. Content provenance and revision-save selection cannot let a later non-mutating open hide an earlier actual write or save. Raw write-effect views remain authoritative for leases, in-flight work and restore safety.

Post-open binding/units and EC1 completion are required after both an immediate applied outcome and replay before a still-live copy, without rebinding an original after an already completed copy. The plan lists all twelve additional source/test paths identified by the writer, including the private modes and host-safety seams, journal compatibility, host-state negatives and CSI descriptor tests. Existing test-first nodes, dependencies, session limit and risk set are preserved; the added AC52 and implementation regressions cover the expanded behavior. No implementation permission is inferred before this amendment merges.

AC36 now states the existing explicit engineer decisions for unsupported/unknown outcomes. Accepting a new baseline after a save remains the existing AC34 engineer choice; the amendment does not invent recovered saved_file/provenance evidence or bypass EC2. No engineering value, dependency, allowlist expansion or real-host authorization was added. The measured 128 changed document lines are informational.

No author findings. Package gate and exact-head local CI must pass before merge; the eventual implementation needs its own full strong review and verification.
