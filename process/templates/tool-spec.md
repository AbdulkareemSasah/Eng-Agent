---
id: tool-{{prefix}}_{{verb}}_{{noun}}
issue: {{issue number}}
status: draft        # draft | approved
size: {{small | standard}}
risk: {{r0 | r1 | r2 | r3}}   # write tools are at least r1; schema changes are at least r2
---

# Tool spec: `{{prefix}}_{{verb}}_{{noun}}`

Server: {{package}} · Toolset: {{toolset}}

## 1. Purpose
{{One sentence: what it does. If it needs "and" or "or", split the tool.}}

## 2. Host API used
{{Methods or operations, with links to the host documentation. Known quirks and return codes.}}

## 3. Annotations
readOnly: {{yes/no}} · destructive: {{yes/no}} · idempotent: {{yes/no}} · openWorld: no · timeout class: {{fast/normal/long}}

## 4. Input schema
| Parameter | Type | Unit | Bounds or enum | Required | Ref-capable | Engineering quantity | Stale-ok | Description |
|---|---|---|---|---|---|---|---|---|
| `op_id` | string | | | write tools: yes | no | no | | Idempotency key |
| `dry_run` | boolean | | | no (default false) | no | no | | Return the change set without applying |

Batch limit: {{n}} items. Paging: {{offset/limit defaults}}.

## 5. Output
Kind: `{{host}}.{{name}}/1` · Summary fields: {{list}} · Payload schema: {{fields with units}}

## 6. Preconditions and errors
| Condition | Error code | Retryable |
|---|---|---|

## 7. Write behavior (write tools only)
Op ledger entry (intent, planned objects) · deterministic names of created objects · change set contents · dirty
marking · how `reconcile_operation` detects `applied`, `partial` and `not_applied` · confirm requirement · accepted
input kinds (neutral `model.*` kinds and own kinds only).

## 8. `check_model` impact
{{New issue codes this tool can create or resolve.}}

## 9. Tests
| Case | Layer (fake host, contract, live) | Expected |
|---|---|---|

## 10. Live acceptance
{{The script steps the owner runs, and what is recorded for fake fidelity.}}
