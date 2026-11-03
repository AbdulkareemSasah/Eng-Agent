# 08. IDEA StatiCa Server: `ideastatica-mcp`

Status: Superseded as a build plan by ADR-0024: the harness uses Sasaah's `sasaah-idea-mcp` · Phase 4 · Language: Python

## 1. Shape

- Python MCP server that drives IDEA StatiCa Connection through its official REST service
  (`IdeaStatiCa.ConnectionRestApi`) and IDEA's published Python client package (`ideastatica_connection_api`).
- The server starts the REST service on a local port when it is not running, attaches to it, and stops it on exit if
  it started it.
- No C# is needed. If a required capability exists only in IDEA's .NET API, it is recorded as a gap and decided by ADR.

## 2. Tool scope (intended; fixed by tool specs)

| Toolset | Tools (without the `idea_` prefix) |
|---|---|
| file | `open_project`, `save_project`, `create_project_from_template` |
| read | `list_connections`, `get_connection_summary`, `list_members`, `list_operations`, `list_load_effects` |
| define | `set_load_effects`, `apply_connection_template`, `set_plate_thickness`, `set_bolt_assembly`, `set_weld_size` |
| analysis | `run_calculation` |
| results | `get_check_results`, `get_stress_strain_results` |
| core | standard tools, including `check_model` (connection integrity: unconnected members, missing load effects, invalid operations) |

## 3. Verdicts from IDEA

IDEA StatiCa evaluates its own code checks. `get_check_results` returns them in the contract verdict shape with
`source: host`, the code and edition configured in the IDEA project, and IDEA's own check identifiers. They are
host-native verdicts, clearly labeled, and are never merged with code-pack verdicts. Agreement between IDEA results
and future code packs is a verification activity, not a runtime merge.

## 4. Load effects by reference

`set_load_effects` accepts references to neutral `forces.member_end/1` results ([04](04-tool-contract.md) §6), as
produced by the CSI servers (for example the end forces of the members meeting at a joint). Selecting the members of a
joint is a harness calc. The server reads the forces from the store and maps them to IDEA's load effect format,
including sign convention and member end mapping. The mapping rules are part of the tool spec and are tested with
recorded examples. No agent ever copies forces into IDEA.

## 5. Open questions (spike S-08)

- Exact coverage of the Python client for editing operations versus templates only.
- Licensing behavior of the REST service when no seat is available (must map to `HOST_NOT_CONNECTED` or
  `PRECONDITION_FAILED`, never hang).
