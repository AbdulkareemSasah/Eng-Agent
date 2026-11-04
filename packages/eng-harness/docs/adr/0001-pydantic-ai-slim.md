# ADR-0001: pydantic-ai-slim (OpenAI-compatible models) as a runtime dependency of eng-harness

Status: Proposed · Date: 2026-11-04 · Deciders: owner

## Context
The language-model tier of the decision layer needs a model client with strictly typed output, for OpenRouter and for
local OpenAI-compatible servers ([ADR-0013](../../../../design/docs/adr/0013-pydanticai-behind-interface.md), spec
[0009](../specs/0009-providers.md) §4.7). Process/04 §7 requires an ADR for each runtime dependency: purpose,
alternatives, license, maintenance health, size. ADR-0028 §5 already names PydanticAI 2.65 as resolving on CPython 3.14.

The figures below were measured on 2026-11-04 in a scratch uv project outside the repository (CPython 3.14.6, Linux),
adding `pydantic-ai-slim[openai]`, `keyring` and `httpx2`; sizes are the installed files listed in each package's
`RECORD`. Licenses are those published in each package's metadata and are to be verified for the whole lock by the
gate's license check. Maintenance health is for the owner to confirm at review.

## Decision
Add `pydantic-ai-slim` with the `openai` extra to `packages/eng-harness`, pinned exactly in `uv.lock`. It is imported by
one module only (`providers/_llm.py`, with `_llm_types.py` for the output model), behind the internal `LLMProvider`
interface; the engine never imports it.

| Package (resolved version) | Role | License | Installed size |
|---|---|---|---|
| `pydantic-ai-slim` 2.65.0 | Agent, typed output, test models | MIT | 9779 KiB |
| `openai` 3.45.0 (extra `openai`) | OpenAI-compatible client used for OpenRouter and local servers | Apache-2.0 | 9402 KiB |
| `tiktoken` 0.14.0 (extra `openai`) | Required by the extra | MIT | 3694 KiB |
| `genai-prices` 0.2.1 | Price tables, unused by the adapter | MIT | 1616 KiB |
| `pydantic-graph` 2.65.0 | Agent graph runtime | MIT | 184 KiB |
| `griffelib` 2.4.1 | Documentation parsing | ISC | 667 KiB |
| `opentelemetry-api` 1.45.2 | Instrumentation API, no exporter | Apache-2.0 | 192 KiB |
| `jiter` 0.18.0 | JSON parsing | MIT | 774 KiB |
| `logfire-api` 5.4.0 (via `pydantic-graph`) | No-op shim without `logfire` | MIT | 438 KiB |

Other transitive packages (`anyio`, `typing-inspection`, `regex`, `requests` and its dependencies, among them) are
covered by the gate's license check; `pydantic` is already a dependency. The HTTP client library is the subject of
[ADR-0003](0003-httpx2.md). No telemetry exporter is installed, and the adapter enables none (spec AC24).

## Consequences
- Easier: typed output validation, model test doubles (`FunctionModel`, `TestModel`) for CI without the network, one
  adapter to swap if the library is replaced.
- Harder: a large, fast-moving dependency set (26746 KiB, about 26 MiB, for the packages in the table). Upgrades are separate
  pull requests, gated by the evaluation reports of spec 0009 §4.10 (a changed model or prompt revision returns a point
  to shadow mode).
- Only OpenAI-compatible endpoints are supported in v1; another native provider (for example the `anthropic` or
  `google` extras) needs its own extra and an amendment of this ADR.
- The `typesafe` extra (`typesafe-sdk`, MIT) exists in the same release and is not added here; whether the Jev adapter
  uses it is decided after spike S-07 (spec 0009 Q1).

## Alternatives considered
- **The `openai` SDK directly**: no typed-output layer; the validation and test doubles would be written by hand, and
  ADR-0013 rejected a hand-written client.
- **LangChain or LangGraph**: heavier and broader than needed (ADR-0013).
- **LiteLLM**: a gateway with many providers and a large surface; not needed for two endpoint kinds.
- **A vendor agent SDK**: tied to one vendor (ADR-0013).
- **A raw HTTP client with hand-written JSON-schema handling**: re-implements retries and typed outputs (ADR-0013).

## Pre-mortem
A release changes structured-output behavior or the names of the extras, and the language-model tier starts returning
invalid answers or fails to import. Early warning: the adapter tests against the pinned version fail in CI at the lock
upgrade, and the evaluation of the point shows more `invalid_output` suggestions; the exact pin limits the blast radius
to the pull request that upgrades it.
