# BUILD-STATUS: Eng-Agent platform v1

The lead engineer's state file for the v1 build ([ADR-0028](design/docs/adr/0028-build-v1-in-this-repository.md)).
After a restart or a context compaction, read this file and `git log origin/build/v1` before anything else.

- Integration branch: `build/v1` · Draft pull request to `main`: [AbdulkareemSasah/Eng-Agent#2](https://github.com/AbdulkareemSasah/Eng-Agent/pull/2)
- Mode: bootstrap (ADR-0028 §4). Checks that need the owner or another identity report `awaiting owner`.
- Live steps: [LOCAL-TESTING.md](LOCAL-TESTING.md). Nothing that needs a host program is claimed as working.

## 1. Environment facts (recorded at the start)

| Item | Value |
|---|---|
| Python | CPython 3.14.6 through uv 0.11.32 (3.15 is beta in uv); pinned 3.14 (ADR-0028 §5) |
| Host programs, .NET SDK | Not available in the build environment; all host work is "needs local test" |
| Sasaah | Read-only checkout at a fixed commit; servers and tools read from source |
| ECC skills and agents (process/09) | **Not available here**: no `ecc:plan`, `ecc:prp-plan`, `ecc:planner`, `ecc:architect`, `ecc:tdd-workflow`, `ecc:tdd-guide`, `ecc:code-review`, `ecc:python-review`, `ecc:code-reviewer`, `ecc:python-reviewer`, `ecc:csharp-reviewer`, `ecc:security-reviewer`, `ecc:silent-failure-hunter`, `ecc:pr-test-analyzer`, `ecc:type-design-analyzer`, `ecc:verification-loop`, `ecc:quality-gate`, `ecc:security-scan`, `ecc:architecture-decision-records`. The same practices are applied by subagents with explicit checklists (planning, test-first, review lenses: correctness, Python, security, silent failures, tests, type design) |
| Built-in skills available | `code-review`, `security-review`, `simplify` (used as author-side pre-checks only, process/09 §2) |
| GitHub | Pull requests, CI status and merges through the GitHub MCP tools; no `gh` except search |

## 2. Phases and packages

| Phase | Package or item | Status |
|---|---|---|
| 0 | ADR-0028, hub moved to `design/` | done (f434a41) |
| 0 | Workspace root (`pyproject.toml`, AGENTS.md, CI skeleton, `.gate/`) | in progress |
| 0 | `eng-contract` 0.1 | spec in progress |
| 0 | `tools/eng-dev-gate` 0.1 | spec in progress |
| 0 | CI workflows (all jobs of process/11 §5) | not started |
| 0 | Spike S-12 (Sasaah tool inventory from catalog sources) | in progress |
| 0 | Spike S-10 (replay; Job Object termination) | in progress |
| 0 | Spikes S-02 and S-04 (scripts for local runs) | not started (needs S-12) |
| 1 | `eng-harness` (engine, journal, replay, ctx, CSI adapter, calcs, templates, basis, decisions, CLI, progress, approval page, run report, edit-cycle workflow) | not started |
| 2 | `structural-codes` (core, `aci318-14`, `sbc304-2018` draft), SAFE via CSI adapter, providers (Jev shadow, PydanticAI), `design_isolated_footing` | not started |
| 3 | `sasaah-revit-mcp` adapter, SAP2000 via CSI adapter, column checks, column workflow | not started |
| 4 | `sasaah-idea-mcp` adapter; desktop products (overlap with Sasaah to the owner queue) | not started |

## 3. Tasks

One task is one pull request into `build/v1` (process/02), reviewed by a subagent that is not its author, merged by
squash after CI is green. Ids are `B-NNN`; branches are `<type>/b<NNN>-<slug>`.

| Id | Task | Author (model, effort) | Reviewer (model, effort) | PR | Status |
|---|---|---|---|---|---|
| B-001 | ADR-0028; move the hub into `design/`; update affected documents | lead | — (owner decision record) | direct commit f434a41 | done |
| B-002 | Workspace root: uv workspace, `.python-version`, README, AGENTS.md, CLAUDE.md, `.gate/`, `.github/` skeleton | sonnet, low | opus, low | — | in progress |
| B-003 | `eng-contract` spec and plan (draft) | opus, medium | opus, medium (R2) | — | in progress |
| B-004 | `eng-dev-gate` spec and plan (draft) | sonnet, high | opus, low | — | in progress |
| B-005 | Spike S-12: Sasaah tool inventory from the catalog sources | sonnet, medium | opus, low | — | in progress |
| B-006 | Spike S-10: replay of async blocks; Job Object termination | sonnet, high | opus, low | — | in progress |
| B-007 | Spikes S-02 and S-04: scripts for local runs | sonnet, medium | opus, low | — | blocked on B-005 |

## 4. Decisions by the lead

| Id | Decision | Why |
|---|---|---|
| D-1 | Tasks are tracked in this file (`B-NNN`), not GitHub issues, during bootstrap; pull requests name `Work-Item: B-NNN` and `Plan-Task:` | One identity; no notifications; the gate reads the plan files |
| D-2 | Phase 0 spikes live in the root `spikes/` folder | Their target package (`eng-harness`) is created when phase 1 starts (19, R4) |
| D-3 | Commits carry `Assisted-by: anthropic/claude` (family and model line, no version identifiers) | process/04 §3 trailer, without model version identifiers in the repository |
| D-4 | The lead updates `BUILD-STATUS.md` and `LOCAL-TESTING.md` directly on `build/v1`; task branches do not touch them; packages list their live steps in `docs/local-testing.md` | Avoids merge conflicts between parallel tasks |
| D-5 | Fakes of the Sasaah servers are test doubles inside `tests/` (synthetic MCP servers built from the tool schemas), never shipped or installed | "Build no MCP server for a host program" applies to product code; the fakes are what the owner asked tests to run against |
| D-6 | Subagent reviews are recorded in the pull request description (section "Review"), not as comments | Durable evidence without notifications |
| D-7 | A spec and its plan may share one documents-only pull request, reviewed together | process/01 §4 forbids mixing specs or plans with other changes; reviewing both together keeps them consistent |
| D-8 | B-002 (workspace root) is built from ADR-0028 §1 and process/11 directly, without a plan file | No gate tooling exists yet to verify a plan; the review still applies |
| D-9 | A phase's specs may start once the specs of the packages it depends on are merged; its code starts when the previous phase's packages are done | Keeps the phase order (19, R4) without idling while the last tasks of a phase finish |

## 5. Problems

| Id | Problem | Handling |
|---|---|---|
| — | none yet | — |

## 6. Owner queue

Approvals and answers only the owner can give. Each item has the lead's recommendation; the build took the safest
option and continued.

### 6.1 Approvals

| Id | Item | Recommendation |
|---|---|---|
| OQ-1 | ADR-0001 to ADR-0023 (not superseded) are still `Proposed`; v1 follows them as the working design, with ADR-0024 to ADR-0028 overriding them | Review and accept or amend, starting with ADR-0001 and ADR-0021 (amended by ADR-0028) |
| OQ-2 | Identities, a paid GitHub plan and branch protection (process/11 §6) end bootstrap mode | Set up before merging `build/v1` to `main` |
| OQ-3 | CI reviewer providers of two model families (process/06 §1) | Choose at identity setup; until then every second-family review is `awaiting owner` |

### 6.2 Proposed ADRs

| Id | ADR | Recommendation |
|---|---|---|
| — | none yet | — |

### 6.3 Gaps (engineering content left draft or not implemented)

| Id | Gap | Recommendation |
|---|---|---|
| — | none yet | — |

### 6.4 Questions

| Id | Question | Lead's recommendation and what the build did |
|---|---|---|
| OQ-Q1 | License: ADR-0023 (Apache-2.0) is `Proposed`, so no `LICENSE` file is added | Accept Apache-2.0; then add `LICENSE` files. The build adds none |
| OQ-Q2 | Phase time boxes (19 §1) are not set for this build | Set them for the local test stage |
| OQ-Q3 | Benchmark B-1 (18 §5) is needed before the first release | Prepare it before the local A4 run |
| OQ-Q4 | The edit-kind list of the first workflow (18 §2; overview §14 item 13) needs the owner's confirmation | Confirm in the workflow spec review; the build implements the listed kinds that S-12 finds tools for |
| OQ-Q5 | The tool-manifest exporter of Sasaah Agent (19, S-12) is not available here; the inventory is built from the catalog sources | Regenerate with the exporter during local testing and compare |

### 6.5 Sasaah pull requests

| Id | Pull request | Why |
|---|---|---|
| — | none | — |
