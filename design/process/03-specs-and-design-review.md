# 03. Specs and Design Review

## 1. Spec types

| Spec | Use for | Lives in | Template |
|---|---|---|---|
| Feature spec | A capability spanning several tools, modules or files | `<repo>/docs/specs/NNNN-<slug>.md` | [feature-spec.md](templates/feature-spec.md) |
| Tool spec | One MCP tool (new or changed) | `<server repo>/docs/tools/specs/<tool_name>.md` | [tool-spec.md](templates/tool-spec.md) |
| Clause spec | One code-pack check | `structural-codes/packages/<pack>/specs/<check_id>.md` | [clause-spec.md](templates/clause-spec.md) |
| Workflow spec | A workflow or block, described by the owner | `eng-harness/docs/workflows/<name>.md` | [workflow-spec.md](templates/workflow-spec.md) |
| ADR | Any architectural decision | This hub, `docs/adr/` (repository-local decisions: `<repo>/docs/adr/`) | [adr.md](templates/adr.md) |
| Implementation plan | The tasks of one spec | `<repo>/docs/plans/<issue>-<slug>.md` | [implementation-plan.md](templates/implementation-plan.md) |

A spec is a contract for the implementation. If implementation shows that the spec is wrong, the spec is changed and
re-approved first, in its own pull request; the code never silently diverges from it.

Rules for spec and plan pull requests ([01](01-lifecycle.md) §4):

- A spec or plan pull request changes only spec or plan files. CI rejects a pull request that changes a spec or plan
  together with code or tests.
- Tool specs of one toolset may be grouped into one spec pull request and approved together, so the owner reviews a
  coherent set once instead of each tool separately.
- Front matter is mandatory (`id`, `issue`, `status`, `size`, `risk`; plans add the task list with files, size
  estimates and session estimates).

## 2. What every spec contains

- The problem and who has it, in one paragraph.
- Acceptance criteria in Given, When, Then form, including failure and edge cases.
- Inputs and outputs with types, units and bounds.
- Errors: which contract error codes, when.
- Non-goals: what this deliberately does not do.
- Risks and their class (R0 to R3).
- Test strategy: which test layers prove each criterion ([05](05-testing-and-verification.md)).
- Open questions, each with an owner. A spec with open questions does not pass G1.

## 3. Spec review checklist (G1)

- [ ] The problem is real and stated measurably; reuse of existing tools, libraries or hosts' features was checked.
- [ ] Acceptance criteria are complete, testable, and include failure cases.
- [ ] It respects the principles P1 to P12 ([01-vision](../docs/architecture/01-vision-and-principles.md) §3).
- [ ] It respects the server standard, the tool contract and the repository's boundaries.
- [ ] Units, bounds and error codes are declared for every input and output.
- [ ] Tool names, verbs and toolsets follow ADR-0008.
- [ ] No hidden assumptions: every default has a source, or is asked.
- [ ] Engineering content (R1) cites clauses and sources and has its verification plan.
- [ ] The version impact (patch, minor, major) is stated.
- [ ] Performance expectations are stated where they matter.

## 4. Design review for architecture changes

An ADR is required when a change affects: the layer structure, a repository boundary, the tool contract, a
cross-repository interface, a new runtime dependency, a new language, persistence formats, or security posture.
Reviews of ADRs include an adversarial pass: a reviewer argues the strongest alternative and the most likely failure
(pre-mortem) before the owner decides.

## 5. Plan review checklist (G2)

- [ ] Tasks are ordered as thin vertical slices; each task is one pull request.
- [ ] Every acceptance criterion maps to named tests in a task.
- [ ] Each task lists the files it will touch; no task touches files outside the repository.
- [ ] New dependencies are listed with their ADR.
- [ ] Risky tasks come first (spikes, unknown host behavior).
- [ ] The plan states how the work will be verified locally and, for hosts, live.
