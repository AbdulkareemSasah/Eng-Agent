Local CI in the build container (lead decision D-23): **PASS** on head 6eda5f5 against base f538973, pull_request mode, finished 2026-11-17T10:53:39Z.

| Job | Result | Seconds |
|---|---|---|
| setup | pass | 3 |
| gate-check | pass | 1 |
| risk-floor | pass | 1 |
| test-first | pass | 14 |
| agents-drift | pass | 0 |
| ci-review | pass | 0 |
| security | pass | 0 |
| build | pass | 1 |
| gate | pass | 645 |

Mutation step: not run in this pull request run (owner decision of 2026-11-15); it runs on build/v1 after every ten merges

Not run in the container: the dependency audit (`uv audit --locked`; api.osv.dev is outside AGENTS.md section 9 and denied by the network policy) and the windows job (no Windows here). Both are owner local-test items (LOCAL-TESTING.md).
