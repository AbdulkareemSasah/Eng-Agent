# B-556 and B-562 integration

**Merged and verified on `build/v1` on 2026-11-18 Riyadh time (UTC+3).** This closes the batch already underway at the pause.

| Work item and pull request | Exact Local CI head | GitHub squash commit | GitHub merge time (UTC) |
| --- | --- | --- | --- |
| B-556 [#417](https://github.com/AbdulkareemSasah/Eng-Agent/pull/417) | `b2d9f734617f8a40fc03bb9701e292dff71dc407` | `78d37e186d51b7edf239c4595c5007b66c884d12` | 2026-11-18 03:39:05 |
| B-562 [#418](https://github.com/AbdulkareemSasah/Eng-Agent/pull/418) | `cb4007ec02843aac66a1c1d10ece9947e24c3bbf` | `686578fed6faf4ed8ec83b05b325f0d63c6e1c7a` | 2026-11-18 03:40:08 |

Local CI returned PASS on both heads against `00770cf1b304c0ee52196908f535f57fa1f6ab0e` at 2026-11-17 20:16:19 UTC (23:16:19 Riyadh). It ran one shared all-package gate for 956 seconds on batch commit `c0830db1316ab9eced7f9ca5c70a3b56aa67fab0`, tree `7bae8899e8ffeb9b25bc28ef06260553337b4b81`.

| Local CI job | #417 (seconds) | #418 (seconds) |
| --- | ---: | ---: |
| setup | 0 | 0 |
| gate-check | 1 | 2 |
| risk-floor | 1 | 1 |
| test-first | 9 | 0 |
| agents-drift | 0 | 0 |
| ci-review | 0 | 0 |
| security | 0 | 1 |
| build | 1 | 1 |
| gate, shared | 956 | 956 |

Both recorded results have exit 0 for every job. Bootstrap gate-check and CI review still reported owner items. #417 passed test-first. #418 was exempt as a documents change. The security job ran the secrets check. Dependency audit (`uv audit --locked`) and the Windows job remain owner local-test items in `LOCAL-TESTING.md`. AGENTS.md section 9 does not allow `api.osv.dev`, and the build container runs Linux. The published CI summaries reflect these limitations. The raw run summaries and result files are intact.

B-556 package verification passed on `9ff084d5217d52a34645c1a101356fbe9aad259b`, whose `eng-harness` tree matches the integration head. The 144 focused tests and formal test-first check passed. Independent lead review approved, and independent sources verification returned APPROVE_WITH_CONCERNS because the `ReadbackReason` docstring omits `check_model_failed`. The separate per-change mutation step returned PASS with notice MU003 for zero generated mutants. Mutation score and mutation coverage for the selected rule predicates are unavailable. Pull-request Local CI omitted mutation.

B-562 is the three-file, 128-line documentation amendment for the owner-approved conservative original-open capability and B-138 completion scope. The independent review approved `cd9d190ae7ee3f2cc1e5a9ea71de379ae2c9e818`, the package gate and risk floor passed, and the three-file task diff matches the integration head relative to its updated base. B-138 implementation remains pending.

Each PR received its Local CI summary before merging. Each squash merge used GitHub's exact-head guard and the registry title with its PR number. The GitHub API confirmed each squash parent and the message body with sole trailer `Assisted-by: anthropic/claude`. After #417 landed, #418's PR metadata still reported the earlier base SHA. The live branch ref was the verified #417 squash as expected, and a local merge-tree computation confirmed the combined tree before #418 landed. After both merges, fetching `origin/build/v1` confirmed `686578fed6faf4ed8ec83b05b325f0d63c6e1c7a` at the exact tested batch tree. The clean root checkout was detached there for the checkpoint state update.

Both runs were released at 2026-11-18 03:40:22 UTC (06:40:22 Riyadh), after both merges and the final tree comparison. Each run has a `released` marker. No CI was started for the pause handoff.

- PR #417 [result](pr417-ci-result.json) and [summary](pr417-ci-summary.md).
- PR #418 [result](pr418-ci-result.json) and [summary](pr418-ci-summary.md).
- [B-556 sources review](b556-sources-verifier.md) and [mutation report](../../integration-2026-11-17/b556-mutation.md).
- [B-562 independent review](b562-review.md) and [writer verification](b562-writer.md).
