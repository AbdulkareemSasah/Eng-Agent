# ADR-0035: No changed-line limit per task

Status: Accepted (decided by the owner, 2026-11-17); amended by ADR-0036 · Date: 2026-11-17

## Context

Each plan task carried `max_changed_lines`, and reaching it meant `BLOCKED` and a plan amendment (A22). `gate-check`
failed a pull request over the estimate (GC009), and the gate's plan parser capped a task at 400 lines
(`limits.max_task_lines`). In practice, tasks stopped repeatedly for plan amendments over a few lines, for example a
77-line change against an estimate of 60. The stops cost owner time and added no review value: the file scope already
keeps a task inside its plan.

## Decision

1. There is no limit on changed lines per task or per pull request.
2. `max_changed_lines` stays in plan front matter as an informational estimate. Exceeding it is never a failure, never
   a reason to stop and never needs a plan amendment.
3. `gate-check` no longer fails on size: GC009 becomes a notice that reports the counted lines, the plan estimate and
   the largest files. The plan-parsing cap `limits.max_task_lines` is removed.
4. Unchanged: a file outside the task's `files` globs still fails `gate-check` (GC008) and needs a plan amendment;
   `max_sessions` stays a session budget (A22); test-first, the risk floor and every other check stay.
5. Reviewers judge whether a pull request is reviewable and may ask for a split as a finding; size alone never blocks.

## Consequences

- Tasks finish without amendments over line counts.
- Larger pull requests are possible; reviewers may still ask for a split.
- The file-scope rule remains the gate that keeps a task inside its plan.
- The gate (`eng-dev-gate`, GC009 and `limits.max_task_lines`) and every generated `AGENTS.md` must be updated.

## Alternatives considered

- **Raise the limit or add a tolerance**: still stops tasks over a number that predicts little. Rejected.
- **Keep the limit, let reviewers waive it**: still a stop and an owner decision per overrun. Rejected.

## Pre-mortem

The likely failure is pull requests too large to review well. Early warning: reviewer findings asking for splits, or
missed defects in large diffs. The answer is better task planning, not a new hard limit.
