# HANDOFF: resume point of the v1 build

The lead engineer's resume point for the next agent (any tool), written on 2026-11-11 when the build was paused at the
owner's request. Read this file, then [BUILD-STATUS.md](BUILD-STATUS.md), then `git log origin/build/v1`, before doing anything.

- Integration branch: `build/v1` (bootstrap mode, [ADR-0028](design/docs/adr/0028-build-v1-in-this-repository.md)). Never push to `main` or `master`.
- Resume commit: see the "Resume commit" line in section 1 (the last merge before the pause).
- Remaining work, machine-readable: [ops/remaining-tasks.json](ops/remaining-tasks.json) (one entry per unmerged work item).
- Local CI (the definition of done while GitHub Actions is unavailable, D-23): [ops/localci.py](ops/localci.py), described in [ops/README.md](ops/README.md).

## 0. Resume prompt for a cloud agent (2026-11-11, second pause)

The owner moved the build to a cloud machine: local CI (mutation runs of 15 minutes and more) froze the owner's
workstation, which also runs AutoCAD. Paste this as the first message of a cloud Claude Code session on this repository:

> You are the lead engineer resuming the v1 build of the Eng-Agent platform (repository AbdulkareemSasah/Eng-Agent,
> branch `build/v1`). Talk to the owner in Arabic; write code, commits and documents in English. Read HANDOFF.md
> (all of it, section 0 first), AGENTS.md, BUILD-STATUS.md, ops/README.md and ops/remaining-tasks.json, then
> `git log origin/build/v1 -15`. Work the order of HANDOFF.md sections 3 and 4 without stopping: for each item, write it
> (or have a subagent write it) on its entry's branch with a `test:` first commit, review the full diff yourself
> (scope, budget, test-first; engineering content: every constant cited, expected values recomputed by hand from the
> clause spec, X/Y swaps and boundary sides), run `uv run eng-gate check --package <package>`, open the pull request
> with Work-Item, Plan-Task and the plan's full Risk line, record the review in its body, run
> `python3 ops/localci.py start --pr-json <file>` and `wait` until PASS on the current head, write the summary under
> "Local CI", squash-merge as `<prTitle> (#N)`. At most two full gate runs at once. Never invent an engineering
> number; stop and ask the owner only for AGENTS.md section 7 items and the open questions of HANDOFF.md section 5
> (queue them in BUILD-STATUS section 6 and continue with other items meanwhile). At each pause update HANDOFF.md and
> BUILD-STATUS.md, commit them as docs(build), push, and tell the owner the percentage done and what comes next.

Notes for the cloud session:
- The pull requests in section 3 were opened, reviewed and fixed on the owner's workstation (writers: Cursor CLI with
  Composer 2.5 and Grok 4.7; reviews by the lead). What each still needs is in section 3.
- `ops/localci.py` needs Linux (`fcntl`, `bash`); the gate's mutation step does not run on Windows (ADR-0002).
- A Windows workstation is not a place for local CI (D-29 in BUILD-STATUS). If the owner's machine is used again, run
  only light work there.

## 1. Where the build stands

- Resume commit: `602968c docs(eng-dev-gate): FB005 form A4, an integer version keyword of a listed callable; plan T39 (B-438) (#267)` on `build/v1`.
- Plan tasks merged: 149 of 290 (51.4 %), plus 84 documents amendments.

| Package | Merged | Total |
|---|---|---|
| eng-contract | 19 | 19 |
| eng-dev-gate | 39 | 41 |
| structural-codes | 29 | 36 |
| eng-harness | 62 | 194 |

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
| B-438 | DOC.GATEA4 Gate spec 4.8 FB005 form A4 | merged (#267, 602968c) | done |
| B-437 | DOC.CALCRULES Calcs spec 0003 4.3 and plan 0003 T7: allowed imports, recursive rules | PR #260 | convergence round done (3de8b96, reviewed: APPROVE); record the review in the body, local CI, merge |
| B-440 | DOC.PROVT1 Providers plan 0009 T1: the license exceptions of cffi and regex | PR #270 | written and reviewed (APPROVE, recorded in the body); local CI, merge |
| B-146 | C.T7 Calc 1, model fingerprint, with the canonical-state helper | branch pushed | continue on the branch (lead note); waits for DOC.CALCRULES, G.T39 |
| B-220 | P.T1 Dependencies, provider errors, configuration, network guard | PR #253 superseded | restart on the fresh branch of its entry (section 5), then close #253; waits for DOC.PROVT1 |
| B-439 | G.T39 FB005 form A4: an integer literal as the version keyword of a listed v | not started | write it; waits for DOC.GATEA4 |
| B-330 | Z.T1 Shared column section model, column preconditions, shared constants mo | PR #269 | lead review with sources and oracle lenses done (notes below), fix 502a2a8 pushed; record the review in the body, local CI, merge |
| B-393 | X.T2 Code-pack route of the CalcPort and the structural-codes workspace dep | PR #268 | finish review, verifiers and local CI, then merge |
| B-394 | X.T3 Calc harness.footing_subjects and the footing calc package | PR #256 | finish review, verifiers and local CI, then merge; waits for C.T7 |

### Notes on the items in flight (second pause)

- **B-437 (PR #260)**: the D-28 convergence round fixed the three verifier findings (AC3 now names the
  `calcs/__init__.py` lock-file exception; the T7 comment cites gate spec 4.5 step 6, AC10b; B-438 is merged, so its
  FB005 form A4 references resolve). Lead review: APPROVE. Merge it, then C.T7 (B-146) can continue once gate T39
  (B-439) merges.
- **B-440 (PR #270)**: plan-only amendment; the section 3 sentence that called the license exceptions a precondition
  outside every task was aligned with T1's new file list. Owner note in the body: two package ADRs share number 0001.
- **B-330 (PR #269)**: lead review of `_column.py` against the axial-flexure and maximum-axial clause specs: every
  constant matches its cited clause (Es 20.2.2.2; Table 21.2.2 phi rows; Table 22.4.2.1; 6.2.5(a) and 6.2.5.1(b);
  Table 22.2.2.4.3); SP-1, CS S6, CS S7 and the CP boundaries recomputed by hand agree with the tests to the last digit.
  Two oracle findings fixed by test-only commit 502a2a8: the `SHORT_COLUMN` test had only `b < h`, so a mutant using
  `b_mm` alone passed (mirrored `h < b` case added); the `d_j < a` boundary of the displaced concrete had no test (added
  at `a == d_1 == 250`). LOW for Z.T2: the column inputs need `n_bars_h >= 2` (CS S1 divides by `n_bars_h - 1`).
  Record this review in the body (the writer was the earlier session), then local CI and merge.
- **B-393 (PR #268)**: written and reviewed with no blocking finding in the earlier session; its body has no Review
  section yet. Record a review (read the diff again: `_calc/_code_packs.py`, `_calc/_port.py`), local CI, merge.
- **Ready to write now** (every dependency merged): B-111 (E.T12), B-129 (S.T10), B-137 (S.T18), B-139 (S.T20), B-186
  (I.T12), B-280 (G.T1) and B-439 (G.T39, gate FB005 form A4, unblocked by B-438). Cursor writers were started on the
  workstation and stopped before writing anything; nothing of them is on GitHub.

## 4. Order of the remaining work

1. Merge the open pull requests of section 3: B-437 (#260), B-440 (#270), B-330 (#269), B-393 (#268). B-438 is merged
   (#267).
2. Gate T39 (B-439, FB005 form A4), now unblocked. Already merged: B-436 (I.T2b fragment links) and B-443 (K.T15
   `CheckMeta.version`).
3. The tasks that were blocked, each with a lead note in its entry: B-111 (E.T12, ready now), B-186 (I.T12, ready
   now), B-393 (X.T2, PR #268, reviewed: local CI and merge), B-330 (Z.T1, PR #269: review), B-146 (C.T7, work on its
   pushed branch, after B-437 and B-439), B-394 (X.T3, PR #256, after C.T7), B-220 (P.T1, after B-440, see section 5).
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
