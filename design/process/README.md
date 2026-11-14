# Development Process

Status: Proposed · Applies to: every package and repository, every contributor, human or AI agent

This process is written as if thousands of developers contributed, because at the speed AI agents write code, that is
effectively the situation. Every rule exists to stop one failure that already happened or that is expensive to undo in
engineering software: improvised code, untested numbers, silent assumptions, unreviewed changes. Wherever a machine can
check a rule, a machine checks it ([ADR-0021](../docs/adr/0021-agent-agnostic-ci-enforced-process.md)).

During incubation ([ADR-0001](../docs/adr/0001-independent-repositories-private-first.md)), "repository" in these
documents means a package directory of the `eng-platform` workspace; repository-level files (CI, branch protection,
`CODEOWNERS`) exist once at its root. Until the owner sets up the identities and branch protection of
[11](11-repository-standard.md) §6, the workspace runs in bootstrap mode
([ADR-0028](../docs/adr/0028-build-v1-in-this-repository.md)).

## The ten golden rules

1. **No code without an approved spec and plan on `main`.** Trivial changes and the project lane excepted
   ([01](01-lifecycle.md) §2, §9).
2. **Tests first.** The first commit of every task holds failing tests; CI checks that they fail without the code.
3. **Never invent an engineering number.** Every constant has a cited source; every value has a provenance.
4. **Never improvise a missing capability.** In live work, log it in the task log and continue with what is possible;
   build it as a permanent tool through the project lane only when the owner asks ([01](01-lifecycle.md) §9, §10);
   outside live work, file a gap report ([02](02-work-items.md) §5).
5. **Stay inside the plan task**: its files, its size budget, its session budget.
6. **Nobody approves their own work.** Reviews that count are run by CI or given by the owner.
7. **CI is the definition of done.** Nothing bypasses CI; nobody bypasses branch protection. The only commits that
   reach the integration branch without a pull request are log-only commits
   ([ADR-0034](../docs/adr/0034-task-log-by-default.md) D5) and, in bootstrap mode, the lead's bookkeeping commits;
   they are checked after the push.
8. **uv only for Python.** No pip, poetry, conda or manual virtual environments.
9. **Stay inside your repository.** No writes to other repositories, system settings, program folders or deployment
   targets; no instructions or memories written outside the repository.
10. **Report honestly.** Say what was verified, with evidence, and what was not.

## Documents

| # | Document | Content |
|---|---|---|
| 01 | [Lifecycle](01-lifecycle.md) | Stages, gates and how they are recorded, tiers, risk classes, risk floor |
| 02 | [Work items](02-work-items.md) | Issues, labels, readiness, done, gap reports |
| 03 | [Specs and design review](03-specs-and-design-review.md) | Spec types, where they live, review checklists |
| 04 | [Implementation rules](04-implementation-rules.md) | Branches, commits, TDD, coding standards, dependencies |
| 05 | [Testing and verification](05-testing-and-verification.md) | Test layers, thresholds, fakes, golden data, live acceptance, the local gate, the test-first check |
| 06 | [Review and merge](06-review-and-merge.md) | CI reviewers, protected paths, branch protection, severity |
| 07 | [Release and open source](07-release-and-open-source.md) | Versions, changelogs, splitting packages out, going public |
| 08 | [Agent operating rules](08-agent-operating-rules.md) | How AI agents must behave in every session |
| 09 | [Tooling map](09-tooling-map.md) | Which skills, agents and commands support each stage, and their restrictions |
| 10 | [Engineering verification](10-engineering-verification.md) | Rules for anything that affects engineering output |
| 11 | [Repository standard](11-repository-standard.md) | Required files, layout, the shared gate, CI jobs, identities |
| 12 | [Operations](12-operations.md) | Emergencies, flaky tests, CI failures, audits, dependency updates, owner digest |
| — | [templates/](templates/) | Every template referenced above |

## How this reaches each package

Each package's `AGENTS.md` is rendered by `eng-gate agents render` from
[templates/AGENTS.template.md](templates/AGENTS.template.md) and the package's `.gate/agents.yml`. CI fails if the
committed file differs from the rendering. When this process changes, the template's version changes and every package
is re-rendered in the same change.
