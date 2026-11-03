---
name: Defect
about: Something behaves differently from its spec
labels: ["type/bug", "status/triage"]
---

## What happened
{{Observed behavior, with the exact tool call, inputs (references), error code or result id.}}

## What should happen
{{Expected behavior, with the spec section it violates.}}

## Reproduction
{{Steps, fixture or fake-host scenario. Host program and version if live.}}

## Engineering impact
{{Could this have produced a wrong number or a wrong model? If yes: risk/r1-engineering and severity critical
([process/10](../10-engineering-verification.md) §7).}}

## Environment
Package versions: {{...}} · Host: {{program and version}} · OS: {{...}}
