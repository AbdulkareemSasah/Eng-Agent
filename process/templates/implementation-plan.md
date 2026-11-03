---
id: plan-{{issue}}-{{slug}}
issue: {{issue number}}
spec: {{path of the approved spec on main}}
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: {{trivial | small | standard | large}}
risk: {{r0 | r1 | r2 | r3}}   # binding for every pull request of this plan; never below the path risk floor
tasks:
  - id: T1
    title: {{short title}}
    files: ["src/<package>/tools/<module>.py", "tests/fake_host/test_<module>.py"]
    max_changed_lines: 300
    max_sessions: 2
    tests_first: ["tests/fake_host/test_<module>.py::test_<criterion>"]
    covers: [AC1, AC2]
    depends_on: []
---

# Implementation plan: {{title}}

## 1. Approach
{{Short summary. Reuse found during research. Risky parts first.}}

## 2. Tasks
{{One paragraph per task: what it does, why in this order. Each task is one pull request.}}

## 3. Dependencies
{{New runtime dependencies with ADR links; development dependencies with justification.}}

## 4. Verification
Local gate · fake-host scenarios · live acceptance needed before the next release: {{scripts, host versions}}

## 5. Rollback
{{How to revert safely if the change misbehaves after merge.}}
