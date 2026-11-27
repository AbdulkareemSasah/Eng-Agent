# ADR-0011: The harness owns a workflow engine; one composable block abstraction

Status: Proposed · Date: 2026-10-24

## Context

The owner wants a personal engineering harness where he defines workflows with specific steps. A general agent that
explores with all tools is slow and unpredictable. The earlier Sasaah Agent spent most effort on a desktop shell and an
agent loop while the model stayed scripted and no workflow engine existed.

## Decision

- The harness's core is a deterministic workflow engine. The engine, not a model, decides the order of steps.
- Blocks and workflows are **typed Python** async functions with Pydantic input and output models. A workflow is a
  top-level block; blocks compose.
- Blocks interact only through `ctx` (tools, calcs, decisions, inputs, approvals, child blocks, parallel steps,
  bounded attempts, escalation).
- Block code has no direct I/O, no engineering arithmetic, and is deterministic.
- The owner describes workflows in a plain-language workflow spec; developers implement them as blocks under the
  normal process.

## Consequences

- Fast runs: tool steps involve no model; decisions involve a model only when rules do not match.
- Workflows are testable with fake hosts and replayable from journals.
- Writing a workflow requires a developer (human or agent) following the process, rather than editing a text file.

## Alternatives considered

- **YAML workflow definitions**: needs an expression language for variables, conditions and loops that grows
  without types or tests. Rejected.
- **A general agent framework that plans its own steps**: contradicts the owner's goal of defined steps. Rejected.
- **A graph library (for example LangGraph) as the engine**: heavier abstractions than needed; the engine's core is
  small and central to the product. Rejected.
