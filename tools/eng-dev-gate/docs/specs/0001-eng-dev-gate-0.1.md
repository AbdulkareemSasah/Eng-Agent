---
id: spec-0001-eng-dev-gate-0-1
issue: "B-004"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: r3
---

# Spec 0001: eng-dev-gate 0.1, the shared process gate

Package: `eng-dev-gate` (`tools/eng-dev-gate`) · Author: agent identity (task B-004) · Date: 2026-11-03

Governing documents: [process/11](../../../../design/process/11-repository-standard.md) §4 and §5,
[process/05](../../../../design/process/05-testing-and-verification.md) §2, §3, §8 and §9,
[process/01](../../../../design/process/01-lifecycle.md) §4 to §6 and §9,
[process/06](../../../../design/process/06-review-and-merge.md),
[ADR-0021](../../../../design/docs/adr/0021-agent-agnostic-ci-enforced-process.md),
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md). The plan is
[0001-eng-dev-gate-0.1](../plans/0001-eng-dev-gate-0.1.md). Where a rule here goes beyond the process documents, §11
lists it as a question for the owner. In bootstrap mode this spec counts as reviewed once a subagent that did not write
it has reviewed it and it is on `build/v1` (ADR-0028 §4); the owner still approves it later.

## 1. Problem

The process says that wherever a machine can check a rule, a machine checks it (process README, ADR-0021). Today nothing
does: there is no `eng-gate` command, the CI is a skeleton, and every rule of process 01, 04, 05, 06 and 11 that an agent
can satisfy by itself (labels, comments, tests written after the code, suppressions, a lowered threshold, a changed
workflow) is only prose. ADR-0021 records that such rules do not hold; ADR-0026 records 61 one-off scripts written under
time pressure without a single test.

Measurable outcome for 0.1: every rule below that a machine can decide is decided by `uv run eng-gate <command>` on the
workstation and by the same command in CI, with a stable exit code and a stable diagnostic code; every rule that needs
the owner or another identity is reported as `awaiting owner` in bootstrap mode, never skipped silently; and the
workspace passes its own gate. Each acceptance criterion in §3 is a test against a temporary git repository.

## 2. Reuse research

| Need | Candidate | Decision |
|---|---|---|
| Format, lint, types, tests, coverage | ruff, mypy, pytest, coverage.py | Used. Pinned by the gate itself, so a package cannot pick older or weaker versions |
| Import layers | import-linter | Not used. Its contracts are configured by the package under check (the package could weaken them), it knows nothing of the workspace metadata (layers, public modules, declared dependencies), and "Sasaah import" and "undeclared dependency" are not expressible. The AST pass is small |
| Pattern lint (forbidden rules) | A ruff plugin; an external rule engine | Ruff loads no custom rules. An external rule engine adds a dependency and a second language; Python AST visitors are tested with the package's own tools and read the workspace configuration |
| Secret scan | GitHub secret scanning and push protection; detect-secrets; Go scanners | The GitHub features are enabled at identity setup (process/11 §7) as a second layer, but cannot be tested offline. Go scanners are binaries (uv only, no vendor binaries). A small pattern scan of added lines avoids a dependency and a baseline format; detect-secrets stays the fallback if false negatives appear |
| Dependency vulnerabilities | `uv audit` (uv 0.11, options checked: `--locked`, `--frozen`, `--output-format`) | Used by the `security` job; no custom code |
| Mutation testing | mutmut, cosmic-ray | Open: chosen in the mutation task after a Windows support check (§11 Q4) |
| License check | pip-licenses | Not used. `importlib.metadata` gives the same data in about thirty lines and avoids a dependency |
| Workflow lint | actionlint (Go binary), zizmor (a Rust tool distributed on PyPI) | Three rules are written here (pinned actions, permissions, expression injection). zizmor is a candidate to evaluate after 0.1 |
| Front matter and templates | python-frontmatter, Jinja2 | Not used. Front matter is a `---` block parsed with a YAML safe loader; rendering is plain, byte-exact substitution with no logic |
| Reusable CI | Reusable workflows (process/11 §4) | Replaced by composite actions kept in this package (lead decision), so they move with the package when it is split |
| Prior art in Sasaah | None found (a single CI file) | No code is copied between repositories (A12) |

## 3. Acceptance criteria

All tests use temporary git repositories built by a fixture (never this repository's history) and fake ports for
external tools, the clock and GitHub (§4.1).

General and modes
- AC1. Given any command, when it ends, then the exit code is 0 (pass, including awaiting owner), 1 (a rule failed),
  2 (usage or configuration error) or 3 (environment or tool error), and `--format json` prints the result schema of §5.
- AC2. Given bootstrap mode and a check that needs the owner or another identity (§4.4), when it runs, then it prints a
  GitHub Actions `::notice` titled `awaiting owner`, appends the same text to the job summary file, and exits 0.
- AC3. Given bootstrap mode off, when the same conditions arise, then the check verifies the condition or fails, and
  never reports `awaiting owner`.
- AC4. Given any environment variable, command-line option or package configuration, when the mode is read, then none
  of them can switch it; the mode comes only from `bootstrap.enabled` in the root `.gate/gate.yml` (from the gate root, which is the
  base commit, in pull-request context, §4.16); a missing or invalid file exits 2.
- AC5. Given `bootstrap.enabled: false` and an empty `identities` block, when any command runs, then it exits 2 with
  CF008.

gate-check (§4.5)
- AC6. Given a pull request body with one `Plan-Task:` line and one work-item line (lines inside code fences and HTML
  comments are ignored) and a plan and spec on the gate branch, when `gate-check` runs, then the task is found and the
  check passes.
- AC7. Given a missing, duplicate or malformed `Plan-Task:` line or a missing work item, when it runs, then GC001,
  GC002 or GC003.
- AC8. Given a plan or spec that is not on the gate branch, then GC004; given `status: draft`, then it passes in
  bootstrap mode and fails with GC006 otherwise.
- AC9. Given a task id that the plan does not define, then GC007.
- AC10. Given a changed file that matches none of the task's globs (a rename counts both paths), then GC008 for each.
- AC10a. Given a changed `CHANGELOG.md` or `docs/local-testing.md` of a workspace member or of the plan's package folder, and another changed file under the same directory that matches a task glob, then no GC008 for those two files; without such a file they are GC008 like any other.
- AC10b. Given a changed `.gate/ratchet.json` whose changed counts all belong to packages with another in-scope change, then no GC008 for it; a changed count of any other package is GC008. Each of these gives GC008 as well: a changed `version` field; a package key added, removed or renamed without a count change of an in-scope package; a lowering (`ratchet --update`) of another package's count; a change anchored only by the workspace root (`.`).
- AC11. Given a diff, when counting lines, then additions plus deletions of files that are not tests, generated files or
  spike files are summed; above `max_changed_lines` gives GC009 and names the largest files.
- AC12. Given a pull request that changes a spec or a plan, when it also changes any other file, then GC010; its
  `Plan-Task:` line must be `none (spec and plan)`.
- AC13. Given a plan whose front matter is invalid, whose task ids repeat, whose `depends_on` is cyclic or unknown, whose
  task exceeds the size cap, or that leaves an acceptance criterion of its spec uncovered, then GC005 or GC016.
- AC14. Given a branch `lane/<issue>-<slug>`, when the pull request is a draft, then gate-check passes with a notice;
  when it is not a draft or its name is malformed, then GC012.
- AC15. Given `Plan-Task: none (<reason>)`, when the reason is not in the table of §4.5 or the diff does not fit it,
  then GC011.
- AC16. Given bootstrap mode, when a pull request sets `status: approved` on a spec or plan, then GC014; given normal
  mode, then the approvals of process/01 §5 are verified through the approvals port (GC015).
- AC17. Given a pull request that changes a path covered by `CODEOWNERS`, then AW02 in bootstrap mode, and a verified
  owner approval otherwise.
- AC18. Given bootstrap mode and a pull request from the gate branch into `main`, then AW06; given any other base branch
  than the gate branch, then GC013.

risk-floor (§4.6)
- AC19. Given the maps `.gate/risk-map.yml` and `<package>/.gate/risk-map.yml` at the base and head commits, when
  `risk-floor` runs, then the floor is the union of the risks of every matching entry, and every risk of the floor is in
  the recorded set (RF001 otherwise).
- AC20. Given a recorded risk that is a set of several risks and a body line `Risk:`, then the body must name the same
  set (RF002); on a lane branch the body line is the recorded risk.
- AC21. Given a malformed map or an unknown risk class, then RF003 and exit 2.
- AC21a. Given a `Plan-Task: none (<reason>)` pull request whose reason is not `spec and plan` and exactly one body `Risk:` line, then that set is the recorded risk; without one, RF004 (amendment B-336).

test-first (§4.7)
- AC22. Given a title in Conventional Commits form, when the type is `docs`, `chore`, `ci` or `release`, or every changed
  file is under a spike path, then the check is exempt; a title that does not parse gives TF001.
- AC23. Given a `feat:` pull request whose first `test:` commit adds tests that fail on the merge base and pass at the
  head, then the check passes.
- AC24. Given a test that passes on the merge base, then TF004; given a test that fails at the head, then TF005.
- AC25. Given no `test:` commit, a first `test:` commit that changes non-test files, or one that adds no test, then
  TF002, TF003 or TF010.
- AC26. Given a `refactor:` pull request that changes any test file, then TF006; given a `test:` pull request that
  changes any non-test file, then TF007.
- AC27. Given any run, then the base is checked out in a temporary worktree that is removed afterwards, the repository
  and its refs are unchanged, and the package under test is imported from the base worktree (TF011 otherwise).
- AC28. Given a task whose `tests_first` names a test file that the first `test:` commit does not touch, then TF008.

forbidden (§4.8)
- AC29. FB001 flags an escape-hatch name; AC30. FB002 flags dynamic code execution; AC31. FB003 flags a host SDK import
  outside `host/`; AC32. FB004 flags I/O, clock, random and environment use in block and rule modules; AC33. FB005
  flags numeric literals in check, calc, block and rule modules except the forms listed in §4.8; AC34. FB006 flags a
  rationale field that does not forbid digits; AC35. FB007 flags `print`; AC36. FB008 flags pytest collection hooks and
  options that deselect tests. In each case the rule flags the construct, does not flag its permitted neighbour, and
  names the rule id, file and line.
- AC37. Given spike code, tests (except for FB008) and strings in comments or docstrings, then no rule flags them; a
  file that does not parse is a failure (FB000); no inline waiver exists.

ratchet (§4.9)
- AC38. Given suppression markers, when counted per package and bucket, then a count above the recorded one gives RT001
  and a count below it gives a notice.
- AC39. Given a skip or expected-failure marker without an issue reference, without a valid expiry date, or with a date
  before today, then RT002, RT003 or RT004.
- AC40. Given a `.gate/ratchet.json` that raises a count against the base commit, then AW05 in bootstrap mode; a package
  absent from the file counts as zero; `ratchet --update` can lower counts and never raise them.
- AC41. Given a `noqa` or `type: ignore` comment without an issue reference, then RT006.

imports (§4.10)
- AC42. Given a package that imports a package of the same or a higher layer (except between layer 3 packages), then
  IM001.
- AC43. Given an import of a module that is not in the other package's `public_modules`, then IM002.
- AC44. Given an import of a workspace package that is not a declared dependency (IM003), of a name that starts with
  `sasaah` (IM004), or of a third-party distribution that is not declared (IM006), then the check fails.
- AC45. Given a cycle between packages, then IM005.

secrets (§4.11)
- AC46. Given an added line that matches a rule, when scanning a commit range or the tree, then SC001 names rule, path,
  line and a fingerprint and never prints the matched text; an allowlist entry with a matching fingerprint suppresses it.

check (§4.12)
- AC47. Given a package, when `check` runs, then the steps run in the order of §4.12, every step is reported, a failing
  step does not stop the others unless `--fail-fast`, and the exit code is the worst result.
- AC48. Given thresholds in `[tool.eng-gate]` below the floor of the package's profile, then CF002.
- AC49. Given a tool table or file that can weaken a tool (§4.12 table), then CF003, CF004 or CF005.
- AC50. Given a coverage run, then line and branch coverage are computed separately and compared with the package's
  thresholds (CV001, CV002), and any deselected test fails the run (CV003).
- AC51. Given a dependency whose license is not allowed, unknown, or excepted without an ADR, then LC001, LC002 or LC003.
- AC52. Given a generated document whose regeneration differs from the committed bytes, then GF001.
- AC53. Given a changed R1 or R2 module, then mutation tests run on it and a score below `mutation_min` gives MU001.
- AC53a. Given changed R1 or R2 files for which mutmut produces no mutant, then MU003 and the step passes; given mutants that no test covers, then MU002 (amendment B-336).
- AC54. Given a workspace member without `[tool.eng-gate]` (CF006) or a stale `uv.lock` (ST001 on step `lock`), then the
  check fails.

agents (§4.13)
- AC55. Given a template and `.gate/agents.yml`, when rendering, then the output is byte-exact, UTF-8, LF, and equal to the
  committed file when nothing changed.
- AC56. Given a placeholder without a value (AG001), a value without a placeholder (AG002) or a stale `template-version`
  (AG003), then rendering fails and writes nothing.
- AC57. Given every `AGENTS.md` in the workspace, when `agents drift` runs, then a differing file gives AG004, one that no
  `agents.yml` manages gives AG005, and a managed one without the one-line `CLAUDE.md` pointer gives AG006.
- AC58. Given a template, `agents keys` prints a YAML skeleton with every placeholder as a correctly quoted key.

CI (§4.14)
- AC59. Given `.github/workflows/ci.yml`, then it defines the nine jobs of process/11 §5 as thin steps that call
  composite actions (from the base checkout in pull-request jobs, §4.14), triggers on pull requests into `build/v1` and `main` and on pushes to `build/v1`, and the
  `windows` job runs only on pushes.
- AC60. Given workflows and actions, then an action not pinned by a 40-character commit SHA (WF001), a missing top-level
  `permissions` (WF002), an attacker-controlled expression inside a `run:` script (WF003) or the trigger
  `pull_request_target` (WF004) fails; a `ci.yml` whose shape departs from §4.14 (WF005, AC68) fails.
- AC61. Given `ci-review`, then the pinned prompts match their recorded hashes; in bootstrap mode the job reports AW04
  and exits 0; in normal mode without configured providers it fails closed.
- AC62. Given the `security` and `build` jobs, then `security` runs the secret scan and `uv audit`, and `build` runs
  `uv build` for every workspace member.
- AC63. Given packages that declare `windows_tests`, when `windows-tests` runs, then exactly those paths run; none declared
  gives a notice and exit 0.
- AC64. Given the workspace after the last task, when CI runs on a pull request, then every job is green (verified by the
  CI run itself, not by a unit test).

base-commit gate (§4.16)
- AC65. Given a pull-request event and a gate root that is a checkout of the event's base commit holding the running
  package, when a judging command runs, then the policy files (`.gate/gate.yml`, `.gate/forbidden.yml`, the risk maps
  of the base) and the gate code come from the gate root and the tree under check is the head; a head tree that
  removes a rule from `.gate/forbidden.yml`, lowers a limit in `.gate/gate.yml` or weakens a check under
  `tools/eng-dev-gate/` while also introducing the violation changes no finding.
- AC66. Given `--gate-root` whose `HEAD` is not the event's base commit, or a running package that is not inside the
  gate root, then CF009 and exit 1; given a push event or no event, then `--gate-root` is not needed and no
  provenance rule applies.
- AC67. Given a pull-request event and no `--gate-root` (a head run), when the base commit has no action for the job
  that runs the command, then AW09 in bootstrap mode and CF009 with bootstrap off; when the base commit has it,
  then CF009 in both modes.
- AC68. Given `.github/workflows/ci.yml`, then WF005 unless it has exactly the jobs of §4.14, each pull-request job
  checks out the head and then the base commit into `.gate-base`, and every `uses:` of a local action in a pull-request
  job is the base variant (guarded by the presence of that action in the base) or the head variant (guarded by its
  absence) and nothing else.

## 4. Design

### 4.1 Package and ports

`eng-dev-gate` is a Python 3.14 package (`requires-python = ">=3.14,<3.15"`) at `tools/eng-dev-gate`, import name
`eng_dev_gate`, script `eng-gate`. It is layer "tool" (§4.10): it imports no other workspace package, and no package
imports it. It runs on Linux and Windows (the owner's machine); paths are handled as POSIX paths relative to the
workspace root.

```
src/eng_dev_gate/
  cli.py  results.py  report.py          dispatch, Finding/StepResult, text/JSON/Actions output
  config/                                gate.yml, [tool.eng-gate], floors
  gate_root.py                           gate root and provenance of the judging gate (§4.16)
  gitio.py  workspace.py  globs.py       Git port, member discovery, glob matching
  event.py  frontmatter.py               GitHub event file, spec/plan models
  checks/                                gate_check, risk_floor, test_first, ratchet, forbidden/, imports,
                                         secrets, licenses, generated, mutation, workflows, review
  agents.py  toolrun.py  pytest_plugin.py  judged_run.py
  prompts/                               pinned reviewer prompts and their hash manifest
actions/<name>/action.yml                composite actions used by the root workflow
```

Pure logic sits in the checks; side effects sit behind ports so tests can fake them: `Git` (subprocess `git` with
`-c core.quotepath=off` and NUL-separated output), `ToolRunner` (ruff, mypy, coverage, pytest, uv through
`sys.executable -m <tool>` or `uv`), `Clock` (today's date), `Env`, `ApprovalSource` (GitHub reviews, used only with
bootstrap off). The gate never edits files except `agents render` and `ratchet --update`, never uses a shell, and never
prints a secret or a token.

### 4.2 Results, exit codes, output

A check returns findings: `code`, `severity` (`error`, `notice`, `awaiting`), `path`, `line`, `message`. The status of a
check is `fail` if any error exists, otherwise `awaiting-owner` if any awaiting finding exists, otherwise `pass`
(`skipped` with a reason when it does not apply). Exit codes: 0 pass or awaiting owner; 1 a rule failed; 2 usage or
configuration error (bad option, malformed `.gate/` file, malformed `[tool.eng-gate]`, unreadable event file); 3
environment or tool error (git or a pinned tool missing, crashed or timed out, `GITHUB_TOKEN` rejected). Output is plain
text by default and JSON with `--format json`; in GitHub Actions each finding is also a workflow command
(`::error file=,line=,title=<code>::`, `::notice title=awaiting owner::`, with `%`, CR and LF escaped as the runner
requires) and the summary is appended to the file named by `GITHUB_STEP_SUMMARY`. Every run prints its mode first.

### 4.3 Configuration

Everything is in `pyproject.toml` tables and the `.gate/` files (§5). The root `.gate/` files are protected paths
(process/06 §4). A package can tighten but never relax: thresholds below the floor of process/05 §2 are rejected (AC48),
risk maps only add, and tool tables are checked against the weakening rules of §4.12. In pull-request context the
commands read `.gate/gate.yml` and the other policy files from the gate root, a checkout of the base commit (§4.16), and
the plan from the gate branch, so a pull request cannot relax the gate or its own plan for itself; `risk-floor` also
reads the risk maps from the head tree and unions them with those of the base.

### 4.4 Bootstrap mode (ADR-0028 §4)

`bootstrap.enabled: true` in `.gate/gate.yml` (initial value, set by the lead) means:

- The gate branch is `bootstrap.gate_branch` (`build/v1`) in place of `main` for every gate: plans and specs are loaded
  from it and pull requests must target it.
- A spec or plan with `status: draft` counts as reviewed once it is on the gate branch. The lead merges spec and plan
  pull requests only after a review by a subagent that did not write them (decision D-6); the gate cannot see that
  review and does not claim to. A pull request that sets `status: approved` fails (GC014): approval is the owner's act (§11 Q7).
- These checks report `awaiting owner` (notice plus summary, exit 0) instead of failing, and nothing else is relaxed:

| Id | Condition that needs the owner or another identity | Where |
|---|---|---|
| AW01 | The owner approval of a spec or plan that [process/01](../../../../design/process/01-lifecycle.md) §5 requires (R1, R2, large plans) | gate-check |
| AW02 | `CODEOWNERS` review of a changed protected path (process/06 §4) | gate-check |
| AW03 | G3 approvals by two reviewer bots of different families or by the owner (process/01 §5) | gate-check |
| AW04 | CI reviewer verdicts, including the second family (no reviewer identity or provider keys yet) | ci-review |
| AW05 | A rise in `.gate/ratchet.json` against the base commit | ratchet |
| AW06 | The merge of the gate branch into `main` (the owner merges after local tests) | gate-check |
| AW07 | The `type/emergency` label set by the owner (honored only with bootstrap off) | gate-check |
| AW08 | Identity checks: author is the agent identity and not the owner; approvals come from a non-author | gate-check |
| AW09 | The command ran from the head tree because the base commit has no action for its job (the first pull requests of a job, §4.16); the pull request is judged by the code it changes | every judging command |

Switching it off: the owner changes `bootstrap.enabled` to `false` in `.gate/gate.yml` and fills `identities`
(`owner_login`, `agent_logins`, `reviewer_app`, all non-empty); otherwise CF008. The file is under `.gate/**`, a
protected path. No environment variable, option or package setting can change the mode (AC4).

### 4.5 gate-check

Inputs: the GitHub event file (`--event`, default `GITHUB_EVENT_PATH`) with `pull_request.{number,title,body,draft,
base.ref,base.sha,head.ref,head.sha,user.login,labels,head.repo}`; the repository with full history. For a `push` event
it exits 0 as `skipped`. A pull request from another repository fails (the repository is private; fork support is a
non-goal). The title and body are data and are parsed, never executed or interpolated into a shell.

Body parsing (lines inside fenced code blocks and HTML comments are ignored; keys are case-sensitive and start the line):

| Line | Form | Notes |
|---|---|---|
| `Plan-Task:` | `<path>#T<n>`, with `<path>` relative to the workspace root, under `<package>/docs/plans/`; or `none (<reason>)` | Exactly one (GC001, GC002) |
| `Work-Item:` | `B-<digits>` in bootstrap mode | In bootstrap mode `Closes #<digits>` is also accepted; with bootstrap off only `Closes #<digits>` (GC003) |
| `Risk:` | one or more of `r0` to `r3` | Read by `risk-floor` |

Checks, in order (all run; findings accumulate):

1. **Base branch.** The base is the gate branch (GC013). Exception, in bootstrap mode only: the pull request whose head
   is the gate branch and whose base is `main` gives AW06 and the remaining checks are skipped (the owner merges it).
2. **Lane.** A head `lane/<digits>-<slug>` (`<slug>` is lowercase letters, digits and hyphens) is the project lane
   (process/01 §9). The pull request must be a draft, which GitHub cannot merge, so a lane branch never reaches the
   gate branch before the release lane; then the remaining checks of gate-check are skipped with a notice. A
   non-draft lane pull request or a malformed name is GC012. `risk-floor` runs on lane branches; `test-first` does not.
3. **Plan-Task reason `none`.** Allowed reasons and their conditions:

| Reason | Condition on the changed files |
|---|---|
| `spec and plan` | Every file matches `spec_globs` or `plan_globs` |
| `trivial` | At most 10 changed counted lines (process/01 §2) and no path under `src/`, `tests/`, `.gate/`, `.github/`, no `pyproject.toml`, no schema or configuration file |
| `hub documents` | Every file is under `design/` |
| `spike` | Every file matches `spike_globs` |
| `release` | Every file is `pyproject.toml`, `CHANGELOG.md` or `uv.lock` of one package (process/07 §3) |

   Any other reason, or a diff that does not fit it, is GC011.
4. **Plan and spec.** Load `<path>` from the gate branch tip (`git show <gate-ref>:<path>`; `--gate-ref`, default
   `origin/<gate_branch>`), parse its front matter (§5) and load the spec named by `spec:` the same way. Missing
   file: GC004. Invalid front matter: GC005. `status` must be `approved`; in bootstrap mode `draft` is accepted
   (AC8, GC006). In bootstrap mode an AW01 notice lists each loaded document that is still a draft and whose risk or
   size requires the owner (process/01 §5).
5. **Task.** The task id must exist (GC007).
6. **Scope.** Changed files come from `git diff --name-status -z -M <merge-base> <head sha>`; a rename or copy
   contributes both paths. Each path must match a glob of the task (`PurePosixPath.full_match` semantics: `*` does not
   cross `/`, `**` matches any number of directories, matching is case-sensitive), or be the `<dir>/CHANGELOG.md` or
   `<dir>/docs/local-testing.md` of a directory `<dir>` that is a workspace member or holds the plan
   (`<dir>/docs/plans/`) when another changed file under `<dir>` matches a task glob: process/04 asks every task for a
   changelog entry and process/05 for its local-testing items (amendment B-096). `.gate/ratchet.json` is also in scope
   when every count it changes belongs to a package that has another changed file matching a task glob: a task that
   adds a justified suppression records it there, and a rise is AW05 for the owner (§4.9; amendment B-088). Any other
   change to that file is GC008: the `version` field, a package key added, removed or renamed without a count change of
   an in-scope package, and counts of other packages, lowerings by `ratchet --update` included (they go in a pull
   request of their own); the workspace root (`.`) never anchors a change (amendment B-089). Else GC008.
7. **Budget.** From `git diff --numstat -z -M <merge-base> <head sha>`, sum additions plus deletions of every changed
   file except: test files (`test_globs`), generated files (`generated_globs`, including `uv.lock` and rendered
   `AGENTS.md`) and spike files (`spike_globs`). Binary files count zero and give a notice. Above `max_changed_lines`
   is GC009 ("BLOCKED, propose a plan change", rule A22). `max_sessions` cannot be observed and is left to review.
8. **Spec and plan pull requests.** If any changed file matches `spec_globs` or `plan_globs`, every changed file must
   (GC010); each changed spec or plan must have valid front matter (GC005); a changed plan must cover every
   acceptance criterion (`AC<n>.` lines) of its spec in some task's `covers` (GC016), and every task must stay within
   the size cap `limits.max_task_lines` (initially 400, "about 400" in process/04 §4) (GC005). A pull request that
   adds or changes `status: approved` fails in bootstrap mode (GC014); with bootstrap off, the approvals of
   process/01 §5 (strictest over the risk set) must exist on the pull request that merged the approving commit,
   from the logins in `identities`, through `ApprovalSource` (GC015).
9. **Protected paths.** Changed files matched by `CODEOWNERS` (`.github/CODEOWNERS` or `CODEOWNERS`; patterns
   follow the gitignore subset `*`, `**`, leading `/`, trailing `/`) give AW02 in bootstrap mode; otherwise an approving
   review by `identities.owner_login` on the head commit is required (GC015). Changes to `tools/eng-dev-gate/**`,
   `.github/**` and `.gate/**` are among them.
10. **Identity and G3.** AW08 and AW03 in bootstrap mode. Otherwise the author login must be in `identities.agent_logins`
    and not the owner, approvals must come from other logins, and the G3 approvals of process/01 §5 for the risk set
    must exist (GC015).

### 4.6 risk-floor

Inputs: the same event (or `--base`, `--head`, `--body-file`), `.gate/risk-map.yml` (a list of
`{paths: [globs], risk: r1 | r2 | r3 | [list]}`) and optional `<package>/.gate/risk-map.yml` (globs relative to the
package directory), read at the base and head commits.

Floor: the union of the `risk` of every entry with at least one glob matching at least one changed path (the union over
both commits and both levels, so an entry can be added but not dropped by the pull request itself). Recorded risk: the
`risk` of the plan named by `Plan-Task` (loaded from the gate branch; a set: `r1`, `r2` and `r3` can apply together;
`r0` stands alone); for spec and plan pull requests, the `risk` of the changed documents; for a lane branch, and for a
`Plan-Task: none (<reason>)` pull request whose reason is not `spec and plan`, the `Risk:` line of the body (amendment B-336). The floor must be a subset of the recorded set (RF001 lists both and the paths that raised the floor).
When a plan is the source, the body `Risk:` line, if present, must be the same set (RF002). A missing recorded risk is
RF004. The default map of process/01 §6 is the root file's content; the gate has no built-in map, so a missing file is
exit 2.

### 4.7 test-first

Inputs: `--base`, `--head`, `--title` or the event. The type is read from the title, which squash merge also uses as
the commit subject: `^(feat|fix|refactor|test|docs|build|ci|chore|perf|release)(\(<scope>\))?!?: <text>$` (process/04 §3
list plus `release`, process/07 §3); anything else is TF001.

1. Exempt, exit 0 with a notice: type `docs`, `chore`, `ci` or `release`; or every changed file matches `spike_globs`.
2. `refactor`: no changed file may be a test file (`test_globs`); then exit 0 (the tests run in `gate`). Else TF006.
3. `test`: no changed file may be a non-test file (TF007); the tests run in `gate`; exit 0.
4. Other types (`feat`, `fix`, `perf`, `build`):
   1. List `git rev-list --reverse --first-parent <merge-base>..<head>` without merge commits. The first commit whose
      subject starts with `test:` or `test(` is the test commit (TF002 if none). Its changed files must all be test
      files (TF003).
   2. The new or changed tests are the `test*` functions (top-level or in `Test*` classes) of the test files of that
      commit whose AST differs from, or is absent in, the merge base (TF010 if there is none). Every `tests_first` file of
      the task, when a plan task is named, must be among the commit's test files (TF008).
   3. Create a temporary worktree of the merge base (`git worktree add --detach`), copy the test commit's versions of its
      test files into it (`git checkout <test commit> -- <paths>`), and run `sys.executable -m pytest` on those files,
      once per owning package, with the package directory as the working directory, `PYTHONPATH` set to the `src`
      directories of the worktree's members, `-p no:cacheprovider`, `--junitxml`, and the time limit
      `limits.test_run_seconds`. Before running, an import probe checks that each existing package under test resolves
      inside the worktree (TF011, exit 3 otherwise). Every new or changed test must be reported failed or errored; a
      collection error counts as failing every test of that module. A test that passes or is skipped is TF004.
      Pytest exit codes 4 and 5, a timeout, or a missing result are TF009 (exit 3).
   4. Run the same files in the checked-out head; every one of them must pass, none skipped or xfailed (TF005).
   5. Remove the worktree in all cases (`finally`); the repository's refs, index and working tree are untouched.

Process/05 §9 names only documentation and chore as exempt; `ci`, `release`, spike-only, and the handling of `test:` are
additions listed in §11.

### 4.8 forbidden

`forbidden` parses each `.py` file with `ast` and reports `FBnnn` findings. Scope: the `src/` tree of every workspace
package, except `FB008`, which applies to `tests/` and every `conftest.py`. Never in scope: `spikes/`, strings and
comments (unless a rule says so). A file that does not parse is FB000. There is no inline waiver; the only
configuration is `.gate/forbidden.yml` (protected) and the module globs in `[tool.eng-gate]` of the package, which
select where a rule applies and cannot remove a rule.

| Id | Rule | Exact scope and test |
|---|---|---|
| FB001 | Escape-hatch name | A string constant, identifier or attribute equal to an entry of `escape_hatch.names` (initially `csi_run_script`, `csi_db_tables_apply`), or a function or class definition whose name fully matches a regex of `escape_hatch.patterns` (initially names that run, execute or evaluate scripts, code or expressions, apply or write database tables, or forward arbitrary API calls). Adapter allowlists are positive lists, so excluded names never appear in `src/`; tests may name them |
| FB002 | Dynamic code execution | Calls of `eval`, `exec`, `compile`, `__import__`, `os.system`, `os.popen`, `runpy.run_module`, `runpy.run_path`, and any call with `shell=True`. Plain `subprocess` calls with an argument list are allowed |
| FB003 | Host SDK import outside `host/` | An import of a module in `host_sdk.modules`, or a call `clr.AddReference`, in a file with no `host` directory component below the package's `src`. Initial modules: `win32com`, `pythoncom`, `pywintypes`, `comtypes`, `clr`, `System`, `Autodesk`. Vendor names for ETABS, SAFE, SAP2000 and IDEA StatiCa are a recorded gap (§11 Q10) |
| FB004 | I/O in block and rule modules | In files matching the package's `block_modules` or `rule_modules`: imports of the modules in `io_modules` (initially `os`, `sys`, `io`, `pathlib`, `shutil`, `tempfile`, `socket`, `ssl`, `http`, `urllib`, `subprocess`, `sqlite3`, `time`, `datetime`, `random`, `secrets`, `uuid`, `requests`, `httpx`) and calls of `open`, `input`. This implements rules 1 and 4 of [11 §3](../../../../design/docs/architecture/11-harness-engine.md) |
| FB005 | Numeric literal | In files matching `check_modules`, `calc_modules`, `block_modules` or `rule_modules`: every `int`, `float` or `complex` constant (a leading minus belongs to the literal; `bool` is not numeric) except the forms below |
| FB006 | Digits in a rationale | A class attribute named `rationale` or ending in `_rationale` must be annotated with a type named in `rationale.types` (initially `Rationale`), or with `Annotated[str, ...]` whose `pattern` constraint is probed with `a<digit>b` for the digits 0 to 9, the Arabic-Indic digits U+0660 to U+0669 and the extended digits U+06F0 to U+06F9 (none may match) and with `ab` (must match); a plain `str` is FB006. Source: [12 §1](../../../../design/docs/architecture/12-decision-layer.md) (rationale "may not contain digits") |
| FB007 | `print` | A call of the builtin `print` (also through an alias). Output goes through the logger or an injected stream |
| FB008 | Collection that deselects tests | Defining `pytest_collection_modifyitems`, `pytest_ignore_collect` or `pytest_deselected`; calling `config.hook.pytest_deselected`; assigning `collect_ignore` or `collect_ignore_glob`. Source: process/05 §3 |

FB005 allowed forms (everything else is flagged, including `0`, `1`, `1.0`, signature defaults, `range(3)` and
`ratio <= 1.0`):

- **A1.** The first positional argument (or `value=`) of a call to a callable named in `cited.callables` (initially
  `Cited`), written as a plain literal, when the call also has a non-empty string literal as second positional argument
  or `source=`. A call without a source is FB005. Source: [10 §3](../../../../design/docs/architecture/10-structural-codes.md)
  (`Cited(0.75, "ACI 318-14 Table 21.2.1(b)")`) and [11 §3](../../../../design/docs/architecture/11-harness-engine.md) rule 3. The gate checks that a source string is present, not that it is true; reviewers do that.
- **A2.** An integer literal used directly as a subscript index or slice bound (`x[0]`, `x[-1]`, `x[1:]`).
- **A3.** An integer literal compared directly with a `len(...)` call.
- Annotations (`Literal[...]`) and docstrings are not constants of the code and are not scanned.

A2 and A3 are structure, not quantities; they cannot carry a threshold. Both are listed for the owner's confirmation
(§11 Q5). Input bounds written as numeric literals in check modules are flagged like any other literal; the contract
decides the pattern (a cited callable added to `cited.callables`), not this gate.

### 4.9 ratchet

Scope: tracked `.py` files of every workspace package (`src/`, `tests/`, `conftest.py`), not `spikes/`. Buckets and what
counts, using `tokenize` for comments and `ast` for markers:

| Bucket | Counted occurrences |
|---|---|
| `noqa` | Each comment containing `noqa` as a directive, including `ruff: noqa` and `flake8: noqa` |
| `type_ignore` | Each comment `type: ignore` and each `mypy: ignore-errors` |
| `pragma_no_cover` | Each comment `pragma: no cover` and `pragma: no branch` (the second is an addition, §11 Q3) |
| `skip` | `pytest.mark.skip`, `pytest.mark.skipif`, `pytest.skip(`, `pytest.importorskip(`, `unittest.skip*`, `skipTest(`, also inside `pytest.param(marks=...)` and `pytestmark` |
| `xfail` | `pytest.mark.xfail`, `pytest.xfail(`, also inside `pytest.param(marks=...)` and `pytestmark` |

`.gate/ratchet.json` is `{"version": 1, "counts": {"<package dir>": {"noqa": n, ...}}}`; a package or bucket that is
absent counts as zero, so a new package starts at zero. A count above the recorded one is RT001. A count below it is a
notice ("run `ratchet --update`"), not a failure, so parallel pull requests do not conflict. In pull-request context,
a recorded count above the base commit's is AW05 in bootstrap mode (and requires the owner's approval of the file with
bootstrap off); `ratchet --update` rewrites the file with lower counts only and refuses to raise one.

Each `skip` and `xfail` marker needs a `reason=` string that contains an issue reference (`#<digits>` or `B-<digits>`;
RT002) and `expires <yyyy-mm-dd>` (a real date; RT003); RT004 when the date is before today (the `Clock` port; the
date itself is still valid). Each `noqa` and `type: ignore` comment must contain an issue reference (RT006), as
process/04 §5 requires a reason and an issue link. Whether open-ness of the issue is checked is a non-goal (§7).

### 4.10 imports

Layers: `[tool.eng-gate] layer` is `1` (contract), `2` (server), `3` (engineering library), `4` (harness), `"tool"` or
`"product"`, consistent with the package's `profile` (§5). For each `.py` file under `src/` and `tests/` of every
member the gate collects absolute imports (including those under `TYPE_CHECKING`, and `import_module` or `__import__`
with a literal name). A top-level name claimed by a member's `import_names` is a workspace import. Findings:

| Id | Rule | Source |
|---|---|---|
| IM001 | The imported package must have a strictly lower layer than the importer. Exception: layer 3 packages may import other layer 3 packages that they declare (the overlay mechanism, [10 §5](../../../../design/docs/architecture/10-structural-codes.md)); layer 1 imports no workspace package; a `tool` package imports none and is imported by none | [03 §3](../../../../design/docs/architecture/03-repositories.md) item 2, [02 §1](../../../../design/docs/architecture/02-system-overview.md) |
| IM002 | Only modules listed in the other package's `public_modules` (or a submodule resolved by the filesystem that is listed) may be imported; `from pkg import name` is a module import when `pkg.name` is a submodule. A leading-underscore module is never public | 03 §3 item 2 |
| IM003 | An imported workspace package must be a declared dependency of the importer (`[project].dependencies` or a dependency group), so each package builds and tests on its own | 03 §3 item 1 |
| IM004 | No import whose top-level name starts with `sasaah` (case-insensitive) | 03 §3 item 2 |
| IM005 | The package dependency graph has no cycle | derived |
| IM006 | A non-standard-library, non-workspace import must belong to a distribution declared by the importer (names resolved with `importlib.metadata.packages_distributions`) | derived; this is also how an undeclared Sasaah module is caught |

Layer 2 servers never depend on each other, on layer 3 or on layer 4 (02 §1) follows from IM001 because the layers must
be strictly lower. The import rules for `product` packages are not defined by 03 §3; only IM002 to IM006 apply to them
(§11 Q9). An exception in the rules is a code change, not a configuration change.

### 4.11 secrets

`secrets --range <base>..<head>` scans the added lines of every commit in the range (history leaks are caught even when a
later commit removes the line); `secrets --tree` scans every tracked text file at the checkout. Files larger than
`limits.max_file_bytes` and binary files are skipped with a notice (SC002). Rules (id, pattern):
GitHub classic token `ghp_` plus 36 alphanumerics; GitHub fine-grained token prefix `github_pat_`; AWS access key id
`AKIA` plus 16 uppercase alphanumerics; Google API key `AIza` plus 35 URL-safe characters; Slack token prefix
`xox[abprs]-`; Anthropic key prefix `sk-ant-`; PEM private key header (`-----BEGIN` ... `PRIVATE KEY-----`); a
quoted literal of at least 8 characters assigned to a name containing `password`, `secret`, `token` or `api_key`; personal
paths (`C:\Users\<name>`, `/home/<name>/`, `/Users/<name>/`, process README rule 6 and A11). A finding prints the rule id,
path, line and a fingerprint (the first 12 hexadecimal digits of the SHA-256 of the matched text) and never the text.
`secrets.allow` in `.gate/gate.yml` lists `{rule, path, fingerprint}` entries (protected path). The gate's own tests
build their sample secrets at run time from parts, so the repository scan does not flag its own fixtures. Names of
clients or projects cannot be detected by pattern and stay with review.

### 4.12 check, the local gate

`uv run eng-gate check` runs in a package directory for that package and at the workspace root for every member
(`--package <name>`, `--all`). Steps run in this order and each is reported; `--only` and `--skip` exist for the
workstation, the CI job never uses them:

| # | Step | Level | Content |
|---|---|---|---|
| 1 | `lock` | root | `uv lock --check` (ST001 when stale) |
| 2 | `config` | package | `[tool.eng-gate]` valid and at or above the floor of its profile (CF001, CF002); weakening rules below (CF003 to CF005); every member declares the table (CF006) |
| 3 | `format` | package | `ruff format --check` |
| 4 | `lint` | package | `ruff check` with the baseline rule set below |
| 5 | `types` | package | `mypy --strict` on `src/` and `tests/` |
| 6 | `forbidden` | package | §4.8 |
| 7 | `imports` | workspace | §4.10 |
| 8 | `ratchet` | workspace | §4.9 |
| 9 | `secrets` | workspace | §4.11 on `<merge base with origin/<gate_branch>>..HEAD`; the whole tree when that ref is absent (a local or shallow checkout). A range is chosen on the `secrets` command itself (`--range`); `check` has no `--base` option (amendment B-099) |
| 10 | `tests` | package | `python -m coverage run --branch` with `-m pytest` on `tests/` and the gate's pytest plugin; coverage JSON; line and branch compared separately with the package's thresholds (CV001, CV002) |
| 11 | `docs-fresh` | package | Generated documents (`[tool.eng-gate].generated`, GF001, GF002) and `agents drift` for the package |
| 12 | `licenses` | package | Allowed licenses of the dependency closure (LC001 to LC003) |
| 13 | `mutation` | package | Mutation tests on changed R1 and R2 modules (MU001, MU002, MU003) |
| 14 | `workflows` | root | §4.14 rules WF001 to WF005 |

A failing tool step reports ST001 with the step, tool, exit code and the first lines of its output. Tools run with an
explicit configuration (`ruff --config pyproject.toml`, `mypy --config-file pyproject.toml`, `pytest -c pyproject.toml`,
`coverage --rcfile` pointing at a configuration the gate generates), so stray files cannot change them. When the
policy comes from a gate root other than the judged tree (§4.16), relative patterns in it (`per-file-ignores`,
`extend-exclude`, `src`, `mypy_path`, `exclude`) apply to the judged tree: `ruff` receives the gate root's `[tool.ruff]`
table as `--isolated --config key=value` options and runs in the judged tree (a configuration file would anchor the
patterns at the gate root), and `mypy` receives the gate root's `pyproject.toml` by absolute path and runs in the
judged tree. Tool caches never live in the judged tree, where a pull request could forge them: `ruff` runs with
`--no-cache` and `mypy` with `--cache-dir` set to a fresh temporary directory outside every checkout, removed afterwards.
A member that has its own `[tool.ruff]` or `[tool.mypy]` table is configured by that table, as before.

The `tests` step executes the code under check, so with a gate root other than the judged tree (§4.16) it runs the
tests of each member in an environment built from the judged tree and its own `uv.lock`, not in the interpreter of the
gate (which holds the gate and its dependencies only): `uv run --project <judged tree> --locked --all-packages --group
dev python ...`, in the member directory. Policy and plugin still come from the base: the coverage rc file is generated
by the gate in a temporary directory outside both checkouts and passed with `--rcfile`, the thresholds are applied by
the gate after the run, and `judged_run.py`, a file of the base commit's package, runs `coverage` in that environment
after loading the base `pytest_plugin.py` as a module of its own name (`-p eng_gate_base_pytest_plugin`), so an
`eng_dev_gate` installed in the judged environment cannot stand in for it. `coverage json` runs in the same environment
from a temporary directory. Without `uv` on the path the step is an environment fault (exit 3). Before the run, the
step checks `uv lock --check` for the judged tree: a stale or missing `uv.lock` is ST001 of the step (the environment
cannot be built), not an environment fault, so the other findings of the run are kept; `uv run` is called with `--quiet`
so that its own warnings (for example an inherited `VIRTUAL_ENV`) do not fill the output. `pytest_plugin.py` imports
nothing from `eng_dev_gate` (a unit test checks it): inside the judged environment such an import would resolve to the
pull request's copy. Accepted residual risk: `coverage` and `pytest` themselves come from the judged lock file, so a
pull request chooses the tools that produce its own report; in-process code of its `conftest.py` could already do the
same, and the gate-generated rc file, the base plugin and the base thresholds are what bound it. A head run (no gate
root, push runs, local runs) uses the interpreter of the gate as before.

Floors, from process/05 §2 (a package may set a higher value, never a lower one):

| Profile | Layer | Line | Branch | Mutation |
|---|---|---|---|---|
| `contract` | 1 | 95 | 90 | at least 80 |
| `server` | 2 | 85 | 75 | `mutation_min` required when R1 or R2 globs exist |
| `codes` | 3 | 95 | 90 | at least 80 |
| `harness` | 4 | 85 | 75 | `mutation_min` required when R1 or R2 globs exist |
| `tool` | "tool" | 95 | 90 | `mutation_min` required when R1 or R2 globs exist |

The `tool` row and the rule for `mutation_min` of the other profiles are not in process/05 §2 (§11 Q2); until the owner
decides, the gate uses the stricter pair for itself and 80 for any declared `mutation_min`. The C# row of process/05 §2
is for the C# build and is not applied here.

Lint baseline: ruff rule families E, W (pycodestyle), F (pyflakes), I (isort), B (bugbear), UP (pyupgrade), SIM, N
(naming) and S (bandit), as listed in process/11 §3; "bandit subset" is not defined there, so S is selected whole with
`S101` ignored under `tests/**` only (§11 Q6).

Weakening rules of `config` (the allowed set is closed; anything else is flagged):

| Where | Allowed | Flagged as |
|---|---|---|
| `[tool.ruff]`, `[tool.ruff.lint]` | `line-length`, `src`, `lint.select` as a superset of the baseline, `lint.per-file-ignores` only `tests/**` with `S101`, `exclude` only `spikes` | CF003 for any ignore, extend-ignore, other per-file-ignore or exclude |
| `[tool.mypy]` | `strict = true`, `plugins`, `mypy_path`, `python_version`, `files`; overrides only with `ignore_missing_imports` for modules outside the package's own namespaces | CF003 |
| `[tool.pytest.ini_options]` | `testpaths`, `pythonpath`, `markers`, `minversion`, `asyncio_mode`, `filterwarnings` without `ignore`, `addopts` made only of `-ra`, `-q`, `--strict-markers`, `--strict-config`, `--import-mode=importlib` | CF003 (so `--deselect`, `-k`, `-m`, `--ignore`, `-p no:...` are rejected) |
| `[tool.coverage.*]` | none (the gate generates the configuration) | CF003 |
| Files `pytest.ini`, `tox.ini`, `setup.cfg`, `ruff.toml`, `.ruff.toml`, `mypy.ini`, `.mypy.ini`, `.coveragerc` | none | CF004 |
| Installed distributions | none of `pytest-rerunfailures`, `flaky`, `pytest-retry` (process/05 §3) | CF005 |

The gate's pytest plugin (`-p eng_dev_gate.pytest_plugin`) loads the Hypothesis profile `ci` with `derandomize=True`
when Hypothesis is installed (process/11 §3) and fails the session if any test is deselected (CV003).

License check: the closure is the package's runtime dependencies and dependency groups, resolved through
`importlib.metadata`. Allowed (process/04 §7): MIT, BSD (2 and 3 clause), Apache-2.0, ISC, PSF,
MPL-2.0, taken from `License-Expression`, the `License` field or trove classifiers. `OR` needs one allowed alternative;
`AND` needs all. Missing metadata is LC002. An exception is an entry `{distribution, license, adr}` in `.gate/gate.yml`
whose `adr` file exists (LC003 otherwise). Workspace members are not checked.
In pull-request context (a gate root other than the judged tree, §4.16) the closure is read from the judged
environment, like the tests of the `tests` step: `judged_metadata.py`, a file of the base commit's package that imports
nothing from `eng_dev_gate`, runs as `uv run --project <judged tree> --locked --all-packages --group dev python -I
judged_metadata.py <output file>` and writes name, `License-Expression`, `License`, license classifiers and
`Requires-Dist` of every installed distribution as JSON; the gate validates it and evaluates the policy itself. A stale
`uv.lock` is ST001 of the step, a missing `uv` or unusable output an environment fault; the residual risk is that of
the `tests` step (the judged lock file chooses what is installed and what its metadata says). Head runs read the
interpreter of the gate.

Generated documents: each `[[tool.eng-gate.generated]]` entry names `path`, `module` and `args`; the gate runs
`sys.executable -m <module> <args>` in the package directory (no shell; the module must belong to a workspace
package) and compares its standard output with the committed file after normalizing line endings to LF.

Mutation: for each file changed against the merge base that matches a package `r1_modules` or `r2_modules` glob, the
backend mutates that file and runs the package tests; the score is killed (timeouts included) over total mutants and
must be at least `mutation_min`. The backend is chosen in the mutation task (§11 Q4); on a platform it does not support,
the step is reported `skipped` with the reason locally and fails in CI if skipped there. Only changed files that hold at
least one function, method or lambda body are mutated (a file of module-level constants has no mutant that a test
reaches); when none remain the step passes with the notice MU003 (amendment B-026). A run in which mutmut produces no mutant at all (for example a file
whose only functions are decorated methods or module-level lambdas) also passes with MU003; mutants that exist but
that no test covers stay MU002 (amendment B-336).

### 4.13 agents render, keys, drift

`.gate/agents.yml` exists at the workspace root, in each package and in any other folder that holds one: every tracked `.gate/agents.yml` of the repository is a unit, so a shared package folder that is not itself a workspace member is managed too (amendment B-026):

```yaml
template: ../../design/process/templates/AGENTS.template.md   # relative to the directory that holds .gate/
output: AGENTS.md                                              # relative to the same directory
values:
  package-name: eng-dev-gate
  template-version: "sha256:0123456789ab"
  "one-paragraph purpose": "..."
```

Keys of `values` are the exact texts between `{{` and `}}` of the template (placeholders are found with the
non-greedy pattern `\{\{(.*?)\}\}` in single-line-or-multiline mode, so a placeholder may span lines). Rendering is a
single pass of plain substitution of each placeholder by its value, with these rules and no others:

- The file is read as UTF-8 with CRLF normalized to LF; the output is UTF-8, LF, without byte order mark, and the end of the
  template is preserved byte for byte. Values are inserted verbatim (use a `|-` block scalar to avoid a trailing newline).
- A placeholder with no value is AG001 (all are listed); a value without a placeholder is AG002; a value that contains
  `{{` is AG007 (no recursion). Nothing is written on any error.
- A placeholder that stands alone on its line with the value `""` removes the whole line, including its newline (this is
  how optional rows such as the C# rows are dropped).
- `template-version` must equal `sha256:` plus the first 12 hexadecimal digits of the SHA-256 of the template (LF
  normalized), else AG003; so changing the template makes every package fail until it is re-rendered, as process README
  requires.
- The template path must stay inside the workspace root.

`agents render [--package P | --all]` writes the outputs. `agents keys <template>` prints a YAML `values` skeleton with
every placeholder as a correctly quoted key (so multi-line keys need not be typed by hand). `agents drift` finds every
tracked `AGENTS.md` (`git ls-files`), renders every `agents.yml` in memory, and fails with AG004 (unified diff, at most
`limits.diff_lines` lines), AG005 for a tracked `AGENTS.md` that no `agents.yml` manages (except the globs in
`agents.unmanaged_ok`, initially `design/**`, the hub's own file), and AG006 when the directory of a managed file has no
`CLAUDE.md` whose whole content is `@AGENTS.md` and a newline ([CLAUDE.template.md](../../../../design/process/templates/CLAUDE.template.md)). CRLF in the committed file is normalized before comparison; `.gitattributes` should pin `*.md` to LF (note for the workspace root).

### 4.14 CI

`.github/workflows/ci.yml` (replacing the skeleton) is a thin root workflow: triggers, permissions, checkouts and calls,
no logic. The logic lives in composite actions in `tools/eng-dev-gate/actions/<name>/action.yml` (one `setup` and one per
job; the action name is the job id), which move with the package when it is split. Every pull-request job judges the
head tree with the gate of the base commit (§4.16) and has these steps, in this order:

1. checkout of the head (`fetch-depth: 0`, `ref: ${{ github.event.pull_request.head.sha }}`);
2. checkout of the base commit (`ref: ${{ github.event.pull_request.base.sha }}`, `path: .gate-base`,
   `persist-credentials: false`);
3. the action `setup`, then 4. the job's action, each in two variants: the base variant
   `./.gate-base/tools/eng-dev-gate/actions/<name>` with `with: gate-root: .gate-base`, guarded by
   `if: hashFiles('.gate-base/tools/eng-dev-gate/actions/<name>/action.yml') != ''`, and the head variant
   `./tools/eng-dev-gate/actions/<name>` without `gate-root`, guarded by `== ''`. The head variant exists only so that
   the pull requests that introduce a job can run it; the gate marks such a run AW09.

Push jobs check out the pushed commit and use the head variants only (the commit is already on a protected branch).
`.gate-base/` is listed in the root `.gitignore`. The actions run `uv sync --all-packages --locked` for the head
environment and, when `gate-root` is set, also `uv sync --project <gate-root> --package eng-dev-gate --locked` into a
separate environment, and start every command as
`uv run --project <gate-root> --package eng-dev-gate eng-gate --root . --gate-root <gate-root> <command>`; without
`gate-root`, as `uv run eng-gate <command>`. Whether `uv run --project` behaves so is a fact to verify in the first CI run.

| Job | Event | Content |
|---|---|---|
| `gate` | PR, push | `eng-gate check --all` (the CI steps never use `--only` or `--skip`) |
| `gate-check` | PR | `eng-gate gate-check` |
| `risk-floor` | PR | `eng-gate risk-floor` |
| `test-first` | PR | `eng-gate test-first` |
| `ci-review` | PR | `eng-gate review`; AW04 in bootstrap mode; prompts pinned (§4.15) |
| `agents-drift` | PR, push | `eng-gate agents drift` |
| `security` | PR, push | `eng-gate secrets` (`--range` on pull requests, `--tree` on pushes) and `uv audit --locked` |
| `windows` | push to `build/v1` only | `eng-gate windows-tests` on a Windows runner (head variant) |
| `build` | PR, push | `uv build --package <name>` for every name printed by `eng-gate packages --names` |

Tools that execute the head's code (`pytest` and `coverage` in the `tests` step, `mypy` through `--python-executable`,
`mutation`, generated documents, `windows-tests`) run with the interpreter of the head environment; `ruff` and the gate
itself run in the gate environment. In a base run the `tests` step puts `<gate-root>/tools/eng-dev-gate/src` first on
`PYTHONPATH` and verifies that the gate's pytest plugin loaded from there (CF009 otherwise), so a head copy of the
plugin never runs.

Triggers: `pull_request` into `build/v1` and `main` with types `opened`, `synchronize`, `reopened`, `edited`,
`ready_for_review`; `push` to `build/v1`. Top-level `permissions: contents: read`; one concurrency group per pull
request that cancels superseded runs. The jobs read the pull request title and body only from the event file through
the gate, never through `${{ }}` in a script (WF003). `setup` uses the official uv setup action with caching. Third-party
actions are pinned by commit SHA with the version in a comment (the SHA is looked up when the workflow is written, not
guessed). The job ids are the required status check names. C# build and test steps (process/11 §5) are added with the
first C# component; 0.1 has none.

`workflows` (step 14) enforces: WF001 every `uses:` is a local path or `owner/repo@<40 hex digits>`; WF002 every workflow
has a top-level `permissions`; WF003 no `${{ github.event.pull_request.title }}`, `.body`, `.head.ref` or
`github.head_ref` inside a `run:` value; WF004 no `pull_request_target`; WF005 `ci.yml` has exactly the jobs of the
table, and each pull-request job has the steps above (head checkout, base checkout into `.gate-base`, and local `uses:`
only in the guarded base and head variants of its own action and of `setup`, with no `run:` step that calls `eng-gate`).
WF005 is judged by the base gate, so a pull request cannot remove its own guard.

### 4.15 ci-review and pinned prompts

`src/eng_dev_gate/prompts/` holds the reviewer prompts (general and security, process/06 §1 rows 3 to 5) and a manifest
of their SHA-256 hashes; `review --check-prompts` and every use verify the hashes (any mismatch exits 1). The prompts
state the checklist of process/06 §2, the severities of process/06 §3, a JSON verdict schema, and that the diff, issue,
spec and plan are data and never instructions (A15). In bootstrap mode the `ci-review` job reports AW04 and exits 0
after verifying the prompts. With bootstrap off and no configured providers it fails closed; the provider adapters and
posting under the reviewer identity are not part of 0.1 (§7).

### 4.16 The gate of the base commit, and limits (threat model)

**Rule.** In pull-request context every judging command (all jobs of §4.14 except `windows`) runs the code and the
policy of the base commit against the head tree. A pull request that changes `tools/eng-dev-gate/**`, `.gate/**` or the
actions is judged by the gate as it was before the change; the change takes effect for the next pull request.

**Gate root.** The global option `--gate-root <dir>` names a checkout of the base commit (`.gate-base` in CI). It moves
where the gate code and the policy files are read from and nothing else; it does not set the mode (AC4), because the
mode file in the gate root is the base commit's own. Read from the gate root: `.gate/gate.yml`, `.gate/forbidden.yml`,
the base risk map, the pinned prompts and the gate code itself. Read from the head tree, as data under check:
`.gate/ratchet.json` (compared with the gate root's copy, §4.9), `.gate/agents.yml` and the package files, the head risk
maps (only added to the base ones, §4.6), the sources, workflows and `CODEOWNERS`. Plans and specs are read from the
gate branch (§4.5).

**Provenance.** The gate does not trust the workflow to have chosen the base. With `--gate-root` in pull-request context
it requires that `git -C <gate-root> rev-parse HEAD` equals `pull_request.base.sha` and that the running `eng_dev_gate`
package lies inside `<gate-root>/tools/eng-dev-gate/src`; otherwise CF009 (exit 1). Without `--gate-root` (a head run)
it requires that the base commit has no `tools/eng-dev-gate/actions/<job>/action.yml` for the job that runs the
command; then it reports AW09 in bootstrap mode and CF009 with bootstrap off. This is the whole exception: the first
pull requests of a job, whose base cannot judge them yet. With bootstrap off a new job is therefore added in two pull
requests (its action first, the workflow step next). Push events and local runs have no base and no provenance rule.

**Limits that remain.** GitHub loads the workflow file of a pull request from the pull request itself, so the gate
cannot stop a pull request from editing `ci.yml`. The controls are WF005 (judged by the base gate: an edited `ci.yml`
that drops the base checkout or a job fails), the required status checks with the job ids as names (a deleted job never
reports, process/11 §6, once branch protection exists), and the protected paths (`tools/eng-dev-gate/**`, `.github/**`,
`.gate/**`: AW02 in bootstrap mode, the owner's review otherwise). A change to the actions or the gate that is itself
faulty is judged by the previous version and found only on the next pull request. Everything that is `awaiting owner`
is not verified, and the lead must not treat it as passed.

## 5. Inputs and outputs

Command line: `eng-gate [--root <dir>] [--gate-root <dir>] [--format text|json] <command> [options]`.

| Command | Options | Reads | Result |
|---|---|---|---|
| `check` | `--package`, `--all`, `--base`, `--only`, `--skip`, `--fail-fast` | package, `.gate/` | Per-step table; exit 0, 1, 2, 3 |
| `gate-check` | `--event`, `--gate-ref` | event, git, `.gate/` | Findings GC and AW |
| `risk-floor` | `--event` or `--base --head --body-file` | event, git, risk maps | Findings RF |
| `test-first` | `--event` or `--base --head --title` | event, git | Findings TF |
| `forbidden`, `imports`, `licenses` | `--package`, `--all` | sources | Findings FB, IM, LC |
| `ratchet` | `--update` | sources, `.gate/ratchet.json` | Findings RT, AW05 |
| `secrets` | `--range <a>..<b>` or `--tree` | git | Findings SC |
| `agents` | `render`, `keys`, `drift` | `.gate/agents.yml`, template | Files or findings AG |
| `workflows` | none | `.github/` | Findings WF |
| `mutation` | `--package`, `--base` | sources | Findings MU |
| `review` | `--check-prompts` | prompts | AW04 or findings |
| `windows-tests` | none | `[tool.eng-gate]` | Test run |
| `packages` | `--names`, `--json` | workspace | Member list |

JSON result: `{"command", "mode", "status", "steps": [{"name", "status", "findings": [{"code", "severity", "path",
"line", "message"}]}]}`.

`[tool.eng-gate]` in each member's `pyproject.toml`:

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| `profile` | `contract`, `server`, `codes`, `harness`, `tool` | — | required | no | process/05 §2 |
| `layer` | 1, 2, 3, 4, "tool", "product" | — | consistent with profile | no | [02 §1](../../../../design/docs/architecture/02-system-overview.md) |
| `import_names` | list of str | — | at least one, matches `src/` | no | 03 §3 |
| `public_modules` | list of dotted names | — | each exists | no | 03 §3 |
| `coverage_line`, `coverage_branch` | int | percent | 0 to 100, at least the floor | no | process/05 §2 |
| `r1_modules`, `r2_modules` | list of globs | relative to the package | optional | no | process/01 §3 |
| `mutation_min` | int | percent | 0 to 100, at least the floor | no | process/05 §2 |
| `check_modules`, `calc_modules`, `block_modules`, `rule_modules` | list of globs | relative to the package | optional | no | process/11 §4 |
| `windows_tests` | list of paths | relative to the package | optional | no | process/11 §5 |
| `generated` | list of `{path, module, args}` | — | optional | no | process/05 §1 |

Root `.gate/` files: `gate.yml` (new in this package; mode `bootstrap.{enabled,gate_branch}`, `main_branch`, `identities`,
`spec_globs`, `plan_globs`, `test_globs`, `generated_globs`, `spike_globs`, `agents.unmanaged_ok`, `limits.{diff_lines,
max_task_lines, test_run_seconds, max_file_bytes}`, `license_exceptions`, `secrets.allow`), `forbidden.yml`
(`escape_hatch`, `host_sdk`, `io_modules`, `cited`, `rationale`), `risk-map.yml`, `ratchet.json`, `agents.yml`.

Spec and plan front matter (YAML between `---` lines at the start of the file): spec `id`, `issue`, `status`, `size`,
`risk`; plan `id`, `issue`, `spec`, `status`, `size`, `risk`, `tasks`; each task `id` (`T<n>`), `title`, `files`
(non-empty globs), `max_changed_lines`, `max_sessions` (positive integers), `tests_first`, `covers` (ids `AC<n>`),
`depends_on`. `risk` is one class or a list of classes (a set; `r0` alone); this extends the templates (§11 Q3).
`status` is `draft` or `approved`; `size` is `trivial`, `small`, `standard` or `large`.

## 6. Errors

Diagnostic codes (the contract of this tool; the package `CHANGELOG.md` lists changes). Fields of every finding: `code`,
`severity`, `path`, `line`, `message`.

| Prefix | Meaning | Codes |
|---|---|---|
| GC | gate-check | 001 no Plan-Task · 002 malformed or duplicate · 003 work item · 004 plan or spec not on the gate branch · 005 front matter invalid · 006 status not acceptable · 007 task unknown · 008 file outside task · 009 budget · 010 spec or plan pull request mixed · 011 `none` reason · 012 lane · 013 base branch · 014 `approved` set in bootstrap · 015 approval missing · 016 criterion uncovered |
| AW | awaiting owner (notice) | 01 to 09, §4.4 |
| RF | risk-floor | 001 below floor · 002 body mismatch · 003 map invalid · 004 no recorded risk |
| TF | test-first | 001 title · 002 no test commit · 003 test commit not tests only · 004 passes at base · 005 fails at head · 006 refactor changed tests · 007 test pull request changed code · 008 `tests_first` file missing · 009 pytest could not run · 010 no new test · 011 import probe |
| FB | forbidden | 000 parse error · 001 to 008, §4.8 |
| RT | ratchet | 001 count rose · 002 issue missing · 003 expiry invalid · 004 expired · 005 file invalid · 006 suppression without issue |
| IM | imports | 001 to 006, §4.10 |
| SC | secrets | 001 match · 002 file skipped |
| CF | configuration | 001 invalid table · 002 below floor · 003 weakening setting · 004 override file · 005 rerun plugin · 006 member without table · 007 `gate.yml` invalid · 008 bootstrap off without identities · 009 judging gate is not the gate of the base commit (§4.16) |
| MU | mutation | 001 score below `mutation_min` · 002 backend failed or cannot run · 003 notice: nothing to mutate, no changed file holds a function body |
| CV, ST, LC, GF, AG, WF | coverage, tool step, licenses, generated, agents, workflows | as named in §4.12 to §4.14; WF 001 to 005 |

Exit code 2 covers CF007, CF008, RF003, RT005, AG007 and unreadable inputs; exit code 3 covers TF009, TF011, MU002, GF002 and
tool or git failures; every other error finding exits 1.

## 7. Non-goals

- The owner digest workflow ([process/12](../../../../design/process/12-operations.md) §7): it needs issues, the GitHub
  API with write permission, and identities; in bootstrap mode the owner's list is the owner queue of `BUILD-STATUS.md`
  (decision D-1). It gets its own spec when identities exist.
- Provider calls of CI reviewers, posting under the reviewer identity, and the monthly seeded-defect audit (process/12
  §5). 0.1 pins the prompts and the job; the providers wait for the owner's choice (OQ-3).
- Release automation (process/07 §3), Dependabot configuration, labels, branch protection and repository settings.
- C# build and test jobs, fork pull requests, checking whether an issue is open, the ten-working-day limit of flaky-test
  quarantine (process/12 §3), detection of client or project names, SBOM generation.
- Auto-fixing: the gate edits only the files of `agents render` and `ratchet --update`.
- Verifying `max_sessions`.

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| The gate gives false assurance: `awaiting owner` read as "passed" | r3 | Distinct status, notice and summary text; `BUILD-STATUS.md` owner queue; spec §4.16 |
| A pull request weakens the gate it runs under | r3 | The gate of the base commit judges every pull request (§4.16, AC65 to AC68); protected paths; tight tool configuration (AC49) |
| Expression injection through the pull request title or body | r3 | Event file only, WF003, no shell |
| A leaked secret or token in logs or in findings | r3 | Fingerprints only (AC46), no token printing, `contents: read` permissions |
| Runtime dependencies | r3 | Package-local ADR for each; license check; `uv audit` |
| False positives of FB005 or the imports check stall work | r3 | Closed list of exceptions in §4.8; structured messages with the rule id; owner questions Q5, Q9 |
| Test-first cannot isolate the base (editable install shadows `PYTHONPATH`) | r3 | Import probe (TF011); verified by the first CI run of the job and recorded in `docs/local-testing.md` |
| Rules drift from the process documents | r3 | The floors table and rule lists cite their source; reviewers compare; Q3 lists the process changes needed |
| Windows differences (paths, line endings, git) | r3 | POSIX path handling, LF normalization, the Windows job on pushes, local test list |

## 9. Test strategy

Layers: unit tests of pure checks with fake ports; integration tests that build a temporary git repository (fixture
`make_repo`: `git init`, local identity, fixed dates, commits, branches, worktrees) and run a command through `cli.main`;
property tests (Hypothesis, `derandomize=True`) for glob matching, workflow-command escaping and the placeholder
scanner. No network, no real clock, no real GitHub; `ruff`, `mypy`, `coverage` and `pytest` run for real only on toy
projects in temporary directories (one test per tool step). Test files sit in `tests/unit/` and `tests/integration/`.

| Criteria | Layer | Planned tests |
|---|---|---|
| AC1 | unit | `test_cli.py::test_exit_codes`, `test_report.py::test_json_result_schema` |
| AC2, AC3 | unit | `test_report.py::test_awaiting_owner_notice_and_summary`, `test_modes.py::test_normal_mode_never_awaits` |
| AC4, AC5 | unit | `test_modes.py::test_mode_only_from_gate_yml`, `::test_bootstrap_off_needs_identities` |
| AC6 to AC11 (with AC10a and AC10b), AC13 | integration and unit | `test_gate_check.py::test_valid_pull_request_passes`, `::test_plan_task_line_errors`, `::test_plan_not_on_gate_branch`, `::test_unknown_task`, `::test_file_outside_globs_including_rename`, `::test_changelog_and_local_testing_in_scope`, `::test_ratchet_baseline_in_scope` (T14b; one case each for the AC10b rules: in scope, other package count, version change, key added, removed or renamed, lowering of another package, root-only anchor), `::test_budget_counting`, `test_frontmatter.py::test_plan_front_matter_rules` |
| AC12, AC14 to AC18 | integration | `test_gate_check_docs.py::test_spec_plan_pull_request_only`, `::test_lane_branch`, `::test_none_reasons`, `::test_status_approved`, `::test_protected_paths_awaiting_owner`, `::test_gate_branch_merge` |
| AC19 to AC21a | integration | `test_risk_floor.py::test_union_of_maps_and_commits`, `::test_risk_sets_and_body_line`, `::test_invalid_map`, `::test_none_reason_takes_the_body_risk_line` (T27) |
| AC22, AC25, AC26, AC28 | integration | `test_test_first_selection.py::test_exempt_types`, `::test_no_test_commit_and_mixed_commit`, `::test_refactor_and_test_types`, `::test_tests_first_files` |
| AC23, AC24, AC27 | integration | `test_test_first_run.py::test_red_green`, `::test_passes_at_base_and_fails_at_head`, `::test_base_isolation_and_cleanup` |
| AC29 to AC37 | unit | `test_forbidden_<rule>.py` (one file per rule: flagged case, permitted neighbour), `test_forbidden_scope.py::test_spikes_tests_and_waivers` |
| AC38 to AC41 | unit and integration | `test_ratchet.py::test_counts_and_rise`, `::test_skip_xfail_reasons`, `::test_json_raise_vs_base`, `::test_suppression_issue_reference` |
| AC42 to AC45 | unit | `test_imports.py::test_layers`, `::test_public_modules`, `::test_declared_and_sasaah_and_third_party`, `::test_cycle` |
| AC46 | unit | `test_secrets.py::test_range_scan_no_echo`, `::test_allowlist_fingerprint` |
| AC47 to AC54 (with AC53a) | unit and integration | `test_check.py::test_step_order_and_aggregate`, `test_config.py::test_floors`, `::test_weakening_rules`, `test_coverage.py::test_line_and_branch_separate`, `::test_deselection_fails`, `test_licenses.py::test_allowed_unknown_exception`, `test_generated.py::test_freshness`, `test_mutation.py::test_changed_modules_only`, `test_workspace.py::test_member_without_table`, `test_tool_steps.py::test_stale_lock_is_st001`, `test_mutation.py::test_zero_mutants_is_nothing_to_mutate` (T29) |
| AC55 to AC58 | unit | `test_agents.py::test_render_byte_exact`, `::test_placeholder_errors`, `::test_template_version`, `::test_keys_skeleton`, `test_agents_drift.py::test_drift_unmanaged_and_pointer` |
| AC59 to AC63 | unit | `test_ci_files.py::test_jobs_triggers_and_local_actions`, `::test_gate_action_runs_only_check` (T28), `::test_security_and_build_commands`, `::test_windows_job_only_on_push`, `::test_pr_jobs_base_first_steps`, `test_workflows_lint.py::test_pin_permissions_injection_trigger`, `test_review.py::test_prompt_hashes_and_modes`, `test_windows_tests.py::test_declared_paths` |
| AC64 | CI | the CI run of the last task's pull request |
| AC65 to AC67 | unit and integration | `test_gate_root.py::test_policy_from_gate_root_not_head`, `::test_provenance_rules`, `::test_head_run_in_both_modes` |
| AC68 | unit | `test_workflows_lint.py::test_ci_shape_base_first` |

## 10. Version impact

First version: `0.1.0` (pre-1.0: a breaking change bumps the minor version and is flagged `BREAKING` in the
changelog, process/07 §1). The diagnostic codes, exit codes, `.gate/` file formats and the `[tool.eng-gate]` keys are the
public interface. Tag `eng-dev-gate-v0.1.0` after the owner's approval; nothing is published to a package index.
Every workspace package pins the gate as a workspace member during incubation.

## 11. Open questions

| Question | Owner | Answer |
|---|---|---|
| Q1. Runtime dependencies: PyYAML (YAML), Pydantic (boundary models, process/04 §5), ruff, mypy, pytest and coverage (pinned by the gate so packages cannot choose weaker versions). Approve through the package-local ADR created in task T1 (process/04 §7) | Owner | Recommend: approve. All five licenses are expected to be on the allowed list; the license check verifies it |
| Q2. Process/05 §2 has no row for development tools. The gate uses 95 and 90 for itself and 80 for any declared `mutation_min`. Add a `tool` row to process/05 §2? | Owner | Recommend: yes, with these values |
| Q3. Process changes this spec relies on (not made here, since this change touches two files): risk as a set in plan and spec front matter and templates; `ci`, `release` and spike-only exemptions and the `test:` handling in process/05 §9; the `Plan-Task: none (<reason>)` forms in the pull request template; `pragma: no branch` in the ratchet bucket; composite actions in place of reusable workflows in process/11 §4 and §5; `.gate/gate.yml` and `.gate/forbidden.yml` in process/11 §1. Propose them as a process pull request | Lead, owner | Recommend: one process change after this spec is reviewed; list every repository whose `AGENTS.md` needs re-rendering (rule 7) |
| Q4. Mutation backend: mutmut or cosmic-ray, and whether either runs on Windows (not verified here). If neither does, mutation runs on Linux CI only and the local step reports `skipped` | Lead (task T20) | Recommend: decide in T20 with a short check, record it in a package ADR |
| Q5. FB005 exceptions A2 (integer index) and A3 (integer compared with `len`), and ruling out any exception for `ctx.attempts(n)`, exponents and input bounds. Align the callable name `Cited` with the `eng-contract` spec | Owner | Recommend: keep A2 and A3, no further exceptions; `eng-contract` and `eng-harness` specs add cited callables to `cited.callables` |
| Q6. The "bandit subset" of process/11 §3 is undefined. The gate selects all S rules and ignores `S101` in tests | Owner | Recommend: accept; refine when the first findings show which S rules are noise |
| Q7. During bootstrap, how does the owner approve a spec or plan? A pull request that sets `approved` fails (GC014) | Owner | Recommend: the owner commits the status change directly to the gate branch (pushes run `gate`, not `gate-check`), or switches bootstrap off first |
| Q8. The gate of the base commit judges every pull request (lead decision, §4.16). The workflow file itself is still loaded from the pull request. Should the owner add a repository ruleset or branch protection with the job ids as required checks once identities exist (process/11 §6)? | Owner | Recommend: yes; WF005 and protected paths are the controls until then |
| Q9. Import rules for `product` packages are not defined in 03 §3; only IM002 to IM006 apply to them | Owner | Recommend: define them in the spec of the first Python product |
| Q10. Host SDK module names beyond the initial list (ETABS, SAFE, SAP2000 and IDEA StatiCa Python-side names) are not known with certainty | Owner | Recommend: add them to `.gate/forbidden.yml` after the first local run shows what the host bridges import. Recorded gap |
| Q11. In bootstrap mode, should `gate-check` require a non-empty "Review" section in the pull request body as evidence of the subagent review (decision D-6)? | Lead | Recommend: yes after the first merged tasks; one line of configuration, not in 0.1 |
| Q12. `ctx.attempts` bounds, quarantine expiry horizon (process/12 §3) and issue open-ness checks are not enforced in 0.1 | Owner | Recommend: leave to review; revisit with `eng-harness` |
