# 11. Repository Standard

Every repository is created from this standard on the day its phase starts.

## 1. Required files

| File | Purpose |
|---|---|
| `README.md` | Purpose, install, quick start, requirements, limits |
| `AGENTS.md` | Rendered from [templates/AGENTS.template.md](templates/AGENTS.template.md) plus `.gate/agents.yml`; never edited by hand |
| Tool-specific instruction files (for example `CLAUDE.md`) | One line pointing to `AGENTS.md` ([templates/CLAUDE.template.md](templates/CLAUDE.template.md)) |
| `CONTRIBUTING.md` | Process summary, how to run the local gate, DCO once public |
| `LICENSE`, `THIRD_PARTY_NOTICES.md` | Apache-2.0 and dependency notices |
| `SECURITY.md` | How to report vulnerabilities and wrong engineering results |
| `SUPPORT.md` | Tested host versions matrix |
| `CHANGELOG.md` | Human-edited release notes |
| `.github/CODEOWNERS` | Protected paths ([06](06-review-and-merge.md) §4) |
| `.github/pull_request_template.md` | From [templates/pull-request.md](templates/pull-request.md) |
| `.github/ISSUE_TEMPLATE/` | Feature, bug, gap report |
| `.github/workflows/` | Thin callers of the reusable workflows in `eng-dev-gate` (§5) |
| `.github/dependabot.yml` | Dependency updates ([12](12-operations.md) §6) |
| `.gate/risk-map.yml`, `.gate/ratchet.json`, `.gate/agents.yml` | Risk floor, suppression ratchet, `AGENTS.md` inputs |
| `pyproject.toml`, `uv.lock`, `.python-version` | Project, locked dependencies, pinned Python (one version for the whole workspace, [ADR-0028](../docs/adr/0028-build-v1-in-this-repository.md)) |

## 2. Layout (Python repository)

```
<repo>/
  src/<package>/            code (servers: tools/, service/, host/, kinds/ per 05-mcp-server-standard)
  tests/
    unit/  contract/  fake_host/  golden/  property/  workflow/   (as applicable)
    data/golden/            expected values with sources (protected)
  acceptance/
    scripts/                live acceptance scripts the owner runs
    records/                records written by the scripts (protected)
    recordings/             sanitized host recordings for fake fidelity tests (protected)
  docs/
    specs/                  feature specs (and tools/specs/, workflows/ as applicable)
    plans/                  implementation plans
    tools/                  generated tools.md and schema.json
    adr/                    repository-local decisions
  spikes/                   throwaway spike code, excluded from the package and from coverage
  .gate/
```

C# components live in `addin/` or `plugin/` beside `src/`, with their own solution and test project.

## 3. Configuration baseline

- All tool configuration lives in `pyproject.toml`. Separate configuration files that override it are not used and
  are protected if they appear.
- `ruff` with a strict rule set (pycodestyle, pyflakes, isort, bugbear, pyupgrade, simplify, naming, bandit subset).
- `mypy --strict`.
- `pytest` with coverage thresholds from [05](05-testing-and-verification.md) §2; Hypothesis CI profile with
  `derandomize=True`.

## 4. The shared gate: `eng-dev-gate`

Process enforcement is code, and it lives in one repository so no repository can quietly weaken it:

- `eng-dev-gate` is a Python package (development dependency, pinned by tag) providing the `eng-gate` command:
  `check` (the local gate), `gate-check`, `risk-floor`, `test-first`, `ratchet`, `forbidden` (pattern lint),
  `agents render` and `agents drift`.
- It also holds the reusable GitHub workflows and the pinned CI reviewer prompts.
- Repositories pin a released tag. Upgrading the pin is a pull request to a protected path.
- Forbidden patterns (defaults): escape-hatch tool names and code paths; host SDK imports outside `host/`; I/O imports in
  harness block and rule modules; numeric literals in check, calc, block and rule modules (cited constants and basis
  references only); digits in language-model rationale schemas; `print`; collection hooks that deselect tests.
- Import rules between packages (layers, no internal modules) are checked here too
  ([03-repositories](../docs/architecture/03-repositories.md) §3).

## 5. CI jobs (all required for merge)

| Job | Runs on | Content |
|---|---|---|
| `gate` | Linux | `uv run eng-gate check` |
| `gate-check` | Linux | Spec and plan approved on `main`; plan task exists; changed files match the task; diff size reported as a notice, never failed; spec or plan pull requests change nothing else; approvals per [01](01-lifecycle.md) §5 |
| `risk-floor` | Linux | Recorded risk is at least the path-derived floor |
| `test-first` | Linux | [05](05-testing-and-verification.md) §9 |
| `ci-review` | Linux | CI reviewers ([06](06-review-and-merge.md) §1), posting under the reviewer identity; re-runs on new commits |
| `agents-drift` | Linux | `AGENTS.md` equals its rendering from the pinned template |
| `security` | Linux | Secret scan; dependency vulnerability audit. On a push to the integration branch: `secrets --range`, `push-scope` and `tasklog-lint` over the pushed commits ([ADR-0034](../docs/adr/0034-task-log-by-default.md) D5) |
| `windows` | Windows | Tests of adapters that only import on Windows (with fakes) |
| `build` | Linux (Windows for C#) | `uv build`; `dotnet build -warnaserror` and `dotnet test` for C# parts |

CI uses the official uv setup action with caching. CI never needs host programs. The `ci-review` job needs provider
keys as repository secrets; it does not run on pull requests from forks (outside contributors get the review when a
maintainer applies a label).

## 6. Identities and permissions

| Identity | Who uses it | Rights |
|---|---|---|
| Owner account | The owner only | Admin. Its token never exists in any agent environment; the one recorded exception is the log-only push on the owner's machine ([ADR-0034](../docs/adr/0034-task-log-by-default.md) D6) |
| Agent identity (GitHub App, or a machine user account) | Coding agents | Write to branches, open pull requests, comment, assign itself. No admin, no bypass, no settings, no secrets |
| Reviewer identity (GitHub App) | The `ci-review` workflow | Post reviews and status checks only |

Consequences: pull requests are authored by the agent identity, so the owner can approve them; nothing an agent posts
can be mistaken for the owner; an agent cannot change protection or merge with admin rights.

Branch protection, required reviews and `CODEOWNERS` enforcement on private repositories need a paid GitHub plan
(Pro for a personal account, or Team for an organization). This is a phase 0 setup item. Until it is done, the
workspace runs in bootstrap mode ([ADR-0028](../docs/adr/0028-build-v1-in-this-repository.md)).

## 7. GitHub settings at creation

- Visibility private; branch protection per [06](06-review-and-merge.md) §5; squash merge only; delete branches on merge.
- Labels per [02](02-work-items.md) §3.
- Secret scanning and push protection enabled; dependency alerts enabled.
- The scheduled owner digest workflow ([12](12-operations.md) §7) enabled.
