Round 1 (b55b965b)

Independent lead review of the complete diff against origin/build/v1, engine plan 0001 T23 and spec AC72, including the merged B-560 scope amendment. The change accepts a model key alongside ModelHandle in Preview and promotion, uses one key-normalization helper at approval binding, inserted preview matching and promotion, and leaves live-state binding, approval reuse/refusal and working-copy/promotion checks in place. The key is still resolved through the existing host and approval checks; a block does not supply an invented model identity or revision. The workflow regression exercises pause/resume, working-copy writes, both stored previews and file-copy promotion with the actual result and file contents asserted. Existing handle callers remain covered. No engineering value or arithmetic changes.

The collateral test edit is in T23's amended file list and preserves the supplied revision-2 handle by comparing the full tuple, fixing the union-type access without weakening its behavioral assertion. Seven changed paths are in scope; counted source/document lines remain 23 against the base gate's estimate of 30. Published implementation/test commits were preserved; current test-first, package gate and mutation evidence must be recorded before integration, with current-head local CI still required.

Author findings: none. Lead findings: none added. This review covers b55b965b; any authored source repair requires another review.

Verdict: APPROVE.
