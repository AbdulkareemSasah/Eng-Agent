# 12. Operations: Emergencies, Flaky Tests, CI Failures, Audits, Dependencies

## 1. Emergency path

For a wrong engineering result in a release, a leaked secret, or a broken release:

1. **Contain first, with one owner approval and green CI**: a pull request that only reverts, withdraws a check or
   calc (marks it `withdrawn` so the harness refuses it), or yanks a release. The normal spec and plan gates are
   waived for this pull request only; `gate-check` recognizes it by the `type/emergency` label set by the owner.
2. Publish what is needed: a security advisory for wrong results or vulnerabilities, a changelog entry, a yanked
   release note.
3. **Then the full pipeline**: the real fix goes through every stage, starting with a regression test.
4. A short post-mortem within one week: cause, why the gates missed it, the process or rule change that prevents it,
   filed as issues.

Runbooks:

| Incident | Steps |
|---|---|
| Wrong engineering result | Withdraw the check or function; advisory listing affected inputs; regression test; full R1 fix ([10](10-engineering-verification.md) §7) |
| Leaked secret | Revoke and rotate at the provider immediately; remove from the repository; if it reached a pushed commit, purge history with the owner and notify affected services; review how it escaped the secret scan |
| Broken release | Yank the release (and the PyPI version once public); publish a patch from `main`; record the cause |

## 2. Claiming work

An agent session claims an issue by assigning the agent identity and setting `status/in-progress`. An item has one
assignee. A claim without activity for three working days is released through the owner digest.

## 3. Flaky tests

- Rerun plugins are not allowed. A test that fails nondeterministically is either fixed in the pull request that
  observed it, or quarantined: a quarantine marker with an issue and an expiry date of at most ten working days,
  counted by the ratchet.
- Property tests use the Hypothesis CI profile (`derandomize=True`) so failures reproduce.

## 4. CI failures

- At most one re-run of a failed job. A second failure is treated as real.
- An infrastructure failure (runner, network, service outage) becomes a `type/ci` issue and the agent reports
  `BLOCKED`.
- Workflows are never edited to get a green result; workflow changes are protected and go through the owner.

## 5. Auditing the reviewers and delegated merges

- Monthly, the owner opens a test pull request with seeded defects (a wrong unit, a missing error path, an uncited
  constant, a weakened test). Every CI reviewer must flag them; misses lead to prompt updates in `eng-dev-gate`.
- The owner reviews at least one in ten merged pull requests that did not require owner approval, chosen at random by
  the digest, and files issues for anything the gates missed.

## 6. Dependency updates

- Dependabot (with uv support) opens update pull requests weekly.
- Patch updates and development-dependency updates merge automatically when every required check is green.
- Minor updates of runtime dependencies are reviewed by the CI reviewers; major updates and new runtime dependencies are
  R3 work with an ADR.

## 7. Owner digest

A scheduled workflow keeps one pinned issue listing every decision waiting for the owner: specs and plans to approve,
R1 and R2 merges, disputed findings, acceptance runs needed before a release, releases to approve, sampled merges to
audit, stale claims, open project-lane branches (flagged after 30 days). Each entry is phrased as a question with a link. The owner's daily work is this list.
