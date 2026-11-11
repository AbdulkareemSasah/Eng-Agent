# HANDOFF: resume point of the v1 build

The lead engineer's resume point for the next agent (any tool), written on 2026-11-11 when the build was paused at the
owner's request. Read this file, then [BUILD-STATUS.md](BUILD-STATUS.md), then `git log origin/build/v1`, before doing anything.

- Integration branch: `build/v1` (bootstrap mode, [ADR-0028](design/docs/adr/0028-build-v1-in-this-repository.md)). Never push to `main` or `master`.
- Resume commit: see the "Resume commit" line in section 1 (the last merge before the pause).
- Remaining work, machine-readable: [ops/remaining-tasks.json](ops/remaining-tasks.json) (one entry per unmerged work item).
- Local CI (the definition of done while GitHub Actions is unavailable, D-23): [ops/localci.py](ops/localci.py), described in [ops/README.md](ops/README.md).

## 1. Where the build stands

- Resume commit: `adfc396 feat(eng-harness): machine-level host-instance lock and process guard (B-126) (#254)` on `build/v1`.
- Plan tasks merged: 147 of 290 (50.7 %), plus 80 documents amendments.

| Package | Merged | Total |
|---|---|---|
| eng-contract | 19 | 19 |
| eng-dev-gate | 39 | 41 |
| structural-codes | 28 | 36 |
| eng-harness | 61 | 194 |

Phases: 0 done; 1 (engine, edit cycle) and 2 (codes, SAFE, providers, footing workflow) in progress; 3 and 4 (Revit,
SAP2000, columns, IDEA) started only in structural-codes (column checks skeleton). Nothing that needs a host program is
claimed as working: every such step is in [LOCAL-TESTING.md](LOCAL-TESTING.md) and the packages' `docs/local-testing.md`.

## 2. How one work item goes from task to merge (keep doing it this way)

1. Pick a task from `ops/remaining-tasks.json` whose `pending_deps` are all merged (a dependency is a plan task key such
   as `E.T12` or a documents amendment key such as `DOC.ET12`; check `git log origin/build/v1` for its work item id).
2. Branch from `origin/build/v1` with the entry's `branch` name. First commit: only the failing tests named in the plan
   task's `tests_first` (gate test-first: they must fail at the merge base for the right reason). Then the code. Stay
   inside the plan task's `files` and `max_changed_lines` (gate GC008, GC009; the task cap is 400 lines, GC005). A task
   that cannot fit is split by a reviewed plan amendment (lead decision D-12), never stretched.
3. Run `uv run eng-gate check --package <package>` (the full gate, including mutation) before pushing.
4. Open a pull request into `build/v1` titled as the entry's `prTitle`. The body follows the repository template and
   must hold `Work-Item: B-NNN`, `Plan-Task: <plan path>#T<n>` (documents amendments: `Plan-Task: none (spec and plan)`)
   and `Risk: <the plan's full risk set>` (gate RF002: the line must name the plan's front-matter `risk` set exactly).
5. Review by an agent that did not write the change (bootstrap mode). Engineering pull requests (code-pack checks,
   harness calcs) also get adversarial verification: one verifier per lens (sources, oracle; documents: consistency,
   implementability; gate code: enforcement). Record every review round in the pull request body under "Review".
   Documents amendments follow lead decision D-28: after three verifier rounds, one convergence round with the
   smallest edits; leftover inconsistencies in untouched lines go to a follow-up amendment.
6. Local CI on the head merged with the latest `build/v1`: `python3 ops/localci.py start --pr-json <file>`, then
   `wait --run-dir <dir>` until PASS (ops/README.md). Write the summary table into the body under "Local CI".
7. Squash-merge on GitHub with the title `<prTitle> (#<number>)`. Never merge without a PASS on the current head.

The rules that never bend are in [AGENTS.md](AGENTS.md) (golden rules, the "Never" list A1 to A22). In particular: no
invented engineering number (cite the code clause or take it from the design basis; an uncertain clause is an explicit
`NOT_IMPLEMENTED` gap with a test), no escape-hatch tool in any allowlist (`csi_run_script`, `csi_db_tables_apply`, any
script runner or table writer, ADR-0008), uv only, no force pushes or history rewrites, nothing from Microsoft Agent
Framework or the earlier Sasaah Agent design system, no MCP server built for a host program (the harness is a client of
the Sasaah servers, ADR-0024), Sasaah is read-only (changes only through a branch and pull request there, never merged
by an agent).

## 3. In flight at the pause (finish these first)

| Work item | Task | State | What is left |
|---|---|---|---|
| B-434 | DOC.ET12 Engine plan T12 gains _runner.py and the step_started action; spec 4.3 | PR #263 | finish review, verifiers and local CI, then merge |
| B-435 | DOC.HTMLFRAG Interface plan 0006: new T2b (fragment links in _html.py) before T12;  | PR #261 | finish review, verifiers and local CI, then merge |
| B-437 | DOC.CALCRULES Calcs spec 0003 4.3 and plan 0003 T7: allowed imports, recursive rules | PR #260 | finish review, verifiers and local CI, then merge |
| B-438 | DOC.GATEA4 Gate spec 4.8 FB005 form A4 (version keyword of versioned callables) a | not started | write it |
| B-440 | DOC.PROVT1 Providers plan 0009 T1: the license evidence for cffi and regex (propo | not started | write it |
| B-442 | DOC.Q20 Structural-codes core: CheckMeta.version (integer, default 1); footing | PR #264 | finish review, verifiers and local CI, then merge |
| B-436 | I.T2b In-page fragment links in the HTML builder: fragment(SafeToken) render | not started | write it; waits for DOC.HTMLFRAG |
| B-146 | C.T7 Calc 1, model fingerprint, with the canonical-state helper | branch pushed | continue on the branch (lead note); waits for DOC.CALCRULES, G.T39 |
| B-220 | P.T1 Dependencies, provider errors, configuration, network guard | PR #253 | finish review, verifiers and local CI, then merge; waits for DOC.PROVT1 |
| B-439 | G.T39 FB005 form A4: an integer literal as the version keyword of a listed v | not started | write it; waits for DOC.GATEA4 |
| B-443 | K.T15 CheckMeta.version: an integer check version, default 1, carried to the | not started | write it; waits for DOC.Q20 |
| B-330 | Z.T1 Shared column section model, column preconditions, shared constants mo | branch pushed | continue on the branch (lead note) |
| B-394 | X.T3 Calc harness.footing_subjects and the footing calc package | PR #256 | finish review, verifiers and local CI, then merge; waits for C.T7 |

## 4. Order of the remaining work

1. The documents amendments of section 3 that are not merged yet (each entry in `ops/remaining-tasks.json` with kind
   `docs` carries its full instructions). They unblock the tasks below.
2. The three small code tasks they create: B-436 (I.T2b, fragment links in `_html.py`), B-439 (G.T39, gate FB005 form
   A4), B-443 (K.T15, `CheckMeta.version`).
3. The tasks that were blocked on them, each with a lead note in its entry: B-111 (E.T12), B-186 (I.T12), B-146 (C.T7,
   work already on its pushed branch), B-394 (X.T3, open pull request, rerun the gate after C.T7), B-393 (X.T2),
   B-330 (Z.T1, work already on its pushed branch), B-220 (P.T1, see section 5).
4. Then by plan, each in its `depends_on` order: engine E.T13 to E.T19; servers S.T10 to S.T20 (S.T15 stays
   unregistered: blocked on the owner and local tests); interface I.*; calcs C.T8 to C.T12; decisions D.T7 to D.T10;
   providers P.T2 to P.T10; templates B.T10; edit cycle W.T2 to W.T12; footing workflow X.T4 to X.T13; SBC overlay Y.T2,
   Y.T3; ACI column checks Z.T2 to Z.T5; then phase 3 and 4 plans no lane has started: SAFE adapter F.T1 to F.T8 (plan
   0008), Revit adapter R.T1 to R.T15 (plan 0011), SAP2000 adapter A.T1 to A.T7 (plan 0012), column workflow G.T1 to
   G.T15 (plan 0013), IDEA adapter H.T1 to H.T9 (plan 0014).

## 5. Open items that need a person

- PR #253 (B-220, providers T1) is superseded: its branch history holds a secret-like test literal (commit aa6b855) that
  the gate's secrets step scans and no new commit can remove, and history rewrites are not allowed. B-220 restarts on the
  fresh branch named in its entry; close #253 when the new pull request is open.
- Owner decisions queued (BUILD-STATUS section 6): OQ-Q43 (report machine time and "left open"); OQ-Q44 (basis paths are
  lowercase only, the unit suffixes are mixed case; recommendation: allow the contract suffixes in the last segment;
  edit-cycle W.T2 and W.T8 wait for it); spec 0006 Q20 (how `run` gets its run id; interface I.T18 binds every other
  default meanwhile); engine spec Q26 to Q29 (B-427) and the B-434 decisions; gate FB005 form A4 (B-438, amends the
  owner's Q5 "no further exceptions"); the license exceptions of cffi (MIT-0) and regex (Apache-2.0 AND CNRI-Python)
  with their proposed ADR (B-440); `CheckMeta.version` (B-442); `SERVER_CHECK_FAILED` versus `HOST_NOT_CONNECTED` for a
  failed build check on a restart (S.T6b, recommendation: keep `HOST_NOT_CONNECTED` until S.T19).
- Not run in the build container, owner items: `uv audit --locked` (api.osv.dev is outside AGENTS.md section 9) and the
  Windows CI job; every live host step in LOCAL-TESTING.md.

## 6. Operational notes

- A fresh container with many loose git objects makes `git fetch` stall in its connectivity check (seen 2026-11-11):
  `git repack -d` fixes it (P-56).
- Agent worktrees live under `.claude/worktrees/` (ignored). Remove only clean ones whose commits are on GitHub
  (`git worktree remove`, never `--force`); 71 dirty or unpushed ones were kept at the pause.
- Load-sensitive tests: the servers session tests with 1 s timeouts failed under heavy load (P-54); S.T6b (B-351)
  enlarged their bounds without relaxing any assertion. Run at most a few gate runs at once on a 4-CPU machine.
- The registry generators, workflow scripts and the run history of local CI stayed in the lead's scratch space; what the
  next agent needs from them is in `ops/`.
