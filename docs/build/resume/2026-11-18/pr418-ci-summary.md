> Archived runner output. The original explanation of network denial reflects older network conditions.
> The audit was omitted under AGENTS.md §9 because that section does not allow the OSV endpoint.

Local CI in the build container (lead decision D-23): **PASS** on head cb4007e against base 00770cf, pull_request mode, finished 2026-11-17T20:16:19Z.

| Job | Result | Seconds |
|---|---|---|
| setup | pass | 0 |
| gate-check | pass | 2 |
| risk-floor | pass | 1 |
| test-first | pass | 0 |
| agents-drift | pass | 0 |
| ci-review | pass | 0 |
| security | pass | 1 |
| build | pass | 1 |
| gate | pass | 956 |

The gate job ran once on the batch tree of pull requests #417, #418 merged onto base 00770cf, tree 7bae8899e8ffeb9b25bc28ef06260553337b4b81, which is the tree build/v1 has after these squash merges.

Mutation step: not run in this pull request run (owner decision of 2026-11-15); it runs on build/v1 after every ten merges

Not run in the container: the dependency audit (`uv audit --locked`; api.osv.dev is outside AGENTS.md section 9 and denied by the network policy) and the windows job (no Windows here). Both are owner local-test items (LOCAL-TESTING.md).
