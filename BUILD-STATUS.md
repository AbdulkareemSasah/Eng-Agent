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
| 0 | Workspace root (`pyproject.toml`, AGENTS.md, CI skeleton, `.gate/`) | done (B-002, B-009) |
| 0 | `eng-contract` 0.1 | spec and plan merged (B-003, amended by B-069); T1 to T6 merged (B-010 to B-015); T7 to T16 in the contract chain (B-016 to B-025), then follow-up B-095 |
| 0 | `tools/eng-dev-gate` 0.1 | spec and plan merged (B-004); T1 to T7, T9a, T10, T26 and the fixes B-058, B-059 merged; lead fixes B-092 to B-094 and T8, T9, T11 to T25 in wave 2f |
| 0 | CI workflows (all jobs of process/11 §5) | gate, build, agents-drift and windows jobs through composite actions (B-035); the remaining jobs come with gate T20 to T25 |
| 0 | Spike S-12 (Sasaah tool inventory from catalog sources) | done (B-005); live comparison with `tools/list` needs local test |
| 0 | Spike S-10 (replay; Job Object termination) | done (B-006). Windows evidence from CI run [41729982994](https://github.com/AbdulkareemSasah/Eng-Agent/actions/runs/41729982994) (windows-latest, Python 3.14.10): all Job Object cases pass (kill on close at engine exit and kill, nested jobs, suspended start 0 of 40 escaped, late assignment escapes as expected); replay scenarios pass; write-step overhead p95 7.0 ms (target 20 ms). Report update queued (B-067) |
| 0 | Spikes S-02 and S-04 (scripts for local runs) | done (B-007); the runs need local test |
| 1 | `eng-harness` (engine, journal, replay, ctx, CSI adapter, calcs, templates, basis, decisions, CLI, progress, approval page, run report, edit-cycle workflow) | specs and plans 0001 to 0007 merged (B-060 to B-068); code: wave 3, after eng-contract is done (D-17) |
| 2 | `structural-codes` (core, `aci318-14`, `sbc304-2018` draft), SAFE via CSI adapter, providers (Jev shadow, PydanticAI), `design_isolated_footing` | merged: structural-codes core spec and plan (B-070), ACI 318-14 footing clause specs and plan (B-071), SAFE adapter (B-073), providers (B-074); in wave 2f: SBC 304-2018 footing (B-072), footing workflow (B-075); code with wave 3 (D-17) |
| 3 | `sasaah-revit-mcp` adapter, SAP2000 via CSI adapter, column checks, column workflow | merged: Revit adapter (B-080), SAP2000 (B-081); in wave 2f: ACI column clauses (B-082), column workflow (B-083) |
| 4 | `sasaah-idea-mcp` adapter; desktop products (overlap with Sasaah to the owner queue) | products: analysis done, nothing built (ADR-0033, B-091); IDEA adapter spec in wave 2f (B-090) |

## 3. Tasks

One task is one pull request into `build/v1` (process/02), reviewed by a subagent that is not its author, merged by
squash after CI is green. Ids are `B-NNN`; branches are `<type>/b<NNN>-<slug>`.

| Id | Task | Author (model, effort) | Reviewer (model, effort) | PR | Status |
|---|---|---|---|---|---|
| B-001 | ADR-0028; move the hub into `design/`; update affected documents | lead | — (owner decision record) | direct commit f434a41 | done |
| B-002 | Workspace root: uv workspace, `.python-version`, README, AGENTS.md, CLAUDE.md, `.gate/`, `.github/` skeleton | sonnet, low (second attempt, P-1) | opus, low | [#7](https://github.com/AbdulkareemSasah/Eng-Agent/pull/7) | done (ea33ff9) |
| B-003 | `eng-contract` spec and plan (draft) | opus, medium; fixes: opus, medium (2 rounds) | opus, medium (R2) | [#3](https://github.com/AbdulkareemSasah/Eng-Agent/pull/3) | done (e13d3c0) |
| B-004 | `eng-dev-gate` spec and plan (draft) | sonnet, high; fix: sonnet, high | opus, low | [#4](https://github.com/AbdulkareemSasah/Eng-Agent/pull/4) | done (0bf48f4) |
| B-005 | Spike S-12: Sasaah tool inventory from the catalog sources | sonnet, medium; report committed by the lead (P-2) | opus, low | [#5](https://github.com/AbdulkareemSasah/Eng-Agent/pull/5) | done (fbbfbec) |
| B-006 | Spike S-10: replay of async blocks; Job Object termination | sonnet, high; report committed by the lead (P-2) | opus, low | [#6](https://github.com/AbdulkareemSasah/Eng-Agent/pull/6) | done (fe93351) |
| B-007 | Spikes S-02 and S-04: scripts for local runs | sonnet, medium | opus, low | [#11](https://github.com/AbdulkareemSasah/Eng-Agent/pull/11) | done (6fdc739) |
| B-008 | Hub: stale 04 section references; ADR-0029 (Proposed) eng-contract 0.1 details | sonnet, medium | opus, low | [#13](https://github.com/AbdulkareemSasah/Eng-Agent/pull/13) | done (f93732b) |
| B-009 | Root workspace members listed explicitly (D-10) | lead | opus, low | [#8](https://github.com/AbdulkareemSasah/Eng-Agent/pull/8) | done (fe5fea2) |
| B-010 | `eng-contract` T1: package skeleton | sonnet, low | opus, medium | [#9](https://github.com/AbdulkareemSasah/Eng-Agent/pull/9) | done |
| B-011 | `eng-contract` T2: error codes, retry rules, warnings | sonnet, medium | opus, medium | [#17](https://github.com/AbdulkareemSasah/Eng-Agent/pull/17) | done |
| B-012 | `eng-contract` T3: canonical JSON (RFC 8785), payload hash | sonnet, high | opus, medium | [#22](https://github.com/AbdulkareemSasah/Eng-Agent/pull/22) | done |
| B-013 to B-025 | `eng-contract` T4 to T16 (serialized) | sonnet, low to high per task | opus, medium (R2) | — | in progress (wave 2b) |
| B-030 | `eng-dev-gate` T1: package skeleton, dependency ADR, CLI shell | sonnet, low | opus, low | [#10](https://github.com/AbdulkareemSasah/Eng-Agent/pull/10) | done (365f3b9) |
| B-056 | `eng-dev-gate` plan amendment: split T2 into T2a and T2b (D-12) | sonnet, low | opus, low | [#14](https://github.com/AbdulkareemSasah/Eng-Agent/pull/14) | done |
| B-031 | `eng-dev-gate` T2a: reporting, globs, event file | sonnet, medium | opus, low | [#18](https://github.com/AbdulkareemSasah/Eng-Agent/pull/18) | done |
| B-057 | `eng-dev-gate` T2b: git port, workspace discovery | sonnet, medium | opus, low | [#19](https://github.com/AbdulkareemSasah/Eng-Agent/pull/19) | done |
| B-032 | `eng-dev-gate` T3: configuration models, floors, bootstrap mode | sonnet, medium | opus, low | [#24](https://github.com/AbdulkareemSasah/Eng-Agent/pull/24) | done |
| B-033 to B-055 | `eng-dev-gate` T4 to T26 (dependency graph) | sonnet, low to high per task | opus, low; medium for T13, T14, T16 to T18, T26 | — | in progress (wave 2b) |
| B-060 | `eng-harness` spec and plan 0001 engine; ADR-0030 (Proposed) | opus, medium (4 fix rounds) | opus, medium | [#12](https://github.com/AbdulkareemSasah/Eng-Agent/pull/12) | done |
| B-061 | `eng-harness` spec and plan 0002 servers and adapters; ADR-0031, ADR-0032 (Proposed) | opus, medium | opus, medium | [#21](https://github.com/AbdulkareemSasah/Eng-Agent/pull/21) | done |
| B-062 | `eng-harness` spec and plan 0003 calcs | opus, medium | opus, medium | — | queued (wave 2) |
| B-063 | `eng-harness` spec and plan 0004 templates and design basis | sonnet, medium | opus, medium | — | queued (wave 2) |
| B-064 | `eng-harness` spec and plan 0005 decision layer | sonnet, medium | opus, low | — | queued (wave 2) |
| B-065 | `eng-harness` spec and plan 0006 command line, progress, approval page, run report | sonnet, high | opus, medium (security) | — | queued (wave 2) |
| B-066 | Model edit cycle: workflow spec, block spec and plan 0007 | opus, medium | opus, medium | — | queued (wave 2) |
| B-067 | S-10 report: record the Windows CI results | haiku | opus, low | — | queued |
| B-070 to B-075 | Phase 2 specs: structural-codes core, ACI 318-14 footing clauses, SBC 304-2018 overlay, SAFE adapter, providers, footing block and workflow | opus or sonnet per task | opus, medium (low for none) | — | queued (wave 2b, after their dependencies) |
| B-080 to B-083 | Phase 3 specs: Revit adapter, SAP2000, ACI 318-14 column clauses, column workflow | opus or sonnet per task | opus, medium or low | — | queued (wave 2b) |
| B-070 | structural-codes core framework spec and plan | opus, medium | opus, medium | [#16](https://github.com/AbdulkareemSasah/Eng-Agent/pull/16) | done |
| B-090 | Phase 4 spec: IDEA adapter | sonnet, high | opus, medium | — | queued (wave 2b) |
| B-091 | Desktop products overlap with Sasaah; ADR-0033 (Proposed) | sonnet, medium | opus, low | [#15](https://github.com/AbdulkareemSasah/Eng-Agent/pull/15) | done (08c2161; merged by the lead, P-9) |

### 3.1 Task details (generated from the workflow task data and the pull requests)

| Id | Plan task | Task | Author (model, effort) | Reviewer (model, effort) | PR | Status |
|---|---|---|---|---|---|---|
| B-007 | docs | write the scripts for spikes S-02 and S-04, ready for the owner's local runs | sonnet, medium | opus, low | [#11](https://github.com/AbdulkareemSasah/Eng-Agent/pull/11) | done |
| B-008 | docs | fix stale section references in the design hub, and write ADR-0029 (Proposed) recording the eng-contract 0.1 details in 04 | sonnet, medium | opus, low | [#13](https://github.com/AbdulkareemSasah/Eng-Agent/pull/13) | done |
| B-010 | T1 | Package skeleton and gate configuration | sonnet, low | opus, medium | [#9](https://github.com/AbdulkareemSasah/Eng-Agent/pull/9) | done |
| B-011 | T2 | Error codes, retry rules, warnings and ContractError | sonnet, medium | opus, medium | [#17](https://github.com/AbdulkareemSasah/Eng-Agent/pull/17) | done |
| B-012 | T3 | Canonical JSON (RFC 8785) and payload hash | sonnet, high | opus, medium | [#22](https://github.com/AbdulkareemSasah/Eng-Agent/pull/22) | done |
| B-013 | T4 | ULID identifiers, clocks and id sources | sonnet, medium | opus, medium | [#28](https://github.com/AbdulkareemSasah/Eng-Agent/pull/28) | done |
| B-014 | T5 | Units of canonical/1 with cited exact factors and CSI unit systems | sonnet, high | opus, medium | [#33](https://github.com/AbdulkareemSasah/Eng-Agent/pull/33) | done |
| B-015 | T6 | Quantity and Cited | sonnet, medium | opus, medium | [#35](https://github.com/AbdulkareemSasah/Eng-Agent/pull/35) | done |
| B-016 | T7 | Provenance, envelopes and result records | sonnet, medium | opus, medium | — | not started or in writing |
| B-017 | T8 | References, JSON Pointer and resolution rules | sonnet, high | opus, medium | — | not started or in writing |
| B-018 | T9 | Input-parameter metadata and the validation pipeline | sonnet, high | opus, medium | — | not started or in writing |
| B-019 | T10 | Verdicts, model issues and calculation traces | sonnet, medium | opus, medium | — | not started or in writing |
| B-020 | T11 | Kind names, the kind registry and the model.* kinds | sonnet, medium | opus, medium | — | not started or in writing |
| B-021 | T12 | forces.*, basis.*, verdicts.set and issues.model_check kinds | sonnet, medium | opus, medium | — | not started or in writing |
| B-022 | T13 | Workspace resolution and location probes (POSIX, Windows, fake) | sonnet, high | opus, medium | — | not started or in writing |
| B-023 | T14 | Result store, atomic writes, payload split and model state | sonnet, high | opus, medium | — | not started or in writing |
| B-024 | T15 | MCP mapping helpers | sonnet, low | opus, medium | — | not started or in writing |
| B-025 | T16 | JSON Schema snapshots, freshness test and 0.1.0 changelog | sonnet, low | opus, medium | — | not started or in writing |
| B-030 | T1 | Package skeleton, dependency ADR, CLI shell | sonnet, low | opus, low | [#10](https://github.com/AbdulkareemSasah/Eng-Agent/pull/10) | done |
| B-031 | T2a | Foundations (reporting, git port, workspace discovery, globs, event file) (part A, after the B-056 split) | sonnet, medium | opus, low | [#18](https://github.com/AbdulkareemSasah/Eng-Agent/pull/18) | done |
| B-032 | T3 | Configuration models, floors and bootstrap mode (root gate.yml) | sonnet, medium | opus, low | [#24](https://github.com/AbdulkareemSasah/Eng-Agent/pull/24) | done |
| B-033 | T4 | agents render, keys and drift (and re-render of drifting AGENTS.md files) | sonnet, medium | opus, low | [#26](https://github.com/AbdulkareemSasah/Eng-Agent/pull/26) | done |
| B-034 | T5 | check orchestrator with the lock, format, lint and types steps | sonnet, medium | opus, low | [#27](https://github.com/AbdulkareemSasah/Eng-Agent/pull/27) | done |
| B-035 | T6 | CI part 1: setup action and the gate, agents-drift and build jobs | sonnet, high | opus, low | [#37](https://github.com/AbdulkareemSasah/Eng-Agent/pull/37) | done |
| B-036 | T7 | tests step with separate line and branch coverage and the pytest plugin | sonnet, medium | opus, low | [#41](https://github.com/AbdulkareemSasah/Eng-Agent/pull/41) | done |
| B-037 | T8 | config step (weakening rules, override files, rerun plugins, member table) | sonnet, medium | opus, low | [#40](https://github.com/AbdulkareemSasah/Eng-Agent/pull/40) | open |
| B-038 | T9 | ratchet command and step | sonnet, medium | opus, low | — | not started or in writing |
| B-038a | docs | plan amendment: T9 also writes the root .gate/ratchet.json baseline | haiku, low | opus, low | [#44](https://github.com/AbdulkareemSasah/Eng-Agent/pull/44) | done |
| B-039 | T10 | forbidden part 1: engine, scope, FB001, FB002, FB003, FB007 | sonnet, high | opus, low | [#39](https://github.com/AbdulkareemSasah/Eng-Agent/pull/39) | done |
| B-040 | T11 | forbidden part 2: FB004, FB005, FB006, FB008 | sonnet, high | opus, low | — | not started or in writing |
| B-041 | T12 | imports command and step | sonnet, medium | opus, low | — | not started or in writing |
| B-042 | T13 | gate-check part 1: front matter, body parsing, plan and task, scope and budget | sonnet, high | opus, medium | [#29](https://github.com/AbdulkareemSasah/Eng-Agent/pull/29) | open |
| B-043 | T14 | gate-check part 2: spec and plan pull requests, lane, reasons, protected paths, and the gate-check job | sonnet, high | opus, medium | — | not started or in writing |
| B-044 | T15 | risk-floor command and job | sonnet, medium | opus, low | — | not started or in writing |
| B-045 | T16 | test-first part 1: title, exemptions, commit selection, new and changed tests | sonnet, high | opus, medium | — | not started or in writing |
| B-046 | T17 | test-first part 2: base worktree, runs, classification, isolation, and the test-first job | sonnet, high | opus, medium | — | not started or in writing |
| B-047 | T18 | secrets command and the security job | sonnet, medium | opus, medium | — | not started or in writing |
| B-048 | T19 | licenses step and generated-document freshness | sonnet, medium | opus, low | [#50](https://github.com/AbdulkareemSasah/Eng-Agent/pull/50) | open |
| B-049 | T20 | mutation step (backend decision, ADR, dependency) | sonnet, medium | opus, low | — | not started or in writing |
| B-050 | T21 | workflows lint (WF001 to WF005) | sonnet, medium | opus, low | — | not started or in writing |
| B-051 | T22 | reviewer prompts, review command and the ci-review job | sonnet, medium | opus, low | — | not started or in writing |
| B-052 | T23 | windows-tests command and the windows job | sonnet, medium | opus, low | — | not started or in writing |
| B-053 | T24 | approvals port and verification with bootstrap off | sonnet, medium | opus, low | — | not started or in writing |
| B-054 | T25 | Documentation, changelog 0.1.0 and the self-gate run | sonnet, low | opus, low | — | not started or in writing |
| B-055 | T26 | Base-commit gate (gate root, provenance, head-run rules); built before T6 | sonnet, high | opus, medium | [#31](https://github.com/AbdulkareemSasah/Eng-Agent/pull/31) | done |
| B-056 | docs | amend the eng-dev-gate plan: split task T2 into T2a and T2b | sonnet, low | opus, low | [#14](https://github.com/AbdulkareemSasah/Eng-Agent/pull/14) | done |
| B-057 | T2b | Foundations (reporting, git port, workspace discovery, globs, event file) (part B, after the B-056 split) | sonnet, medium | opus, low | [#19](https://github.com/AbdulkareemSasah/Eng-Agent/pull/19) | done |
| B-060 | docs | write the eng-harness engine specification and plan, and ADR-0030 (Proposed) amending ADR-0014 | opus, medium | opus, medium | [#12](https://github.com/AbdulkareemSasah/Eng-Agent/pull/12) | done |
| B-061 | docs | write the eng-harness server and adapter specification and plan, and ADR-0031 and ADR-0032 (Proposed) | opus, medium | opus, medium | [#21](https://github.com/AbdulkareemSasah/Eng-Agent/pull/21) | done |
| B-062 | docs | write the eng-harness calcs specification and plan | opus, medium | opus, medium | [#20](https://github.com/AbdulkareemSasah/Eng-Agent/pull/20) | done |
| B-063 | docs | write the eng-harness templates and design-basis specification and plan | sonnet, medium | opus, medium | [#23](https://github.com/AbdulkareemSasah/Eng-Agent/pull/23) | done |
| B-064 | docs | write the eng-harness decision-layer specification and plan | sonnet, medium | opus, low | [#30](https://github.com/AbdulkareemSasah/Eng-Agent/pull/30) | done |
| B-065 | docs | write the eng-harness command-line, progress, approval-page and run-report specification and plan | sonnet, high | opus, medium | [#32](https://github.com/AbdulkareemSasah/Eng-Agent/pull/32) | done |
| B-066 | docs | write the model edit cycle workflow spec, block specification and plan | opus, medium | opus, medium | [#43](https://github.com/AbdulkareemSasah/Eng-Agent/pull/43) | done |
| B-068 | docs | amend the engine spec as specs 0003 (Q11), 0005 (Q1) and 0006 (§11) require | opus, medium | opus, medium | [#42](https://github.com/AbdulkareemSasah/Eng-Agent/pull/42) | done |
| B-069 | docs | amend the eng-contract spec: the Quantity comparison key uses the shortest round-trip decimal | sonnet, low | opus, medium | [#49](https://github.com/AbdulkareemSasah/Eng-Agent/pull/49) | done |
| B-070 | docs | write the structural-codes core framework specification and plan | opus, medium | opus, medium | [#16](https://github.com/AbdulkareemSasah/Eng-Agent/pull/16) | done |
| B-071 | docs | write the ACI 318-14 isolated-footing clause specifications and plan (draft) | opus, medium | opus, medium | [#34](https://github.com/AbdulkareemSasah/Eng-Agent/pull/34) | done |
| B-072 | docs | write the SBC 304-2018 overlay specification and plan for the footing checks (draft, with explicit gaps) | opus, medium | opus, medium | — | not started or in writing |
| B-073 | docs | write the specification and plan for SAFE through the CSI adapter | sonnet, high | opus, medium | [#36](https://github.com/AbdulkareemSasah/Eng-Agent/pull/36) | done |
| B-074 | docs | write the provider-layer specification and plan (Jev decision-model tier in shadow mode, language-model tier with PydanticAI) | sonnet, high | opus, medium | [#46](https://github.com/AbdulkareemSasah/Eng-Agent/pull/46) | done |
| B-075 | docs | write the design_isolated_footing block and footing workflow specifications and plan | opus, medium | opus, medium | — | not started or in writing |
| B-080 | docs | write the sasaah-revit-mcp adapter specification and plan | sonnet, high | opus, medium | [#47](https://github.com/AbdulkareemSasah/Eng-Agent/pull/47) | done |
| B-081 | docs | write the SAP2000 coverage check and the specification and plan for SAP2000 through the CSI adapter | sonnet, medium | opus, low | [#48](https://github.com/AbdulkareemSasah/Eng-Agent/pull/48) | done |
| B-082 | docs | write the ACI 318-14 column check clause specifications and plan (draft) | opus, medium | opus, medium | — | not started or in writing |
| B-083 | docs | write the column workflow specification (design columns in ETABS, update Revit by reference) and plan | opus, medium | opus, medium | — | not started or in writing |
| B-090 | docs | write the sasaah-idea-mcp adapter specification and plan | sonnet, high | opus, medium | — | not started or in writing |
| B-091 | docs | write the desktop-products overlap analysis and ADR-0033 (Proposed) | sonnet, medium | opus, low | [#15](https://github.com/AbdulkareemSasah/Eng-Agent/pull/15) | done |
| B-092 | docs | fix(eng-dev-gate): give every suppression comment an issue reference and a reason (B-092) | sonnet, low | opus, low | [#52](https://github.com/AbdulkareemSasah/Eng-Agent/pull/52) | open |
| B-093 | docs | build(eng-contract): pyproject within the gate's config and imports rules (B-093) | sonnet, low | opus, low | [#53](https://github.com/AbdulkareemSasah/Eng-Agent/pull/53) | open |
| B-094 | docs | docs(eng-dev-gate): T11 also edits the forbidden package's __init__.py (B-094 plan amendment) | sonnet, low | opus, low | [#54](https://github.com/AbdulkareemSasah/Eng-Agent/pull/54) | open |
| B-095 | docs | eng-contract: follow-ups from the reviews of B-015 and B-069 | sonnet, low | opus, low | — | not started or in writing |
| B-100 | E.T1 | Package skeleton, gate configuration and workspace member | sonnet, low | opus, medium | — | not started or in writing |
| B-101 | E.T2 | Harness codes, EngineStop and StepError families | sonnet, low | opus, medium | — | not started or in writing |
| B-102 | E.T3 | Journal schema, append-only writer, hash chain, durability, payloads by reference | sonnet, high | opus, medium | — | not started or in writing |
| B-103 | E.T4 | Journal reader API and views | sonnet, medium | opus, medium | — | not started or in writing |
| B-104 | E.T5 | Blocks, workflows, registry, code hash and the block lock file | sonnet, medium | opus, medium | — | not started or in writing |
| B-105 | E.T6 | Ports, port data types and in-memory fakes | sonnet, medium | opus, medium | — | not started or in writing |
| B-106 | E.T7 | ctx types, basis view and the result codec | sonnet, medium | opus, medium | — | not started or in writing |
| B-107 | E.T8 | Step paths, scopes, op_id, overlap detection, parallel and attempts scopes | sonnet, high | opus, medium | — | not started or in writing |
| B-108 | E.T9 | Engine start and resume, run lock, run header, replay index and divergence | sonnet, xhigh | opus, medium | — | not started or in writing |
| B-109 | E.T10 | ctx implementation of tool, read, calc, block, parallel, attempts, escalate | sonnet, high | opus, medium | — | not started or in writing |
| B-110 | E.T11 | In-flight reconciliation and the host-state check before live execution | sonnet, xhigh | opus, medium | — | not started or in writing |
| B-111 | E.T12 | Invariants 1, 2, 3 and 7 (check after write, references, staleness, save before analysis) | sonnet, high | opus, medium | — | not started or in writing |
| B-112 | E.T13 | Invariants 5, 6, 8, 9 and 10 (basis, honest outcomes, server checks, units, host leases) | sonnet, high | opus, medium | — | not started or in writing |
| B-113 | E.T14 | ctx.decide, ctx.decide_many and ctx.ask (invariant 4) | sonnet, medium | opus, medium | — | not started or in writing |
| B-114 | E.T15 | Approvals (binding, single use, re-check before the write, items, pause and re-presentation) | sonnet, high | opus, medium | — | not started or in writing |
| B-115 | E.T16 | Permission modes, always-ask list, working copies and file-copy promotion | sonnet, high | opus, medium | — | not started or in writing |
| B-116 | E.T17 | Runtime guard for block and rule code, and the block-module rules test | sonnet, medium | opus, medium | — | not started or in writing |
| B-117 | E.T18 | Resource limits, progress sink and the overhead benchmark | sonnet, medium | opus, medium | — | not started or in writing |
| B-118 | E.T19 | Crash-matrix replay suite with a worker process | sonnet, high | opus, medium | — | not started or in writing |
| B-120 | S.T1 | MCP SDK dependency ADR, harness.toml server and tool sections | sonnet, medium | opus, medium | — | not started or in writing |
| B-121 | S.T2 | Process launcher and inspector ports, POSIX implementation | sonnet, high | opus, medium | — | not started or in writing |
| B-122 | S.T3 | Windows launcher, per-server Job Objects with breakaway, Windows process inspector | sonnet, xhigh | opus, medium | — | not started or in writing |
| B-123 | S.T4 | Synthetic Sasaah CSI fake server (test-only) and its schema check | sonnet, medium | opus, medium | — | not started or in writing |
| B-124 | S.T5 | Process transport, MCP client session, crash detection, restart and shutdown | sonnet, high | opus, medium | — | not started or in writing |
| B-125 | S.T6 | Tool descriptors, allowlist data with escape-hatch refusal, build check and fingerprint | sonnet, high | opus, medium | — | not started or in writing |
| B-126 | S.T7 | Machine-level host-instance lock and process guard | sonnet, high | opus, medium | — | not started or in writing |
| B-127 | S.T8 | Adapter framework - arguments and references, envelopes, write ledger, ToolPort describe and call | sonnet, high | opus, medium | — | not started or in writing |
| B-128 | S.T9 | Error and timeout mapping, the CSI error table (interim model_locked) | sonnet, medium | opus, medium | — | not started or in writing |
| B-129 | S.T10 | Harness-side model identity (ADR-0032), CSI session operations, HostPort file and instance methods | sonnet, high | opus, medium | — | not started or in writing |
| B-130 | S.T11 | CSI model-state reader, model kinds, fingerprint and units read | sonnet, high | opus, medium | — | not started or in writing |
| B-131 | S.T12 | CSI edit kinds, read-back helpers and check_model | sonnet, high | opus, medium | — | not started or in writing |
| B-132 | S.T13 | CSI analysis, design and results through the long role | sonnet, high | opus, medium | — | not started or in writing |
| B-133 | S.T14 | Reconciliation by reading model state, preview and read_back | sonnet, high | opus, medium | — | not started or in writing |
| B-135 | S.T16 | Command-line tool adapter (dxf-prep, etabs-model build) | sonnet, medium | opus, medium | — | not started or in writing |
| B-136 | S.T17 | Record mode, sanitizer and manifest, recorded-reply fake, contract tests on recordings | sonnet, high | opus, medium | — | not started or in writing |
| B-137 | S.T18 | eng-harness doctor | sonnet, medium | opus, medium | — | not started or in writing |
| B-138 | S.T19 | Port wiring, edit-cycle step sequence and crash matrix against real fake-server processes | sonnet, high | opus, medium | — | not started or in writing |
| B-140 | C.T1 | Calc decorator, registry, inputs, input metadata, trace builder, statuses and harness codes | sonnet, medium | opus, medium | — | not started or in writing |
| B-141 | C.T2 | Content hash over the static import closure and the calc lock file | sonnet, high | opus, medium | — | not started or in writing |
| B-142 | C.T3 | approvals.yaml schema, loader, status resolution and the YAML parser ADR | sonnet, medium | opus, medium | — | not started or in writing |
| B-143 | C.T4 | Calc kinds and their registration | sonnet, medium | opus, medium | — | not started or in writing |
| B-144 | C.T5 | HarnessCalcPort (describe, run, preflight, run class, limits, storage) and the calc step workflow test | sonnet, medium | opus, medium | — | not started or in writing |
| B-145 | C.T6 | Calc-module rules test, golden data loader and golden file lint, verification record template | sonnet, low | opus, medium | — | not started or in writing |
| B-146 | C.T7 | Calc 1, model fingerprint, with the canonical-state helper | sonnet, high | opus, medium | — | not started or in writing |
| B-147 | C.T8 | Calc 2, difference report, with the tolerance-comparison helper | sonnet, high | opus, medium | — | not started or in writing |
| B-148 | C.T9 | Calc 3, read-back check | sonnet, high | opus, medium | — | not started or in writing |
| B-149 | C.T10 | Calc 4, design results summary | sonnet, high | opus, medium | — | not started or in writing |
| B-150 | C.T11 | Calc 5, section size rounding | sonnet, high | opus, medium | — | not started or in writing |
| B-151 | C.T12 | Calc 6, element count and position comparison | sonnet, high | opus, medium | — | not started or in writing |
| B-155 | B.T1 | Template model, entries, citations, canonical units and bounds | sonnet, medium | opus, medium | — | not started or in writing |
| B-156 | B.T2 | Strict YAML 1.2 loader and the YAML dependency | sonnet, high | opus, medium | — | not started or in writing |
| B-157 | B.T3 | Inheritance, merge rules, ask paths and the resolved content hash | sonnet, medium | opus, medium | — | not started or in writing |
| B-158 | B.T4 | Template repository (shipped and user folders) and check_template | sonnet, medium | opus, medium | — | not started or in writing |
| B-159 | B.T5 | FieldSpec and the workflow declaration rules | sonnet, medium | opus, medium | — | not started or in writing |
| B-160 | B.T6 | Basis draft: precedence, sources, citations, pending list and draft hash | sonnet, medium | opus, medium | — | not started or in writing |
| B-161 | B.T7 | Setup view, answer model and BasisSetupPort | sonnet, medium | opus, medium | — | not started or in writing |
| B-162 | B.T8 | Freeze, storage as basis.design_basis/1 and StoreBasisPort | sonnet, medium | opus, medium | — | not started or in writing |
| B-163 | B.T9 | Shipped blank template, package data and golden pin | sonnet, low | opus, medium | — | not started or in writing |
| B-164 | B.T10 | Property tests and the fake-host workflow with replay | sonnet, medium | opus, medium | — | not started or in writing |
| B-165 | D.T1 | Types, policy, settings, public modules | sonnet, medium | opus, low | — | not started or in writing |
| B-166 | D.T2 | Decision points, state field rules, point registry and lock | sonnet, medium | opus, low | — | not started or in writing |
| B-167 | D.T3 | Redaction check (by construction and at runtime) | sonnet, high | opus, medium | — | not started or in writing |
| B-168 | D.T4 | Rule definitions, restricted basis view, registry, lock and review table | sonnet, medium | opus, medium | — | not started or in writing |
| B-169 | D.T5 | Provider interfaces, suggestion and port models, fake providers | sonnet, medium | opus, low | — | not started or in writing |
| B-170 | D.T6 | Label store, pending store, override and opt-in export | sonnet, medium | opus, low | — | not started or in writing |
| B-171 | D.T7 | Cascade core (validation, tier 1, engineer tier, pending, record) | sonnet, medium | opus, medium | — | not started or in writing |
| B-172 | D.T8 | Tiers 2 and 3, shadow mode, timeouts, policy switches, local_only | sonnet, high | opus, medium | — | not started or in writing |
| B-173 | D.T9 | decide_many batching and one batched screen | sonnet, medium | opus, low | — | not started or in writing |
| B-174 | D.T10 | Engine wiring, workflow, replay, conformance and performance tests, local-testing notes | sonnet, medium | opus, low | — | not started or in writing |
| B-175 | I.T1 | Text, date and number formatting and sanitizing | sonnet, low | opus, low | — | not started or in writing |
| B-176 | I.T2 | HTML builder: escaping by construction, safe tokens, labeled untrusted fields, style hash | sonnet, high | opus, medium | — | not started or in writing |
| B-177 | I.T3 | Command line shell: parser, exit codes, configuration, output encoding, launch-address opener, entry point | sonnet, medium | opus, low | — | not started or in writing |
| B-178 | I.T4 | Expected times from earlier journals and the progress renderer | sonnet, medium | opus, low | — | not started or in writing |
| B-179 | I.T5 | Non-blocking progress sink, heartbeat task and liveness reader | sonnet, high | opus, low | — | not started or in writing |
| B-180 | I.T6 | Page server: loopback bind, launch code and session, Host, Origin and CSRF checks, headers, routes, lockdown | sonnet, xhigh | opus, medium | — | not started or in writing |
| B-181 | I.T7 | Answer models and checks, approval and input ports, durable wait, stop-file run control | sonnet, high | opus, medium | — | not started or in writing |
| B-182 | I.T8 | Report package skeleton, release marks and lineage closure | sonnet, low | opus, low | — | not started or in writing |
| B-183 | I.T9 | Approval screens: change set, promotion, info and sign-off | sonnet, medium | opus, medium | — | not started or in writing |
| B-184 | I.T10 | Choice screens (engineer turn, batched decisions, engine requests), the read-only input screen and the answers-file gate | sonnet, medium | opus, medium | — | not started or in writing |
| B-185 | I.T11 | Report model: fold the journal and the store; timings, waiting and machine time | sonnet, medium | opus, low | — | not started or in writing |
| B-186 | I.T12 | Report sections: changes, results, sources, decisions; renderer registry; value cells with sources | sonnet, medium | opus, low | — | not started or in writing |
| B-187 | I.T13 | Report document: DRAFT and completeness marks, integrity line, policy meta, atomic UTF-8 write | sonnet, medium | opus, low | — | not started or in writing |
| B-188 | I.T14 | Commands run and resume: wiring, generated options, answers file, signals, outcome mapping | sonnet, high | opus, medium | — | not started or in writing |
| B-189 | I.T15 | Basis confirmation screen, setup log and its place in run | sonnet, medium | opus, low | — | not started or in writing |
| B-190 | I.T16 | Commands status, stop, report and doctor | sonnet, medium | opus, low | — | not started or in writing |
| B-191 | I.T17 | End-to-end approval, replay and untrusted-text tests; Arabic environment; local testing list; agent rule | sonnet, medium | opus, medium | — | not started or in writing |
| B-195 | W.T1 | Edit-cycle kinds and the change-set model | sonnet, medium | opus, medium | — | not started or in writing |
| B-196 | W.T2 | Calc harness.change_set_check (resolve, validate, conflicts, refused kinds) | sonnet, medium | opus, medium | — | not started or in writing |
| B-197 | W.T3 | Calc harness.expected_effects (projection of a resolved change set) | sonnet, medium | opus, medium | — | not started or in writing |
| B-198 | W.T4 | Calcs harness.host_design_verdicts and harness.analysis_summary | sonnet, medium | opus, medium | — | not started or in writing |
| B-199 | W.T5 | CSI adapter read tool, revision save and open, analysis-messages read (spec 0002 amendment) | sonnet, medium | opus, medium | — | not started or in writing |
| B-200 | W.T6 | Engine amendments (copy on open, tool saves journaled, mode approvals and always-ask, basis fields) | sonnet, medium | opus, medium | — | not started or in writing |
| B-201 | W.T7 | Decision points and rules of the edit cycle | sonnet, medium | opus, medium | — | not started or in writing |
| B-202 | W.T8 | Workflow part 1 - definition, basis fields, steps 1 to 10 (read, differences, change set, approval, apply, read back) | sonnet, medium | opus, medium | — | not started or in writing |
| B-203 | W.T9 | Workflow part 2 - steps 11 to 17 (analysis, design, summaries, engineer turn, promotion, sign-off) and the cycle loop | sonnet, medium | opus, medium | — | not started or in writing |
| B-204 | W.T10 | Report renderers, value-source audit, prompt counter and B-1 cycle timings | sonnet, medium | opus, medium | — | not started or in writing |
| B-205 | W.T11 | Acceptance support in CI (A3 and A7 over the workflow scenarios) and the local-testing list | sonnet, medium | opus, medium | — | not started or in writing |
| B-206 | W.T12 | Replay test and crash matrix of the workflow (A6) | sonnet, medium | opus, medium | — | not started or in writing |

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
| D-18 | Work runs as several workflows at once, because the workflow runtime runs at most two agents per workflow (P-17): wave 2g is three workflows (contract chain with the remaining specs; gate graph part A; gate graph part B). Wave 3 runs as lanes (harness core E/S/W; harness side C/B/D/I/P; structural-codes; later the F/R/A adapters), each a dependency graph that treats the other lanes' merged tasks as done and stops when nothing more can start; the lead relaunches each lane from the state on GitHub. A workflow resumed after a restart keeps its cached results (`resumeFromRunId`); an approving review recorded by an earlier run carries over when the head is unchanged (resume mode `approved`) | Keeps about five writers busy, as the mission asks, instead of two; dependencies stay enforced inside each lane and by the relaunch |
| D-17 | Refines D-9 for code: a package's code starts when the packages it imports (03 §3 layers) are done, not when the whole previous phase is done; inside a package, the plans' `depends_on` and the cross-plan dependencies in their text order the tasks. So `structural-codes` (imports `eng-contract` only) is built alongside `eng-harness`, and the adapter plans of phases 2 and 3 (SAFE, providers, Revit, SAP2000) join the harness graph behind the harness tasks they need | Phase order exists to limit risk R4, which ADR-0028 accepts for v1; strict phase gating would serialize about 160 tasks behind the eng-contract chain |
| D-16 | When an approved pull request's merge step did not run because of an external failure (the usage limit, P-14), the lead merges it after checking that the pull_request run on its head is green, and records the review in the body's Review section, instead of a new review. Used for B-015 ([#35](https://github.com/AbdulkareemSasah/Eng-Agent/pull/35), after updating its branch and a green run on the new head), B-074 ([#46](https://github.com/AbdulkareemSasah/Eng-Agent/pull/46)) and B-080 ([#47](https://github.com/AbdulkareemSasah/Eng-Agent/pull/47)) | A second review of unchanged, approved work spends tokens for nothing; the lead is not the author of these changes |
| D-15 | When a new gate step fails on existing code outside its task's files, the lead lands a small fix first (its own pull request, reviewed and merged by subagents) and the task resumes in open-PR mode; the rule is not widened. B-092 ([#52](https://github.com/AbdulkareemSasah/Eng-Agent/pull/52)): every `noqa` comment carries `# B-NNN: reason` in a second comment (ruff and mypy accept that form; mypy rejects text directly after `type: ignore`), for T9. B-093 ([#53](https://github.com/AbdulkareemSasah/Eng-Agent/pull/53)): eng-contract declares its own test dependencies (IM006, for T12) and keeps its tool tables in the closed allowed set of gate spec 4.12 (route A, for T8). B-094 ([#54](https://github.com/AbdulkareemSasah/Eng-Agent/pull/54)): T11's file list gains the forbidden package's `__init__.py`. New packages follow the same rules from their skeleton task | The rules match the spec and the future repository split (each package declares what it imports); widening them would weaken the gate |
| D-14 | Reviewers mark each finding's action: `author` (fix in this pull request) or `lead` (the code is right; only a spec, plan or design document must change). Lead actions do not block a merge or trigger fix rounds; the lead amends the document in its own pull request | B-015's correct code looped through three fix rounds over a spec contradiction only a spec change could resolve (P-12) |
| D-13 | When the base-commit gate itself is defective so that every pull request fails on the defect, the lead may merge the fix with its gate job red only if: an independent reviewer approved; the only failing step is the defect being fixed (job log); the fixed gate, run the way CI runs it against the repository, passes; and the exception is recorded here and in the owner queue. Used twice: B-058 ([#45](https://github.com/AbdulkareemSasah/Eng-Agent/pull/45)) and B-059 ([#51](https://github.com/AbdulkareemSasah/Eng-Agent/pull/51)). Every remaining gate task must now prove pull-request mode before it merges (a checkout of its branch as `--gate-root`), so a third use should not arise | The emergency path of process/12 §1 needs an owner approval and green CI, neither available in bootstrap mode; every route through the gate deadlocks otherwise |
| D-12 | A task over its line budget is split by a plan amendment in its own reviewed pull request, not given a budget above the ~400-line cap of process/04 §4 | B-031 measured 573 lines; splitting keeps reviews small |
| D-11 | Tasks run as workflow chains: writer, independent review with up to two fix rounds, then a mechanical merge step that waits for CI and squash-merges only on an approving review and green CI; at most five writers at once | Serialized chains (the 16 `eng-contract` tasks) do not stall between tasks; the merge rule stays the lead's |

## 5. Problems

| Id | Problem | Handling |
|---|---|---|
| P-1 | The first five worktrees of wave 1 were created from the Sasaah checkout (the lead's shell was there at launch); B-002 stopped, the others cloned Eng-Agent into the scratchpad. Nothing reached Sasaah | Launch every agent from `/home/user/Eng-Agent`; every prompt checks `git remote -v` first |
| P-2 | Subagents' write tool refuses files it treats as report files (`REPORT.md`) | The lead commits such files from the drafts the subagents return; prompts say not to work around a refusal |
| P-3 | Worktrees are created from the lead's current folder when each agent starts, not when its workflow starts; two reviews failed while the lead's shell was outside the repository | The lead's shell stays in `/home/user/Eng-Agent` while workflows run (other folders only in subshells) |
| P-4 | The root workspace glob broke `uv sync` once a package folder held only docs (CI red on #3 and #4) | Fixed by B-009 (D-10) |
| P-5 | The harness flagged the merge of B-009 as possible self-approval: the lead wrote that 3-line fix, an independent subagent reviewed it, and the merge step merged it. In bootstrap mode every pull request is opened and merged under the owner's GitHub account (no separate identities yet, OQ-2) | Lead-written changes are kept to integration fixes; the owner may re-review [#8](https://github.com/AbdulkareemSasah/Eng-Agent/pull/8) |
| P-7 | The harness flagged the merge of B-007 as "merge without review": the subagent review (APPROVE, recorded in the PR body) is not a GitHub review, because every account action is the owner's in bootstrap mode | Reviews stay recorded in the PR body (D-6); the owner can audit [#11](https://github.com/AbdulkareemSasah/Eng-Agent/pull/11) |
| P-17 | Every workflow so far ran at most two agents at a time (measured from the agent transcripts of all fourteen runs; two overlapping runs reached three), so the writer cap of five in the chain script never applied and each wave was about twice as slow as planned; the container also restarted twice more (about 06:00 and 06:21 UTC), stopping wave 2f | D-18: several workflows at once; stale worktrees and empty local branches cleaned before each launch |
| P-16 | The security monitor flagged the merge steps of B-069 and B-039 as self-approval: in bootstrap mode every account action is the owner's account (D-6), as in P-5 | Recorded; both merges followed an approving review by a subagent that did not write the change, and a green pull_request run |
| P-15 | New gate steps failed on existing code outside their tasks' files: T9 ratchet (14 `noqa` comments without an issue reference and one skip in eng-dev-gate), T12 imports (eng-contract tests import pytest and Hypothesis that only the root declared), T8 config (nine keys of eng-contract's pyproject outside the allowed set), T11 (its registration file was missing from its globs). B-038, B-041, B-037 and B-040 stopped as BLOCKED with the evidence | D-15: lead fixes B-092, B-093 and B-094, each verified with the blocked branch's own step and in pull-request mode; the four tasks resume in wave 2f |
| P-14 | The 5-hour usage limit was reached at about 05:00 UTC: ten agents of wave 2e failed (the review of B-042; the merge steps of B-015, B-074 and B-080; B-037's second fix round; B-047's open step; the writers of B-090, B-072 and B-082), and a review that returned no result crashed the gate graph's branch (`r.findings` of null) | Wave 2e ended. The chain script now stops a task when an agent returns no result. After the 06:00 reset: D-16 merges, then wave 2f from the state on GitHub |
| P-13 | After gate T7 (B-036, the tests step) merged, the base-commit gate ran the judged tree's tests in its own interpreter (the base environment holds eng-dev-gate only), so every pull request failed with ImportError; push runs passed | Wave 2d stopped; fixed by B-059 and merged under D-13; remaining gate tasks must verify pull-request mode before merging (written into their task statements and reviews) |
| P-12 | The contract chain stopped at B-015: four reviews approved its code but repeated one MEDIUM, a contradiction inside the spec (rule 4 against AC35) that only a spec change could resolve, and the chain treated it as author work | Spec amended by B-069 (#49); D-14; the contract chain runs as its own workflow from B-069 |
| P-11 | After gate T6 (B-035) merged, the base-commit gate ran ruff with the base checkout as working directory, so `per-file-ignores` never matched the judged tree and every pull request failed lint (S101 in tests); wave 2c stalled on it | Wave 2c stopped; fixed by B-058 and merged under D-13; also closed a cache-planting hole the review found |
| P-10 | The container restarted at about 02:00 UTC and stopped wave 2b; agents in flight were lost (six open PRs, two pushed branches without PRs, writers without pushes) | Relaunched as wave 2c from the state on GitHub: merged tasks marked done, open PRs resume at review, pushed branches resume in open-PR mode, the rest restart; stale worktrees removed |
| P-9 | The merge step of B-091 declined to merge because GitHub showed no GitHub review | The lead merged after CI passed on the conflict-resolved head; merge prompts now say a missing GitHub review is expected in bootstrap mode |
| P-8 | Wave 2 stopped early on three blockers: B-010 CI (the skeleton ran mypy on an empty folder; B-030 fixed it first, leaving B-010 in conflict), B-031 over budget (573 of 380 lines), B-060 one open MEDIUM after three rounds | Relaunched as wave 2b: conflict resolution for B-010, the T2 split (D-12), a fourth fix round for B-060 |
| P-6 | The merge step merged B-005 after only the Dependabot check had reported, before the CI job appeared; the content was validated by the next push run on `build/v1` (green) | The merge step now requires a pull-request workflow run for the exact head commit to succeed |

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
| OQ-A5 | `eng-dev-gate` package ADR-0001: runtime dependencies PyYAML, Pydantic, ruff, mypy, pytest, coverage (gate spec; licenses to be confirmed by the gate's license check) | Approve |
| OQ-A6 | ADR-0029 (Proposed): eng-contract 0.1 details recorded in 04 (B-008) | Accept: all items are additive |
| OQ-A7 | ADR-0030 (Proposed): replay by step path and reconciliation, amending ADR-0014 (B-060) | Accept with ADR-0014; the Windows CI evidence in §2 supports the Job Object part |
| OQ-A8 | ADR-0031 (Proposed): `model_locked` after analysis is a precondition with an approved unlock step (B-061) | Accept |
| OQ-A9 | ADR-0032 (Proposed): harness-side model identity when the host cannot stamp one (B-061) | Accept until Sasaah offers a typed identity tool |
| OQ-A12 | `eng-harness` package ADRs 0001 to 0003 (Proposed, B-074): runtime dependencies `pydantic-ai-slim`, `keyring` and `httpx2`, with two license exceptions outside process/04 §7 (`regex`: Apache-2.0 AND CNRI-Python; `cffi`: MIT-0), each an entry in `license_exceptions` of `.gate/gate.yml` (protected path, left to the owner) | Approve the ADRs when the provider tasks confirm the dependency closure; approve both license exceptions (permissive) or name alternatives |
| OQ-A11 | D-13 exceptions: B-058 ([#45](https://github.com/AbdulkareemSasah/Eng-Agent/pull/45)) and B-059 ([#51](https://github.com/AbdulkareemSasah/Eng-Agent/pull/51)) merged with their own gate job red (the defect each fixes); B-058 also changed one existing test assertion to the new command-line shape (A4) | Review both; confirm the exceptions and the assertion change |
| OQ-A10 | ADR-0033 (Proposed): desktop products stay in Sasaah during v1; overlap items O-1 to O-6 in `products/README.md` (B-091) | Accept; decide O-1 to O-6 |

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
| OQ-Q20 | Spikes: may a spike's first commit mix tests and code, since spikes have no plan task? (B-007) | Yes; say so in process/05 §9 |
| OQ-Q21 | S-02 needs a call timeout shorter than an analysis, but the timeout is a server start option, so the scripts start a second server (B-007) | The harness adapter does the same: a dedicated server instance for long runs |
| OQ-Q22 | Engine spec (B-060) questions Q1 to Q11: attempt limits from the basis, block version plus code hash, restore only when no later model was written, autonomous mode resolving info and change-set approvals, the durability set, a new `op_id` after not-applied, harness codes for engine-only conditions, explicit `args` mappings, `for` loops over finite collections, a single-writer journal with an answer inbox, saving after every write step | Accept each as recommended in the spec; measure saving cost with S-02 |
| OQ-Q23 | Engine gap E-G1: promotion by replaying journaled write steps (11 §7) is not built; it raises NOT_IMPLEMENTED and a test expects it | Build when a Revit or workshared-model workflow needs it |
| OQ-Q29 | Each draft spec ends with its own open questions and gaps, each with a recommendation; the build follows the recommendations as drafted. Count by spec: eng-contract 0001 (Q1 to Q6, G-1 to G-4); eng-harness 0001 engine (23), 0002 servers and adapters (7, S12 gaps), 0003 calcs (14), 0004 templates and basis (9), 0005 decisions (11), 0006 interface (14), 0007 edit cycle (10), 0008 SAFE (8), 0009 providers (13, J-G1), 0011 Revit (Q1 to Q9, R-G1 to R-G16, correction C1 to S-12), 0012 SAP2000 (6, SP-1 to SP-8); structural-codes 0001 core (15); eng-dev-gate 0001 (12) | Review them with each spec's approval (OQ-Q13); the questions are in the last numbered section of each spec |
| OQ-Q28 | Gate T9 writes the initial ratchet baseline `.gate/ratchet.json` (a protected path); in pull-request context a raised count is AW05, awaiting owner | Approve the baseline; later rises are reviewed one by one |
| OQ-Q27 | Gate spec 4.12: should keys that only make a tool stricter (pytest `xfail_strict`, mypy `warn_unreachable`) join the closed allowed set? B-093 removed them from eng-contract (the root's mypy configuration, with `warn_unreachable`, now applies to it) | Allow stricter-only keys in a later spec revision; v1 keeps the closed set |
| OQ-Q26 | Gate follow-up from the B-059 review: `_stale_lock` reports any failure of `uv lock --check` (for example a network error) as a stale lock, not an environment fault (fails closed); and in pull-request mode `coverage` and `pytest` come from the judged lock (accepted residual risk, spec 4.12) | Distinguish uv's own failures in a later gate task |
| OQ-Q25 | Gate gap: a member's own `[tool.ruff]` or `[tool.mypy]` table in a pull request replaces the base policy for that member until the CF003/CF004 config step (gate T8, B-037) lands; ruff's `respect-gitignore` lets head `.gitignore` files hide sources from lint | Land T8; consider `respect-gitignore = false` in the base policy |
| OQ-Q24 | `[tool.eng-gate]` key names differ between the eng-contract plan and the gate spec (mutation module list, `may_import`) | Align in the gate's configuration task (T3); until then the gate spec's names apply |

### 6.5 Sasaah pull requests

| Id | Pull request | Why |
|---|---|---|
| — | none | — |
