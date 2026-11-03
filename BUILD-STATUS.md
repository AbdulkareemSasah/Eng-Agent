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
| 0 | Workspace root (`pyproject.toml`, AGENTS.md, CI skeleton, `.gate/`) | done (B-002, B-009 in review) |
| 0 | `eng-contract` 0.1 | spec in progress |
| 0 | `tools/eng-dev-gate` 0.1 | spec in progress |
| 0 | CI workflows (all jobs of process/11 §5) | not started |
| 0 | Spike S-12 (Sasaah tool inventory from catalog sources) | report written; merging |
| 0 | Spike S-10 (replay; Job Object termination) | report written; merging; Windows result pending the Windows CI job |
| 0 | Spikes S-02 and S-04 (scripts for local runs) | queued (B-007) |
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
| B-002 | Workspace root: uv workspace, `.python-version`, README, AGENTS.md, CLAUDE.md, `.gate/`, `.github/` skeleton | sonnet, low (second attempt, P-1) | opus, low | [#7](https://github.com/AbdulkareemSasah/Eng-Agent/pull/7) | done (ea33ff9) |
| B-003 | `eng-contract` spec and plan (draft) | opus, medium; fixes: opus, medium (2 rounds) | opus, medium (R2) | [#3](https://github.com/AbdulkareemSasah/Eng-Agent/pull/3) | in review |
| B-004 | `eng-dev-gate` spec and plan (draft) | sonnet, high; fix: sonnet, high | opus, low | [#4](https://github.com/AbdulkareemSasah/Eng-Agent/pull/4) | in review |
| B-005 | Spike S-12: Sasaah tool inventory from the catalog sources | sonnet, medium; report committed by the lead (P-2) | opus, low | [#5](https://github.com/AbdulkareemSasah/Eng-Agent/pull/5) | in review |
| B-006 | Spike S-10: replay of async blocks; Job Object termination | sonnet, high; report committed by the lead (P-2) | opus, low | [#6](https://github.com/AbdulkareemSasah/Eng-Agent/pull/6) | in review |
| B-007 | Spikes S-02 and S-04: scripts for local runs | sonnet, medium | opus, low | — | queued (wave 2) |
| B-008 | Hub: stale 04 section references; ADR-0029 (Proposed) eng-contract 0.1 details | sonnet, medium | opus, low | — | queued (wave 2) |
| B-009 | Root workspace members listed explicitly (D-10) | lead | opus, low | [#8](https://github.com/AbdulkareemSasah/Eng-Agent/pull/8) | in review |
| B-010 to B-025 | `eng-contract` 0.1, plan tasks T1 to T16 (serialized) | sonnet, low to high per task | opus, medium (R2) | — | queued (wave 2) |
| B-030 to B-055 | `eng-dev-gate` 0.1, plan tasks T1 to T26 (dependency graph) | sonnet, low to high per task | opus, low; medium for T13, T14, T16 to T18, T26 | — | queued (wave 2) |
| B-060 | `eng-harness` spec and plan 0001 engine; ADR-0030 (Proposed) | opus, medium | opus, medium | — | queued (wave 2) |
| B-061 | `eng-harness` spec and plan 0002 servers and adapters; ADR-0031, ADR-0032 (Proposed) | opus, medium | opus, medium | — | queued (wave 2) |
| B-062 | `eng-harness` spec and plan 0003 calcs | opus, medium | opus, medium | — | queued (wave 2) |
| B-063 | `eng-harness` spec and plan 0004 templates and design basis | sonnet, medium | opus, medium | — | queued (wave 2) |
| B-064 | `eng-harness` spec and plan 0005 decision layer | sonnet, medium | opus, low | — | queued (wave 2) |
| B-065 | `eng-harness` spec and plan 0006 command line, progress, approval page, run report | sonnet, high | opus, medium (security) | — | queued (wave 2) |
| B-066 | Model edit cycle: workflow spec, block spec and plan 0007 | opus, medium | opus, medium | — | queued (wave 2) |

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
| D-10 | The root uv workspace lists its members explicitly; each package's skeleton task adds its folder (B-009) | A package folder holds its spec and plan before its `pyproject.toml` exists, and uv refuses a glob that matches such a folder |
| D-11 | Tasks run as workflow chains: writer, independent review with up to two fix rounds, then a mechanical merge step that waits for CI and squash-merges only on an approving review and green CI; at most five writers at once | Serialized chains (the 16 `eng-contract` tasks) do not stall between tasks; the merge rule stays the lead's |

## 5. Problems

| Id | Problem | Handling |
|---|---|---|
| P-1 | The first five worktrees of wave 1 were created from the Sasaah checkout (the lead's shell was there at launch); B-002 stopped, the others cloned Eng-Agent into the scratchpad. Nothing reached Sasaah | Launch every agent from `/home/user/Eng-Agent`; every prompt checks `git remote -v` first |
| P-2 | Subagents' write tool refuses files it treats as report files (`REPORT.md`) | The lead commits such files from the drafts the subagents return; prompts say not to work around a refusal |
| P-3 | Worktrees are created from the lead's current folder when each agent starts, not when its workflow starts; two reviews failed while the lead's shell was outside the repository | The lead's shell stays in `/home/user/Eng-Agent` while workflows run (other folders only in subshells) |
| P-4 | The root workspace glob broke `uv sync` once a package folder held only docs (CI red on #3 and #4) | Fixed by B-009 (D-10) |

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
| OQ-A1 | Hub ADR "eng-contract 0.1 details": the details the contract spec adds to 04 (marked [added], spec Q1) | To be written as `Proposed` once the spec merges; accept after review |
| OQ-A2 | ADR amending ADR-0014 (from S-10): replay by step path, block version and code hash, in-flight reconciliation events, durability policy, one engine per run, one Job Object per server with host programs breaking away | To be written as `Proposed` with the engine spec |
| OQ-A3 | ADR: `model_locked` after analysis versus `HOST_LOCKED`, and an approved unlock step (S-12 gap S12-G3) | To be written as `Proposed` with the CSI adapter spec |
| OQ-A4 | ADR amending 04 §3.3: a harness-side model identity when the host cannot stamp one (S12-G6) | To be written as `Proposed` with the CSI adapter spec |
| OQ-A5 | `eng-dev-gate` package ADR-0001: runtime dependencies PyYAML, Pydantic, ruff, mypy, pytest, coverage (gate spec) | Approve |

### 6.3 Gaps (engineering content left draft or not implemented)

| Id | Gap | Recommendation |
|---|---|---|
| OQ-G1 | CSI `Ton` unit systems: metric tonne-force or short ton-force? Until confirmed, `eng-contract` refuses them (contract G-1) | Confirm from the CSI API documentation or a local check |
| OQ-G2 | CSI mass and time units are not mapped in `eng-contract` 0.1 (G-2) | Map when an adapter needs masses |
| OQ-G3 | Sign and axis convention of `forces.member_end/1` (G-3) | CSI local axes 1-2-3 (`host_local/1`), confirmed at the first local run |
| OQ-G4 | Exact table and section numbers of the SI Brochure and NIST SP 811 citations for unit factors (G-4) | Confirmed or removed in contract task T4; never guessed |
| OQ-G5 | No server version or build id in any Sasaah server (S12-G1) | The harness pins the Sasaah commit and hashes the executable; ask Sasaah for `serverInfo.version` and a tool-list hash |
| OQ-G6 | Analysis and design are synchronous; no start-and-poll (S12-G2) | Per-run larger call timeout sized by S-02, then `TIMEOUT_UNKNOWN_OUTCOME` and reconciliation |
| OQ-G7 | No batch edit tools (S12-G4) | Bounded per-object calls in the adapter; typed batch tools in Sasaah later |
| OQ-G8 | No seismic-parameter tool, no load-pattern change or delete, typed slab section not exposed (S12-G5) | Out of the v1 edit-kind list; gap report to Sasaah (its `02_Engines` is frozen outside spec 005, so the build opens no pull request) |
| OQ-G9 | `csi_db_tables_apply` stays visible under `DisableScript` (S12-G7) | The allowlist and the tool-list fingerprint keep it out; ask Sasaah for a switch that hides it |
| OQ-G10 | Read-back gaps for area thickness, restraints and distributed frame loads (S12-G8) | Typed reads of pinned table keys through `csi_db_table_read` (read only), confirmed locally |
| OQ-G11 | `csi_define_*` tools take untyped specs (S12-G10) | Allow with an adapter-pinned list of methods and keys |
| OQ-G12 | Revit: no save, analytical-model or move tools; timeout code lost; an internal retry may duplicate writes (S12-G11) | Phase 3 adapter works around what it can; the rest are gaps |
| OQ-G13 | IDEA: stub mode, no check-model, a load unit missing, scripts on by default (S12-G12) | Phase 4 adapter rules; start the server with `--disable-script` |
| OQ-G14 | `tools/etabs-model/classify-columns.ps1` embeds engineering thresholds (S12-G13) | Not adopted by the harness until the owner reviews it |

### 6.4 Questions

| Id | Question | Lead's recommendation and what the build did |
|---|---|---|
| OQ-Q1 | License: ADR-0023 (Apache-2.0) is `Proposed`, so no `LICENSE` file is added | Accept Apache-2.0; then add `LICENSE` files. The build adds none |
| OQ-Q2 | Phase time boxes (19 §1) are not set for this build | Set them for the local test stage |
| OQ-Q3 | Benchmark B-1 (18 §5) is needed before the first release | Prepare it before the local A4 run |
| OQ-Q4 | The edit-kind list of the first workflow (18 §2; overview §14 item 13) needs the owner's confirmation | Confirm in the workflow spec review; the build implements the listed kinds that S-12 finds tools for |
| OQ-Q5 | The tool-manifest exporter of Sasaah Agent (19, S-12) is not available here; the inventory is built from the catalog sources | Regenerate with the exporter during local testing and compare |
| OQ-Q6 | Contract: refuse a workspace whose location cannot be classified (spec Q2) | Yes; revisit after local tests |
| OQ-Q7 | Contract: envelopes and records forbid unknown fields (Q3) | Keep while packages upgrade together; decide by ADR before the first public release |
| OQ-Q8 | Contract: should verdicts recompute `ratio = demand / capacity`? (Q5) | No: it needs a tolerance, which is engineering content |
| OQ-Q9 | Seismic load parameters: a harness kind `harness.seismic_parameters/1` (contract Q6) | Harness-owned until a second consumer needs it; seismic edits wait for a Sasaah tool (OQ-G8) |
| OQ-Q10 | Gate: add a `tool` row (95/90/80) to process/05 §2 for `eng-dev-gate` (gate Q2) | Yes, in a process change that lists the `AGENTS.md` files to re-render |
| OQ-Q11 | Gate: numeric literals in checks, calcs, blocks and rules: only integer indexes and comparisons with `len` are allowed (gate Q5) | Keep only those two exceptions |
| OQ-Q12 | Gate: the "bandit subset" of process/11 §3 is undefined; the gate uses all `S` rules except `S101` in tests (Q6) | Accept |
| OQ-Q13 | Gate: how the owner approves a spec or plan in bootstrap mode (Q7) | Commit the status change directly to `build/v1`, or switch bootstrap off first |
| OQ-Q14 | Gate: import rules for Python products are not defined in 03 §3 (Q9) | Define in the first Python product's spec |
| OQ-Q15 | Gate: host SDK module names for ETABS, SAFE, SAP2000 and IDEA for the forbidden-import rule (Q10) | Fill in after the first local runs |
| OQ-Q16 | Engine (S-10): after "not applied", retry with a new `op_id` or the old one? | Reuse the `op_id` where the server deduplicates; otherwise define "not applied" per adapter; decide with S-02 |
| OQ-Q17 | Engine (S-10): block version bump or recorded code hash for unfinished runs? | Record both: a hash change with the same version warns, a version change stops |
| OQ-Q18 | Stale section references in the hub: 01 P5 and P9, 05, 10 §3, 11 §12 and 17 §2 cite the wrong 04 sections | Fix in a hub documents change (task queued) |
| OQ-Q19 | 17 §4 asks for the current and the previous Python minor version; ADR-0028 §5 pins 3.14 only | ADR-0028 applies for v1; amend 17 §4 when the owner accepts it |

### 6.5 Sasaah pull requests

| Id | Pull request | Why |
|---|---|---|
| — | none | — |
