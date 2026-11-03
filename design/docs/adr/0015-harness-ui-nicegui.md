# ADR-0015: Harness UI in NiceGUI

Status: Superseded for phase 1 by ADR-0027; NiceGUI stays a candidate for the later UI · Date: 2026-10-24

## Context

The owner wants a desktop or web application showing each workflow step by step. The harness is Python, managed with
uv only. A separate TypeScript front end would need a JavaScript toolchain and a second language.

## Decision

- Build the UI with NiceGUI (MIT), in Python, served locally on `127.0.0.1` with a session token, usable in a browser
  or as a native window.
- Spike S-09 must confirm Arabic right-to-left layout and live updates for long runs. Native window mode and packaging
  are checked when they are needed, after phase 1.
- If S-09 fails, the fallback is a TypeScript front end over a local HTTP API of the harness, by a new ADR.

## Consequences

- One language and one tool chain for the whole harness.
- UI flexibility is lower than a custom web front end; acceptable for an engineering tool.

## Alternatives considered

- **WPF desktop app** (the earlier choice): C# and Windows-only UI code. Rejected.
- **TypeScript web front end**: most flexible, second language and tool chain. Kept as fallback.
- **Other Python UI frameworks**: NiceGUI offers browser and native modes with live updates and a mature component set;
  others can be compared in S-09 if NiceGUI fails.
