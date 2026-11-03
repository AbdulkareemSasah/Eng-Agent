# ADR-0002: Python with uv by default; C# only at the host boundary

Status: Proposed; amended by ADR-0024 (host servers stay in Sasaah, in C#) · Date: 2026-10-24

## Context

The owner wants tools that most developers can contribute to, in Python or TypeScript, with C# only where unavoidable.
Host programs differ: CSI programs expose a COM-accessible API; Revit and AutoCAD APIs run only in process on .NET;
CSI plugins must be .NET; IDEA StatiCa has a REST service with a Python client. The owner also requires uv as the only
Python development tool.

## Decision

- Python is the default language for every library, server and the harness.
- uv is the only tool for Python environments, dependencies, locking, running, building and publishing.
- C# is used only for: the Revit add-in of `revit-agent-bridge`, the CSI in-process plugin, the AutoCAD add-in, and the
  Revit product add-ins (Synapse, Sheet Exporter).
- Every MCP server's front end (tools, validation, contract) is Python, including Revit's. C# components are thin
  executors behind a local pipe.

## Consequences

- The tool contract is implemented once, in Python (ADR-0004).
- C# code stays small and focused on host threading, transactions and API calls.
- Python COM access to CSI programs must be validated (spike S-01).

## Alternatives considered

- **TypeScript**: strong MCP ecosystem, but weaker for numeric engineering work, COM access and engineering libraries
  such as ezdxf. Rejected as default; allowed later for a UI front end if NiceGUI fails (ADR-0015).
- **C# everywhere** (the earlier choice): best host access, but narrows contributors and duplicates the contract per
  language. Rejected.
