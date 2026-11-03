# 05. Testing and Verification

## 1. Test layers

| Layer | What it proves | Runs |
|---|---|---|
| Unit | Functions and classes behave per spec | Every pull request |
| Contract | Every envelope, kind and tool schema validates against `eng-contract`; generated catalogs and schema snapshots are current | Every pull request |
| Fake-host | Every tool works end to end against the fake host, including every declared error path | Every pull request |
| Fake fidelity | The fake host behaves like the real host, checked against recordings from live acceptance | Every pull request (against stored recordings) |
| Golden engineering | Code-pack checks and calc functions match worked examples and program outputs within tolerance | Every pull request |
| Property | Physical sense holds over generated inputs (Hypothesis, CI profile with `derandomize=True`) | Every pull request |
| Workflow | Workflows run against real server processes in fake-host mode, including decisions, approvals and resumption | Every pull request in `eng-harness` |
| Replay | Recorded journals replay without divergence | Every pull request in `eng-harness` |
| Mutation | Tests detect injected faults: on changed R1 and R2 modules for every pull request; full run before release | Pull requests (changed modules), release (full) |
| Decision evaluation | Decision points meet their agreement and calibration thresholds | On change of a decision point, a model, or a provider |
| Performance | Overhead targets hold (server under 50 ms, engine under 20 ms per step at p95) | Nightly and before release |
| Live acceptance | The real host program behaves as the tools assume | By the owner before each release that touches host code (S7) |

## 2. Thresholds (CI fails below them)

| Repository | Line | Branch | Other |
|---|---|---|---|
| `eng-contract` | 95% | 90% | Mutation score at least 80% for units and references |
| `structural-codes` | 95% | 90% | Every check has worked examples; mutation score at least 80% |
| MCP servers | 85% | 75% | Every tool and every declared error path has a fake-host test |
| `eng-harness` | 85% | 75% | Every workflow has a fake-host workflow test and a replay test |
| C# components | 80% of separable logic | — | Host behavior covered by live acceptance |

Coverage is a floor, not a goal. Reviewers check that tests assert behavior from the spec, not implementation details.

## 3. Test rules

- Tests are deterministic: no network, no clock, no randomness without a fixed seed, no host programs.
- No rerun-on-failure plugins. A flaky test is fixed or quarantined under [12](12-operations.md) §3.
- **Suppression ratchet**: the counts of `noqa`, `type: ignore`, `pragma: no cover`, skip and expected-failure markers
  are stored in `.gate/ratchet.json` and may only go down. Every skip or expected failure names an open issue and an
  expiry date; CI fails when the date has passed.
- Test collection hooks (`conftest.py` collection modifiers) may not deselect tests.
- Fixtures are small and committed; real project data is never committed (synthetic or owner-approved anonymized
  models only).
- Floating-point comparisons use explicit tolerances stated in the spec.

## 4. Fakes and recordings

- Every host port has a fake implementation in the same repository.
- Live acceptance scripts record the real host's responses for a fixed set of operations (sanitized), into
  `acceptance/recordings/<host>-<version>/`, with a hash manifest.
- Fake fidelity tests run the same operations against the fake and compare with the recordings. A mismatch means the
  fake is wrong, and it is fixed before anything that depends on it.

## 5. Golden engineering tests

- Expected values live in data files, never inline in test code. Each case has a non-empty `source` (citation) field,
  checked by lint. No copied text.
- A change in a golden output is never "updated to match". It requires a golden diff report, a verification record
  and owner approval ([10](10-engineering-verification.md) §5). Golden data files are protected paths.

## 6. Live acceptance (S7)

- Scripted per toolset in `acceptance/scripts/`, run by the owner on the real host from a normal terminal, before
  each release that changes host-facing code.
- **The script writes the record itself** ([templates/acceptance-record.md](templates/acceptance-record.md)): commit
  SHA, package version, host program and build, script version, results, recording hashes. Records are protected paths;
  only the owner commits them.
- The release workflow blocks unless a passing record exists for every host version in `SUPPORT.md`, at a commit that
  includes all host-facing changes since the previous release.

## 7. Evaluations for decision points

- Each decision point keeps a labeled set (owner decisions) in the harness repository's `evals/`, anonymized.
- The evaluation reports agreement above threshold, calibration, abstention rate and latency per provider and model.
- Thresholds are in [12-decision-layer](../docs/architecture/12-decision-layer.md) §6.

## 8. The local gate

Every repository runs the shared gate from the pinned `eng-dev-gate` development dependency
([11](11-repository-standard.md) §4):

```
uv run eng-gate check
```

It runs everything that can run on the workstation: format check, lint, types, forbidden-pattern lint, suppression
ratchet, unit, contract, fake-host, golden, property and workflow tests with coverage, changed-module mutation tests,
generated-document freshness, and the dependency license check. CI runs the same command plus the jobs that need the
pull request context (`gate-check`, `risk-floor`, `test-first`, CI reviewers, secret scan, Windows tests, build). The
pull request links its CI run; pasted local output is not evidence.

## 9. Test-first check

The `test-first` CI job takes the pull request's first `test:` commit, applies its test changes to the base branch, and
runs the new or changed tests: they must fail there and pass at the pull request's head. Refactor pull requests
(`refactor:`) must instead change no test files. Documentation and chore pull requests are exempt.
