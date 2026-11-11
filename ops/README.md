# ops: build operations for the v1 build

Lead tooling kept in the repository so any agent can continue the build (see [HANDOFF.md](../HANDOFF.md)).
It is not a workspace member and holds no importable code.

## localci.py: local CI (lead decision D-23)

GitHub Actions cannot run for this repository (no paid plan), so CI runs locally and its result is written into the
pull request. `localci.py` reproduces `.github/workflows/ci.yml`: the pull request head merged with the latest
`build/v1` (the tree the squash merge produces), the base commit checked out at `.gate-base`, `GITHUB_ACTIONS=true` and
a `pull_request` event file, then the jobs gate-check, risk-floor, test-first, agents-drift, ci-review, security, build
and gate (`eng-gate check --all` plus the spike checks). It resolves CHANGELOG, local-testing and ratchet conflicts
mechanically and pushes that merge commit to the pull request's branch; any other conflict is reported as CONFLICT.
Not run locally: `uv audit --locked` and the Windows job (owner items).

```bash
python3 ops/localci.py start --pr-json pr.json
```

```bash
python3 ops/localci.py wait --run-dir .localci/runs/<run> --max 600
```

```bash
python3 ops/localci.py release --run-dir .localci/runs/<run>
```

- `pr.json` is the pull request as the GitHub API returns it: `number`, `title`, `body`, `draft`, `user.login`,
  `labels`, `head.ref`, `head.sha`, `base.ref`. The run key includes the title and body, so update the body (Review
  section) before starting.
- `start` answers STARTED, ALREADY_DONE, HEAD_MISMATCH (read the pull request again), BEHIND (merge `build/v1` into the
  branch first) or CONFLICT. One run at a time (a lock); after a PASS the lock is held until the pull request merges,
  `release` is called, or ten minutes pass (D-26).
- `wait` exits 0 on PASS, 1 on FAIL, 3 while running; `summary.md` in the run directory is the table for the body.
- Run state lives in `.localci/` (ignored); set `LOCALCI_HOME` to put it elsewhere. Merge commits it pushes are signed
  with `LOCALCI_GIT_NAME`, `LOCALCI_GIT_EMAIL` and the trailer lines in `LOCALCI_TRAILERS`.
- The gate's mutation step can run up to `limits.mutation_run_seconds` (7200 s) on large changes; the per-job limit
  is three hours.

## remaining-tasks.json

Every registered work item not merged on `build/v1` at the pause, in plan order: work item and plan task, title,
branch and pull request title, the plan's risk line, dependencies still pending, the suggested writer and reviewer,
the verifier lenses, an open pull request or pushed branch, the lead notes, and for documents amendments their full
instructions. Regenerate nothing by hand from it: when a task merges, it is simply done.
