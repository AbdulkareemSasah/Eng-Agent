---
id: spec-{{NNNN}}-{{slug}}
issue: {{issue number}}
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: {{trivial | small | standard | large}}
risk: {{r0 | r1 | r2 | r3}}
---

# Spec NNNN: {{title}}

Package: {{package}} · Author: {{identity}} · Date: {{yyyy-mm-dd}}

## 1. Problem
{{Who has the problem, what it costs today, in measurable terms.}}

## 2. Reuse research
{{Existing tools, libraries, host features checked, and why they are or are not enough.}}

## 3. Acceptance criteria
- AC1. Given {{state}}, when {{action}}, then {{observable result}}.
- AC2. Given {{invalid input}}, when {{action}}, then {{error code}} with {{fields}}.
- {{...}}

## 4. Design
{{Components touched, data flow, interfaces. Diagrams welcome. Link the architecture documents it follows.}}

## 5. Inputs and outputs
| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|

## 6. Errors
| Condition | Contract error code | Fields |
|---|---|---|

## 7. Non-goals
- {{...}}

## 8. Risks
| Risk | Class | Mitigation |
|---|---|---|

## 9. Test strategy
| Criterion | Test layer | Test name (planned) |
|---|---|---|

## 10. Version impact
{{patch / minor / major, and why}}

## 11. Open questions
| Question | Owner | Answer |
|---|---|---|
