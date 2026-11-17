# 09. Tooling Map

The checklists in documents 01 to 08 and 10 to 12 define what each stage must produce. The tools below help produce
it. If a tool is not available in your environment, follow the checklist by hand: the checklist is the norm, the tool is
an accelerator.

Pinned versions: ECC 2.2.3; gstack at the version recorded in the repository's `AGENTS.md` when set up. Upgrades are
pull requests to this document. Notation: `/name` is a command, *name* is a skill, **name** is a review or helper agent.

## 1. By stage

| Stage | Norm | ECC | gstack | Other skills |
|---|---|---|---|---|
| S0 Intake | Issue from template, claimed | *github-ops*; `/epic-decompose`, `/epic-validate`, `/epic-claim` | `/spec` (idea to issue) | |
| S1 Discovery | Problem, criteria, reuse research | `/prp-prd`; *search-first*; *deep-research*; **docs-lookup**; **code-explorer** | `/office-hours`; `/plan-ceo-review` | *brainstorming*; *requirements-analysis* |
| S2 Spec | Spec file from template; ADR if needed | *contract-first*; *api-design*; *agent-harness-construction* (tool design for agents); *architecture-decision-records*; **architect**, **code-architect**; *council* | `/plan-eng-review`; `/plan-devex-review` (tool and CLI ergonomics) | *premortem*; *strategy-red-team*; *domain-driven-design* |
| S3 Plan | Plan file with tasks, files, size estimates, session budgets | `/plan`; `/prp-plan`; *blueprint*; **planner** | `/autoplan` | *writing-plans* |
| S4 Implement | `test:` commit first, then code | `/orch-add-feature`, `/orch-change-feature`, `/orch-fix-defect`, `/orch-refine-code` (only after G2, see §2); `/prp-implement`; *tdd-workflow*, **tdd-guide**; *python-patterns*, *python-testing*, *dotnet-patterns*, *csharp-testing*, *error-handling*, *hexagonal-architecture*; `/build-fix` | `/investigate` | *test-driven-development*; *executing-plans*; *subagent-driven-development*; *using-git-worktrees*; *systematic-debugging* |
| S5 Pre-checks | `uv run eng-gate check` | *verification-loop*; `/checkpoint`; `/test-coverage`; `/quality-gate` (single file); author-side `/review-pr`, `/code-review`, `/santa-loop`, **python-reviewer**, **csharp-reviewer**, **silent-failure-hunter**, **pr-test-analyzer**, **type-design-analyzer**, **security-reviewer**, **commit-reviewer** | `/review`; `/codex`; `/cso`; `/health` | *verification-before-completion* |
| S6 Pull request | PR from template; CI reviewers | `/pr` (open the PR only) | `/ship` (open the PR only, see §2) | |
| S7 Live acceptance | Owner runs scripts | | | |
| S8 Release | Release checklist | `/update-docs`; **doc-updater**; *git-workflow*; *opensource-pipeline* (**opensource-forker**, **opensource-sanitizer**, **opensource-packager**) | `/document-release` | |
| S9 Learn | Lessons as issues | *rules-distill* (proposals as pull requests) | `/retro` | |

The CI reviewers of S6 reuse the review prompts of the agents listed in S5, pinned in `eng-dev-gate`; running them from
CI is what makes them independent.

## 2. Restrictions on specific tools

| Tool | Restriction | Reason |
|---|---|---|
| `/orch-*` pipelines | Start only after G2; their internal plan approval is not G2 | They plan and code in one session |
| `/prp-prd`, `/prp-plan`, `/code-review` | Their output is copied into the repository's spec, plan or PR templates under `docs/`; files they write elsewhere are scratch | Gates are verified from `docs/` only |
| `/build-fix`, `/refactor-clean`, automatic fixers | Full diff reviewed before commit; no added suppressions | They can add ignores or delete code (A5) |
| `/santa-loop`, `/review-pr`, `/review`, `/codex` | Pre-checks only | Started by the author (A7) |
| `/ship` | Opening the pull request only; no version or changelog edits | Versions change only at release ([07](07-release-and-open-source.md)) |
| `/land-and-deploy` and any self-merge flow | Forbidden | A7 |
| `/learn` (ECC, gstack), `/save-session`, `/context-save` | Owner only, outside agent work sessions | They write instructions or state outside the repository (A21) |
| `/careful`, `/guard`, `/freeze`, *safety-guard*, *gateguard* | Recommended in every agent session; `/freeze` set to the repository folder | Local guard rails; CI is still the enforcement |

## 3. Cross-cutting

| Need | ECC | gstack | Other |
|---|---|---|---|
| Decision-point evaluations, agent reliability | *eval-harness*; *agent-eval* | | |
| Documentation that does not rot | *living-docs-governance*; *docs-governance* | `/document-generate` | |
| Dead code and simplification | `/refactor-clean`; **code-simplifier** | `/test-audit` | *simplify* |
| Agent configuration security | `/security-scan` | | |
| Harness UI quality | | `/qa`, `/design-review` | *impeccable*; *web-design-guidelines* |
| MCP server concepts | *mcp-server-patterns* (TypeScript-oriented; for Python code use the official Python SDK documentation through **docs-lookup**) | | |

## 4. Rules for using tools

- A tool's output never replaces a gate.
- Tools that edit code follow the same rules as any author: plan task, tests first, local gate, CI review.
- When two tools disagree, the stricter result applies until a reviewer decides.
