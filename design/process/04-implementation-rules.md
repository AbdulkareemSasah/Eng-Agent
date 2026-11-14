# 04. Implementation Rules

## 1. Research before writing

Before writing new code, look for: an existing tool or function in the repository, an existing library with an allowed
license, and the host program's own API or feature. Record what was found in the plan. Prefer a proven library over new
code, and prefer the host's own capability over re-implementing it.

## 2. Test-driven development (mandatory)

For every task:

1. **Red**: write the test that expresses one acceptance criterion; run it; see it fail for the right reason.
2. **Green**: write the smallest code that makes it pass.
3. **Refactor**: improve structure with all tests green.

Defects start with a failing regression test. Refactors start with green tests and must not change them. Reviewers
reject pull requests whose tests do not cover the acceptance criteria or that were obviously written after the fact to
match the implementation's output (tests that assert whatever the code returns).

## 3. Branches and commits

- Trunk-based: `main` is always releasable. Branches are short-lived: `<type>/<issue-number>-<slug>`, for example
  `feat/42-etabs-add-frames`.
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `build:`, `ci:`, `chore:`, `perf:`, with
  scope, for example `feat(tools): add etabs_add_frames`. A breaking change uses `!` and a `BREAKING CHANGE:` footer.
- Commits written with an AI agent carry an `Assisted-by: <model family>/<model>` trailer. CI uses it to require a
  reviewer of a different model family for R1 and R2.
- The Developer Certificate of Origin (`Signed-off-by:`) is required once a repository is public and accepts outside
  contributions; the owner signs off on squash merges. While private, it is not required.
- Each task's first commit is `test: ...` with the failing tests only; CI checks that these tests fail on the base
  branch and pass at the head ([05](05-testing-and-verification.md) §9).
- One logical change per commit. No "WIP" commits on `main` (pull requests are squash-merged).
- Log-only commits ([ADR-0034](../docs/adr/0034-task-log-by-default.md) D5, which defines them) are the one kind of
  commit that reaches the integration branch without a pull request after bootstrap: pushed by the harness task-log
  push command, fast-forward, never mixed with any other path; their subject is `docs(tasklog): ...`. In bootstrap
  mode the lead's bookkeeping commits named in the workspace root rules also do.

## 4. Pull request size

- At most about 400 changed lines of non-test, non-generated code per pull request. Larger work is split by the plan.
- One issue per pull request. No unrelated changes ("while I was here" edits are separate pull requests).

## 5. Python standards

| Topic | Rule |
|---|---|
| Tooling | uv only: `uv sync`, `uv add`, `uv add --dev`, `uv run`, `uv lock`, `uv build`, `uv publish`, `uvx`. Never `pip install`, never a manually created virtual environment |
| Formatting and lint | `ruff format` and `ruff check` with the repository's configuration; no per-line suppression without a reason and an issue link |
| Types | `mypy --strict` passes; `Any` only at true boundaries, commented; no `# type: ignore` without a reason and an issue link |
| Models | Pydantic v2 for every boundary model (tool inputs, kinds, envelopes, templates, decision states) |
| Errors | Raise typed exceptions that map to contract error codes; never swallow exceptions; no bare `except`; no "return None on failure" |
| Logging | Structured logging through the repository's logger; no `print`; never log secrets or full payloads |
| State | No global mutable state; dependencies passed explicitly; host access only through ports |
| Numbers | No bare numeric literals for engineering constants: use `Cited` values or design-basis references |
| Functions | Small and single-purpose; pure core, side effects at the edges |
| Docstrings | Public functions and classes have docstrings stating purpose, units and errors |
| Async | Async only where I/O requires it; no blocking calls in async code |

## 6. C# standards (add-ins and plugins only)

| Topic | Rule |
|---|---|
| Project | Nullable reference types enabled; warnings as errors; .NET analyzers at the recommended level |
| Scope | Thin executors: no business rules, no unit conversion (except where the host forces it), no tool schemas |
| Threading | Host API calls only on the thread the host requires; no blocking of the host UI thread beyond a request's budget |
| Errors | Every host failure is caught, mapped to a wire error with the host's message, and never shown as a dialog |
| Resources | Deterministic disposal of host objects; no static mutable state except what the host's add-in model requires |
| Tests | Logic that can be separated from the host is unit-tested; host behavior is covered by live acceptance |

## 7. Dependencies

- A new **runtime** dependency needs an ADR (repository-local is enough unless it crosses repositories): purpose,
  alternatives, license, maintenance health, size.
- Allowed licenses: MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0. Anything else needs an ADR approved by the owner.
- Development dependencies may be added in a pull request with a one-line justification.
- `uv.lock` is committed; upgrades are separate pull requests with tests run.

## 8. Forbidden

- Escape-hatch tools or code paths: script execution, expression evaluation, arbitrary API forwarding, reflection-based
  setters, database-table writes ([ADR-0008](../docs/adr/0008-tool-naming-toolsets-no-escape-hatches.md)).
- Copying code between repositories. Shared needs go to `eng-contract` or a new library by ADR.
- Committing vendor binaries, generated vendor wrappers, secrets, personal paths or real client data.
- Adding, changing or deleting `tasklog/**` in a pull request.
- Pushing directly to the integration branch anything but a log-only commit (bootstrap bookkeeping excepted, §3).
- Disabling, skipping or weakening tests, lint rules, type checks or CI jobs to get a green build.
- Editing generated files by hand.
- Changing CI configuration, `CODEOWNERS`, `AGENTS.md`, test and tool configuration, gate files, code-pack approvals,
  decision policies or templates shipped with the harness without owner review (enforced by `CODEOWNERS`,
  [06](06-review-and-merge.md) §4).
- Adding suppressions (`noqa`, `type: ignore`, `pragma: no cover`, skip or expected-failure markers) beyond the
  ratchet ([05](05-testing-and-verification.md) §3).
- Running code-modifying helper tools (automatic build fixers, dead-code removers, formatters with unsafe fixes) without
  reviewing their full diff before committing.
- Writing outside the repository, into program folders, add-in folders or deployment targets.
- Changing operating-system security settings, ACLs, ownership or integrity levels.
