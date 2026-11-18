Local CI in the build container (lead decision D-23): **PASS** on head a6fbe29 against base 3cb4563 (merged locally with that base as 92e16b6, the tree the squash merge produces), pull_request mode, finished 2026-11-17T11:06:15Z.

| Job | Result | Seconds |
|---|---|---|
| setup | pass | 0 |
| gate-check | pass | 1 |
| risk-floor | pass | 1 |
| test-first | pass | 0 |
| agents-drift | pass | 0 |
| ci-review | pass | 1 |
| security | pass | 0 |
| build | pass | 1 |
| gate | pass | 712 |

The gate job ran once on the batch tree of pull requests #412, #413 merged onto base 3cb4563, tree b7648fbd2140d36cd87a00c1246bbabf36b3007b, which is the tree build/v1 has after these squash merges.

Mutation step: not run in this pull request run (owner decision of 2026-11-15); it runs on build/v1 after every ten merges

Not run in the container: the dependency audit (`uv audit --locked`; api.osv.dev is outside AGENTS.md section 9 and denied by the network policy) and the windows job (no Windows here). Both are owner local-test items (LOCAL-TESTING.md).
