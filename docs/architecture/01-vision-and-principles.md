# 01. Vision and Principles

Status: Proposed · Owner: product owner (structural engineer) · Applies to: every repository

## 1. Vision

An engineering harness that designs, modifies, analyzes, and checks structural models in Revit, ETABS, SAFE,
SAP2000 and IDEA StatiCa by running **workflows that the engineer defines**, using **tools that never guess**.

The harness must beat the engineer's own time on a repeated task while producing results the engineer can trust
without re-deriving them. If it is slower than doing the task by hand, it has failed, no matter how autonomous it is.

## 2. The core principle

> **The agent decides. It never calculates, and it never invents a number.**

Every engineering number comes from a trusted tool (a host program, or a verified code check). Every change to a
model goes through a tool. The agent (a decision model, a language model, or the workflow engine itself) only
chooses between options that tools and workflows put in front of it.

## 3. Rules that follow from the principle

These are numbered and stable. Other documents cite them as `P1` to `P12`.

| # | Rule | Where it is enforced |
|---|---|---|
| P1 | **Work only through tools.** Reading, writing, analysis, design, and checks are tool calls. No agent writes engineering values from memory. | Harness engine; MCP server standard |
| P2 | **Pass results by reference, not by copy.** Every tool result gets a `result_id`. The next tool accepts the reference and reads the value itself (for the Sasaah servers, the harness adapter does, [ADR-0024](../adr/0024-harness-on-existing-sasaah-servers.md)). | [04-tool-contract](04-tool-contract.md) §3 |
| P3 | **The agent sees what it judges.** Values that a decision depends on (ratios, drifts, statuses) come back in full and in plain structure. Bulk data stays in the store. | Tool contract `summary` field |
| P4 | **Tools return the verdict with the number.** A check returns `ratio`, `limit`, `status`, `clause`. The agent never compares numbers or remembers limits. | Code packs ([10](10-structural-codes.md)) |
| P5 | **Tools validate their inputs.** Every input has a type, a unit, and physical bounds. Out-of-range input is rejected with a structured error, never silently accepted or clamped. | Tool contract §6; every server |
| P6 | **Small, single-purpose tools.** One tool does one thing, with fixed JSON input and output. Names are `verb_noun`. No multi-purpose "do anything" tools and no script runners. | [05-mcp-server-standard](05-mcp-server-standard.md) |
| P7 | **Check after every change.** Every write leaves the model "dirty" until a model check runs. The engine runs it automatically; nothing can skip it. | Harness engine; `check_model` tool |
| P8 | **Never assume an input.** Missing design inputs are asked for. Template defaults are shown and confirmed. Every value carries its source. | Design basis ([13](13-templates-and-design-basis.md)) |
| P9 | **Every outcome is honest.** A timeout whose effect is unknown is reported as `TIMEOUT_UNKNOWN_OUTCOME`, never as success or plain failure. Partial results say they are partial. | Tool contract §7 |
| P10 | **Decisions are fast, typed and recorded.** Rules first, then a typed decision model, then a language model, then the engineer. Every decision is logged with who made it and with what confidence. | Decision layer ([12](12-decision-layer.md)) |
| P11 | **The engineer stays in charge.** Write permissions are a user setting. Original models are protected by default. Outputs stay `DRAFT` until the engineer signs them. | Permission modes; UI |
| P12 | **A missing capability becomes a permanent tool, never ad-hoc code.** During a live project the tool is built or extended on a branch with tests (project lane); before reuse it passes the full process (release lane) ([ADR-0026](../adr/0026-project-lane-for-tools.md)). | Process ([02-work-items](../../process/02-work-items.md)) |

## 4. Quality attributes, in priority order

When two attributes conflict, the higher one wins.

1. **Correctness of engineering results.** A wrong number that looks right is the worst possible failure.
2. **Workflow accuracy.** Steps run in the defined order, every check runs, every decision is traceable.
3. **Performance.** Tool steps add little time beyond the host program's own work. Decisions take well under a
   second when a decision model is used. Targets are in [11-harness-engine](11-harness-engine.md) §10.
4. **Recoverability.** A crash, a host freeze, or a timeout never corrupts a model and never loses a run.
5. **Contributor friendliness.** Python by default, small repositories, clear contracts, tests that run without
   the host programs installed.
6. **Portability across host versions.** The design allows supporting older versions; testing starts with the
   latest versions only ([17](17-versioning-and-compatibility.md)).

## 5. What this system is not

- Not a chat app with tools bolted on. Chat may be one entry point; the product is the workflow engine.
- Not a general autonomous agent that explores a model until it finds an answer.
- Not a replacement for the engineer's responsibility. It is a fast, traceable assistant that refuses to guess.
- Not a single repository. Each tool is independent and useful on its own, including outside the harness.

## 6. Lessons carried over from the earlier projects

The earlier projects (Sasaah and Sasaah Agent) are references for this design, except Sasaah's MCP servers and tools,
which the harness uses directly ([ADR-0024](../adr/0024-harness-on-existing-sasaah-servers.md)). The following lessons
shape this design:

| Lesson | Consequence here |
|---|---|
| Script-runner tools (`run_script`, `invoke`) let agents write random code, and tasks took hours | Forbidden by P6 and [ADR-0008](../adr/0008-tool-naming-toolsets-no-escape-hatches.md) |
| Results returned as text forced agents to re-type numbers | `result_id` store and `$ref` inputs ([ADR-0005](../adr/0005-pass-by-reference.md)) |
| Unit state in ETABS was not restored after timeouts | Servers never leave host units changed; unit handling is centralized ([06](06-csi-servers.md) §5). Until the Sasaah CSI engine does this, the harness checks the model's units after every timeout or reconnect ([11](11-harness-engine.md) §6) |
| Timeouts were reported as plain failures although the write may have happened | `TIMEOUT_UNKNOWN_OUTCOME` plus idempotency keys ([ADR-0007](../adr/0007-write-safety.md)) |
| A modal dialog in Revit froze the request queue | Failure preprocessing and dialog suppression in the add-in ([07](07-revit-agent-bridge.md) §6) |
| Two servers for one host starved each other | Exactly one server per host instance, enforced by a lock in the harness ([11](11-harness-engine.md) §6) |
| Building a desktop host and agent loop consumed the effort while tools stayed thin | The harness reuses libraries for the model loop and owns only the workflow engine ([ADR-0011](../adr/0011-harness-owns-workflow-engine.md)) |
| Over half the code was never in version control | Every repository is in git from its first commit; CI is mandatory ([process](../../process/README.md)) |
| Processes at low integrity level could not drive host programs reliably | Servers run at the same integrity level as the host program ([16](16-security-safety-privacy.md) §6) |
| A server build older than its own fix failed every design run | The harness checks server builds and tool lists at run start ([ADR-0024](../adr/0024-harness-on-existing-sasaah-servers.md), [11](11-harness-engine.md) §6) |
| Save dialogs and analysis timeouts turned into manual steps for the engineer | Save before every analysis; timeouts reconciled, never retried blindly ([11](11-harness-engine.md) §6) |
| Agents met missing tools mid-project and wrote one-off scripts | Project lane: permanent tools with tests ([ADR-0026](../adr/0026-project-lane-for-tools.md)) |
| Sasaah Agent ran a free agent loop on Microsoft Agent Framework behind a WPF shell; the effort went there and no real engineering task was finished | The harness never uses Microsoft Agent Framework (its core or its free loop), a WPF interface, or the Sasaah Agent design system (owner's rule, 2026-11-03). It has its own engine ([ADR-0011](../adr/0011-harness-owns-workflow-engine.md)) and no graphical interface in phase 1 ([ADR-0027](../adr/0027-phase-1-interface.md)) |
| Sasaah Agent spent its phases on design documents and on fakes, and never finished a real engineering task | Every phase has a time box; scope is cut, never the exit criteria ([19](19-roadmap-and-spikes.md) §1) |
| Engineers edit the model by hand between turns, so it can change after an approval | Approvals are bound to what was shown and to the model, and checked again just before the write ([11](11-harness-engine.md) §3), as in Sasaah Agent's approval token |
