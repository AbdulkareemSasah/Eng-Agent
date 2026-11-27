# ADR-0010: Revit thin add-in, Python front end

Status: Superseded by ADR-0024 · Date: 2026-10-24

## Context

The Revit API runs only inside Revit, on its main thread, in .NET. The earlier Revit stack had a large C# tool catalog,
a queue without a depth limit, a conditional dialog that froze Revit's thread, and ambiguous busy and timeout states.

## Decision

- The C# add-in executes a fixed allowlist of operations through an `ExternalEvent`, one at a time, from a bounded
  queue, in transaction groups, with a failures preprocessor and dialog handling. It returns raw values in Revit
  internal units, tagged per value.
- The Python server owns tool schemas, validation, references, unit conversion, envelopes and the result store.
- Transport: per-instance named pipe, current user only, length-prefixed JSON, versioned handshake.
- Revisions follow Revit's document change events.

## Consequences

- The contract stays implemented once, in Python.
- Dry runs are exact (apply, then roll back).
- Adding a tool usually means a Python tool plus one add-in operation; both are reviewed together.

## Alternatives considered

- **C# MCP server inside or beside Revit**: duplicates the contract in C#. Rejected.
- **Adopt an existing open-source Revit MCP server**: loosely typed commands and no write-safety model; contributing
  these changes upstream would change their design fundamentally. Rejected; it remains a reference.
