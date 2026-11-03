# 06. Review and Merge

## 1. Reviews

| # | Review | By | Counts toward G3 |
|---|---|---|---|
| 1 | Self-review checklist in the PR template | Author | No |
| 2 | Author-side review tools (multi-agent review, adversarial review loops) | Started by the author, during S5 | **No.** Pre-checks only |
| 3 | CI reviewer | A CI workflow that runs the pinned reviewer prompts from `eng-dev-gate` on the diff, the issue, the spec and the plan, and posts its verdict under the reviewer identity | Yes |
| 4 | Second CI reviewer of a different model family | Same workflow, another provider; its family must differ from the `Assisted-by` families in the pull request | Yes, required for R1 and R2 |
| 5 | Security reviewer | CI reviewer with the security prompt | Yes, required for R3 and when the diff touches input handling, file paths, network, pipes, secrets or dependencies |
| 6 | Owner review | The owner's account, through `CODEOWNERS` and §5 of [01](01-lifecycle.md) | Yes, where required |

A review counts only if CI started it or the owner gave it. The author chooses neither the files the CI reviewers see
nor their rubric. A CI reviewer verdict of CRITICAL or HIGH fails its required check.

## 2. What reviewers check

Beyond general code quality:

- [ ] The change does what the spec says, and only that; the files match the plan task.
- [ ] Every acceptance criterion has a test that would fail without the change.
- [ ] Principles P1 to P12 hold; no escape hatches; nothing from the forbidden list ([04](04-implementation-rules.md) §8).
- [ ] Units and suffixes are correct; conversions use `eng-contract.units` only.
- [ ] Errors use contract codes; no swallowed exceptions; no silent fallbacks.
- [ ] Engineering constants are cited; tolerances come from the spec or the design basis.
- [ ] Public schemas, kinds and tool names follow the contract and ADR-0008; version impact matches the changelog.
- [ ] Generated documents are current; human documents are updated.

## 3. Finding severity

| Severity | Examples | Merge rule |
|---|---|---|
| CRITICAL | Wrong or unverified engineering output, data loss or model corruption, secret exposure, contract break without ADR | Blocks |
| HIGH | Missing tests for a criterion, unhandled error path, unit ambiguity, unsafe write behavior | Blocks |
| MEDIUM | Maintainability, naming, minor duplication | Fix, or open a linked follow-up issue before merge |
| LOW | Style preferences not covered by tooling | Optional |

A disputed CRITICAL or HIGH finding is decided by the owner, not by the author.

## 4. Protected paths (`CODEOWNERS`: owner review required)

Process and enforcement:
`.github/**`, `CODEOWNERS`, `AGENTS.md`, `.gate/**` (risk map, ratchet), `pyproject.toml`, `uv.lock` (except bot
patch updates, [12](12-operations.md) §6), and every test or tool configuration file that can override it:
`conftest.py` (any level), `pytest.ini`, `setup.cfg`, `tox.ini`, `ruff.toml`, `.ruff.toml`, `mypy.ini`,
`.coveragerc`, `.pre-commit-config.yaml`.

Test oracles:
`acceptance/records/**`, `acceptance/recordings/**`, golden data files, decision evaluation sets.

Engineering content:
code-pack checks, `approvals.yaml`, calc functions, shipped templates, decision rules and policies.

Contracts:
the whole `eng-contract` repository; each server's generated schema snapshot (`docs/tools/schema.json`).

Specs and plans are verified by `gate-check` rather than `CODEOWNERS`, because their required approver depends on
their risk ([01](01-lifecycle.md) §5).

## 5. Branch protection on `main` (every repository)

- Pull request required; direct pushes disabled; **no bypass for anyone**, the owner's account included.
- Required status checks: the shared gate, `gate-check`, `risk-floor`, `test-first`, CI reviewers, security scan,
  Windows tests, build ([11](11-repository-standard.md) §5).
- Branch must be up to date with `main` before merge.
- At least one approval from a non-author identity; `CODEOWNERS` review where paths match; stale approvals dismissed
  on new commits.
- Linear history; squash merge only; force pushes and deletion of `main` disabled.

## 6. After merge

- If `main` breaks, or engineering output is found wrong, revert first through the emergency path
  ([12](12-operations.md) §1), then fix in a new pull request.
- The issue closes only when the Definition of Done is met ([02](02-work-items.md) §4).
