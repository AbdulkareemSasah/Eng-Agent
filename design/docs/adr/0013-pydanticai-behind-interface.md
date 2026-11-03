# ADR-0013: PydanticAI for language-model steps, behind an interface

Status: Proposed · Date: 2026-10-24

## Context

Some decision points (those that need unstructured context, such as reading notes on a drawing) need a general language
model with strictly typed output, from any provider. Reports are never written by a model: they are generated from
traces and journals. Building a model client layer ourselves is the effort
sink the earlier project fell into.

## Decision

- Language-model calls use PydanticAI (MIT): provider-agnostic, typed outputs as Pydantic models or literals, MCP
  client support, evaluation tooling.
- The engine never imports PydanticAI directly. It talks to an internal `LLMProvider` interface; one implementation
  uses PydanticAI.
- The PydanticAI version is pinned in `uv.lock` and upgraded deliberately with the evaluation suite as the gate.
- Language models never call MCP tools inside workflows; the engine calls tools. A model only returns a typed answer;
  its rationale text may not contain digits.
- Introduced in phase 2. Phase 1 uses rules, the decision model and the engineer only.

## Consequences

- Swapping the library later touches one adapter.
- Fast-moving library releases do not break workflows unexpectedly.

## Alternatives considered

- **LangGraph or LangChain**: heavier and broader than needed. Rejected.
- **A vendor agent SDK**: built for autonomous agents and tied to one vendor. Rejected.
- **A hand-written client over raw HTTP**: re-implements typed outputs and retries. Rejected.
