# ADR-0001: `mcp` (official MCP Python SDK) as a runtime dependency of eng-harness

Status: Proposed · Date: 2026-11-04 · Deciders: owner

## Context
The harness talks to the existing Sasaah servers over MCP ([ADR-0024](../../../../design/docs/adr/0024-harness-on-existing-sasaah-servers.md))
and needs a protocol client: session handshake, `tools/list`, `tools/call` with a read timeout and cancellation, and the
JSON-RPC message types ([spec 0002](../specs/0002-servers-and-adapters.md) section 2 and 4.3.3). Process/04 section 7
requires an ADR for a runtime dependency.

Resolved on 2026-11-04 by `uv add` (CPython 3.14.6, Linux): `mcp` 2.3.0 and `mcp-types` 2.3.0. Only the SDK's `Client`
and message types are used; its `stdio_client` is not (spec 0002 section 2), because it creates its Job Object after the
spawn and without breakaway.

## Decision
Declare `mcp>=2.3,<3` as a direct runtime dependency of `packages/eng-harness`, locked in `uv.lock`. It is imported only
from `servers/` (transport and session modules of later plan tasks). `httpx2` 2.16.0 in the lock is the same version as
in [ADR-0003](0003-httpx2.md), so the lock holds one HTTP stack.

Amendment B-124 (servers plan T5, B-373): `anyio>=4.16,<5` is also declared as a direct dependency, because the process
transport builds the anyio memory-object streams the SDK's client session reads; it is already locked through `mcp`
(4.16.0, MIT), so the lock gains no package.

| Package (resolved version) | Role | License | Installed size |
|---|---|---|---|
| `mcp` 2.3.0 | MCP client and server framework | MIT | 1171 KiB |
| `mcp-types` 2.3.0 | Protocol message types | MIT | 346 KiB |
| `anyio` 4.16.0 | Async layer; direct dependency since amendment B-124 (memory-object streams of the process transport) | MIT | within the next row's size |
| `httpx2` 2.16.0, `httpcore2` 2.16.0, `httpx2-jsfetch` 1.0 | HTTP transports (unused by us) | MIT, BSD-3-Clause | about 1.3 MiB (including `anyio`) |
| `starlette` 1.10.0, `uvicorn` 0.54.0, `sse-starlette` 3.6.0, `python-multipart` 0.0.33 | Server-side web stack of the SDK (unused by us) | BSD-3-Clause, Apache-2.0 | about 0.7 MiB |
| `jsonschema` 4.26.0 with `referencing`, `rpds-py`, `attrs`, `jsonschema-specifications` | Schema validation | MIT | about 1.9 MiB |
| `pyjwt` 2.15.1, `cryptography` 50.0.2, `cffi` 2.1.1, `pycparser` 3.12 | Authentication helpers (unused by us) | MIT, Apache-2.0 OR BSD-3-Clause, MIT-0 | about 15.7 MiB |
| `opentelemetry-api` 1.45.2, `h11`, `idna`, `truststore`, `typing-extensions`, `typing-inspection`, `pydantic` (already locked) | Supporting libraries | Apache-2.0, MIT, BSD-3-Clause | small |
| `pywin32` 312 | Windows only, transitive | as published | not installed on Linux |

Licenses are as published in package metadata (not read for `httpx2-jsfetch` and `pywin32`); the gate's license check
covers the whole lock.

## Consequences
- Easier: a maintained protocol implementation; no hand-written JSON-RPC.
- Harder: a large transitive set (web server and cryptography packages we never call), a young 2.x line, and a
  Windows-only `pywin32` dependency. An SDK release can change `Client` or `Transport`; the exact lock and the session
  tests catch it.

## Alternatives considered
- **Hand-written JSON-RPC client over stdio**: no new dependency, but we would own protocol versions, cancellation and message types.
- **SDK 1.x**: lacks the `Client` and `Transport` API the spec relies on.
- **PydanticAI's MCP client**: ties server sessions to an agent framework and hides the process ownership the Job Object design needs.

## Pre-mortem
A later SDK 2.x release changes `Client` or `Transport` and the session stops attaching to our process. Early warning: the
workflow session tests of plan 0002 T5 fail at the upgrade pull request, before it merges. The owner should also confirm
that the large transitive set is acceptable.
