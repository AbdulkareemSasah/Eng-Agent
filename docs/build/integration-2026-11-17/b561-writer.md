# B-561 writer handoff

Status: DONE; independent lead review and integration remain.

Work item B-561 / DOC.B561, documents-only amendment; risk r2, r3; large inherited document size. Plan-Task: none (spec and plan). Authorized scope is exactly the two frontmatter amendments below. No source, risk-map, acceptance criteria, task, estimate, dependency, tooling, state or ops changes. One writing session; no new task or session allocation.

Branch: docs/b561-gate-plan-risk-r2
Worktree: <worktrees>/b561
Base: d9c19fbddf59078bcd44ed4f7eee5f0806e70697
Head: 77ce9dd07475471d54809e1a1244ca7d063a44b5
Commit identity: Claude <noreply@anthropic.com>; sole trailer Assisted-by: anthropic/claude.

Pause check: .lead/locks/pause.lane absent before creating the worktree. Fetched origin/build/v1 and created the fresh branch from d9c19fbd. Read root and gate AGENTS, .lead/PLAYBOOK.md, process 08 and 06, relevant plan/spec frontmatter and T40, root and contract member risk maps, B553 contract-render diff, B553 body and .lead/logs/b553-base-risk-floor.log. Gate member has no additional .gate/risk-map.yml. Root packages/eng-contract/** and the contract member ** map raise r2 for the required render/metadata; tools/eng-dev-gate/** raises r3. Existing RF001 correctly blocks B553 against its old base plan [r3]. This amendment retains all enforcement and adds r2; it is not a body-only exception. Future implementation bodies must match r2,r3; historical tasks remain judged by their bases.

Measured scope: 2 files, 6 additions and 2 deletions = 8 counted lines. No other tracked change. git diff --check passes. No implementation tests were added for this reversible metadata edit; formal test-first reports docs exemption.

Commands and evidence (each uv command uses UV_CACHE_DIR=./.lead/uv-cache and UV_PYTHON_INSTALL_DIR=./.lead/python):

- uv sync --all-packages --locked: exit 0; run exactly once; .lead/logs/b561-sync.log. Existing uv-build/current uv version compatibility warnings were printed; sync completed successfully.
- uv run --no-sync --project ./.worktrees/full-ci eng-gate --root <worktrees>/b561 --gate-root ./.worktrees/full-ci gate-check --event ./.lead/pr/b561-enforcement-event.json: exit 0, awaiting-owner only AW02, AW08 and AW03; .lead/logs/b561-base-gate-check.log.
- Same base-installed command replacing gate-check with risk-floor: exit 0, risk-floor: pass; .lead/logs/b561-base-risk-floor.log.
- The full-ci checkout is base d9c19fbd; these commands use its installed unchanged gate and policy checkout, against this branch/head. The event names branch docs/b561-gate-plan-risk-r2, base build/v1 d9c19fbd, head 77ce9dd0, docs title, B-561, Plan-Task none (spec and plan), Risk r2, r3. Its body is the writer body. It is a local enforcement fixture only, never a real localCI run or PR. The base documents rule reads the union of amended document risks at head, and does not require the implementation PR risk match rule.
- uv run --no-sync eng-gate test-first --base d9c19fbddf59078bcd44ed4f7eee5f0806e70697 --head HEAD --title "docs(eng-dev-gate): include contract render risk in the gate plan (B-561)": exit 0, skipped (exempt: type docs); .lead/logs/b561-test-first.log.
- uv run eng-gate check --package eng-dev-gate --skip mutation: exit 0, check: pass at head 77ce9dd07475471d54809e1a1244ca7d063a44b5; .lead/logs/b561-check.log.
- git diff --numstat origin/build/v1 HEAD: 3 additions/1 deletion in each document.
- git diff --check: exit 0; git status --short: clean.

Mutation is not run because this is documents-only; no workspace-wide additional tests or real localCI dry run were run. No PR or merge. Complete writer PR body: .lead/pr/b561-body.md. Exact diff also saved at .lead/logs/b561-exact.diff.

Remaining: independent lead review, integration local CI and PR/merge by lead. Early push result is recorded below. No self-approval claimed.

Exact diff:

```diff
diff --git a/tools/eng-dev-gate/docs/plans/0001-eng-dev-gate-0.1.md b/tools/eng-dev-gate/docs/plans/0001-eng-dev-gate-0.1.md
index f7d90a51..bd60ff93 100644
--- a/tools/eng-dev-gate/docs/plans/0001-eng-dev-gate-0.1.md
+++ b/tools/eng-dev-gate/docs/plans/0001-eng-dev-gate-0.1.md
@@ -4,7 +4,9 @@ issue: "B-004"
 spec: tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md
 status: draft            # draft | approved (approved only by merging this file's own pull request)
 size: large
-risk: r3                 # binding for every pull request of this plan; never below the path risk floor
+risk: [r2, r3]           # binding for every pull request of this plan; never below the path risk floor
+# Amendment (B-561): T40 requires packages/eng-contract/AGENTS.md and .gate/agents.yml
+# under that package; their existing contract path floor adds r2 to the gate's r3.
 tasks:
   - id: T1
     title: Package skeleton, dependency ADR, CLI shell
diff --git a/tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md b/tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md
index 94856185..d208032e 100644
--- a/tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md
+++ b/tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md
@@ -3,7 +3,9 @@ id: spec-0001-eng-dev-gate-0-1
 issue: "B-004"
 status: draft        # draft | approved (approved only by merging this file's own pull request)
 size: large
-risk: r3
+risk: [r2, r3]
+# Amendment (B-561): T40 requires packages/eng-contract/AGENTS.md and .gate/agents.yml
+# under that package; their existing contract path floor adds r2 to the gate's r3.
 ---

 # Spec 0001: eng-dev-gate 0.1, the shared process gate
```

Package gate exact result at 77ce9dd07475471d54809e1a1244ca7d063a44b5:

```text
mode: bootstrap
check: pass
  lock: pass
  config: pass
  format: pass
  lint: pass
  types: pass
  forbidden: pass
  imports: pass
  ratchet: pass
    [notice] .gate/ratchet.json: RT001 tools/eng-dev-gate: noqa count fell from 19 to 18; run `ratchet --update`
  secrets: pass
  tests: pass
  docs-fresh: pass
  licenses: pass
  workflows: pass
```
