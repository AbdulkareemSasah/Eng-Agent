# ADR-0006: One canonical unit system with unit-suffixed field names

Status: Proposed · Date: 2026-10-24

## Context

Host programs use different and changeable unit systems (ETABS present units, Revit internal feet). The earlier project
had unit state that was not restored after timeouts, which can turn every later number wrong.

## Decision

- All values crossing the contract use `canonical/1`: mm, kN, kN·m, MPa, kN/m, kPa, kN/m³, kg, degrees, seconds, °C
  ([04](../architecture/04-tool-contract.md) §4).
- Every unit-bearing field name carries its unit suffix (`b_mm`, `P_kN`), and the schema states the unit as metadata.
- Conversions are implemented once, in `eng-contract.units`, with exact factors and tests.
- Servers never leave a host in different units than they found it; changes are restored and verified.

## Consequences

- Any reader (human, model or code) sees the unit in the name; mixing units becomes visible in review.
- Coordinates in mm produce large numbers for big sites; float64 handles this without precision issues at building
  scale.

## Alternatives considered

- **Quantity objects everywhere**: safest for generic data, verbose for tool parameters. Used inside generic tables only.
- **Host units passed through**: pushes unit knowledge to every consumer. Rejected.
- **A units library such as pint**: heavy dependency for a fixed, small set of conversions. Rejected for the contract.
