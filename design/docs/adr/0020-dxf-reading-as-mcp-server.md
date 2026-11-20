# ADR-0020: DXF reading as its own MCP server

Status: Superseded by ADR-0024 · Date: 2026-10-24

## Context

The first workflow starts from DXF drawings. Reading DXF needs no host program. Putting it inside the harness would
break the rule that the harness reaches the world only through tools; putting it in the AutoCAD add-in would require
AutoCAD.

## Decision

- `dxf-mcp` is a small Python MCP server based on ezdxf (MIT) that reads drawings and extracts geometry candidates
  deterministically, by reference, under the same server standard.
- Interpreting what layers and candidates mean is a harness decision, not a server function.

## Consequences

- The DXF capability is reusable by anyone and testable with sample drawings.
- One more repository in phase 1, small in size.

## Alternatives considered

- **DXF parsing inside the harness as calc functions**: mixes file I/O into the engine. Rejected.
- **Live AutoCAD through the add-in**: needs AutoCAD and is slower. Rejected for this purpose.
